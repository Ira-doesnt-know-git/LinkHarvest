from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import yaml

from src.core.http import HttpClient
from src.core.robots import RobotsCache
from src.core.scheduler import RateLimiter
from src.core.normalize import normalize_url, resolve_canonical_once
from src.core import db as dbm
from src.core.models import SiteConfig, Discovered
from src.adapters.wordpress import WordPressAdapter
from src.adapters.rss import RSSAdapter
from src.adapters.sitemap import SitemapAdapter
from src.adapters.crawl import CrawlerAdapter
from src.adapters.jscrawl import JsCrawlAdapter
from src import reports


def _utcnow_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')


def _load_sites(path: str) -> List[SiteConfig]:
    with open(path, 'r') as f:
        data = yaml.safe_load(f)
    sites = []
    for s in data.get('sites', []):
        sites.append(SiteConfig(id=s['id'], kind=s['kind'], cfg=s))
    return sites


def _select_adapter(site: SiteConfig, ctx: Dict):
    if site.kind == 'wordpress':
        return WordPressAdapter(site.id, site.cfg, ctx)
    if site.kind == 'rss':
        return RSSAdapter(site.id, site.cfg, ctx)
    if site.kind == 'sitemap':
        return SitemapAdapter(site.id, site.cfg, ctx)
    if site.kind == 'crawl':
        if site.cfg.get('js_render'):
            return JsCrawlAdapter(site.id, site.cfg, ctx)
        return CrawlerAdapter(site.id, site.cfg, ctx)
    raise ValueError(f"Unknown site kind: {site.kind}")


def run_once(*, sites_path: str, out_dir: str, since_seconds: int | None) -> int:
    os.makedirs(out_dir, exist_ok=True)
    run_id = _utcnow_iso()
    run_dir = os.path.join(out_dir, run_id)
    os.makedirs(run_dir, exist_ok=True)
    log_path = os.path.join(run_dir, 'run.log')

    db_path = os.path.join('data', 'urls.db')
    conn = dbm.ensure_db(db_path)

    http = HttpClient()
    robots = RobotsCache(http.client)
    rl = RateLimiter()

    sites = _load_sites(sites_path)

    run_start = int(time.time())
    # Upsert sources
    for s in sites:
        base = s.cfg.get('base')
        dbm.upsert_source(conn, s.id, s.kind, base, json.dumps(s.cfg))
    conn.commit()

    # Logging and counters per site
    summary: List[Tuple[str, int, int, int]] = []  # site_id, new_count, total_seen, errors
    with open(log_path, 'w') as logf:
        for s in sites:
            counters: Dict = {
                'fetched': 0,
                'parsed': 0,
                'discovered': 0,
                'inserted': 0,
                'skipped_robots': 0,
                'errors': 0,
                'status': {},
            }
            ctx = {
                'http': http,
                'robots': robots,
                'ratelimiter': rl,
                'db': conn,
                'counters': counters,
            }
            adapter = _select_adapter(s, ctx)
            logf.write(f"[{s.id}] start kind={s.kind}\n")
            try:
                for d in adapter.discover():
                    # Normalize and enrich with one-round redirect + canonical
                    final_url, canon_tag = normalize_url(d.url), None
                    try:
                        resolved, canon = resolve_canonical_once(d.url, http, robots=robots, ratelimiter=rl, rps=float(s.cfg.get('rate_limit_rps', 1.0)))
                        candidate = canon or resolved
                        canon_tag = canon
                        final_url = normalize_url(candidate)
                    except Exception:
                        # Fallback to simple normalization
                        final_url = normalize_url(d.url)
                    is_new_url, first_seen_url = dbm.upsert_url(
                        conn,
                        final_url,
                        canonical=canon_tag or d.canonical,
                        discovered_via=d.source,
                        http_status=None,
                        lastmod=d.lastmod,
                        etag=None,
                    )
                    is_new_pair, first_seen_pair = dbm.touch_url_by_source(conn, s.id, final_url)
                    if is_new_pair:
                        counters['inserted'] += 1
                conn.commit()
            except Exception as e:
                counters['errors'] += 1
                logf.write(f"[{s.id}] ERROR: {e}\n")
            # compute counts for site
            new_count, total_seen = dbm.counts_for_site(conn, s.id)
            summary.append((s.id, new_count, total_seen, counters['errors']))
            # write per-site metrics snapshot to log
            logf.write(f"[{s.id}] metrics: {json.dumps(counters)}\n")

    run_end = int(time.time())
    # Select new this run, or since flag override
    if since_seconds is not None:
        window_start = int(time.time()) - since_seconds
        window_end = int(time.time())
    else:
        window_start = run_start
        window_end = run_end

    new_rows = list(dbm.query_new_urls(conn, start_ts=window_start, end_ts=window_end))
    # Artifacts
    reports.write_new_ndjson(os.path.join(run_dir, 'new.ndjson'), new_rows)
    reports.write_new_csv(os.path.join(run_dir, 'new.csv'), new_rows)
    reports.write_counts_csv(os.path.join(run_dir, 'per_site_counts.csv'), summary)
    if since_seconds is not None:
        latest_rows = list(dbm.query_latest_all(conn, since_ts=int(time.time()) - since_seconds))
        reports.write_latest_all_csv(os.path.join(run_dir, 'latest_all.csv'), latest_rows)

    # Print compact summary
    total_new = sum(n for _, n, _, _ in summary)
    print(f"Run {run_id}: new={total_new}, sites={len(sites)}, out={run_dir}")
    return 0


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='LinkHarvest runner')
    ap.add_argument('--sites', required=True, help='YAML config path')
    ap.add_argument('--out', default=os.path.join('data', 'runs'), help='Output directory')
    ap.add_argument('--since', type=int, default=None, help='SECONDS window for new items (overrides run window)')
    args = ap.parse_args(argv)

    return run_once(sites_path=args.sites, out_dir=args.out, since_seconds=args.since)


if __name__ == '__main__':
    raise SystemExit(main())
