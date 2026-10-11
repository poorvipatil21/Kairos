#!/usr/bin/env python3
"""
Kairos: Multi-Strategy Backtesting Engine
Runs 6 trading strategies on 20 S&P 500 stocks using free Yahoo Finance data.
"""
import sys
from datetime import date

from config import SYMBOLS, STARTING_CAPITAL
from data.fetcher import fetch_prices
from db.database import init_db, save_result, load_latest

from strategies.ma_crossover import MACrossover
from strategies.rsi import RSIReversion
from strategies.bollinger import BollingerBands
from strategies.momentum import Momentum
from strategies.pairs import PairsTrading
from strategies.macd import MACD

STRATEGIES = [
    MACrossover(STARTING_CAPITAL),
    RSIReversion(STARTING_CAPITAL),
    BollingerBands(STARTING_CAPITAL),
    Momentum(STARTING_CAPITAL),
    PairsTrading(STARTING_CAPITAL),
    MACD(STARTING_CAPITAL),
]

def run():
    init_db()
    run_date = str(date.today())

    print(f"Kairos — fetching {len(SYMBOLS)} symbols...")
    prices = fetch_prices(SYMBOLS)
    print(f"Got {len(prices)} trading days, {len(prices.columns)} symbols\n")

    results = []
    for strat in STRATEGIES:
        print(f"Running: {strat.name}...", end=" ", flush=True)
        result = strat.run(prices)
        save_result(result, STARTING_CAPITAL, run_date)
        pnl = result.final_value - STARTING_CAPITAL
        print(f"P&L=${pnl:+,.0f}  Sharpe={result.sharpe:.2f}  "
              f"MaxDD={result.max_dd:.1%}  Trades={result.total_trades}  "
              f"WinRate={result.win_rate:.0%}")
        results.append(result)

    print("\n=== LEADERBOARD ===")
    ranked = sorted(results, key=lambda r: r.final_value, reverse=True)
    for i, r in enumerate(ranked, 1):
        pnl = r.final_value - STARTING_CAPITAL
        print(f"{i}. {r.name:<35} ${r.final_value:>10,.0f}  ({pnl:+,.0f})")

    best = ranked[0]
    print(f"\nBest strategy: {best.name}")
    print(f"Return: {(best.final_value/STARTING_CAPITAL - 1):.1%}")
    print(f"Sharpe: {best.sharpe:.2f}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "serve":
        import uvicorn
        uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=False)
    else:
        run()
