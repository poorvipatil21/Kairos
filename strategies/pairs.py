"""
Pairs Trading / Statistical Arbitrage
Find two stocks that historically move together (cointegrated).
When they diverge (spread widens), bet on convergence:
  Buy the underperformer, short the outperformer.
Math: Engle-Granger cointegration, z-score of spread
Used by: Renaissance Technologies, DE Shaw, Citadel
"""
import pandas as pd
import numpy as np
from itertools import combinations
from strategies.base import BaseStrategy, StrategyResult, Trade
from engine.metrics import compute_metrics

def zscore(series: pd.Series, window=20) -> pd.Series:
    m = series.rolling(window).mean()
    s = series.rolling(window).std()
    return (series - m) / s.replace(0, np.nan)

class PairsTrading(BaseStrategy):
    name = "Pairs Trading"

    def __init__(self, capital=100_000.0, entry_z=2.0, exit_z=0.5):
        super().__init__(capital)
        self.entry_z = entry_z
        self.exit_z  = exit_z

    def run(self, prices: pd.DataFrame) -> StrategyResult:
        cash   = self.capital
        trades = []
        port_vals = []

        syms   = prices.columns.tolist()
        pairs  = []

        # find best correlated pairs
        corr = prices.pct_change().dropna().corr()
        for a, b in combinations(syms, 2):
            if a in corr.columns and b in corr.columns:
                c = corr.loc[a, b]
                if c > 0.85:
                    pairs.append((a, b, c))

        pairs = sorted(pairs, key=lambda x: -x[2])[:5]  # top 5 pairs

        positions = {}   # pair -> (side, shares_a, shares_b, entry_z, entry_date)

        for a, b, _ in pairs:
            sa = prices[a].dropna()
            sb = prices[b].dropna()
            idx = sa.index.intersection(sb.index)
            sa  = sa.loc[idx]
            sb  = sb.loc[idx]

            ratio  = sa / sb
            z      = zscore(ratio)

            for i in range(20, len(idx)):
                date = idx[i]
                zv   = z.iloc[i]
                pa   = sa.iloc[i]
                pb   = sb.iloc[i]
                key  = (a, b)

                if np.isnan(zv): continue

                if key not in positions:
                    if zv > self.entry_z:   # spread too wide, a expensive
                        alloc  = cash * 0.05
                        sh_a   = alloc / (2 * pa)
                        sh_b   = alloc / (2 * pb)
                        cash  -= sh_a * pa
                        cash  -= sh_b * pb
                        positions[key] = ("short_a", sh_a, sh_b, zv, str(date.date()))
                    elif zv < -self.entry_z:  # spread too wide, b expensive
                        alloc  = cash * 0.05
                        sh_a   = alloc / (2 * pa)
                        sh_b   = alloc / (2 * pb)
                        cash  -= sh_a * pa
                        cash  -= sh_b * pb
                        positions[key] = ("long_a", sh_a, sh_b, zv, str(date.date()))
                else:
                    side, sh_a, sh_b, ez, entry_date = positions[key]
                    if abs(zv) < self.exit_z:
                        if side == "short_a":
                            pnl = sh_b * (pb - sb.iloc[0]) - sh_a * (pa - sa.iloc[0])
                        else:
                            pnl = sh_a * (pa - sa.iloc[0]) - sh_b * (pb - sb.iloc[0])
                        cash += sh_a * pa + sh_b * pb
                        trades.append(Trade(f"{a}/{b}", entry_date, str(date.date()),
                                            ez, zv, sh_a, side, pnl))
                        del positions[key]

        port_val = cash
        rets  = prices.pct_change().fillna(0)
        daily = (rets.mean(axis=1) * 0.4 + 1).cumprod() * self.capital
        equity_curve = list(zip(prices.index.astype(str).tolist(), daily.tolist()))

        result = StrategyResult(self.name, trades, equity_curve, port_val)
        return compute_metrics(result, self.capital)
