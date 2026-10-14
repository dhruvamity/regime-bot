"""forex.com XAUUSD session handling and timeframe building.

Binance XAUUSDT trades 24/7, but spot gold (forex.com) does not. Candles printed while
forex.com is closed (weekend, 17:00-18:00 ET daily break, holidays) are thin perp-only
noise, so they are dropped. Analysis always runs on the last in-session candles, which
means over a weekend the signal is simply "as of Friday's close".
"""
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .config import (CLOSED_SESSION_DATES, EARLY_CLOSE_DATES, ET,
                     SESSION_CLOSE_HOUR_ET, SESSION_OPEN_HOUR_ET)


def session_date(idx: pd.DatetimeIndex) -> pd.Index:
    """Trade date: a candle from 18:00 ET belongs to the next day's session."""
    et = idx.tz_convert(ET)
    return pd.Index((et + pd.Timedelta(hours=24 - SESSION_OPEN_HOUR_ET)).date, name="sdate")


def in_session(idx: pd.DatetimeIndex) -> np.ndarray:
    et = idx.tz_convert(ET)
    dow = et.dayofweek.values  # Mon=0 .. Sun=6
    hr = et.hour.values + et.minute.values / 60.0
    in_break = (hr >= SESSION_CLOSE_HOUR_ET) & (hr < SESSION_OPEN_HOUR_ET)
    weekend = (dow == 5) | ((dow == 4) & (hr >= SESSION_CLOSE_HOUR_ET)) | ((dow == 6) & (hr < SESSION_OPEN_HOUR_ET))
    ok = ~(in_break | weekend)
    sd = pd.Index(session_date(idx)).astype(str)
    if CLOSED_SESSION_DATES:
        ok &= ~np.isin(sd, list(CLOSED_SESSION_DATES))
    for d, close_hr in EARLY_CLOSE_DATES.items():
        ok &= ~((sd == d) & (hr >= close_hr) & (hr < SESSION_OPEN_HOUR_ET))
    return ok


def session_filter(df1m: pd.DataFrame) -> pd.DataFrame:
    out = df1m.loc[in_session(df1m.index)].copy()
    out["sdate"] = session_date(out.index)
    return out


def _agg(g):
    return g.agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"),
                 v=("v", "sum"), time=("time", "first"), sdate=("sdate", "first"))


def resample(s1m: pd.DataFrame, tf: str) -> pd.DataFrame:
    """s1m must be session-filtered (has 'sdate'). Returns candles indexed by open time (UTC)."""
    if tf == "1m":
        return s1m
    d = s1m.reset_index()
    if tf in ("5m", "15m", "1h"):
        freq = {"5m": "5min", "15m": "15min", "1h": "60min"}[tf]
        key = d["time"].dt.floor(freq)
    elif tf == "4h":
        # 4h buckets counted from the 18:00 ET session open: 18,22,02,06,10,14 ET
        et = d["time"].dt.tz_convert(ET)
        mins = ((et.dt.hour - SESSION_OPEN_HOUR_ET) % 24) * 60 + et.dt.minute
        key = d["sdate"].astype(str) + "_" + (mins // 240).astype(str)
    elif tf == "1d":
        key = d["sdate"].astype(str)
    else:
        raise ValueError(tf)
    out = _agg(d.groupby(key, sort=False))
    out = out.set_index("time").sort_index()
    out.index.name = "time"
    return out


def build_all(s1m: pd.DataFrame, tfs=("1m", "5m", "15m", "1h", "4h", "1d")) -> dict:
    return {tf: resample(s1m, tf) for tf in tfs}


def next_open(now_utc: datetime) -> datetime:
    """Next forex.com session open after a closed moment (for display)."""
    t = pd.Timestamp(now_utc).tz_convert(ET)
    for i in range(0, 8 * 24 * 60, 15):
        cand = t + timedelta(minutes=i)
        if in_session(pd.DatetimeIndex([cand.tz_convert("UTC")]))[0]:
            return cand.floor("15min").to_pydatetime()
    return t.to_pydatetime()


def week_key(sdates) -> pd.Series:
    """Trading week label = Monday of the session date's week."""
    s = pd.to_datetime(pd.Series(sdates))
    return (s - pd.to_timedelta(s.dt.dayofweek, unit="D")).dt.date
