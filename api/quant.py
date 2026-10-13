"""Kairos quant toolkit: backtests, metrics, parameter grids, cointegration,
portfolio optimisation and conformal forecast bands.

Pure NumPy/pandas. If the optional C++ module `fastbt` is built, the heavy
loops (position backtest, MA parameter grid) run in C++ instead.
"""
import math
import time

import numpy as np
import pandas as pd

try:
    import fastbt  # built from cpp/fastbt.cpp, see build_cpp.sh
    HAS_CPP = True
except Exception:
    fastbt = None
    HAS_CPP = False

TD = 252  # trading days per year


# ════════════════════════════════════════════════════════════ indicators
def sma(x, n):
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    if n <= 0 or len(x) < n:
        return out
    c = np.cumsum(np.insert(x, 0, 0.0))
    out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def ema(x, n):
    return pd.Series(np.asarray(x, float)).ewm(span=n, adjust=False).mean().to_numpy(copy=True)


def rsi(x, n=14):
    d = np.diff(np.asarray(x, float), prepend=np.nan)
    g = pd.Series(np.where(d > 0, d, 0.0)).ewm(alpha=1 / n, adjust=False).mean()
    l = pd.Series(np.where(d < 0, -d, 0.0)).ewm(alpha=1 / n, adjust=False).mean()
    r = 100 - 100 / (1 + g / l.replace(0, np.nan))
    r = r.fillna(100.0).to_numpy(copy=True)
    r[:n] = np.nan
    return r


def rolling_std(x, n):
    return pd.Series(np.asarray(x, float)).rolling(n).std(ddof=0).values


def rolling_max(x, n):
    return pd.Series(np.asarray(x, float)).rolling(n).max().values


def rolling_min(x, n):
    return pd.Series(np.asarray(x, float)).rolling(n).min().values


# ════════════════════════════════════════════════════════════ strategies
# Every strategy returns a position array p where p[t] is the position decided at
# the close of day t and held over day t+1. No look-ahead.
STRATEGIES = {
    "ma_cross": {
        "name": "MA Crossover",
        "desc": "Long when the fast SMA is above the slow SMA. Classic trend following.",
        "params": [
            {"key": "fast", "label": "Fast SMA", "default": 20, "min": 2, "max": 150, "step": 1},
            {"key": "slow", "label": "Slow SMA", "default": 50, "min": 5, "max": 300, "step": 1},
        ],
        "short": True,
        "grid": {"x": ["fast", [5, 10, 15, 20, 25, 30, 40, 50]],
                 "y": ["slow", [30, 50, 75, 100, 125, 150, 200]]},
    },
    "rsi_mr": {
        "name": "RSI Mean Reversion",
        "desc": "Buy when RSI drops below the lower level, sell when it rises above the upper level.",
        "params": [
            {"key": "period", "label": "RSI period", "default": 14, "min": 2, "max": 50, "step": 1},
            {"key": "lower", "label": "Buy below", "default": 30, "min": 5, "max": 50, "step": 1},
            {"key": "upper", "label": "Sell above", "default": 70, "min": 50, "max": 95, "step": 1},
        ],
        "short": False,
        "grid": {"x": ["lower", [15, 20, 25, 30, 35, 40, 45]],
                 "y": ["upper", [50, 55, 60, 65, 70, 75, 80]]},
    },
    "bollinger": {
        "name": "Bollinger Reversion",
        "desc": "Buy a close below the lower band, exit when price gets back to the middle band.",
        "params": [
            {"key": "window", "label": "Window", "default": 20, "min": 5, "max": 100, "step": 1},
            {"key": "k", "label": "Band width (σ)", "default": 2.0, "min": 0.5, "max": 4.0, "step": 0.1},
        ],
        "short": False,
        "grid": {"x": ["window", [10, 15, 20, 25, 30, 40, 50]],
                 "y": ["k", [1.0, 1.5, 2.0, 2.5, 3.0]]},
    },
    "macd": {
        "name": "MACD",
        "desc": "Long when the MACD line is above its signal line.",
        "params": [
            {"key": "fast", "label": "Fast EMA", "default": 12, "min": 2, "max": 50, "step": 1},
            {"key": "slow", "label": "Slow EMA", "default": 26, "min": 5, "max": 100, "step": 1},
            {"key": "signal", "label": "Signal", "default": 9, "min": 2, "max": 30, "step": 1},
        ],
        "short": True,
        "grid": {"x": ["fast", [5, 8, 10, 12, 15, 20]],
                 "y": ["slow", [20, 26, 30, 35, 40, 50]]},
    },
    "momentum": {
        "name": "Time-Series Momentum",
        "desc": "Long when the trailing return beats the threshold (Moskowitz, Ooi & Pedersen 2012).",
        "params": [
            {"key": "lookback", "label": "Lookback (days)", "default": 63, "min": 5, "max": 252, "step": 1},
            {"key": "threshold", "label": "Threshold %", "default": 0.0, "min": 0.0, "max": 20.0, "step": 0.5},
        ],
        "short": True,
        "grid": {"x": ["lookback", [10, 21, 42, 63, 126, 189, 252]],
                 "y": ["threshold", [0.0, 1.0, 2.0, 5.0, 10.0]]},
    },
    "breakout": {
        "name": "Donchian Breakout",
        "desc": "Buy a close above the prior N-day high, exit below the prior M-day low (turtle style).",
        "params": [
            {"key": "entry", "label": "Entry high (N)", "default": 20, "min": 5, "max": 200, "step": 1},
            {"key": "exit", "label": "Exit low (M)", "default": 10, "min": 2, "max": 100, "step": 1},
        ],
        "short": False,
        "grid": {"x": ["entry", [10, 20, 30, 40, 55, 80, 100]],
                 "y": ["exit", [5, 10, 15, 20, 30]]},
    },
}


