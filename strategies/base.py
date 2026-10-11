from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

@dataclass
class Trade:
    symbol:     str
    entry_date: str
    exit_date:  Optional[str]
    entry_px:   float
    exit_px:    Optional[float]
    shares:     float
    side:       str          # "long" or "short"
    pnl:        float = 0.0

@dataclass
class StrategyResult:
    name:        str
    trades:      list = field(default_factory=list)
    equity:      list = field(default_factory=list)  # list of (date, value)
    final_value: float = 100_000.0
    sharpe:      float = 0.0
    max_dd:      float = 0.0
    win_rate:    float = 0.0
    total_trades:int   = 0

class BaseStrategy:
    name = "base"

    def __init__(self, capital: float = 100_000.0):
        self.capital = capital

    def run(self, prices: pd.DataFrame) -> StrategyResult:
        raise NotImplementedError
