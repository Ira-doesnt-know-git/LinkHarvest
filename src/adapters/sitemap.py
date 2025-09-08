from __future__ import annotations

from typing import Iterable

from lxml import etree

from src.adapters.base import Adapter
from src.core import db as dbm
from src.core.models import Discovered


class SitemapAdapter(Adapter):
    @staticmethod
    def _iter_sitemap_xml(content: str) -> Iterable[Discovered]:
        ns = {
            'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'
        }
        root = etree.fromstring(content.encode('utf-8'))
        # index sitemap
        for smi in root.findall('.//sm:sitemap', namespaces=ns):
            loc_el = smi.find('sm:loc', namespaces=ns)
            if loc_el is not None and loc_el.text:
                yield Discovered(url=loc_el.text.strip(), canonical=None, lastmod=None, source='sitemap', meta={'_type': 'index'})
        # urlset sitemap
        for url_el in root.findall('.//sm:url', namespaces=ns):
            loc_el = url_el.find('sm:loc', namespaces=ns)
            lastmod_el = url_el.find('sm:lastmod', namespaces=ns)
            if loc_el is not None and loc_el.text:
                lastmod = lastmod_el.text.strip() if lastmod_el is not None and lastmod_el.text else None
                yield Discovered(url=loc_el.text.strip(), canonical=None, lastmod=lastmod, source='sitemap', meta={})

    def discover(self) -> Iterable[Discovered]:
        http = self.ctx['http']
        robots = self.ctx['robots']
        rl = self.ctx['ratelimiter']
        conn = self.ctx['db']
        counters = self.ctx['counters']

        sitemap_url = self.cfg['sitemap']
        rps = float(self.cfg.get('rate_limit_rps', 1.0))
        ua = self.cfg.get('user_agent')
        base_headers = dict(self.cfg.get('headers') or {})
        if ua:
            base_headers['User-Agent'] = ua

        def fetch(url: str) -> str | None:
            if not robots.allowed(url, user_agent=ua):
                counters['skipped_robots'] += 1
                return None
            rl.await_slot(url, rps)
            etag, lastmod = dbm.get_resource_etag_lastmod(conn, url)
            try:
                resp = http.get(url, etag=etag, last_modified=lastmod, extra_headers=base_headers)
            except Exception:
                counters['errors'] += 1
                return None
            counters['fetched'] += 1
            counters['status'][resp.status_code] = counters['status'].get(resp.status_code, 0) + 1
            if resp.status_code == 304:
                return None
            if resp.status_code != 200:
                counters['errors'] += 1
                return None
            dbm.set_resource_etag_lastmod(conn, url, resp.headers.get('ETag'), resp.headers.get('Last-Modified'))
            return resp.text

        text = fetch(sitemap_url)
        if not text:
            return
        items = list(self._iter_sitemap_xml(text))
        counters['parsed'] += 1
        for it in items:
            # If index, recursively fetch children
            if it.meta.get('_type') == 'index':
                child_text = fetch(it.url)
                if not child_text:
                    continue
                for sub in self._iter_sitemap_xml(child_text):
                    if sub.meta.get('_type') == 'index':
                        continue
                    counters['discovered'] += 1
                    yield sub
            else:
                counters['discovered'] += 1
                yield it