def _clean_params(strategy, params):
    spec = STRATEGIES[strategy]["params"]
    out = {}
    for p in spec:
        v = params.get(p["key"], p["default"])
        try:
            v = float(v)
        except (TypeError, ValueError):
            v = float(p["default"])
        v = min(max(v, p["min"]), p["max"])
        out[p["key"]] = v if isinstance(p["step"], float) or p["step"] < 1 else int(round(v))
    return out


def positions(strategy, close, params, allow_short=False):
    c = np.asarray(close, float)
    n = len(c)
    P = _clean_params(strategy, params)
    short = allow_short and STRATEGIES[strategy]["short"]
    lo = -1.0 if short else 0.0
    p = np.zeros(n)

    if strategy == "ma_cross":
        f, s = sma(c, P["fast"]), sma(c, P["slow"])
        ok = ~np.isnan(f) & ~np.isnan(s)
        p[ok] = np.where(f[ok] > s[ok], 1.0, lo)
    elif strategy == "macd":
        m = ema(c, P["fast"]) - ema(c, P["slow"])
        sig = ema(m, P["signal"])
        p = np.where(m > sig, 1.0, lo)
        p[:max(P["slow"], P["signal"])] = 0.0
    elif strategy == "momentum":
        lb, th = P["lookback"], P["threshold"] / 100
        r = np.full(n, np.nan)
        r[lb:] = c[lb:] / c[:-lb] - 1
        ok = ~np.isnan(r)
        p[ok] = np.where(r[ok] > th, 1.0, np.where(r[ok] < -th, lo, 0.0))
    elif strategy == "rsi_mr":
        rv = rsi(c, P["period"])
        state = 0.0
        for t in range(n):
            if np.isnan(rv[t]):
                continue
            if state == 0 and rv[t] < P["lower"]:
                state = 1.0
            elif state == 1 and rv[t] > P["upper"]:
                state = 0.0
            p[t] = state
    elif strategy == "bollinger":
        mid = sma(c, P["window"])
        sd = rolling_std(c, P["window"])
        lower = mid - P["k"] * sd
        state = 0.0
        for t in range(n):
            if np.isnan(mid[t]):
                continue
            if state == 0 and c[t] < lower[t]:
                state = 1.0
            elif state == 1 and c[t] >= mid[t]:
                state = 0.0
            p[t] = state
    elif strategy == "breakout":
        hi = np.concatenate([[np.nan], rolling_max(c, P["entry"])[:-1]])
        low = np.concatenate([[np.nan], rolling_min(c, P["exit"])[:-1]])
        state = 0.0
        for t in range(n):
            if np.isnan(hi[t]) or np.isnan(low[t]):
                continue
            if state == 0 and c[t] > hi[t]:
                state = 1.0
            elif state == 1 and c[t] < low[t]:
                state = 0.0
            p[t] = state
    else:
        raise ValueError(f"unknown strategy {strategy}")
    return p, P


# ════════════════════════════════════════════════════════════ backtest engine
def strat_returns(close, pos, cost_bps=0.0, engine="auto"):
    """Daily strategy returns. held[t] = pos[t-1]; costs charged on turnover."""
    c = np.ascontiguousarray(close, dtype=float)
    p = np.ascontiguousarray(np.nan_to_num(pos), dtype=float)
    if (engine == "cpp" or (engine == "auto" and HAS_CPP)) and HAS_CPP:
        return np.asarray(fastbt.strat_returns(c, p, float(cost_bps)))
    r = np.zeros(len(c))
    r[1:] = c[1:] / c[:-1] - 1
    held = np.zeros(len(c))
    held[1:] = p[:-1]
    prev = np.zeros(len(c))
    prev[1:] = held[:-1]
    return held * r - np.abs(held - prev) * cost_bps / 1e4


