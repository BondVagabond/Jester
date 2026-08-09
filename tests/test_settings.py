from __future__ import annotations

from pathlib import Path

import pytest

from jester.ai import ModelRole
from jester.config.settings import SettingsError, load_settings


def test_load_settings_uses_default_prompt_root() -> None:
    settings = load_settings({})
    assert settings.prompt_registry.prompt_root.name == 'prompts'
    assert settings.retrieval.default_top_k == 5
    assert settings.ai.bindings()[ModelRole.PRIMARY_GENERATION].model_name == 'deterministic-primary'
    assert {source.corpus_id for source in settings.corpora.sources} == {'world', 'rules'}


def test_invalid_prompt_root_fails_immediately(tmp_path: Path) -> None:
    missing = tmp_path / 'missing-prompts'
    with pytest.raises(SettingsError):
        load_settings({'JESTER_PROMPT_ROOT': str(missing)})


def test_invalid_world_corpus_path_fails_immediately(tmp_path: Path) -> None:
    missing = tmp_path / 'missing-world.jsonl'
    with pytest.raises(SettingsError):
        load_settings({'JESTER_WORLD_CORPUS_PATH': str(missing)})


def test_invalid_boolean_setting_fails_immediately() -> None:
    with pytest.raises(SettingsError):
        load_settings({'JESTER_ALLOW_URLS_IN_OUTPUT': 'maybe'})


def test_invalid_top_k_fails_immediately() -> None:
    with pytest.raises(SettingsError):
        load_settings({'JESTER_DEFAULT_TOP_K': '0'})


def test_ai_role_can_be_disabled_by_config() -> None:
    settings = load_settings({'JESTER_REASONING_ENABLED': 'false'})
    assert settings.ai.reasoning.enabled is False


def test_invalid_model_temperature_fails_immediately() -> None:
    with pytest.raises(SettingsError):
        load_settings({'JESTER_PRIMARY_TEMPERATURE': '2.0'})


def test_prod_environment_rejects_fake_models() -> None:
    with pytest.raises(SettingsError):
        load_settings({'JESTER_ENVIRONMENT': 'prod'})


def test_mixed_fake_and_real_model_roles_are_rejected() -> None:
    with pytest.raises(SettingsError):
        load_settings(
            {
                'JESTER_PRIMARY_PROVIDER': 'openai',
                'JESTER_OPENAI_API_KEY': 'test-key',
            }
        )


def test_openai_provider_requires_api_key_when_enabled() -> None:
    with pytest.raises(SettingsError):
        load_settings(
            {
                'JESTER_PRIMARY_PROVIDER': 'openai',
                'JESTER_REASONING_PROVIDER': 'openai',
                'JESTER_SMALL_FAST_PROVIDER': 'openai',
            }
        )


def test_openai_provider_can_be_configured_for_dev_runtime() -> None:
    settings = load_settings(
        {
            'JESTER_PRIMARY_PROVIDER': 'openai',
            'JESTER_REASONING_PROVIDER': 'openai',
            'JESTER_SMALL_FAST_PROVIDER': 'openai',
            'JESTER_OPENAI_API_KEY': 'test-key',
        }
    )
    assert settings.providers.openai.api_key == 'test-key'
    assert settings.ai.bindings()[ModelRole.PRIMARY_GENERATION].provider_name == 'openai'
