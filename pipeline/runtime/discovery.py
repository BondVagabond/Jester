from __future__ import annotations

import json
import warnings
from pathlib import Path
from urllib import robotparser
from urllib.parse import urlparse

import aiohttp
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from training.validation import validate_records
from training.validation.validate_candidate_source import validate_candidate_manifest

from .manifests import CANDIDATE_SOURCE_DIR
from .models import PIPELINE_VERSION, ApprovedSource, CandidateSource, JobRun, utcnow_iso
from .state_store import RuntimeStateStore
from .url_tools import (
    apparent_license_signals,
    apparent_owner_signals,
    domain_allowed,
    host_from_url,
    normalize_url,
    score_candidate_domain,
    text_content_hash,
    url_hash,
)

XML_PREFIX_MARKERS = (
    "<?xml",
    "<rss",
    "<feed",
    "<urlset",
    "<sitemapindex",
    "<rdf:rdf",
)


class DiscoveryEngine:
    def __init__(self, store: RuntimeStateStore, candidate_dir: Path = CANDIDATE_SOURCE_DIR):
        self.store = store
        self.candidate_dir = Path(candidate_dir)
        self.candidate_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _looks_like_xml(markup: str) -> bool:
        sample = str(markup or "").lstrip()[:2048].lower()
        if not sample:
            return False
        if sample.startswith(XML_PREFIX_MARKERS):
            return True
        if "xhtml" in sample:
            return True
        if 'xmlns="http://www.w3.org/1999/xhtml"' in sample:
            return True
        return False

    @classmethod
    def _parse_markup(cls, markup: str) -> BeautifulSoup:
        if cls._looks_like_xml(markup):
            return BeautifulSoup(markup, "xml")
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
            return BeautifulSoup(markup, "lxml")

    async def _probe_candidate(self, session: aiohttp.ClientSession, url: str) -> tuple[bool, str]:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = origin + "/robots.txt"
        rp = robotparser.RobotFileParser()
        try:
            async with session.get(robots_url) as response:
                if response.status != 200:
                    return False, ""
                rp.parse((await response.text()).splitlines())
        except Exception:
            return False, ""

        try:
            if not rp.can_fetch(session.headers.get("User-Agent", "*"), origin + "/"):
                return False, ""
        except Exception:
            return False, ""

        try:
            async with session.get(origin + "/") as response:
                if response.status != 200 or "text/html" not in response.headers.get("content-type", ""):
                    return True, ""
                return True, await response.text()
        except Exception:
            return True, ""

    def _candidate_record(self, candidate: CandidateSource, run: JobRun) -> dict[str, object]:
        payload = candidate.to_dict()
        return {
            "record_id": f"discovery_candidate:{candidate.candidate_source_id}:{run.run_id}",
            "stage": "discovery_candidate",
            "candidate_source_id": candidate.candidate_source_id,
            "candidate_domain": candidate.candidate_domain,
            "seed_url": candidate.seed_url,
            "discovered_at": run.started_at,
            "discovery_methods": candidate.discovery_methods,
            "relevance_score": candidate.relevance_score,
            "risk_score": candidate.risk_score,
            "review_status": candidate.review_status,
            "apparent_owner": candidate.apparent_owner,
            "apparent_license": candidate.apparent_license,
            "apparent_content_type": candidate.apparent_content_type,
            "discovery_evidence": candidate.discovery_evidence,
            "run_id": run.run_id,
            "job_id": run.job_id,
            "content_hash": text_content_hash(json.dumps(payload, ensure_ascii=False, sort_keys=True)),
            "pipeline_version": PIPELINE_VERSION,
        }

    @staticmethod
    def _candidate_manifest_path(candidate_id: str, candidate_dir: Path) -> Path:
        safe_name = candidate_id.replace(":", "_")
        return candidate_dir / f"{safe_name}.json"

    def _write_candidate_manifest(self, path: Path, payload: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    async def discover_from_html(self, *, session: aiohttp.ClientSession, source: ApprovedSource, run: JobRun, base_url: str, html: str, max_candidates: int = 10) -> list[dict[str, object]]:
        soup = self._parse_markup(html)
        external_links: dict[str, dict[str, str]] = {}
        for anchor in soup.find_all("a", href=True):
            href = normalize_url(anchor["href"], base_url=base_url)
            host = host_from_url(href)
            if not host or domain_allowed(host, source.host_policy.allowed_domains):
                continue
            if host in external_links:
                continue
            anchor_text = anchor.get_text(" ", strip=True)
            external_links[host] = {"url": href, "anchor_text": anchor_text}
            if len(external_links) >= max_candidates:
                break

        records: list[dict[str, object]] = []
        for host, info in external_links.items():
            candidate_id = f"candidate:{url_hash(host)}"
            robots_accessible, homepage_html = await self._probe_candidate(session, info["url"])
            soup_home = self._parse_markup(homepage_html) if homepage_html else None
            home_text = soup_home.get_text(" ", strip=True)[:2000] if soup_home else ""
            relevance_score, risk_score = score_candidate_domain(host, info["url"], context_text=info["anchor_text"] + " " + home_text)
            review_status = "quarantined" if risk_score >= 0.8 else "pending_review"
            candidate = CandidateSource(
                candidate_source_id=candidate_id,
                candidate_domain=host,
                seed_url=info["url"],
                first_seen_at=utcnow_iso(),
                last_seen_at=utcnow_iso(),
                discovery_methods=["approved_outbound_link"],
                relevance_score=relevance_score,
                risk_score=risk_score,
                review_status=review_status,
                robots_accessible=robots_accessible,
                apparent_owner=", ".join(apparent_owner_signals(home_text)) or None,
                apparent_license=", ".join(apparent_license_signals(home_text)) or None,
                apparent_content_type="html" if homepage_html else None,
                discovered_from_source_id=source.source_id,
                discovery_evidence={
                    "discovered_from_url": base_url,
                    "anchor_text": info["anchor_text"],
                    "homepage_sample": home_text[:400],
                },
                review_notes="Automatically discovered. Pending human review before approved ingestion.",
            )

            candidate_path = self._candidate_manifest_path(candidate_id, self.candidate_dir)
            candidate_errors = validate_candidate_manifest(candidate.to_dict(), candidate_path)
            record = self._candidate_record(candidate, run)
            record_errors = validate_records([record], "discovery_candidate", path=info["url"])
            self._write_candidate_manifest(candidate_path, candidate.to_dict())
            self.store.upsert_candidate(candidate_id, host, info["url"], review_status, candidate.to_dict())
            if candidate_errors or record_errors:
                record["review_status"] = "quarantined"
                record.setdefault("discovery_evidence", {})["validation_errors"] = candidate_errors + record_errors
            records.append(record)

        return records