from __future__ import annotations

import json
from collections.abc import Callable
from typing import Protocol

from jester.ai.contracts import (
    CritiqueArtifact,
    ModelRequest,
    ModelResponse,
    ModelRole,
    PlanArtifact,
    TeachingPlanArtifact,
)
from jester.processing.sanitizer import sanitize_content


class ModelError(RuntimeError):
    """Raised when a model invocation fails safely."""


class ModelRoleUnavailableError(ModelError):
    """Raised when a required model role cannot be resolved."""


class ModelClient(Protocol):
    def generate(self, request: ModelRequest) -> ModelResponse:
        ...


ModelResponder = Callable[[ModelRequest], str]


class FakeModelClient:
    def __init__(
        self,
        *,
        role: ModelRole,
        provider_name: str = 'fake',
        model_name: str = 'deterministic',
        responder: ModelResponder | None = None,
        latency_ms: int = 1,
    ) -> None:
        self._role = role
        self._provider_name = provider_name
        self._model_name = model_name
        self._responder = responder
        self._latency_ms = latency_ms

    def generate(self, request: ModelRequest) -> ModelResponse:
        if request.role != self._role:
            raise ModelError(
                f'FakeModelClient for role {self._role.value!r} received '
                f'{request.role.value!r}.'
            )
        content = self._responder(request) if self._responder is not None else _default_response(request)
        token_usage = {
            'prompt_tokens': len(request.prompt.split()),
            'completion_tokens': len(content.split()),
        }
        return ModelResponse(
            role=request.role,
            content=content,
            provider_name=self._provider_name,
            model_name=self._model_name,
            latency_ms=self._latency_ms,
            token_usage=token_usage,
        )


class ScriptedModelClient(FakeModelClient):
    pass


def _default_response(request: ModelRequest) -> str:
    if request.role == ModelRole.REASONING:
        return _default_reasoning_response(request)
    if request.role == ModelRole.SMALL_FAST:
        return _default_small_fast_response(request)
    return _default_primary_response(request)


def _default_primary_response(request: ModelRequest) -> str:
    fallback_text = str(request.metadata.get('fallback_text', '')).strip()
    if fallback_text:
        return sanitize_content(fallback_text)

    summary = str(request.metadata.get('summary', '')).strip()
    if summary:
        return sanitize_content(summary)

    prompt_excerpt = ' '.join(request.prompt.split())[:160]
    return sanitize_content(prompt_excerpt or 'Jester generated a concise response.')


def _default_reasoning_response(request: ModelRequest) -> str:
    prompt_name = request.prompt_name or ''
    if prompt_name == 'prep_plan':
        plan_payload = PlanArtifact(
            objective=str(request.metadata.get('objective', 'Produce a usable prep artifact.')),
            assumptions=[
                f"Topic: {str(request.metadata.get('topic', 'Unknown topic')).strip()}",
                f"Artifact type: {str(request.metadata.get('artifact_type', 'unknown')).strip()}",
            ],
            steps=[
                'Identify the playable core of the request.',
                'Anchor the artifact to retrieved context and current goals.',
                'Keep the final output concise, structured, and reusable.',
            ],
            success_criteria=[
                'The artifact is immediately usable at the table.',
                'The artifact stays aligned with the requested goal.',
            ],
        )
        return plan_payload.model_dump_json()

    if prompt_name == 'prep_critique':
        draft_text = str(request.metadata.get('draft_text', '')).strip()
        topic = str(request.metadata.get('topic', '')).strip()
        goal = str(request.metadata.get('goal', '')).strip()
        violations: list[str] = []
        instructions: list[str] = []
        if topic and topic.lower() not in draft_text.lower():
            violations.append('Draft does not mention the requested topic clearly.')
            instructions.append(f'Make {topic} explicit in the final artifact.')
        if goal and goal.lower() not in draft_text.lower():
            violations.append('Draft does not tie itself directly to the requested goal.')
            instructions.append(f'Connect the artifact to {goal}.')
        if len(draft_text.split()) < 14:
            violations.append('Draft is too thin to serve as reusable prep output.')
            instructions.append('Add one concrete detail and one actionable table hook.')
        critique_payload = CritiqueArtifact(
            strengths=['The draft remains bounded to the requested artifact scope.'],
            weaknesses=['The draft may need stronger table-ready specificity.'],
            violations=violations,
            revision_instructions=instructions,
        )
        return critique_payload.model_dump_json()

    if prompt_name == 'teaching_structure':
        teaching_payload = TeachingPlanArtifact(
            concept=str(request.metadata.get('concept', 'Unknown concept')).strip(),
            depth=str(request.metadata.get('depth', 'BEGINNER')).strip(),
            prerequisites=[
                str(item).strip()
                for item in list(request.metadata.get('prerequisites', []))
                if str(item).strip()
            ],
            learning_objectives=[
                'Explain the purpose of the concept in plain language.',
                'Show the mechanical sequence step by step.',
            ],
            explanation_sections=[
                'What this rule answers',
                'How the step resolves',
                'Worked example',
            ],
            misconception_focus=[
                str(item).strip()
                for item in list(request.metadata.get('misconceptions', []))
                if str(item).strip()
            ],
        )
        return teaching_payload.model_dump_json()

    if prompt_name in {
        'teaching_explain_concept',
        'teaching_practice_scenario',
        'live_dm_rules_explanation',
        'live_dm_info_response',
    }:
        fallback_text = str(request.metadata.get('fallback_text', '')).strip()
        if fallback_text:
            return sanitize_content(fallback_text)
        summary = str(request.metadata.get('summary', '')).strip()
        if summary:
            return sanitize_content(summary)
        return sanitize_content('Jester generated a concise rules explanation.')

    return PlanArtifact(
        objective='Produce a structured Jester artifact.',
        assumptions=[],
        steps=['Use the provided prompt and stay inside the contract.'],
        success_criteria=['The artifact validates against its schema.'],
    ).model_dump_json()


def _default_small_fast_response(request: ModelRequest) -> str:
    prompt_name = request.prompt_name or ''
    if prompt_name == 'routing_mode':
        payload = {
            'mode': str(request.metadata.get('fallback_mode', 'PLAYER_TEACHING')),
            'subtask': str(request.metadata.get('fallback_subtask', 'concept_explanation')),
            'confidence': float(request.metadata.get('fallback_confidence', 0.7)),
            'rationale': 'Small-fast classifier matched the deterministic routing signal.',
        }
        return json.dumps(payload)

    if prompt_name == 'routing_live_dm_intent':
        payload = {
            'request_kind': str(request.metadata.get('fallback_kind', 'INFORMATIONAL_QUERY')),
            'confidence': float(request.metadata.get('fallback_confidence', 0.7)),
            'rationale': 'Small-fast classifier confirmed the lightweight intent label.',
        }
        return json.dumps(payload)

    if prompt_name == 'teaching_depth':
        question = str(request.metadata.get('question', '')).lower()
        depth = 'INTERMEDIATE' if any(
            term in question for term in ('advanced', 'deeper', 'why', 'interaction', 'sequence')
        ) else str(request.metadata.get('fallback_depth', 'BEGINNER'))
        payload = {
            'depth': depth,
            'confidence': 0.76,
            'rationale': 'Depth classification used lightweight question cues.',
        }
        return json.dumps(payload)

    return json.dumps({'label': 'fallback', 'confidence': 0.6, 'rationale': 'Fallback classification.'})
