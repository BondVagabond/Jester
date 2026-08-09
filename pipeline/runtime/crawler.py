from __future__ import annotations

import asyncio
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib import robotparser
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup

try:
    import trafilatura
except Exception:
    trafilatura = None

from .discovery import DiscoveryEngine
from .manifests import load_approved_source
from .models import ApprovedSource, FrontierItem, JobRun
from .pipeline import process_html_document, process_pdf_document, process_text_document
from .quarantine import quarantine_records
from .stage_writer import (
    DEFAULT_RUNTIME_ROOT,
    ensure_runtime_layout,
    write_binary_blob,
    write_html_blob,
    write_records,
    write_report,
    write_run_manifest,
)
from .state_store import RuntimeStateStore
from .url_tools import (
    domain_allowed,
    host_from_url,
    is_probably_low_value_url,
    normalize_url,
    path_allowed,
    quick_duplicate_key,
    score_page,
    soft_404_signal,
    text_content_hash,
)

LIKELY_MARKERS = ["play", "session", "transcript", "report", "episode", "recap", "actual play", "campaign"]
TEXT_ARTIFACT_SUFFIXES = {".txt", ".md", ".markdown", ".text"}
JSON_ARTIFACT_SUFFIXES = {".jsonl", ".json"}


def fandom_extractor(html: str) -> tuple[str, str]:
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    main = soup.select_one(".mw-parser-output")
    if not main:
        return title, ""
    for selector in ["table", "script", "style", ".navbox", ".toc"]:
        for element in main.select(selector):
            element.decompose()
    return title, main.get_text("\n", strip=True)


