"""Day / week comparison tables shared by the report script and the live server."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import metrics, session
from .config import BASELINE_DAYS, ET, SESSION_OPEN_HOUR_ET
from .signal import Engine

STRUCT = ("er", "chop", "wick", "vr", "atr", "y2", "y1")
LABELS = {
    "er": "Efficiency (higher = cleaner trend)",
    "chop": "Choppiness Index (higher = choppier)",
    "wick": "Wick share of candles (higher = more rejection)",
    "vr": "Follow-through / variance ratio (>1 trends, <1 snaps back)",
    "atr": "ATR $ (movement per candle)",
    "y2": "Trend-follow 1:2 net R per entry (with 1h bias)",
    "y1": "Trend-follow 1:1 net R per entry (with 1h bias)",
}


def _group(f: pd.DataFrame, key) -> pd.DataFrame:
    g = f.groupby(key)
    out = g[["er", "chop", "wick", "atr", "y2", "y1"]].mean()
    out["vr"] = g["rk"].var() / (metrics.VR_K * g["r"].var())
    return out


def daily_table(eng: Engine) -> pd.DataFrame:
    d1 = eng.tfs["1d"].copy()
    d1.index = pd.to_datetime(d1.sdate)
    d1["range"] = d1.h - d1.l
    ov = (np.minimum(d1.h, d1.h.shift()) - np.maximum(d1.l, d1.l.shift())).clip(lower=0)
    d1["overlap"] = ov / d1.range
    d1["body"] = (d1.c - d1.o).abs() / d1.range
    parts = [d1[["o", "h", "l", "c", "range", "overlap", "body"]]]
    for tf in ("1m", "5m", "15m"):
        f = eng.bar[tf]
        t = _group(f, pd.to_datetime(f.sdate))
        t.columns = [f"{c}_{tf}" for c in t.columns]
        parts.append(t)
    h = eng.tfs["1h"]
    path = h.c.diff().abs().groupby(h.sdate.values).sum()
    net = (h.c.groupby(h.sdate.values).last() - h.o.groupby(h.sdate.values).first()).abs()
    pe = (net / path)
    pe.index = pd.to_datetime(pe.index)
    D = pd.concat(parts, axis=1)
    D["path_eff_1h"] = pe
    D["minutes"] = eng.s1m.groupby(eng.s1m.sdate.values).size().reindex(D.index.date).values
    return D


def weekly_table(D: pd.DataFrame) -> pd.DataFrame:
    wk = session.week_key(D.index.date)
    wk.index = D.index
    D = D.assign(wk=wk.values)
    agg = {"o": "first", "h": "max", "l": "min", "c": "last", "range": "mean", "overlap": "mean", "path_eff_1h": "mean",
           "minutes": "sum"}
    for tf in ("1m", "5m", "15m"):
        for k in STRUCT:
            agg[f"{k}_{tf}"] = "mean"
    W = D.groupby("wk").agg(agg)
    W["days"] = D.groupby("wk").size()
    W = W.rename(columns={"range": "avg_day_range"})
    W["week_range"] = W.h - W.l
    W["net_move"] = W.c - W.o
    W["y2_ltf"] = W[["y2_1m", "y2_5m", "y2_15m"]].mean(axis=1)
    W["y1_ltf"] = W[["y1_1m", "y1_5m", "y1_15m"]].mean(axis=1)
    return W


def pct_rank(series: pd.Series, value: float) -> float:
    s = series.dropna()
    return float((s < value).mean() * 100) if len(s) else float("nan")


def week_verdict(W: pd.DataFrame, wk) -> dict:
    """Where a week sits vs the previous ~6 months of weeks."""
    base = W[(W.index < wk) & (W.index >= pd.Timestamp(wk).date() - pd.Timedelta(days=BASELINE_DAYS))]
    base = base[base.days >= 4]
    row = W.loc[wk]
    out = {}
    for c in ["avg_day_range", "week_range", "overlap", "path_eff_1h", "atr_5m", "er_5m", "er_15m", "chop_15m",
              "wick_5m", "vr_5m", "vr_15m", "y2_ltf", "y1_ltf", "y2_1m", "y2_5m", "y2_15m", "y1_1m", "y1_5m", "y1_15m"]:
        out[c] = {"value": float(row[c]), "median_6m": float(base[c].median()), "pct": pct_rank(base[c], row[c])}
    return out


def bad_week_mask(W: pd.DataFrame) -> pd.Series:
    """'Like last week' = movement in the bottom 20% of the trailing 6 months AND below-median LTF results."""
    res = []
    for wk in W.index:
        base = W[(W.index < wk) & (W.index >= wk - pd.Timedelta(days=BASELINE_DAYS)) & (W.days >= 4)]
        if len(base) < 12:
            res.append(np.nan)
            continue
        low_move = W.loc[wk, "avg_day_range"] <= base.avg_day_range.quantile(0.20)
        poor = W.loc[wk, "y2_ltf"] <= base.y2_ltf.median()
        res.append(bool(low_move and poor))
    return pd.Series(res, index=W.index, dtype="object")


def session_open_utc(sdate) -> pd.Timestamp:
    d = pd.Timestamp(sdate) - pd.Timedelta(days=1)
    return pd.Timestamp(d.year, d.month, d.day, SESSION_OPEN_HOUR_ET, tz=ET).tz_convert("UTC")


def time_matched(eng: Engine, sdates, elapsed: pd.Timedelta) -> pd.DataFrame:
    """Stats for each session using only the first `elapsed` of that session."""
    rows = {}
    for sd in sdates:
        start = session_open_utc(sd)
        end = start + elapsed
        r = {}
        s1 = eng.s1m[(eng.s1m.sdate == sd) & (eng.s1m.index < end - pd.Timedelta(minutes=1) + pd.Timedelta(seconds=1))]
        if len(s1) == 0:
            continue
        r["range"] = s1.h.max() - s1.l.min()
        r["net"] = s1.c.iloc[-1] - s1.o.iloc[0]
        for tf in ("1m", "5m", "15m"):
            f = eng.bar[tf]
            ff = f[(f.sdate == sd) & (f.index <= end)]
            ws = metrics.window_stats(ff.assign())
            for k in ("er", "chop", "wick", "vr", "atr"):
                r[f"{k}_{tf}"] = ws[k]
            # y2/y1 only for trades resolved before `end`
            hz = metrics.HORIZON[tf] * pd.Timedelta(minutes={"1m": 1, "5m": 5, "15m": 15}[tf])
            fr = ff[ff.index <= end - hz]
            r[f"y2_{tf}"] = fr.y2.mean()
            r[f"y1_{tf}"] = fr.y1.mean()
        rows[pd.Timestamp(sd)] = r
    return pd.DataFrame(rows).T


def today_vs_last_week(eng: Engine) -> dict:
    """Compare the current session so far against last week's sessions at the same elapsed time."""
    sdates = sorted(set(eng.s1m.sdate))
    today = sdates[-1]
    start = session_open_utc(today)
    elapsed = eng.last_bar_close - start
    wk_today = session.week_key([today]).iloc[0]
    prev_wk = wk_today - pd.Timedelta(days=7)
    last_week_days = [d for d in sdates if session.week_key([d]).iloc[0] == prev_wk]
    if today and session.week_key([today]).iloc[0] != wk_today:
        last_week_days = []
    prior6m = [d for d in sdates[:-1] if pd.Timestamp(d) >= pd.Timestamp(today) - pd.Timedelta(days=BASELINE_DAYS)]
    tm_today = time_matched(eng, [today], elapsed)
    tm_lw = time_matched(eng, last_week_days, elapsed)
    tm_6m = time_matched(eng, prior6m, elapsed)
    return {
        "today": str(today),
        "elapsed_hours": round(elapsed.total_seconds() / 3600, 2),
        "last_week": [str(d) for d in last_week_days],
        "table_today": tm_today,
        "table_last_week": tm_lw,
        "table_6m": tm_6m,
    }
