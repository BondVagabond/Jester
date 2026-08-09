#!/usr/bin/env python3
"""Compatibility wrapper for the managed crawl runtime.

This script used to be an ad hoc crawler. It now requires manifest-backed collection and
forwards into the canonical runtime.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.runtime.crawler import run_crawl_once
from pipeline.runtime.models import DEFAULT_RUNTIME_ROOT
from pipeline.runtime.state_store import RuntimeStateStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manifest-backed crawl wrapper for approved sources.")
    parser.add_argument("--source-id", required=True, help="Approved source manifest id.")
    parser.add_argument("--runtime-root", default=str(DEFAULT_RUNTIME_ROOT), help="Runtime root directory.")
    parser.add_argument("--dry-run", action="store_true", help="Evaluate the crawl without writing staged outputs.")
    parser.add_argument("--max-pages", type=int, default=None, help="Optional page cap for this run.")
    parser.add_argument("--enable-candidate-discovery", action="store_true", help="Also emit candidate discovery records for external domains.")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    runtime_root = Path(args.runtime_root)
    store = RuntimeStateStore(runtime_root / "state" / "runtime.db")
    summary = run_crawl_once(
        source_id=args.source_id,
        runtime_root=runtime_root,
        store=store,
        dry_run=args.dry_run,
        job_id="crawl.manual",
        job_config={
            "max_pages": args.max_pages,
            "enable_candidate_discovery": args.enable_candidate_discovery,
        },
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
