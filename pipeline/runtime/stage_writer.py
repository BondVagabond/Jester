from __future__ import annotations

import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .models import DEFAULT_RUNTIME_ROOT, JobRun


def ensure_runtime_layout(runtime_root: Path = DEFAULT_RUNTIME_ROOT) -> None:
    for rel in [
        "runs",
        "state",
        "logs",
        "staged/discovery_candidate",
        "staged/raw",
        "staged/extracted",
        "staged/cleaned",
        "staged/sectionized",
        "staged/chunked",
        "staged/indexed",
        "quarantine",
        "raw_html",
        "raw_binary",
        "reports",
    ]:
        (runtime_root / rel).mkdir(parents=True, exist_ok=True)


def stage_file(runtime_root: Path, stage: str, source_key: str, run_id: str, job_id: str) -> Path:
    path = runtime_root / "staged" / stage / source_key
    path.mkdir(parents=True, exist_ok=True)
    return path / f"{run_id}__{job_id}.jsonl"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def atomic_write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    return path


def write_records(runtime_root: Path, stage: str, source_key: str, run: JobRun, records: list[dict[str, Any]]) -> Path:
    path = stage_file(runtime_root, stage, source_key, run.run_id, run.job_id)
    existing = load_jsonl(path)
    existing.extend(records)
    return atomic_write_jsonl(path, existing)


def write_html_blob(runtime_root: Path, source_id: str, content_hash: str, html: str) -> Path:
    safe_hash = content_hash.replace(":", "_")
    out = runtime_root / "raw_html" / source_id / f"{safe_hash}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(html, encoding="utf-8")
    os.replace(tmp, out)
    return out


def write_binary_blob(runtime_root: Path, source_id: str, content_hash: str, suffix: str, data: bytes) -> Path:
    safe_hash = content_hash.replace(":", "_")
    normalized_suffix = suffix if str(suffix).startswith(".") else f".{suffix}"
    out = runtime_root / "raw_binary" / source_id / f"{safe_hash}{normalized_suffix.lower()}"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, out)
    return out


def write_run_manifest(runtime_root: Path, run: JobRun, payload: dict[str, Any]) -> Path:
    run_dir = runtime_root / "runs" / run.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "run_manifest.json"
    tmp = path.with_suffix(path.suffix + ".tmp")
    data = {**run.to_dict(), **payload}
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def write_report(runtime_root: Path, run: JobRun, name: str, payload: dict[str, Any]) -> Path:
    run_dir = runtime_root / "runs" / run.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / name
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path