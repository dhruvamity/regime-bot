"""SMC bias alerts: a Telegram message whenever a closed candle switches the structure on any timeframe.

Two kinds (gold/bias.py has the rules):
  SMC_TREND     the trend flipped (CHoCH: body close beyond the CHoCH point). Loud, except on BIAS_SILENT_TFS.
  SMC_INTERNAL  the internal bias moved (MSS against the trend, or back with it on the next BOS). Silent.

Which timeframes alert is set in .env (defaults below). One code path for the live bot and
scripts/verify_bias.py, which replays it candle by candle against the full-history events.

What the backtest says (reports/bias_backtest.md): these are bias INFORMATION, not entry signals. Only the 15m
trend flip did better than the same moments traded the other way in both XAUUSDT halves, and on 51 flips that is
not proven. Each message quotes its timeframe's own numbers once there are at least 15 flips behind them.
"""
from __future__ import annotations

import html
import json

import numpy as np
import pandas as pd

from . import bias, env
from .config import ET, IST, REPORTS_DIR

DEFAULTS = {"BIAS_TREND_TFS": "5m,15m,1h,4h,1d,1w", "BIAS_INTERNAL_TFS": "1h,4h,1d,1w", "BIAS_SILENT_TFS": "5m"}
ARROW = {1: "▲", -1: "▼", 0: "•"}
WORD = {1: "BULLISH", -1: "BEARISH"}
MIN_N = 15


def settings(cfg: dict | None = None) -> dict:
    cfg = env.load() if cfg is None else cfg
    return {k: {x.strip() for x in (cfg.get(k) or v).split(",") if x.strip()} for k, v in DEFAULTS.items()}


def load_stats() -> dict:
    try:
        return json.loads((REPORTS_DIR / "bias_stats.json").read_text())
    except Exception:
        return {}


def alerts_between(maps: dict, since: pd.Timestamp, until: pd.Timestamp, cfg: dict) -> list:
    """Alerts for every event known in (since, until], filtered by the timeframe settings."""
    from .alerts import Alert
    ev = bias.events_from(maps, ("CHOCH", "MSS"))
    ev = ev[(ev.index > since) & (ev.index <= until)]
    out = []
    for t, e in ev.iterrows():
        kind = "SMC_TREND" if e.kind == "CHOCH" else "SMC_INTERNAL"
        if e.tf not in cfg["BIAS_TREND_TFS" if kind == "SMC_TREND" else "BIAS_INTERNAL_TFS"]:
            continue
        hi = bias.HIGHER.get(e.tf)
        hs = bias.trend_at(maps, hi, t) if hi else 0
        tr = bias.trend_at(maps, e.tf, t)
        out.append(Alert(time=t, kind=kind, tf=e.tf, direction=int(e.dir), price=float(e.close),
                         tag=None if not hs else ("WITH" if hs == int(e.dir) else "AGAINST"),
                         data={"level": float(e.level), "invalid": float(e.invalid),
                               "ext": None if not np.isfinite(e.ext) else float(e.ext), "trend": tr,
                               "map": {tf: bias.trend_at(maps, tf, t) for tf in maps}},
                         loud=kind == "SMC_TREND" and e.tf not in cfg["BIAS_SILENT_TFS"]))
    return out


def merge(alerts: list) -> list:
    """One message per candle close: switches of the same kind and direction at the same moment are combined
    under the highest timeframe, with the others listed in data["also"]. Loud if any part is loud."""
    groups: dict = {}
    for a in alerts:
        groups.setdefault((a.time, a.kind, a.direction), []).append(a)
    out = []
    for g in groups.values():
        g = sorted(g, key=lambda a: bias.TF_ORDER.index(a.tf))
        top = g[-1]
        top.data["also"] = [a.tf for a in g[:-1]]
        top.loud = any(a.loud for a in g)
        out.append(top)
    return sorted(out, key=lambda a: a.time)


def _when(t: pd.Timestamp) -> str:
    return f"{t.tz_convert(IST):%a %d %b %H:%M} IST · {t.tz_convert(ET):%H:%M} ET"


