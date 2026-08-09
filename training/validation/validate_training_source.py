from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from training.validation.common import SourceManifest, load_json_file, normalize_validation_error


def collect_manifest_paths(targets: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for target in targets:
        if not target.exists():
            raise ValueError(f"{target}: path does not exist.")
        if target.is_dir():
            paths.extend(sorted(path for path in target.rglob("*.json") if path.is_file()))
        elif target.suffix.lower() == ".json":
            paths.append(target)
    if not paths:
        raise ValueError("No source manifest JSON files found.")
    return sorted(dict.fromkeys(paths))


def load_source_manifest(path: Path) -> SourceManifest:
    payload = load_json_file(path)
    try:
        return SourceManifest.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(normalize_validation_error(str(path), exc)) from exc


def validate_source_manifests(targets: list[Path]) -> list[tuple[Path, SourceManifest]]:
    manifests: list[tuple[Path, SourceManifest]] = []
    errors: list[str] = []

    for path in collect_manifest_paths(targets):
        try:
            manifests.append((path, load_source_manifest(path)))
        except ValueError as exc:
            errors.append(str(exc))

    source_id_index: dict[str, tuple[Path, SourceManifest]] = {}
    hash_index: dict[str, tuple[Path, SourceManifest]] = {}

    for path, manifest in manifests:
        existing_by_id = source_id_index.get(manifest.source_id)
        if existing_by_id is not None:
            previous_path, previous_manifest = existing_by_id
            if previous_manifest.content_hash != manifest.content_hash:
                errors.append(
                    "Conflicting source_id "
                    f"{manifest.source_id}: {previous_path} uses {previous_manifest.content_hash}, "
                    f"but {path} uses {manifest.content_hash}."
                )
            else:
                errors.append(f"Duplicate manifest for source_id {manifest.source_id}: {previous_path} and {path}.")
        else:
            source_id_index[manifest.source_id] = (path, manifest)

        existing_by_hash = hash_index.get(manifest.content_hash)
        if existing_by_hash is not None:
            previous_path, previous_manifest = existing_by_hash
            if previous_manifest.source_id != manifest.source_id:
                errors.append(
                    "Duplicate content_hash "
                    f"{manifest.content_hash}: {previous_manifest.source_id} ({previous_path}) and "
                    f"{manifest.source_id} ({path})."
                )
        else:
            hash_index[manifest.content_hash] = (path, manifest)

    if errors:
        raise ValueError("\n".join(errors))
    return manifests


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate Jester training source manifests.")
    parser.add_argument("targets", nargs="+", type=Path, help="Source manifest files or directories.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        manifests = validate_source_manifests(args.targets)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"Validated {len(manifests)} source manifest(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
