"""SMC bias finder: market structure mapped by the rules of the "SMC A to Z" guide, on any timeframe.

One implementation for the live bot, the backtest (scripts/backtest_bias.py) and the replay check
(scripts/verify_bias.py). Runs candle by candle on CLOSED candles only, so nothing repaints: the state at a
candle is known the moment it closes.

The rules (chapter numbers from the guide):
  Swings (ch.2)     A swing low is a candle whose low swept the previous candle's low, with the next candle
                    turning up (a "V"). Candles inside a larger "mother" candle are ignored until the mother's
                    high or low is taken, so the mother's extreme must be swept first.
  Inducement (ch.7) In an uptrend, the most recent pullback low to the LEFT of the current high.
  Mapping (ch.8)    1. A high is not confirmed until its inducement is taken (a wick through is enough: the
                       liquidity is taken). The highest wick before that becomes the confirmed HH, the BOS level.
                    2. No inducement, no BOS: highs that break before the IDM is taken are "aggressive buying";
                       the IDM trails forward to the latest pullback and the CHoCH point does not move.
                    3. The CHoCH point moves only after IDM + BOS: on the BOS candle it becomes the lowest
                       point between the HH candle and the BOS candle (the vertical-line method).
  BOS / CHoCH (ch.6) Both need a BODY CLOSE beyond the level; a wick through is a sweep. A close below the
                    CHoCH point flips the trend to bearish, and the new lower high (the level whose break flips it
                    back) is the top of the whole move, not the minor swing that broke.
  Downtrends mirror all of this.

Start-up: the first candle that closes beyond the range of the first 20 candles sets the initial trend.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import session, store
from .config import CLOSED_SESSION_DATES, DATA_DIR, EARLY_CLOSE_DATES, ET, LISTING_MS, SESSION_CLOSE_HOUR_ET

BOOT = 20


@dataclass
class Event:
    i: int              # candle index (position) of the closing candle
    kind: str           # CHOCH | BOS | IDM
    dir: int            # trend after the event (+1 bullish, -1 bearish); for IDM the trend it threatens
    level: float        # the level the candle broke (real price)
    invalid: float      # the new CHoCH point: a close beyond it flips the trend (real price)
    ext: float          # confirmed HH (bull) / LL (bear) at the time, real price, nan if none


def _swings(h, l):
    """Swing highs/lows on the inside-bar-filtered series.

    Returns two lists of (confirm_index, swing_index, price): a swing at candle j is known when the next
    non-inside candle k closes. Swing low: l[j] < l[prev] and l[k] > l[j] (strict); highs mirror it.
    """
    lows, highs = [], []
    seq = []                       # indices of non-inside ("mother") candles
    for i in range(len(h)):
        if seq:
            m = seq[-1]
            if h[i] <= h[m] and l[i] >= l[m]:
                continue           # inside the mother candle: ignored until the mother is swept
        seq.append(i)
        if len(seq) >= 3:
            p, j, k = seq[-3], seq[-2], seq[-1]
            if l[j] < l[p] and l[k] > l[j]:
                lows.append((k, j, l[j]))
            if h[j] > h[p] and h[k] < h[j]:
                highs.append((k, j, h[j]))
    return lows, highs


def map_structure(df: pd.DataFrame):
    """Map structure on one timeframe. df: o,h,l,c indexed by candle open time, closed candles only.

    Returns (bars, events):
      bars   per candle: trend (+1/-1/0), choch (the level whose close-through flips the trend), ext (confirmed
             HH in an uptrend / LL in a downtrend, nan until the IDM is taken), idm (current inducement), run
             (running extreme of the current leg)
      events DataFrame of CHOCH / BOS / IDM events at the candle that closed them
    """
    h, l, c = df.h.to_numpy(float), df.l.to_numpy(float), df.c.to_numpy(float)
    n = len(df)
    sw_lo, sw_hi = _swings(h, l)
    # confirmed swings per sign, in "trend space": for s=+1 pullback lows are real lows (value l);
    # for s=-1 they are real highs, stored negated so one code path handles both directions
    piv = {1: sw_lo, -1: [(k, j, -p) for k, j, p in sw_hi]}
    out = np.full((n, 6), np.nan)
    ev: list[Event] = []

    s = 0
    mss_lvl = None                 # the inducement that was taken (trend space)
    internal = 0                   # internal bias: flips on an MSS against the trend, back on the next BOS / CHoCH
    choch = choch_i = run = run_i = idm = hh = hh_i = None
    ptr = {1: 0, -1: 0}           # next unconsumed swing per sign (by confirm index)
    known = {1: [], -1: []}        # (swing_index, value) confirmed so far, per sign

    def H(k, sg):
        return h[k] if sg > 0 else -l[k]

    def L(k, sg):
        return l[k] if sg > 0 else -h[k]

    def real(v, sg):
        return v if sg > 0 else -v

    def fvg(k, d):
        """Displacement: a fair value gap in direction d among the last 3 candles ending at k (known at k's close)."""
        if k < 2:
            return False
        return (l[k] > h[k - 2]) if d > 0 else (h[k] < l[k - 2])

    def latest_pullback(sg, after, before):
        """Most recent confirmed pullback low (trend space) with after < index < before."""
        for j, v in reversed(known[sg]):
            if j <= after:
                return None
            if j < before:
                return v
        return None

    for i in range(n):
        for sg in (1, -1):        # swings confirmed by this candle's close
            lst = piv[sg]
            while ptr[sg] < len(lst) and lst[ptr[sg]][0] <= i:
                _, j, v = lst[ptr[sg]]
                known[sg].append((j, v))
                ptr[sg] += 1

        if s == 0:                 # start-up
            if i >= BOOT:
                hi0, lo0 = h[:BOOT].max(), l[:BOOT].min()
                if c[i] > hi0 or c[i] < lo0:
                    s = 1 if c[i] > hi0 else -1
                    seg = np.array([L(k, s) for k in range(0, i + 1)])
                    choch_i = int(seg.argmin()); choch = float(seg[choch_i])
                    segh = np.array([H(k, s) for k in range(choch_i, i + 1)])
                    run_i = choch_i + int(segh.argmax()); run = float(segh.max())
                    idm = latest_pullback(s, choch_i, run_i)
                    hh = hh_i = None
                    internal = s
            if s == 0:
                continue
            out[i] = [s, real(choch, s), np.nan, np.nan if idm is None else real(idm, s), real(run, s), internal]
            continue

        Ci, Hi, Li = c[i] * s, H(i, s), L(i, s)

        # 1. CHoCH: body close beyond the CHoCH point -> trend flips
        if Ci < choch:
            old = choch
            top = np.array([H(k, s) for k in range(choch_i, i + 1)])      # the whole move since the HL
            top_i = choch_i + int(top.argmax())
            s = -s
            choch_i, choch = top_i, L(top_i, s)                           # new LH = top of the whole move
            seg = np.array([H(k, s) for k in range(top_i + 1, i + 1)]) if i > top_i else np.array([H(i, s)])
            run_i = (top_i + 1 + int(seg.argmax())) if i > top_i else i
            run = float(seg.max())
            idm = latest_pullback(s, choch_i, run_i)
            hh = hh_i = None
            internal = s
            ev.append(Event(i, "CHOCH", s, real(old, -s), real(choch, s), np.nan))
        # 2. waiting for the BOS (IDM taken, HH confirmed)
        elif hh is not None:
            if Ci > hh:
                seg = np.array([L(k, s) for k in range(hh_i, i + 1)])
                new_i = hh_i + int(seg.argmin())
                lvl = hh
                choch_i, choch = new_i, float(seg.min())                  # vertical-line method
                segh = np.array([H(k, s) for k in range(hh_i + 1, i + 1)])
                run_i = hh_i + 1 + int(segh.argmax()); run = float(segh.max())
                idm = latest_pullback(s, choch_i, run_i)
                hh = hh_i = None
                if internal != s:
                    ev.append(Event(i, "MSS", s, real(lvl, s), real(choch, s), np.nan))   # internal back with the trend
                internal = s
                ev.append(Event(i, "BOS", s, real(lvl, s), real(choch, s), np.nan))
        # 3. building the leg: track the high, trail the IDM, watch for the IDM being taken
        else:
            if idm is not None and Li < idm:
                hh, hh_i = run, run_i                                     # the high is now confirmed
                ev.append(Event(i, "IDM", s, real(idm, s), real(choch, s), real(hh, s)))
                mss_lvl = idm
                idm = None
            if hh is None and Hi > run:
                run, run_i = Hi, i
                idm = latest_pullback(s, choch_i, run_i)                  # IDM trails to the latest pullback
            elif hh is None and idm is None:
                idm = latest_pullback(s, choch_i, run_i)                  # a pullback left of the high may confirm late
        # MSS (minor CHoCH, ch.7): with the HH confirmed, a body close back through the taken IDM, with
        # displacement, flips the internal bias against the trend until the next BOS / CHoCH
        if hh is not None and internal == s and mss_lvl is not None and c[i] * s < mss_lvl and fvg(i, -s):
            internal = -s
            ev.append(Event(i, "MSS", -s, real(mss_lvl, s), real(hh, s), real(choch, s)))
        out[i] = [s, real(choch, s), np.nan if hh is None else real(hh, s), np.nan if idm is None else real(idm, s),
                  real(run, s), internal]

    bars = pd.DataFrame(out, index=df.index, columns=["trend", "choch", "ext", "idm", "run", "internal"])
    E = pd.DataFrame([e.__dict__ for e in ev], columns=["i", "kind", "dir", "level", "invalid", "ext"])
    E.index = df.index[E.i.to_numpy(int)] if len(E) else pd.DatetimeIndex([], tz="UTC")
    E.index.name = "open_time"
    E["close"] = c[E.i.to_numpy(int)] if len(E) else []
    return bars, E


# ------------------------------------------------------------------ candle-to-candle bias (ch.12)
def candle_bias(df: pd.DataFrame) -> pd.DataFrame:
    """For each closed candle B vs the candle before it (A): the guide's bias for the NEXT candle and its target.

      B's body closed above A's high            -> bullish, target B's high at minimum
      B swept A's low and closed back inside    -> bullish, target A's high (the range candle's high)
      B's body closed below A's low             -> bearish, target B's low
      B swept A's high and closed back inside   -> bearish, target A's low
    A candle that swept both sides and closed inside, or did neither, gives no bias.
    """
    ah, al = df.h.shift(), df.l.shift()
    bh, bl, bc = df.h, df.l, df.c
    up_close, dn_close = bc > ah, bc < al
    sw_lo = (bl < al) & (bc >= al) & ~up_close & ~(bh > ah)
    sw_hi = (bh > ah) & (bc <= ah) & ~dn_close & ~(bl < al)
    bias = np.select([up_close, dn_close, sw_lo, sw_hi], [1, -1, 1, -1], 0)
    target = np.select([up_close, dn_close, sw_lo, sw_hi], [bh, bl, ah, al], np.nan)
    why = np.select([up_close, dn_close, sw_lo, sw_hi],
                    ["closed above the previous high", "closed below the previous low",
                     "swept the previous low and closed back inside", "swept the previous high and closed back inside"], "")
    return pd.DataFrame({"bias": bias, "target": target, "why": why}, index=df.index)


# ------------------------------------------------------------------ timeframes
TF_ORDER = ("5m", "15m", "1h", "4h", "1d", "1w")
TF_MIN = {"5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080}
HIGHER = {"5m": "15m", "15m": "1h", "1h": "4h", "4h": "1d", "1d": "1w", "1w": None}


def session_close(sdates) -> pd.DatetimeIndex:
    """UTC time each session (ET trade date) closes: 17:00 ET, or the early close on listed holidays."""
    out = {}
    for d in pd.unique(np.asarray(sdates).astype(str)):
        hr = EARLY_CLOSE_DATES.get(d, SESSION_CLOSE_HOUR_ET)
        out[d] = (pd.Timestamp(str(d)).tz_localize(ET) + pd.Timedelta(hours=hr)).tz_convert("UTC")
    return pd.DatetimeIndex([out[d] for d in np.asarray(sdates).astype(str)])


def _week_last_session(monday: str) -> str:
    """The last trading session of the week starting `monday` (Friday unless the market is shut that day)."""
    d = pd.Timestamp(str(monday)) + pd.Timedelta(days=4)
    while d.strftime("%Y-%m-%d") in CLOSED_SESSION_DATES:
        d -= pd.Timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def weekly(d1: pd.DataFrame) -> pd.DataFrame:
    """Weekly candles from session-dated daily candles. A week = the Monday-Friday sessions (Sunday's 18:00 ET
    open belongs to Monday's session). `final` is the week's last scheduled session, so a week still in progress
    is never treated as closed."""
    sd = pd.to_datetime(pd.Series(d1["sdate"].astype(str).to_numpy(), index=d1.index))
    wk = (sd - pd.to_timedelta(sd.dt.dayofweek, unit="D")).dt.strftime("%Y-%m-%d")
    g = d1.assign(wk=wk.to_numpy()).reset_index().groupby("wk", sort=True)
    w = g.agg(time=("time", "first"), o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"),
              sdate=("sdate", "last"))
    w["final"] = [_week_last_session(k) for k in w.index]
    return w.set_index("time").sort_index()


def known_at(df: pd.DataFrame, tf: str) -> pd.DatetimeIndex:
    """When each candle is final: its natural end, or its session's close if that comes first (the last 4h
    candle of a session, early-close holidays). Daily = the session close; weekly = the week's last session."""
    if tf == "1w":
        return session_close(df["final"])
    sc = session_close(df["sdate"])
    if tf == "1d":
        return sc
    end = df.index + pd.Timedelta(minutes=TF_MIN[tf])
    sc = sc.as_unit(end.unit)
    return end.where(end <= sc, sc)


def frames(tfs: dict) -> dict:
    """Bias timeframes (session-filtered, from gold.session.build_all) plus weekly."""
    out = {tf: tfs[tf] for tf in ("5m", "15m", "1h", "4h", "1d") if tf in tfs}
    if "1d" in tfs and len(tfs["1d"]):
        out["1w"] = weekly(tfs["1d"])
    return out


SEED_FILE = DATA_DIR / "paxg_1m.parquet"
SEED_TFS = ("4h", "1d")          # (weekly is built from the seeded daily)


def paxg_clean(d: pd.DataFrame) -> pd.DataFrame:
    """PAXG has thin-book spikes: wicks longer than 15x the rolling median 1m range are trimmed."""
    d = d.copy()
    med = (d.h - d.l).rolling(60, min_periods=10).median().bfill()
    cap = 15 * med.clip(lower=0.2)
    top, bot = d[["o", "c"]].max(axis=1), d[["o", "c"]].min(axis=1)
    d["h"] = np.minimum(d.h, top + cap)
    d["l"] = np.maximum(d.l, bot - cap)
    return d


_seed_cache: dict = {}


def seed_frames() -> dict:
    """4h / 1d candles from PAXG (Sep 2023 - Dec 2025, scripts/fetch_paxg.py) so daily and weekly structure start
    from real swings instead of a start-up guess on the XAUUSDT perp's first weeks. Empty if the file is missing."""
    if not SEED_FILE.exists():
        return {}
    key = SEED_FILE.stat().st_mtime
    if _seed_cache.get("key") != key:
        s1m = session.session_filter(paxg_clean(pd.read_parquet(SEED_FILE)))
        _seed_cache.update(key=key, tfs=session.build_all(s1m, SEED_TFS))
    return _seed_cache["tfs"]


def seeded(tfs: dict) -> dict:
    """Prepend the PAXG seed to 4h / 1d: PAXG for sessions before the first full XAUUSDT session, the perp after."""
    seed = seed_frames()
    if not seed or "1d" not in tfs or not len(tfs["1d"]):
        return tfs
    first = str(tfs["1d"]["sdate"].astype(str).iloc[1])          # the listing day itself is partial
    out = dict(tfs)
    for tf in SEED_TFS:
        a = seed[tf][seed[tf]["sdate"].astype(str) < first]
        b = tfs[tf][tfs[tf]["sdate"].astype(str) >= first]
        out[tf] = pd.concat([a, b])
    return out


def load_frames(con, now: pd.Timestamp | None = None) -> tuple[dict, pd.Timestamp]:
    """All candles from the XAUUSDT listing (a FIXED start, so structure never depends on how much history the
    caller happened to load), up to `now` for a replay, with 4h/1d/1w seeded from PAXG.
    Returns (frames, time the last closed 1m candle closed)."""
    end_ms = None if now is None else int(pd.Timestamp(now).timestamp() * 1000) - 59_999
    raw = store.load(con, start_ms=LISTING_MS, end_ms=end_ms)
    s1m = session.session_filter(raw)
    last = s1m.index[-1] + pd.Timedelta(minutes=1)
    return frames(seeded(session.build_all(s1m, ("5m", "15m", "1h", "4h", "1d")))), last


def closed_only(df: pd.DataFrame, tf: str, now: pd.Timestamp) -> pd.DataFrame:
    """Drop the candle still forming at `now` (the engine builds higher timeframes from whatever 1m exists)."""
    return df[known_at(df, tf) <= now]


def build(fr: dict, now: pd.Timestamp) -> dict:
    """Map every timeframe once, on candles closed by `now`. {tf: {df, bars, events, known}}"""
    maps = {}
    for tf in TF_ORDER:
        if tf not in fr:
            continue
        df = closed_only(fr[tf], tf, now)
        if len(df) < BOOT + 5:
            continue
        bars, E = map_structure(df)
        kn = known_at(df, tf)
        E = E.copy()
        E["tf"] = tf
        E["time"] = kn[E.i.to_numpy(int)] if len(E) else pd.DatetimeIndex([], tz="UTC")
        maps[tf] = {"df": df, "bars": bars, "events": E, "known": kn}
    return maps


def events_from(maps: dict, kinds=("CHOCH", "MSS")) -> pd.DataFrame:
    """Every event of the given kinds on every timeframe, indexed by the time it became known, oldest first."""
    rows = [m["events"][m["events"].kind.isin(kinds)].reset_index() for m in maps.values()]
    rows = [r for r in rows if len(r)]
    if not rows:
        return pd.DataFrame(columns=["time", "tf", "kind", "dir", "level", "invalid", "ext", "close", "open_time", "i"]
                            ).set_index("time")
    return pd.concat(rows).set_index("time").sort_index(kind="stable")


def trend_at(maps: dict, tf: str, t: pd.Timestamp, col: str = "trend") -> int:
    """Structure trend (or internal bias) of `tf` as known at time t: 0 if unknown."""
    m = maps.get(tf)
    if m is None:
        return 0
    k = int(np.searchsorted(m["known"].asi8, pd.Timestamp(t).as_unit(m["known"].unit).asm8.astype("int64"), side="right")) - 1
    if k < 0:
        return 0
    v = m["bars"][col].iloc[k]
    return int(v) if np.isfinite(v) else 0


def snapshot_from(maps: dict) -> dict:
    """Current structure per timeframe: trend, internal bias, the level that flips it, confirmed HH/LL, IDM."""
    snap = {}
    for tf, m in maps.items():
        bars, E, df, kn = m["bars"], m["events"], m["df"], m["known"]
        b = bars.iloc[-1]
        ch = E[E.kind == "CHOCH"]
        f = lambda v: float(v) if np.isfinite(v) else None  # noqa: E731
        snap[tf] = {
            "trend": int(b.trend) if np.isfinite(b.trend) else 0,
            "internal": int(b.internal) if np.isfinite(b.internal) else 0,
            "choch": f(b.choch), "ext": f(b.ext), "idm": f(b.idm), "run": f(b.run),
            "since": ch.time.iloc[-1].isoformat() if len(ch) else None,
            "close": float(df.c.iloc[-1]), "as_of": kn[-1].isoformat(),
        }
        if tf in ("4h", "1d", "1w"):
            cb = candle_bias(df).iloc[-1]
            snap[tf]["candle"] = {"bias": int(cb.bias), "target": f(cb.target), "why": cb.why}
    return snap


def aligned(snap: dict, tf: str) -> str | None:
    """WITH / AGAINST the next higher timeframe's structure trend (ch.14: neighbouring timeframes must agree)."""
    hi = HIGHER.get(tf)
    if not hi or hi not in snap or tf not in snap or not snap[hi]["trend"]:
        return None
    return "WITH" if snap[hi]["trend"] == snap[tf]["trend"] else "AGAINST"
