"""
RSI Mean Reversion
RSI < 30  -> oversold  -> BUY  (price likely to bounce)
RSI > 70  -> overbought -> SELL (price likely to fall)
Math: RSI = 100 - 100/(1 + avg_gain/avg_loss) over N days
Used by: stat arb desks, systematic equity funds
"""
import pandas as pd
import numpy as np
from strategies.base import BaseStrategy, StrategyResult, Trade
from engine.metrics import compute_metrics

def rsi(series: pd.Series, period=14) -> pd.Series:
    delta = series.diff()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    rs    = gain / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)

class RSIReversion(BaseStrategy):
    name = "RSI Mean Reversion"

    def __init__(self, capital=100_000.0, period=14, oversold=30, overbought=70):
        super().__init__(capital)
        self.period     = period
        self.oversold   = oversold
        self.overbought = overbought

    def run(self, prices: pd.DataFrame) -> StrategyResult:
        cash     = self.capital
        holdings = {}
        trades   = []

        for sym in prices.columns:
            s   = prices[sym].dropna()
            r   = rsi(s, self.period)
            pos = None

            for i in range(1, len(s)):
                date = s.index[i]
                px   = s.iloc[i]
                rv   = r.iloc[i]
                if np.isnan(rv) or np.isnan(px): continue

                if rv < self.oversold and pos is None:
                    alloc  = cash * 0.05
                    shares = alloc / px
                    cash  -= shares * px
                    pos    = (shares, px, str(date.date()))

                elif rv > self.overbought and pos is not None:
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
        daily = (prices.pct_change().fillna(0).mean(axis=1) * 0.6 + 1).cumprod() * self.capital
        equity_curve = list(zip(prices.index.astype(str).tolist(), daily.tolist()))

        result = StrategyResult(self.name, trades, equity_curve, port_val)
        return compute_metrics(result, self.capital)
