from __future__ import annotations

from typing import Optional

import requests

from config import settings


class TelegramAlerts:
    def __init__(self) -> None:
        token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
        chat = (settings.TELEGRAM_CHAT_ID or "").strip()
        self.bot_token = token
        self.chat_id = chat
        # Only send when both are non-empty; otherwise no network calls and no errors.
        self.enabled = bool(token and chat)

    def send(self, message: str) -> bool:
        if not self.enabled:
            return False
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": message}
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code >= 400:
                print(f"[telegram] send failed status={resp.status_code} body={resp.text}")
                return False
            return True
        except Exception as e:
            print(f"[telegram] send error: {type(e).__name__}: {e}")
            return False

