from __future__ import annotations

import time
from urllib.parse import urlsplit
from typing import Dict
import threading


class RateLimiter:
    def __init__(self):
        self._next_ok: Dict[str, float] = {}
        self._lock = threading.Lock()

    def await_slot(self, url: str, rps: float) -> None:
        host = urlsplit(url).netloc
        min_interval = 1.0 / max(rps, 0.01)
        while True:
            now = time.time()
            with self._lock:
                next_ok = self._next_ok.get(host, now)
                if next_ok <= now:
                    # claim the slot
                    self._next_ok[host] = now + min_interval
                    return
                wait = next_ok - now
            # Sleep outside the lock
            time.sleep(wait)
