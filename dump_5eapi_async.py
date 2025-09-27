#!/usr/bin/env python3
"""
5eAPI Dumper — Async + ETag + SQLite Resume (polite + robust)

Adds on top of the robust sync script:
- asyncio + aiohttp for efficient, polite concurrency
- Global rate limiter via semaphore + inter-request delay
- Honors Retry-After on 429 and does exponential backoff with jitter
- ETag conditional requests (If-None-Match) to skip unchanged objects
- SQLite persistence for URL status (resume, audit, incremental updates)
- Retry-only-failures mode
- Category/index isolation; graceful shutdown
- Structured logging

Usage (examples):
  python dump_5eapi_async.py --format both --log-level INFO
  python dump_5eapi_async.py --categories spells,monsters --workers 24 --delay 0.02
  python dump_5eapi_async.py --retry-failures --log-level DEBUG

Notes on politeness:
- Defaults are conservative: workers=10, delay=0.05.
- If you see 429s, *lower* workers and *increase* delay.
- We also respect Retry-After headers from the server.

Output:
- by_category/<cat>.jsonl (and/or .txt)
- all.jsonl / all.txt
- SQLite DB: state.db with table objects(url PRIMARY KEY, category, status, etag, last_fetch, path)

"""

import argparse
import asyncio
import json
import logging
import os
import random
import signal
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import aiohttp
import async_timeout

BASE = "https://www.dnd5eapi.co"
ROOT = f"{BASE}/api"

STOP_REQUESTED = False


def _setup_logging(level: str) -> None:
    lvl = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=lvl,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )


def _install_signal_handlers():
    def _handler(signum, frame):
        global STOP_REQUESTED
        STOP_REQUESTED = True
        logging.warning("Stop requested (signal %s). Finishing current tasks and exiting gracefully...", signum)
    try:
        signal.signal(signal.SIGINT, _handler)
        signal.signal(signal.SIGTERM, _handler)
    except Exception:
        pass


