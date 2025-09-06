from __future__ import annotations

import re
from collections import deque
from typing import Iterable, Set
from urllib.parse import urljoin, urlsplit

from lxml import html

from src.adapters.base import Adapter
from src.core.models import Discovered


class CrawlerAdapter(Adapter):
    @staticmethod
    def extract_links(base_url: str, content: str) -> Iterable[str]:
        try:
            doc = html.fromstring(content)
        except Exception:
            return []
        for a in doc.xpath('//a[@href]'):
            href = a.get('href')
            if not href:
                continue
            yield urljoin(base_url, href)

    def _in_scope(self, url: str) -> bool:
        scope_host = self.cfg.get('scope_host')
        parts = urlsplit(url)
        if scope_host and parts.netloc != scope_host:
            return False
        inc = self.cfg.get('include_paths') or []
        if inc and not any(parts.path.startswith(p) for p in inc):
            return False
        exc = self.cfg.get('exclude_patterns') or []
        for pat in exc:
            if re.search(pat, parts.path):
                return False
        return True

    def discover(self) -> Iterable[Discovered]:
        http = self.ctx['http']
        robots = self.ctx['robots']
        rl = self.ctx['ratelimiter']
        counters = self.ctx['counters']

        base = self.cfg['base']
        rps = float(self.cfg.get('rate_limit_rps', 0.5))
        max_depth = int(self.cfg.get('max_depth', 2))

        visited: Set[str] = set()
        q = deque([(base, 0)])

        while q:
            url, depth = q.popleft()
            if url in visited:
                continue
            visited.add(url)
            if not robots.allowed(url):
                counters['skipped_robots'] += 1
                continue
            if not self._in_scope(url):
                continue
            rl.await_slot(url, rps)
            resp = http.get(url)
            counters['fetched'] += 1
            counters['status'][resp.status_code] = counters['status'].get(resp.status_code, 0) + 1
            if resp.status_code != 200:
                counters['errors'] += 1
                continue
            counters['parsed'] += 1
            for link in self.extract_links(url, resp.text):
                if not self._in_scope(link):
                    continue
                yield Discovered(url=link, canonical=None, lastmod=None, source='crawl', meta={})
                counters['discovered'] += 1
                if depth + 1 <= max_depth:
                    q.append((link, depth + 1))

