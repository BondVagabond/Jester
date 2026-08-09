from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .crawler import run_crawl_once
from .models import DEFAULT_RUNTIME_ROOT, JobDefinition, JobRun, JobSchedule, utcnow_iso
from .state_store import RuntimeStateStore

JobHandler = Callable[[JobDefinition, JobRun, RuntimeStateStore, Path], dict[str, Any]]


def _parse_schedule(payload: dict | None) -> JobSchedule | None:
    if not payload:
        return None
    return JobSchedule(
        interval_minutes=int(payload.get("interval_minutes", 0)),
        max_retries=int(payload.get("max_retries", 3)),
        retry_backoff_seconds=int(payload.get("retry_backoff_seconds", 300)),
        backfill_hours=int(payload.get("backfill_hours", 0)),
        jitter_seconds=int(payload.get("jitter_seconds", 0)),
    )


def _next_run_iso(schedule: JobSchedule | None, base_time: datetime | None = None) -> str | None:
    if not schedule or schedule.interval_minutes <= 0:
        return None
    base_time = base_time or datetime.now(UTC)
    return (base_time + timedelta(minutes=schedule.interval_minutes)).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class JobRunner:
    def __init__(self, runtime_root: Path = DEFAULT_RUNTIME_ROOT, store: RuntimeStateStore | None = None):
        self.runtime_root = Path(runtime_root)
        self.store = store or RuntimeStateStore(self.runtime_root / "state" / "runtime.db")
        self.handlers: dict[str, JobHandler] = {
            "crawl.source": self._handle_crawl,
            "discover.source": self._handle_discovery,
        }

    def register_job(self, job: JobDefinition) -> None:
        self.store.upsert_job(job, next_run_at=_next_run_iso(job.schedule))

    def _job_from_row(self, row) -> JobDefinition:
        schedule_json = json.loads(row["schedule_json"]) if row["schedule_json"] else None
        depends_on_json = json.loads(row["depends_on_json"]) if row["depends_on_json"] else []
        config_json = json.loads(row["config_json"]) if row["config_json"] else {}
        return JobDefinition(
            job_id=row["job_id"],
            job_type=row["job_type"],
            source_id=row["source_id"],
            enabled=bool(row["enabled"]),
            schedule=_parse_schedule(schedule_json),
            depends_on=list(depends_on_json),
            config=dict(config_json),
        )

    def _dependencies_satisfied(self, job: JobDefinition) -> bool:
        return all(self.store.latest_successful_run(dep) is not None for dep in job.depends_on)

    def _handle_crawl(self, job: JobDefinition, run: JobRun, store: RuntimeStateStore, runtime_root: Path) -> dict[str, Any]:
        return run_crawl_once(
            source_id=job.source_id,
            runtime_root=runtime_root,
            store=store,
            dry_run=run.dry_run,
            job_id=job.job_id,
            job_config={**job.config, "enable_candidate_discovery": job.config.get("enable_candidate_discovery", True)},
            run=run,
        )

    def _handle_discovery(self, job: JobDefinition, run: JobRun, store: RuntimeStateStore, runtime_root: Path) -> dict[str, Any]:
        return run_crawl_once(
            source_id=job.source_id,
            runtime_root=runtime_root,
            store=store,
            dry_run=run.dry_run,
            job_id=job.job_id,
            job_config={**job.config, "discover_only": True, "enable_candidate_discovery": True},
            run=run,
        )

    def run_job(self, job_id: str, *, trigger: str = "manual", dry_run: bool = False) -> dict[str, Any]:
        row = self.store.get_job(job_id)
        if row is None:
            raise KeyError(f"Unknown job_id: {job_id}")
        job = self._job_from_row(row)
        if not self._dependencies_satisfied(job):
            raise RuntimeError(f"Job {job_id} is blocked by unsatisfied dependencies: {job.depends_on}")

        handler = self.handlers.get(job.job_type)
        if handler is None:
            raise KeyError(f"No handler registered for job_type={job.job_type!r}")

        latest_run = self.store.latest_successful_run(job.job_id)
        attempt = 1 if latest_run is None else int(latest_run["attempt"] or 1)
        run = self.store.create_run(job.job_id, job.job_type, job.source_id, trigger_mode=trigger, attempt=attempt, dry_run=dry_run)
        self.store.record_event(run.run_id, "INFO", "job_started", f"Starting job {job.job_id}", {"job_type": job.job_type, "source_id": job.source_id})
        try:
            summary = handler(job, run, self.store, self.runtime_root)
            self.store.finish_run(run.run_id, "completed", summary=summary)
            self.store.record_event(run.run_id, "INFO", "job_completed", f"Completed job {job.job_id}", summary)
            self.store.mark_job_scheduled(job.job_id, _next_run_iso(job.schedule), last_run_at=utcnow_iso())
            return summary
        except Exception as exc:
            self.store.finish_run(run.run_id, "failed", summary={}, error_text=str(exc))
            self.store.record_event(run.run_id, "ERROR", "job_failed", f"Job {job.job_id} failed", {"error": str(exc)})
            if job.schedule:
                retry_at = datetime.now(UTC) + timedelta(seconds=job.schedule.retry_backoff_seconds)
                self.store.mark_job_scheduled(job.job_id, retry_at.replace(microsecond=0).isoformat().replace("+00:00", "Z"), last_run_at=utcnow_iso())
            raise

    def run_due_jobs(self) -> int:
        ran = 0
        for row in self.store.list_due_jobs(utcnow_iso()):
            job = self._job_from_row(row)
            if not self._dependencies_satisfied(job):
                continue
            self.run_job(job.job_id, trigger="scheduled", dry_run=False)
            ran += 1
        return ran

    def worker_loop(self, *, poll_seconds: int = 30, once: bool = False) -> None:
        while True:
            self.run_due_jobs()
            if once:
                return
            asyncio.run(asyncio.sleep(poll_seconds))

    def backfill_job(self, job_id: str, *, hours: int, dry_run: bool = False) -> None:
        for _ in range(max(1, hours)):
            self.run_job(job_id, trigger="backfill", dry_run=dry_run)
