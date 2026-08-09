from __future__ import annotations

from pathlib import Path
from typing import Any

from .models import DEFAULT_RUNTIME_ROOT, JobRun
from .stage_writer import atomic_write_jsonl, write_report
from .state_store import RuntimeStateStore


def quarantine_records(
    *,
    runtime_root: Path = DEFAULT_RUNTIME_ROOT,
    store: RuntimeStateStore,
    run: JobRun,
    stage: str,
    reason: str,
    records: list[dict[str, Any]],
    source_id: str | None = None,
    candidate_source_id: str | None = None,
    errors: list[str] | None = None,
) -> Path:
    key = candidate_source_id or source_id or "unknown"
    out = runtime_root / "quarantine" / key / stage / f"{run.run_id}__{reason}.jsonl"
    artifact_path = atomic_write_jsonl(out, records)
    payload = {"errors": errors or [], "record_count": len(records)}
    store.record_quarantine(
        run_id=run.run_id,
        stage=stage,
        source_id=source_id,
        candidate_source_id=candidate_source_id,
        reason=reason,
        artifact_path=str(artifact_path),
        payload=payload,
    )
    write_report(runtime_root, run, f"{stage}__{key}__{reason}.rejection.json", payload)
    return artifact_path
