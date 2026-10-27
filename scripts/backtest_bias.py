"""Backtest of the SMC bias finder (gold/bias.py) against simpler trend reads, on every candle available.

Data
  development  PAXGUSDT spot (gold-backed token), Sep 2023 - 10 Dec 2025 (python scripts/fetch_paxg.py).
               PAXG has thin-book spikes, so wicks longer than 15x the rolling median 1m range are trimmed.
  test         XAUUSDT perp (the bot's own feed, data/candles.db), 11 Dec 2025 - now.
  Both filtered to forex.com hours and built into 5m/15m/1h/4h/1d exactly as the live bot does.

Signals (all known at the candle close, nothing repaints)
  smc_trend     external structure: flips on a CHoCH (body close beyond the CHoCH point)
  smc_internal  internal bias: flips on an MSS (IDM taken + body close through it + displacement), back on BOS/CHoCH
  fractal       the bot's current 1h/4h/1d shift alert (gold/trend.py state_structure, 3-bar fractals)
  ema20_50      EMA20 vs EMA50

Tests
  A  state edge     at every candle close: the next 1 / 4 / 12 candles' move in ATR units, long-state minus
                    short-state, with a 95% interval from a block bootstrap over weeks
  B  flips          each flip judged on 1m candles: +1R before -1R, +2R before -1R and a 1:2 trade (R = 1 ATR of
                    that timeframe, $0.40 cost), against the SAME moments traded the other way; flips per week;
                    share reversed within 3 candles
  C  alignment      smc_trend flips WITH vs AGAINST the next higher timeframe's smc_trend (ch.14)
  D  candle rules   ch.12 next-candle bias on 1h/4h/1d: does candle C reach the target before B's opposite extreme?

Writes reports/bias_backtest.md / .json and reports/bias_stats.json (quoted by the bot in alerts).
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from gold import bias, session, store, trend  # noqa: E402
from gold.config import LISTING_MS, REPORTS_DIR  # noqa: E402
from gold.util import md_table  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TFS = ("5m", "15m", "1h", "4h", "1d")
HZ_MIN = {"5m": 60, "15m": 180, "1h": 720, "4h": 2880, "1d": 5 * 1380}     # 12 candles (1d: 5 sessions)
SIGNALS = ("smc_trend", "smc_internal", "fractal", "ema20_50")
RNG = np.random.default_rng(11)


def load_paxg():
    return bias.paxg_clean(pd.read_parquet(ROOT / "data/paxg_1m.parquet"))


XAU_CUT = pd.Timestamp("2026-06-01", tz="UTC")


def datasets():
    """(raw 1m, timeframes it is valid for, [(period label, start, end)]).

    PAXG's thin book makes its 1m-15m returns mean-revert (lag-1 autocorrelation -0.16 at 1m, -0.10 at 5m vs
    about 0 on XAUUSDT), so PAXG is only used for 1h and up. 5m/15m are judged on XAUUSDT alone, in two halves."""
    far, near = pd.Timestamp("2000-01-01", tz="UTC"), pd.Timestamp("2100-01-01", tz="UTC")
    out = []
    if (ROOT / "data/paxg_1m.parquet").exists():
        out.append((load_paxg(), ("1h", "4h", "1d"), [("PAXG Sep 2023-Dec 2025", far, near)]))
    else:
        print("data/paxg_1m.parquet missing (python scripts/fetch_paxg.py): XAUUSDT only")
    con = store.connect()
    listing = pd.Timestamp(LISTING_MS, unit="ms", tz="UTC")
    out.append((store.load(con, start_ms=LISTING_MS), TFS,
                [("XAU Dec 2025-May 2026", listing, XAU_CUT), ("XAU Jun-Oct 2026", XAU_CUT, near)]))
    return out


def states(df):
    bars, E = bias.map_structure(df)
    return {
        "smc_trend": bars.trend.replace(0, np.nan),
        "smc_internal": bars.internal.replace(0, np.nan),
        "fractal": trend.state_structure(df),
        "ema20_50": trend.state_ema(df),
    }, bars, E


def week_boot(vals, weeks, n=1000):
    """95% interval of a mean by resampling whole weeks."""
    df = pd.DataFrame({"v": vals, "w": weeks}).dropna()
    if df.w.nunique() < 8:
        return np.nan, np.nan
    g = df.groupby("w").v.agg(["sum", "count"])
    s, c = g["sum"].to_numpy(), g["count"].to_numpy()
    idx = RNG.integers(0, len(g), (n, len(g)))
    m = s[idx].sum(1) / c[idx].sum(1)
    return np.percentile(m, 2.5), np.percentile(m, 97.5)


def test_state(df, st, tf, a_, b_):
    """Test A: long-state minus short-state forward move, in ATR units."""
    a = trend.atr(df)
    wk = df.index.tz_localize(None).to_period("W").astype(str)
    rows = []
    for N in (1, 4, 12):
        fwd = (df.c.shift(-N) - df.c) / a
        for name, s in st.items():
            x = pd.DataFrame({"s": s, "f": fwd, "w": wk}).iloc[60:].dropna()          # 60-candle warm-up
            x = x[(x.index >= a_) & (x.index < b_)]
            if len(x) < 50 or x.s.nunique() < 2:
                continue
            # signed move: +1 state earns fwd, -1 earns -fwd; minus the unconditional drift on each side
            drift = x.f.mean()
            v = x.s * (x.f - drift)
            lo, hi = week_boot(v.to_numpy(), x.w.to_numpy())
            rows.append(dict(tf=tf, N=N, signal=name, edge=v.mean(), lo=lo, hi=hi,
                             agree=float((np.sign(x.f) == x.s).mean()), n=len(x)))
    return rows


def flip_events(df, s, tf):
    s = s.dropna()
    prev = s.shift()
    f = s[(s != prev) & prev.notna()]
    f = f[f.index >= df.index[60]]
    kn = bias.known_at(df.loc[f.index], tf)
    return pd.DataFrame({"dir": f.to_numpy().astype(int), "known": kn}, index=f.index)


def test_flips(s1m, df, st, tf, a_, b_):
    """Test B: what happened after each flip, both ways."""
    a = trend.atr(df)
    out, raw = [], {}
    for name, s in st.items():
        ev = flip_events(df, s, tf)
        ev = ev[(ev.index >= a_) & (ev.index < b_)]
        if len(ev) < 3:
            continue
        atrs = a.loc[ev.index].to_numpy()
        H = HZ_MIN[tf]
        fw = trend.follow_through(s1m, pd.DatetimeIndex(ev.known), ev.dir.to_numpy(), atrs, H)
        bw = trend.follow_through(s1m, pd.DatetimeIndex(ev.known), -ev.dir.to_numpy(), atrs, H)
        # reversed within 3 candles of the same signal
        pos = {t: k for k, t in enumerate(s.index)}
        sv = s.to_numpy()
        rev = [np.nanmax(np.abs(np.diff(sv[pos[t]:pos[t] + 4]))) > 0 if pos[t] + 4 <= len(sv) else np.nan for t in ev.index]
        span = df.index[(df.index >= max(a_, df.index[60])) & (df.index < b_)]
        weeks = max(1e-9, (span[-1] - span[0]).days / 7)
        out.append(dict(tf=tf, signal=name, n=len(ev), per_week=len(ev) / weeks,
                        hit1=fw.hit1.mean() * 100, hit1_other=bw.hit1.mean() * 100,
                        hit2=fw.hit2.mean() * 100, hit2_other=bw.hit2.mean() * 100,
                        r2=fw.r2.mean(), r2_other=bw.r2.mean(), whipsaw=np.nanmean(rev) * 100))
        raw[name] = ev.join(fw.set_index(ev.index))
    return out, raw


def test_candles(s1m, df, tf, a_, b_):
    """Test D: ch.12 next-candle bias. Within candle C, is the target hit before B's opposite extreme?"""
    cb = bias.candle_bias(df)
    t1 = s1m.index
    rows = []
    idx = df.index
    for k in range(1, len(df) - 1):
        b = cb.iloc[k]
        if b.bias == 0 or not np.isfinite(b.target) or not (a_ <= idx[k] < b_):
            continue
        stop = df.l.iloc[k] if b.bias > 0 else df.h.iloc[k]
        cl = df.c.iloc[k]
        dt, ds = abs(b.target - cl), abs(cl - stop)
        exp = ds / (dt + ds) if dt + ds > 0 else np.nan     # driftless random walk from B's close
        a, z = idx[k + 1], (idx[k + 2] if k + 2 < len(idx) else idx[k + 1] + pd.Timedelta(days=1))
        p = s1m.iloc[t1.searchsorted(a):t1.searchsorted(z)]
        if p.empty:
            continue
        hit_t = (p.h >= b.target) if b.bias > 0 else (p.l <= b.target)
        hit_s = (p.l <= stop) if b.bias > 0 else (p.h >= stop)
        ft = hit_t.to_numpy().argmax() if hit_t.any() else 10**9
        fs = hit_s.to_numpy().argmax() if hit_s.any() else 10**9
        rows.append(dict(tf=tf, why=b.why, bias=int(b.bias), target_first=ft < fs, stop_first=fs < ft,
                         target_any=bool(hit_t.any()), expected=exp, resolved=min(ft, fs) < 10**9))
    return pd.DataFrame(rows)


