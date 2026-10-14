"""Trend state per timeframe and the shift events the bot alerts on.

Every definition uses closed candles only and is known at the candle's close, so a
shift never repaints. A shift is the bar where the state flips from +1 to -1 or back.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TF_MIN = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df.c.shift()
    tr = pd.concat([df.h - df.l, (df.h - pc).abs(), (df.l - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def state_ema(df: pd.DataFrame, fast: int = 20, slow: int = 50) -> pd.Series:
    """+1 when EMA20 > EMA50, -1 when below."""
    c = df.c
    return np.sign(c.ewm(span=fast, adjust=False).mean() - c.ewm(span=slow, adjust=False).mean()).replace(0, np.nan).ffill()


def state_structure(df: pd.DataFrame, k: int = 3, with_levels: bool = False):
    """Market-structure trend (BOS / CHoCH style).

    Swing highs/lows are fractals with k candles either side, so a swing only counts k
    candles after it formed. State turns bullish when a candle CLOSES above the latest
    confirmed swing high, bearish when it closes below the latest confirmed swing low.
    """
    h, l, c = df.h.to_numpy(), df.l.to_numpy(), df.c.to_numpy()
    n = len(df)
    win = 2 * k + 1
    hmax = pd.Series(h).rolling(win, center=True).max().to_numpy()
    lmin = pd.Series(l).rolling(win, center=True).min().to_numpy()
    is_sh = (h == hmax)
    is_sl = (l == lmin)
    state = np.full(n, np.nan)
    broke = np.full(n, np.nan)      # swing level broken on the flip bar
    inval = np.full(n, np.nan)      # opposite swing: closing beyond it flips the trend back
    last_sh = last_sl = np.nan
    cur = np.nan
    for i in range(n):
        j = i - k  # the swing at j is confirmed once bar i (k bars later) has closed
        if j >= 0:
            if is_sh[j]:
                last_sh = h[j]
            if is_sl[j]:
                last_sl = l[j]
        if not np.isnan(last_sh) and c[i] > last_sh and cur != 1:
            cur = 1
            broke[i], inval[i] = last_sh, last_sl
        elif not np.isnan(last_sl) and c[i] < last_sl and cur != -1:
            cur = -1
            broke[i], inval[i] = last_sl, last_sh
        state[i] = cur
    st = pd.Series(state, index=df.index)
    if with_levels:
        return st, pd.Series(broke, index=df.index), pd.Series(inval, index=df.index)
    return st


def state_supertrend(df: pd.DataFrame, n: int = 10, mult: float = 3.0) -> pd.Series:
    a = atr(df, n).to_numpy()
    h, l, c = df.h.to_numpy(), df.l.to_numpy(), df.c.to_numpy()
    mid = (h + l) / 2
    ub, lb = mid + mult * a, mid - mult * a
    fub, flb = ub.copy(), lb.copy()
    st = np.full(len(df), np.nan)
    d = 1
    for i in range(1, len(df)):
        fub[i] = ub[i] if (ub[i] < fub[i - 1] or c[i - 1] > fub[i - 1]) else fub[i - 1]
        flb[i] = lb[i] if (lb[i] > flb[i - 1] or c[i - 1] < flb[i - 1]) else flb[i - 1]
        if d == 1 and c[i] < flb[i]:
            d = -1
        elif d == -1 and c[i] > fub[i]:
            d = 1
        st[i] = d
    return pd.Series(st, index=df.index)


def state_donchian(df: pd.DataFrame, n: int = 20) -> pd.Series:
    hi = df.h.shift().rolling(n).max()
    lo = df.l.shift().rolling(n).min()
    s = pd.Series(np.where(df.c > hi, 1.0, np.where(df.c < lo, -1.0, np.nan)), index=df.index)
    return s.ffill()


DEFINITIONS = {
    "ema20_50": state_ema,
    "structure": state_structure,
    "supertrend": state_supertrend,
    "donchian20": state_donchian,
}


def shifts(df: pd.DataFrame, tf: str, definition: str) -> pd.DataFrame:
    """Shift events, indexed by the time they become known (candle close)."""
    broke = inval = None
    if definition == "structure":
        st, broke, inval = state_structure(df, with_levels=True)
    else:
        st = DEFINITIONS[definition](df)
    prev = st.shift()
    ev = df.loc[(st != prev) & prev.notna() & st.notna()].copy()
    ev["dir"] = st.loc[ev.index].astype(int)
    ev["broke"] = broke.loc[ev.index] if broke is not None else np.nan
    ev["invalid"] = inval.loc[ev.index] if inval is not None else np.nan
    ev["atr"] = atr(df).loc[ev.index]
    ev["price"] = ev.c
    ev["open_time"] = ev.index
    ev.index = ev.index + pd.Timedelta(minutes=TF_MIN[tf]) if tf != "1d" else ev.index + pd.Timedelta(hours=23)
    ev.index.name = "time"
    return ev[["dir", "price", "atr", "broke", "invalid", "open_time", "sdate"]]


def state_at(df: pd.DataFrame, tf: str, definition: str, times: pd.DatetimeIndex) -> np.ndarray:
    """Trend state as known at each time (from closed candles)."""
    st = DEFINITIONS[definition](df)
    known = st.index + (pd.Timedelta(minutes=TF_MIN[tf]) if tf != "1d" else pd.Timedelta(hours=23))
    s = pd.Series(st.to_numpy(), index=known).dropna()
    return pd.merge_asof(pd.DataFrame({"t": times}), pd.DataFrame({"t": s.index, "v": s.values}), on="t").v.to_numpy()


def follow_through(s1m: pd.DataFrame, times: pd.DatetimeIndex, dirs, atrs, horizon_min: int,
                   cost_usd: float = 0.40, stop_atr: float = 1.0, max_gap_min: int = 120) -> pd.DataFrame:
    """What happened after each event, measured on 1m candles (intrabar-accurate).

    From the close price at `time`, in direction `dir`, with stop = stop_atr x ATR(TF):
      hit1  : +1 R reached before -1 R            (coin-flip ~50%)
      hit2  : +2 R reached before -1 R            (coin-flip ~33%)
      r2    : result of a 1:2 trade in R, net of cost (timeout = marked to market)
      ret   : move to the horizon end in R
      mfe/mae: best / worst excursion in R
    Horizon counts in-session minutes and never crosses a weekend.
    """
    t1 = s1m.index + pd.Timedelta(minutes=1)
    h, l, c = s1m.h.to_numpy(), s1m.l.to_numpy(), s1m.c.to_numpy()
    tsec = (t1.asi8 // 10**9)
    pos = np.searchsorted(t1.asi8, pd.DatetimeIndex(times).asi8, side="right")  # first bar after the event
    n = len(s1m)
    H = horizon_min
    out = {k: np.full(len(times), np.nan) for k in ("hit1", "hit2", "r2", "ret", "mfe", "mae")}
    dirs = np.asarray(dirs, float)
    atrs = np.asarray(atrs, float)
    entry_px = np.asarray([np.nan] * len(times))
    # entry = close of the last 1m candle at/ before the event time
    ok = pos > 0
    entry_px[ok] = c[pos[ok] - 1]
    pad = H
    hp = np.concatenate([h, np.full(pad, np.nan)])
    lp = np.concatenate([l, np.full(pad, np.nan)])
    cp = np.concatenate([c, np.full(pad, np.nan)])
    tp_ = np.concatenate([tsec, np.full(pad, np.iinfo(np.int64).max)])
    for s in range(0, len(times), 2000):
        e = min(len(times), s + 2000)
        rows = np.arange(s, e)
        rows = rows[ok[rows] & (pos[rows] < n) & np.isfinite(atrs[rows]) & (atrs[rows] > 0)]
        if not len(rows):
            continue
        idx = pos[rows, None] + np.arange(H)[None, :]
        Hh, Ll, Cc, Tt = hp[idx], lp[idx], cp[idx], tp_[idx]
        # cut at a gap longer than max_gap_min (weekend / holiday)
        gaps = np.diff(Tt, axis=1, prepend=Tt[:, :1]) > max_gap_min * 60
        cut = np.cumsum(gaps, axis=1) > 0
        Hh = np.where(cut, np.nan, Hh)
        Ll = np.where(cut, np.nan, Ll)
        Cc = np.where(cut, np.nan, Cc)
        d, a, px = dirs[rows], atrs[rows] * stop_atr, entry_px[rows]
        fav = np.where(d[:, None] > 0, Hh - px[:, None], px[:, None] - Ll) / a[:, None]
        adv = np.where(d[:, None] > 0, px[:, None] - Ll, Hh - px[:, None]) / a[:, None]
        last_c = pd.DataFrame(Cc).ffill(axis=1).to_numpy()[:, -1]
        ret = d * (last_c - px) / a

        def first(mask):
            anyv = mask.any(1)
            return np.where(anyv, mask.argmax(1), H + 1)
        f_stop = first(adv >= 1)
        f1, f2 = first(fav >= 1), first(fav >= 2)
        out["hit1"][rows] = (f1 < f_stop).astype(float)
        out["hit2"][rows] = (f2 < f_stop).astype(float)
        r2 = np.where(f2 < f_stop, 2.0, np.where(f_stop <= H, -1.0, np.clip(ret, -1, 2)))
        out["r2"][rows] = r2 - cost_usd / a
        out["ret"][rows] = ret
        out["mfe"][rows] = np.nanmax(fav, axis=1)
        out["mae"][rows] = np.nanmax(adv, axis=1)
    return pd.DataFrame(out, index=pd.DatetimeIndex(times))
