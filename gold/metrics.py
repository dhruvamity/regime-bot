"""Trend-vs-chop measurements.

Structure metrics (per bar, then averaged over any window):
  er    Kaufman efficiency ratio over 10 bars: net move / total distance travelled.
        1.0 = straight line, ~0.2-0.3 = random, lower = back-and-forth chop.
  chop  Choppiness Index (14). >61.8 choppy, <38.2 trending.
  wick  share of each candle that is wick rather than body. High = rejection/stop-hunt candles.
  vr    variance ratio (k=6): >1 moves follow through, <1 moves snap back (mean reversion).
Outcome metrics (what a trader would actually have experienced):
  tf2   avg R of trend-following entries with 1:2 RR (stop = 1 ATR, after costs)
  tf1   same with 1:1 RR
  fd1   fade (counter-trend) entries with 1:1 RR
"""
import numpy as np
import pandas as pd

from .config import COST_USD

VR_K = 6
HORIZON = {"1m": 60, "5m": 48, "15m": 32, "1h": 24}


def bar_features(df: pd.DataFrame) -> pd.DataFrame:
    o, h, l, c = df.o, df.h, df.l, df.c
    pc = c.shift()
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    out = pd.DataFrame(index=df.index)
    out["tr"] = tr
    out["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    absd = c.diff().abs()
    out["er"] = (c - c.shift(10)).abs() / absd.rolling(10).sum().replace(0, np.nan)
    rng14 = h.rolling(14).max() - l.rolling(14).min()
    out["chop"] = 100 * np.log10(tr.rolling(14).sum() / rng14.replace(0, np.nan)) / np.log10(14)
    hl = (h - l).replace(0, np.nan)
    out["wick"] = (hl - (c - o).abs()) / hl
    out["r"] = np.log(c).diff()
    out["rk"] = out["r"].rolling(VR_K).sum()
    ema20 = c.ewm(span=20, adjust=False).mean()
    ema50 = c.ewm(span=50, adjust=False).mean()
    out["dir"] = np.sign(ema20 - ema50)
    out["sdate"] = df["sdate"].values
    return out


def simulate(df: pd.DataFrame, direction, risk, rrs=(2.0, 1.0), hz: int = 48,
             cost_usd: float = COST_USD) -> dict:
    """Enter at each bar close where direction != 0 with stop distance `risk` ($).

    Returns {rr: array of R outcomes (nan = no trade)}. Same-bar TP+SL touch counts as a
    loss; trades never carry past the session end (marked to market at the last bar).
    """
    h = df.h.to_numpy(np.float64)
    l = df.l.to_numpy(np.float64)
    c = df.c.to_numpy(np.float64)
    sd = pd.factorize(df["sdate"])[0]
    d = np.nan_to_num(np.asarray(direction, dtype=np.float64))
    risk = np.asarray(risk, dtype=np.float64)
    n = len(df)
    pad = np.full(hz, np.nan)
    hp, lp, cp = np.concatenate([h, pad]), np.concatenate([l, pad]), np.concatenate([c, pad])
    sdp = np.concatenate([sd, np.full(hz, -1)])
    res = {rr: np.full(n, np.nan) for rr in rrs}
    todo = np.flatnonzero((d != 0) & np.isfinite(risk) & (risk > 0))
    chunk = 40000
    for s in range(0, len(todo), chunk):
        rows = todo[s:s + chunk]
        idx = rows[:, None] + 1 + np.arange(hz)[None, :]
        H, L, C, S = hp[idx], lp[idx], cp[idx], sdp[idx]
        valid = S == sd[rows, None]
        H = np.where(valid, H, np.nan)
        L = np.where(valid, L, np.nan)
        nvalid = valid.sum(axis=1)
        last_c = np.where(nvalid > 0, C[np.arange(len(rows)), np.maximum(nvalid - 1, 0)], np.nan)
        entry, rk, dd = c[rows], risk[rows], d[rows]
        up = dd > 0
        sl = np.where(up, entry - rk, entry + rk)
        hit_sl = np.where(up[:, None], L <= sl[:, None], H >= sl[:, None])
        fsl = np.where(hit_sl.any(1), hit_sl.argmax(1), hz + 1)
        mtm = dd * (last_c - entry) / rk
        cost_r = cost_usd / rk
        for rr in rrs:
            tp = np.where(up, entry + rr * rk, entry - rr * rk)
            hit_tp = np.where(up[:, None], H >= tp[:, None], L <= tp[:, None])
            ftp = np.where(hit_tp.any(1), hit_tp.argmax(1), hz + 1)
            r = np.where(fsl <= ftp, np.where(fsl <= hz, -1.0, mtm), rr) - cost_r
            r[nvalid < max(3, hz // 4)] = np.nan
            res[rr][rows] = r
    return res


def trade_outcomes(df: pd.DataFrame, feat: pd.DataFrame, tf: str, cost_usd: float = COST_USD) -> pd.DataFrame:
    """Entry at every bar close, trend-following (EMA20 vs EMA50) and fade. Stop = 1 ATR."""
    hz = HORIZON[tf]
    d = feat.dir.fillna(0).to_numpy()
    trend = simulate(df, d, feat.atr.to_numpy(), (2.0, 1.0), hz, cost_usd)
    fade = simulate(df, -d, feat.atr.to_numpy(), (1.0,), hz, cost_usd)
    return pd.DataFrame({"tf2": trend[2.0], "tf1": trend[1.0], "fd1": fade[1.0]}, index=df.index)


def add_all(df: pd.DataFrame, tf: str, outcomes: bool = True) -> pd.DataFrame:
    f = bar_features(df)
    if outcomes and tf in HORIZON:
        f = f.join(trade_outcomes(df, f, tf))
    return f


def window_stats(f: pd.DataFrame) -> dict:
    """Aggregate bar features over a window into one row."""
    r, rk = f["r"], f["rk"]
    vr = rk.var() / (VR_K * r.var()) if r.count() > 3 * VR_K else np.nan
    out = {"er": f["er"].mean(), "chop": f["chop"].mean(), "wick": f["wick"].mean(), "vr": vr,
           "atr": f["atr"].mean(), "n": len(f)}
    for k in ("tf2", "tf1", "fd1"):
        if k in f:
            out[k] = f[k].mean()
    return out


def group_stats(f: pd.DataFrame, key) -> pd.DataFrame:
    """Vectorised window_stats over groups (e.g. session date or week)."""
    g = f.groupby(key)
    out = g[["er", "chop", "wick", "atr"]].mean()
    out["vr"] = g["rk"].var() / (VR_K * g["r"].var())
    out["n"] = g.size()
    for k in ("tf2", "tf1", "fd1"):
        if k in f:
            out[k] = g[k].mean()
    return out


def rolling_stats(f: pd.DataFrame, bars: int) -> pd.DataFrame:
    """Trailing-window version of window_stats at every bar (no look-ahead)."""
    mp = max(3, bars // 2)
    out = pd.DataFrame(index=f.index)
    for k in ("er", "chop", "wick", "atr"):
        out[k] = f[k].rolling(bars, min_periods=mp).mean()
    out["vr"] = f["rk"].rolling(bars, min_periods=mp).var() / (VR_K * f["r"].rolling(bars, min_periods=mp).var())
    return out


def adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df.h, df.l, df.c
    up, dn = h.diff(), -l.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pc = c.shift()
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    pdi = 100 * pd.Series(pdm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    ndi = 100 * pd.Series(ndm, index=df.index).ewm(alpha=1 / n, adjust=False).mean() / atr
    dx = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    return dx.ewm(alpha=1 / n, adjust=False).mean()
