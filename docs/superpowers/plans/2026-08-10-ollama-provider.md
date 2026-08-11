# Ollama Local Model Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a native Ollama provider to Jester's existing model-provider seam, plus a measurement harness that produces a per-role go/no-go on whether a locally-served model can do the Narrator, Arbiter and Router roles.

**Architecture:** `OllamaProvider` implements the existing two-member `AIProvider` protocol in `jester/ai/providers.py` and registers under the key `'ollama'` in `_resolve_real_providers`. `OllamaChatClient` posts to Ollama's native `/api/chat`. `OpenAIProvider` and `OpenAIChatCompletionsClient` are **not modified**. A standalone harness under `scripts/spike/` measures real prompts against a live Ollama and writes a report.

**Tech Stack:** Python 3.12, pydantic v2, httpx (already a dependency), pytest, `httpx.MockTransport` for tests. No new runtime dependencies.

**Spec:** `docs/superpowers/specs/2026-08-10-ollama-provider-design.md`

## Global Constraints

- Python `>=3.12`. `from __future__ import annotations` at the top of every new module, matching every existing module in `jester/`.
- `jester/` is `mypy --strict` clean with **zero** exclusions. It must stay that way. Annotate everything.
- `ruff` config: `line-length = 120`, `select = ["E", "F", "I", "UP", "B", "N"]`. `jester/` carries no per-file ignores and must not acquire any.
- All pydantic settings models in `jester/config/settings.py` use `model_config = ConfigDict(extra='forbid', frozen=True)`.
- Single quotes for strings, matching the existing codebase style.
- **Do not modify `OpenAIProvider`, `OpenAIChatCompletionsClient`, or their tests.** This work is purely additive.
- **Do not touch the mixed fake/real provider guard** at `settings.py:305-311` or `providers.py:150-158`. That is audit finding D2-17, deferred to Wave R5.
- **Do not add an `api_key` field to Ollama settings.** There is no credential; adding an unused one invites the fake-value pattern the spec rejects.
- The existing test suite runs in ~2.1 s. **No test in `tests/` may contact a live Ollama.** Live inference belongs to the harness only.
- Run `.venv\Scripts\pytest`, `.venv\Scripts\ruff check .`, `.venv\Scripts\mypy` before each commit.

## File Structure

| File | Responsibility |
|---|---|
| `jester/config/settings.py` *(modify)* | Add `OllamaProviderSettings`; add `ollama` field to `ProviderSettings`; wire env vars in `load_settings` |
| `jester/ai/providers.py` *(modify)* | Add `OllamaProvider`, `OllamaChatClient`, three module-level helpers; register in `_resolve_real_providers`; extend `build_model_registry` signature |
| `tests/test_ollama_provider.py` *(create)* | 13 hermetic tests — 3 settings, the spec's 9 client cases, 1 registry wiring |
| `scripts/spike/ollama_eval.py` *(create)* | Harness entry point, CLI, environment capture, measured call, oversubscription detection |
| `scripts/spike/prompt_suite.py` *(create)* | Prompt/role mapping, fixture values, per-role result checks, report rendering |

`scripts/` sits outside `pyproject.toml`'s `[tool.setuptools.packages.find] include = ["jester*", "pipeline*", "training*"]`, so harness code can never ship in a wheel.

---

### Task 1: Ollama provider settings

**Files:**
- Modify: `jester/config/settings.py` (add class after `OpenAIProviderSettings` at line 156; add field to `ProviderSettings` at line 161; wire env in `load_settings` at line 399)
- Test: `tests/test_ollama_provider.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `OllamaProviderSettings(base_url: str, timeout_seconds: float, num_ctx: int, think: bool, keep_alive: str | None)`, importable from `jester.config.settings`. `ProviderSettings.ollama: OllamaProviderSettings`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_ollama_provider.py`:

```python
from __future__ import annotations

import httpx
import pytest

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_ollama_provider.py -v`
Expected: FAIL with `ImportError: cannot import name 'OllamaProviderSettings'`

- [ ] **Step 3: Add the settings model**

In `jester/config/settings.py`, insert immediately after `OpenAIProviderSettings` (after line 156, before `class ProviderSettings`):

```python
class OllamaProviderSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    base_url: str = 'http://127.0.0.1:11434'
    timeout_seconds: float = Field(default=300.0, gt=0.0, le=1800.0)
    num_ctx: int = Field(default=4096, ge=256, le=131072)
    think: bool = False
    keep_alive: str | None = None

    @field_validator('base_url', mode='before')
    @classmethod
    def strip_base_url(cls, value: object) -> str:
        text = str(value).strip().rstrip('/')
        if not text:
            raise ValueError('base_url must not be blank.')
        return text

    @field_validator('keep_alive', mode='before')
    @classmethod
    def strip_keep_alive(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
```

