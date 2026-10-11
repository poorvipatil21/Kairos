import sqlite3
import json
from config import DB_PATH
from strategies.base import StrategyResult

def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date    TEXT,
            strategy    TEXT,
            final_value REAL,
            pnl         REAL,
            sharpe      REAL,
            max_dd      REAL,
            win_rate    REAL,
            total_trades INTEGER,
            equity_json TEXT,
            trades_json TEXT
        )
    """)
    con.commit()
    con.close()

def save_result(result: StrategyResult, initial: float, run_date: str):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        INSERT INTO runs
        (run_date, strategy, final_value, pnl, sharpe, max_dd, win_rate, total_trades, equity_json, trades_json)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        run_date,
        result.name,
        result.final_value,
        result.final_value - initial,
        result.sharpe,
        result.max_dd,
        result.win_rate,
        result.total_trades,
        json.dumps(result.equity[-100:]),  # last 100 points
        json.dumps([vars(t) for t in result.trades[-50:]])
    ))
    con.commit()
    con.close()

def load_latest() -> list[dict]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("""
        SELECT * FROM runs
        WHERE run_date = (SELECT MAX(run_date) FROM runs)
        ORDER BY pnl DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows

def load_history(strategy: str) -> list[dict]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("""
        SELECT run_date, final_value, pnl, sharpe FROM runs
        WHERE strategy = ? ORDER BY run_date
    """, (strategy,))
    rows = [dict(r) for r in cur.fetchall()]
    con.close()
    return rows
