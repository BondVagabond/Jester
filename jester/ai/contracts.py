from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _require_text(value: object) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError('Text fields must not be blank.')
    return text


def _normalize_text_list(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError('Expected a list of strings.')
    return [str(item).strip() for item in value if str(item).strip()]


class ModelRole(StrEnum):
    PRIMARY_GENERATION = 'primary_generation'
    REASONING = 'reasoning'
    SMALL_FAST = 'small_fast'


class ModelRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    role: ModelRole
    prompt: str = Field(min_length=1)
    temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    prompt_name: str | None = None
    prompt_version: str | None = None

    @field_validator('prompt', 'prompt_name', 'prompt_version', mode='before')
    @classmethod
    def strip_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        return _require_text(value)


class ModelResponse(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    role: ModelRole
    content: str = Field(min_length=1)
    provider_name: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    latency_ms: int | None = Field(default=None, ge=0)
    token_usage: dict[str, int] | None = None

    @field_validator('content', 'provider_name', 'model_name', mode='before')
    @classmethod
    def strip_required_text(cls, value: object) -> str:
        return _require_text(value)

    @field_validator('token_usage', mode='before')
    @classmethod
    def validate_token_usage(cls, value: object) -> dict[str, int] | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise TypeError('token_usage must be a mapping of token counters.')
        parsed: dict[str, int] = {}
        for key, item in value.items():
            normalized_key = _require_text(key)
            count = int(item)
            if count < 0:
                raise ValueError('token_usage values must be greater than or equal to zero.')
            parsed[normalized_key] = count
        return parsed


class ModelRoleBinding(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    provider_name: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    enabled: bool = True
    default_temperature: float = Field(default=0.2, ge=0.0, le=1.0)
    max_tokens: int | None = Field(default=None, ge=1)

    @field_validator('provider_name', 'model_name', mode='before')
    @classmethod
    def strip_binding_text(cls, value: object) -> str:
        return _require_text(value)


class ModelSelection(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    role: ModelRole
    configured: bool
    enabled: bool
    available: bool
    provider_name: str | None = None
    model_name: str | None = None
    degraded: bool = False
    warning: str | None = None

    @field_validator('provider_name', 'model_name', 'warning', mode='before')
    @classmethod
    def strip_selection_text(cls, value: object) -> str | None:
        if value is None:
            return None
        return _require_text(value)


class ModelTraceRecord(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    role: ModelRole
    provider_name: str | None = None
    model_name: str | None = None
    prompt_name: str | None = None
    prompt_version: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    validation_passed: bool | None = None
    fallback_triggered: bool = False
    degraded: bool = False
    outcome: str = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)

    @field_validator(
        'provider_name',
        'model_name',
        'prompt_name',
        'prompt_version',
        'outcome',
        mode='before',
    )
    @classmethod
    def strip_trace_text(cls, value: object) -> str | None:
        if value is None:
            return None
        return _require_text(value)

    @field_validator('notes', mode='before')
    @classmethod
    def normalize_notes(cls, value: object) -> list[str]:
        return _normalize_text_list(value)


class PlanArtifact(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    objective: str = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)

    @field_validator('objective', mode='before')
    @classmethod
    def strip_objective(cls, value: object) -> str:
        return _require_text(value)

    @field_validator('assumptions', 'steps', 'success_criteria', mode='before')
    @classmethod
    def normalize_lists(cls, value: object) -> list[str]:
        return _normalize_text_list(value)


class CritiqueArtifact(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)

    @field_validator('strengths', 'weaknesses', 'violations', 'revision_instructions', mode='before')
    @classmethod
    def normalize_lists(cls, value: object) -> list[str]:
        return _normalize_text_list(value)


class TeachingPlanArtifact(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    concept: str = Field(min_length=1)
    depth: str = Field(min_length=1)
    prerequisites: list[str] = Field(default_factory=list)
    learning_objectives: list[str] = Field(default_factory=list)
    explanation_sections: list[str] = Field(default_factory=list)
    misconception_focus: list[str] = Field(default_factory=list)

    @field_validator('concept', 'depth', mode='before')
    @classmethod
    def strip_plan_text(cls, value: object) -> str:
        return _require_text(value)

    @field_validator(
        'prerequisites',
        'learning_objectives',
        'explanation_sections',
        'misconception_focus',
        mode='before',
    )
    @classmethod
    def normalize_plan_lists(cls, value: object) -> list[str]:
        return _normalize_text_list(value)