def format_alert(a, stats: dict | None = None) -> str:
    d, tf, up = a.data, a.tf, a.direction > 0
    hi = bias.HIGHER.get(tf)
    L = []
    tfs = " + ".join(x.upper() for x in [*d.get("also", []), tf])
    if a.kind == "SMC_TREND":
        L.append(f"🧭 <b>{tfs} TREND → {WORD[a.direction]} {ARROW[a.direction]}</b>  (CHoCH)")
        L.append(f"{tf} closed {'above' if up else 'below'} its CHoCH point {d['level']:.2f}. "
                 f"Flips back on a close {'below' if up else 'above'} {d['invalid']:.2f}.")
    else:
        with_trend = a.direction == d.get("trend")
        if with_trend:
            L.append(f"↪️ <b>{tfs} internal back with the trend {ARROW[a.direction]}</b>  (BOS)")
            L.append(f"Closed {'above' if up else 'below'} {d['level']:.2f}. The {tf} trend is "
                     f"{WORD[a.direction].lower()}; it flips on a close {'below' if up else 'above'} {d['invalid']:.2f}.")
        else:
            L.append(f"↪️ <b>{tfs} INTERNAL SHIFT → {WORD[a.direction]} {ARROW[a.direction]}</b>  (MSS)")
            line = (f"Took the inducement at {d['level']:.2f} with a body close and displacement. The {tf} trend is "
                    f"still {WORD[-a.direction].lower()}: back in line on a close {'below' if up else 'above'} "
                    f"{d['invalid']:.2f}")
            if d.get("ext") is not None:
                line += f", trend flips on a close {'above' if up else 'below'} {d['ext']:.2f}"
            L.append(line + ".")
    if hi and a.tag == "WITH":
        L.append(f"<b>With the {hi}</b> ({hi} is also {WORD[a.direction].lower()}).")
    elif hi and a.tag == "AGAINST":
        L.append(f"<b>Against the {hi}</b> ({hi} is {WORD[-a.direction].lower()}): counter-trend on the bigger picture.")
    mp = d.get("map") or {}
    if mp:
        L.append("Map: " + " · ".join(f"{k} {ARROW.get(v, '•')}" for k, v in mp.items()))
    L.append("<i>Bias information, not an entry signal.</i>")
    st = (stats or {}).get(f"{'smc_trend' if a.kind == 'SMC_TREND' else 'smc_internal'}|{tf}")
    if st and st.get("n", 0) >= MIN_N:
        parts = [f"{p['label']}: {p['hit1']:.0f}% vs {p['hit1_other']:.0f}% ({p['n']:.0f})" for p in st["periods"]]
        L.append(f"<i>Backtest, +1R before −1R this way vs the other way: {' · '.join(parts)}</i>")
    L.append(f"Price {a.price:.2f}")
    L.append(f"⏱ {_when(a.time)}")
    return "\n".join(x for x in L if x)


def map_text(snap: dict) -> str:
    """The /smc reply: structure on every timeframe, closed candles only."""
    if not snap:
        return "Still loading."
    e = lambda x: html.escape(str(x), quote=False)  # noqa: E731
    L = ["<b>SMC structure (closed candles)</b>", ""]
    for tf in reversed(bias.TF_ORDER):
        s = snap.get(tf)
        if not s:
            continue
        t, it = s["trend"], s["internal"]
        if not t:
            continue
        flip = s["choch"]
        dist = f" ({flip - s['close']:+.1f})" if flip is not None else ""
        line = f"<b>{tf}</b> {ARROW[t]} {WORD[t].lower()}"
        if it and it != t:
            line += f" · internal {ARROW[it]} (MSS)"
        line += f" · flips on a close {'below' if t > 0 else 'above'} {flip:.2f}{dist}" if flip is not None else ""
        if s.get("ext") is not None:
            line += f" · confirmed {'HH' if t > 0 else 'LL'} {s['ext']:.2f}"
        elif s.get("idm") is not None:
            line += f" · IDM {s['idm']:.2f}"
        L.append(line)
    pairs = [("1w", "1d"), ("1d", "4h"), ("4h", "1h")]
    agree = [f"{a}+{b} {WORD[snap[a]['trend']].lower()}" for a, b in pairs
             if a in snap and b in snap and snap[a]["trend"] and snap[a]["trend"] == snap[b]["trend"]]
    L += ["", "Neighbours agreeing (ch.14): " + (", ".join(agree) if agree else "none")]
    cl = [f"{tf}: {e(s['candle']['why'])} → {WORD[s['candle']['bias']].lower()}, "
          f"target {s['candle']['target']:.2f}" for tf, s in snap.items()
          if s.get("candle") and s["candle"]["bias"] and s["candle"]["target"] is not None]
    if cl:
        L += ["", "<b>Last closed candle (ch.12)</b>"] + cl
        L.append("<i>Backtest: the sweep-and-close-back rules did not beat chance; use them only with a POI.</i>")
    any_s = next(iter(snap.values()))
    L += ["", f"Price {any_s['close']:.2f}"]
    return "\n".join(L)