def sharpe(sr):
    sr = np.asarray(sr, float)
    if len(sr) < 3:
        return 0.0
    sd = sr.std(ddof=1)
    return float(sr.mean() / sd * math.sqrt(TD)) if sd > 0 else 0.0


def metrics(sr, held=None):
    sr = np.asarray(sr, float)
    n = len(sr)
    if n < 2:
        return {}
    eq = np.cumprod(1 + sr)
    yrs = n / TD
    tot = eq[-1] - 1
    cagr = eq[-1] ** (1 / yrs) - 1 if eq[-1] > 0 and yrs > 0 else -1.0
    vol = sr.std(ddof=1) * math.sqrt(TD)
    down = math.sqrt(np.mean(np.minimum(sr, 0) ** 2)) * math.sqrt(TD)
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1
    maxdd = float(-dd.min())
    out = {
        "total_return": float(tot),
        "cagr": float(cagr),
        "vol": float(vol),
        "sharpe": sharpe(sr),
        "sortino": float(sr.mean() * TD / down) if down > 0 else 0.0,
        "max_dd": maxdd,
        "calmar": float(cagr / maxdd) if maxdd > 0 else 0.0,
        "days": n,
    }
    if held is not None:
        out["exposure"] = float(np.mean(np.asarray(held) != 0))
    return out


def extract_trades(dates, close, pos, cost_bps=0.0):
    c = np.asarray(close, float)
    p = np.nan_to_num(np.asarray(pos, float))
    trades = []
    open_t = None
    prev = 0.0
    for t in range(len(p)):
        cur = p[t]
        if cur != prev:
            if prev != 0 and open_t is not None:
                i, side = open_t
                ret = side * (c[t] / c[i] - 1) - 2 * cost_bps / 1e4
                trades.append({"entry_date": dates[i], "exit_date": dates[t], "side": "LONG" if side > 0 else "SHORT",
                               "entry": round(float(c[i]), 4), "exit": round(float(c[t]), 4),
                               "ret": float(ret), "bars": t - i, "open": False})
                open_t = None
            if cur != 0:
                open_t = (t, cur)
        prev = cur
    if open_t is not None:
        i, side = open_t
        t = len(c) - 1
        trades.append({"entry_date": dates[i], "exit_date": dates[t], "side": "LONG" if side > 0 else "SHORT",
                       "entry": round(float(c[i]), 4), "exit": round(float(c[t]), 4),
                       "ret": float(side * (c[t] / c[i] - 1) - cost_bps / 1e4), "bars": t - i, "open": True})
    return trades


def trade_stats(trades):
    if not trades:
        return {"trades": 0, "win_rate": 0.0, "avg_trade": 0.0, "profit_factor": 0.0, "avg_bars": 0.0}
    r = np.array([t["ret"] for t in trades])
    gains, losses = r[r > 0].sum(), -r[r < 0].sum()
    return {"trades": len(trades), "win_rate": float(np.mean(r > 0)), "avg_trade": float(r.mean()),
            "profit_factor": float(gains / losses) if losses > 0 else (float("inf") if gains > 0 else 0.0),
            "avg_bars": float(np.mean([t["bars"] for t in trades]))}


def backtest(dates, close, strategy, params, cost_bps=5.0, oos_frac=0.3, allow_short=False, capital=100_000.0):
    c = np.asarray(close, float)
    pos, P = positions(strategy, c, params, allow_short)
    sr = strat_returns(c, pos, cost_bps)
    held = np.zeros(len(c))
    held[1:] = pos[:-1]
    bh = np.zeros(len(c))
    bh[1:] = c[1:] / c[:-1] - 1
    split = int(len(c) * (1 - oos_frac)) if 0 < oos_frac < 0.9 else len(c)
    trades = extract_trades(dates, c, pos, cost_bps)
    split_date = dates[split] if split < len(c) else None
    is_tr = [t for t in trades if split_date is None or t["entry_date"] < split_date]
    oos_tr = [t for t in trades if split_date is not None and t["entry_date"] >= split_date]
    eq = capital * np.cumprod(1 + sr)
    bh_eq = capital * np.cumprod(1 + bh)
    peak = np.maximum.accumulate(eq)

    def seg(a, b):
        m = metrics(sr[a:b], held[a:b])
        m["bh_return"] = float(np.prod(1 + bh[a:b]) - 1)
        m["bh_sharpe"] = sharpe(bh[a:b])
        return m

    full = seg(0, len(c)); full.update(trade_stats(trades))
    res = {
        "strategy": strategy, "name": STRATEGIES[strategy]["name"], "params": P,
        "dates": list(dates), "close": [round(float(v), 4) for v in c],
        "equity": [round(float(v), 2) for v in eq], "bh_equity": [round(float(v), 2) for v in bh_eq],
        "drawdown": [round(float(v), 5) for v in (eq / peak - 1)],
        "position": [int(v) for v in pos],
        "trades": trades, "split": split if split < len(c) else None,
        "metrics": {"full": full},
        "engine": "C++ (pybind11)" if HAS_CPP else "NumPy",
    }
    if split < len(c) and split > 30 and len(c) - split > 30:
        m_is = seg(0, split); m_is.update(trade_stats(is_tr))
        m_oos = seg(split, len(c)); m_oos.update(trade_stats(oos_tr))
        res["metrics"]["in_sample"] = m_is
        res["metrics"]["out_of_sample"] = m_oos
    return res