def main():
    t0 = time.time()
    A, B, C, D, rawall = [], [], [], [], {}
    for raw, valid, periods in datasets():
        s1m = session.session_filter(raw)
        tfs = session.build_all(s1m, ("1m", "5m", "15m", "1h", "4h", "1d"))
        if "5m" in valid:            # XAUUSDT: exactly the live bot's frames (4h / 1d seeded from PAXG)
            tfs = bias.seeded(tfs)
        cache = {tf: states(tfs[tf]) for tf in TFS if tf in valid}
        for dname, a_, b_ in periods:
            smc = {}
            for tf in TFS:
                if tf not in valid:
                    continue
                df = tfs[tf]
                st, bars, E = cache[tf]
                smc[tf] = st["smc_trend"]
                A += [{"data": dname, **r} for r in test_state(df, st, tf, a_, b_)]
                fl, rw = test_flips(s1m, df, st, tf, a_, b_)
                B += [{"data": dname, **r} for r in fl]
                rawall[(dname, tf)] = rw
                if tf in ("1h", "4h", "1d"):
                    d = test_candles(s1m, df, tf, a_, b_)
                    if len(d):
                        d["data"] = dname
                        D.append(d)
                print(f"{dname} {tf:4s} done ({time.time() - t0:.0f}s)", flush=True)
            # Test C: smc_trend flips with / against the next higher timeframe
            for tf in ("5m", "15m", "1h", "4h"):
                hi = bias.HIGHER[tf]
                rw = rawall.get((dname, tf), {}).get("smc_trend")
                if rw is None or not len(rw) or hi not in smc:
                    continue
                hk = pd.Series(smc[hi].to_numpy(), index=bias.known_at(tfs[hi], hi)).dropna()
                h_at = pd.merge_asof(pd.DataFrame({"t": pd.DatetimeIndex(rw.known)}),
                                     pd.DataFrame({"t": hk.index, "v": hk.values}), on="t").v.to_numpy()
                tag = np.where(h_at == rw.dir.to_numpy(), "WITH", np.where(np.isnan(h_at), "n/a", "AGAINST"))
                for g in ("WITH", "AGAINST"):
                    x = rw[tag == g]
                    if len(x):
                        C.append(dict(data=dname, tf=tf, tag=g, n=len(x), hit1=x.hit1.mean() * 100,
                                      hit2=x.hit2.mean() * 100, r2=x.r2.mean()))
    A, B, C = pd.DataFrame(A), pd.DataFrame(B), pd.DataFrame(C)
    D = pd.concat(D) if D else pd.DataFrame()
    write(A, B, C, D, rawall)
    print(f"done in {time.time() - t0:.0f}s")