- [ ] **Step 4: Add the field to `ProviderSettings`**

Change `ProviderSettings` (currently line 158-161) to:

```python
class ProviderSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    openai: OpenAIProviderSettings = Field(default_factory=OpenAIProviderSettings)
    ollama: OllamaProviderSettings = Field(default_factory=OllamaProviderSettings)
```

- [ ] **Step 5: Wire the environment variables**

In `load_settings`, the `providers=ProviderSettings(...)` block currently ends at line 407 with the closing paren of `OpenAIProviderSettings(...)`. Add a sibling argument so the block reads:

```python
            providers=ProviderSettings(
                openai=OpenAIProviderSettings(
                    api_key=_parse_optional_text(values.get('JESTER_OPENAI_API_KEY')),
                    base_url=values.get('JESTER_OPENAI_BASE_URL', 'https://api.openai.com/v1'),
                    timeout_seconds=float(values.get('JESTER_OPENAI_TIMEOUT_SECONDS', '30.0')),
                    organization=_parse_optional_text(values.get('JESTER_OPENAI_ORGANIZATION')),
                    project=_parse_optional_text(values.get('JESTER_OPENAI_PROJECT')),
                ),
                ollama=OllamaProviderSettings(
                    base_url=values.get('JESTER_OLLAMA_BASE_URL', 'http://127.0.0.1:11434'),
                    timeout_seconds=float(values.get('JESTER_OLLAMA_TIMEOUT_SECONDS', '300.0')),
                    num_ctx=int(values.get('JESTER_OLLAMA_NUM_CTX', '4096')),
                    think=_parse_bool(values.get('JESTER_OLLAMA_THINK'), default=False),
                    keep_alive=_parse_optional_text(values.get('JESTER_OLLAMA_KEEP_ALIVE')),
                ),
            ),
```

`_parse_bool` and `_parse_optional_text` already exist in this module and are used by the surrounding code.

Do **not** add anything to `AppSettings.validate_runtime_guards`. Ollama needs no credential, so it needs no guard.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/test_ollama_provider.py -v`
Expected: 3 passed

- [ ] **Step 7: Verify gates and commit**

```bash
.venv/Scripts/pytest -q
.venv/Scripts/ruff check .
.venv/Scripts/mypy
git add jester/config/settings.py tests/test_ollama_provider.py
git commit -m "feat: add OllamaProviderSettings with num_ctx and think controls"
```

---

### Task 2: Ollama chat client — request construction and response mapping

**Files:**
- Modify: `jester/ai/providers.py` (add client class and two helpers after `OpenAIChatCompletionsClient`, which ends at line 136)
- Test: `tests/test_ollama_provider.py`

**Interfaces:**
- Consumes: `OllamaProviderSettings` from Task 1.
- Produces: `OllamaChatClient(*, role: ModelRole, model_name: str, settings: OllamaProviderSettings, http_client: httpx.Client)` with `generate(request: ModelRequest) -> ModelResponse`. Module-level `_extract_ollama_content(payload: Mapping[str, object], *, model_name: str) -> str` and `_extract_ollama_usage(payload: Mapping[str, object]) -> dict[str, int] | None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ollama_provider.py`:

```python
from jester.ai import ModelRequest, ModelRole
from jester.ai.providers import OllamaChatClient


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
```

Add these to the test module's imports: `import json`, `from collections.abc import Callable`, and
`from jester.ai.base import ModelError`.

**No `# type: ignore` comments anywhere in this task.** `tests` is inside `[tool.mypy] packages`, so this
module is checked under `--strict`, and strict enables `warn_unused_ignores` — a stale ignore becomes an
error. Typing the handler alias as `Callable[[httpx.Request], httpx.Response]` satisfies
`httpx.MockTransport` directly.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/test_ollama_provider.py -v`
Expected: FAIL with `ImportError: cannot import name 'OllamaChatClient'`

- [ ] **Step 3: Add the client and helpers**

In `jester/ai/providers.py`, extend the `TYPE_CHECKING` import block (line 14-15) to:

```python
if TYPE_CHECKING:
    from jester.config.settings import AppSettings, OllamaProviderSettings, OpenAIProviderSettings
