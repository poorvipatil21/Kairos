import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from config import LOOKBACK_DAYS

def fetch_prices(symbols: list[str]) -> pd.DataFrame:
    end   = datetime.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    raw   = yf.download(symbols, start=start, end=end, auto_adjust=True, progress=False)
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    close = close.dropna(how="all")
    return close

def fetch_single(symbol: str) -> pd.Series:
    end   = datetime.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    df    = yf.download(symbol, start=start, end=end, auto_adjust=True, progress=False)
    return df["Close"].dropna()
