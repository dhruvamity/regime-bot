"""The trade / don't-trade filter. One code path for the backtest and the live server.

What the research showed (10 months of XAUUSDT, hourly decision points, Jun-Oct held out):
  * Whether the NEXT hours trend or chop is not predictable from past candles (IC ~ 0).
  * How much gold WILL MOVE is predictable (volatility clusters), and net LTF results are
    clearly worse when movement is low relative to normal (stops + spread vs. small moves).
  * Recently resolved trade results carry a small amount of extra information.
So the score is built from movement (65%) and recent edge (35%). Live LTF chop/trend is
reported as context, not as a forecast.

All inputs are known at the decision time (closed candles only, trades counted only once
they have resolved), so nothing repaints.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from . import metrics, session
from .config import ET, IST

TF_MIN = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
BARS_4H = {"1m": 240, "5m": 48, "15m": 16}
BARS_24H = {"1m": 1380, "5m": 276, "15m": 92}
BASELINE_SAMPLES = 126 * 23          # ~6 months of hourly decision points
HOUR_LOOKBACK = 126                  # sessions used for same-hour baselines

TIER_GREEN = 55.0
TIER_RED = 35.0

STATE_TEXT = {
    "GREEN": ("TRADE", "Normal conditions. Your usual setups, 1:2+ targets are fine."),
    "AMBER": ("SELECTIVE", "Only A+ setups at half size. Take profit quickly, don't wait for extended targets."),
    "RED": ("NO TRADE / WAIT", "Gold isn't moving enough to pay for stops and spread. Sit out or wait for conditions to improve."),
}


def _asof(known: pd.Series, times: pd.DatetimeIndex) -> np.ndarray:
    known = known.dropna()
    left = pd.DataFrame({"t": times})
    right = pd.DataFrame({"t": known.index, "v": known.values})
    return pd.merge_asof(left, right, on="t").v.to_numpy()


def _known_at(df: pd.DataFrame, tf: str) -> pd.DatetimeIndex:
    """Time at which a candle is final. Daily candles are final at the 17:00 ET close."""
    if tf == "1d":
        return df.index + pd.Timedelta(hours=23)
    return df.index + pd.Timedelta(minutes=TF_MIN[tf])


def ema_dir(c: pd.Series) -> pd.Series:
    return np.sign(c.ewm(span=20, adjust=False).mean() - c.ewm(span=50, adjust=False).mean())


def pct_vs_trailing(base_t: np.ndarray, base_v: np.ndarray, eval_t: np.ndarray, eval_v: np.ndarray,
                    n: int = BASELINE_SAMPLES, min_periods: int = 300) -> np.ndarray:
    """Percentile (0-100) of each eval value among the last n-1 baseline values strictly before it."""
    from numpy.lib.stride_tricks import sliding_window_view
    m = n - 1
    base_v = np.asarray(base_v, float)
    eval_v = np.asarray(eval_v, float)
    padded = np.concatenate([np.full(m, np.nan), base_v])
    W = sliding_window_view(padded, m)            # W[i] = base_v[i-m : i]
    idx = np.searchsorted(base_t, eval_t, side="left")
    out = np.full(len(eval_v), np.nan)
    for s in range(0, len(eval_v), 2000):
        sl = slice(s, s + 2000)
        win = W[idx[sl]]
        valid = ~np.isnan(win)
        cnt = valid.sum(1)
        less = (win < eval_v[sl, None]).sum(1)
        with np.errstate(invalid="ignore", divide="ignore"):
            r = less / cnt * 100
        r[(cnt + 1 < min_periods) | np.isnan(eval_v[sl])] = np.nan
        out[sl] = r
    return out


def trail_pct(s: pd.Series, n: int = BASELINE_SAMPLES, min_periods: int = 300) -> pd.Series:
    """Percentile (0-100) of each value vs the preceding n samples. No look-ahead."""
    return s.rolling(n, min_periods=min_periods).apply(lambda w: (w[:-1] < w[-1]).mean() * 100, raw=True)


class Engine:
    """Builds every timeframe from 1m candles and evaluates the filter at arbitrary times."""

    def __init__(self, df1m: pd.DataFrame):
        self.s1m = session.session_filter(df1m)
        self.tfs = session.build_all(self.s1m)
        self.last_bar_close = self.s1m.index[-1] + pd.Timedelta(minutes=1)
        self._prepare()

    # ------------------------------------------------------------------ bar level
    def _prepare(self):
        tfs = self.tfs
        h1 = tfs["1h"]
        self.h1dir = pd.Series(ema_dir(h1.c).values, index=_known_at(h1, "1h"))
        self.bar = {}
        for tf in ("1m", "5m", "15m"):
            df = tfs[tf]
            f = metrics.bar_features(df)
            kt = _known_at(df, tf)
            hd = _asof(self.h1dir, kt)
            r = metrics.simulate(df, np.nan_to_num(hd), f.atr.to_numpy(), (2.0, 1.0), metrics.HORIZON[tf])
            f["y2"], f["y1"] = r[2.0], r[1.0]
            f["htf_dir"] = hd
            f.index = kt
            self.bar[tf] = f
        d1 = tfs["1d"].copy()
        d1["rng"] = d1.h - d1.l
        d1.index = _known_at(d1, "1d")
        self.d1 = d1

    # ------------------------------------------------------------------ features
    def features(self, T: pd.DatetimeIndex) -> pd.DataFrame:
        X = pd.DataFrame(index=T)
        for tf in ("1m", "5m", "15m"):
            f = self.bar[tf]
            rs = metrics.rolling_stats(f, BARS_4H[tf])
            for k in ("er", "chop", "wick", "vr", "atr"):
                X[f"{k}_{tf}_4h"] = _asof(rs[k], T)
            X[f"atr_{tf}_24h"] = _asof(f.atr.rolling(BARS_24H[tf], min_periods=BARS_24H[tf] // 3).mean(), T)
            hz = metrics.HORIZON[tf]
            # only trades that have already resolved (entered >= hz bars ago)
            X[f"past1_{tf}_24h"] = _asof(f.y1.shift(hz).rolling(BARS_24H[tf], min_periods=BARS_24H[tf] // 3).mean(), T)
            X[f"past2_{tf}_4h"] = _asof(f.y2.shift(hz).rolling(BARS_4H[tf], min_periods=BARS_4H[tf] // 3).mean(), T)
        d1 = self.d1
        X["rng5_rel"] = _asof(d1.rng.rolling(5).mean() / d1.rng.rolling(60, min_periods=20).median(), T)
        X["rng_prev"] = _asof(d1.rng, T)
        X["rng_med60"] = _asof(d1.rng.rolling(60, min_periods=20).median(), T)
        et = T.tz_convert(ET)
        X["hour_et"] = (et.hour + (et.minute >= 30).astype(int)) % 24
        return X

    def same_hour_baseline(self, X: pd.DataFrame, col: str, how: str = "median") -> pd.Series:
        """Trailing same-ET-hour statistic over previous sessions (excludes the current row)."""
        g = X[col].groupby(X.hour_et)
        roll = lambda s: getattr(s.rolling(HOUR_LOOKBACK, min_periods=20), how)().shift(1)
        return g.transform(roll)

    def baseline(self) -> pd.DataFrame:
        """Hourly decision points: the 6-month reference every score is ranked against."""
        if getattr(self, "_B", None) is None:
            B = self.features(self.decision_times(extra_now=False))
            B["volrel_5m"] = B.atr_5m_4h / self.same_hour_baseline(B, "atr_5m_4h")
            self._B = B
        return self._B

    @staticmethod
    def _same_hour_at(B: pd.DataFrame, E: pd.DataFrame, col: str) -> np.ndarray:
        """For each eval time: median of the last HOUR_LOOKBACK same-hour baseline values strictly before it."""
        out = np.full(len(E), np.nan)
        for h, Bh in B.groupby("hour_et"):
            med = Bh[col].rolling(HOUR_LOOKBACK, min_periods=20).median().dropna()
            m = (E.hour_et == h).to_numpy()
            if not m.any() or med.empty:
                continue
            left = pd.DataFrame({"t": E.index[m]})
            right = pd.DataFrame({"t": med.index, "v": med.to_numpy()})
            out[m] = pd.merge_asof(left, right, on="t", allow_exact_matches=False).v.to_numpy()
        return out

    # ------------------------------------------------------------------ scores
    def score(self, T: pd.DatetimeIndex | None = None, fwd: pd.DataFrame | None = None) -> pd.DataFrame:
        """Evaluate the filter at any times T (default: the hourly grid).

        Each value is ranked against the hourly baseline samples strictly before it, so a
        15-minute or 1-minute evaluation means exactly the same thing as an hourly one.
        """
        B = self.baseline()
        if T is None:
            X = B.copy()
        else:
            X = self.features(pd.DatetimeIndex(T))
            X["volrel_5m"] = X.atr_5m_4h / self._same_hour_at(B, X, "atr_5m_4h")
        bt = B.index.asi8
        et = X.index.asi8
        for c in ("volrel_5m", "atr_5m_24h", "rng5_rel", "past1_1m_24h", "past2_5m_4h"):
            X["p_" + c] = pct_vs_trailing(bt, B[c].to_numpy(), et, X[c].to_numpy())
        X["move"] = X[["p_volrel_5m", "p_atr_5m_24h", "p_rng5_rel"]].mean(axis=1)
        X["edge"] = X[["p_past1_1m_24h", "p_past2_5m_4h"]].mean(axis=1)
        X["score"] = 0.65 * X.move + 0.35 * X.edge
        # descriptive live structure (trend quality right now vs 6 months)
        parts = []
        for tf in ("1m", "5m", "15m"):
            for k, inv in (("er", False), ("vr", False), ("chop", True), ("wick", True)):
                col = f"{k}_{tf}_4h"
                p = pct_vs_trailing(bt, B[col].to_numpy(), et, X[col].to_numpy())
                parts.append(100 - p if inv else p)
        with warnings.catch_warnings():  # warm-up rows where every part is NaN
            warnings.simplefilter("ignore", RuntimeWarning)
            X["trend_q"] = np.nanmean(np.vstack(parts), axis=0)
        # hour quality: trailing same-hour mean of resolved forward results
        if fwd is not None:
            X["hour_q"] = self.same_hour_baseline(X.join(fwd[["y2"]]), "y2", "mean")
        X["tier"] = np.select([X.score >= TIER_GREEN, X.score >= TIER_RED], ["GREEN", "AMBER"], "RED")
        X.loc[X.score.isna(), "tier"] = None
        return X

    def slot_times(self, minutes: int = 15) -> pd.DatetimeIndex:
        """In-session candle closes on a fixed grid (the cadence alerts are evaluated on)."""
        tf = {5: "5m", 15: "15m", 60: "1h"}[minutes]
        T = pd.DatetimeIndex(_known_at(self.tfs[tf], tf))
        return T[T <= self.last_bar_close]

    # ------------------------------------------------------------------ forward truth (backtest only)
    def forward(self, T: pd.DatetimeIndex, hours: int = 4) -> pd.DataFrame:
        """What actually happened after each decision time, within the same session."""
        def fwd_roll(s: pd.Series, sd: pd.Series, nb: int, fn: str) -> pd.Series:
            return s.groupby(sd.values).transform(
                lambda x: getattr(x[::-1].rolling(nb, min_periods=max(2, nb // 4)), fn)()[::-1].shift(-1))
        Y = pd.DataFrame(index=T)
        for tf in ("1m", "5m", "15m"):
            f = self.bar[tf]
            nb = BARS_4H[tf] * hours // 4
            for k in ("y2", "y1"):
                Y[f"{k}_{tf}"] = _asof(fwd_roll(f[k], f.sdate, nb, "mean"), T)
        Y["y2"] = Y[["y2_1m", "y2_5m", "y2_15m"]].mean(axis=1)
        Y["y1"] = Y[["y1_1m", "y1_5m", "y1_15m"]].mean(axis=1)
        f5 = self.bar["5m"]
        nb = BARS_4H["5m"] * hours // 4
        hi = pd.Series(self.tfs["5m"].h.to_numpy(), index=f5.index)
        lo = pd.Series(self.tfs["5m"].l.to_numpy(), index=f5.index)
        Y["fwd_range"] = _asof(fwd_roll(hi, f5.sdate, nb, "max") - fwd_roll(lo, f5.sdate, nb, "min"), T)
        return Y

    # ------------------------------------------------------------------ HTF bias
    def htf_bias(self) -> dict:
        out = {}
        for tf in ("1h", "4h", "1d"):
            d = self.tfs[tf]
            kt = _known_at(d, tf)
            closed = d[kt <= self.last_bar_close]
            if len(closed) < 60:
                continue
            e20 = closed.c.ewm(span=20, adjust=False).mean()
            e50 = closed.c.ewm(span=50, adjust=False).mean()
            a = metrics.adx(closed).iloc[-1]
            dirn = int(np.sign(e20.iloc[-1] - e50.iloc[-1]))
            above = closed.c.iloc[-1] > e20.iloc[-1]
            if dirn > 0 and above:
                label = "Bullish"
            elif dirn < 0 and not above:
                label = "Bearish"
            else:
                label = "Mixed"
            out[tf] = {"dir": dirn, "label": label, "adx": round(float(a), 1),
                       "strength": "strong" if a >= 25 else ("weak" if a < 18 else "moderate"),
                       "close": float(closed.c.iloc[-1]), "ema20": float(e20.iloc[-1]), "ema50": float(e50.iloc[-1])}
        dirs = [v["dir"] for v in out.values()]
        out["aligned"] = len(set(dirs)) == 1 and len(dirs) == 3
        return out

    # ------------------------------------------------------------------ hourly decision grid
    def decision_times(self, extra_now: bool = True) -> pd.DatetimeIndex:
        h1 = self.tfs["1h"]
        T = pd.DatetimeIndex(_known_at(h1, "1h"))
        T = T[T <= self.last_bar_close]
        if extra_now and (len(T) == 0 or T[-1] < self.last_bar_close):
            T = T.append(pd.DatetimeIndex([self.last_bar_close]))
        return T
