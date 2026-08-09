from __future__ import annotations

import re
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _normalize_extension(value: str) -> str:
    text = value.strip().lower()
    if not text:
        raise ValueError("Extension values must not be blank.")
    return text if text.startswith(".") else f".{text}"


def _normalize_pattern(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("Pattern values must not be blank.")
    return text


def _normalize_path_part(value: str) -> str:
    text = value.strip().lower().strip("/\\")
    if not text:
        raise ValueError("Path parts must not be blank.")
    return text


class SourceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str | None = None
    source_id: str | None = None
    corpus: str | None = None
    tags: list[str] = Field(default_factory=list)


class IngestionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    denied_name_patterns: list[str] = Field(
        default_factory=lambda: [
            r"\breports?\b",
            r"\bmanifest\b",
            r"\bwatchdog\b",
            r"\blogs?\b",
            r"\boutput\b",
            r"\bsummary\b",
            r"\bgenerated\b",
        ]
    )
    denied_extensions: list[str] = Field(default_factory=lambda: [".json", ".jsonl"])
    denied_path_parts: list[str] = Field(
        default_factory=lambda: [
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "artifacts",
            "cache",
            "caches",
            "generated",
            "log",
            "logs",
            "output",
            "outputs",
            "temp",
            "tmp",
        ]
    )
    allowed_extensions: list[str] = Field(
        default_factory=lambda: [".md", ".markdown", ".pdf", ".rst", ".txt"]
    )
    explicit_whitelist_patterns: list[str] = Field(default_factory=list)

    @field_validator("denied_extensions", "allowed_extensions")
    @classmethod
    def normalize_extensions(cls, values: list[str]) -> list[str]:
        normalized = [_normalize_extension(value) for value in values]
        return sorted(dict.fromkeys(normalized))

    @field_validator("denied_name_patterns", "explicit_whitelist_patterns")
    @classmethod
    def normalize_patterns(cls, values: list[str]) -> list[str]:
        normalized = [_normalize_pattern(value) for value in values]
        return list(dict.fromkeys(normalized))

    @field_validator("denied_path_parts")
    @classmethod
    def normalize_path_parts(cls, values: list[str]) -> list[str]:
        normalized = [_normalize_path_part(value) for value in values]
        return sorted(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def validate_extension_overlap(self) -> IngestionPolicy:
        overlap = set(self.denied_extensions) & set(self.allowed_extensions)
        if overlap:
            raise ValueError(
                f"Extensions cannot be both allowed and denied: {sorted(overlap)}"
            )
        return self


DEFAULT_INGESTION_POLICY: Final[IngestionPolicy] = IngestionPolicy()


class IngestionFilter:
    def __init__(self, policy: IngestionPolicy) -> None:
        self._policy = policy
        self._denied_name_patterns = self._compile_patterns(policy.denied_name_patterns)
        self._whitelist_patterns = self._compile_patterns(
            policy.explicit_whitelist_patterns
        )

    @property
    def policy(self) -> IngestionPolicy:
        return self._policy

    def is_valid_source(
        self,
        file_path: Path,
        metadata: SourceMetadata | None = None,
    ) -> bool:
        resolved = Path(file_path)
        metadata_model = metadata or SourceMetadata()
        candidates = [
            str(resolved),
            resolved.name,
            metadata_model.title or "",
            metadata_model.source_id or "",
        ]
        normalized_candidates = [self._normalize_candidate(candidate) for candidate in candidates]

        if self._matches_whitelist(normalized_candidates):
            return True

        if not resolved.suffix:
            return False

        suffix = resolved.suffix.lower()
        if suffix in self._policy.denied_extensions:
            return False
        if suffix not in self._policy.allowed_extensions:
            return False

        path_parts = {part.lower() for part in resolved.parts}
        if any(part in path_parts for part in self._policy.denied_path_parts):
            return False

        name_inputs = [resolved.stem.lower(), resolved.name.lower()]
        if metadata_model.title:
            name_inputs.append(metadata_model.title.lower())
        return not any(
            pattern.search(name_input)
            for pattern in self._denied_name_patterns
            for name_input in name_inputs
        )

    @staticmethod
    def _compile_patterns(patterns: list[str]) -> tuple[re.Pattern[str], ...]:
        return tuple(re.compile(pattern, flags=re.IGNORECASE) for pattern in patterns)

    @staticmethod
    def _normalize_candidate(candidate: str) -> str:
        return candidate.replace("\\", "/").lower().strip()

    def _matches_whitelist(self, candidates: list[str]) -> bool:
        if not self._whitelist_patterns:
            return False
        return any(
            pattern.search(candidate)
            for pattern in self._whitelist_patterns
            for candidate in candidates
        )


def is_valid_source(file_path: Path, metadata: SourceMetadata | None = None) -> bool:
    """Validate source file paths against the default ingestion policy."""

    return IngestionFilter(DEFAULT_INGESTION_POLICY).is_valid_source(
        file_path,
        metadata=metadata,
    )
