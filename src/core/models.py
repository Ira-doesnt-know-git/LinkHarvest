from __future__ import annotations

from typing import Optional, Dict, NamedTuple, Literal, Any

SourceKind = Literal['wordpress', 'rss', 'sitemap', 'crawl', 'jscrawl']
DiscoverySource = Literal['api', 'rss', 'sitemap', 'crawl']


class Discovered(NamedTuple):
    url: str
    canonical: Optional[str]
    lastmod: Optional[str]
    source: DiscoverySource
    meta: Dict[str, str]


class SiteConfig(NamedTuple):
    id: str
    kind: SourceKind
    cfg: Dict[str, Any]
