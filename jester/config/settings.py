from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from jester.ai.contracts import ModelRole, ModelRoleBinding
from jester.ingestion.filtering import IngestionPolicy
from jester.validation.output_validator import OutputValidationPolicy


class SettingsError(ValueError):
    """Raised when Jester startup configuration is invalid."""


EnvironmentName = Literal['dev', 'test', 'staging', 'prod']
CorpusProfileName = Literal['arbiter', 'narrator']


def _default_prompt_root() -> Path:
    return Path(__file__).resolve().parents[2] / 'prompts'


def _default_state_db_path() -> Path:
    return Path(__file__).resolve().parents[2] / 'jester_state.sqlite3'


def _default_corpus_root() -> Path:
    return Path(__file__).resolve().parents[2] / 'data' / 'corpora'


def _default_world_corpus_path() -> Path:
    return _default_corpus_root() / 'narrator_world_v1.jsonl'


def _default_rules_corpus_path() -> Path:
    return _default_corpus_root() / 'arbiter_rules_v1.jsonl'


def _split_csv(raw_value: str | None) -> list[str]:
    if raw_value is None:
        return []
    return [item.strip() for item in raw_value.split(',') if item.strip()]


def _parse_bool(raw_value: str | None, *, default: bool) -> bool:
    if raw_value is None:
        return default
    normalized = raw_value.strip().lower()
    if normalized in {'1', 'true', 'yes', 'on'}:
        return True
    if normalized in {'0', 'false', 'no', 'off'}:
        return False
    raise ValueError(f'Expected a boolean value, received {raw_value!r}.')


def _parse_optional_int(raw_value: str | None) -> int | None:
    if raw_value is None or not raw_value.strip():
        return None
    return int(raw_value)


def _parse_optional_text(raw_value: str | None) -> str | None:
    if raw_value is None:
        return None
    text = raw_value.strip()
    return text or None


class LoggingSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR'] = 'INFO'


class RetrievalSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    default_top_k: int = Field(default=5, ge=1, le=25)
    bm25_weight: float = Field(default=1.0, gt=0.0)
    vector_weight: float = Field(default=0.85, gt=0.0)
    cache_ttl_seconds: int = Field(default=60, ge=0)


class PromptRegistrySettings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    prompt_root: Path

    @field_validator('prompt_root')
    @classmethod
    def ensure_prompt_root_exists(cls, value: Path) -> Path:
        resolved = value.expanduser().resolve()
        if not resolved.exists():
            raise ValueError(f'Prompt root does not exist: {resolved}')
        if not resolved.is_dir():
            raise ValueError(f'Prompt root must be a directory: {resolved}')
        return resolved


class StateStoreSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    sqlite_path: Path

    @field_validator('sqlite_path')
    @classmethod
    def normalize_sqlite_path(cls, value: Path) -> Path:
        return value.expanduser().resolve()


class NarrationSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    prompt_name: str = 'narration'
    prompt_version: str = 'v2'


class ApiSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    host: str = '127.0.0.1'
    port: int = Field(default=8000, ge=1, le=65535)
    require_api_key: bool = False
    api_keys: list[str] = Field(default_factory=list)
    enable_narration: bool = True
    default_tenant_id: str = Field(default='default', min_length=1)
    max_request_chars: int = Field(default=2000, ge=100, le=20000)

    @model_validator(mode='after')
    def validate_api_keys(self) -> ApiSettings:
        if self.require_api_key and not self.api_keys:
            raise ValueError('api_keys must be configured when require_api_key is true.')
        return self


class OpenAIProviderSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    api_key: str | None = None
    base_url: str = 'https://api.openai.com/v1'
    timeout_seconds: float = Field(default=30.0, gt=0.0, le=120.0)
    organization: str | None = None
    project: str | None = None

    @field_validator('api_key', 'base_url', 'organization', 'project', mode='before')
    @classmethod
    def strip_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


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


class ProviderSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    openai: OpenAIProviderSettings = Field(default_factory=OpenAIProviderSettings)
    ollama: OllamaProviderSettings = Field(default_factory=OllamaProviderSettings)


class CorpusSourceSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    corpus_id: str = Field(min_length=1)
    profile: CorpusProfileName
    path: Path
    version: str = Field(min_length=1)
    source_type: str = Field(default='jsonl', min_length=1)
    allowed: bool = True

    @field_validator('corpus_id', 'version', 'source_type', mode='before')
    @classmethod
    def strip_required_text(cls, value: object) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError('Corpus source fields must not be blank.')
        return text

    @field_validator('path')
    @classmethod
    def normalize_path(cls, value: Path) -> Path:
        resolved = value.expanduser().resolve()
        if not resolved.exists():
            raise ValueError(f'Corpus source does not exist: {resolved}')
        if not resolved.is_file():
            raise ValueError(f'Corpus source must be a file: {resolved}')
        return resolved


class CorpusSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    sources: list[CorpusSourceSettings]
    require_non_empty: bool = True

    @model_validator(mode='after')
    def validate_sources(self) -> CorpusSettings:
        if self.require_non_empty and not self.sources:
            raise ValueError('At least one corpus source must be configured.')
        seen: set[str] = set()
        for source in self.sources:
            if source.corpus_id in seen:
                raise ValueError(f'Duplicate corpus_id configured: {source.corpus_id!r}.')
            seen.add(source.corpus_id)
        return self

    def by_id(self, corpus_id: str) -> CorpusSourceSettings:
        for source in self.sources:
            if source.corpus_id == corpus_id:
                return source
        raise KeyError(corpus_id)


class AISettings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    primary_generation: ModelRoleBinding = Field(
        default_factory=lambda: ModelRoleBinding(
            provider_name='fake',
            model_name='deterministic-primary',
            enabled=True,
        )
    )
    reasoning: ModelRoleBinding = Field(
        default_factory=lambda: ModelRoleBinding(
            provider_name='fake',
            model_name='deterministic-reasoning',
            enabled=True,
        )
    )
    small_fast: ModelRoleBinding = Field(
        default_factory=lambda: ModelRoleBinding(
            provider_name='fake',
            model_name='deterministic-small-fast',
            enabled=True,
        )
    )

    def bindings(self) -> dict[ModelRole, ModelRoleBinding]:
        return {
            ModelRole.PRIMARY_GENERATION: self.primary_generation,
            ModelRole.REASONING: self.reasoning,
            ModelRole.SMALL_FAST: self.small_fast,
        }


class AppSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    environment: EnvironmentName = 'dev'
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    prompt_registry: PromptRegistrySettings = Field(
        default_factory=lambda: PromptRegistrySettings(prompt_root=_default_prompt_root())
    )
    state_store: StateStoreSettings = Field(
        default_factory=lambda: StateStoreSettings(sqlite_path=_default_state_db_path())
    )
    ingestion: IngestionPolicy = Field(default_factory=IngestionPolicy)
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    output_validation: OutputValidationPolicy = Field(default_factory=OutputValidationPolicy)
    narration: NarrationSettings = Field(default_factory=NarrationSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)
    providers: ProviderSettings = Field(default_factory=ProviderSettings)
    corpora: CorpusSettings = Field(
        default_factory=lambda: CorpusSettings(
            sources=[
                CorpusSourceSettings(
                    corpus_id='world',
                    profile='narrator',
                    path=_default_world_corpus_path(),
                    version='v1',
                ),
                CorpusSourceSettings(
                    corpus_id='rules',
                    profile='arbiter',
                    path=_default_rules_corpus_path(),
                    version='v1',
                ),
            ]
        )
    )
    ai: AISettings = Field(default_factory=AISettings)

    @model_validator(mode='after')
    def validate_runtime_guards(self) -> AppSettings:
        enabled_bindings = {
            role: binding
            for role, binding in self.ai.bindings().items()
            if binding.enabled
        }
        fake_roles = [
            role.value
            for role, binding in enabled_bindings.items()
            if binding.provider_name.lower() == 'fake'
        ]
        real_roles = [
            role.value
            for role, binding in enabled_bindings.items()
            if binding.provider_name.lower() != 'fake'
        ]

        if fake_roles and real_roles:
            raise ValueError(
                'Mixed fake and real model providers are not allowed in one runtime. '
                f'Fake roles: {", ".join(fake_roles)}. Real roles: {", ".join(real_roles)}.'
            )
        if self.environment in {'staging', 'prod'} and fake_roles:
            raise ValueError('Fake model providers are not allowed in staging or prod.')
        if any(binding.provider_name.lower() == 'openai' for binding in enabled_bindings.values()):
            if self.providers.openai.api_key is None:
                raise ValueError(
                    'JESTER_OPENAI_API_KEY must be configured when any enabled model role uses provider=openai.'
                )
        if self.corpora.require_non_empty and not self.corpora.sources:
            raise ValueError('At least one startup corpus must be configured.')
        return self


def _load_role_binding(
    values: Mapping[str, str],
    *,
    prefix: str,
    default_provider: str,
    default_model: str,
) -> ModelRoleBinding:
    enabled = _parse_bool(values.get(f'{prefix}_ENABLED'), default=True)
    return ModelRoleBinding(
        provider_name=values.get(f'{prefix}_PROVIDER', default_provider),
        model_name=values.get(f'{prefix}_MODEL', default_model),
        enabled=enabled,
        default_temperature=float(values.get(f'{prefix}_TEMPERATURE', '0.2')),
        max_tokens=_parse_optional_int(values.get(f'{prefix}_MAX_TOKENS')),
    )


