"""Stateful live wrapper around gold.alerts, persisted so restarts never re-send or spam.

Each call to process(engine) looks only at 15-minute checks and shift candles that are new
since the last call, runs them through exactly the same code as scripts/backtest_alerts.py,
and returns the alerts to send.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import alerts, regime, trend
from .config import DATA_DIR, REPORTS_DIR

STALE_MIN = 30          # never send an alert about something older than this (e.g. after downtime)
WARMUP_SLOTS = 400      # ~4 sessions of 15-min checks replayed silently on first start


class AlertRunner:
    def __init__(self, path: Path = DATA_DIR / "alert_state.json"):
        self.path = path
        st = json.loads(path.read_text()) if path.exists() else {}
        self.cond = alerts.ConditionTracker(**st.get("cond", {}))
        self.last_slot = pd.Timestamp(st["last_slot"]) if st.get("last_slot") else None
        self.last_shift = pd.Timestamp(st["last_shift"]) if st.get("last_shift") else None
        self.history: list[dict] = st.get("history", [])
        self.regime: dict | None = st.get("regime")   # {"mode", "session"} last seen quiet-mode reading
        self.stats = self.load_stats()

    @staticmethod
    def load_stats() -> dict:
        try:
            return json.loads((REPORTS_DIR / "alert_stats.json").read_text())
        except Exception:
            return {}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "cond": self.cond.to_dict(),
            "last_slot": self.last_slot.isoformat() if self.last_slot is not None else None,
            "last_shift": self.last_shift.isoformat() if self.last_shift is not None else None,
            "history": self.history[-200:],
            "regime": self.regime,
        }, indent=1, default=str))

    def context(self, eng, state: dict | None) -> dict:
        t = pd.DatetimeIndex([eng.last_bar_close])
        bias = {}
        for tf in ("15m", "1h", "4h", "1d"):
            v = trend.state_at(eng.tfs[tf], tf, alerts.SHIFT_DEF, t)[0]
            if np.isfinite(v):
                bias[tf] = int(v)
        ctx = {"price": float(eng.s1m.c.iloc[-1]), "bias": bias}
        if state:
            c = state.get("components", {})
            if c.get("atr_5m_4h") and c.get("normal_atr_5m_4h_this_hour"):
                ctx["move_line"] = (f"5m ATR (last 4h) ${c['atr_5m_4h']:.2f} vs ${c['normal_atr_5m_4h_this_hour']:.2f} "
                                    f"normal for this hour")
        return ctx

    def regime_change(self, r: dict | None, now: pd.Timestamp | None = None) -> str | None:
        """Text of a QUIET MODE ON/OFF alert when the mode flipped since the last reading, else None.
        The first reading is adopted silently, like the condition alerts."""
        if not r:
            return None
        prev = self.regime
        self.regime = {"mode": r["mode"], "session": r["as_of_session"]}
        if prev is None or prev.get("mode") == r["mode"]:
            if prev != self.regime:
                self.save()
            return None
        now = now or pd.Timestamp.now(tz="UTC")
        self.history.append({"time": now.isoformat(), "kind": "QUIET_" + ("ON" if r["mode"] == "QUIET" else "OFF"),
                             "tf": None, "dir": None, "score": None, "tag": None, "loud": True, "sent_at": time.time()})
        self.save()
        return regime.alert_text(r)

    def process(self, eng, now: pd.Timestamp | None = None) -> list[alerts.Alert]:
        now = now or pd.Timestamp.now(tz="UTC")
        slots = eng.slot_times(15)
        out: list[alerts.Alert] = []
        if self.last_slot is None:  # first run: rebuild state silently from recent history
            warm = slots[-WARMUP_SLOTS:]
            S = eng.score(warm)
            for t, row in S.iterrows():
                self.cond.step(t, row)
            self.last_slot = slots[-1] if len(slots) else None
            self.last_shift = eng.last_bar_close
            self.save()
            return []
        new = slots[slots > self.last_slot]
        S = None
        if len(new):
            S = eng.score(new)
            for t, row in S.iterrows():
                out += self.cond.step(t, row)
            self.last_slot = new[-1]
        ev = alerts.shift_events(eng, since=self.last_shift)
        if len(ev):
            for t, e in ev.iterrows():
                cond_row = eng.score(pd.DatetimeIndex([t])).iloc[-1]
                out.append(alerts.shift_alert(t, e, cond_row))
            self.last_shift = ev.index.max()
        fresh = [a for a in out if a.time >= now - pd.Timedelta(minutes=STALE_MIN)]
        for a in fresh:
            self.history.append({"time": a.time.isoformat(), "kind": a.kind, "tf": a.tf, "dir": a.direction,
                                 "score": a.score, "tag": a.tag, "loud": a.loud, "sent_at": time.time()})
        self.save()
        return fresh