def generic_extractor(html: str) -> tuple[str, str, str]:
    soup = BeautifulSoup(html, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else ""
    if trafilatura is not None:
        try:
            text = trafilatura.extract(html, include_comments=False, include_tables=False) or ""
            if len(text.split()) > 50:
                return title, text, "trafilatura"
        except Exception:
            pass
    article = soup.find("article") or soup.find("main") or soup.find("div", class_="content")
    if article:
        for element in article.select("script, style, nav, header, footer, aside"):
            element.decompose()
        text = article.get_text("\n", strip=True)
        if len(text.split()) > 50:
            return title, text, "bs4:article"
    body = soup.find("body")
    text = body.get_text("\n", strip=True) if body else ""
    return title, text, "bs4:body"


class ManagedCrawler:
    def __init__(
        self,
        *,
        source: ApprovedSource,
        store: RuntimeStateStore,
        runtime_root: Path = DEFAULT_RUNTIME_ROOT,
        discovery_engine: DiscoveryEngine | None = None,
        job_config: dict[str, object] | None = None,
    ):
        self.source = source
        self.store = store
        self.runtime_root = Path(runtime_root)
        self.discovery_engine = discovery_engine or DiscoveryEngine(store)
        self.job_config = job_config or {}
        self.robots: dict[str, robotparser.RobotFileParser] = {}
        self.host_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.host_next_allowed: dict[str, float] = defaultdict(float)
        self.summary: dict[str, int] = defaultdict(int)
        self.force_recrawl = bool(self.job_config.get("force_recrawl", False))
        self.discovery_only = bool(self.job_config.get("discover_only", False))
        self.enable_candidate_discovery = bool(self.job_config.get("enable_candidate_discovery", False))
        self.min_recrawl_hours = int(self.job_config.get("min_recrawl_hours", 24))
        self.max_chunk_chars = int(self.job_config.get("max_chunk_chars", 1200))
        self.max_candidates = int(self.job_config.get("max_candidates", 10))
        self.pdf_ocr = bool(self.job_config.get("ocr", False))
        self.pdf_ocr_dpi = int(self.job_config.get("ocr_dpi", 300))
        self.pdf_max_pages = self.job_config.get("pdf_max_pages")
        if self.pdf_max_pages is not None:
            self.pdf_max_pages = int(self.pdf_max_pages)

    def _url_in_scope(self, url: str) -> bool:
        host = host_from_url(url)
        if not domain_allowed(host, self.source.host_policy.allowed_domains):
            return False
        return path_allowed(
            url,
            allowed_path_prefixes=self.source.host_policy.allowed_path_prefixes,
            blocked_url_patterns=self.source.host_policy.blocked_url_patterns,
        )

    def _robots_override_applies(self, url: str) -> bool:
        normalized_url = normalize_url(url)
        parsed = urlparse(normalized_url)
        path = parsed.path or "/"
        for raw in self.source.host_policy.robots_override_allowlist:
            entry = str(raw or "").strip()
            if not entry:
                continue
            if entry.startswith("http://") or entry.startswith("https://"):
                normalized_entry = normalize_url(entry)
                if normalized_url == normalized_entry:
                    return True
                continue
            prefix = entry if entry == "/" else entry.rstrip("/")
            if prefix == "/":
                return True
            if path == prefix or path.startswith(prefix + "/"):
                return True
        return False

    async def _load_robots(self, session: aiohttp.ClientSession, url: str) -> robotparser.RobotFileParser:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin in self.robots:
            return self.robots[origin]
        rp = robotparser.RobotFileParser()
        rp.set_url(origin + "/robots.txt")
        try:
            async with session.get(rp.url) as response:
                if response.status != 200 or "text" not in response.headers.get("content-type", ""):
                    raise RuntimeError(f"robots fetch failed with status={response.status}")
                rp.parse((await response.text()).splitlines())
        except Exception as exc:
            if self._robots_override_applies(url):
                rp.parse(["User-agent: *", "Allow: /"])
                self.robots[origin] = rp
                self.summary["robots_override_used"] += 1
                return rp
            raise RuntimeError(f"fail-closed robots error for {origin}: {exc}") from exc
        self.robots[origin] = rp
        return rp

    async def _respect_host_policy(self, host: str) -> None:
        async with self.host_locks[host]:
            now = asyncio.get_running_loop().time()
            wait_for = self.host_next_allowed[host] - now
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            self.host_next_allowed[host] = asyncio.get_running_loop().time() + self.source.host_policy.minimum_delay_seconds

    async def _fetch(self, session: aiohttp.ClientSession, url: str) -> tuple[tuple[str, str, int] | None, str]:
        host = host_from_url(url)
        retries = 3
        last_error = "fetch failed"
        for attempt in range(1, retries + 1):
            await self._respect_host_policy(host)
            try:
                async with session.get(url, allow_redirects=True) as response:
                    if response.status == 429:
                        retry_after = response.headers.get("Retry-After")
                        delay = float(retry_after) if retry_after and retry_after.isdigit() else self.source.host_policy.minimum_delay_seconds * (attempt + 1)
                        last_error = f"http_status=429 retry_after={retry_after or 'none'}"
                        await asyncio.sleep(delay)
                        continue
                    if 500 <= response.status < 600 and attempt < retries:
                        last_error = f"http_status={response.status}"
                        await asyncio.sleep(self.source.host_policy.minimum_delay_seconds * (attempt + 1))
                        continue
                    if response.status != 200:
                        return None, f"http_status={response.status}"
                    content_type = response.headers.get("content-type", "")
                    if "text/html" not in content_type.lower():
                        return None, f"unsupported_content_type={content_type or 'missing'}"
                    html = await response.text(errors="ignore")
                    return (str(response.url), html, response.status), ""
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt == retries:
                    return None, last_error
                await asyncio.sleep(self.source.host_policy.minimum_delay_seconds * attempt)
        return None, last_error

    async def _fetch_binary(self, session: aiohttp.ClientSession, url: str) -> tuple[tuple[str, bytes, int, str] | None, str]:
        host = host_from_url(url)
        retries = 3
        last_error = "binary fetch failed"
        for attempt in range(1, retries + 1):
            await self._respect_host_policy(host)
            try:
                async with session.get(url, allow_redirects=True) as response:
                    if response.status == 429:
                        retry_after = response.headers.get("Retry-After")
                        delay = float(retry_after) if retry_after and retry_after.isdigit() else self.source.host_policy.minimum_delay_seconds * (attempt + 1)
                        last_error = f"http_status=429 retry_after={retry_after or 'none'}"
                        await asyncio.sleep(delay)
                        continue
                    if 500 <= response.status < 600 and attempt < retries:
                        last_error = f"http_status={response.status}"
                        await asyncio.sleep(self.source.host_policy.minimum_delay_seconds * (attempt + 1))
                        continue
                    if response.status != 200:
                        return None, f"http_status={response.status}"
                    final_url = str(response.url)
                    content_type = response.headers.get("content-type", "")
                    is_pdf = "pdf" in content_type.lower() or final_url.lower().endswith(".pdf") or url.lower().endswith(".pdf")
                    if not is_pdf and "application/octet-stream" not in content_type.lower():
                        return None, f"unsupported_content_type={content_type or 'missing'}"
                    payload = await response.read()
                    return (final_url, payload, response.status, content_type), ""
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt == retries:
                    return None, last_error
                await asyncio.sleep(self.source.host_policy.minimum_delay_seconds * attempt)
        return None, last_error

    def _extract_main_text(self, url: str, html: str) -> tuple[str, str, str]:
        host = host_from_url(url)
        if host.endswith("fandom.com"):
            title, text = fandom_extractor(html)
            return title, text, "fandom"
        title, text, extractor = generic_extractor(html)
        return title, text, extractor

    def _extract_links(self, base_url: str, html: str, base_depth: int) -> list[FrontierItem]:
        soup = BeautifulSoup(html, "lxml")
        items: list[FrontierItem] = []
        seen = set()
        for anchor in soup.find_all("a", href=True):
            normalized = normalize_url(anchor["href"], base_url=base_url)
            if normalized in seen or not self._url_in_scope(normalized):
                continue
            if is_probably_low_value_url(normalized):
                continue
            seen.add(normalized)
            host = host_from_url(normalized)
            link_text = anchor.get_text(" ", strip=True)
            priority = score_page(normalized, link_text, link_text, depth=base_depth + 1, discovery_reason="internal_link")
            items.append(
                FrontierItem(
                    source_id=self.source.source_id,
                    url=normalized,
                    normalized_url=normalized,
                    host=host,
                    depth=base_depth + 1,
                    priority=priority,
                    discovery_reason="internal_link",
                    discovered_from=base_url,
                )
            )
        return items

    def _page_is_low_value(self, url: str, title: str, text: str) -> bool:
        if is_probably_low_value_url(url):
            return True
        if soft_404_signal(title, text):
            return True
        if len(text.split()) < 120:
            return True
        lowered = f"{title}\n{text[:600]}".lower()
        if not any(marker in lowered for marker in LIKELY_MARKERS):
            return False
        return False

    def _write_pipeline_result(self, run: JobRun, pipeline_result: dict[str, Any]) -> None:
        if self.discovery_only or run.dry_run:
            return
        for stage in ["raw", "extracted", "cleaned", "sectionized", "chunked"]:
            write_records(self.runtime_root, stage, self.source.source_id, run, pipeline_result[stage])

    def _handle_validation_failure(self, run: JobRun, records: list[dict[str, Any]], errors: list[str]) -> None:
        quarantine_records(
            runtime_root=self.runtime_root,
            store=self.store,
            run=run,
            stage="chunked",
            reason="validation_failure",
            records=records,
            source_id=self.source.source_id,
            errors=errors,
        )

    def _planned_binary_blob_path(self, content_hash: str, suffix: str) -> Path:
        safe_hash = content_hash.replace(":", "_")
        normalized_suffix = suffix if str(suffix).startswith(".") else f".{suffix}"
        return self.runtime_root / "raw_binary" / self.source.source_id / f"{safe_hash}{normalized_suffix.lower()}"

    def _resolve_local_artifact_path(self, artifact_path: str) -> Path:
        path = Path(artifact_path)
        if not path.is_absolute():
            path = (self.source.manifest_path.parent / path).resolve()
        return path

    def _binary_hash(self, data: bytes) -> str:
        return "sha256:" + hashlib.sha256(data).hexdigest()

    def _process_local_pdf_artifact(self, run: JobRun, artifact_path: str) -> None:
        path = self._resolve_local_artifact_path(artifact_path)
        try:
            pdf_bytes = path.read_bytes()
        except Exception as exc:
            self.summary["pdf_artifacts_failed"] += 1
            self.summary["pdf_local_read_failed"] += 1
            self.store.record_event(run.run_id, "ERROR", "pdf_local_read_failed", f"Failed to read PDF artifact {path}", {"error": str(exc)})
            return

        raw_hash = self._binary_hash(pdf_bytes)
        raw_path = str(path)
        if not run.dry_run:
            raw_path = str(write_binary_blob(self.runtime_root, self.source.source_id, raw_hash, ".pdf", pdf_bytes))

        pipeline_result = process_pdf_document(
            source=self.source,
            run=run,
            source_ref=str(path),
            pdf_bytes=pdf_bytes,
            raw_pdf_path=raw_path,
            title=path.stem,
            original_filename=path.name,
            http_status=None,
            content_type="application/pdf",
            acquisition_method="local_path",
            max_chunk_chars=self.max_chunk_chars,
            do_ocr=self.pdf_ocr,
            ocr_dpi=self.pdf_ocr_dpi,
            max_pdf_pages=self.pdf_max_pages,
        )

        if pipeline_result["validation_errors"]:
            if not run.dry_run:
                self._handle_validation_failure(run, pipeline_result["chunked"], pipeline_result["validation_errors"])
            self.summary["pdf_artifacts_quarantined"] += 1
            return

        self._write_pipeline_result(run, pipeline_result)
        self.summary["pdf_artifacts_completed"] += 1
        self.summary["emitted_chunks"] += len(pipeline_result["chunked"])

    def _iter_local_artifact_files(self, artifact_path: str) -> list[Path]:
        path = self._resolve_local_artifact_path(artifact_path)
        if path.is_dir():
            files = [candidate for candidate in sorted(path.rglob("*")) if candidate.is_file()]
            return files
        return [path]

    @staticmethod
    def _coerce_json_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (int, float, bool)):
            return str(value)
        if isinstance(value, list):
            parts = [ManagedCrawler._coerce_json_text(item) for item in value]
            return "\n".join(part for part in parts if part)
        if isinstance(value, dict):
            parts = []
            for key, item in value.items():
                rendered = ManagedCrawler._coerce_json_text(item)
                if rendered:
                    parts.append(f"{key}: {rendered}")
            return "\n".join(parts)
        return ""

    def _extract_json_document(self, payload: dict[str, Any], *, fallback_title: str, source_ref: str) -> dict[str, Any] | None:
        title = ""
        for key in ("title", "name", "heading", "full_name", "id"):
            candidate = self._coerce_json_text(payload.get(key))
            if candidate:
                title = candidate
                break
        title = title or fallback_title

        body_parts: list[str] = []
        for key in ("text", "page_content", "content", "desc", "description", "body", "markdown", "rules", "summary", "traits", "skills", "page"):
            rendered = self._coerce_json_text(payload.get(key))
            if rendered:
                body_parts.append(rendered)

        if not body_parts:
            for key, value in payload.items():
                if key in {"title", "name", "heading", "full_name", "id"}:
                    continue
                rendered = self._coerce_json_text(value)
                if len(rendered) >= 80:
                    body_parts.append(rendered)

        body = "\n\n".join(part for part in body_parts if part).strip()
        if not body:
            return None

        return {
            "title": title,
            "text": body,
            "source_ref": source_ref,
            "document_metadata": {"keys": sorted(payload.keys())},
        }

    def _process_local_text_artifact(self, run: JobRun, path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            self.summary["artifact_files_failed"] += 1
            self.summary["artifact_read_failed"] += 1
            self.store.record_event(run.run_id, "ERROR", "artifact_read_failed", f"Failed to read text artifact {path}", {"error": str(exc)})
            return

        pipeline_result = process_text_document(
            source=self.source,
            run=run,
            source_ref=str(path),
            text=text,
            title=path.stem,
            original_filename=path.name,
            acquisition_method="local_path",
            content_type="text/markdown" if path.suffix.lower() in {".md", ".markdown"} else "text/plain",
            max_chunk_chars=self.max_chunk_chars,
        )

        if pipeline_result["validation_errors"]:
            if not run.dry_run:
                self._handle_validation_failure(run, pipeline_result["chunked"], pipeline_result["validation_errors"])
            self.summary["artifact_documents_quarantined"] += 1
            return

        self._write_pipeline_result(run, pipeline_result)
        self.summary["artifact_documents_completed"] += 1
        self.summary["artifact_files_completed"] += 1
        self.summary["emitted_chunks"] += len(pipeline_result["chunked"])

    def _process_local_json_artifact(self, run: JobRun, path: Path) -> None:
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            self.summary["artifact_files_failed"] += 1
            self.summary["artifact_read_failed"] += 1
            self.store.record_event(run.run_id, "ERROR", "artifact_read_failed", f"Failed to read structured artifact {path}", {"error": str(exc)})
            return

        payloads: list[dict[str, Any]] = []
        try:
            if path.suffix.lower() == ".jsonl":
                for line in raw.splitlines():
                    stripped = line.strip()
                    if not stripped:
                        continue
                    item = json.loads(stripped)
                    if isinstance(item, dict):
                        payloads.append(item)
            else:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    payloads = [item for item in parsed if isinstance(item, dict)]
                elif isinstance(parsed, dict):
                    payloads = [parsed]
        except Exception as exc:
            self.summary["artifact_files_failed"] += 1
            self.summary["artifact_parse_failed"] += 1
            self.store.record_event(run.run_id, "ERROR", "artifact_parse_failed", f"Failed to parse structured artifact {path}", {"error": str(exc)})
            return

        if not payloads:
            self.summary["artifact_files_failed"] += 1
            self.summary["artifact_parse_failed"] += 1
            self.store.record_event(run.run_id, "WARN", "artifact_parse_empty", f"No structured records found in {path}", {})
            return

        emitted_from_file = 0
        completed_from_file = 0
        quarantined_from_file = 0
        for index, payload in enumerate(payloads, 1):
            document = self._extract_json_document(payload, fallback_title=f"{path.stem}-{index:04d}", source_ref=f"{path}#{index}")
            if document is None:
                continue
            pipeline_result = process_text_document(
                source=self.source,
                run=run,
                source_ref=str(document["source_ref"]),
                text=document["text"],
                title=document["title"],
                original_filename=path.name,
                acquisition_method="local_json_record",
                content_type="application/jsonl" if path.suffix.lower() == ".jsonl" else "application/json",
                max_chunk_chars=self.max_chunk_chars,
                document_metadata=document["document_metadata"],
            )
            if pipeline_result["validation_errors"]:
                if not run.dry_run:
                    self._handle_validation_failure(run, pipeline_result["chunked"], pipeline_result["validation_errors"])
                quarantined_from_file += 1
                continue

            self._write_pipeline_result(run, pipeline_result)
            completed_from_file += 1
            emitted_from_file += len(pipeline_result["chunked"])

        self.summary["artifact_documents_completed"] += completed_from_file
        self.summary["artifact_documents_quarantined"] += quarantined_from_file
        self.summary["artifact_files_completed"] += 1 if completed_from_file > 0 else 0
        self.summary["emitted_chunks"] += emitted_from_file

    async def _process_remote_pdf_artifact(self, session: aiohttp.ClientSession, run: JobRun, artifact_url: str) -> None:
        normalized_url = normalize_url(artifact_url)
        if not self._url_in_scope(normalized_url):
            self.summary["pdf_rejected_scope"] += 1
            return

        robots = await self._load_robots(session, normalized_url)
        if not robots.can_fetch(self.source.host_policy.user_agent, normalized_url):
            self.summary["pdf_rejected_robots"] += 1
            return

        fetched, fetch_error = await self._fetch_binary(session, normalized_url)
        if not fetched:
            self.summary["pdf_artifacts_failed"] += 1
            self.summary["pdf_fetch_failed"] += 1
            self.store.record_event(run.run_id, "WARN", "pdf_fetch_failed", f"Failed to fetch PDF artifact {normalized_url}", {"url": normalized_url, "error": fetch_error})
            return

        final_url, pdf_bytes, http_status, content_type = fetched
        raw_hash = self._binary_hash(pdf_bytes)
        raw_path = str(self._planned_binary_blob_path(raw_hash, ".pdf"))
        if not run.dry_run:
            raw_path = str(write_binary_blob(self.runtime_root, self.source.source_id, raw_hash, ".pdf", pdf_bytes))

        filename = Path(urlparse(final_url).path or "artifact.pdf").name or "artifact.pdf"
        pipeline_result = process_pdf_document(
            source=self.source,
            run=run,
            source_ref=final_url,
            pdf_bytes=pdf_bytes,
            raw_pdf_path=raw_path,
            title=Path(filename).stem,
            original_filename=filename,
            http_status=http_status,
            content_type=content_type,
            acquisition_method="remote_fetch",
            max_chunk_chars=self.max_chunk_chars,
            do_ocr=self.pdf_ocr,
            ocr_dpi=self.pdf_ocr_dpi,
            max_pdf_pages=self.pdf_max_pages,
        )

        if pipeline_result["validation_errors"]:
            if not run.dry_run:
                self._handle_validation_failure(run, pipeline_result["chunked"], pipeline_result["validation_errors"])
            self.summary["pdf_artifacts_quarantined"] += 1
            return

        self._write_pipeline_result(run, pipeline_result)
        self.summary["pdf_artifacts_completed"] += 1
        self.summary["emitted_chunks"] += len(pipeline_result["chunked"])

    async def _run_pdf_ingest(self, run: JobRun, max_artifacts: int | None = None) -> dict[str, int]:
        if self.discovery_only:
            raise ValueError("discover_only is not supported for PDF sources")

        manifest = self.source.manifest
        artifact_urls = list(manifest.get("artifact_urls") or [])
        artifact_path = str(manifest.get("artifact_path") or "").strip()
        artifacts: list[tuple[str, str]] = []
        if artifact_path:
            artifacts.append(("local", artifact_path))
        for artifact_url in artifact_urls:
            artifacts.append(("remote", str(artifact_url)))
        if max_artifacts is not None:
            artifacts = artifacts[: max(0, int(max_artifacts))]

        self.summary["pdf_artifacts_declared"] = len(artifacts)
        if not artifacts:
            raise ValueError(f"PDF source {self.source.source_id} has no artifact_path or artifact_urls")

        needs_remote_session = any(kind == "remote" for kind, _value in artifacts)
        session: aiohttp.ClientSession | None = None
        try:
            if needs_remote_session:
                timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_read=120)
                session = aiohttp.ClientSession(
                    timeout=timeout,
                    headers={
                        "User-Agent": self.source.host_policy.user_agent,
                        "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.5",
                    },
                    raise_for_status=False,
                )
            for kind, value in artifacts:
                self.summary["processed_artifacts"] += 1
                if kind == "local":
                    self._process_local_pdf_artifact(run, value)
                else:
                    assert session is not None
                    await self._process_remote_pdf_artifact(session, run, value)
        finally:
            if session is not None:
                await session.close()

        summary = dict(self.summary)
        write_report(self.runtime_root, run, "crawl_summary.json", summary)
        write_run_manifest(self.runtime_root, run, {"summary": summary, "source_id": self.source.source_id})
        return summary

    async def _run_artifact_ingest(self, run: JobRun, max_artifacts: int | None = None) -> dict[str, int]:
        if self.discovery_only:
            raise ValueError("discover_only is not supported for local artifact manifests")

        manifest = self.source.manifest
        artifact_urls = list(manifest.get("artifact_urls") or [])
        artifact_path = str(manifest.get("artifact_path") or "").strip()
        if artifact_urls:
            raise ValueError(f"Non-PDF source {self.source.source_id} declares artifact_urls, but only local artifact_path ingestion is implemented")
        if not artifact_path:
            raise ValueError(f"Source {self.source.source_id} has no artifact_path")

        files = self._iter_local_artifact_files(artifact_path)
        supported_files = [
            path
            for path in files
            if path.suffix.lower() in TEXT_ARTIFACT_SUFFIXES or path.suffix.lower() in JSON_ARTIFACT_SUFFIXES
        ]
        if max_artifacts is not None:
            supported_files = supported_files[: max(0, int(max_artifacts))]

        self.summary["artifact_files_declared"] = len(supported_files)
        if not supported_files:
            raise ValueError(f"Source {self.source.source_id} resolved no supported local artifacts from {artifact_path}")

        for path in supported_files:
            self.summary["processed_artifacts"] += 1
            if path.suffix.lower() in JSON_ARTIFACT_SUFFIXES:
                self._process_local_json_artifact(run, path)
            else:
                self._process_local_text_artifact(run, path)

        summary = dict(self.summary)
        write_report(self.runtime_root, run, "crawl_summary.json", summary)
        write_run_manifest(self.runtime_root, run, {"summary": summary, "source_id": self.source.source_id})
        return summary

    async def _process_frontier_row(self, session: aiohttp.ClientSession, run: JobRun, row) -> None:
        url = row["url"]
        normalized_url = row["normalized_url"]
        host = row["host"]

        if not self._url_in_scope(url):
            self.store.finish_frontier_item(run.run_id, normalized_url, "rejected", "url outside manifest scope")
            self.summary["rejected_scope"] += 1
            return

        robots = await self._load_robots(session, url)
        if not robots.can_fetch(self.source.host_policy.user_agent, url):
            self.store.finish_frontier_item(run.run_id, normalized_url, "rejected", "robots disallow")
            self.summary["rejected_robots"] += 1
            return

        existing = self.store.get_url_state(self.source.source_id, normalized_url)
        if existing and existing["last_status"] == "kept" and not self.force_recrawl:
            self.summary["already_known"] += 1

        fetched, fetch_error = await self._fetch(session, url)
        if not fetched:
            self.store.finish_frontier_item(run.run_id, normalized_url, "failed", fetch_error)
            self.store.record_event(run.run_id, "WARN", "page_fetch_failed", f"Fetch failed for {url}", {"url": url, "error": fetch_error})
            self.summary["fetch_failed"] += 1
            return

        final_url, html, http_status = fetched
        title, extracted_text, extractor_name = self._extract_main_text(final_url, html)
        if self._page_is_low_value(final_url, title, extracted_text):
            self.store.upsert_url_state(source_id=self.source.source_id, normalized_url=normalized_url, canonical_url=final_url, host=host, last_status="rejected", http_status=http_status, content_hash=None, page_title=title, quality_class="low_value")
            self.store.finish_frontier_item(run.run_id, normalized_url, "rejected", "low value page")
            self.summary["rejected_low_value"] += 1
            return

        content_hash = text_content_hash(extracted_text or html)
        duplicate = self.store.find_content_hash(self.source.source_id, content_hash)
        if duplicate and duplicate["normalized_url"] != normalized_url:
            self.store.upsert_url_state(source_id=self.source.source_id, normalized_url=normalized_url, canonical_url=final_url, host=host, last_status="duplicate", http_status=http_status, content_hash=content_hash, page_title=title, quality_class="duplicate")
            self.store.finish_frontier_item(run.run_id, normalized_url, "duplicate", "duplicate content hash")
            self.summary["duplicate_pages"] += 1
            return

        duplicate_key = quick_duplicate_key(extracted_text)
        if existing and existing["content_hash"] == content_hash and not self.force_recrawl:
            self.store.upsert_url_state(source_id=self.source.source_id, normalized_url=normalized_url, canonical_url=final_url, host=host, last_status="unchanged", http_status=http_status, content_hash=content_hash, page_title=title, quality_class="unchanged")
            self.store.finish_frontier_item(run.run_id, normalized_url, "unchanged")
            self.summary["unchanged_pages"] += 1
            return

        html_path = write_html_blob(self.runtime_root, self.source.source_id, content_hash, html)
        pipeline_result = process_html_document(
            source=self.source,
            run=run,
            url=final_url,
            normalized_url=normalized_url,
            final_url=final_url,
            title=title,
            html=html,
            html_path=str(html_path),
            extracted_text=extracted_text,
            extractor_name=extractor_name,
            discovery_reason=row["discovery_reason"],
            http_status=http_status,
            max_chunk_chars=self.max_chunk_chars,
        )

        if pipeline_result["validation_errors"]:
            if not run.dry_run:
                self._handle_validation_failure(run, pipeline_result["chunked"], pipeline_result["validation_errors"])
            self.store.upsert_url_state(source_id=self.source.source_id, normalized_url=normalized_url, canonical_url=final_url, host=host, last_status="quarantined", http_status=http_status, content_hash=content_hash, page_title=title, quality_class="quarantined")
            self.store.finish_frontier_item(run.run_id, normalized_url, "quarantined", "stage validation failed")
            self.summary["quarantined_pages"] += 1
            return

        if not self.discovery_only and not run.dry_run:
            for stage in ["raw", "extracted", "cleaned", "sectionized", "chunked"]:
                write_records(self.runtime_root, stage, self.source.source_id, run, pipeline_result[stage])

        if self.enable_candidate_discovery:
            candidate_records = await self.discovery_engine.discover_from_html(
                session=session,
                source=self.source,
                run=run,
                base_url=final_url,
                html=html,
                max_candidates=self.max_candidates,
            )
            if candidate_records and not run.dry_run:
                write_records(self.runtime_root, "discovery_candidate", self.source.source_id, run, candidate_records)
            self.summary["candidate_records"] += len(candidate_records)

        links = self._extract_links(final_url, html, int(row["depth"]))
        self.store.enqueue_frontier_items(run.run_id, links)
        self.store.upsert_url_state(source_id=self.source.source_id, normalized_url=normalized_url, canonical_url=final_url, host=host, last_status="kept", http_status=http_status, content_hash=content_hash, page_title=title, quality_class="kept")
        self.store.finish_frontier_item(run.run_id, normalized_url, "completed")
        self.summary["kept_pages"] += 1
        self.summary["emitted_chunks"] += len(pipeline_result["chunked"])
        self.summary["frontier_enqueued"] += len(links)
        self.summary["duplicate_keys_seen"] += 1 if duplicate_key else 0

    async def run(self, run: JobRun, max_pages: int | None = None) -> dict[str, int]:
        ensure_runtime_layout(self.runtime_root)
        source_type = self.source.manifest.get("source_type")
        if source_type == "pdf":
            return await self._run_pdf_ingest(run, max_artifacts=max_pages)
        if source_type not in {"website", "api", "html"}:
            return await self._run_artifact_ingest(run, max_artifacts=max_pages)

        max_pages = min(max_pages or self.source.host_policy.daily_url_budget, self.source.host_policy.daily_url_budget)

        seed_items: list[FrontierItem] = []
        for seed in self.source.manifest.get("seed_urls", []):
            normalized = normalize_url(seed)
            if not self._url_in_scope(normalized):
                continue
            seed_items.append(
                FrontierItem(
                    source_id=self.source.source_id,
                    url=normalized,
                    normalized_url=normalized,
                    host=host_from_url(normalized),
                    depth=0,
                    priority=score_page(seed, seed, seed, depth=0, discovery_reason="seed"),
                    discovery_reason="seed",
                    discovered_from=None,
                )
            )
        self.store.enqueue_frontier_items(run.run_id, seed_items)

        timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_read=30)
        async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": self.source.host_policy.user_agent, "Accept": "text/html,application/xhtml+xml"}, raise_for_status=False) as session:
            processed = 0
            fatal_error = None
            while processed < max_pages:
                rows = self.store.claim_frontier_items(run.run_id, limit=self.source.host_policy.max_parallel_requests)
                if not rows:
                    break
                try:
                    await asyncio.gather(*(self._process_frontier_row(session, run, row) for row in rows))
                except Exception as exc:
                    fatal_error = str(exc)
                    break
                processed += len(rows)

        summary = dict(self.summary)
        summary["processed_frontier_items"] = processed
        summary["pending_frontier_items"] = self.store.pending_frontier_count(run.run_id)
        if fatal_error:
            summary["fatal_error"] = fatal_error
            raise RuntimeError(fatal_error)

        write_report(self.runtime_root, run, "crawl_summary.json", summary)
        write_run_manifest(self.runtime_root, run, {"summary": summary, "source_id": self.source.source_id})
        return summary