def load_settings(env: Mapping[str, str] | None = None) -> AppSettings:
    """Load validated settings from environment variables."""

    values: Mapping[str, str] = env if env is not None else os.environ
    default_ingestion = IngestionPolicy()

    try:
        return AppSettings(
            environment=cast(EnvironmentName, values.get('JESTER_ENVIRONMENT', 'dev')),
            logging=LoggingSettings(
                level=cast(
                    Literal['DEBUG', 'INFO', 'WARNING', 'ERROR'],
                    values.get('JESTER_LOG_LEVEL', 'INFO'),
                )
            ),
            prompt_registry=PromptRegistrySettings(
                prompt_root=Path(values.get('JESTER_PROMPT_ROOT', str(_default_prompt_root())))
            ),
            state_store=StateStoreSettings(
                sqlite_path=Path(values.get('JESTER_STATE_DB_PATH', str(_default_state_db_path())))
            ),
            ingestion=IngestionPolicy(
                denied_name_patterns=_split_csv(values.get('JESTER_DENIED_NAME_PATTERNS'))
                or default_ingestion.denied_name_patterns,
                denied_extensions=_split_csv(values.get('JESTER_DENIED_EXTENSIONS'))
                or default_ingestion.denied_extensions,
                denied_path_parts=_split_csv(values.get('JESTER_DENIED_PATH_PARTS'))
                or default_ingestion.denied_path_parts,
                allowed_extensions=_split_csv(values.get('JESTER_ALLOWED_EXTENSIONS'))
                or default_ingestion.allowed_extensions,
                explicit_whitelist_patterns=_split_csv(
                    values.get('JESTER_INGESTION_WHITELIST_PATTERNS')
                ),
            ),
            retrieval=RetrievalSettings(
                default_top_k=int(values.get('JESTER_DEFAULT_TOP_K', '5')),
                bm25_weight=float(values.get('JESTER_RETRIEVAL_BM25_WEIGHT', '1.0')),
                vector_weight=float(values.get('JESTER_RETRIEVAL_VECTOR_WEIGHT', '0.85')),
                cache_ttl_seconds=int(values.get('JESTER_RETRIEVAL_CACHE_TTL_SECONDS', '60')),
            ),
            output_validation=OutputValidationPolicy(
                allow_urls=_parse_bool(values.get('JESTER_ALLOW_URLS_IN_OUTPUT'), default=False),
                enable_anachronism_check=_parse_bool(
                    values.get('JESTER_ENABLE_ANACHRONISM_CHECK'),
                    default=True,
                ),
            ),
            narration=NarrationSettings(
                prompt_name=values.get('JESTER_NARRATION_PROMPT_NAME', 'narration'),
                prompt_version=values.get('JESTER_NARRATION_PROMPT_VERSION', 'v2'),
            ),
            api=ApiSettings(
                host=values.get('JESTER_API_HOST', '127.0.0.1'),
                port=int(values.get('JESTER_API_PORT', '8000')),
                require_api_key=_parse_bool(values.get('JESTER_API_REQUIRE_KEY'), default=False),
                api_keys=_split_csv(values.get('JESTER_API_KEYS')),
                enable_narration=_parse_bool(values.get('JESTER_API_ENABLE_NARRATION'), default=True),
                default_tenant_id=values.get('JESTER_DEFAULT_TENANT_ID', 'default'),
                max_request_chars=int(values.get('JESTER_API_MAX_REQUEST_CHARS', '2000')),
            ),
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
            corpora=CorpusSettings(
                require_non_empty=_parse_bool(values.get('JESTER_REQUIRE_NON_EMPTY_CORPORA'), default=True),
                sources=[
                    CorpusSourceSettings(
                        corpus_id='world',
                        profile='narrator',
                        path=Path(values.get('JESTER_WORLD_CORPUS_PATH', str(_default_world_corpus_path()))),
                        version=values.get('JESTER_WORLD_CORPUS_VERSION', 'v1'),
                    ),
                    CorpusSourceSettings(
                        corpus_id='rules',
                        profile='arbiter',
                        path=Path(values.get('JESTER_RULES_CORPUS_PATH', str(_default_rules_corpus_path()))),
                        version=values.get('JESTER_RULES_CORPUS_VERSION', 'v1'),
                    ),
                ],
            ),
            ai=AISettings(
                primary_generation=_load_role_binding(
                    values,
                    prefix='JESTER_PRIMARY',
                    default_provider='fake',
                    default_model='deterministic-primary',
                ),
                reasoning=_load_role_binding(
                    values,
                    prefix='JESTER_REASONING',
                    default_provider='fake',
                    default_model='deterministic-reasoning',
                ),
                small_fast=_load_role_binding(
                    values,
                    prefix='JESTER_SMALL_FAST',
                    default_provider='fake',
                    default_model='deterministic-small-fast',
                ),
            ),
        )
    except (ValidationError, ValueError) as exc:
        raise SettingsError(f'Invalid Jester configuration: {exc}') from exc

