"""Backtest the Telegram alerts exactly as the bot would have sent them.

* Conditions alerts: the 15-minute score stream is fed through alerts.ConditionTracker.
  Each alert is judged on the next 4 hours (net R of 1:2 / 1:1 trend-following entries on
  1m+5m+15m with the 1h bias, and the 4h range), and so is the state it puts you in.
* Trend-shift alerts: every 1h/4h/1d market-structure flip, judged on 1m candles: does
  price reach +1R / +2R in the new direction before -1R (R = 1 ATR of that timeframe)?
  Baseline = entries at random times in a random direction.

Rules (the trend definition, thresholds, 2-check confirmation) were chosen on
5 Jan - 12 Apr 2026. The headline numbers are the last 6 months: 13 Apr - today.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from gold import alerts, store, trend  # noqa: E402
from gold.config import ET, IST, REPORTS_DIR  # noqa: E402
from gold.signal import Engine  # noqa: E402
from gold.util import md_table  # noqa: E402

START = pd.Timestamp("2026-01-05", tz="UTC")
CUT = pd.Timestamp("2026-04-13", tz="UTC")
SHIFT_HZ = {"1h": 720, "4h": 1440, "1d": 2760}   # in-session minutes: 12h / 1 day / 2 days


def periods(idx):
    return {"selection (5 Jan-12 Apr)": idx < CUT, "LAST 6 MONTHS (13 Apr-now)": idx >= CUT}


def run_conditions(S: pd.DataFrame):
    tr = alerts.ConditionTracker()
    out, states = [], []
    for t, row in S.iterrows():
        for a in tr.step(t, row):
            out.append(a)
        states.append(tr.state)
    return out, pd.Series(states, index=S.index)


def main():
    t0 = time.time()
    eng = Engine(store.load(store.connect()))
    S = eng.score(eng.slot_times(15))
    S = S[S.index >= START]
    fwd = eng.forward(S.index)
    S = S.join(fwd)
    print(f"15-min checks: {len(S)}  ({time.time() - t0:.0f}s)")

    # ---------------- conditions
    cond, state = run_conditions(S)
    S["state"] = state
    A = pd.DataFrame([{"time": a.time, "kind": a.kind, "score": a.score} for a in cond]).set_index("time")
    A = A.join(S[["y2", "y1", "fwd_range"]])
    md = ["# Telegram alert backtest", "",
          f"Generated {pd.Timestamp.now(tz=IST):%d %b %Y %H:%M} IST. Every 15-minute check and every 1h/4h/1d candle close since "
          f"5 Jan 2026 was replayed through the same alert code the bot runs (`gold/alerts.py`). "
          "Rules were picked on 5 Jan to 12 Apr. **The last 6 months (13 Apr to today) are the out-of-sample test.**", ""]
    res = {"generated": str(pd.Timestamp.now(tz=IST))}
    md += ["## 1. Conditions alerts (trade / selective / stop)", "",
           f"Thresholds: alert ON at score ≥{alerts.VIABLE_ON:.0f}, OFF below {alerts.VIABLE_OFF:.0f}, TRADE at ≥{alerts.GREEN_ON:.0f} "
           f"(drops back below {alerts.GREEN_OFF:.0f}). Each change must hold for {alerts.CONFIRM_SLOTS} consecutive 15-min checks.", ""]
    res["conditions"] = {}
    stats_cond = {}
    for pname, m in periods(S.index).items():
        Z = S[m]
        med = Z.y2.median()
        st = Z.groupby("state").agg(share=("y2", "size"), next4h_R_1to2=("y2", "mean"), next4h_R_1to1=("y1", "mean"),
                                    next4h_range=("fwd_range", "mean"),
                                    better_than_median=("y2", lambda s: (s > med).mean() * 100))
        st["share"] = st.share / st.share.sum() * 100
        st = st.reindex(["GREEN", "ON", "OFF"]).rename(index={"GREEN": "🟢 TRADE", "ON": "🟡 SELECTIVE", "OFF": "🔴 STOP"})
        Ap = A[(A.index >= Z.index.min()) & (A.index <= Z.index.max())]
        weeks = (Z.index.max() - Z.index.min()).days / 7
        ak = Ap.groupby("kind").agg(n=("score", "size"), next4h_R_1to2=("y2", "mean"), next4h_R_1to1=("y1", "mean"),
                                    next4h_range=("fwd_range", "mean"),
                                    better_than_median=("y2", lambda s: (s > med).mean() * 100))
        ak["per_week"] = ak.n / weeks
        # precision: ON/GREEN alerts followed by an above-median 4h; OFF alerts by a below-median 4h
        on = Ap[Ap.kind.isin(["CONDITIONS_ON", "CONDITIONS_GREEN"])]
        off = Ap[Ap.kind == "CONDITIONS_OFF"]
        prec_on = (on.y2 > med).mean() * 100
        prec_off = (off.y2 <= med).mean() * 100
        # how long ON windows last
        runs = (Z.state != Z.state.shift()).cumsum().rename("run")
        dur = pd.DataFrame({"st": Z.state, "t": Z.index, "run": runs.values}).groupby("run").agg(
            st=("st", "first"), start=("t", "first"), end=("t", "last"))
        dur["hours"] = (dur.end - dur.start).dt.total_seconds() / 3600 + 0.25
        dmed = dur.groupby("st").hours.median()
        print(f"\n== {pname}: state table\n{st.round(3).to_string()}\n-- alerts\n{ak.round(3).to_string()}")
        print(f"precision ON/GREEN -> above-median next 4h: {prec_on:.1f}%   OFF -> below-median: {prec_off:.1f}%  (coin flip = 50%)")
        md += [f"### {pname}", "", "**Time spent in each state, and what happened in the next 4 hours:**", "",
               md_table(st.round(3)), "", "**Each alert and the 4 hours after it:**", "", md_table(ak.round(3)), "",
               f"* Alerts per week (all condition types): **{len(Ap) / weeks:.1f}**",
               f"* **ON / TRADE alerts followed by a better-than-median 4h: {prec_on:.0f}%** (coin flip 50%)",
               f"* **STOP alerts followed by a worse-than-median 4h: {prec_off:.0f}%** (coin flip 50%)",
               f"* Median length of a window: TRADE {dmed.get('GREEN', np.nan):.1f}h · SELECTIVE {dmed.get('ON', np.nan):.1f}h · "
               f"STOP {dmed.get('OFF', np.nan):.1f}h", ""]
        if pname.startswith("LAST"):
            for kind, r in ak.iterrows():
                better = r.better_than_median if kind != "CONDITIONS_OFF" else 100 - r.better_than_median
                stats_cond[kind] = {"better": float(better), "n": int(r.n)}
        res["conditions"][pname] = {"states": json.loads(st.round(4).to_json(orient="index")),
                                    "alerts": json.loads(ak.round(4).to_json(orient="index")),
                                    "precision_on": prec_on, "precision_off": prec_off, "per_week": len(Ap) / weeks}

    # ---------------- trend shifts
    ev = alerts.shift_events(eng)
    ev = ev[ev.index >= START]
    rows = []
    for tf in alerts.SHIFT_TFS:
        e = ev[ev.tf == tf]
        if e.empty:
            continue
        ft = trend.follow_through(eng.s1m, e.index, e.dir, e.atr, SHIFT_HZ[tf])
        rows.append(e.join(ft))
    E = pd.concat(rows).sort_index()
    cs = pd.merge_asof(pd.DataFrame({"t": E.index}), S[["score", "tier", "state"]].reset_index().rename(columns={"time": "t"}),
                       on="t")
    E["cond"] = cs.state.values
    E["score"] = cs.score.values
    # whipsaw: state flips back within 6 / 3 / 2 candles
    whip_n = {"1h": 6, "4h": 3, "1d": 2}
    E["whip"] = np.nan
    for tf in alerts.SHIFT_TFS:
        df = eng.tfs[tf]
        stv = trend.state_structure(df).to_numpy()
        m = E.tf == tf
        pos = df.index.get_indexer(E.loc[m, "open_time"])
        E.loc[m, "whip"] = [float(np.nanmin(stv[p + 1:p + 1 + whip_n[tf]] * d) < 0) if p + 1 < len(stv) else np.nan
                            for p, d in zip(pos, E.loc[m, "dir"])]
    # random baseline per TF
    rng = np.random.default_rng(11)
    base = {}
    for tf in alerts.SHIFT_TFS:
        df = eng.tfs[tf]
        T = pd.DatetimeIndex(df.index + (pd.Timedelta(hours=23) if tf == "1d" else pd.Timedelta(minutes=trend.TF_MIN[tf])))
        a = trend.atr(df).to_numpy()
        keep = T >= START
        T, a = T[keep], a[keep]
        b = trend.follow_through(eng.s1m, T, rng.choice([-1, 1], len(T)), a, SHIFT_HZ[tf])
        for pname, m in periods(T).items():
            base[(tf, pname)] = (b[m].hit1.mean() * 100, b[m].hit2.mean() * 100, b[m].r2.mean())
    md += ["## 2. Trend-shift alerts (market structure, closed candles)", "",
           "A shift = a candle closes beyond the last confirmed swing high/low against the current trend (BOS/CHoCH). "
           "Judged on 1m candles: from the close of the shift candle, does price reach +1R / +2R in the new direction before −1R? "
           "(R = 1 ATR of that timeframe; horizon 12h for 1h, 1 day for 4h, 2 days for 1d; $0.40 cost included in R.)", ""]
    stats = dict(stats_cond)
    res["shifts"] = {}
    for pname, m in periods(E.index).items():
        Z = E[m]
        weeks = max(1.0, (S[periods(S.index)[pname]].index.max() - S[periods(S.index)[pname]].index.min()).days / 7)
        grp = []
        for (tf, tag), g in list(Z.groupby(["tf", Z.tag.fillna("ALL")])) + [((tf, "ALL"), Z[Z.tf == tf]) for tf in alerts.SHIFT_TFS]:
            if g.empty:
                continue
            b1, b2, br = base[(tf, pname)]
            grp.append({"tf": tf, "type": tag, "n": len(g), "per_week": len(g) / weeks,
                        "hit +1R first %": g.hit1.mean() * 100, "hit +2R first %": g.hit2.mean() * 100,
                        "random +1R %": b1, "random +2R %": b2, "avg R (1:2)": g.r2.mean(), "random R": br,
                        "median best move (R)": g.mfe.median(), "flip back fast %": g.whip.mean() * 100})
            if pname.startswith("LAST"):
                stats[f"{tf}|{tag}"] = {"hit1": g.hit1.mean() * 100, "hit2": g.hit2.mean() * 100, "n": len(g),
                                        "base_hit1": b1, "base_hit2": b2, "r2": g.r2.mean()}
        G = pd.DataFrame(grp).drop_duplicates(["tf", "type"]).set_index(["tf", "type"]).sort_index()
        # 1h shifts by conditions at the time
        h1 = Z[Z.tf == "1h"]
        byc = h1.groupby([h1.tag.fillna("?"), h1.cond.fillna("?")]).agg(n=("r2", "size"), hit1=("hit1", "mean"),
                                                                        hit2=("hit2", "mean"), avg_R=("r2", "mean"))
        byc[["hit1", "hit2"]] *= 100
        print(f"\n== shifts {pname}\n{G.round(2).to_string()}\n-- 1h by tag x conditions\n{byc.round(2).to_string()}")
        md += [f"### {pname}", "", md_table(G.round(2)), "", "1h shifts split by direction vs 4h and by conditions at the time:", "",
               md_table(byc.round(2)), ""]
        res["shifts"][pname] = json.loads(G.reset_index().round(4).to_json(orient="records"))

    # ---------------- volume + sample of what you'd have received last week
    last6 = (ev.index >= CUT)
    shifts6 = ev[last6]
    weeks6 = (S.index.max() - CUT).days / 7
    cond6 = [a for a in cond if a.time >= CUT]
    loud = sum(a.loud for a in cond6) + len(shifts6)
    md += ["## 3. How many messages", "",
           f"Last 6 months: {len(cond6) / weeks6:.1f} conditions alerts + {len(shifts6) / weeks6:.1f} trend-shift alerts per week "
           f"(1h {((shifts6.tf == '1h').sum()) / weeks6:.1f}, 4h {((shifts6.tf == '4h').sum()) / weeks6:.1f}, "
           f"1d {((shifts6.tf == '1d').sum()) / weeks6:.1f}). About **{loud / weeks6:.1f} loud notifications per week**. "
           f"'Selective ON' and downgrade messages arrive silently, because their moment wasn't better than a coin flip.", ""]
    sample_from = S.index.max() - pd.Timedelta(days=8)
    samp = [a for a in cond if a.time >= sample_from]
    for t, e in ev[ev.index >= sample_from].iterrows():
        row = S[S.index <= t].iloc[-1] if (S.index <= t).any() else None
        samp.append(alerts.shift_alert(t, e, row))
    samp.sort(key=lambda a: a.time)
    md += ["## 4. Exactly what the bot would have sent over the last 8 days", ""]
    for a in samp:
        bias = {tf: trend.state_at(eng.tfs[tf], tf, "structure", pd.DatetimeIndex([a.time]))[0] for tf in ("15m", "1h", "4h", "1d")}
        price = float(eng.s1m.c[eng.s1m.index < a.time].iloc[-1])
        msg = alerts.format_alert(a, {"price": price, "bias": {k: int(v) for k, v in bias.items() if np.isfinite(v)}}, stats)
        md += ["```", msg.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", ""), "```", ""]
    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "alerts_backtest.md").write_text("\n".join(md))
    (REPORTS_DIR / "alert_stats.json").write_text(json.dumps(stats, indent=1))
    (REPORTS_DIR / "alerts_backtest.json").write_text(json.dumps(res, indent=1, default=str))
    print(f"\nlast 6m: {len(cond6) / weeks6:.1f} condition + {len(shifts6) / weeks6:.1f} shift alerts/week, loud {loud / weeks6:.1f}/week")
    print(f"sample alerts last 8 days: {len(samp)}")
    print(f"wrote reports/alerts_backtest.md ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
