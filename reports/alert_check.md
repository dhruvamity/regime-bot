# Alert check: live code vs backtest

Generated 14 Oct 2026 15:13 IST.

## 1. Trade-condition and trend-shift alerts

Replayed 2025 live steps (every 15-minute candle close) from 14 Sep 12:00 to 14 Oct 12:00 IST, each with only the candles a live server would have had. Restart from saved state at Tue 29 Sep 12:00 IST; offline Mon 05 Oct 14:30–17:30 IST.

* Should be sent: **66** · must be held back as stale during the outage: **3**
* Sent by the live code: **66** {'SHIFT': 28, 'CONDITIONS_OFF': 15, 'CONDITIONS_ON': 14, 'CONDITIONS_DOWN': 5, 'CONDITIONS_GREEN': 4}
* Missing **0** · extra **0** · duplicates **0** · more than 30 min late **0** · stale alerts leaked **0**
* **PASS**

## 2. Quiet-mode flips

Replayed 7871 steps over 120 days (16 Jun → 14 Oct).

* Expected flips **11** · sent **11** · missing **0** · extra **0** · duplicates **0** · not within 15 min of the session close **0**
* QUIET_ON after 2026-06-16 (+0 min), QUIET_OFF after 2026-06-17 (+0 min), QUIET_ON after 2026-07-20 (+0 min), QUIET_OFF after 2026-07-23 (+0 min), QUIET_ON after 2026-07-27 (+0 min), QUIET_OFF after 2026-07-29 (+0 min), QUIET_ON after 2026-10-01 (+0 min), QUIET_OFF after 2026-10-02 (+0 min), QUIET_ON after 2026-10-05 (+0 min), QUIET_OFF after 2026-10-06 (+0 min), QUIET_ON after 2026-10-12 (+0 min)
* **PASS**

**ALL CHECKS PASSED**

### Held back during the outage (correct)

* SHIFT 1h ▲ @ Mon 05 Oct 14:30 IST
* CONDITIONS_GREEN @ Mon 05 Oct 15:30 IST
* CONDITIONS_DOWN @ Mon 05 Oct 16:45 IST

### Every alert sent in the replay

* SHIFT 1h ▼ @ Mon 14 Sep 12:30 IST
* CONDITIONS_DOWN @ Tue 15 Sep 12:00 IST
* SHIFT 1h ▲ @ Wed 16 Sep 00:30 IST
* CONDITIONS_OFF @ Wed 16 Sep 03:45 IST
* CONDITIONS_ON @ Wed 16 Sep 08:30 IST
* SHIFT 1h ▼ @ Thu 17 Sep 00:30 IST
* CONDITIONS_GREEN @ Thu 17 Sep 01:00 IST
* SHIFT 1d ▼ @ Thu 17 Sep 02:30 IST
* SHIFT 1h ▲ @ Thu 17 Sep 13:30 IST
* CONDITIONS_DOWN @ Fri 18 Sep 04:30 IST
* SHIFT 4h ▲ @ Fri 18 Sep 23:30 IST
* CONDITIONS_GREEN @ Sat 19 Sep 02:15 IST
* CONDITIONS_DOWN @ Mon 21 Sep 06:30 IST
* SHIFT 1h ▼ @ Mon 21 Sep 13:30 IST
* CONDITIONS_OFF @ Tue 22 Sep 03:45 IST
* CONDITIONS_ON @ Tue 22 Sep 07:30 IST
* SHIFT 4h ▼ @ Tue 22 Sep 11:30 IST
* CONDITIONS_GREEN @ Tue 22 Sep 15:45 IST
* SHIFT 1h ▲ @ Tue 22 Sep 23:30 IST
* CONDITIONS_DOWN @ Tue 22 Sep 23:30 IST
* CONDITIONS_OFF @ Wed 23 Sep 13:30 IST
* CONDITIONS_ON @ Wed 23 Sep 17:15 IST
* SHIFT 1h ▼ @ Wed 23 Sep 19:30 IST
* CONDITIONS_OFF @ Thu 24 Sep 06:00 IST
* CONDITIONS_ON @ Thu 24 Sep 15:00 IST
* CONDITIONS_OFF @ Fri 25 Sep 08:15 IST
* CONDITIONS_ON @ Fri 25 Sep 12:45 IST
* SHIFT 1h ▲ @ Fri 25 Sep 16:30 IST
* CONDITIONS_OFF @ Fri 25 Sep 17:30 IST
* CONDITIONS_ON @ Fri 25 Sep 23:15 IST
* SHIFT 1h ▼ @ Mon 28 Sep 06:30 IST
* CONDITIONS_GREEN @ Mon 28 Sep 09:00 IST
* CONDITIONS_DOWN @ Tue 29 Sep 15:45 IST
* CONDITIONS_OFF @ Tue 29 Sep 20:15 IST
* CONDITIONS_ON @ Wed 30 Sep 01:00 IST
* SHIFT 1h ▲ @ Wed 30 Sep 01:30 IST
* CONDITIONS_OFF @ Wed 30 Sep 06:15 IST
* CONDITIONS_ON @ Wed 30 Sep 19:45 IST
* SHIFT 1h ▼ @ Wed 30 Sep 20:30 IST
* CONDITIONS_OFF @ Thu 01 Oct 00:45 IST
* SHIFT 1h ▲ @ Thu 01 Oct 09:30 IST
* CONDITIONS_ON @ Thu 01 Oct 17:30 IST
* CONDITIONS_OFF @ Thu 01 Oct 21:15 IST
* CONDITIONS_ON @ Thu 01 Oct 23:15 IST
* CONDITIONS_OFF @ Fri 02 Oct 05:30 IST
* CONDITIONS_ON @ Fri 02 Oct 17:45 IST
* SHIFT 1h ▼ @ Fri 02 Oct 20:30 IST
* SHIFT 1h ▲ @ Mon 05 Oct 06:30 IST
* SHIFT 1h ▼ @ Mon 05 Oct 10:30 IST
* CONDITIONS_OFF @ Tue 06 Oct 03:45 IST
* SHIFT 1h ▼ @ Tue 06 Oct 10:30 IST
* CONDITIONS_ON @ Tue 06 Oct 11:15 IST
* SHIFT 1h ▲ @ Tue 06 Oct 14:30 IST
* CONDITIONS_OFF @ Tue 06 Oct 16:45 IST
* SHIFT 1h ▼ @ Wed 07 Oct 08:30 IST
* SHIFT 1h ▲ @ Thu 08 Oct 07:30 IST
* CONDITIONS_ON @ Fri 09 Oct 01:15 IST
* CONDITIONS_OFF @ Fri 09 Oct 05:00 IST
* SHIFT 4h ▲ @ Fri 09 Oct 11:30 IST
* CONDITIONS_ON @ Fri 09 Oct 13:30 IST
* CONDITIONS_OFF @ Fri 09 Oct 17:00 IST
* SHIFT 1h ▼ @ Mon 12 Oct 13:30 IST
* SHIFT 1h ▲ @ Tue 13 Oct 08:30 IST
* SHIFT 1h ▼ @ Tue 13 Oct 23:30 IST
* SHIFT 4h ▼ @ Tue 13 Oct 23:30 IST
* SHIFT 1h ▲ @ Wed 14 Oct 08:30 IST

_Took 1572s._