# ════════════════════════════════════════════════════════════ parameter grid
def _ma_grid_numpy(c, fasts, slows, cost_bps, split, allow_short):
    lo = -1.0 if allow_short else 0.0
    cache = {w: sma(c, w) for w in set(fasts) | set(slows)}
    r = np.zeros(len(c)); r[1:] = c[1:] / c[:-1] - 1
    gi = np.full((len(slows), len(fasts)), np.nan)
    go = np.full((len(slows), len(fasts)), np.nan)
    for yi, s in enumerate(slows):
        for xi, f in enumerate(fasts):
            if f >= s:
                continue
            a, b = cache[f], cache[s]
            ok = ~np.isnan(a) & ~np.isnan(b)
            p = np.zeros(len(c)); p[ok] = np.where(a[ok] > b[ok], 1.0, lo)
            held = np.zeros(len(c)); held[1:] = p[:-1]
            prev = np.zeros(len(c)); prev[1:] = held[:-1]
            sr = held * r - np.abs(held - prev) * cost_bps / 1e4
            gi[yi, xi] = sharpe(sr[:split])
            go[yi, xi] = sharpe(sr[split:])
    return gi, go


def _ma_grid_python(c, fasts, slows, cost_bps, split, allow_short, max_combos=None):
    """Deliberately plain Python loops, used only for the speed benchmark."""
    c = [float(v) for v in c]
    n = len(c)
    lo = -1.0 if allow_short else 0.0
    done = 0
    out = {}
    for s in slows:
        for f in fasts:
            if f >= s:
                continue
            if max_combos is not None and done >= max_combos:
                return out, done
            pos = [0.0] * n
            sf = ss = 0.0
            for t in range(n):
                sf += c[t]; ss += c[t]
                if t >= f: sf -= c[t - f]
                if t >= s: ss -= c[t - s]
                if t >= s - 1:
                    pos[t] = 1.0 if sf / f > ss / s else lo
            rets = []
            prev_h = 0.0
            for t in range(1, n):
                h = pos[t - 1]
                rets.append(h * (c[t] / c[t - 1] - 1) - abs(h - prev_h) * cost_bps / 1e4)
                prev_h = h
            seg = rets[:split - 1]
            m = sum(seg) / len(seg)
            v = sum((x - m) ** 2 for x in seg) / (len(seg) - 1)
            out[(f, s)] = m / math.sqrt(v) * math.sqrt(TD) if v > 0 else 0.0
            done += 1
    return out, done


def param_grid(dates, close, strategy, cost_bps=5.0, oos_frac=0.3, allow_short=False, engine="auto"):
    c = np.asarray(close, float)
    g = STRATEGIES[strategy]["grid"]
    xk, xs = g["x"]; yk, ys = g["y"]
    split = int(len(c) * (1 - oos_frac))
    t0 = time.perf_counter()
    used = "NumPy"
    if strategy == "ma_cross":
        if HAS_CPP and engine in ("auto", "cpp"):
            gi, go = fastbt.ma_grid(np.ascontiguousarray(c), list(map(int, xs)), list(map(int, ys)),
                                    float(cost_bps), int(split), bool(allow_short))
            gi, go = np.asarray(gi), np.asarray(go)
            used = "C++ (pybind11)"
        else:
            gi, go = _ma_grid_numpy(c, xs, ys, cost_bps, split, allow_short)
    else:
        base = {p["key"]: p["default"] for p in STRATEGIES[strategy]["params"]}
        gi = np.full((len(ys), len(xs)), np.nan)
        go = np.full((len(ys), len(xs)), np.nan)
        for yi, yv in enumerate(ys):
            for xi, xv in enumerate(xs):
                prm = dict(base, **{xk: xv, yk: yv})
                if strategy == "macd" and prm["fast"] >= prm["slow"]:
                    continue
                if strategy == "rsi_mr" and prm["lower"] >= prm["upper"]:
                    continue
                pos, _ = positions(strategy, c, prm, allow_short)
                sr = strat_returns(c, pos, cost_bps)
                gi[yi, xi] = sharpe(sr[:split]); go[yi, xi] = sharpe(sr[split:])
    ms = (time.perf_counter() - t0) * 1000
    clean = lambda a: [[None if np.isnan(v) else round(float(v), 3) for v in row] for row in a]
    best = None
    if np.any(~np.isnan(gi)):
        yi, xi = np.unravel_index(np.nanargmax(gi), gi.shape)
        best = {"x": xs[xi], "y": ys[yi], "is_sharpe": float(gi[yi, xi]),
                "oos_sharpe": None if np.isnan(go[yi, xi]) else float(go[yi, xi])}
    return {"x_key": xk, "x": xs, "y_key": yk, "y": ys, "is": clean(gi), "oos": clean(go),
            "best": best, "ms": round(ms, 1), "engine": used, "split_date": dates[split] if split < len(dates) else None}


