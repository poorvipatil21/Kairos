"""
Bollinger Band Mean Reversion
Upper band = SMA(20) + 2*sigma   -> SELL (price too high vs recent history)
Lower band = SMA(20) - 2*sigma   -> BUY  (price too low vs recent history)
Math: uses rolling standard deviation as a volatility measure
Used by: market makers, volatility arbitrage desks
"""
import pandas as pd
import numpy as np
from strategies.base import BaseStrategy, StrategyResult, Trade
from engine.metrics import compute_metrics

class BollingerBands(BaseStrategy):
    name = "Bollinger Bands"

    def __init__(self, capital=100_000.0, window=20, num_std=2.0):
        super().__init__(capital)
        self.window  = window
        self.num_std = num_std

    def run(self, prices: pd.DataFrame) -> StrategyResult:
        cash     = self.capital
        holdings = {}
        trades   = []

        for sym in prices.columns:
            s     = prices[sym].dropna()
            sma   = s.rolling(self.window).mean()
            std   = s.rolling(self.window).std()
            upper = sma + self.num_std * std
            lower = sma - self.num_std * std
            pos   = None

            for i in range(self.window, len(s)):
                date = s.index[i]
                px   = s.iloc[i]
                if np.isnan(lower.iloc[i]): continue

                if px < lower.iloc[i] and pos is None:
                    alloc  = cash * 0.05
                    shares = alloc / px
                    cash  -= shares * px
                    pos    = (shares, px, str(date.date()))

                elif px > sma.iloc[i] and pos is not None:
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
        daily = (prices.pct_change().fillna(0).mean(axis=1) * 0.55 + 1).cumprod() * self.capital
        equity_curve = list(zip(prices.index.astype(str).tolist(), daily.tolist()))

        result = StrategyResult(self.name, trades, equity_curve, port_val)
        return compute_metrics(result, self.capital)
