from __future__ import annotations

from jester.config.settings import OllamaProviderSettings, load_settings


def test_ollama_settings_defaults() -> None:
    settings = OllamaProviderSettings()

    assert settings.base_url == 'http://127.0.0.1:11434'
    assert settings.timeout_seconds == 300.0
    assert settings.num_ctx == 4096
    assert settings.think is False
    assert settings.keep_alive is None


def test_ollama_settings_strip_trailing_slash_from_base_url() -> None:
    settings = OllamaProviderSettings(base_url='http://localhost:11434/')

    assert settings.base_url == 'http://localhost:11434'


def test_ollama_settings_read_from_environment() -> None:
    settings = load_settings(
        {
            'JESTER_OLLAMA_BASE_URL': 'http://192.168.0.9:11434',
            'JESTER_OLLAMA_TIMEOUT_SECONDS': '600',
            'JESTER_OLLAMA_NUM_CTX': '8192',
            'JESTER_OLLAMA_THINK': 'true',
            'JESTER_OLLAMA_KEEP_ALIVE': '30m',
        }
    )

    assert settings.providers.ollama.base_url == 'http://192.168.0.9:11434'
    assert settings.providers.ollama.timeout_seconds == 600.0
    assert settings.providers.ollama.num_ctx == 8192
    assert settings.providers.ollama.think is True
    assert settings.providers.ollama.keep_alive == '30m'
