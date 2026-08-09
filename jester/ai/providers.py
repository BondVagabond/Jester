from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Protocol

import httpx

from jester.ai.base import FakeModelClient, ModelClient, ModelError
from jester.ai.contracts import ModelRequest, ModelResponse, ModelRole
from jester.ai.registry import ModelRegistry

if TYPE_CHECKING:
    from jester.config.settings import AppSettings, OpenAIProviderSettings


class ProviderConfigurationError(ModelError):
    """Raised when a model provider is misconfigured."""


class ProviderRequestError(ModelError):
    """Raised when a model provider request fails."""


class ProviderTimeoutError(ProviderRequestError):
    """Raised when a provider request times out."""


class ProviderRateLimitError(ProviderRequestError):
    """Raised when a provider rate limit blocks execution."""


class AIProvider(Protocol):
    name: str

    def build_client(self, *, role: ModelRole, model_name: str) -> ModelClient:
        ...


class OpenAIProvider:
    name = 'openai'

    def __init__(
        self,
        settings: OpenAIProviderSettings,
        *,
        client_factory: Callable[[OpenAIProviderSettings], httpx.Client] | None = None,
    ) -> None:
        if settings.api_key is None:
            raise ProviderConfigurationError(
                'OpenAI provider requires JESTER_OPENAI_API_KEY when any enabled role uses provider=openai.'
            )
        self._settings = settings
        self._client_factory = client_factory or _default_http_client

    def build_client(self, *, role: ModelRole, model_name: str) -> ModelClient:
        return OpenAIChatCompletionsClient(
            role=role,
            model_name=model_name,
            settings=self._settings,
            http_client=self._client_factory(self._settings),
        )