```

Then add after `OpenAIChatCompletionsClient` (after line 136):

```python
class OllamaChatClient:
    def __init__(
        self,
        *,
        role: ModelRole,
        model_name: str,
        settings: OllamaProviderSettings,
        http_client: httpx.Client,
    ) -> None:
        self._role = role
        self._model_name = model_name
        self._settings = settings
        self._http_client = http_client

    def generate(self, request: ModelRequest) -> ModelResponse:
        if request.role != self._role:
            raise ModelError(
                f'Ollama client for role {self._role.value!r} received {request.role.value!r}.'
            )

        options: dict[str, object] = {
            'temperature': request.temperature,
            'num_ctx': self._settings.num_ctx,
        }
        if request.max_tokens is not None:
            options['num_predict'] = request.max_tokens

        payload: dict[str, object] = {
            'model': self._model_name,
            'stream': False,
            'think': self._settings.think,
            'messages': [
                {'role': 'system', 'content': _system_message_for_role(request.role)},
                {'role': 'user', 'content': request.prompt},
            ],
            'options': options,
        }
        if _expects_json_response(request.prompt_name):
            payload['format'] = 'json'
        if self._settings.keep_alive is not None:
            payload['keep_alive'] = self._settings.keep_alive

        started = time.perf_counter()
        response = self._http_client.post('/api/chat', json=payload)
        latency_ms = int((time.perf_counter() - started) * 1000)

        payload_json = response.json()
        content = _extract_ollama_content(payload_json, model_name=self._model_name)
        usage = _extract_ollama_usage(payload_json)
        return ModelResponse(
            role=request.role,
            content=content,
            provider_name='ollama',
            model_name=self._model_name,
            latency_ms=latency_ms,
            token_usage=usage,
        )


def _extract_ollama_content(payload: Mapping[str, object], *, model_name: str) -> str:
    message = payload.get('message')
    if not isinstance(message, Mapping):
        raise ProviderRequestError('Ollama returned no message payload.')
    content = message.get('content')
    if isinstance(content, str) and content.strip():
        return content.strip()
    thinking = message.get('thinking')
    if isinstance(thinking, str) and thinking.strip():
        raise ProviderRequestError(
            f'Model {model_name!r} returned reasoning tokens but no answer. It is a thinking model '
            'whose token budget was exhausted before it replied. Set JESTER_OLLAMA_THINK=false or '
            'raise max_tokens.'
        )
    raise ProviderRequestError('Ollama returned an empty content payload.')


def _extract_ollama_usage(payload: Mapping[str, object]) -> dict[str, int] | None:
    prompt_tokens = payload.get('prompt_eval_count')
    completion_tokens = payload.get('eval_count')
    usage: dict[str, int] = {}
    if isinstance(prompt_tokens, int):
        usage['prompt_tokens'] = prompt_tokens
    if isinstance(completion_tokens, int):
        usage['completion_tokens'] = completion_tokens
    if not usage:
        return None
    usage['total_tokens'] = usage.get('prompt_tokens', 0) + usage.get('completion_tokens', 0)
    return usage
```

Error handling around the HTTP call is deliberately absent here — Task 3 adds it with its own tests.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/test_ollama_provider.py -v`
Expected: 7 passed

- [ ] **Step 5: Verify gates and commit**

```bash
.venv/Scripts/pytest -q
.venv/Scripts/ruff check .
.venv/Scripts/mypy
git add jester/ai/providers.py tests/test_ollama_provider.py
git commit -m "feat: add OllamaChatClient request construction and response mapping"
```

---

### Task 3: Ollama chat client — error mapping

**Files:**
- Modify: `jester/ai/providers.py` (wrap the HTTP call added in Task 2; add `_ollama_error_message`)
- Test: `tests/test_ollama_provider.py`

**Interfaces:**
- Consumes: `OllamaChatClient` from Task 2.
- Produces: `_ollama_error_message(response: httpx.Response) -> str`. No signature changes.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_ollama_provider.py`:

```python
from jester.ai.providers import ProviderConfigurationError, ProviderRequestError, ProviderTimeoutError


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\pytest tests/test_ollama_provider.py -v`
Expected: the three error-mapping tests FAIL (raw `httpx` exceptions propagate; the 404 surfaces as a `json.JSONDecodeError` or a content error rather than `ProviderConfigurationError`). `test_ollama_client_raises_when_only_reasoning_tokens_returned` should already PASS from Task 2.

- [ ] **Step 3: Replace the bare HTTP call with mapped error handling**

In `OllamaChatClient.generate`, replace these three lines:

```python
        started = time.perf_counter()
        response = self._http_client.post('/api/chat', json=payload)
        latency_ms = int((time.perf_counter() - started) * 1000)

        payload_json = response.json()
