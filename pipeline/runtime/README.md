# Runtime Activation Sprint

This package is the canonical runtime for approved discovery and ingestion.

Key properties:

- repo-native internal job runner backed by SQLite state
- manifest-backed approved crawling and artifact ingestion
- separate candidate discovery workflow for unapproved domains
- persistent frontier and URL state for resumable crawls
- fail-closed robots and policy behavior
- canonical staged outputs under the runtime root
- raw HTML under `raw_html/` and raw binary artifacts under `raw_binary/`
- quarantine artifacts under `quarantine/`
- run manifests and summaries under `runs/`
- local control-room GUI for source selection, crawl actions, and run visibility

Default storage:

- `JESTER_DATA_ROOT` defaults to `F:\JesterData`
- `JESTER_RUNTIME_ROOT` defaults to `F:\JesterData\runtime`
- CLI `--runtime-root` still overrides both

Main entrypoints:

```powershell
py -3 -m Scraping.runtime.cli setup-data-root
py -3 -m Scraping.runtime.cli worker
py -3 -m Scraping.runtime.cli gui --port 8766
```

Common commands:

```powershell
py -3 -m Scraping.runtime.cli register-job --job-id crawl.reports --job-type crawl.source --source-id src_reports --interval-minutes 360
py -3 -m Scraping.runtime.cli run-job crawl.reports
py -3 -m Scraping.runtime.cli crawl-source --source-id src_reports --enable-candidate-discovery
py -3 -m Scraping.runtime.cli crawl-source --source-id wotc_srd_5_1_cc_by_4_0 --ocr --pdf-max-pages 50
py -3 -m Scraping.runtime.cli discover-source --source-id src_reports
py -3 -m Scraping.runtime.cli gui --host 127.0.0.1 --port 8766
```

PDF/runtime notes:

- PDF manifests use `artifact_path` for local files or `artifact_urls` for approved remote PDFs.
- Remote PDF collection still respects the manifest host policy and fail-closed robots behavior, with optional explicit `robots_override_allowlist` exceptions for reviewed artifact URLs.
- PDFs are staged through the same `raw -> extracted -> cleaned -> sectionized -> chunked` pipeline as HTML.
- OCR is optional and exposed through `crawl-source --ocr --ocr-dpi ...` or job config fields `ocr`, `ocr_dpi`, and `pdf_max_pages`.
- `discover.source` is for HTML discovery only and is not valid for PDF manifests.

GUI notes:

- The GUI is a no-build local web app served directly by Python.
- It shows approved sources, recent runs, run events, runtime-root status, and crawl/discovery actions.
- PDF sources expose OCR controls in the same surface.

Runtime separation rules:

- `discover.source` may create candidate review records, but it must not auto-approve them.
- `crawl.source` only runs for approved manifests.
- training and retrieval exports must read validated staged chunk outputs, not ad hoc raw script outputs.