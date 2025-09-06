from __future__ import annotations

import csv
import os
from datetime import datetime, timezone
from typing import Iterable, Dict, Tuple, Optional

import orjson


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def write_new_ndjson(path: str, rows: Iterable[Tuple[str, str, int, Optional[str]]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        for site_id, url, first_seen, lastmod in rows:
            obj = {
                'site_id': site_id,
                'url': url,
                'first_seen': first_seen,
                'lastmod': lastmod,
            }
            f.write(orjson.dumps(obj))
            f.write(b"\n")


def write_new_csv(path: str, rows: Iterable[Tuple[str, str, int, Optional[str]]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['site_id', 'url', 'first_seen_iso', 'lastmod'])
        for site_id, url, first_seen, lastmod in rows:
            w.writerow([site_id, url, _iso(first_seen), lastmod or ''])


def write_counts_csv(path: str, counts: Iterable[Tuple[str, int, int, int]]) -> None:
    # rows: (site_id, new_count, total_seen, errors)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['site_id', 'new_count', 'total_seen', 'errors'])
        for row in counts:
            w.writerow(row)


def write_latest_all_csv(path: str, rows: Iterable[Tuple[str, str, int, Optional[str]]]) -> None:
    # rows: (site_id, url, last_seen, lastmod)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['site_id', 'url', 'last_seen_iso', 'lastmod'])
        for site_id, url, last_seen, lastmod in rows:
            w.writerow([site_id, url, _iso(last_seen), lastmod or ''])
