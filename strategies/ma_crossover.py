"""
Moving Average Crossover
Buy  when SMA(20) crosses above SMA(50)  -- momentum confirmed
Sell when SMA(20) crosses below SMA(50)  -- momentum broken
Used by: trend-following CTAs, systematic macro funds
"""
import pandas as pd
import numpy as np
from strategies.base import BaseStrategy, StrategyResult, Trade
from engine.metrics import compute_metrics

class MACrossover(BaseStrategy):
    name = "MA Crossover (20/50)"

    def __init__(self, capital=100_000.0, fast=20, slow=50):
        super().__init__(capital)
        self.fast = fast
        self.slow = slow

    def run(self, prices: pd.DataFrame) -> StrategyResult:
        cash     = self.capital
        holdings = {}   # symbol -> (shares, entry_px, entry_date)
        trades   = []
        equity_curve = []

        for sym in prices.columns:
            s = prices[sym].dropna()
            sma_f = s.rolling(self.fast).mean()
            sma_s = s.rolling(self.slow).mean()
            signal = (sma_f > sma_s).astype(int).diff()

            for date, sig in signal.items():
                px = s.loc[date]
                if np.isnan(px): continue
                if sig == 1:  # buy signal
                    alloc  = cash * 0.05  # 5% per position
                    shares = alloc / px
                    cash  -= shares * px
                    holdings[sym] = (shares, px, str(date.date()))
                elif sig == -1 and sym in holdings:
                    shares, entry_px, entry_date = holdings.pop(sym)
                    pnl  = shares * (px - entry_px)
                    cash += shares * px
                    trades.append(Trade(sym, entry_date, str(date.date()),
                                        entry_px, px, shares, "long", pnl))

        port_val = cash + sum(
            sh * prices[sym].iloc[-1] for sym, (sh, _, _) in holdings.items()
            if sym in prices.columns
        )
        # simple daily equity proxy
        daily = (prices.pct_change().fillna(0).mean(axis=1) * 0.5 + 1).cumprod() * self.capital
        equity_curve = list(zip(prices.index.astype(str).tolist(), daily.tolist()))

        result = StrategyResult(self.name, trades, equity_curve, port_val)
        return compute_metrics(result, self.capital)
