from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .models import DEFAULT_CANDIDATE_SOURCE_DIR, DEFAULT_DATA_ROOT, DEFAULT_RUNTIME_ROOT
from .stage_writer import ensure_runtime_layout


def _copy_tree_contents(src: Path, dst: Path) -> dict[str, int]:
    copied_files = 0
    skipped_files = 0
    copied_bytes = 0
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        target = dst / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            skipped_files += 1
            continue
        shutil.copy2(path, target)
        copied_files += 1
        copied_bytes += path.stat().st_size
    return {
        "copied_files": copied_files,
        "skipped_files": skipped_files,
        "copied_bytes": copied_bytes,
    }


def setup_data_root(
    *,
    data_root: Path | str = DEFAULT_DATA_ROOT,
    runtime_root: Path | str = DEFAULT_RUNTIME_ROOT,
    migrate_from: Path | str | None = None,
) -> dict[str, Any]:
    resolved_data_root = Path(data_root)
    resolved_runtime_root = Path(runtime_root)
    resolved_candidate_dir = DEFAULT_CANDIDATE_SOURCE_DIR
    resolved_data_root.mkdir(parents=True, exist_ok=True)
    resolved_candidate_dir.mkdir(parents=True, exist_ok=True)
    ensure_runtime_layout(resolved_runtime_root)

    migration_summary: dict[str, Any] = {
        "migration_source": None,
        "migration_performed": False,
        "copied_files": 0,
        "skipped_files": 0,
        "copied_bytes": 0,
    }

    if migrate_from:
        source = Path(migrate_from)
        migration_summary["migration_source"] = str(source)
        if source.exists() and source.resolve() != resolved_runtime_root.resolve():
            counts = _copy_tree_contents(source, resolved_runtime_root)
            migration_summary.update(counts)
            migration_summary["migration_performed"] = counts["copied_files"] > 0

    return {
        "data_root": str(resolved_data_root),
        "runtime_root": str(resolved_runtime_root),
        "candidate_source_dir": str(resolved_candidate_dir),
        **migration_summary,
    }