def benchmark(close, cost_bps=5.0, oos_frac=0.3):
    """Same MA grid on three engines. Reports backtests per second."""
    c = np.asarray(close, float)
    fasts = list(range(2, 51, 2))
    slows = list(range(20, 251, 5))
    split = int(len(c) * (1 - oos_frac))
    combos = sum(1 for s in slows for f in fasts if f < s)
    res = []
    t0 = time.perf_counter()
    _, done = _ma_grid_python(c, fasts, slows, cost_bps, split, False, max_combos=60)
    dt = time.perf_counter() - t0
    res.append({"engine": "Pure Python", "combos": done, "sec": dt, "per_sec": done / dt})
    t0 = time.perf_counter()
    gi_np, _ = _ma_grid_numpy(c, fasts, slows, cost_bps, split, False)
    dt = time.perf_counter() - t0
    res.append({"engine": "NumPy", "combos": combos, "sec": dt, "per_sec": combos / dt})
    parity = None
    if HAS_CPP:
        t0 = time.perf_counter()
        gi_c, _ = fastbt.ma_grid(np.ascontiguousarray(c), fasts, slows, float(cost_bps), split, False)
        dt = time.perf_counter() - t0
        res.append({"engine": "C++ (pybind11)", "combos": combos, "sec": dt, "per_sec": combos / dt})
        a, b = np.asarray(gi_c), gi_np
        m = ~np.isnan(a) & ~np.isnan(b)
        parity = float(np.max(np.abs(a[m] - b[m]))) if m.any() else None
    base = res[0]["per_sec"]
    for r in res:
        r["speedup"] = r["per_sec"] / base
        r["sec"] = round(r["sec"], 4)
        r["per_sec"] = round(r["per_sec"], 1)
    return {"bars": len(c), "grid": f"{len(fasts)}×{len(slows)} ({combos} valid combos)",
            "results": res, "has_cpp": HAS_CPP, "max_abs_diff_cpp_vs_numpy": parity}


# ════════════════════════════════════════════════════════════ cointegration
# Engle-Granger 2-variable, constant: MacKinnon (2010) asymptotic critical values
EG_CRIT = {0.01: -3.8962, 0.05: -3.3377, 0.10: -3.0462}

try:
    from statsmodels.tsa.stattools import coint as _sm_coint
    HAS_SM = True
except Exception:
    HAS_SM = False


def _ols(y, x):
    X = np.column_stack([np.ones(len(x)), x])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta[0], beta[1], y - X @ beta


def adf_tstat(e, lags=1):
    """ADF regression on residuals with no constant: de_t = g*e_{t-1} + sum(phi*de_{t-i})."""
    e = np.asarray(e, float)
    de = np.diff(e)
    y = de[lags:]
    cols = [e[lags:-1]]
    for i in range(1, lags + 1):
        cols.append(de[lags - i:-i])
    X = np.column_stack(cols)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = len(y) - X.shape[1]
    s2 = resid @ resid / dof
    cov = s2 * np.linalg.inv(X.T @ X)
    return float(beta[0] / math.sqrt(cov[0, 0]))


def eg_pvalue_bucket(t):
    if t < EG_CRIT[0.01]:
        return "<1%"
    if t < EG_CRIT[0.05]:
        return "<5%"
    if t < EG_CRIT[0.10]:
        return "<10%"
    return ">10%"


def eg_pvalue_approx(t):
    """Log-linear interpolation between MacKinnon critical points. Exact p comes from statsmodels when installed."""
    pts = [(-3.8962, 0.01), (-3.3377, 0.05), (-3.0462, 0.10)]
    if t <= pts[0][0]:
        return 0.01
    if t >= pts[-1][0]:
        return None
    for (t1, p1), (t2, p2) in zip(pts, pts[1:]):
        if t1 <= t <= t2:
            w = (t - t1) / (t2 - t1)
            return float(math.exp(math.log(p1) + w * (math.log(p2) - math.log(p1))))
    return None


def half_life(e):
    e = np.asarray(e, float)
    de = np.diff(e)
    X = np.column_stack([np.ones(len(de)), e[:-1]])
    b, *_ = np.linalg.lstsq(X, de, rcond=None)
    lam = b[1]
    return float(-math.log(2) / lam) if lam < 0 else float("inf")


