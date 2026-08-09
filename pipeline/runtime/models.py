from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PIPELINE_VERSION = "runtime-activation-v1"
DEFAULT_DATA_ROOT = Path(os.environ.get("JESTER_DATA_ROOT") or r"F:\JesterData")
DEFAULT_RUNTIME_ROOT = Path(os.environ.get("JESTER_RUNTIME_ROOT") or (DEFAULT_DATA_ROOT / "runtime"))
DEFAULT_CANDIDATE_SOURCE_DIR = Path(os.environ.get("JESTER_CANDIDATE_SOURCE_DIR") or (DEFAULT_DATA_ROOT / "candidate_sources"))
DEFAULT_DB_PATH = DEFAULT_RUNTIME_ROOT / "state" / "runtime.db"


def utcnow_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(slots=True)
class JobSchedule:
    interval_minutes: int
    max_retries: int = 3
    retry_backoff_seconds: int = 300
    backfill_hours: int = 0
    jitter_seconds: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "interval_minutes": self.interval_minutes,
            "max_retries": self.max_retries,
            "retry_backoff_seconds": self.retry_backoff_seconds,
            "backfill_hours": self.backfill_hours,
            "jitter_seconds": self.jitter_seconds,
        }


@dataclass(slots=True)
class JobDefinition:
    job_id: str
    job_type: str
    source_id: str | None = None
    enabled: bool = True
    schedule: JobSchedule | None = None
    depends_on: list[str] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "source_id": self.source_id,
            "enabled": self.enabled,
            "schedule": self.schedule.to_dict() if self.schedule else None,
            "depends_on": list(self.depends_on),
            "config": dict(self.config),
        }


@dataclass(slots=True)
class JobRun:
    run_id: str
    job_id: str
    job_type: str
    source_id: str | None
    status: str
    trigger: str
    attempt: int
    dry_run: bool
    started_at: str
    finished_at: str | None = None
    resume_of: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "job_id": self.job_id,
            "job_type": self.job_type,
            "source_id": self.source_id,
            "status": self.status,
            "trigger": self.trigger,
            "attempt": self.attempt,
            "dry_run": self.dry_run,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "resume_of": self.resume_of,
        }


@dataclass(slots=True)
class HostPolicy:
    allowed_domains: list[str]
    fail_closed_on_robots: bool
    respect_crawl_delay: bool
    crawl_delay_seconds: float
    requests_per_minute: int
    max_parallel_requests: int
    daily_url_budget: int
    user_agent: str
    allowed_schemes: list[str] = field(default_factory=lambda: ["https", "http"])
    allowed_path_prefixes: list[str] = field(default_factory=list)
    blocked_url_patterns: list[str] = field(default_factory=list)
    robots_override_allowlist: list[str] = field(default_factory=list)

    @property
    def minimum_delay_seconds(self) -> float:
        rpm_delay = 60.0 / max(self.requests_per_minute, 1)
        return max(float(self.crawl_delay_seconds or 0.0), rpm_delay)


@dataclass(slots=True)
class ApprovedSource:
    source_id: str
    manifest_path: Path
    manifest: dict[str, Any]
    host_policy: HostPolicy


@dataclass(slots=True)
class FrontierItem:
    source_id: str
    url: str
    normalized_url: str
    host: str
    depth: int
    priority: float
    discovery_reason: str
    discovered_from: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "url": self.url,
            "normalized_url": self.normalized_url,
            "host": self.host,
            "depth": self.depth,
            "priority": self.priority,
            "discovery_reason": self.discovery_reason,
            "discovered_from": self.discovered_from,
        }


@dataclass(slots=True)
class CandidateSource:
    candidate_source_id: str
    candidate_domain: str
    seed_url: str
    first_seen_at: str
    last_seen_at: str
    discovery_methods: list[str]
    relevance_score: float
    risk_score: float
    review_status: str
    robots_accessible: bool | None = None
    apparent_owner: str | None = None
    apparent_license: str | None = None
    apparent_content_type: str | None = None
    discovered_from_source_id: str | None = None
    discovery_evidence: dict[str, Any] = field(default_factory=dict)
    review_notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_version": 1,
            "candidate_source_id": self.candidate_source_id,
            "candidate_domain": self.candidate_domain,
            "seed_url": self.seed_url,
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "discovery_methods": list(self.discovery_methods),
            "relevance_score": round(float(self.relevance_score), 4),
            "risk_score": round(float(self.risk_score), 4),
            "review_status": self.review_status,
            "robots_accessible": self.robots_accessible,
            "apparent_owner": self.apparent_owner,
            "apparent_license": self.apparent_license,
            "apparent_content_type": self.apparent_content_type,
            "discovered_from_source_id": self.discovered_from_source_id,
            "discovery_evidence": dict(self.discovery_evidence),
            "review_notes": self.review_notes,
        }