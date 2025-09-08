# LinkHarvest — Multi‑site URL discovery and “new posts” detector

LinkHarvest is a pull‑based aggregator that discovers article/post URLs from many sites using the best available source per site (WordPress REST API, RSS/Atom, sitemaps, or crawling). It persists history in SQLite so each run can output only newly seen URLs. Designed for newsfeed‑like consumers and polite by default (robots.txt, rate limits, conditional GETs).

---

## Features

- WordPress, RSS/Atom, Sitemap, and Crawl adapters; optional Playwright for JS rendering
- SQLite persistence with strict URL normalization and first_seen/last_seen tracking
 - Conditional GET (ETag/Last‑Modified) for feeds/sitemaps/APIs and crawled HTML pages (skips unchanged pages on 304)
- Per‑host rate limiting + retries with exponential backoff and jitter
- Per‑run artifacts (NDJSON/CSV) and per‑site counts, with run logs
- Per‑site User‑Agent and headers overrides for sites that block default bots
 - Cross‑site concurrency with per‑host politeness; overall and per‑site tqdm progress bars

## Requirements

- Python 3.11+
- macOS target (works elsewhere too)

## Installation

```bash
python3 -m pip install -r requirements.txt
# Optional (for JS crawling):
python3 -m playwright install chromium
```

## Quick start

1) Edit `config/sites.yaml` to define the sites you want to track

2) Run the aggregator

```bash
python3 -m src.runner --sites config/sites.yaml --out data/runs
```

## WordPress setup (recommended)

Use the WordPress REST API for sites that allow it.

```yaml
sites:
  - id: example_wp
    kind: wordpress
    base: https://example.com
    rate_limit_rps: 1.0
    max_pages: 10
```

The adapter fetches:

```
/wp-json/wp/v2/posts?per_page=100&_fields=link,modified&orderby=date&page=N
```

…until it reaches the end (empty response/400/headers indicate end).

## Other adapters (fallbacks)

- RSS: `kind: rss`, `feed: https://example.com/feed/`
- Sitemap: `kind: sitemap`, `sitemap: https://example.com/sitemap.xml` (supports sitemap index and urlsets)
- Crawl (static): `kind: crawl`, with `base`, `scope_host`, optional `include_paths`, `exclude_patterns`, `max_depth`, `rate_limit_rps`
- JS‑Crawl: same as Crawl but add `js_render: true` and optional `wait_selector`, `max_rendered_pages` (requires Playwright)

  Crawl specifics:
  - Uses ETag/Last‑Modified to skip unchanged pages (304) and prunes traversal (children not enqueued when parent unchanged)
  - Optional TTL via `recrawl_ttl_seconds` to skip pages seen recently

  JS‑Crawl specifics:
  - Performs a preflight conditional GET before rendering; skips Playwright when preflight returns 304
  - Supports `recrawl_ttl_seconds` like Crawl

### Per‑site headers and User‑Agent

You can override the User‑Agent and add extra headers per site. These values are used consistently for:
- robots.txt checks (same UA evaluated)
- all HTTP requests (adapters and canonical resolution)

Example (sitemap with browser‑like UA):

```yaml
- id: example_browser_ua
  kind: sitemap
  sitemap: https://example.com/sitemap_index.xml
  user_agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36
  headers:
    Accept-Language: en-US,en;q=0.9
  rate_limit_rps: 0.5
```

### Crawl examples with TTL

```
- id: example_crawl
  kind: crawl
  base: https://weirdsite.tld
  scope_host: weirdsite.tld
  include_paths: ["/updates/"]
  exclude_patterns: ["/page/\\d+$"]
  max_depth: 2
  rate_limit_rps: 0.5
  recrawl_ttl_seconds: 900   # optional: skip refetch if seen within last 15m
```

```
- id: example_js_crawl
  kind: crawl
  base: https://spa.example
  scope_host: spa.example
  js_render: true
  wait_selector: ".article-list"
  max_rendered_pages: 20
  rate_limit_rps: 0.5
  recrawl_ttl_seconds: 900
```

## CLI usage

```bash
python3 -m src.runner --sites config/sites.yaml --out data/runs [--since SECONDS] [--concurrency N]
```

