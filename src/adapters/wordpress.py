from __future__ import annotations

from typing import Dict, Iterable, List

from src.adapters.base import Adapter
from src.core import db as dbm
from src.core.models import Discovered


class WordPressAdapter(Adapter):
    @staticmethod
    def _endpoint(base: str, page: int) -> str:
        if base.endswith('/'):
            base = base[:-1]
        return f"{base}/wp-json/wp/v2/posts?per_page=100&_fields=link,modified&orderby=date&page={page}"

    @staticmethod
    def parse_posts(json_list: List[Dict]) -> Iterable[Discovered]:
        for item in json_list:
            link = item.get('link')
            modified = item.get('modified')
            if link:
                yield Discovered(url=link, canonical=None, lastmod=modified, source='api', meta={})

    def discover(self) -> Iterable[Discovered]:
        http = self.ctx['http']
        robots = self.ctx['robots']
        rl = self.ctx['ratelimiter']
        conn = self.ctx['db']
        counters = self.ctx['counters']

        base = self.cfg['base']
        max_pages = int(self.cfg.get('max_pages', 10))
        rps = float(self.cfg.get('rate_limit_rps', 1.0))
        ua = self.cfg.get('user_agent')
        extra_headers = dict(self.cfg.get('headers') or {})
        if ua:
            extra_headers['User-Agent'] = ua

        for page in range(1, max_pages + 1):
            url = self._endpoint(base, page)
            if not robots.allowed(url, user_agent=ua):
                counters['skipped_robots'] += 1
                break
            rl.await_slot(url, rps)
            etag, lastmod = dbm.get_resource_etag_lastmod(conn, url)
            try:
                resp = http.get(url, etag=etag, last_modified=lastmod, extra_headers=extra_headers)
            except Exception:
                counters['errors'] += 1
                break
            counters['fetched'] += 1
            counters['status'][resp.status_code] = counters['status'].get(resp.status_code, 0) + 1

            if resp.status_code == 304:
                # Not modified; nothing new on subsequent pages either
                break
            if resp.status_code == 400 or resp.status_code == 404:
                break
            if resp.status_code != 200:
                counters['errors'] += 1
                break

            dbm.set_resource_etag_lastmod(conn, url, resp.headers.get('ETag'), resp.headers.get('Last-Modified'))
            try:
                data = resp.json()
            except Exception:
                counters['errors'] += 1
                break

            items = list(self.parse_posts(data if isinstance(data, list) else []))
            counters['parsed'] += 1
            if not items:
                break
            for d in items:
                counters['discovered'] += 1
                yield d
