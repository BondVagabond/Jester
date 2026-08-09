from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from jester.ai.base import ModelError
from jester.ai.contracts import ModelRequest, ModelRole, ModelTraceRecord
from jester.ai.selection import ModelSelectionPolicy
from jester.prompts import load_prompt

ArtifactT = TypeVar('ArtifactT', bound=BaseModel)


def _require_text(value: object) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError('Classification fields must not be blank.')
    return text


class ModeRoutingArtifact(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    mode: str = Field(min_length=1)
    subtask: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)

    @field_validator('mode', 'subtask', 'rationale', mode='before')
    @classmethod
    def strip_required_text(cls, value: object) -> str:
        return _require_text(value)


class IntentClassificationArtifact(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    request_kind: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)

    @field_validator('request_kind', 'rationale', mode='before')
    @classmethod
    def strip_required_text(cls, value: object) -> str:
        return _require_text(value)


class TeachingDepthArtifact(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    depth: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1)

    @field_validator('depth', 'rationale', mode='before')
    @classmethod
    def strip_required_text(cls, value: object) -> str:
        return _require_text(value)


class SmallFastClassifier:
    def __init__(self, selector: ModelSelectionPolicy | None = None) -> None:
        self._selector = selector

    def classify_mode(
        self,
        *,
        request_text: str,
        fallback_mode: str,
        fallback_subtask: str,
        fallback_confidence: float,
        candidates: Sequence[str],
        trace_sink: list[ModelTraceRecord] | None = None,
    ) -> ModeRoutingArtifact | None:
        return self._classify_json(
            prompt_name='routing_mode',
            prompt_version='v1',
            template_values={
                'request_text': request_text,
                'rule_candidates': ' | '.join(candidates) or 'No deterministic candidates.',
            },
            metadata={
                'fallback_mode': fallback_mode,
                'fallback_subtask': fallback_subtask,
                'fallback_confidence': fallback_confidence,
            },
            response_model=ModeRoutingArtifact,
            trace_sink=trace_sink,
        )

    def classify_live_dm_intent(
        self,
        *,
        request_text: str,
        fallback_kind: str,
        fallback_confidence: float,
        trace_sink: list[ModelTraceRecord] | None = None,
    ) -> IntentClassificationArtifact | None:
        return self._classify_json(
            prompt_name='routing_live_dm_intent',
            prompt_version='v1',
            template_values={
                'request_text': request_text,
                'fallback_kind': fallback_kind,
            },
            metadata={
                'fallback_kind': fallback_kind,
                'fallback_confidence': fallback_confidence,
            },
            response_model=IntentClassificationArtifact,
            trace_sink=trace_sink,
        )

    def classify_teaching_depth(
        self,
        *,
        question: str,
        fallback_depth: str,
        trace_sink: list[ModelTraceRecord] | None = None,
    ) -> TeachingDepthArtifact | None:
        return self._classify_json(
            prompt_name='teaching_depth',
            prompt_version='v1',
            template_values={
                'question': question,
                'fallback_depth': fallback_depth,
            },
            metadata={
                'question': question,
                'fallback_depth': fallback_depth,
            },
            response_model=TeachingDepthArtifact,
            trace_sink=trace_sink,
        )

    def _classify_json(
        self,
        *,
        prompt_name: str,
        prompt_version: str,
        template_values: dict[str, str],
        metadata: dict[str, object],
        response_model: type[ArtifactT],
        trace_sink: list[ModelTraceRecord] | None,
    ) -> ArtifactT | None:
        if self._selector is None:
            _append_trace(
                trace_sink,
                ModelTraceRecord(
                    role=ModelRole.SMALL_FAST,
                    outcome='classifier_unavailable',
                    degraded=True,
                    fallback_triggered=True,
                    notes=['No selection policy is configured.'],
                ),
            )
            return None

        selected = self._selector.optional(ModelRole.SMALL_FAST)
        if selected is None:
            _append_trace(
                trace_sink,
                ModelTraceRecord(
                    role=ModelRole.SMALL_FAST,
                    outcome='classifier_unavailable',
                    degraded=True,
                    fallback_triggered=True,
                    notes=[self._selector.resolve(ModelRole.SMALL_FAST).warning or 'Classifier unavailable.'],
                ),
            )
            return None

        prompt_spec = load_prompt(prompt_name, prompt_version)
        rendered_prompt = prompt_spec.template.format(**template_values)
        try:
            response = selected.client.generate(
                ModelRequest(
                    role=ModelRole.SMALL_FAST,
                    prompt=rendered_prompt,
                    temperature=0.0,
                    max_tokens=256,
                    metadata=metadata,
                    prompt_name=prompt_name,
                    prompt_version=prompt_version,
                )
            )
        except ModelError as exc:
            _append_trace(
                trace_sink,
                ModelTraceRecord(
                    role=ModelRole.SMALL_FAST,
                    prompt_name=prompt_name,
                    prompt_version=prompt_version,
                    validation_passed=False,
                    fallback_triggered=True,
                    degraded=True,
                    outcome='classification_model_failed',
                    notes=[str(exc)],
                ),
            )
            return None
        try:
            artifact = response_model.model_validate_json(response.content)
        except ValidationError as exc:
            _append_trace(
                trace_sink,
                ModelTraceRecord(
                    role=ModelRole.SMALL_FAST,
                    provider_name=response.provider_name,
                    model_name=response.model_name,
                    prompt_name=prompt_name,
                    prompt_version=prompt_version,
                    latency_ms=response.latency_ms,
                    validation_passed=False,
                    fallback_triggered=True,
                    degraded=False,
                    outcome='classification_invalid',
                    notes=[str(exc)],
                ),
            )
            return None

        _append_trace(
            trace_sink,
            ModelTraceRecord(
                role=ModelRole.SMALL_FAST,
                provider_name=response.provider_name,
                model_name=response.model_name,
                prompt_name=prompt_name,
                prompt_version=prompt_version,
                latency_ms=response.latency_ms,
                validation_passed=True,
                fallback_triggered=False,
                degraded=False,
                outcome='classification_applied',
            ),
        )
        return artifact


def _append_trace(
    trace_sink: list[ModelTraceRecord] | None,
    record: ModelTraceRecord,
) -> None:
    if trace_sink is not None:
        trace_sink.append(record)
