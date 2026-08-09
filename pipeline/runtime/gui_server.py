from __future__ import annotations

import json
import mimetypes
import threading
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from training.validation.validate_source_manifest import manifest_allows_collection, validate_manifest

from .crawler import run_crawl_once
from .data_root_setup import setup_data_root
from .manifests import APPROVED_SOURCE_DIR, load_manifest
from .models import DEFAULT_DATA_ROOT, DEFAULT_RUNTIME_ROOT, JobRun
from .state_store import RuntimeStateStore

GUI_ASSET_DIR = Path(__file__).with_name("gui")
RUN_WARNING_KEYS = (
    ("fetch_failed", "fetch failed"),
    ("pdf_fetch_failed", "pdf fetch failed"),
    ("rejected_robots", "robots blocked"),
    ("pdf_rejected_robots", "pdf robots blocked"),
    ("rejected_scope", "out of scope"),
    ("pdf_rejected_scope", "pdf out of scope"),
    ("quarantined_pages", "quarantined"),
    ("pdf_artifacts_quarantined", "pdf quarantined"),
    ("pdf_artifacts_failed", "pdf artifact failed"),
)
RUN_ACTIVITY_KEYS = (
    ("kept_pages", "pages kept"),
    ("candidate_records", "candidates"),
    ("unchanged_pages", "unchanged"),
    ("already_known", "already known"),
    ("duplicate_pages", "duplicates"),
    ("rejected_low_value", "low value"),
)


@dataclass(slots=True)
class UITask:
    task_id: str
    action: str
    source_id: str
    run_id: str
    status: str
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    error: str = ""
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "action": self.action,
            "source_id": self.source_id,
            "run_id": self.run_id,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "summary": dict(self.summary),
        }


def _pluralize(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or f"{singular}s")


def _summary_phrase(summary: dict[str, Any], key: str, label: str) -> str | None:
    raw = summary.get(key)
    if raw in (None, ""):
        return None
    try:
        count = int(raw)
    except (TypeError, ValueError):
        return None
    if count <= 0:
        return None
    return f"{count} {label}"


def summarize_run_result(summary: dict[str, Any] | None, error_text: str | None, status: str | None) -> dict[str, Any]:
    summary = dict(summary or {})
    emitted_chunks = int(summary.get("emitted_chunks") or summary.get("chunk_files") or 0)
    error_value = str(error_text or "").strip()
    if error_value:
        return {
            "result_tone": "error",
            "result_message": error_value,
            "warning_count": 0,
            "emitted_chunks": emitted_chunks,
        }

    warning_phrases = [phrase for key, label in RUN_WARNING_KEYS if (phrase := _summary_phrase(summary, key, label))]
    activity_phrases = [phrase for key, label in RUN_ACTIVITY_KEYS if (phrase := _summary_phrase(summary, key, label))]

    if status == "running":
        tone = "info"
        message = "Run in progress."
    elif warning_phrases and emitted_chunks > 0:
        tone = "warning"
        message = f"{emitted_chunks} {_pluralize(emitted_chunks, 'chunk')} emitted; {', '.join(warning_phrases[:2])}."
    elif warning_phrases:
        tone = "warning"
        message = f"No chunks emitted; {', '.join(warning_phrases[:3])}."
    elif emitted_chunks > 0:
        tone = "success"
        message = f"{emitted_chunks} {_pluralize(emitted_chunks, 'chunk')} emitted"
        if activity_phrases:
            message += f"; {activity_phrases[0]}"
        message += "."
    elif activity_phrases:
        tone = "info"
        message = f"No new chunks; {', '.join(activity_phrases[:2])}."
    else:
        tone = "info"
        message = "No chunks emitted."

    return {
        "result_tone": tone,
        "result_message": message,
        "warning_count": len(warning_phrases),
        "emitted_chunks": emitted_chunks,
    }


def _count_jsonl_records(root: Path) -> int:
    total = 0
    if not root.exists():
        return 0
    for path in root.rglob("*.jsonl"):
        try:
            with path.open("r", encoding="utf-8") as handle:
                total += sum(1 for line in handle if line.strip())
        except Exception:
            continue
    return total


