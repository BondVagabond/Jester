#!/usr/bin/env python3
"""Validate candidate source review records."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

VALID_METHODS = {"approved_outbound_link", "sitemap", "feed", "query_seed", "search_snapshot", "manual"}
VALID_STATUSES = {"pending_review", "approved", "rejected", "quarantined"}


def validate_candidate_manifest(candidate: dict[str, Any], path: Path) -> list[str]:
    errors: list[str] = []
    for key in [
        "candidate_source_id",
        "candidate_domain",
        "seed_url",
        "first_seen_at",
        "last_seen_at",
        "discovery_methods",
        "relevance_score",
        "risk_score",
        "review_status",
    ]:
        if key not in candidate:
            errors.append(f"{path}: missing required field {key!r}")

    if candidate.get("review_status") not in VALID_STATUSES:
        errors.append(f"{path}: invalid review_status {candidate.get('review_status')!r}")

    methods = candidate.get("discovery_methods") or []
    if not methods or any(method not in VALID_METHODS for method in methods):
        errors.append(f"{path}: discovery_methods must only contain supported values")

    for key in ("relevance_score", "risk_score"):
        value = candidate.get(key)
        if not isinstance(value, (int, float)) or value < 0 or value > 1:
            errors.append(f"{path}: {key} must be between 0 and 1")

    if candidate.get("review_status") == "approved" and not candidate.get("review_notes"):
        errors.append(f"{path}: approved candidates must include review_notes")

    return errors


def iter_paths(paths: Iterable[str]) -> Iterable[Path]:
    for raw in paths:
        candidate = Path(raw)
        if candidate.is_dir():
            yield from sorted(candidate.rglob("*.json"))
        else:
            yield candidate


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate candidate source review records.")
    parser.add_argument("paths", nargs="+", help="Candidate record JSON file(s) or directories.")
    args = parser.parse_args()

    total_errors = 0
    checked = 0
    for path in iter_paths(args.paths):
        checked += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"ERROR {path}: could not read JSON: {exc}")
            total_errors += 1
            continue
        errors = validate_candidate_manifest(payload, path)
        for msg in errors:
            print(f"ERROR {msg}")
        if not errors:
            print(f"OK    {path}")
        total_errors += len(errors)

    print(f"SUMMARY candidates_checked={checked} errors={total_errors}")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
