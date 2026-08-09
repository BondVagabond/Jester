from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from training.validation.common import (
    PolicyCategory,
    ReviewStatus,
    SourceManifest,
    TrainingRecord,
    iter_record_payloads,
    normalize_validation_error,
)
from training.validation.validate_training_source import validate_source_manifests


def load_training_records(paths: list[Path]) -> list[tuple[str, TrainingRecord]]:
    records: list[tuple[str, TrainingRecord]] = []
    errors: list[str] = []

    for path in paths:
        if not path.exists():
            errors.append(f"{path}: path does not exist.")
            continue
        for location, payload in iter_record_payloads(path):
            try:
                records.append((location, TrainingRecord.model_validate(payload)))
            except ValidationError as exc:
                errors.append(normalize_validation_error(location, exc))

    seen_record_ids: dict[str, str] = {}
    for location, record in records:
        previous_location = seen_record_ids.get(record.record_id)
        if previous_location is not None:
            errors.append(f"Duplicate record_id {record.record_id}: {previous_location} and {location}.")
        else:
            seen_record_ids[record.record_id] = location

    if errors:
        raise ValueError("\n".join(errors))
    return records


def validate_record_eligibility(source_targets: list[Path], record_paths: list[Path]) -> list[tuple[str, TrainingRecord]]:
    source_manifests = validate_source_manifests(source_targets)
    source_index: dict[str, SourceManifest] = {
        manifest.source_id: manifest for _, manifest in source_manifests
    }
    records = load_training_records(record_paths)

    errors: list[str] = []
    for location, record in records:
        source = source_index.get(record.source_id)
        if source is None:
            errors.append(f"{location}: unknown source_id {record.source_id}.")
            continue

        if record.allowed_for_training and not source.allowed_for_training:
            errors.append(
                f"{location}: source {record.source_id} is not approved for training "
                f"(category={source.policy_category})."
            )

        if record.allowed_for_rag and not source.allowed_for_rag:
            errors.append(
                f"{location}: source {record.source_id} is not approved for RAG "
                f"(category={source.policy_category})."
            )

        if source.policy_category in {PolicyCategory.REFERENCE_ONLY, PolicyCategory.BLOCKED} and (
            record.allowed_for_training or record.allowed_for_rag
        ):
            errors.append(
                f"{location}: source {record.source_id} is {source.policy_category} and cannot back eligible records."
            )

        if record.allowed_for_training and source.review_status is not ReviewStatus.APPROVED:
            errors.append(
                f"{location}: training record requires source {record.source_id} to have review_status=approved."
            )

        if source.review_status in {ReviewStatus.QUARANTINED, ReviewStatus.REMOVED} and (
            record.allowed_for_training or record.allowed_for_rag
        ):
            errors.append(
                f"{location}: source {record.source_id} is {source.review_status} and must not produce eligible records."
            )

    if errors:
        raise ValueError("\n".join(errors))
    return records


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate training-record eligibility against source manifests.")
    parser.add_argument("source_targets", nargs="+", type=Path, help="Source manifest files or directories.")
    parser.add_argument(
        "--records",
        nargs="+",
        required=True,
        type=Path,
        help="Training record JSON or JSONL files to validate.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        records = validate_record_eligibility(args.source_targets, args.records)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Validated {len(records)} training record(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