def coint_test(p1, p2, exact=False):
    y, x = np.log(np.asarray(p1, float)), np.log(np.asarray(p2, float))
    a, b, e = _ols(y, x)
    t = adf_tstat(e, 1)
    out = {"alpha": float(a), "beta": float(b), "adf": t, "pbucket": eg_pvalue_bucket(t),
           "pvalue": eg_pvalue_approx(t), "p_exact": False, "half_life": half_life(e)}
    if exact and HAS_SM:
        try:
            _, p, _ = _sm_coint(y, x)
            out["pvalue"] = float(p); out["p_exact"] = True
        except Exception:
            pass
    return out


def pairs_backtest(dates, p1, p2, entry=2.0, exit_=0.5, window=30, cost_bps=5.0, capital=100_000.0):
    p1, p2 = np.asarray(p1, float), np.asarray(p2, float)
    ct = coint_test(p1, p2, exact=True)
    spread = np.log(p1) - ct["beta"] * np.log(p2) - ct["alpha"]
    s = pd.Series(spread)
    mu = s.rolling(window).mean().values
    sd = s.rolling(window).std(ddof=0).values
    z = (spread - mu) / np.where(sd > 0, sd, np.nan)
    n = len(spread)
    pos = np.zeros(n)
    state = 0.0
    for t in range(n):
        if np.isnan(z[t]):
            continue
        if state == 0:
            if z[t] > entry: state = -1.0     # spread rich: short s1, long beta*s2
            elif z[t] < -entry: state = 1.0   # spread cheap: long s1, short beta*s2
        elif state == 1 and z[t] > -exit_:
            state = 0.0
        elif state == -1 and z[t] < exit_:
            state = 0.0
        pos[t] = state
    b = abs(ct["beta"])
    w1, w2 = 1 / (1 + b), b / (1 + b)
    r1 = np.zeros(n); r1[1:] = p1[1:] / p1[:-1] - 1
    r2 = np.zeros(n); r2[1:] = p2[1:] / p2[:-1] - 1
    held = np.zeros(n); held[1:] = pos[:-1]
    prev = np.zeros(n); prev[1:] = held[:-1]
    sr = held * (w1 * r1 - np.sign(ct["beta"]) * w2 * r2) - np.abs(held - prev) * 2 * cost_bps / 1e4
    eq = capital * np.cumprod(1 + sr)
    trades = []
    i0 = None
    for t in range(1, n):
        if pos[t] != pos[t - 1]:
            if pos[t - 1] != 0 and i0 is not None:
                trades.append({"entry_date": dates[i0], "exit_date": dates[t],
                               "side": "LONG SPREAD" if pos[t - 1] > 0 else "SHORT SPREAD",
                               "ret": float(np.prod(1 + sr[i0 + 1:t + 1]) - 1), "bars": t - i0})
                i0 = None
            if pos[t] != 0:
                i0 = t
    m = metrics(sr, held)
    m.update(trade_stats(trades))
    zc = [None if np.isnan(v) else round(float(v), 3) for v in z]
    return {"coint": ct, "z": zc, "position": [int(v) for v in pos], "equity": [round(float(v), 2) for v in eq],
            "dates": list(dates), "trades": trades[-25:], "metrics": m, "window": window,
            "current_z": None if np.isnan(z[-1]) else float(z[-1]), "entry": entry, "exit": exit_,
            "note": "Hedge ratio is estimated on the whole window (in-sample), so results are optimistic."}


# ════════════════════════════════════════════════════════════ portfolio optimisation
def _proj_simplex(v):
    if not np.all(np.isfinite(v)):
        raise FloatingPointError("non-finite weights in simplex projection")
    u = np.sort(v)[::-1]
    css = np.cumsum(u)
    rho = np.nonzero(u * np.arange(1, len(v) + 1) > (css - 1))[0][-1]
    th = (css[rho] - 1) / (rho + 1.0)
    return np.maximum(v - th, 0)


def _min_var(cov, iters=3000):
    k = cov.shape[0]
    w = np.ones(k) / k
    L = np.linalg.eigvalsh(cov).max() * 2
    for _ in range(iters):
        w = _proj_simplex(w - (2 * cov @ w) / L)
    return w


def _max_sharpe(mu, cov, w0, iters=4000):
    w = w0.copy()
    step = 0.05
    def S(w):
        v = math.sqrt(max(w @ cov @ w, 1e-16)); return (w @ mu) / v
    cur = S(w)
    for _ in range(iters):
        v = math.sqrt(max(w @ cov @ w, 1e-16))
        g = mu / v - (w @ mu) * (cov @ w) / v ** 3
        nw = _proj_simplex(w + step * g)
        ns = S(nw)
        if ns > cur + 1e-12:          # real improvement: keep it and try a slightly bigger step
            w, cur = nw, ns
            step = min(step * 1.1, 10.0)
        else:                         # no gain (e.g. stuck at a corner like 100% one stock): shrink
            step *= 0.5
            if step < 1e-9:
                break
    return w


