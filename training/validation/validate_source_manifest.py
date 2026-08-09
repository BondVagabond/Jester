#!/usr/bin/env python3
"""Validate Jester source manifests with compliance-focused business rules."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

TRAINING_SAFE_LICENSES = {
    "owned",
    "license-grants-training",
    "cc0-1.0",
    "cc-by-4.0",
    "cc-by-sa-4.0",
    "public-domain",
    "user-consent",
}
TRAINING_SAFE_RIGHTS = {
    "owned-by-jester",
    "explicit-training-license",
    "open-license",
    "public-domain",
    "user-opt-in",
}
RETRIEVAL_SAFE_LICENSES = TRAINING_SAFE_LICENSES | {"license-grants-retrieval", "ogl-1.0a"}
RETRIEVAL_SAFE_RIGHTS = TRAINING_SAFE_RIGHTS | {"explicit-retrieval-license", "internal-use-only"}
WEB_SOURCE_TYPES = {"website", "api", "html"}
ARTIFACT_SOURCE_TYPES = {"pdf", "text", "jsonl", "internal_doc", "licensed_dataset"}
CONSENT_SOURCE_TYPES = {"user_upload", "campaign_log"}
LICENSE_URL_REQUIRED = {
    "license-grants-training",
    "license-grants-retrieval",
    "cc0-1.0",
    "cc-by-4.0",
    "cc-by-sa-4.0",
    "ogl-1.0a",
    "public-domain",
}
ATTRIBUTION_REQUIRED_LICENSES = {
    "license-grants-training",
    "license-grants-retrieval",
    "cc-by-4.0",
    "cc-by-sa-4.0",
    "ogl-1.0a",
}
SHARE_ALIKE_LICENSES = {"cc-by-sa-4.0"}


def derived_class(manifest: dict[str, Any]) -> str:
    if manifest.get("allowed_for_training") and manifest.get("allowed_for_rag"):
        return "training_and_retrieval"
    if (not manifest.get("allowed_for_training")) and manifest.get("allowed_for_rag"):
        return "retrieval_only"
    if (not manifest.get("allowed_for_training")) and (not manifest.get("allowed_for_rag")):
        return "neither"
    return "invalid"


def _validate_remote_policy(path: Path, manifest: dict[str, Any], errors: list[str]) -> None:
    host_policy = manifest.get("host_policy") or {}
    if not manifest.get("allowed_domains"):
        errors.append(f"{path}: remote-fetch sources must declare allowed_domains")
    if not host_policy.get("fail_closed_on_robots"):
        errors.append(f"{path}: remote-fetch sources must fail closed on robots errors")
    if not host_policy.get("respect_crawl_delay"):
        errors.append(f"{path}: remote-fetch sources must respect crawl-delay")
    if host_policy.get("crawl_delay_seconds") is None:
        errors.append(f"{path}: remote-fetch sources must declare crawl_delay_seconds")
    if not host_policy.get("requests_per_minute"):
        errors.append(f"{path}: remote-fetch sources must set requests_per_minute")
    if not host_policy.get("max_parallel_requests"):
        errors.append(f"{path}: remote-fetch sources must set max_parallel_requests")
    if not host_policy.get("daily_url_budget"):
        errors.append(f"{path}: remote-fetch sources must set daily_url_budget")
    user_agent = host_policy.get("user_agent", "")
    if "example.org" in user_agent or not user_agent.strip():
        errors.append(f"{path}: remote-fetch sources must declare a real contactable user-agent")
    if not manifest.get("removal_path"):
        errors.append(f"{path}: remote-fetch sources must declare removal_path")


def validate_manifest(manifest: dict[str, Any], path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    declared_class = manifest.get("eligibility_class")
    actual_class = derived_class(manifest)
    if declared_class != actual_class:
        errors.append(f"{path}: eligibility_class={declared_class!r} does not match derived class {actual_class!r}")

    if manifest.get("review_status") not in {"approved", "pending_review", "rejected", "quarantined"}:
        errors.append(f"{path}: review_status must be one of approved, pending_review, rejected, quarantined")

    license_name = manifest.get("license")
    rights_basis = manifest.get("rights_basis")
    if license_name in (None, "", "unknown") or rights_basis in (None, "", "unknown"):
        if declared_class != "neither":
            errors.append(f"{path}: missing or unknown rights must resolve to eligibility_class='neither'")
        if manifest.get("status") != "quarantined":
            errors.append(f"{path}: missing or unknown rights require status='quarantined'")

    if manifest.get("attribution_required") not in {True, False}:
        errors.append(f"{path}: attribution_required must be explicitly true or false")
    if manifest.get("share_alike_required") not in {True, False}:
        errors.append(f"{path}: share_alike_required must be explicitly true or false")

    if license_name in LICENSE_URL_REQUIRED and not str(manifest.get("license_url") or "").strip():
        errors.append(f"{path}: open or public-domain sources must declare license_url")

    if license_name in ATTRIBUTION_REQUIRED_LICENSES and not manifest.get("attribution_required"):
        errors.append(f"{path}: {license_name!r} must set attribution_required=true")
    if manifest.get("attribution_required") and not str(manifest.get("attribution_text") or "").strip():
        errors.append(f"{path}: attribution_required=true must include attribution_text")
    if license_name in SHARE_ALIKE_LICENSES and not manifest.get("share_alike_required"):
        errors.append(f"{path}: {license_name!r} must set share_alike_required=true")

    artifact_path = str(manifest.get("artifact_path") or "").strip()
    artifact_urls = list(manifest.get("artifact_urls") or [])
    if manifest.get("source_type") in ARTIFACT_SOURCE_TYPES:
        if not artifact_path and not artifact_urls:
            errors.append(f"{path}: {manifest.get('source_type')!r} sources must declare artifact_path or artifact_urls")
        if artifact_path and artifact_urls:
            errors.append(f"{path}: declare either artifact_path or artifact_urls, not both")
        if artifact_urls:
            _validate_remote_policy(path, manifest, errors)

    if manifest.get("status") == "quarantined" and not manifest.get("quarantine_reason"):
        errors.append(f"{path}: quarantined sources must include quarantine_reason")

    if manifest.get("removal_required"):
        if declared_class != "neither":
            errors.append(f"{path}: removal_required=true must force eligibility_class='neither'")
        if manifest.get("status") != "quarantined":
            errors.append(f"{path}: removal_required=true requires status='quarantined'")

    if declared_class == "training_and_retrieval":
        if license_name not in TRAINING_SAFE_LICENSES or rights_basis not in TRAINING_SAFE_RIGHTS:
            errors.append(f"{path}: training_and_retrieval requires a training-safe license/rights combination")
        if manifest.get("provenance_status") != "complete":
            errors.append(f"{path}: training_and_retrieval requires provenance_status='complete'")

    if manifest.get("source_family") in {"dnd_official", "dnd_fan"} and manifest.get("allowed_for_training"):
        errors.append(f"{path}: DND proprietary or fan sources are not training-safe by default")

    if manifest.get("source_type") in CONSENT_SOURCE_TYPES and manifest.get("allowed_for_training"):
        consent = manifest.get("consent") or {}
        if not consent.get("explicit_opt_in"):
            errors.append(f"{path}: training-eligible user content requires consent.explicit_opt_in=true")
        if not consent.get("granted_by") or not consent.get("granted_at"):
            errors.append(f"{path}: training-eligible user content requires granted_by and granted_at")

    if manifest.get("source_type") in WEB_SOURCE_TYPES:
        if not manifest.get("seed_urls"):
            errors.append(f"{path}: web sources must declare seed_urls")
        _validate_remote_policy(path, manifest, errors)

    if declared_class == "retrieval_only":
        if license_name not in RETRIEVAL_SAFE_LICENSES and license_name not in {"all-rights-reserved", "contract-restricted"}:
            warnings.append(f"{path}: retrieval_only source has an unusual license value {license_name!r}")
        if rights_basis not in RETRIEVAL_SAFE_RIGHTS and rights_basis not in {"contract-restricted"}:
            warnings.append(f"{path}: retrieval_only source has an unusual rights_basis {rights_basis!r}")

    return errors, warnings


def manifest_allows_collection(manifest: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if manifest.get("review_status") != "approved":
        errors.append("review_status must be 'approved' for runtime collection")
    if manifest.get("status") != "active":
        errors.append("status must be 'active' for runtime collection")
    if manifest.get("removal_required"):
        errors.append("removal_required sources cannot be collected")
    if manifest.get("rights_basis") in (None, "", "unknown"):
        errors.append("rights_basis is missing or unknown")
    if manifest.get("license") in (None, "", "unknown"):
        errors.append("license is missing or unknown")
    return (len(errors) == 0), errors


def iter_manifest_paths(paths: Iterable[str]) -> Iterable[Path]:
    for raw in paths:
        candidate = Path(raw)
        if candidate.is_dir():
            yield from sorted(candidate.rglob("*.json"))
        else:
            yield candidate


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate source manifests for legal safety and provenance completeness.")
    parser.add_argument("paths", nargs="+", help="Manifest JSON file(s) or directory/directories.")
    args = parser.parse_args()

    manifest_paths = list(iter_manifest_paths(args.paths))
    total_errors = 0
    total_warnings = 0

    for path in manifest_paths:
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"ERROR {path}: could not read JSON: {exc}")
            total_errors += 1
            continue

        errors, warnings = validate_manifest(manifest, path)
        for msg in errors:
            print(f"ERROR {msg}")
        for msg in warnings:
            print(f"WARN  {msg}")
        if not errors and not warnings:
            print(f"OK    {path}")

        total_errors += len(errors)
        total_warnings += len(warnings)

    print(f"SUMMARY manifests_checked={len(manifest_paths)} errors={total_errors} warnings={total_warnings}")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())