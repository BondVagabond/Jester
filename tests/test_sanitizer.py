from __future__ import annotations

import pytest

from jester.processing.sanitizer import (
    SanitizationError,
    looks_like_filename,
    sanitize_content,
    sanitize_title,
)


def test_sanitize_title_removes_paths_extensions_and_noise() -> None:
    sanitized = sanitize_title(r"F:\Jester\sources\Goblin_Cave.final.md")
    assert sanitized == "Goblin Cave final"


def test_sanitize_title_rejects_artifact_names() -> None:
    with pytest.raises(SanitizationError):
        sanitize_title("generated_output_summary.jsonl")


def test_sanitize_content_strips_paths_filenames_and_tooling_terms() -> None:
    cleaned = sanitize_content(
        "Read F:/Jester/generated/manifest.jsonl now!!!\nwatchdog pipeline output"
    )
    assert cleaned == "Read now!"


def test_looks_like_filename_detects_expected_cases() -> None:
    assert looks_like_filename("reports.jsonl") is True
    assert looks_like_filename(r"C:\Temp\notes.txt") is True
    assert looks_like_filename("Goblin Cave") is False
