# LinkHarvest Flowcharts

Below are two Mermaid diagrams:
- A detailed technical flowchart of the end-to-end pipeline
- A high‑level overview focused on the main concepts

## Detailed Pipeline

```mermaid
flowchart TD
  %% Top level
  A[CLI runner.py] --> B[Load sites.yaml]
  B --> C[Upsert sources in DB]
  C --> D{--concurrency N?}
  D -->|spawn N workers| E[ThreadPoolExecutor]

  subgraph Runner_and_Scheduler
    E --> F[For each site submit task]
    F --> G[Shared RateLimiter per-host]
    F --> H[Shared RobotsCache per-UA]
  end

  %% Site worker
  subgraph Site_Worker_one_per_site
    I[Open per-site SQLite autocommit] --> J[Select adapter by kind]
    J --> J1{wordpress}
    J --> J2{rss}
    J --> J3{sitemap}
    J --> J4{crawl}
    J --> J5{crawl plus js_render}

    %% HTTP and Politeness layer reused by all adapters
    subgraph HTTP_and_Politeness
      K{robots allowed?} -->|no| Kskip[Skip and count skipped_robots]
      K -->|yes| L[RateLimiter await_slot host rps]
      L --> M[HttpClient get url ETag Last-Modified follow_redirects UA headers]
      M --> N{HTTP 304?}
    end

    %% WordPress
    J1 --> K
    N -->|304| WPdone[Stop no new pages]
    N -->|200| WPparse[Parse JSON posts]
    WPparse --> O[Yield Discovered url lastmod source api]

    %% RSS
    J2 --> K
    N -->|304| RSSdone[Stop]
    N -->|200| RSSparse[Parse feed entries]
    RSSparse --> O

    %% Sitemap
    J3 --> K
    N -->|304| SMdone[Stop]
    N -->|200| SMparse[Parse XML]
    SMparse --> P{index or urlset?}
    P -->|index| SMchild[Fetch each child sitemap via K to L to M to N]
    P -->|urlset| O
    SMchild --> O

    %% Crawl static
    J4 --> Q{recrawl_ttl hit?}
    Q -->|yes| Cskip[Skip fetch]
    Q -->|no| K
    N -->|304| Cdone[Skip parse enqueue children]
    N -->|200| Cparse[Parse HTML links]
    Cparse --> O

    %% JS Crawl
    J5 --> Q2{recrawl_ttl hit?}
    Q2 -->|yes| JSSkip[Skip]
    Q2 -->|no| K
    N -->|304| JSPrefSkip[Skip Playwright render]
    N -->|200| JSRender[Playwright goto wait_selector]
    JSRender --> JSParse[Parse rendered HTML links]
    JSParse --> O

    %% Common path for yielded URLs
    O --> R[Normalize URL]
    R --> S{Exists in DB?}
    S -->|yes| T[Upsert url_by_source touch inserted++ if new pair]
    S -->|no| U[Resolve canonical redirect once robots rate limit UA headers]
    U --> V[Normalize candidate]
    V --> W[Upsert urls and url_by_source]
    T --> X[Short transaction autocommit]
    W --> X
    X --> Y[Update per-site tqdm]

    %% Finish
    Y --> Z[Return counters]
  end

  %% After all workers
  E --> AA[Wait for futures]
  AA --> AB[Write run.log per-site metrics]
  AB --> AC[Compute per_site_counts.csv]
  AC --> AD[Query new URLs for window]
  AD --> AE[Write new.ndjson and new.csv plus latest_all.csv if --since]
```

## High‑Level Overview
```mermaid
flowchart LR
  A[Start CLI] --> B[Load config]
  B --> C[Spawn workers concurrency=N]
  C --> D[Per-site worker]
  D --> E{Adapter?}
  E -->|WordPress| F1[Fetch posts API]
  E -->|RSS| F2[Fetch feed]
  E -->|Sitemap| F3[Fetch sitemap]
  E -->|Crawl| F4[Fetch HTML]
  E -->|JS-crawl| F5[Render page]
  F1 --> R{Robots allow?}
  F2 --> R
  F3 --> R
  F4 --> R
  F5 --> R
  R -->|No| S[Skip politely]
  R -->|Yes| T[Rate limit]
  T --> U[HTTP request]
  U --> V{New data?}
  V -->|No 304| W[Skip quickly]
  V -->|Yes| X[Parse and discover]
  X --> Y[Normalize and dedupe]
  Y --> Z[Store in SQLite]
  Z --> AA[Aggregate results]
  AA --> AB[Write reports]
  AB --> AC[Done]
```
