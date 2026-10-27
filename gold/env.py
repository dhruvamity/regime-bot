"""Settings from the project's .env file (or the real environment, which wins)."""
import os

from .config import ROOT


def load() -> dict:
    vals = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip('"').strip("'")
    for k in list(vals) + ["TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_CHATS", "QUIET_HOURS_IST", "BRIEF_TIME_IST",
                           "TELEGRAM_API_BASE", "GOLD_STATE_DIR", "BIAS_TREND_TFS", "BIAS_INTERNAL_TFS", "BIAS_SILENT_TFS"]:
        if os.environ.get(k):
            vals[k] = os.environ[k]
    return vals
