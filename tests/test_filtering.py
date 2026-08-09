from __future__ import annotations

from pathlib import Path

import pytest

from jester.ingestion.filtering import (
    IngestionFilter,
    IngestionPolicy,
    SourceMetadata,
    is_valid_source,
)


def test_default_policy_rejects_generated_jsonl_artifacts() -> None:
    path = Path("generated/manifest.jsonl")
    metadata = SourceMetadata(title="manifest.jsonl")
    assert is_valid_source(path, metadata) is False


def test_whitelist_can_allow_validated_jsonl_sources() -> None:
    policy = IngestionPolicy(
        denied_name_patterns=[r"\bmanifest\b"],
        denied_extensions=[".json", ".jsonl"],
        denied_path_parts=["generated"],
        allowed_extensions=[".md", ".txt"],
        explicit_whitelist_patterns=[r"trusted/.+\.jsonl$"],
    )
    source_filter = IngestionFilter(policy)

    assert source_filter.is_valid_source(Path("trusted/rules.jsonl")) is True


def test_policy_rejects_extension_overlap() -> None:
    with pytest.raises(ValueError):
        IngestionPolicy(
            denied_extensions=[".md"],
            allowed_extensions=[".md"],
        )