def write(A, B, C, D, rawall):
    REPORTS_DIR.mkdir(exist_ok=True)
    L = ["# SMC bias finder: backtest", "",
         f"Generated {pd.Timestamp.now(tz='UTC'):%Y-%m-%d %H:%M} UTC by `scripts/backtest_bias.py`. "
         "Three periods: PAXG Sep 2023-Dec 2025 (1h and up only), XAUUSDT perp Dec 2025-May 2026 and Jun-Oct 2026. "
         "All reads use closed candles only.", ""]
    L += ["## A. Does the state point the right way?", "",
          "Next N candles' move in ATR units when the state is long, minus when it is short (drift removed). "
          "Positive = the state points the right way. 95% interval from resampling whole weeks.", ""]
    for d in A.data.unique():
        x = A[(A.data == d) & (A.N == 4)]
        L += [f"**{d}**, N = 4 candles", ""]
        cols_ = [tf for tf in TFS if tf in set(x.tf)]
        t = x.pivot_table(index="signal", columns="tf", values="edge").reindex(SIGNALS)[cols_]
        lo = x.pivot_table(index="signal", columns="tf", values="lo").reindex(SIGNALS)[cols_]
        hi = x.pivot_table(index="signal", columns="tf", values="hi").reindex(SIGNALS)[cols_]
        cells = t.round(3).astype(str) + " [" + lo.round(3).astype(str) + ", " + hi.round(3).astype(str) + "]"
        L += [md_table(cells.reset_index()), ""]
    L += ["Full table (N = 1, 4, 12): `reports/bias_backtest.json`.", ""]
    L += ["## B. After each flip", "",
          "Entry at the flip candle's close, R = 1 ATR of that timeframe, judged on 1m candles over the next 12 "
          "candles (1d: 5 sessions). 'other way' = the same moments traded in the opposite direction.", ""]
    cols = ["signal", "tf", "n", "per_week", "whipsaw", "hit1", "hit1_other", "hit2", "hit2_other", "r2", "r2_other"]
    for d in B.data.unique():
        x = B[B.data == d][cols].round(2)
        L += [f"**{d}**", "", md_table(x), ""]
    L += ["## C. smc_trend flips with vs against the next higher timeframe", "", md_table(C.round(2)), ""]
    if len(D):
        R = D[D.resolved]
        g = R.groupby(["data", "tf", "why"]).agg(n=("bias", "size"), target_first=("target_first", "mean"),
                                                 random_walk=("expected", "mean")).reset_index()
        g["edge_pts"] = (g.target_first - g.random_walk) * 100
        for k in ("target_first", "random_walk"):
            g[k] = (g[k] * 100).round(1)
        g["edge_pts"] = g.edge_pts.round(1)
        L += ["## D. Candle-to-candle rules (ch.12)", "",
              "Next candle C, candles where C reached the target or B's opposite extreme: share that reached the target "
              "first, against a driftless random walk from B's close (distance to stop / total distance). "
              "edge_pts > 0 = the rule beats chance.", "", md_table(g), ""]
    (REPORTS_DIR / "bias_backtest.md").write_text("\n".join(L))
    (REPORTS_DIR / "bias_backtest.json").write_text(json.dumps(
        {"state": A.to_dict("records"), "flips": B.to_dict("records"), "align": C.to_dict("records")}, default=float, indent=1))
    # what the bot quotes: each XAUUSDT half separately (pooling would hide halves that disagree)
    stats = {}
    for _, r in B[B.data.str.startswith("XAU")].iterrows():
        k = f"{r.signal}|{r.tf}"
        stats.setdefault(k, {"n": 0, "periods": []})
        stats[k]["n"] += int(r.n)
        stats[k]["periods"].append({"label": r.data.replace("XAU ", ""), **{x: round(float(r[x]), 2) for x in
                                    ("n", "per_week", "hit1", "hit1_other", "hit2", "hit2_other", "r2", "r2_other", "whipsaw")}})
    (REPORTS_DIR / "bias_stats.json").write_text(json.dumps(stats, indent=1))
    # every flip, for inspection
    rows = []
    for (d, tf), rw in rawall.items():
        for name, ev in rw.items():
            e = ev.reset_index().rename(columns={"index": "open_time", "time": "open_time"})
            e["data"], e["tf"], e["signal"] = d, tf, name
            rows.append(e)
    pd.concat(rows).to_csv(REPORTS_DIR / "bias_flips.csv", index=False)


if __name__ == "__main__":
    main()
