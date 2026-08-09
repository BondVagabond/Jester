from __future__ import annotations

import re
from pathlib import Path

KNOWN_EXTENSIONS = {
    ".csv",
    ".faiss",
    ".html",
    ".htm",
    ".json",
    ".jsonl",
    ".log",
    ".md",
    ".markdown",
    ".pdf",
    ".rst",
    ".txt",
    ".yaml",
    ".yml",
}
FILENAME_RE = re.compile(
    r"(?i)\b[a-z0-9][a-z0-9_. -]*\.(?:csv|faiss|html?|jsonl?|log|md|markdown|pdf|rst|txt|ya?ml)\b"
)
PATH_RE = re.compile(r"(?i)(?:[a-z]:)?(?:[\\/][^\\/\s]+)+")
DRIVE_RE = re.compile(r"(?i)\b[a-z]:[\\/]")
ARTIFACT_ONLY_RE = re.compile(
    r"(?i)^(?:artifact|artifacts|generated|logs?|manifest|output|pipeline|reports?|summary|watchdog)(?:\s+(?:artifact|artifacts|generated|logs?|manifest|output|pipeline|reports?|summary|watchdog))*$"
)
METADATA_TRIPLET_RE = re.compile(r"(?i)\b[a-z0-9_-]+::[a-z0-9_-]+::[a-z0-9_.-]+\b")
TOOLING_TERM_RE = re.compile(
    r"(?i)\b(?:artifact|artifacts|generated|logs?|manifest|output|pipeline|reports?|summary|watchdog)\b"
)
MULTISPACE_RE = re.compile(r"\s+")
REPEATED_PUNCTUATION_RE = re.compile(r"([!?.,:;])\1+")
SPACE_BEFORE_PUNCTUATION_RE = re.compile(r"\s+([!?.,:;])")


class SanitizationError(ValueError):
    """Raised when a title cannot be sanitized into safe user-facing text."""


def looks_like_filename(value: str) -> bool:
    candidate = value.strip().strip("\"'")
    if not candidate:
        return False
    if DRIVE_RE.search(candidate) or "/" in candidate or "\\" in candidate:
        return True

    suffix = Path(candidate).suffix.lower()
    if suffix in KNOWN_EXTENSIONS:
        return True

    return bool(FILENAME_RE.fullmatch(candidate))


def sanitize_title(raw_title: str) -> str:
    candidate = raw_title.strip()
    if not candidate:
        raise SanitizationError("Title must not be blank.")

    if DRIVE_RE.search(candidate) or "/" in candidate or "\\" in candidate:
        candidate = re.split(r"[\\/]+", candidate)[-1]

    candidate = _strip_known_extensions(candidate)
    candidate = candidate.replace("_", " ").replace("-", " ").replace(".", " ")
    candidate = REPEATED_PUNCTUATION_RE.sub(r"\1", candidate)
    candidate = MULTISPACE_RE.sub(" ", candidate).strip(" .,:;!?-_")

    if ARTIFACT_ONLY_RE.fullmatch(candidate):
        candidate = TOOLING_TERM_RE.sub(" ", candidate)
        candidate = MULTISPACE_RE.sub(" ", candidate).strip(" .,:;!?-_")

    if not candidate:
        raise SanitizationError(
            f"Title {raw_title!r} collapsed to empty text during sanitization."
        )
    if looks_like_filename(candidate) or ARTIFACT_ONLY_RE.fullmatch(candidate):
        raise SanitizationError(
            f"Title {raw_title!r} still looks like an unsafe filename after sanitization."
        )
    return candidate


def sanitize_content(raw_text: str) -> str:
    candidate = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    candidate = METADATA_TRIPLET_RE.sub(" ", candidate)
    candidate = PATH_RE.sub(" ", candidate)
    candidate = FILENAME_RE.sub(" ", candidate)
    candidate = DRIVE_RE.sub(" ", candidate)

    cleaned_lines: list[str] = []
    for raw_line in candidate.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        stripped_line = TOOLING_TERM_RE.sub(" ", line)
        normalized_line = MULTISPACE_RE.sub(" ", stripped_line).strip(" .,:;-_")
        if normalized_line:
            cleaned_lines.append(normalized_line)

    cleaned = "\n".join(cleaned_lines)
    cleaned = REPEATED_PUNCTUATION_RE.sub(r"\1", cleaned)
    cleaned = SPACE_BEFORE_PUNCTUATION_RE.sub(r"\1", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _strip_known_extensions(value: str) -> str:
    candidate = value.strip()
    while True:
        suffix = Path(candidate).suffix.lower()
        if suffix not in KNOWN_EXTENSIONS:
            return candidate
        candidate = candidate[: -len(suffix)]
