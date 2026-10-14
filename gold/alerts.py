"""Alert rules: one implementation for the Telegram bot and the backtest.

Two families:
  1. Conditions  - the trade/no-trade score, checked every 15 minutes on closed candles,
                   with a hysteresis band so it doesn't flip-flop around a threshold.
  2. Trend shift - market-structure (BOS/CHoCH) flips on closed 1h / 4h / 1d candles,
                   tagged WITH or AGAINST the next-higher timeframe's trend.

Loud vs silent comes from the backtest (scripts/backtest_alerts.py): TRADE-ON and STOP
alerts beat a coin flip in both periods; "selective ON" did not, so it arrives silently.
"""
from __future__ import annotations

import html
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from . import trend
from .config import ET, IST

# conditions (score 0-100; tiers are RED <35, AMBER 35-55, GREEN >=55)
VIABLE_ON, VIABLE_OFF = 38.0, 32.0
GREEN_ON, GREEN_OFF = 58.0, 52.0
CONFIRM_SLOTS = 2            # consecutive 15-min checks beyond a threshold before alerting
SHIFT_TFS = ("1h", "4h", "1d")
SHIFT_DEF = "structure"
HIGHER = {"1h": "4h", "4h": "1d", "1d": None}


@dataclass
class Alert:
    time: pd.Timestamp
    kind: str                 # CONDITIONS_ON | CONDITIONS_GREEN | CONDITIONS_DOWN | CONDITIONS_OFF | SHIFT
    tf: str | None = None
    direction: int | None = None
    score: float | None = None
    prev_score: float | None = None
    tier: str | None = None
    price: float | None = None
    tag: str | None = None    # WITH / AGAINST higher-TF trend
    data: dict = field(default_factory=dict)
    loud: bool = True         # False -> sent as a silent Telegram notification

    def key(self) -> str:
        return f"{self.kind}|{self.tf}|{self.time.isoformat()}"


class ConditionTracker:
    """OFF -> ON (selective) -> GREEN, with hysteresis + confirmation."""

    def __init__(self, state: str | None = None, pending: str | None = None, pending_n: int = 0,
                 last_score: float | None = None):
        self.state = state
        self.pending = pending
        self.pending_n = pending_n
        self.last_score = last_score

    def to_dict(self):
        return {"state": self.state, "pending": self.pending, "pending_n": self.pending_n, "last_score": self.last_score}

    def _target(self, s: float) -> str:
        """Where the score points, given the current state (hysteresis)."""
        st = self.state
        if st == "GREEN":
            return "OFF" if s < VIABLE_OFF else ("ON" if s < GREEN_OFF else "GREEN")
        if st == "ON":
            return "OFF" if s < VIABLE_OFF else ("GREEN" if s >= GREEN_ON else "ON")
        return "GREEN" if s >= GREEN_ON else ("ON" if s >= VIABLE_ON else "OFF")

    def step(self, t: pd.Timestamp, row: pd.Series) -> list[Alert]:
        s = row.get("score")
        if s is None or not np.isfinite(s):
            return []
        prev_score = self.last_score
        self.last_score = float(s)
        if self.state is None:  # first observation: adopt silently
            self.state = "GREEN" if s >= GREEN_ON else ("ON" if s >= VIABLE_ON else "OFF")
            return []
        tgt = self._target(s)
        if tgt == self.state:
            self.pending, self.pending_n = None, 0
            return []
        if tgt != self.pending:
            self.pending, self.pending_n = tgt, 0
        self.pending_n += 1
        if self.pending_n < CONFIRM_SLOTS:
            return []
        old, self.state = self.state, tgt
        self.pending, self.pending_n = None, 0
        kind = {"OFF": "CONDITIONS_OFF", "ON": "CONDITIONS_ON" if old == "OFF" else "CONDITIONS_DOWN",
                "GREEN": "CONDITIONS_GREEN"}[tgt]
        return [Alert(time=t, kind=kind, score=float(s), prev_score=prev_score, tier=row.get("tier"),
                      data={"from": old, "to": tgt}, loud=kind in ("CONDITIONS_GREEN", "CONDITIONS_OFF"))]


def shift_events(eng, since: pd.Timestamp | None = None) -> pd.DataFrame:
    """All structure shifts on 1h/4h/1d known by the engine's last candle, tagged vs the higher TF."""
    rows = []
    for tf in SHIFT_TFS:
        df = eng.tfs[tf]
        if len(df) < 30:
            continue
        ev = trend.shifts(df, tf, SHIFT_DEF)
        ev = ev[ev.index <= eng.last_bar_close]
        if since is not None:
            ev = ev[ev.index > since]
        if ev.empty:
            continue
        hi = HIGHER[tf]
        if hi:
            hs = trend.state_at(eng.tfs[hi], hi, SHIFT_DEF, ev.index)
            ev["tag"] = np.where(hs == ev.dir, "WITH", np.where(np.isnan(hs), None, "AGAINST"))
        else:
            ev["tag"] = None
        ev["tf"] = tf
        rows.append(ev)
    if not rows:
        return pd.DataFrame(columns=["dir", "price", "atr", "broke", "invalid", "tf", "tag"])
    return pd.concat(rows).sort_index()


def shift_alert(t, ev: pd.Series, cond_row: pd.Series | None) -> Alert:
    return Alert(time=t, kind="SHIFT", tf=ev.tf, direction=int(ev.dir), price=float(ev.price), tag=ev.tag,
                 score=float(cond_row.score) if cond_row is not None and np.isfinite(cond_row.score) else None,
                 tier=cond_row.tier if cond_row is not None else None,
                 data={"broke": float(ev.broke) if np.isfinite(ev.broke) else None,
                       "invalid": float(ev.invalid) if np.isfinite(ev.invalid) else None,
                       "atr": float(ev.atr)},
                 loud=True)


