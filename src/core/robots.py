from __future__ import annotations

import time
from urllib.parse import urlsplit
from urllib import robotparser
from typing import Dict

import httpx


class RobotsCache:
    def __init__(self, client: httpx.Client, user_agent: str = "LinkHarvest/1.0"):
        self._client = client
        self._ua = user_agent
        self._cache: Dict[str, robotparser.RobotFileParser] = {}
        self._fetched_at: Dict[str, float] = {}
        self._ttl = 60 * 60  # 1 hour

    def _robots_url(self, url: str) -> str:
        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}/robots.txt"

    def allowed(self, url: str) -> bool:
        rob_url = self._robots_url(url)
        now = time.time()
        if rob_url not in self._cache or (now - self._fetched_at.get(rob_url, 0)) > self._ttl:
            try:
                resp = self._client.get(rob_url, headers={"User-Agent": self._ua}, timeout=5.0)
                rp = robotparser.RobotFileParser()
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                else:
                    # Treat missing/forbidden robots as allowing by default per common practice
                    rp.parse(":\n".splitlines())
                self._cache[rob_url] = rp
                self._fetched_at[rob_url] = now
            except Exception:
                # On error, be conservative and allow to avoid blocking; adapters can still rate limit
                rp = robotparser.RobotFileParser()
                rp.parse(":\n".splitlines())
                self._cache[rob_url] = rp
                self._fetched_at[rob_url] = now
        rp = self._cache[rob_url]
        return rp.can_fetch(self._ua, url)