class RuntimeGUIApp:
    def __init__(self, runtime_root: Path = DEFAULT_RUNTIME_ROOT):
        self.runtime_root = Path(runtime_root)
        setup_data_root(
            data_root=self.runtime_root.parent if self.runtime_root.parent != self.runtime_root else DEFAULT_DATA_ROOT,
            runtime_root=self.runtime_root,
        )
        self.store = RuntimeStateStore(self.runtime_root / "state" / "runtime.db")
        self._tasks: dict[str, UITask] = {}
        self._lock = threading.Lock()

    def list_sources(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for path in sorted(APPROVED_SOURCE_DIR.glob("*.json")):
            manifest = load_manifest(path)
            errors, warnings = validate_manifest(manifest, path)
            collectable, collection_errors = manifest_allows_collection(manifest)
            items.append(
                {
                    "source_id": manifest.get("source_id"),
                    "source_name": manifest.get("source_name"),
                    "source_type": manifest.get("source_type"),
                    "source_family": manifest.get("source_family"),
                    "license": manifest.get("license"),
                    "eligibility_class": manifest.get("eligibility_class"),
                    "status": manifest.get("status"),
                    "review_status": manifest.get("review_status"),
                    "owner": manifest.get("owner"),
                    "seed_count": len(manifest.get("seed_urls") or []),
                    "artifact_count": len(manifest.get("artifact_urls") or []) + (1 if manifest.get("artifact_path") else 0),
                    "scope_notes": str(manifest.get("scope_notes") or ""),
                    "notes": str(manifest.get("notes") or ""),
                    "collectable": collectable,
                    "validation_errors": errors,
                    "validation_warnings": warnings,
                    "collection_errors": collection_errors,
                    "manifest_path": str(path),
                }
            )
        return items

    def list_runs(self, limit: int = 30) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for row in self.store.list_runs(limit=limit):
            payload = dict(row)
            payload["dry_run"] = bool(payload.get("dry_run"))
            payload["summary_json"] = json.loads(payload.get("summary_json") or "{}")
            payload.update(summarize_run_result(payload["summary_json"], payload.get("error_text"), payload.get("status")))
            items.append(payload)
        return items

    def get_run_events(self, run_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for row in self.store.list_events(run_id):
            payload = dict(row)
            payload["payload_json"] = json.loads(payload.get("payload_json") or "{}")
            items.append(payload)
        return items

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._lock:
            return [task.to_dict() for task in sorted(self._tasks.values(), key=lambda item: item.created_at, reverse=True)]

    def summary(self) -> dict[str, Any]:
        runs = self.list_runs(limit=200)
        chunk_root = self.runtime_root / "staged" / "chunked"
        return {
            "data_root": str(self.runtime_root.parent),
            "runtime_root": str(self.runtime_root),
            "source_count": len(self.list_sources()),
            "completed_runs": sum(1 for run in runs if run.get("status") == "completed"),
            "failed_runs": sum(1 for run in runs if run.get("status") == "failed"),
            "running_runs": sum(1 for run in runs if run.get("status") == "running"),
            "quarantine_count": self.store.quarantine_count(),
            "raw_html_files": len(list((self.runtime_root / "raw_html").rglob("*.html"))) if (self.runtime_root / "raw_html").exists() else 0,
            "raw_binary_files": len([path for path in (self.runtime_root / "raw_binary").rglob("*") if path.is_file()]) if (self.runtime_root / "raw_binary").exists() else 0,
            "chunk_files": len(list(chunk_root.rglob("*.jsonl"))) if chunk_root.exists() else 0,
            "chunk_records": _count_jsonl_records(chunk_root),
        }

    def start_task(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        source_id = str(payload.get("source_id") or "").strip()
        if not source_id:
            raise ValueError("source_id is required")

        source_lookup = {item["source_id"]: item for item in self.list_sources()}
        source_manifest = source_lookup.get(source_id)
        if source_manifest is None:
            raise ValueError(f"Unknown source_id: {source_id}")
        if action == "discover" and source_manifest.get("source_type") == "pdf":
            raise ValueError("discover is not supported for PDF manifests")

        dry_run = bool(payload.get("dry_run", False))
        max_pages = payload.get("max_pages")
        max_pages = None if max_pages in ("", None) else int(max_pages)
        pdf_max_pages = payload.get("pdf_max_pages")
        pdf_max_pages = None if pdf_max_pages in ("", None) else int(pdf_max_pages)

        config = {
            "max_pages": max_pages,
            "enable_candidate_discovery": bool(payload.get("enable_candidate_discovery", False)),
            "ocr": bool(payload.get("ocr", False)),
            "ocr_dpi": int(payload.get("ocr_dpi") or 300),
            "pdf_max_pages": pdf_max_pages,
        }
        if action == "discover":
            config["discover_only"] = True
            config["enable_candidate_discovery"] = True

        run = self.store.create_run(
            job_id=f"{action}.gui",
            job_type="discover.source" if action == "discover" else "crawl.source",
            source_id=source_id,
            trigger_mode="gui",
            dry_run=dry_run,
        )
        self.store.record_event(run.run_id, "INFO", "gui_task_created", f"GUI queued {action} for {source_id}", {"payload": payload})

        task = UITask(
            task_id=f"task_{uuid.uuid4().hex[:12]}",
            action=action,
            source_id=source_id,
            run_id=run.run_id,
            status="queued",
            created_at=run.started_at,
        )
        with self._lock:
            self._tasks[task.task_id] = task

        thread = threading.Thread(
            target=self._run_task,
            args=(task.task_id, run.run_id, source_id, action, dry_run, config),
            daemon=True,
        )
        thread.start()
        return task.to_dict()

    def _job_run_from_row(self, run_id: str) -> JobRun | None:
        row = self.store.get_run(run_id)
        if row is None:
            return None
        return JobRun(
            run_id=row["run_id"],
            job_id=row["job_id"],
            job_type=row["job_type"],
            source_id=row["source_id"],
            status=row["status"],
            trigger=row["trigger_mode"],
            attempt=int(row["attempt"] or 1),
            dry_run=bool(row["dry_run"]),
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            resume_of=row["resume_of"],
        )

    def _run_task(self, task_id: str, run_id: str, source_id: str, action: str, dry_run: bool, config: dict[str, Any]) -> None:
        with self._lock:
            task = self._tasks[task_id]
            task.status = "running"
            task.started_at = task.created_at

        run = self._job_run_from_row(run_id)
        if run is None:
            error_text = f"Missing run row for {run_id}"
            with self._lock:
                task = self._tasks[task_id]
                task.status = "failed"
                task.finished_at = task.created_at
                task.error = error_text
            return

        try:
            summary = run_crawl_once(
                source_id=source_id,
                runtime_root=self.runtime_root,
                store=self.store,
                trigger="gui",
                dry_run=dry_run,
                job_id=run.job_id,
                job_type=run.job_type,
                job_config=config,
                run=run,
            )
            result = summarize_run_result(summary, "", "completed")
            self.store.finish_run(run.run_id, "completed", summary=summary)
            event_level = "WARN" if result["result_tone"] == "warning" else "INFO"
            event_type = "gui_task_completed_with_warnings" if result["result_tone"] == "warning" else "gui_task_completed"
            event_message = f"GUI completed {action} for {source_id}"
            if result["result_tone"] == "warning":
                event_message += " with warnings"
            event_payload = dict(summary)
            event_payload["result_message"] = result["result_message"]
            self.store.record_event(run.run_id, event_level, event_type, event_message, event_payload)
            finished = self.store.get_run(run.run_id)
            with self._lock:
                task = self._tasks[task_id]
                task.status = "completed"
                task.finished_at = finished["finished_at"] if finished else task.created_at
                task.summary = summary
                task.error = result["result_message"] if result["result_tone"] == "warning" else ""
        except Exception as exc:
            self.store.finish_run(run.run_id, "failed", summary={}, error_text=str(exc))
            self.store.record_event(run.run_id, "ERROR", "gui_task_failed", f"GUI failed {action} for {source_id}", {"error": str(exc)})
            finished = self.store.get_run(run.run_id)
            with self._lock:
                task = self._tasks[task_id]
                task.status = "failed"
                task.finished_at = finished["finished_at"] if finished else task.created_at
                task.error = str(exc)


class RuntimeGUIHandler(BaseHTTPRequestHandler):
    server_version = "JesterRuntimeGUI/1.0"

    @property
    def app(self) -> RuntimeGUIApp:
        return self.server.app  # type: ignore[attr-defined]

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._serve_asset("index.html")
            return
        if parsed.path.startswith("/assets/"):
            self._serve_asset(parsed.path.removeprefix("/assets/"))
            return
        if parsed.path == "/api/config":
            self._send_json({"data_root": str(self.app.runtime_root.parent), "runtime_root": str(self.app.runtime_root)})
            return
        if parsed.path == "/api/sources":
            self._send_json(self.app.list_sources())
            return
        if parsed.path == "/api/summary":
            self._send_json(self.app.summary())
            return
        if parsed.path == "/api/tasks":
            self._send_json(self.app.list_tasks())
            return
        if parsed.path == "/api/runs":
            query = parse_qs(parsed.query)
            limit = int((query.get("limit") or ["30"])[0])
            self._send_json(self.app.list_runs(limit=limit))
            return
        if parsed.path.startswith("/api/runs/") and parsed.path.endswith("/events"):
            run_id = parsed.path.split("/")[3]
            self._send_json(self.app.get_run_events(run_id))
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/actions/crawl":
            payload = self._read_json_body()
            try:
                task = self.app.start_task("crawl", payload)
                self._send_json(task, status=HTTPStatus.ACCEPTED)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        if parsed.path == "/api/actions/discover":
            payload = self._read_json_body()
            try:
                task = self.app.start_task("discover", payload)
                self._send_json(task, status=HTTPStatus.ACCEPTED)
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def log_message(self, format: str, *args) -> None:
        return

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_asset(self, relative_name: str) -> None:
        root = GUI_ASSET_DIR.resolve()
        path = (root / relative_name).resolve()
        if not path.exists() or not str(path).startswith(str(root)):
            self.send_error(HTTPStatus.NOT_FOUND, "Asset not found")
            return
        content_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class RuntimeGUIHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address, request_handler_class, app: RuntimeGUIApp):
        super().__init__(server_address, request_handler_class)
        self.app = app


def launch_gui_server(*, runtime_root: Path = DEFAULT_RUNTIME_ROOT, host: str = "127.0.0.1", port: int = 8766) -> None:
    app = RuntimeGUIApp(runtime_root=runtime_root)
    server = RuntimeGUIHTTPServer((host, port), RuntimeGUIHandler, app)
    print(json.dumps({"status": "serving", "url": f"http://{host}:{port}", "runtime_root": str(runtime_root)}, ensure_ascii=False))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
