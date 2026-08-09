from __future__ import annotations

from jester.validation.output_validator import OutputValidationPolicy, validate_output


def test_clean_fantasy_output_passes_validation() -> None:
    result = validate_output(
        "The lantern light flickers across the ancient stone corridor."
    )
    assert result.is_valid is True
    assert result.issues == []


def test_urls_and_anachronisms_are_rejected() -> None:
    result = validate_output(
        "Check https://example.com from your smartphone before the ritual."
    )
    codes = {issue.code for issue in result.issues}

    assert result.is_valid is False
    assert "url_leakage" in codes
    assert "anachronism" in codes


def test_policy_can_allow_urls_when_explicitly_enabled() -> None:
    result = validate_output(
        "Visit https://example.com for lore.",
        policy=OutputValidationPolicy(
            allow_urls=True,
            enable_anachronism_check=False,
        ),
    )
    assert result.is_valid is True