def ensure_outdir_writable(outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    testfile = outdir / ".write_test"
    try:
        testfile.write_text("ok", encoding="utf-8")
        testfile.unlink(missing_ok=True)
    except Exception as e:
        raise RuntimeError(f"Output directory not writable: {outdir} ({e})")


# ------------- SQLite persistence -------------

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS objects (
  url TEXT PRIMARY KEY,
  category TEXT,
  status TEXT,            -- 'success','failed','pending'
  etag TEXT,
  last_fetch REAL,
  path TEXT               -- optional per-object path
);
"""

def open_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute(CREATE_SQL)
    return conn

def upsert_row(conn: sqlite3.Connection, url: str, category: str, status: str, etag: Optional[str], path: Optional[str]):
    conn.execute(
        "INSERT INTO objects(url,category,status,etag,last_fetch,path) VALUES(?,?,?,?,?,?) "
        "ON CONFLICT(url) DO UPDATE SET category=excluded.category, status=excluded.status, "
        "etag=COALESCE(excluded.etag, objects.etag), last_fetch=excluded.last_fetch, path=COALESCE(excluded.path, objects.path)",
        (url, category, status, etag, time.time(), path),
    )

def get_row(conn: sqlite3.Connection, url: str) -> Optional[Tuple]:
    cur = conn.execute("SELECT url, category, status, etag, last_fetch, path FROM objects WHERE url=?", (url,))
    return cur.fetchone()

def list_failed(conn: sqlite3.Connection) -> List[str]:
    cur = conn.execute("SELECT url FROM objects WHERE status='failed'")
    return [r[0] for r in cur.fetchall()]

# ------------- HTTP / Async -------------

@dataclass
class FetchResult:
    url: str
    obj: Optional[dict]
    err: Optional[str]
    etag: Optional[str]


class PoliteFetcher:
    def __init__(self, workers: int, delay: float, timeout: int, max_retries: int):
        self.sema = asyncio.Semaphore(workers)
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries

    async def fetch_json(self, session: aiohttp.ClientSession, url: str, etag: Optional[str] = None) -> FetchResult:
        attempt = 0
        headers = {"Accept-Encoding": "gzip"}
        if etag:
            headers["If-None-Match"] = etag

        while True:
            attempt += 1
            if STOP_REQUESTED:
                return FetchResult(url, None, "Stop requested", None)

            async with self.sema:
                try:
                    async with async_timeout.timeout(self.timeout):
                        async with session.get(url, headers=headers) as r:
                            # 304 = not modified
                            if r.status == 304:
                                await asyncio.sleep(self.delay)
                                return FetchResult(url, None, None, etag)

                            if r.status == 429:
                                ra = r.headers.get("Retry-After")
                                wait = float(ra) if ra and ra.isdigit() else max(2.0, self.delay * 10)
                                logging.warning("429 from %s; sleeping %.2fs", url, wait)
                                await asyncio.sleep(wait)
                                if attempt <= self.max_retries:
                                    continue
                                return FetchResult(url, None, f"HTTP 429 after retries", None)

                            if 500 <= r.status < 600:
                                # exponential backoff with jitter
                                backoff = min(10.0, (2 ** (attempt - 1)) * self.delay) + random.uniform(0, 0.25)
                                logging.warning("%s server error %d; retrying in %.2fs", url, r.status, backoff)
                                await asyncio.sleep(backoff)
                                if attempt <= self.max_retries:
                                    continue
                                return FetchResult(url, None, f"HTTP {r.status} after retries", None)

                            r.raise_for_status()
                            # parse JSON
                            try:
                                data = await r.json()
                            except Exception as e:
                                text = await r.text()
                                snippet = text[:200].replace("\n", "\\n")
                                return FetchResult(url, None, f"JSON error: {e}; first 200: {snippet}", None)

                            new_etag = r.headers.get("ETag")
                            await asyncio.sleep(self.delay)
                            return FetchResult(url, data, None, new_etag)
                except aiohttp.ClientResponseError as e:
                    if attempt <= self.max_retries:
                        backoff = min(10.0, (2 ** (attempt - 1)) * self.delay) + random.uniform(0, 0.25)
                        logging.warning("Response error on %s: %s; retrying in %.2fs", url, e, backoff)
                        await asyncio.sleep(backoff)
                        continue
                    return FetchResult(url, None, f"ResponseError: {e}", None)
                except Exception as e:
                    if attempt <= self.max_retries:
                        backoff = min(10.0, (2 ** (attempt - 1)) * self.delay) + random.uniform(0, 0.25)
                        logging.warning("Request error on %s: %s; retrying in %.2fs", url, e, backoff)
                        await asyncio.sleep(backoff)
                        continue
                    return FetchResult(url, None, f"Exception: {e}", None)


async def discover_categories(session: aiohttp.ClientSession, fetcher: PoliteFetcher) -> Dict[str, str]:
    res = await fetcher.fetch_json(session, ROOT, etag=None)
    if res.err:
        raise RuntimeError(f"Failed to load /api: {res.err}")
    if not isinstance(res.obj, dict):
        raise ValueError(f"Unexpected /api payload type: {type(res.obj)}")
    cats = {k: BASE + v for k, v in res.obj.items() if isinstance(v, str) and v.startswith("/")}
    if not cats:
        raise ValueError("No categories found at /api.")
    return cats


async def fetch_index(session: aiohttp.ClientSession, fetcher: PoliteFetcher, index_url: str) -> List[dict]:
    res = await fetcher.fetch_json(session, index_url, etag=None)
    if res.err:
        raise RuntimeError(f"Index fetch failed {index_url}: {res.err}")
    idx = res.obj or {}
    results = idx.get("results") or []
    if not isinstance(results, list):
        raise ValueError(f"Unexpected 'results' at {index_url}: {type(results)}")
    return results


def dump_jsonl(path: Path, objs: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for obj in objs:
            if obj is not None:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def dump_txt(path: Path, objs: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for i, obj in enumerate(objs, 1):
            if obj is None:
                continue
            f.write(f"### OBJECT {i}\n")
            f.write(json.dumps(obj, ensure_ascii=False, indent=2))
            f.write("\n\n")


async def main_async(args):
    _install_signal_handlers()

    outdir = Path(args.outdir)
    by_cat = outdir / "by_category"
    ensure_outdir_writable(outdir)
    by_cat.mkdir(parents=True, exist_ok=True)

    # SQLite
    db_path = outdir / "state.db"
    conn = open_db(db_path)

    fetcher = PoliteFetcher(workers=args.workers, delay=args.delay, timeout=args.timeout, max_retries=args.max_retries)

    timeout = aiohttp.ClientTimeout(total=None, connect=args.timeout, sock_read=args.timeout)
    async with aiohttp.ClientSession(
        timeout=timeout,
        headers={"User-Agent": "5eAPI-full-dump/async-1.0", "Accept": "application/json"},
        raise_for_status=False,
    ) as session:

        # Discover categories (unless retry-failures mode)
        if not args.retry_failures:
            cats = await discover_categories(session, fetcher)

            if args.categories.lower() != "all":
                requested = {c.strip() for c in args.categories.split(",") if c.strip()}
                missing = requested - set(cats.keys())
                if missing:
                    logging.warning("Unknown categories (ignored): %s", ", ".join(sorted(missing)))
                cats = {k: v for k, v in cats.items() if k in requested}

            if not cats:
                logging.critical("No categories resolved. Exiting.")
                return 2

            logging.info("Discovered %d categories: %s", len(cats), ", ".join(sorted(cats.keys())))

            # Build URL list from indices
            cat_urls: Dict[str, List[str]] = {}
            for cat, url in sorted(cats.items()):
                if STOP_REQUESTED:
                    logging.warning("Stop requested before fetching category %s.", cat)
                    break
                logging.info("Index -> %s", url)
                try:
                    results = await fetch_index(session, fetcher, url)
                except Exception as e:
                    logging.error("Skipping category %s (index failed): %s", cat, e)
                    continue

                urls = []
                for item in results:
                    rel = item.get("url")
                    if isinstance(rel, str) and rel.startswith("/"):
                        urls.append(BASE + rel)
                if args.limit_per_category > 0:
                    urls = urls[: args.limit_per_category]
                cat_urls[cat] = urls

            # Insert "pending" into DB for any new URLs
            with conn:
                for cat, urls in cat_urls.items():
                    for u in urls:
                        row = get_row(conn, u)
                        if not row:
                            upsert_row(conn, u, cat, "pending", None, None)

        # Build worklist
        work_urls: List[Tuple[str, str]] = []  # (url, category)
        if args.retry_failures:
            # Only failed URLs
            failed = list_failed(conn)
            logging.info("Retrying %d failed URLs", len(failed))
            for u in failed:
                row = get_row(conn, u)
                cat = row[1] if row else "unknown"
                work_urls.append((u, cat))
        else:
            # All 'pending' or 'failed'
            cur = conn.execute("SELECT url, category FROM objects WHERE status!='success' OR status IS NULL")
            work_urls = cur.fetchall()
            logging.info("Planned %d fetches", len(work_urls))

        # Producer/consumer tasks
        async def worker(u: str, cat: str):
            if STOP_REQUESTED:
                return None

            # Check ETag and current status
            row = get_row(conn, u)
            etag = row[3] if row else None
            status = row[2] if row else None

            if status == "success" and not args.force_refresh:
                # Already done
                return None

            res = await fetcher.fetch_json(session, u, etag=etag)

            if res.err:
                with conn:
                    upsert_row(conn, u, cat, "failed", res.etag, None)
                return ("failed", u, res.err)

            # 304 case: no new object returned, but not an error
            if res.obj is None:
                with conn:
                    upsert_row(conn, u, cat, "success", res.etag or etag, None)
                return ("not_modified", u, "304")

            # Got object
            with conn:
                upsert_row(conn, u, cat, "success", res.etag, None)
            return ("success", u, res.obj)

        # Run tasks with bounded concurrency (via fetcher.sema)
        results = []
        for u, cat in work_urls:
            if STOP_REQUESTED:
                break
            results.append(asyncio.create_task(worker(u, cat)))

        successes: Dict[str, List[dict]] = {}
        failures: List[str] = []

        for coro in asyncio.as_completed(results):
            if STOP_REQUESTED:
                break
            out = await coro
            if not out:
                continue
            status, u, payload = out
            if status == "success":
                # payload is the JSON object; group by category for later output
                row = get_row(conn, u)
                cat = row[1] if row else "unknown"
                successes.setdefault(cat, []).append(payload)
            elif status == "not_modified":
                # We'll rely on existing by_category files or skip (still counts as success)
                pass
            else:
                failures.append(f"{u}\t{payload}")

        # Sort each category's objs deterministically
        for cat, objs in successes.items():
            def key(o):
                return (str(o.get("index")) if isinstance(o, dict) and o.get("index") is not None else "",
                        str(o.get("name")) if isinstance(o, dict) and o.get("name") is not None else "")
            objs.sort(key=key)

        # Write outputs
        if args.format in ("jsonl", "both"):
            for cat, objs in successes.items():
                dump_jsonl(by_cat / f"{cat}.jsonl", objs)
            # combined
            all_objs = [o for objs in successes.values() for o in objs]
            if all_objs:
                dump_jsonl(outdir / "all.jsonl", all_objs)

        if args.format in ("txt", "both"):
            for cat, objs in successes.items():
                dump_txt(by_cat / f"{cat}.txt", objs)
            all_objs = [o for objs in successes.values() for o in objs]
            if all_objs:
                dump_txt(outdir / "all.txt", all_objs)

        # Failures file
        if failures:
            (outdir / args.failures_out).write_text("\n".join(failures), encoding="utf-8")
            logging.warning("Wrote failures list: %s (%d lines)", outdir / args.failures_out, len(failures))

    return 0


def main():
    p = argparse.ArgumentParser(description="Dump 5eAPI with asyncio, ETag, and SQLite resume (polite).")
    p.add_argument("--outdir", default="5eapi_dump", help="Output directory (default: 5eapi_dump)")
    p.add_argument("--format", choices=["jsonl", "txt", "both"], default="jsonl", help="Output format(s)")
    p.add_argument("--categories", default="all", help='Comma-separated categories (default "all")')
    p.add_argument("--workers", type=int, default=10, help="Max concurrent requests (default: 10)")
    p.add_argument("--delay", type=float, default=0.05, help="Delay between requests per worker (seconds)")
    p.add_argument("--timeout", type=int, default=30, help="Per-request timeout seconds (default: 30)")
    p.add_argument("--max-retries", type=int, default=5, help="Extra retries for transient errors (default: 5)")
    p.add_argument("--failures-out", default="failures.txt", help="Where to write failed URLs (+messages)")
    p.add_argument("--retry-failures", action="store_true", help="Only retry URLs previously marked failed")
    p.add_argument("--limit-per-category", type=int, default=0, help="Debug: limit items per category (0=all)")
    p.add_argument("--log-level", default="INFO", help="Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL")
    p.add_argument("--force-refresh", action="store_true", help="Ignore success cache and fetch everything again")

    args = p.parse_args()
    _setup_logging(args.log_level)

    try:
        rc = asyncio.run(main_async(args))
    except KeyboardInterrupt:
        logging.warning("Interrupted by user. Exiting.")
        rc = 130
    sys.exit(rc)


if __name__ == "__main__":
    main()
