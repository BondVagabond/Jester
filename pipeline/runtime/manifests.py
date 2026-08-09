from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from training.validation.validate_source_manifest import manifest_allows_collection, validate_manifest

from .models import DEFAULT_CANDIDATE_SOURCE_DIR, ApprovedSource, HostPolicy

APPROVED_SOURCE_DIR = Path("Training/sources/approved")
CANDIDATE_SOURCE_DIR = DEFAULT_CANDIDATE_SOURCE_DIR


def host_policy_from_manifest(manifest: dict[str, Any]) -> HostPolicy:
    host_policy = manifest.get("host_policy") or {}
    return HostPolicy(
        allowed_domains=list(manifest.get("allowed_domains") or []),
        fail_closed_on_robots=bool(host_policy.get("fail_closed_on_robots", True)),
        respect_crawl_delay=bool(host_policy.get("respect_crawl_delay", True)),
        crawl_delay_seconds=float(host_policy.get("crawl_delay_seconds") or 0.0),
        requests_per_minute=int(host_policy.get("requests_per_minute") or 1),
        max_parallel_requests=int(host_policy.get("max_parallel_requests") or 1),
        daily_url_budget=int(host_policy.get("daily_url_budget") or 1),
        user_agent=str(host_policy.get("user_agent") or ""),
        allowed_schemes=list(host_policy.get("allowed_schemes") or ["https", "http"]),
        allowed_path_prefixes=list(host_policy.get("allowed_path_prefixes") or []),
        blocked_url_patterns=list(host_policy.get("blocked_url_patterns") or []),
        robots_override_allowlist=list(host_policy.get("robots_override_allowlist") or []),
    )


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_approved_source(*, source_id: str | None = None, manifest_path: str | Path | None = None) -> ApprovedSource:
    if source_id is None and manifest_path is None:
        raise ValueError("source_id or manifest_path is required")
    path = Path(manifest_path) if manifest_path else APPROVED_SOURCE_DIR / f"{source_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Source manifest not found: {path}")

    manifest = load_manifest(path)
    schema_errors, _warnings = validate_manifest(manifest, path)
    if schema_errors:
        raise ValueError("Invalid source manifest: " + " | ".join(schema_errors))

    allowed, collection_errors = manifest_allows_collection(manifest)
    if not allowed:
        raise ValueError("Source manifest is not collectable: " + " | ".join(collection_errors))

    return ApprovedSource(
        source_id=str(manifest["source_id"]),
        manifest_path=path,
        manifest=manifest,
        host_policy=host_policy_from_manifest(manifest),
    )


def iter_approved_sources() -> Iterable[ApprovedSource]:
    for path in sorted(APPROVED_SOURCE_DIR.glob("*.json")):
        try:
            yield load_approved_source(manifest_path=path)
        except Exception:
            continue