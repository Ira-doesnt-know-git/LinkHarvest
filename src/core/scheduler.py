from __future__ import annotations

import time
from urllib.parse import urlsplit
from typing import Dict


class RateLimiter:
    def __init__(self):
        self._next_ok: Dict[str, float] = {}

    def await_slot(self, url: str, rps: float) -> None:
        host = urlsplit(url).netloc
        min_interval = 1.0 / max(rps, 0.01)
        now = time.time()
        next_ok = self._next_ok.get(host, now)
        if next_ok > now:
            time.sleep(next_ok - now)
        self._next_ok[host] = time.time() + min_interval

