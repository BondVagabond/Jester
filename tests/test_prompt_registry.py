from __future__ import annotations

from jester.prompts.registry import PromptNotFoundError, load_prompt


def test_load_prompt_returns_valid_spec() -> None:
    spec = load_prompt("narration", "v1")

    assert spec.name == "narration"
    assert spec.version == "v1"
    assert "player_intent" in spec.input_contract
    assert "narration" in spec.output_contract


def test_missing_prompt_version_fails_loudly() -> None:
    try:
        load_prompt("narration", "v9")
    except PromptNotFoundError as exc:
        assert "v9" in str(exc)
    else:
        raise AssertionError("Expected PromptNotFoundError for missing version.")
