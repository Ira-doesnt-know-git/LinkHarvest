from __future__ import annotations

from typing import Iterable

import feedparser

from src.adapters.base import Adapter
from src.core import db as dbm
from src.core.models import Discovered


class RSSAdapter(Adapter):
    @staticmethod
    def parse_feed(content: str) -> Iterable[Discovered]:
        fp = feedparser.parse(content)
        for e in fp.entries:
            link = getattr(e, 'link', None) or getattr(e, 'id', None)
            lastmod = getattr(e, 'updated', None) or getattr(e, 'published', None)
            if link:
                yield Discovered(url=link, canonical=None, lastmod=lastmod, source='rss', meta={})

    def discover(self) -> Iterable[Discovered]:
        http = self.ctx['http']
        robots = self.ctx['robots']
        rl = self.ctx['ratelimiter']
        conn = self.ctx['db']
        counters = self.ctx['counters']

        feed_url = self.cfg['feed']
        rps = float(self.cfg.get('rate_limit_rps', 1.0))
        ua = self.cfg.get('user_agent')
        extra_headers = dict(self.cfg.get('headers') or {})
        if ua:
            extra_headers['User-Agent'] = ua

        if not robots.allowed(feed_url, user_agent=ua):
            counters['skipped_robots'] += 1
            return
        rl.await_slot(feed_url, rps)
        etag, lastmod = dbm.get_resource_etag_lastmod(conn, feed_url)
        try:
            resp = http.get(feed_url, etag=etag, last_modified=lastmod, extra_headers=extra_headers)
        except Exception:
            counters['errors'] += 1
            return
        counters['fetched'] += 1
        counters['status'][resp.status_code] = counters['status'].get(resp.status_code, 0) + 1
        if resp.status_code == 304:
            return
        if resp.status_code != 200:
            counters['errors'] += 1
            return
        dbm.set_resource_etag_lastmod(conn, feed_url, resp.headers.get('ETag'), resp.headers.get('Last-Modified'))
        for d in self.parse_feed(resp.text):
            counters['discovered'] += 1
            yield d
