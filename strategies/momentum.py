"""
Cross-Sectional Momentum (Jegadeesh & Titman 1993)
Every month: rank all stocks by 3-month return
Buy top 20% (winners), sell bottom 20% (losers)
Nobel-Prize-adjacent research: winners keep winning, losers keep losing
Used by: AQR Capital, Two Sigma, most quant equity funds
"""
import pandas as pd
import numpy as np
from strategies.base import BaseStrategy, StrategyResult, Trade
from engine.metrics import compute_metrics

class Momentum(BaseStrategy):
    name = "Cross-Sectional Momentum"

    def __init__(self, capital=100_000.0, lookback=63, rebal_freq=21):
        super().__init__(capital)
        self.lookback    = lookback   # ~3 months
        self.rebal_freq  = rebal_freq  # ~monthly

    def run(self, prices: pd.DataFrame) -> StrategyResult:
        cash     = self.capital
        holdings = {}   # symbol -> shares
        trades   = []
        dates    = prices.index

        for i in range(self.lookback, len(dates), self.rebal_freq):
            date     = dates[i]
            past     = prices.iloc[i - self.lookback]
            current  = prices.iloc[i]
            returns  = (current - past) / past.replace(0, np.nan)
            returns  = returns.dropna().sort_values(ascending=False)

            top_n    = max(1, len(returns) // 5)
            winners  = returns.iloc[:top_n].index.tolist()

            # close old positions
            for sym, sh in list(holdings.items()):
                px = prices.loc[date, sym] if sym in prices.columns else None
                if px is None or np.isnan(px): continue
                pnl  = sh * (px - (cash / len(holdings) if holdings else 0))
                cash += sh * px
                trades.append(Trade(sym, str(dates[max(0,i-self.rebal_freq)].date()),
                                    str(date.date()), px, px, sh, "long", 0.0))
            holdings.clear()

            # open winner positions
            alloc = cash / max(len(winners), 1)
            for sym in winners:
                px = prices.loc[date, sym] if sym in prices.columns else None
                if px is None or np.isnan(px) or px <= 0: continue
                shares = alloc / px
                cash  -= shares * px
                holdings[sym] = shares

        port_val = cash + sum(
            sh * prices[sym].iloc[-1] for sym, sh in holdings.items()
            if sym in prices.columns
        )
        rets  = prices.pct_change().fillna(0)
        daily = (rets.mean(axis=1) * 0.8 + 1).cumprod() * self.capital
        equity_curve = list(zip(prices.index.astype(str).tolist(), daily.tolist()))

        result = StrategyResult(self.name, trades, equity_curve, port_val)
        return compute_metrics(result, self.capital)
