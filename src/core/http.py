from __future__ import annotations

import random
import time
from typing import Dict, Optional, Tuple

import httpx

RETRY_STATUS = {429, 500, 502, 503, 504}


class HttpClient:
    def __init__(self, user_agent: str = "LinkHarvest/1.0", connect_timeout: float = 5.0, read_timeout: float = 20.0):
        # httpx requires either a default timeout or all four parameters explicitly
        self.client = httpx.Client(
            timeout=httpx.Timeout(
                connect=connect_timeout,
                read=read_timeout,
                write=read_timeout,
                pool=connect_timeout,
            )
        )
        self.ua = user_agent

    def get(
        self,
        url: str,
        *,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        max_retries: int = 3,
        follow_redirects: bool = True,
    ) -> httpx.Response:
        headers = {"User-Agent": self.ua}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        if extra_headers:
            headers.update(extra_headers)

        delay = 0.5
        for attempt in range(1, max_retries + 1):
            try:
                resp = self.client.get(url, headers=headers, follow_redirects=follow_redirects)
            except Exception as e:
                if attempt == max_retries:
                    raise
                self._backoff_sleep(delay)
                delay = min(delay * 2, 8.0)
                continue

            if resp.status_code in RETRY_STATUS:
                if attempt == max_retries:
                    return resp
                self._backoff_sleep(delay)
                delay = min(delay * 2, 8.0)
                continue
            return resp
        return resp  # type: ignore

    @staticmethod
    def _backoff_sleep(base: float) -> None:
        jitter = base * random.uniform(0.8, 1.2)
        time.sleep(jitter)