def run_crawl_once(*, source_id: str | None = None, manifest_path: str | None = None, runtime_root: Path = DEFAULT_RUNTIME_ROOT, store: RuntimeStateStore | None = None, trigger: str = "manual", dry_run: bool = False, job_id: str = "crawl.manual", job_type: str = "crawl.source", job_config: dict[str, object] | None = None, run: JobRun | None = None) -> dict[str, int]:
    source = load_approved_source(source_id=source_id, manifest_path=manifest_path)
    store = store or RuntimeStateStore(runtime_root / "state" / "runtime.db")
    owns_run = run is None
    run = run or store.create_run(job_id=job_id, job_type=job_type, source_id=source.source_id, trigger_mode=trigger, dry_run=dry_run)
    crawler = ManagedCrawler(source=source, store=store, runtime_root=runtime_root, job_config=job_config)
    try:
        summary = asyncio.run(crawler.run(run, max_pages=job_config.get("max_pages") if job_config else None))
        if owns_run:
            store.finish_run(run.run_id, "completed", summary=summary)
            final_row = store.get_run(run.run_id)
            if final_row is not None:
                run.status = str(final_row["status"])
                run.finished_at = final_row["finished_at"]
                write_run_manifest(runtime_root, run, {"summary": summary, "source_id": source.source_id})
        return summary
    except Exception as exc:
        if owns_run:
            store.finish_run(run.run_id, "failed", summary=dict(crawler.summary), error_text=str(exc))
            final_row = store.get_run(run.run_id)
            if final_row is not None:
                run.status = str(final_row["status"])
                run.finished_at = final_row["finished_at"]
                write_run_manifest(runtime_root, run, {"summary": dict(crawler.summary), "source_id": source.source_id, "error_text": str(exc)})
        raise