# ------------------------------------------------------------------ message formatting (Telegram HTML)
TIER_LINE = {"GREEN": "🟢 TRADE", "AMBER": "🟡 SELECTIVE", "RED": "🔴 NO TRADE"}


def _when(t: pd.Timestamp) -> str:
    return f"{t.tz_convert(IST):%a %d %b %H:%M} IST · {t.tz_convert(ET):%H:%M} ET"


def _bias_line(bias: dict | None) -> str:
    if not bias:
        return ""
    arrows = {1: "▲", -1: "▼"}
    parts = [f"{tf} {arrows.get(bias[tf], '•')}" for tf in ("15m", "1h", "4h", "1d") if tf in bias]
    return "Structure trend: " + " · ".join(parts)


def format_alert(a: Alert, ctx: dict | None = None, stats: dict | None = None) -> str:
    """ctx: optional live context {price, bias:{tf:dir}, move_line}. stats: backtested hit rates."""
    ctx = ctx or {}
    e = lambda x: html.escape(str(x), quote=False)
    price = a.price or ctx.get("price")
    lines = []
    if a.kind == "CONDITIONS_GREEN":
        lines += ["🟢🟢 <b>GOLD: TRADE CONDITIONS ON</b>", "<b>Movement is back. Normal setups, 1:2+ targets OK.</b>"]
    elif a.kind == "CONDITIONS_ON":
        lines += ["🟡 <b>GOLD: TRADABLE (SELECTIVE)</b>", "<b>Conditions improved. A+ setups only, half size.</b>"]
    elif a.kind == "CONDITIONS_DOWN":
        lines += ["🟡 <b>GOLD: DOWNGRADED TO SELECTIVE</b>", "Movement fading. Tighten up, take profits quicker."]
    elif a.kind == "CONDITIONS_OFF":
        lines += ["🔴 <b>GOLD: STOP TRADING (NO-TRADE CONDITIONS)</b>",
                  "<b>Gold isn't moving enough to pay for stops and spread. Step away.</b>"]
    elif a.kind == "SHIFT":
        word = "BULLISH ▲" if a.direction > 0 else "BEARISH ▼"
        head = "TREND SHIFT" if a.tf == "1h" else "BIAS CHANGE"
        lines.append(f"🔄 <b>{a.tf.upper()} {head} → {word}</b>")
        hi = HIGHER.get(a.tf)
        if hi and a.tag == "WITH":
            lines.append(f"<b>With the {hi} trend</b> ({hi} is also {'bullish' if a.direction > 0 else 'bearish'}).")
        elif hi and a.tag == "AGAINST":
            lines.append(f"<b>Against the {hi} trend</b>: counter-trend, so the {hi} hasn't confirmed it.")
        if a.tf != "1h":
            lines.append("<i>Higher-timeframe bias info, not an entry signal.</i>")
        d = a.data
        lvl = []
        if d.get("broke") is not None:
            lvl.append(f"closed {'above swing high' if a.direction > 0 else 'below swing low'} {d['broke']:.2f}")
        if d.get("invalid") is not None:
            lvl.append(f"invalid on a close {'below' if a.direction > 0 else 'above'} {d['invalid']:.2f}")
        if lvl:
            lines.append(" · ".join(lvl))
        if d.get("atr"):
            lines.append(f"{a.tf} ATR ${d['atr']:.2f}")
        if stats:
            st = next((x for x in (stats.get(f"{a.tf}|{a.tag}"), stats.get(f"{a.tf}|ALL"))
                       if x and x.get("n", 0) >= 15), None)  # too few events -> no numbers at all
            if st:
                lines.append(f"<i>Backtest (6m): +1R before −1R {st['hit1']:.0f}% · +2R before −1R {st['hit2']:.0f}% "
                             f"(random ≈ {st['base_hit1']:.0f}% / {st['base_hit2']:.0f}%) · n={st['n']}</i>")
    if a.kind.startswith("CONDITIONS") and a.score is not None:
        names = {"OFF": "NO TRADE", "ON": "SELECTIVE", "GREEN": "TRADE"}
        chg = f" · {names.get(a.data.get('from'), '?')} → {names.get(a.data.get('to'), '?')}" if a.data.get("from") else ""
        lines.append(f"Score <b>{a.score:.0f}</b>/100{chg}")
        if stats and stats.get(a.kind):
            st = stats[a.kind]
            word = "worse" if a.kind == "CONDITIONS_OFF" else "better"
            lines.append(f"<i>Backtest (6m): the next 4h was {word} than median {st['better']:.0f}% of the time "
                         f"(coin flip 50%), n={st['n']}</i>")
        if ctx.get("move_line"):
            lines.append(e(ctx["move_line"]))
    if a.kind == "SHIFT" and a.tier:
        lines.append(f"Conditions now: {TIER_LINE.get(a.tier, a.tier)} (score {a.score:.0f})" if a.score is not None else "")
    bl = _bias_line(ctx.get("bias"))
    if bl:
        lines.append(bl)
    if price:
        lines.append(f"Price {price:.2f}")
    lines.append(f"⏱ {_when(a.time)}")
    return "\n".join(x for x in lines if x)


def to_jsonable(a: Alert) -> dict:
    d = asdict(a)
    d["time"] = a.time.isoformat()
    return d
