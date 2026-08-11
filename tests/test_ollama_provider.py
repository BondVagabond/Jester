from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from jester.ai import ModelRequest, ModelRole
from jester.ai.base import ModelError
from jester.ai.providers import OllamaChatClient, ProviderConfigurationError, ProviderRequestError, ProviderTimeoutError
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


Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler, *, settings: OllamaProviderSettings | None = None) -> OllamaChatClient:
    resolved = settings or OllamaProviderSettings()
    return OllamaChatClient(
        role=ModelRole.PRIMARY_GENERATION,
        model_name='qwen3.5:4b',
        settings=resolved,
        http_client=httpx.Client(
            base_url=resolved.base_url,
            transport=httpx.MockTransport(handler),
        ),
    )


def test_ollama_client_maps_response_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == '/api/chat'
        return httpx.Response(
            200,
            json={
                'message': {'role': 'assistant', 'content': ' A concise narration. '},
                'done': True,
                'prompt_eval_count': 120,
                'eval_count': 40,
            },
        )

    response = _client(handler).generate(
        ModelRequest(role=ModelRole.PRIMARY_GENERATION, prompt='Narrate the scene.')
    )

    assert response.provider_name == 'ollama'
    assert response.model_name == 'qwen3.5:4b'
    assert response.content == 'A concise narration.'
    assert response.token_usage == {
        'prompt_tokens': 120,
        'completion_tokens': 40,
        'total_tokens': 160,
    }


def test_ollama_client_sends_options_think_and_no_format_for_prose() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.read().decode('utf-8')))
        return httpx.Response(200, json={'message': {'content': 'ok'}})

    settings = OllamaProviderSettings(num_ctx=8192, think=False, keep_alive='30m')
    _client(handler, settings=settings).generate(
        ModelRequest(
            role=ModelRole.PRIMARY_GENERATION,
            prompt='Narrate the scene.',
            temperature=0.4,
            max_tokens=384,
            prompt_name='live_dm_narration',
        )
    )

    assert captured['model'] == 'qwen3.5:4b'
    assert captured['stream'] is False
    assert captured['think'] is False
    assert captured['keep_alive'] == '30m'
    assert captured['options'] == {'temperature': 0.4, 'num_ctx': 8192, 'num_predict': 384}
    assert 'format' not in captured


def test_ollama_client_sets_json_format_for_structured_prompts() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.read().decode('utf-8')))
        return httpx.Response(200, json={'message': {'content': '{"objective": "x"}'}})

    OllamaChatClient(
        role=ModelRole.REASONING,
        model_name='qwen3.5:4b',
        settings=OllamaProviderSettings(),
        http_client=httpx.Client(
            base_url='http://127.0.0.1:11434',
            transport=httpx.MockTransport(handler),
        ),
    ).generate(
        ModelRequest(role=ModelRole.REASONING, prompt='Plan it.', prompt_name='prep_plan')
    )

    assert captured['format'] == 'json'


def test_ollama_client_rejects_role_mismatch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError('should not issue a request')

    with pytest.raises(ModelError):
        _client(handler).generate(
            ModelRequest(role=ModelRole.REASONING, prompt='Plan it.')
        )


def test_ollama_client_reports_unreachable_service() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('connection refused', request=request)

    with pytest.raises(ProviderRequestError, match='is the Ollama service running'):
        _client(handler).generate(
            ModelRequest(role=ModelRole.PRIMARY_GENERATION, prompt='Narrate.')
        )


def test_ollama_client_reports_missing_model_as_configuration_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={'error': 'model "qwen3.5:4b" not found, try pulling it first'})

    with pytest.raises(ProviderConfigurationError, match='ollama pull qwen3.5:4b'):
        _client(handler).generate(
            ModelRequest(role=ModelRole.PRIMARY_GENERATION, prompt='Narrate.')
        )


def test_ollama_client_maps_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout('timed out', request=request)

    with pytest.raises(ProviderTimeoutError):
        _client(handler).generate(
            ModelRequest(role=ModelRole.PRIMARY_GENERATION, prompt='Narrate.')
        )


def test_ollama_client_rejects_empty_content() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={'message': {'role': 'assistant', 'content': '   '}})

    with pytest.raises(ProviderRequestError, match='empty content'):
        _client(handler).generate(
            ModelRequest(role=ModelRole.PRIMARY_GENERATION, prompt='Narrate.')
        )


def test_ollama_client_raises_when_only_reasoning_tokens_returned() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                'message': {'role': 'assistant', 'content': '', 'thinking': 'Thinking Process: ...'},
                'done_reason': 'length',
            },
        )

    with pytest.raises(ProviderRequestError, match='reasoning tokens but no answer'):
        _client(handler).generate(
            ModelRequest(role=ModelRole.PRIMARY_GENERATION, prompt='Narrate.')
        )
