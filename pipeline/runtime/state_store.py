from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .models import DEFAULT_DB_PATH, FrontierItem, JobDefinition, JobRun, utcnow_iso

CREATE_TABLES = [
    """
    CREATE TABLE IF NOT EXISTS jobs (
      job_id TEXT PRIMARY KEY,
      job_type TEXT NOT NULL,
      source_id TEXT,
      enabled INTEGER NOT NULL,
      schedule_json TEXT,
      depends_on_json TEXT,
      config_json TEXT,
      next_run_at TEXT,
      last_run_at TEXT,
      updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_runs (
      run_id TEXT PRIMARY KEY,
      job_id TEXT NOT NULL,
      job_type TEXT NOT NULL,
      source_id TEXT,
      status TEXT NOT NULL,
      trigger_mode TEXT NOT NULL,
      attempt INTEGER NOT NULL,
      dry_run INTEGER NOT NULL,
      resume_of TEXT,
      started_at TEXT NOT NULL,
      finished_at TEXT,
      summary_json TEXT,
      error_text TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS run_events (
      event_id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id TEXT NOT NULL,
      ts TEXT NOT NULL,
      level TEXT NOT NULL,
      event_type TEXT NOT NULL,
      message TEXT NOT NULL,
      payload_json TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS url_state (
      source_id TEXT NOT NULL,
      normalized_url TEXT NOT NULL,
      canonical_url TEXT,
      host TEXT NOT NULL,
      last_status TEXT,
      http_status INTEGER,
      content_hash TEXT,
      etag TEXT,
      page_title TEXT,
      quality_class TEXT,
      first_seen_at TEXT NOT NULL,
      last_seen_at TEXT NOT NULL,
      last_fetched_at TEXT,
      PRIMARY KEY (source_id, normalized_url)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS frontier (
      run_id TEXT NOT NULL,
      source_id TEXT NOT NULL,
      normalized_url TEXT NOT NULL,
      url TEXT NOT NULL,
      host TEXT NOT NULL,
      depth INTEGER NOT NULL,
      priority REAL NOT NULL,
      discovery_reason TEXT NOT NULL,
      discovered_from TEXT,
      status TEXT NOT NULL,
      retry_count INTEGER NOT NULL DEFAULT 0,
      last_error TEXT,
      updated_at TEXT NOT NULL,
      PRIMARY KEY (run_id, normalized_url)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS candidate_sources (
      candidate_source_id TEXT PRIMARY KEY,
      candidate_domain TEXT NOT NULL,
      seed_url TEXT NOT NULL,
      review_status TEXT NOT NULL,
      first_seen_at TEXT NOT NULL,
      last_seen_at TEXT NOT NULL,
      discovery_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS quarantine (
      quarantine_id TEXT PRIMARY KEY,
      run_id TEXT,
      stage TEXT NOT NULL,
      source_id TEXT,
      candidate_source_id TEXT,
      reason TEXT NOT NULL,
      artifact_path TEXT,
      payload_json TEXT,
      created_at TEXT NOT NULL
    )
    """,
]