def _risk_parity(cov, iters=500):
    k = cov.shape[0]
    w = np.ones(k) / k
    for _ in range(iters):
        sig = math.sqrt(w @ cov @ w)
        rc = w * (cov @ w) / sig
        w = w * np.sqrt((sig / k) / np.maximum(rc, 1e-12))
        w /= w.sum()
    return w


def _frontier(mu, cov, n=24, iters=2500):
    wmv = _min_var(cov)
    r_lo, r_hi = float(wmv @ mu), float(mu.max())
    pts = []
    if r_hi <= r_lo:
        return pts
    L = np.linalg.eigvalsh(cov).max() * 2
    for tgt in np.linspace(r_lo, r_hi, n):
        rho = 50.0 / max(np.var(mu), 1e-8)
        w = wmv.copy()
        lr = 1.0 / (L + 2 * rho * (mu @ mu))
        for _ in range(iters):
            g = 2 * cov @ w + 2 * rho * (w @ mu - tgt) * mu
            w = _proj_simplex(w - lr * g)
        pts.append({"vol": float(math.sqrt(w @ cov @ w)), "ret": float(w @ mu)})
    return pts


def portfolio_stats(rets, w, bench=None, capital=100_000.0):
    pr = rets.values @ w
    eq = np.cumprod(1 + pr)
    q = np.quantile(pr, 0.05)
    out = {"ann_return": float(pr.mean() * TD), "ann_vol": float(pr.std(ddof=1) * math.sqrt(TD)),
           "sharpe": sharpe(pr), "max_dd": float(-(eq / np.maximum.accumulate(eq) - 1).min()),
           "var95_hist": float(-q * capital), "cvar95_hist": float(-pr[pr <= q].mean() * capital),
           "var95_param": float(-(pr.mean() - 1.6449 * pr.std(ddof=1)) * capital)}
    if bench is not None and len(bench) == len(pr):
        b = np.asarray(bench)
        out["beta"] = float(np.cov(pr, b)[0, 1] / np.var(b, ddof=1))
        out["corr_bench"] = float(np.corrcoef(pr, b)[0, 1])
    return out