class OpenAIChatCompletionsClient:
    def __init__(
        self,
        *,
        role: ModelRole,
        model_name: str,
        settings: OpenAIProviderSettings,
        http_client: httpx.Client,
    ) -> None:
        self._role = role
        self._model_name = model_name
        self._settings = settings
        self._http_client = http_client

    def generate(self, request: ModelRequest) -> ModelResponse:
        if request.role != self._role:
            raise ModelError(
                f'OpenAI client for role {self._role.value!r} received {request.role.value!r}.'
            )

        payload: dict[str, object] = {
            'model': self._model_name,
            'messages': [
                {'role': 'system', 'content': _system_message_for_role(request.role)},
                {'role': 'user', 'content': request.prompt},
            ],
            'temperature': request.temperature,
        }
        if request.max_tokens is not None:
            payload['max_tokens'] = request.max_tokens
        if _expects_json_response(request.prompt_name):
            payload['response_format'] = {'type': 'json_object'}

        headers = {
            'Authorization': f'Bearer {self._settings.api_key}',
            'Content-Type': 'application/json',
        }
        if self._settings.organization is not None:
            headers['OpenAI-Organization'] = self._settings.organization
        if self._settings.project is not None:
            headers['OpenAI-Project'] = self._settings.project

        started = time.perf_counter()
        try:
            response = self._http_client.post('/chat/completions', json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError('Model request timed out before the provider returned a response.') from exc
        except httpx.HTTPError as exc:
            raise ProviderRequestError(f'Model request failed before receiving a response: {exc}') from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code == 429:
            raise ProviderRateLimitError('Model provider rate limited the request.')
        if response.status_code >= 400:
            raise ProviderRequestError(_error_message_from_response(response))

        try:
            payload_json = response.json()
        except json.JSONDecodeError as exc:
            raise ProviderRequestError('Model provider returned invalid JSON.') from exc

        content = _extract_message_content(payload_json)
        usage = _extract_usage(payload_json)
        return ModelResponse(
            role=request.role,
            content=content,
            provider_name='openai',
            model_name=self._model_name,
            latency_ms=latency_ms,
            token_usage=usage,
        )


def build_model_registry(
    settings: AppSettings,
    *,
    openai_client_factory: Callable[[OpenAIProviderSettings], httpx.Client] | None = None,
) -> ModelRegistry:
    bindings = settings.ai.bindings()
    registry = ModelRegistry.from_bindings(bindings)
    enabled_bindings = {role: binding for role, binding in bindings.items() if binding.enabled}
    fake_roles = [role for role, binding in enabled_bindings.items() if binding.provider_name.lower() == 'fake']
    real_roles = [role for role, binding in enabled_bindings.items() if binding.provider_name.lower() != 'fake']

    if fake_roles and real_roles:
        fake_names = ', '.join(role.value for role in fake_roles)
        real_names = ', '.join(role.value for role in real_roles)
        raise ProviderConfigurationError(
            'Mixed fake and real model providers are not allowed in one runtime. '
            f'Fake roles: {fake_names}. Real roles: {real_names}.'
        )
    if settings.environment in {'staging', 'prod'} and fake_roles:
        raise ProviderConfigurationError('Fake model providers are not allowed in staging or prod.')

    if real_roles:
        providers = _resolve_real_providers(settings, openai_client_factory=openai_client_factory)
        for role, binding in enabled_bindings.items():
            provider_name = binding.provider_name.lower()
            if provider_name == 'fake':
                continue
            provider = providers.get(provider_name)
            if provider is None:
                raise ProviderConfigurationError(f'Unsupported model provider {binding.provider_name!r}.')
            registry.register_client(role, provider.build_client(role=role, model_name=binding.model_name))
    else:
        for role, binding in enabled_bindings.items():
            if binding.provider_name.lower() != 'fake':
                continue
            registry.register_client(
                role,
                FakeModelClient(
                    role=role,
                    provider_name=binding.provider_name,
                    model_name=binding.model_name,
                ),
            )
    return registry


def _resolve_real_providers(
    settings: AppSettings,
    *,
    openai_client_factory: Callable[[OpenAIProviderSettings], httpx.Client] | None,
) -> Mapping[str, AIProvider]:
    providers: dict[str, AIProvider] = {}
    if any(
        binding.enabled and binding.provider_name.lower() == 'openai'
        for binding in settings.ai.bindings().values()
    ):
        providers['openai'] = OpenAIProvider(
            settings.providers.openai,
            client_factory=openai_client_factory,
        )
    return providers


def _default_http_client(settings: OpenAIProviderSettings) -> httpx.Client:
    return httpx.Client(
        base_url=str(settings.base_url),
        timeout=settings.timeout_seconds,
        follow_redirects=False,
    )


def _system_message_for_role(role: ModelRole) -> str:
    if role == ModelRole.REASONING:
        return 'You are Jester reasoning runtime. Return only the requested structured result.'
    if role == ModelRole.SMALL_FAST:
        return 'You are Jester lightweight classifier. Return only the requested structured result.'
    return 'You are Jester generation runtime. Follow the prompt exactly and avoid extra framing.'


def _expects_json_response(prompt_name: str | None) -> bool:
    return prompt_name in {
        'prep_plan',
        'prep_critique',
        'teaching_structure',
        'routing_mode',
        'routing_live_dm_intent',
        'teaching_depth',
    }


def _extract_message_content(payload: Mapping[str, object]) -> str:
    choices = payload.get('choices')
    if not isinstance(choices, list) or not choices:
        raise ProviderRequestError('Model provider returned no choices.')
    choice = choices[0]
    if not isinstance(choice, Mapping):
        raise ProviderRequestError('Model provider returned an invalid choice payload.')
    message = choice.get('message')
    if not isinstance(message, Mapping):
        raise ProviderRequestError('Model provider returned no message content.')
    content = message.get('content')
    if isinstance(content, str) and content.strip():
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, Mapping):
                continue
            text = item.get('text')
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        combined = '\n'.join(parts).strip()
        if combined:
            return combined
    raise ProviderRequestError('Model provider returned an empty content payload.')


def _extract_usage(payload: Mapping[str, object]) -> dict[str, int] | None:
    usage = payload.get('usage')
    if not isinstance(usage, Mapping):
        return None
    result: dict[str, int] = {}
    for key in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
        value = usage.get(key)
        if value is None:
            continue
        result[key] = int(value)
    return result or None


def _error_message_from_response(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        body = response.text.strip()
        return body or f'Model provider returned HTTP {response.status_code}.'
    error = payload.get('error') if isinstance(payload, Mapping) else None
    if isinstance(error, Mapping):
        message = error.get('message')
        if isinstance(message, str) and message.strip():
            return message.strip()
    return f'Model provider returned HTTP {response.status_code}.'
