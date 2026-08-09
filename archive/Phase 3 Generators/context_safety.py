import re
from pathlib import Path
from typing import Any, Dict, Iterable


_ARTIFACT_BASENAME_RE = re.compile(
    r"(?i)^("
    r"manifest(?:\.[a-z0-9]+)?|"
    r"reports?(?:_clean|_rejects|_watchdog)?(?:\.[a-z0-9]+)?|"
    r"watchdog(?:\.[a-z0-9]+)?|"
    r".*\.summary\.csv|"
    r".*\.log"
    r")$"
)
_FILENAME_TOKEN_RE = re.compile(
    r"(?i)\b[a-z0-9][a-z0-9_.-]*\.(?:jsonl|json|csv|html?|log|faiss)\b"
)
_TOOLING_TERMS_RE = re.compile(
    r"(?i)\b(jsonl|json|csv|faiss|watchdog|dataset|datasets|metadata|index|indexes|logs?|reports?|manifest)\b"
)
_PATH_SEP_RE = re.compile(r"[\\/]+")


def _basename(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().strip("\"'")
    if not text:
        return ""
    return Path(_PATH_SEP_RE.split(text)[-1]).name


def looks_like_artifact_name(value: Any) -> bool:
    base = _basename(value)
    if not base:
        return False
    if _ARTIFACT_BASENAME_RE.match(base):
        return True
    lower = str(value).lower()
    return "\\logs\\" in lower or "/logs/" in lower


def sanitize_prompt_title(title: Any) -> str:
    base = _basename(title)
    if not base:
        return ""
    base = re.sub(r"(?i)\.(jsonl|json|csv|html?|log|faiss)$", "", base)
    base = base.replace("_", " ").replace("-", " ")
    base = _TOOLING_TERMS_RE.sub(" ", base)
    base = _FILENAME_TOKEN_RE.sub(" ", base)
    base = re.sub(r"\s{2,}", " ", base).strip(" .,:;-_")
    return base


def is_index_artifact(record: Dict[str, Any]) -> bool:
    for key in ("title", "meta_source_file", "source"):
        if looks_like_artifact_name(record.get(key)):
            return True

    page_content = str(record.get("page_content") or "")
    if page_content.startswith("{\"url\":") and looks_like_artifact_name(record.get("title")):
        return True
    if "::" in page_content and looks_like_artifact_name(record.get("title")):
        return True
    return False


def contains_internal_reference(text: str) -> bool:
    if not text:
        return False
    return bool(_FILENAME_TOKEN_RE.search(text) or _ARTIFACT_BASENAME_RE.search(text))


def scrub_internal_references(text: str) -> str:
    if not text:
        return ""
    cleaned = _FILENAME_TOKEN_RE.sub(" ", text)
    cleaned = _ARTIFACT_BASENAME_RE.sub(" ", cleaned)
    cleaned = _TOOLING_TERMS_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:!?])", r"\1", cleaned)
    return cleaned.strip()


def object_contains_internal_reference(obj: Any) -> bool:
    if obj is None:
        return False
    if isinstance(obj, str):
        return contains_internal_reference(obj)
    if isinstance(obj, dict):
        return any(object_contains_internal_reference(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return any(object_contains_internal_reference(v) for v in obj)
    return False


def iter_string_values(obj: Any) -> Iterable[str]:
    if obj is None:
        return
    if isinstance(obj, str):
        yield obj
        return
    if isinstance(obj, dict):
        for v in obj.values():
            yield from iter_string_values(v)
        return
    if isinstance(obj, (list, tuple)):
        for v in obj:
            yield from iter_string_values(v)
