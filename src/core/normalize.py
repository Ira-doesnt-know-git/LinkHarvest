from __future__ import annotations

import re
from typing import Optional, Tuple
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from lxml import html

try:
    import httpx  # type: ignore
except Exception:  # pragma: no cover
    httpx = None

TRACKING_PARAMS = {
    'gclid', 'fbclid', 'mc_cid', 'mc_eid'
}


def _strip_tracking_params(query_items):
    cleaned = []
    for k, v in query_items:
        if k.startswith('utm_'):
            continue
        if k in TRACKING_PARAMS:
            continue
        cleaned.append((k, v))
    return cleaned


def _collapse_index_html(path: str) -> str:
    if path.endswith('/index.html'):
        return path[: -len('/index.html')] + '/'
    return path


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    scheme = parts.scheme
    netloc = parts.netloc.lower()  # lowercase host only
    path = _collapse_index_html(parts.path or '/')
    # remove fragments
    fragment = ''
    # sort query params by key and strip tracking
    query_items = parse_qsl(parts.query, keep_blank_values=True)
    query_items = _strip_tracking_params(query_items)
    query_items.sort(key=lambda x: x[0])
    query = urlencode(query_items, doseq=True)
    return urlunsplit((scheme, netloc, path, query, fragment))


def resolve_canonical_once(url: str, http_client, *, robots=None, ratelimiter=None, rps: float = 1.0) -> Tuple[str, Optional[str]]:
    """
    Try a single redirect resolution via HEAD, and if HTML, prefer <link rel="canonical">.
    Returns (final_url, canonical_tag_url_or_None). If network unavailable, returns input.
    """
    try:
        if robots and not robots.allowed(url):
            return url, None
        if ratelimiter:
            ratelimiter.await_slot(url, rps)
        resp = http_client.get(url, extra_headers={"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}, max_retries=1)
    except Exception:
        return url, None
    if 300 <= resp.status_code < 400 and resp.headers.get('Location'):
        return resp.headers['Location'], None
    content_type = resp.headers.get('Content-Type', '')
    if 'html' in content_type and resp.text:
        try:
            doc = html.fromstring(resp.text)
            link = doc.xpath("//link[@rel='canonical']/@href")
            if link:
                return url, link[0]
        except Exception:
            pass
    return url, None

