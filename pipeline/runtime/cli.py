from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .crawler import run_crawl_once
from .job_runner import JobRunner
from .models import DEFAULT_DATA_ROOT, DEFAULT_RUNTIME_ROOT, JobDefinition, JobSchedule
from .state_store import RuntimeStateStore


def _load_config(args) -> dict[str, Any]:
    if args.config_file:
        return json.loads(Path(args.config_file).read_text(encoding="utf-8"))
    if args.config_json:
        return json.loads(args.config_json)
    return {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Jester runtime job runner, managed crawler, and local GUI.")
    parser.add_argument("--runtime-root", default=str(DEFAULT_RUNTIME_ROOT), help="Runtime root directory.")
    sub = parser.add_subparsers(dest="command", required=True)

    register = sub.add_parser("register-job", help="Register or update a scheduled job.")
    register.add_argument("--job-id", required=True)
    register.add_argument("--job-type", required=True, choices=["crawl.source", "discover.source"])
    register.add_argument("--source-id", required=True)
    register.add_argument("--interval-minutes", type=int, required=True)
    register.add_argument("--depends-on", nargs="*", default=[])
    register.add_argument("--config-json", default=None)
    register.add_argument("--config-file", default=None)

    run_job = sub.add_parser("run-job", help="Run a registered job immediately.")
    run_job.add_argument("job_id")
    run_job.add_argument("--dry-run", action="store_true")

    worker = sub.add_parser("worker", help="Run the internal scheduler worker loop.")
    worker.add_argument("--once", action="store_true")
    worker.add_argument("--poll-seconds", type=int, default=30)

    backfill = sub.add_parser("backfill", help="Run backfill executions for a registered job.")
    backfill.add_argument("job_id")
    backfill.add_argument("--hours", type=int, required=True)
    backfill.add_argument("--dry-run", action="store_true")

    crawl = sub.add_parser("crawl-source", help="Run a one-off approved crawl directly.")
    crawl.add_argument("--source-id", required=True)
    crawl.add_argument("--dry-run", action="store_true")
    crawl.add_argument("--max-pages", type=int, default=None)
    crawl.add_argument("--enable-candidate-discovery", action="store_true")
    crawl.add_argument("--ocr", action="store_true", help="Enable OCR fallback for PDF sources.")
    crawl.add_argument("--ocr-dpi", type=int, default=300, help="OCR rasterization DPI for PDF sources.")
    crawl.add_argument("--pdf-max-pages", type=int, default=None, help="Optional per-PDF page limit for extraction.")

    discover = sub.add_parser("discover-source", help="Run a one-off discovery-only job for an approved source.")
    discover.add_argument("--source-id", required=True)
    discover.add_argument("--dry-run", action="store_true")
    discover.add_argument("--max-pages", type=int, default=None)

    setup = sub.add_parser("setup-data-root", help="Create the external data root and optionally copy existing runtime data into it.")
    setup.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT), help="Top-level Jester data directory.")
    setup.add_argument("--copy-from", default=str(Path("out/runtime")), help="Optional existing runtime folder to copy into the external runtime root.")

    gui = sub.add_parser("gui", help="Launch the local control-room GUI.")
    gui.add_argument("--host", default="127.0.0.1")
    gui.add_argument("--port", type=int, default=8766)

    sub.add_parser("list-jobs", help="List registered jobs.")
    sub.add_parser("list-candidates", help="List candidate sources in the state store.")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    runtime_root = Path(args.runtime_root)

    if args.command == "setup-data-root":
        from .data_root_setup import setup_data_root

        result = setup_data_root(data_root=Path(args.data_root), runtime_root=runtime_root, migrate_from=Path(args.copy_from) if args.copy_from else None)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "gui":
        from .gui_server import launch_gui_server

        launch_gui_server(runtime_root=runtime_root, host=args.host, port=args.port)
        return 0

    store = RuntimeStateStore(runtime_root / "state" / "runtime.db")
    runner = JobRunner(runtime_root=runtime_root, store=store)

    if args.command == "register-job":
        config = _load_config(args)
        job = JobDefinition(
            job_id=args.job_id,
            job_type=args.job_type,
            source_id=args.source_id,
            schedule=JobSchedule(interval_minutes=args.interval_minutes),
            depends_on=args.depends_on,
            config=config,
        )
        runner.register_job(job)
        print(json.dumps({"job_id": job.job_id, "status": "registered"}, ensure_ascii=False))
        return 0

    if args.command == "run-job":
        summary = runner.run_job(args.job_id, trigger="manual", dry_run=args.dry_run)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if args.command == "worker":
        runner.worker_loop(poll_seconds=args.poll_seconds, once=args.once)
        return 0

    if args.command == "backfill":
        runner.backfill_job(args.job_id, hours=args.hours, dry_run=args.dry_run)
        return 0

    if args.command == "crawl-source":
        config = {
            "max_pages": args.max_pages,
            "enable_candidate_discovery": args.enable_candidate_discovery,
            "ocr": args.ocr,
            "ocr_dpi": args.ocr_dpi,
            "pdf_max_pages": args.pdf_max_pages,
        }
        summary = run_crawl_once(source_id=args.source_id, runtime_root=runtime_root, store=store, dry_run=args.dry_run, job_id="crawl.manual", job_type="crawl.source", job_config=config)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if args.command == "discover-source":
        config = {"max_pages": args.max_pages, "discover_only": True, "enable_candidate_discovery": True}
        summary = run_crawl_once(source_id=args.source_id, runtime_root=runtime_root, store=store, dry_run=args.dry_run, job_id="discover.manual", job_type="discover.source", job_config=config)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if args.command == "list-jobs":
        rows = [dict(row) for row in store.list_jobs()]
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    if args.command == "list-candidates":
        rows = []
        for row in store.list_candidates():
            payload = dict(row)
            if payload.get("discovery_json"):
                payload["discovery_json"] = json.loads(payload["discovery_json"])
            rows.append(payload)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    parser.error(f"Unhandled command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())