class RuntimeStateStore:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            for statement in CREATE_TABLES:
                conn.execute(statement)
            conn.commit()

    def upsert_job(self, job: JobDefinition, next_run_at: str | None) -> None:
        payload = job.to_dict()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs(job_id, job_type, source_id, enabled, schedule_json, depends_on_json, config_json, next_run_at, last_run_at, updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(job_id) DO UPDATE SET
                  job_type=excluded.job_type,
                  source_id=excluded.source_id,
                  enabled=excluded.enabled,
                  schedule_json=excluded.schedule_json,
                  depends_on_json=excluded.depends_on_json,
                  config_json=excluded.config_json,
                  next_run_at=excluded.next_run_at,
                  updated_at=excluded.updated_at
                """,
                (
                    job.job_id,
                    job.job_type,
                    job.source_id,
                    1 if job.enabled else 0,
                    json.dumps(payload.get("schedule"), ensure_ascii=False),
                    json.dumps(payload.get("depends_on"), ensure_ascii=False),
                    json.dumps(payload.get("config"), ensure_ascii=False),
                    next_run_at,
                    None,
                    utcnow_iso(),
                ),
            )
            conn.commit()

    def get_job(self, job_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()

    def list_jobs(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM jobs ORDER BY job_id").fetchall()

    def list_due_jobs(self, now_iso: str) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM jobs WHERE enabled=1 AND next_run_at IS NOT NULL AND next_run_at <= ? ORDER BY next_run_at, job_id",
                (now_iso,),
            ).fetchall()

    def mark_job_scheduled(self, job_id: str, next_run_at: str | None, last_run_at: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET next_run_at=?, last_run_at=COALESCE(?, last_run_at), updated_at=? WHERE job_id=?",
                (next_run_at, last_run_at, utcnow_iso(), job_id),
            )
            conn.commit()

    def create_run(self, job_id: str, job_type: str, source_id: str | None, trigger_mode: str, attempt: int = 1, dry_run: bool = False, resume_of: str | None = None) -> JobRun:
        run = JobRun(
            run_id=f"run_{uuid.uuid4().hex[:16]}",
            job_id=job_id,
            job_type=job_type,
            source_id=source_id,
            status="running",
            trigger=trigger_mode,
            attempt=attempt,
            dry_run=dry_run,
            started_at=utcnow_iso(),
            resume_of=resume_of,
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO job_runs(run_id, job_id, job_type, source_id, status, trigger_mode, attempt, dry_run, resume_of, started_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (run.run_id, run.job_id, run.job_type, run.source_id, run.status, run.trigger, run.attempt, 1 if run.dry_run else 0, run.resume_of, run.started_at),
            )
            conn.commit()
        return run

    def finish_run(self, run_id: str, status: str, summary: dict[str, Any] | None = None, error_text: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE job_runs SET status=?, finished_at=?, summary_json=?, error_text=? WHERE run_id=?",
                (status, utcnow_iso(), json.dumps(summary or {}, ensure_ascii=False), error_text, run_id),
            )
            conn.commit()

    def latest_successful_run(self, job_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM job_runs WHERE job_id=? AND status='completed' ORDER BY started_at DESC LIMIT 1",
                (job_id,),
            ).fetchone()
    def get_run(self, run_id: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM job_runs WHERE run_id=?", (run_id,)).fetchone()

    def list_runs(self, limit: int = 25) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM job_runs ORDER BY started_at DESC LIMIT ?",
                (max(1, int(limit)),),
            ).fetchall()

    def quarantine_count(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM quarantine").fetchone()
            return int(row["n"]) if row else 0

    def record_event(self, run_id: str, level: str, event_type: str, message: str, payload: dict[str, Any] | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO run_events(run_id, ts, level, event_type, message, payload_json) VALUES(?,?,?,?,?,?)",
                (run_id, utcnow_iso(), level.upper(), event_type, message, json.dumps(payload or {}, ensure_ascii=False)),
            )
            conn.commit()

    def list_events(self, run_id: str) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM run_events WHERE run_id=? ORDER BY event_id", (run_id,)).fetchall()

    def get_url_state(self, source_id: str, normalized_url: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM url_state WHERE source_id=? AND normalized_url=?",
                (source_id, normalized_url),
            ).fetchone()

    def find_content_hash(self, source_id: str, content_hash: str) -> sqlite3.Row | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM url_state WHERE source_id=? AND content_hash=? LIMIT 1",
                (source_id, content_hash),
            ).fetchone()

    def upsert_url_state(self, *, source_id: str, normalized_url: str, canonical_url: str, host: str, last_status: str, http_status: int, content_hash: str | None, page_title: str | None, quality_class: str) -> None:
        existing = self.get_url_state(source_id, normalized_url)
        now = utcnow_iso()
        first_seen_at = existing["first_seen_at"] if existing else now
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO url_state(source_id, normalized_url, canonical_url, host, last_status, http_status, content_hash, page_title, quality_class, first_seen_at, last_seen_at, last_fetched_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(source_id, normalized_url) DO UPDATE SET
                  canonical_url=excluded.canonical_url,
                  host=excluded.host,
                  last_status=excluded.last_status,
                  http_status=excluded.http_status,
                  content_hash=excluded.content_hash,
                  page_title=excluded.page_title,
                  quality_class=excluded.quality_class,
                  last_seen_at=excluded.last_seen_at,
                  last_fetched_at=excluded.last_fetched_at
                """,
                (source_id, normalized_url, canonical_url, host, last_status, http_status, content_hash, page_title, quality_class, first_seen_at, now, now),
            )
            conn.commit()

    def enqueue_frontier_items(self, run_id: str, items: Iterable[FrontierItem]) -> None:
        with self._connect() as conn:
            for item in items:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO frontier(run_id, source_id, normalized_url, url, host, depth, priority, discovery_reason, discovered_from, status, updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (run_id, item.source_id, item.normalized_url, item.url, item.host, item.depth, item.priority, item.discovery_reason, item.discovered_from, "pending", utcnow_iso()),
                )
            conn.commit()

    def claim_frontier_items(self, run_id: str, limit: int = 1) -> list[sqlite3.Row]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM frontier WHERE run_id=? AND status='pending' ORDER BY priority DESC, depth ASC, normalized_url ASC LIMIT ?",
                (run_id, limit),
            ).fetchall()
            for row in rows:
                conn.execute(
                    "UPDATE frontier SET status='in_progress', updated_at=? WHERE run_id=? AND normalized_url=?",
                    (utcnow_iso(), run_id, row["normalized_url"]),
                )
            conn.commit()
            return rows

    def finish_frontier_item(self, run_id: str, normalized_url: str, status: str, last_error: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE frontier SET status=?, last_error=?, updated_at=? WHERE run_id=? AND normalized_url=?",
                (status, last_error, utcnow_iso(), run_id, normalized_url),
            )
            conn.commit()

    def pending_frontier_count(self, run_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM frontier WHERE run_id=? AND status='pending'", (run_id,)).fetchone()
            return int(row["n"]) if row else 0

    def upsert_candidate(self, candidate_id: str, domain: str, seed_url: str, review_status: str, discovery_payload: dict[str, Any]) -> None:
        now = utcnow_iso()
        with self._connect() as conn:
            existing = conn.execute("SELECT first_seen_at FROM candidate_sources WHERE candidate_source_id=?", (candidate_id,)).fetchone()
            first_seen = existing["first_seen_at"] if existing else now
            conn.execute(
                """
                INSERT INTO candidate_sources(candidate_source_id, candidate_domain, seed_url, review_status, first_seen_at, last_seen_at, discovery_json)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(candidate_source_id) DO UPDATE SET
                  candidate_domain=excluded.candidate_domain,
                  seed_url=excluded.seed_url,
                  review_status=excluded.review_status,
                  last_seen_at=excluded.last_seen_at,
                  discovery_json=excluded.discovery_json
                """,
                (candidate_id, domain, seed_url, review_status, first_seen, now, json.dumps(discovery_payload, ensure_ascii=False)),
            )
            conn.commit()

    def list_candidates(self) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute("SELECT * FROM candidate_sources ORDER BY last_seen_at DESC, candidate_source_id ASC").fetchall()

    def record_quarantine(self, *, run_id: str | None, stage: str, source_id: str | None, candidate_source_id: str | None, reason: str, artifact_path: str, payload: dict[str, Any]) -> str:
        quarantine_id = f"q_{uuid.uuid4().hex[:16]}"
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO quarantine(quarantine_id, run_id, stage, source_id, candidate_source_id, reason, artifact_path, payload_json, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (quarantine_id, run_id, stage, source_id, candidate_source_id, reason, artifact_path, json.dumps(payload, ensure_ascii=False), utcnow_iso()),
            )
            conn.commit()
        return quarantine_id