- `--sites PATH`: YAML config path (required)
- `--out PATH`: Output directory (default `data/runs`)
- `--since SECONDS`: Treat items with `first_seen >= now-SECONDS` as new (also writes `latest_all.csv` for items seen in that window)
- `--concurrency N`: Number of sites to process in parallel (default 1). Per‑host politeness is preserved via a global rate limiter (one in‑flight request per host).

## Concurrency & progress

- Cross‑site parallelism: different sites run concurrently; each worker uses its own SQLite connection.
- Per‑host politeness: a shared rate limiter coordinates all workers so only one request to the same host is in flight at a time.
- Progress bars: an overall `sites` bar plus one per site shows discovery progress (updates as items are yielded by adapters).

## Outputs per run

Directory: `data/runs/<YYYYMMDDTHHMMSSZ>/`

```
new.ndjson           # One JSON object per line {site_id,url,first_seen,lastmod}
new.csv              # Columns: site_id,url,first_seen_iso,lastmod
per_site_counts.csv  # site_id,new_count,total_seen,errors
run.log              # Per‑site metrics and errors
latest_all.csv       # only when --since is set (site_id,url,last_seen_iso,lastmod)
```

## Data model & normalization

- SQLite file: `data/urls.db`
- Tables: `sources`, `urls`, `url_by_source` (see `src/core/db.py`)
- Normalization rules:
  - Lowercase host only; keep path case
  - Strip fragments
  - Remove tracking params: `utm_*`, `gclid`, `fbclid`, `mc_cid`, `mc_eid`
  - Sort remaining query params by key
  - Collapse `/index.html` → `/`
  - One‑round redirect resolution; prefer `<link rel="canonical">` if present

Note on canonical handling:
- Redirect/canonical resolution runs when a URL is first seen; known URLs skip re‑resolution to avoid extra network calls. If you need periodic canonical revalidation, schedule an occasional recheck.

## Politeness & resilience

- robots.txt honored for all fetches (APIs/feeds/sitemaps/crawl/JS crawl)
- Token‑bucket rate limiting per host (`rate_limit_rps` per site)
- Conditional requests for crawled HTML pages (not just feeds/APIs) to reduce bandwidth and runtime
- Retries: up to 3 on 5xx/429/network with exponential backoff (base 0.5s, max 8s, ±20% jitter)
- Timeouts: HTTP connect 5s, read 20s; Playwright navigation default timeout 30s

## Troubleshooting

- Inspect `run.log` in the latest run directory for per‑site errors, HTTP status tallies, and counters (`fetched`, `parsed`, `discovered`, `inserted`, `skipped_robots`, `errors`).
- If a WordPress site returns errors or 403s, try switching that site to `kind: rss` or `kind: sitemap`.
- If no new items appear, ensure URLs actually changed since the last run (diff logic keys off `first_seen`).
- For JS crawling, ensure browsers are installed: `python3 -m playwright install chromium`.
- If a site doesn’t send ETag/Last‑Modified, 304 pruning during crawling is limited; consider setting `recrawl_ttl_seconds` to bound revisit frequency.
- If deep pages change without parent listing pages changing, lower TTL temporarily or rerun an indexing pass with a higher `max_depth`.

## Repository layout

```
.
├─ README.md
├─ requirements.txt
├─ config/
│  └─ sites.yaml
├─ data/
│  ├─ urls.db
│  └─ runs/
├─ src/
│  ├─ core/
│  │  ├─ models.py
│  │  ├─ db.py
│  │  ├─ normalize.py
│  │  ├─ robots.py
│  │  ├─ http.py
│  │  └─ scheduler.py
│  ├─ adapters/
│  │  ├─ base.py
│  │  ├─ rss.py
│  │  ├─ sitemap.py
│  │  ├─ wordpress.py
│  │  ├─ crawl.py
│  │  └─ jscrawl.py
│  ├─ runner.py
│  └─ reports.py
└─ tests/
   ├─ test_normalize.py
   ├─ test_db.py
   ├─ test_rss_adapter.py
   ├─ test_sitemap_adapter.py
   ├─ test_wordpress_adapter.py
   └─ test_diff_logic.py
```

## Development

```bash
python3 -m unittest
```

Guidelines: keep changes minimal and focused; timestamps in UTC; no web server. Network calls are avoided in tests.

## Security, privacy, and politeness

- Respect robots.txt and site rate limits
- Use conditional requests to minimize bandwidth
- No authentication or scraping of private content

## License

Apache 2.0
