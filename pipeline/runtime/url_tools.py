from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

TRACKING_QUERY_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src",
}
LOW_VALUE_PATH_PATTERNS = [
    r"/tag/", r"/tags/", r"/category/", r"/categories/", r"/archive", r"/archives",
    r"/search", r"/feed", r"/author/", r"/comments", r"/wp-admin", r"/wp-login",
]
SOFT_404_PATTERNS = [r"\b404\b", r"not found", r"page not found", r"no results"]
TOPIC_MARKERS = ["dnd", "d&d", "dungeon", "dragon", "session", "transcript", "play", "report", "campaign", "rpg"]
LICENSE_MARKERS = ["copyright", "creative commons", "cc-by", "all rights reserved", "license"]
OWNER_MARKERS = ["about", "contact", "terms", "privacy"]


def normalize_url(url: str, base_url: str | None = None) -> str:
    absolute = urljoin(base_url, url) if base_url else url
    parsed = urlparse(absolute)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    if netloc.endswith(":80") and scheme == "http":
        netloc = netloc[:-3]
    if netloc.endswith(":443") and scheme == "https":
        netloc = netloc[:-4]
    path = parsed.path or "/"
    path = re.sub(r"/{2,}", "/", path)
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=False) if k.lower() not in TRACKING_QUERY_KEYS]
    query.sort()
    normalized_query = urlencode(query)
    normalized = urlunparse((scheme, netloc, path, "", normalized_query, ""))
    return normalized


def host_from_url(url: str) -> str:
    return urlparse(url).netloc.lower()


def domain_allowed(host: str, allowed_domains: Iterable[str]) -> bool:
    host = host.lower()
    for allowed in allowed_domains:
        allowed = allowed.lower().strip()
        if host == allowed or host.endswith("." + allowed):
            return True
    return False


def path_allowed(url: str, allowed_path_prefixes: Iterable[str] | None = None, blocked_url_patterns: Iterable[str] | None = None) -> bool:
    normalized = normalize_url(url)
    if blocked_url_patterns:
        for pattern in blocked_url_patterns:
            if pattern and re.search(pattern, normalized, re.IGNORECASE):
                return False
    prefixes = [str(prefix or "").strip() for prefix in (allowed_path_prefixes or []) if str(prefix or "").strip()]
    if not prefixes:
        return True
    path = urlparse(normalized).path or "/"
    for raw_prefix in prefixes:
        prefix = raw_prefix if raw_prefix == "/" else raw_prefix.rstrip("/")
        if prefix == "/":
            return True
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def is_probably_low_value_url(url: str) -> bool:
    lower = normalize_url(url).lower()
    return any(re.search(pattern, lower) for pattern in LOW_VALUE_PATH_PATTERNS)


def text_content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()


def url_hash(url: str) -> str:
    return hashlib.sha1(normalize_url(url).encode("utf-8", "ignore")).hexdigest()[:16]


def soft_404_signal(title: str, text: str) -> bool:
    haystack = f"{title}\n{text}".lower()
    return any(re.search(pattern, haystack) for pattern in SOFT_404_PATTERNS)


def normalize_text_for_similarity(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def quick_duplicate_key(text: str) -> str:
    normalized = normalize_text_for_similarity(text)
    return hashlib.sha1(normalized[:5000].encode("utf-8", "ignore")).hexdigest()


def score_page(url: str, title: str, text: str, depth: int, discovery_reason: str) -> float:
    score = 1.0
    lowered = f"{url} {title} {text[:500]}".lower()
    for marker in TOPIC_MARKERS:
        if marker in lowered:
            score += 0.5
    if discovery_reason == "seed":
        score += 1.0
    if depth <= 1:
        score += 0.4
    if len(text.split()) > 200:
        score += 0.6
    if is_probably_low_value_url(url):
        score -= 1.2
    return round(score, 4)


def score_candidate_domain(domain: str, url: str, context_text: str = "") -> tuple[float, float]:
    lowered = f"{domain} {url} {context_text}".lower()
    relevance = 0.1
    risk = 0.1
    for marker in TOPIC_MARKERS:
        if marker in lowered:
            relevance += 0.12
    for marker in LICENSE_MARKERS:
        if marker in lowered:
            risk += 0.1
    if "fandom" in lowered or "wiki" in lowered:
        risk += 0.15
    if any(word in lowered for word in ["official", "blog", "archive"]):
        relevance += 0.08
    relevance = max(0.0, min(1.0, relevance))
    risk = max(0.0, min(1.0, risk))
    return round(relevance, 4), round(risk, 4)


def apparent_license_signals(text: str) -> list[str]:
    lowered = text.lower()
    return [marker for marker in LICENSE_MARKERS if marker in lowered]


def apparent_owner_signals(text: str) -> list[str]:
    lowered = text.lower()
    return [marker for marker in OWNER_MARKERS if marker in lowered]
