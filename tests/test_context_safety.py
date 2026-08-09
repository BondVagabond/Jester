from __future__ import annotations

import pytest

from jester.processing.sanitizer import SanitizationError, sanitize_title
from jester.validation.output_validator import validate_output


def test_artifact_titles_are_rejected() -> None:
    with pytest.raises(SanitizationError):
        sanitize_title("reports.jsonl")

    with pytest.raises(SanitizationError):
        sanitize_title("manifest.jsonl")


def test_output_validation_rejects_filename_and_path_leakage() -> None:
    result = validate_output(
        "The answer is stored in F:/Jester/generated/manifest.jsonl."
    )

    codes = {issue.code for issue in result.issues}
    assert result.is_valid is False
    assert "path_leakage" in codes
    assert "filename_leakage" in codes
    assert "tooling_leakage" in codes


def test_legitimate_filename_title_is_sanitized_without_leakage() -> None:
    sanitized = sanitize_title(
        r"F:\Jester\world\100_beach_encounters.jsonl"
    )
    assert sanitized == "100 beach encounters"
