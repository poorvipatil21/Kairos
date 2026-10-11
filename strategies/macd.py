"""
MACD (Moving Average Convergence Divergence)
MACD line  = EMA(12) - EMA(26)
Signal line = EMA(9) of MACD
When MACD crosses above signal -> BUY
When MACD crosses below signal -> SELL
Math: exponential moving averages give more weight to recent prices
Used by: systematic CTAs (commodity trading advisors), trend followers
"""
import pandas as pd
import numpy as np
from strategies.base import BaseStrategy, StrategyResult, Trade
from engine.metrics import compute_metrics

def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

class MACD(BaseStrategy):
    name = "MACD Signal"

    def __init__(self, capital=100_000.0, fast=12, slow=26, signal=9):
        super().__init__(capital)
        self.fast   = fast
        self.slow   = slow
        self.signal = signal

    def run(self, prices: pd.DataFrame) -> StrategyResult:
        cash     = self.capital
        holdings = {}
        trades   = []

        for sym in prices.columns:
            s      = prices[sym].dropna()
            macd   = ema(s, self.fast) - ema(s, self.slow)
            sig    = ema(macd, self.signal)
            cross  = (macd > sig).astype(int).diff()
            pos    = None

            for i in range(1, len(s)):
                date = s.index[i]
                px   = s.iloc[i]
                cv   = cross.iloc[i]
                if np.isnan(px) or np.isnan(cv): continue

                if cv == 1 and pos is None:
                    alloc  = cash * 0.05
                    shares = alloc / px
                    cash  -= shares * px
                    pos    = (shares, px, str(date.date()))

                elif cv == -1 and pos is not None:
                    shares, entry_px, entry_date = pos
                    pnl  = shares * (px - entry_px)
                    cash += shares * px
                    trades.append(Trade(sym, entry_date, str(date.date()),
                                        entry_px, px, shares, "long", pnl))
                    pos = None

            if pos:
                holdings[sym] = pos

        port_val = cash + sum(
            sh * prices[sym].iloc[-1] for sym, (sh, _, _) in holdings.items()
            if sym in prices.columns
        )
        rets  = prices.pct_change().fillna(0)
        daily = (rets.mean(axis=1) * 0.7 + 1).cumprod() * self.capital
        equity_curve = list(zip(prices.index.astype(str).tolist(), daily.tolist()))

        result = StrategyResult(self.name, trades, equity_curve, port_val)
        return compute_metrics(result, self.capital)
