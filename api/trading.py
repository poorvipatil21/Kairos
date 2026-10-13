"""Paper trading, watchlist and price alerts for Kairos (SQLite, file: paper.db)."""
import os
import sqlite3
import threading
import time
import math

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.environ.get("STRATLAB_PAPER_DB", os.path.join(ROOT, "paper.db"))
START_CASH = {"india": 1_000_000.0, "usa": 100_000.0}   # ₹10 lakh, $100k
_lock = threading.Lock()


def _conn():
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _lock, _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS accounts(mkt TEXT PRIMARY KEY, cash REAL, start_cash REAL, created REAL);
        CREATE TABLE IF NOT EXISTS positions(mkt TEXT, symbol TEXT, qty REAL, avg_price REAL, PRIMARY KEY(mkt, symbol));
        CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, mkt TEXT, symbol TEXT,
                                          side TEXT, qty REAL, price REAL, value REAL, realized REAL);
        CREATE TABLE IF NOT EXISTS equity_snap(ts REAL, mkt TEXT, equity REAL);
        CREATE TABLE IF NOT EXISTS watchlist(symbol TEXT PRIMARY KEY, added REAL);
        CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, cond TEXT, price REAL,
                                          active INTEGER DEFAULT 1, created REAL, triggered REAL, trig_price REAL);
        """)
        for m, cash in START_CASH.items():
            c.execute("INSERT OR IGNORE INTO accounts VALUES(?,?,?,?)", (m, cash, cash, time.time()))
        # repair rows written with a blank (NaN) Yahoo price, which SQLite stores as NULL
        bad = c.execute("SELECT COUNT(*) FROM orders WHERE price IS NULL OR value IS NULL OR qty IS NULL").fetchone()[0]
        bad += c.execute("SELECT COUNT(*) FROM positions WHERE qty IS NULL OR avg_price IS NULL").fetchone()[0]
        bad += c.execute("SELECT COUNT(*) FROM accounts WHERE cash IS NULL OR start_cash IS NULL").fetchone()[0]
        if bad:
            c.execute("DELETE FROM orders WHERE price IS NULL OR value IS NULL OR qty IS NULL")
            c.execute("DELETE FROM equity_snap WHERE equity IS NULL")
            for m in START_CASH:
                _rebuild(c, m)


def _rebuild(c, m):
    """Recompute cash and positions for one market by replaying its valid orders."""
    start = c.execute("SELECT start_cash FROM accounts WHERE mkt=?", (m,)).fetchone()[0] or START_CASH[m]
    cash, pos = start, {}
    for sym, side, qty, px in c.execute("SELECT symbol, side, qty, price FROM orders WHERE mkt=? ORDER BY id", (m,)).fetchall():
        q0, a0 = pos.get(sym, (0.0, 0.0))
        if side == "BUY":
            nq = q0 + qty
            pos[sym] = (nq, (q0 * a0 + qty * px) / nq)
            cash -= qty * px
        else:
            pos[sym] = (max(q0 - qty, 0.0), a0)
            cash += qty * px
    c.execute("DELETE FROM positions WHERE mkt=?", (m,))
    for sym, (q, a) in pos.items():
        if q > 1e-9:
            c.execute("INSERT INTO positions VALUES(?,?,?,?)", (m, sym, q, a))
    c.execute("UPDATE accounts SET cash=?, start_cash=? WHERE mkt=?", (cash, start, m))


def mkt_of(symbol):
    return "india" if symbol.endswith(".NS") or symbol.endswith(".BO") else "usa"


# ═══════════════════════════════════════ paper trading
def account(mkt, quote_fn):
    with _conn() as c:
        acc = dict(c.execute("SELECT * FROM accounts WHERE mkt=?", (mkt,)).fetchone())
        pos = [dict(r) for r in c.execute("SELECT * FROM positions WHERE mkt=? AND qty>0 ORDER BY symbol", (mkt,))]
        orders = [dict(r) for r in c.execute("SELECT * FROM orders WHERE mkt=? ORDER BY id DESC LIMIT 50", (mkt,))]
        realized = c.execute("SELECT COALESCE(SUM(realized),0) FROM orders WHERE mkt=?", (mkt,)).fetchone()[0]
    mv = 0.0
    for p in pos:
        q = quote_fn(p["symbol"])
        last = q["price"] if q and q.get("price") is not None and math.isfinite(q["price"]) else p["avg_price"]
        p["last"] = last
        p["change"] = q["change"] if q else 0.0
        p["value"] = last * p["qty"]
        p["unrealized"] = (last - p["avg_price"]) * p["qty"]
        p["unrealized_pct"] = (last / p["avg_price"] - 1) if p["avg_price"] else 0.0
        mv += p["value"]
    equity = acc["cash"] + mv
    for p in pos:
        p["weight"] = p["value"] / equity if equity else 0.0
    with _lock, _conn() as c:
        last = c.execute("SELECT ts FROM equity_snap WHERE mkt=? ORDER BY ts DESC LIMIT 1", (mkt,)).fetchone()
        if not last or time.time() - last[0] > 900:
            c.execute("INSERT INTO equity_snap VALUES(?,?,?)", (time.time(), mkt, equity))
        snaps = [dict(r) for r in c.execute("SELECT ts, equity FROM equity_snap WHERE mkt=? ORDER BY ts", (mkt,))]
    return {"mkt": mkt, "cash": acc["cash"], "start_cash": acc["start_cash"], "market_value": mv, "equity": equity,
            "pnl": equity - acc["start_cash"], "pnl_pct": equity / acc["start_cash"] - 1, "realized": realized,
            "positions": pos, "orders": orders, "history": snaps}


def place_order(symbol, side, qty, quote_fn):
    side = side.upper()
    if side not in ("BUY", "SELL"):
        return {"ok": False, "error": "side must be BUY or SELL"}
    try:
        qty = float(qty)
    except (TypeError, ValueError):
        return {"ok": False, "error": "quantity must be a number"}
    if qty <= 0 or qty != int(qty):
        return {"ok": False, "error": "quantity must be a whole number above 0"}
    q = quote_fn(symbol)
    if not q:
        return {"ok": False, "error": f"no live price for {symbol}"}
    px = float(q["price"])
    if not math.isfinite(px) or px <= 0:
        return {"ok": False, "error": f"Yahoo has no valid price for {symbol} right now, try again in a minute"}
    mkt = mkt_of(symbol)
    val = px * qty
    with _lock, _conn() as c:
        cash = c.execute("SELECT cash FROM accounts WHERE mkt=?", (mkt,)).fetchone()[0]
        row = c.execute("SELECT qty, avg_price FROM positions WHERE mkt=? AND symbol=?", (mkt, symbol)).fetchone()
        have, avg = (row["qty"], row["avg_price"]) if row else (0.0, 0.0)
        realized = 0.0
        if side == "BUY":
            if val > cash + 1e-6:
                return {"ok": False, "error": f"not enough cash: need {val:,.2f}, have {cash:,.2f}"}
            new_q = have + qty
            new_avg = (have * avg + val) / new_q
            c.execute("INSERT OR REPLACE INTO positions VALUES(?,?,?,?)", (mkt, symbol, new_q, new_avg))
            c.execute("UPDATE accounts SET cash=cash-? WHERE mkt=?", (val, mkt))
        else:
            if qty > have + 1e-9:
                return {"ok": False, "error": f"you only hold {have:g} shares (no short selling in paper mode)"}
            realized = (px - avg) * qty
            left = have - qty
            if left <= 1e-9:
                c.execute("DELETE FROM positions WHERE mkt=? AND symbol=?", (mkt, symbol))
            else:
                c.execute("UPDATE positions SET qty=? WHERE mkt=? AND symbol=?", (left, mkt, symbol))
            c.execute("UPDATE accounts SET cash=cash+? WHERE mkt=?", (val, mkt))
        c.execute("INSERT INTO orders(ts,mkt,symbol,side,qty,price,value,realized) VALUES(?,?,?,?,?,?,?,?)",
                  (time.time(), mkt, symbol, side, qty, px, val, realized))
    return {"ok": True, "symbol": symbol, "side": side, "qty": qty, "price": px, "value": val, "realized": realized}


def reset(mkt):
    with _lock, _conn() as c:
        for t in ("positions", "orders", "equity_snap"):
            c.execute(f"DELETE FROM {t} WHERE mkt=?", (mkt,))
        c.execute("UPDATE accounts SET cash=start_cash, created=? WHERE mkt=?", (time.time(), mkt))
    return {"ok": True}


# ═══════════════════════════════════════ watchlist
def watchlist():
    with _conn() as c:
        return [r["symbol"] for r in c.execute("SELECT symbol FROM watchlist ORDER BY added")]


def watch_add(symbol):
    with _lock, _conn() as c:
        c.execute("INSERT OR IGNORE INTO watchlist VALUES(?,?)", (symbol, time.time()))
    return watchlist()


def watch_remove(symbol):
    with _lock, _conn() as c:
        c.execute("DELETE FROM watchlist WHERE symbol=?", (symbol,))
    return watchlist()


# ═══════════════════════════════════════ alerts
def alerts_list():
    with _conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM alerts ORDER BY active DESC, id DESC LIMIT 100")]


def alert_add(symbol, cond, price):
    if cond not in ("above", "below"):
        return {"ok": False, "error": "condition must be above or below"}
    try:
        price = float(price)
    except (TypeError, ValueError):
        return {"ok": False, "error": "price must be a number"}
    with _lock, _conn() as c:
        c.execute("INSERT INTO alerts(symbol,cond,price,active,created) VALUES(?,?,?,1,?)",
                  (symbol, cond, price, time.time()))
    return {"ok": True}


def alert_delete(aid):
    with _lock, _conn() as c:
        c.execute("DELETE FROM alerts WHERE id=?", (aid,))
    return {"ok": True}


def alerts_check(quote_fn):
    fired = []
    with _conn() as c:
        act = [dict(r) for r in c.execute("SELECT * FROM alerts WHERE active=1")]
    for a in act:
        q = quote_fn(a["symbol"])
        if not q:
            continue
        px = q["price"]
        if (a["cond"] == "above" and px >= a["price"]) or (a["cond"] == "below" and px <= a["price"]):
            with _lock, _conn() as c:
                c.execute("UPDATE alerts SET active=0, triggered=?, trig_price=? WHERE id=?", (time.time(), px, a["id"]))
            a.update({"active": 0, "trig_price": px, "triggered": time.time()})
            fired.append(a)
    return fired
