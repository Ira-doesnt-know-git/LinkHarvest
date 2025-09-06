from __future__ import annotations

import os
import sqlite3
import time
from typing import Dict, Iterable, Optional, Tuple

SCHEMA = r"""
CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  base TEXT,
  cfg JSON
);

CREATE TABLE IF NOT EXISTS urls (
  url TEXT PRIMARY KEY,
  canonical TEXT,
  first_seen INTEGER NOT NULL,
  last_seen INTEGER NOT NULL,
  discovered_via TEXT,
  http_status INTEGER,
  lastmod TEXT,
  etag TEXT
);

CREATE TABLE IF NOT EXISTS url_by_source (
  source_id TEXT NOT NULL,
  url TEXT NOT NULL,
  first_seen INTEGER NOT NULL,
  last_seen INTEGER NOT NULL,
  PRIMARY KEY (source_id, url)
);

CREATE INDEX IF NOT EXISTS idx_urls_last_seen ON urls(last_seen);
CREATE INDEX IF NOT EXISTS idx_ubs_last_seen ON url_by_source(last_seen);
"""


def ensure_db(path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA synchronous=NORMAL;')
    conn.executescript(SCHEMA)
    return conn


def upsert_source(conn: sqlite3.Connection, sid: str, kind: str, base: Optional[str], cfg_json: str) -> None:
    conn.execute(
        "INSERT INTO sources(id, kind, base, cfg) VALUES(?,?,?,?)\n"
        "ON CONFLICT(id) DO UPDATE SET kind=excluded.kind, base=excluded.base, cfg=excluded.cfg",
        (sid, kind, base, cfg_json),
    )


def _now() -> int:
    return int(time.time())


def upsert_url(conn: sqlite3.Connection, url: str, *, canonical: Optional[str], discovered_via: Optional[str], http_status: Optional[int], lastmod: Optional[str], etag: Optional[str]) -> Tuple[bool, int]:
    now = _now()
    cur = conn.execute("SELECT first_seen FROM urls WHERE url=?", (url,))
    row = cur.fetchone()
    is_new = row is None
    if is_new:
        conn.execute(
            "INSERT INTO urls(url, canonical, first_seen, last_seen, discovered_via, http_status, lastmod, etag) VALUES(?,?,?,?,?,?,?,?)",
            (url, canonical, now, now, discovered_via, http_status, lastmod, etag),
        )
        first_seen = now
    else:
        first_seen = row[0]
        conn.execute(
            "UPDATE urls SET canonical=COALESCE(?, canonical), last_seen=?, discovered_via=COALESCE(?, discovered_via), http_status=COALESCE(?, http_status), lastmod=COALESCE(?, lastmod), etag=COALESCE(?, etag) WHERE url=?",
            (canonical, now, discovered_via, http_status, lastmod, etag, url),
        )
    return is_new, first_seen


def touch_url_by_source(conn: sqlite3.Connection, sid: str, url: str) -> Tuple[bool, int]:
    now = _now()
    cur = conn.execute("SELECT first_seen FROM url_by_source WHERE source_id=? AND url=?", (sid, url))
    row = cur.fetchone()
    is_new = row is None
    if is_new:
        conn.execute(
            "INSERT INTO url_by_source(source_id, url, first_seen, last_seen) VALUES(?,?,?,?)",
            (sid, url, now, now),
        )
        first_seen = now
    else:
        first_seen = row[0]
        conn.execute(
            "UPDATE url_by_source SET last_seen=? WHERE source_id=? AND url=?",
            (now, sid, url),
        )
    return is_new, first_seen


def set_resource_etag_lastmod(conn: sqlite3.Connection, resource_url: str, etag: Optional[str], lastmod: Optional[str]) -> None:
    # Store conditional GET metadata in urls table keyed by resource URL
    now = _now()
    cur = conn.execute("SELECT url FROM urls WHERE url=?", (resource_url,))
    if cur.fetchone() is None:
        conn.execute(
            "INSERT INTO urls(url, canonical, first_seen, last_seen, discovered_via, http_status, lastmod, etag) VALUES(?,?,?,?,?,?,?,?)",
            (resource_url, None, now, now, None, None, lastmod, etag),
        )
    else:
        conn.execute(
            "UPDATE urls SET last_seen=?, lastmod=COALESCE(?, lastmod), etag=COALESCE(?, etag) WHERE url=?",
            (now, lastmod, etag, resource_url),
        )


def get_resource_etag_lastmod(conn: sqlite3.Connection, resource_url: str) -> Tuple[Optional[str], Optional[str]]:
    cur = conn.execute("SELECT etag, lastmod FROM urls WHERE url=?", (resource_url,))
    row = cur.fetchone()
    if not row:
        return None, None
    return row[0], row[1]


def query_new_urls(conn: sqlite3.Connection, *, start_ts: int, end_ts: int) -> Iterable[Tuple[str, str, int, Optional[str]]]:
    sql = (
        "SELECT source_id, url, first_seen, (SELECT lastmod FROM urls u WHERE u.url = url_by_source.url) as lastmod "
        "FROM url_by_source WHERE first_seen BETWEEN ? AND ? ORDER BY first_seen ASC"
    )
    for row in conn.execute(sql, (start_ts, end_ts)):
        yield row  # (source_id, url, first_seen, lastmod)


def query_latest_all(conn: sqlite3.Connection, *, since_ts: int) -> Iterable[Tuple[str, str, int, Optional[str]]]:
    sql = (
        "SELECT source_id, url, last_seen, (SELECT lastmod FROM urls u WHERE u.url = url_by_source.url) as lastmod "
        "FROM url_by_source WHERE last_seen >= ? ORDER BY last_seen ASC"
    )
    for row in conn.execute(sql, (since_ts,)):
        yield row  # (source_id, url, last_seen, lastmod)


def counts_for_site(conn: sqlite3.Connection, sid: str) -> Tuple[int, int]:
    cur = conn.execute("SELECT COUNT(*) FROM url_by_source WHERE source_id=?", (sid,))
    total_seen = cur.fetchone()[0]
    cur2 = conn.execute(
        "SELECT COUNT(*) FROM url_by_source WHERE source_id=? AND first_seen = last_seen",
        (sid,),
    )
    new_count = cur2.fetchone()[0]
    return new_count, total_seen
