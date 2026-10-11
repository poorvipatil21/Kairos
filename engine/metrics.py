import numpy as np
from strategies.base import StrategyResult

def compute_metrics(result: StrategyResult, initial_capital: float) -> StrategyResult:
    trades = result.trades

    # win rate
    closed = [t for t in trades if t.pnl != 0]
    if closed:
        wins = sum(1 for t in closed if t.pnl > 0)
        result.win_rate = wins / len(closed)
    result.total_trades = len(closed)

    # sharpe from equity curve
    if result.equity:
        vals  = np.array([v for _, v in result.equity])
        rets  = np.diff(vals) / vals[:-1]
        rets  = rets[np.isfinite(rets)]
        if len(rets) > 1 and rets.std() > 0:
            result.sharpe = float(np.sqrt(252) * rets.mean() / rets.std())

    # max drawdown
    if result.equity:
        vals     = np.array([v for _, v in result.equity])
        peak     = np.maximum.accumulate(vals)
        dd       = (vals - peak) / np.where(peak > 0, peak, 1)
        result.max_dd = float(dd.min())

    return result