def optimize_portfolio(prices: pd.DataFrame, bench=None, user_weights=None, capital=100_000.0, n_random=2500):
    rets = prices.pct_change().dropna()
    syms = list(rets.columns)
    mu = rets.mean().values * TD
    cov = rets.cov().values * TD
    k = len(syms)
    rng = np.random.default_rng(7)
    W = np.vstack([rng.dirichlet(np.ones(k), n_random // 2), rng.dirichlet(np.ones(k) * 0.25, n_random - n_random // 2)])
    pr = W @ mu
    pv = np.sqrt(np.einsum("ij,jk,ik->i", W, cov, W))
    cloud = [{"vol": float(v), "ret": float(r), "sharpe": float(r / v) if v > 0 else 0}
             for v, r in zip(pv[::3], pr[::3])]
    w_mv = _min_var(cov)
    w_ms = _max_sharpe(mu, cov, W[np.argmax(pr / pv)])
    w_rp = _risk_parity(cov)
    w_eq = np.ones(k) / k
    b = None
    if bench is not None:
        b = bench.reindex(rets.index).fillna(0).values
    methods = {"Max Sharpe": w_ms, "Min Variance": w_mv, "Risk Parity": w_rp, "Equal Weight": w_eq}
    if user_weights is not None:
        uw = np.array([user_weights.get(s, 0.0) for s in syms], float)
        if uw.sum() > 0:
            methods["Your Weights"] = uw / uw.sum()
    out_m = {}
    for name, w in methods.items():
        st = portfolio_stats(rets, w, b, capital)
        st["weights"] = {s: round(float(x), 4) for s, x in zip(syms, w)}
        st["vol_pt"] = float(math.sqrt(w @ cov @ w)); st["ret_pt"] = float(w @ mu)
        out_m[name] = st
    corr = rets.corr().values
    return {"symbols": syms, "assets": [{"symbol": s, "ret": float(m), "vol": float(math.sqrt(cov[i, i]))}
                                       for i, (s, m) in enumerate(zip(syms, mu))],
            "cloud": cloud, "frontier": _frontier(mu, cov), "methods": out_m,
            "corr": [[round(float(v), 3) for v in row] for row in corr],
            "days": len(rets), "start": str(rets.index[0].date()), "end": str(rets.index[-1].date())}


# ════════════════════════════════════════════════════════════ forecasts (+ conformal)
Z80 = 1.2816


def _quarter_ends(n=4):
    import datetime as dt
    t = dt.date.today()
    out = []
    y, q = t.year, (t.month - 1) // 3 + 1
    for _ in range(n):
        m = q * 3
        end = dt.date(y, m, 31 if m in (3, 12) else 30)
        out.append((f"Q{q}/{str(y)[2:]}", max((end - t).days, 1)))
        q += 1
        if q > 4:
            q = 1; y += 1
    return out


def forecast_bands(closes, shrink=0.5, lookback=252, alpha=0.2, calib_frac=0.6):
    """Drift projection plus three 80% bands for each upcoming quarter end:
       gauss: +/- 1.2816 sigma sqrt(h)
       conf:  split conformal on normalised errors |e|/(sigma_t sqrt h)
       rc:    regime-conditional conformal, separate quantiles for high/low vol regimes
    Also reports out-of-sample coverage of each band on the most recent 40% of origins."""
    c = np.asarray(closes, float)
    c = c[c > 0]
    if len(c) < lookback + 40:
        return None
    lp = np.log(c)
    dl = np.diff(lp)
    s_dl = pd.Series(dl)
    mu_r = (s_dl.rolling(lookback).mean() * shrink).values      # index i -> uses dl[i-lookback+1..i]
    sd_r = s_dl.rolling(lookback).std(ddof=0).values
    v21 = s_dl.rolling(21).std(ddof=0).values
    n = len(c)
    # origin t (price index) uses dl up to index t-1
    mu_t = np.full(n, np.nan); mu_t[1:] = mu_r
    sd_t = np.full(n, np.nan); sd_t[1:] = sd_r
    v_t = np.full(n, np.nan); v_t[1:] = v21
    p = float(c[-1])
    mu_now, sd_now, v_now = mu_t[-1], sd_t[-1], v_t[-1]
    sma50, sma200 = c[-50:].mean(), c[-200:].mean() if n >= 200 else c[-50:].mean()
    signal = "up" if p > sma50 and p > sma200 else "down" if p < sma50 and p < sma200 else "flat"
    qs = []
    for lbl, days in _quarter_ends():
        h = max(1, round(days * TD / 365))
        idx = np.arange(lookback + 1, n - h)
        idx = idx[~np.isnan(mu_t[idx]) & ~np.isnan(sd_t[idx]) & (sd_t[idx] > 0)]
        mid = p * math.exp(mu_now * h)
        row = {"q": lbl, "days": days, "tdays": h, "mid": mid,
               "lo": p * math.exp(mu_now * h - Z80 * sd_now * math.sqrt(h)),
               "hi": p * math.exp(mu_now * h + Z80 * sd_now * math.sqrt(h)),
               "Q": {"gauss": Z80, "conf": None, "rc": None}, "coverage": None}
        if len(idx) >= 60:
            pred = lp[idx] + mu_t[idx] * h
            score = np.abs(lp[idx + h] - pred) / (sd_t[idx] * math.sqrt(h))
            reg = v_t[idx]
            k = int(len(idx) * calib_frac)
            cal, test = score[:k], score[k:]
            def cq(s):
                m = len(s)
                lvl = min(1.0, math.ceil((m + 1) * (1 - alpha)) / m)
                return float(np.quantile(s, lvl, method="higher"))
            med = np.nanmedian(reg[:k])
            hi_cal, lo_cal = cal[reg[:k] > med], cal[reg[:k] <= med]
            q_hi = cq(hi_cal) if len(hi_cal) > 10 else cq(cal)
            q_lo = cq(lo_cal) if len(lo_cal) > 10 else cq(cal)
            q_c = cq(cal)
            test_reg = reg[k:] > med
            cov_g = float(np.mean(test <= Z80))
            cov_c = float(np.mean(test <= q_c))
            cov_r = float(np.mean(np.where(test_reg, test <= q_hi, test <= q_lo)))
            # live quantiles use every origin
            med_all = np.nanmedian(reg)
            q_c_all = cq(score)
            hi_all, lo_all = score[reg > med_all], score[reg <= med_all]
            q_rc_all = cq(hi_all if v_now > med_all else lo_all) if min(len(hi_all), len(lo_all)) > 10 else q_c_all
            row["Q"] = {"gauss": Z80, "conf": q_c_all, "rc": q_rc_all}
            row["coverage"] = {"gauss": cov_g, "conf": cov_c, "rc": cov_r, "n_test": int(len(test)),
                               "n_eff": round(len(test) / h, 1),
                               "regime_now": "high vol" if v_now > med_all else "low vol"}
            for key, Q in (("conf", q_c_all), ("rc", q_rc_all)):
                row[key] = {"lo": p * math.exp(mu_now * h - Q * sd_now * math.sqrt(h)),
                            "hi": p * math.exp(mu_now * h + Q * sd_now * math.sqrt(h))}
        qs.append(row)
    return {"price": p, "signal": signal, "annDrift": mu_now * TD * 100, "annVol": sd_now * math.sqrt(TD) * 100,
            "quarters": qs}
