from __future__ import annotations

import re
import time
from collections import deque
from typing import Iterable, Set
from urllib.parse import urljoin, urlsplit

from lxml import html

from src.adapters.base import Adapter
from src.core import db as dbm
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
        conn = self.ctx['db']
        counters = self.ctx['counters']

        base = self.cfg['base']
        rps = float(self.cfg.get('rate_limit_rps', 0.5))
        max_depth = int(self.cfg.get('max_depth', 2))
        recrawl_ttl = int(self.cfg.get('recrawl_ttl_seconds', 0))  # optional, 0 disables

        visited: Set[str] = set()
        ua = self.cfg.get('user_agent')
        base_headers = dict(self.cfg.get('headers') or {})
        if ua:
            base_headers['User-Agent'] = ua
        q = deque([(base, 0)])

        while q:
            url, depth = q.popleft()
            if url in visited:
                continue
            visited.add(url)
            if not robots.allowed(url, user_agent=ua):
                counters['skipped_robots'] += 1
                continue
            if not self._in_scope(url):
                continue
            # Optional TTL-based skip
            if recrawl_ttl > 0:
                last_seen = dbm.get_last_seen(conn, url)
                if last_seen is not None and (time.time() - last_seen) < recrawl_ttl:
                    continue
            rl.await_slot(url, rps)
            etag, lastmod = dbm.get_resource_etag_lastmod(conn, url)
            try:
                resp = http.get(url, etag=etag, last_modified=lastmod, extra_headers=base_headers)
            except Exception:
                counters['errors'] += 1
                continue
            counters['fetched'] += 1
            counters['status'][resp.status_code] = counters['status'].get(resp.status_code, 0) + 1
            if resp.status_code == 304:
                # Unchanged; skip parsing and do not enqueue children
                continue
            if resp.status_code != 200:
                counters['errors'] += 1
                continue
            dbm.set_resource_etag_lastmod(conn, url, resp.headers.get('ETag'), resp.headers.get('Last-Modified'))
            counters['parsed'] += 1
            for link in self.extract_links(url, resp.text):
                if not self._in_scope(link):
                    continue
                yield Discovered(url=link, canonical=None, lastmod=None, source='crawl', meta={})
                counters['discovered'] += 1
                if depth + 1 <= max_depth:
                    q.append((link, depth + 1))