```

with:

```python
        started = time.perf_counter()
        try:
            response = self._http_client.post('/api/chat', json=payload)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                'Ollama did not respond before the timeout. Local generation can be slow on a cold '
                'model load or when the model does not fit in VRAM; raise '
                'JESTER_OLLAMA_TIMEOUT_SECONDS or lower JESTER_OLLAMA_NUM_CTX.'
            ) from exc
        except httpx.ConnectError as exc:
            raise ProviderRequestError(
                f'Ollama is not reachable at {self._settings.base_url!r} - is the Ollama service '
                'running?'
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderRequestError(f'Ollama request failed before a response: {exc}') from exc

        latency_ms = int((time.perf_counter() - started) * 1000)

        if response.status_code == 404:
            raise ProviderConfigurationError(
                f'Ollama has no model named {self._model_name!r}. Pull it with: '
                f'ollama pull {self._model_name}'
            )
        if response.status_code >= 400:
            raise ProviderRequestError(_ollama_error_message(response))

        try:
            payload_json = response.json()
        except json.JSONDecodeError as exc:
            raise ProviderRequestError('Ollama returned invalid JSON.') from exc
```

`httpx.TimeoutException` must be caught before `httpx.ConnectError`, and both before `httpx.HTTPError` — all three are subclasses of `httpx.HTTPError` and Python matches the first arm.

Then add after `_extract_ollama_usage`:

```python
def _ollama_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        body = response.text.strip()
        return body or f'Ollama returned HTTP {response.status_code}.'
    if isinstance(payload, Mapping):
        error = payload.get('error')
        if isinstance(error, str) and error.strip():
            return error.strip()
    return f'Ollama returned HTTP {response.status_code}.'
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/test_ollama_provider.py -v`
Expected: 12 passed

- [ ] **Step 5: Verify gates and commit**

```bash
.venv/Scripts/pytest -q
.venv/Scripts/ruff check .
.venv/Scripts/mypy
git add jester/ai/providers.py tests/test_ollama_provider.py
git commit -m "feat: map Ollama transport and HTTP failures to provider errors"
```

---

### Task 4: Provider registration

**Files:**
- Modify: `jester/ai/providers.py` (add `OllamaProvider` and `_default_ollama_http_client`; extend `build_model_registry` at line 139-143 and `_resolve_real_providers` at line 185-199)
- Test: `tests/test_ollama_provider.py`

**Interfaces:**
- Consumes: `OllamaChatClient` from Tasks 2-3, `OllamaProviderSettings` from Task 1.
- Produces: `OllamaProvider(settings, *, client_factory=None)` with `name = 'ollama'` and `build_client(*, role, model_name) -> ModelClient`. `build_model_registry` gains keyword argument `ollama_client_factory: Callable[[OllamaProviderSettings], httpx.Client] | None = None`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ollama_provider.py`:

```python
from jester.ai import ModelSelectionPolicy, build_model_registry
from jester.ai.providers import OllamaChatClient as _OllamaChatClient


def test_build_model_registry_registers_ollama_clients() -> None:
    settings = load_settings(
        {
            'JESTER_ENVIRONMENT': 'dev',
            'JESTER_PRIMARY_PROVIDER': 'ollama',
            'JESTER_PRIMARY_MODEL': 'qwen3.5:4b',
            'JESTER_REASONING_PROVIDER': 'ollama',
            'JESTER_REASONING_MODEL': 'qwen3.5:4b',
            'JESTER_SMALL_FAST_PROVIDER': 'ollama',
            'JESTER_SMALL_FAST_MODEL': 'qwen3.5:4b',
        }
    )

    def factory(_: OllamaProviderSettings) -> httpx.Client:
        return httpx.Client(
            base_url='http://127.0.0.1:11434',
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={'message': {'content': 'ok'}})
            ),
        )

    registry = build_model_registry(settings, ollama_client_factory=factory)
    policy = ModelSelectionPolicy(registry)

    selected = policy.require(ModelRole.PRIMARY_GENERATION)
    assert isinstance(selected.client, _OllamaChatClient)
    assert selected.selection.provider_name == 'ollama'
    assert selected.selection.model_name == 'qwen3.5:4b'
```

Note: `ModelSelectionPolicy.require` returns a `SelectedModelClient` dataclass
(`jester/ai/selection.py:11`) with `.selection: ModelSelection` and `.client: ModelClient` — not a bare
client. There is no `describe` method; `resolve(role) -> ModelSelection` is the equivalent.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\pytest tests/test_ollama_provider.py::test_build_model_registry_registers_ollama_clients -v`
Expected: FAIL with `ProviderConfigurationError: Unsupported model provider 'ollama'.`

- [ ] **Step 3: Add the provider class and its client factory**

In `jester/ai/providers.py`, add after `OpenAIProvider` (after line 63):

```python
class OllamaProvider:
    name = 'ollama'

    def __init__(
        self,
        settings: OllamaProviderSettings,
        *,
        client_factory: Callable[[OllamaProviderSettings], httpx.Client] | None = None,
    ) -> None:
        self._settings = settings
        self._client_factory = client_factory or _default_ollama_http_client

    def build_client(self, *, role: ModelRole, model_name: str) -> ModelClient:
        return OllamaChatClient(
            role=role,
            model_name=model_name,
            settings=self._settings,
            http_client=self._client_factory(self._settings),
        )
```

And add beside `_default_http_client` (after line 207):

```python
def _default_ollama_http_client(settings: OllamaProviderSettings) -> httpx.Client:
    return httpx.Client(
        base_url=settings.base_url,
        timeout=settings.timeout_seconds,
        follow_redirects=False,
    )
```

- [ ] **Step 4: Thread the factory through registry construction**

Change the `build_model_registry` signature (line 139-143) to:

```python
def build_model_registry(
    settings: AppSettings,
    *,
    openai_client_factory: Callable[[OpenAIProviderSettings], httpx.Client] | None = None,
    ollama_client_factory: Callable[[OllamaProviderSettings], httpx.Client] | None = None,
) -> ModelRegistry:
```

Change its single call to `_resolve_real_providers` (line 161) to:

```python
        providers = _resolve_real_providers(
            settings,
            openai_client_factory=openai_client_factory,
            ollama_client_factory=ollama_client_factory,
        )
```

Change `_resolve_real_providers` (line 185-199) to:

```python
def _resolve_real_providers(
    settings: AppSettings,
    *,
    openai_client_factory: Callable[[OpenAIProviderSettings], httpx.Client] | None,
    ollama_client_factory: Callable[[OllamaProviderSettings], httpx.Client] | None,
) -> Mapping[str, AIProvider]:
    providers: dict[str, AIProvider] = {}
    bindings = settings.ai.bindings().values()
    if any(binding.enabled and binding.provider_name.lower() == 'openai' for binding in bindings):
        providers['openai'] = OpenAIProvider(
            settings.providers.openai,
            client_factory=openai_client_factory,
        )
    if any(binding.enabled and binding.provider_name.lower() == 'ollama' for binding in bindings):
        providers['ollama'] = OllamaProvider(
            settings.providers.ollama,
            client_factory=ollama_client_factory,
        )
    return providers
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv\Scripts\pytest tests/test_ollama_provider.py -v`
Expected: 13 passed

- [ ] **Step 6: Verify gates and commit**

```bash
.venv/Scripts/pytest -q
.venv/Scripts/ruff check .
.venv/Scripts/mypy
git add jester/ai/providers.py tests/test_ollama_provider.py
git commit -m "feat: register OllamaProvider in the model registry"
```

---

### Task 5: Harness core — environment capture and measured call

**Files:**
- Create: `scripts/spike/__init__.py` (empty)
- Create: `scripts/spike/ollama_eval.py`

**Interfaces:**
- Consumes: nothing from `jester.ai` — see the note below.
- Produces: `capture_environment() -> dict[str, str]`, `MeasuredCall` dataclass with fields `content: str`, `thinking: str`, `latency_s: float`, `prompt_tokens: int`, `eval_tokens: int`, `prompt_tok_s: float`, `gen_tok_s: float`, `done_reason: str`, and `call_ollama(...) -> MeasuredCall`, plus `is_oversubscribed(call: MeasuredCall) -> bool`.

**Why the harness calls Ollama directly rather than through `OllamaChatClient`:** it needs `prompt_eval_duration` and `eval_duration`, which `ModelResponse` deliberately does not expose. The oversubscription detector is built from exactly those two fields. The client is covered by Tasks 1-4; the harness's job is measuring the model.

- [ ] **Step 1: Create the package marker**

```bash
mkdir -p scripts/spike
touch scripts/spike/__init__.py
```

- [ ] **Step 2: Write the harness core**

Create `scripts/spike/ollama_eval.py`:

```python
"""Spike harness: measure a local Ollama model against Jester's real prompts.

Not production code. Lives outside the packaged trees on purpose - pyproject's
packages.find includes only jester*, pipeline* and training*.
"""

from __future__ import annotations

import argparse
import statistics
import subprocess
import time
from dataclasses import dataclass, field

import httpx

OVERSUBSCRIPTION_RATIO = 0.05


@dataclass(frozen=True)
class MeasuredCall:
    content: str
    thinking: str
    latency_s: float
    prompt_tokens: int
    eval_tokens: int
    prompt_tok_s: float
    gen_tok_s: float
    done_reason: str


@dataclass
class RoleResult:
    role: str
    prompt_name: str
    calls: list[MeasuredCall] = field(default_factory=list)
    passes: list[bool] = field(default_factory=list)


def _run(command: list[str]) -> str:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return 'unavailable'
    return completed.stdout.strip() or 'unavailable'


def capture_environment() -> dict[str, str]:
    return {
        'ollama_ps': _run(['ollama', 'ps']),
        'gpu': _run(
            [
                'nvidia-smi',
                '--query-gpu=memory.used,memory.free,utilization.gpu',
                '--format=csv,noheader',
            ]
        ),
    }


def call_ollama(
    client: httpx.Client,
    *,
    model: str,
    prompt: str,
    num_ctx: int,
    think: bool,
    num_predict: int,
    temperature: float,
    json_format: bool,
) -> MeasuredCall:
    payload: dict[str, object] = {
        'model': model,
        'stream': False,
        'think': think,
        'messages': [{'role': 'user', 'content': prompt}],
        'options': {
            'temperature': temperature,
            'num_ctx': num_ctx,
            'num_predict': num_predict,
        },
    }
    if json_format:
        payload['format'] = 'json'

    started = time.perf_counter()
    response = client.post('/api/chat', json=payload)
    latency_s = time.perf_counter() - started
    response.raise_for_status()
    body = response.json()

    message = body.get('message') or {}
    prompt_tokens = int(body.get('prompt_eval_count') or 0)
    eval_tokens = int(body.get('eval_count') or 0)
    prompt_ns = int(body.get('prompt_eval_duration') or 0)
    eval_ns = int(body.get('eval_duration') or 0)

    return MeasuredCall(
        content=str(message.get('content') or ''),
        thinking=str(message.get('thinking') or ''),
        latency_s=latency_s,
        prompt_tokens=prompt_tokens,
        eval_tokens=eval_tokens,
        prompt_tok_s=prompt_tokens / (prompt_ns / 1e9) if prompt_ns else 0.0,
        gen_tok_s=eval_tokens / (eval_ns / 1e9) if eval_ns else 0.0,
        done_reason=str(body.get('done_reason') or ''),
    )


def is_oversubscribed(call: MeasuredCall) -> bool:
    """Generation far slower than prompt eval means VRAM is paging to system RAM.

    Measured 2026-08-10: 709 tok/s prompt against 3.0 tok/s generation while
    `ollama ps` reported 100% GPU. Placement alone called that run healthy.
    """
    if call.prompt_tok_s <= 0 or call.gen_tok_s <= 0:
        return False
    return (call.gen_tok_s / call.prompt_tok_s) < OVERSUBSCRIPTION_RATIO


def summarize(values: list[float]) -> str:
    if not values:
        return 'n/a'
    ordered = sorted(values)
    p50 = statistics.median(ordered)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    return f'p50 {p50:.1f} / p95 {p95:.1f}'


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Measure a local Ollama model against Jester prompts.')
    parser.add_argument('--model', default='qwen3.5:4b')
    parser.add_argument('--base-url', default='http://127.0.0.1:11434')
    parser.add_argument('--num-ctx', type=int, default=4096)
    parser.add_argument('--think', action='store_true')
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--timeout', type=float, default=600.0)
    parser.add_argument('--out-dir', default='scripts/spike/out')
    return parser
```

- [ ] **Step 3: Verify it imports and the CLI parses**

Run: `.venv\Scripts\python -c "from scripts.spike.ollama_eval import build_parser; print(build_parser().parse_args(['--model','x']))"`
Expected: prints a `Namespace` with `model='x'`, `num_ctx=4096`, `think=False`

- [ ] **Step 4: Verify environment capture works**

Run: `.venv\Scripts\python -c "from scripts.spike.ollama_eval import capture_environment; print(capture_environment())"`
Expected: a dict with `ollama_ps` and `gpu` keys. Values may be `unavailable` on a machine without Ollama or an NVIDIA GPU — that is correct behaviour, not a failure.

- [ ] **Step 5: Commit**

```bash
.venv/Scripts/ruff check .
git add scripts/spike/__init__.py scripts/spike/ollama_eval.py
git commit -m "feat: add Ollama spike harness core with oversubscription detection"
```

---

### Task 6: Harness suite — prompts, checks and report

**Files:**
- Create: `scripts/spike/prompt_suite.py`
- Modify: `scripts/spike/ollama_eval.py` (add `main()` and the `__main__` guard)

**Interfaces:**
- Consumes: `MeasuredCall`, `RoleResult`, `call_ollama`, `capture_environment`, `is_oversubscribed`, `summarize`, `build_parser` from Task 5.
- Produces: `SUITE: list[PromptCase]`, `render_prompt(name: str, version: str) -> tuple[str, dict[str, str]]`, `check_call(case: PromptCase, content: str, output_contract: dict[str, str]) -> bool`.

- [ ] **Step 1: Write the prompt suite**

Create `scripts/spike/prompt_suite.py`:

```python
"""Prompt cases, fixture values and per-role checks for the Ollama spike harness."""

from __future__ import annotations

import json
from dataclasses import dataclass

from jester.prompts.registry import load_prompt
from jester.validation import validate_output

# Fixture values keyed by input_contract variable name. Prompts share variable
# names, so one table covers the whole suite. Values are deliberately realistic -
# invented prompts would not answer the question the spike exists to answer.
FIXTURES: dict[str, str] = {
    'state_summary': (
        'Scene: the Copper Vault, a smugglers hideout beneath the old customs house. '
        'Party: Aria (fighter, 24/30 HP), Bram (cleric, 19/22 HP). '
        'Enemies: Goblin Lookout (7/12 HP, prone). Round 2, Aria to act.'
    ),
    'action_summary': 'Aria attacks the Goblin Lookout with a longsword and hits for 7 slashing damage.',
    'retrieved_context': (
        'Attack Roll Sequence: roll d20, add ability modifier and proficiency, compare to AC. '
        'Damage Step: on a hit, roll the weapon damage die and add the ability modifier.'
    ),
    'artifact_type': 'NPC_BRIEF',
    'topic': 'Sera Duskwater, harbourmaster of Stonebridge',
    'goal': 'Give the party a reason to investigate the missing cargo manifest',
    'inputs_used': 'campaign notes, previous session summary',
    'concept': 'ATTACK_ROLLS',
    'question': 'How does cover affect an attack roll?',
    'request_text': 'I want to sneak past the guards and reach the vault door.',
    'depth': 'STANDARD',
    'lesson_focus': 'attack rolls and armour class',
}


@dataclass(frozen=True)
class PromptCase:
    role: str
    prompt_name: str
    version: str
    expects_json: bool
    num_predict: int
    temperature: float


SUITE: list[PromptCase] = [
    PromptCase('router', 'routing_live_dm_intent', 'v1', True, 256, 0.0),
    PromptCase('router', 'teaching_depth', 'v1', True, 256, 0.0),
    PromptCase('arbiter', 'prep_plan', 'v1', True, 512, 0.0),
    PromptCase('arbiter', 'prep_critique', 'v1', True, 512, 0.0),
    PromptCase('arbiter', 'teaching_structure', 'v1', True, 512, 0.0),
    PromptCase('narrator', 'live_dm_narration', 'v1', False, 384, 0.2),
    PromptCase('narrator', 'live_dm_info_response', 'v1', False, 384, 0.2),
    PromptCase('narrator', 'prep_npc', 'v1', False, 512, 0.2),
    PromptCase('narrator', 'teaching_explain_concept', 'v1', False, 512, 0.2),
]


def render_prompt(name: str, version: str) -> tuple[str, dict[str, str]]:
    """Render a real prompt with fixture values. Returns (rendered, output_contract)."""
    spec = load_prompt(name, version)
    values = {key: FIXTURES.get(key, f'[no fixture for {key}]') for key in spec.input_contract}
    return spec.template.format(**values), dict(spec.output_contract)


def check_call(case: PromptCase, content: str, output_contract: dict[str, str]) -> bool:
    if case.expects_json:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return False
        if not isinstance(parsed, dict):
            return False
        return all(key in parsed for key in output_contract)
    return bool(validate_output(content).is_valid)
```

Both APIs used here are verified against the source: `load_prompt(name, version, *, prompt_root=None)`
returns a `PromptSpec` exposing `.template`, `.input_contract: dict[str, Any]` and
`.output_contract: dict[str, Any]` (`jester/prompts/registry.py:18-27, 63`); `validate_output(text, policy=None, *, rules=None) -> ValidationResult`
is exported from `jester.validation` and its result carries `.is_valid` and `.issues`
(`jester/validation/output_validator.py:164`).

Note that `validate_output` applies `AnachronismRule`, whose 10-word denylist the audit found
false-positives on legitimate fantasy prose — "streaming" through a window fails it (finding D2-06).
Narrator pass rates below 100% should be checked against `samples.md` before being read as a model
failure. That is a known defect in Jester, not in the model.

- [ ] **Step 2: Verify prompts render**

Run: `.venv\Scripts\python -c "from scripts.spike.prompt_suite import SUITE, render_prompt; [print(c.prompt_name, len(render_prompt(c.prompt_name, c.version)[0])) for c in SUITE]"`
Expected: nine lines, each with a character count in the hundreds. A `KeyError` means a prompt uses a variable missing from `FIXTURES` — add it there.

- [ ] **Step 3: Add `main()` to the harness**

Append to `scripts/spike/ollama_eval.py`:

```python
def main() -> int:
    from scripts.spike.prompt_suite import SUITE, check_call, render_prompt

    args = build_parser().parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    env_before = capture_environment()
    client = httpx.Client(base_url=args.base_url, timeout=args.timeout)
    results: list[RoleResult] = []
    samples: list[str] = []
    oversubscribed = False

    for case in SUITE:
        prompt, output_contract = render_prompt(case.prompt_name, case.version)
        result = RoleResult(role=case.role, prompt_name=case.prompt_name)
        for _ in range(args.repetitions):
            call = call_ollama(
                client,
                model=args.model,
                prompt=prompt,
                num_ctx=args.num_ctx,
                think=args.think,
                num_predict=case.num_predict,
                temperature=case.temperature,
                json_format=case.expects_json,
            )
            result.calls.append(call)
            result.passes.append(check_call(case, call.content, output_contract))
            oversubscribed = oversubscribed or is_oversubscribed(call)
        results.append(result)
        if not case.expects_json and result.calls:
            samples.append(f'## {case.prompt_name}\n\n{result.calls[0].content}\n')
        print(f'{case.role:9} {case.prompt_name:28} {sum(result.passes)}/{len(result.passes)}')

    env_after = capture_environment()
    report = _render_report(args, env_before, env_after, results, oversubscribed)
    (out_dir / 'report.md').write_text(report, encoding='utf-8')
    (out_dir / 'samples.md').write_text('\n'.join(samples), encoding='utf-8')
    print(f'\nWrote {out_dir / "report.md"} and {out_dir / "samples.md"}')
    return 0


def _render_report(
    args: argparse.Namespace,
    env_before: dict[str, str],
    env_after: dict[str, str],
    results: list[RoleResult],
    oversubscribed: bool,
) -> str:
    lines = [
        f'# Ollama spike report - {args.model}',
        '',
        f'num_ctx {args.num_ctx} | think {args.think} | repetitions {args.repetitions}',
        '',
    ]
    if oversubscribed:
        lines += [
            '> **VRAM OVERSUBSCRIPTION DETECTED.** Generation ran at under 5% of prompt-eval rate.',
            '> The model does not fit in available VRAM and the driver is paging to system RAM.',
            '> Latency figures below are not representative. Free VRAM or use a smaller model.',
            '',
        ]
    lines += ['| role | prompt | pass | gen tok/s | latency s |', '|---|---|---|---|---|']
    for result in results:
        rate = summarize([call.gen_tok_s for call in result.calls])
        latency = summarize([call.latency_s for call in result.calls])
        lines.append(
            f'| {result.role} | {result.prompt_name} | '
            f'{sum(result.passes)}/{len(result.passes)} | {rate} | {latency} |'
        )
    lines += [
        '',
        '## Environment before',
        '```',
        env_before['ollama_ps'],
        env_before['gpu'],
        '```',
        '',
        '## Environment after',
        '```',
        env_after['ollama_ps'],
        env_after['gpu'],
        '```',
    ]
    return '\n'.join(lines)


if __name__ == '__main__':
    raise SystemExit(main())
```

Add `from pathlib import Path` to the imports at the top of `ollama_eval.py`.

- [ ] **Step 4: Run the harness against the baseline model**

Run: `.venv\Scripts\python -m scripts.spike.ollama_eval --model mistral:latest --repetitions 1`
Expected: nine progress lines, then a report path. `mistral` first because it is already pulled and is not a thinking model, so a failure here indicates a harness bug rather than a model result.

- [ ] **Step 5: Run against the primary candidate**

`qwen3.5:4b` must be pulled first (3.4 GB) — confirm with the repo owner before downloading.

```bash
ollama pull qwen3.5:4b
.venv/Scripts/python -m scripts.spike.ollama_eval --model qwen3.5:4b --repetitions 3
```

Expected: `report.md` with a per-role pass table and no oversubscription banner. If the banner appears, lower `--num-ctx` or free VRAM and rerun before drawing any conclusion.

- [ ] **Step 6: Commit**

```bash
.venv/Scripts/ruff check .
git add scripts/spike/prompt_suite.py scripts/spike/ollama_eval.py
git commit -m "feat: add Ollama spike prompt suite and report generation"
```

---

## Verification gates

- [ ] `.venv\Scripts\pytest` passes with 13 new tests and no regressions (180 existing + 13 = 193)
- [ ] Suite still completes in roughly 2 s — no test contacts a live Ollama
- [ ] `.venv\Scripts\ruff check .` clean, with no new per-file ignores
- [ ] `.venv\Scripts\mypy` reports success with no new exclusions
- [ ] `git diff --stat` shows no changes to `OpenAIProvider`, `OpenAIChatCompletionsClient`, or the mixed-provider guard
- [ ] `scripts/spike/out/report.md` exists with a per-role pass table and captured environment

## Out of scope

Streaming · retry and backoff (D2-13) · health-endpoint integration (CQ-011) · relaxing the mixed fake/real provider guard (D2-17) · per-role provider splitting · extracting a shared `ChatCompletionsClient` base · any Wave R1 remediation.
