"""SQLite storage for 1-minute candles. Every other timeframe is derived from these."""
import sqlite3
from pathlib import Path

import pandas as pd

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS candles_1m (
    ts INTEGER PRIMARY KEY,   -- open time, ms since epoch (UTC)
    o REAL NOT NULL, h REAL NOT NULL, l REAL NOT NULL, c REAL NOT NULL,
    v REAL NOT NULL,          -- base volume (oz)
    n INTEGER NOT NULL        -- number of trades
);
"""


def connect(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=30, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript(SCHEMA)
    return con


def upsert(con: sqlite3.Connection, rows) -> int:
    """rows: iterable of (ts, o, h, l, c, v, n)."""
    rows = list(rows)
    if rows:
        con.executemany(
            "INSERT OR REPLACE INTO candles_1m (ts,o,h,l,c,v,n) VALUES (?,?,?,?,?,?,?)", rows
        )
        con.commit()
    return len(rows)


def last_ts(con: sqlite3.Connection):
    r = con.execute("SELECT MAX(ts) FROM candles_1m").fetchone()
    return r[0]


def load(con: sqlite3.Connection, start_ms: int | None = None, end_ms: int | None = None) -> pd.DataFrame:
    q, args = "SELECT ts,o,h,l,c,v,n FROM candles_1m", []
    cond = []
    if start_ms is not None:
        cond.append("ts >= ?"); args.append(start_ms)
    if end_ms is not None:
        cond.append("ts < ?"); args.append(end_ms)
    if cond:
        q += " WHERE " + " AND ".join(cond)
    q += " ORDER BY ts"
    df = pd.read_sql_query(q, con, params=args)
    df.index = pd.to_datetime(df.pop("ts"), unit="ms", utc=True)
    df.index.name = "time"
    return df
