"""Minimal Telegram Bot API client: retrying sender + long-poll command reader.

Only chats that are allowed (TELEGRAM_ALLOWED_CHATS, or the first chat to /start when
that is empty) can subscribe. Subscribers and the update offset live in data/telegram.json.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

import aiohttp

log = logging.getLogger("gold.telegram")


class Telegram:
    def __init__(self, token: str, state_path: Path, allowed: str = "", base: str = "https://api.telegram.org"):
        self.api = f"{base.rstrip('/')}/bot{token}"
        self.path = state_path
        self.allowed = {int(x) for x in allowed.replace(" ", "").split(",") if x.strip().lstrip("-").isdigit()}
        st = json.loads(state_path.read_text()) if state_path.exists() else {}
        self.chats: list[int] = st.get("chats", [])
        self.owner: int | None = st.get("owner")
        self.offset: int = st.get("offset", 0)
        self.queue: asyncio.Queue = asyncio.Queue()
        self.session: aiohttp.ClientSession | None = None
        self.me: dict | None = None
        self.status = "starting"
        self.last_error: str | None = None

    # ------------------------------------------------------------------ persistence
    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"chats": self.chats, "owner": self.owner, "offset": self.offset}, indent=1))

    def is_allowed(self, chat_id: int) -> bool:
        if self.allowed:
            return chat_id in self.allowed
        return self.owner is None or chat_id == self.owner

    def subscribe(self, chat_id: int) -> bool:
        if not self.is_allowed(chat_id):
            return False
        if not self.allowed and self.owner is None:
            self.owner = chat_id
        if chat_id not in self.chats:
            self.chats.append(chat_id)
        self._save()
        return True

    def unsubscribe(self, chat_id: int):
        if chat_id in self.chats:
            self.chats.remove(chat_id)
            self._save()

    # ------------------------------------------------------------------ http
    async def _call(self, method: str, http_timeout: float = 30, **params):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        async with self.session.post(f"{self.api}/{method}", json=params,
                                     timeout=aiohttp.ClientTimeout(total=http_timeout)) as r:
            data = await r.json(content_type=None)
            if not data.get("ok"):
                err = RuntimeError(f"{method}: {data.get('description')}")
                err.retry_after = (data.get("parameters") or {}).get("retry_after")
                err.code = data.get("error_code")
                raise err
            return data["result"]

    async def check(self) -> bool:
        try:
            self.me = await self._call("getMe", http_timeout=15)
            self.status = f"connected as @{self.me.get('username')}"
            return True
        except Exception as e:
            self.status = f"error: {e}"
            self.last_error = str(e)
            return False

    # ------------------------------------------------------------------ sending
    def enqueue(self, text: str, silent: bool = False, chat_id: int | None = None):
        self.queue.put_nowait({"text": text, "silent": silent, "chat_id": chat_id, "t": time.time()})

    async def sender_loop(self):
        while True:
            msg = await self.queue.get()
            targets = [msg["chat_id"]] if msg["chat_id"] else list(self.chats)
            for chat in targets:
                for attempt in range(8):
                    try:
                        await self._call("sendMessage", chat_id=chat, text=msg["text"], parse_mode="HTML",
                                         disable_web_page_preview=True, disable_notification=msg["silent"])
                        break
                    except Exception as e:
                        code = getattr(e, "code", None)
                        if code in (400, 403):  # bad markup or the user blocked the bot: don't retry forever
                            log.warning("telegram send to %s failed permanently: %s", chat, e)
                            if code == 403:
                                self.unsubscribe(chat)
                            break
                        wait = getattr(e, "retry_after", None) or min(60, 2 ** attempt)
                        self.last_error = str(e)
                        log.warning("telegram send failed (%s), retry in %ss", e, wait)
                        await asyncio.sleep(wait)
            await asyncio.sleep(0.05)

    # ------------------------------------------------------------------ commands
    async def poll_loop(self, handler):
        """handler(chat_id, command, args) -> awaitable reply text (or None)."""
        backoff = 1
        while True:
            try:
                updates = await self._call("getUpdates", http_timeout=65, offset=self.offset, timeout=50,
                                           allowed_updates=["message"])
                backoff = 1
                for u in updates:
                    self.offset = u["update_id"] + 1
                    m = u.get("message") or {}
                    text = (m.get("text") or "").strip()
                    chat = (m.get("chat") or {}).get("id")
                    if not chat or not text.startswith("/"):
                        continue
                    cmd, *args = text.split()
                    cmd = cmd.split("@")[0].lower()
                    try:
                        reply = await handler(chat, cmd, args)
                    except Exception as e:  # never let a command kill the loop
                        log.exception("command %s failed", cmd)
                        reply = f"Sorry, that failed: {e}"
                    if reply:
                        self.enqueue(reply, chat_id=chat)
                if updates:
                    self._save()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.last_error = str(e)
                log.warning("telegram poll error: %s (retry %ss)", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(60, backoff * 2)
