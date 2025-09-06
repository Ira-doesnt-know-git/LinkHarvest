from __future__ import annotations

import re
from collections import deque
from typing import Iterable, Set
from urllib.parse import urljoin, urlsplit

from lxml import html
from playwright.sync_api import sync_playwright

from src.adapters.base import Adapter
from src.core.models import Discovered


class JsCrawlAdapter(Adapter):
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

    @staticmethod
    def _extract_links(base_url: str, content: str):
        try:
            doc = html.fromstring(content)
        except Exception:
            return []
        out = []
        for a in doc.xpath('//a[@href]'):
            href = a.get('href')
            if not href:
                continue
            out.append(urljoin(base_url, href))
        return out

    def discover(self) -> Iterable[Discovered]:
        # Only render if js_render true in cfg
        if not self.cfg.get('js_render', False):
            return []

        robots = self.ctx['robots']
        rl = self.ctx['ratelimiter']
        counters = self.ctx['counters']

        base = self.cfg['base']
        rps = float(self.cfg.get('rate_limit_rps', 0.5))
        max_depth = int(self.cfg.get('max_depth', 2))
        wait_selector = self.cfg.get('wait_selector')  # optional
        max_rendered = int(self.cfg.get('max_rendered_pages', 20))

        visited: Set[str] = set()
        rendered = 0
        q = deque([(base, 0)])

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            try:
                while q and rendered < max_rendered:
                    url, depth = q.popleft()
                    if url in visited:
                        continue
                    visited.add(url)

                    if not self._in_scope(url):
                        continue
                    if not robots.allowed(url):
                        counters['skipped_robots'] += 1
                        continue

                    rl.await_slot(url, rps)
                    try:
                        page.set_default_navigation_timeout(30000)
                        page.set_default_timeout(30000)
                        page.goto(url, wait_until='domcontentloaded')
                        if wait_selector:
                            try:
                                page.wait_for_selector(wait_selector)
                            except Exception:
                                # Continue even if selector didn't appear within timeout
                                pass
                        content = page.content()
                        counters['fetched'] += 1
                        counters['parsed'] += 1
                        rendered += 1
                    except Exception:
                        counters['errors'] += 1
                        continue

                    for link in self._extract_links(url, content):
                        if not self._in_scope(link):
                            continue
                        yield Discovered(url=link, canonical=None, lastmod=None, source='crawl', meta={})
                        counters['discovered'] += 1
                        if depth + 1 <= max_depth:
                            q.append((link, depth + 1))
            finally:
                page.close()
                context.close()
                browser.close()

