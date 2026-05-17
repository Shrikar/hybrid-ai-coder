from __future__ import annotations

from typing import Any, Optional

import httpx


class WebhookDispatcher:
    def __init__(self, url: Optional[str] = None):
        self.url = url

    def emit(self, payload: dict[str, Any]) -> None:
        if not self.url:
            return
        try:
            httpx.post(self.url, json=payload, timeout=3.0)
        except Exception:
            # Best-effort only for local app mode.
            return
