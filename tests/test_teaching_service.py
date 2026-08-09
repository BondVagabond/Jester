from __future__ import annotations

import pytest

from jester.ai import ModelRegistry, ModelRole, ModelRoleBinding, ScriptedModelClient
from jester.app.contracts import TeachingConcept, TeachingDepth, TeachingRequest
from jester.app.teaching import TeachingService, TeachingServiceError
from tests.app_factory import build_rules_retriever


def test_teaching_service_explains_supported_concept_with_prerequisites() -> None:
    service = TeachingService(retriever=build_rules_retriever())
    response = service.build_lesson(
        TeachingRequest(
            request_id='teach-1',
            question='Explain how initiative works.',
            depth=TeachingDepth.BEGINNER,
        )
    )

    assert response.concept == TeachingConcept.INITIATIVE
    assert response.explanation.prerequisites == [TeachingConcept.TURNS]
    assert 'turn order' in response.explanation.summary.lower()
    assert response.misconceptions
    assert response.practice_scenario is not None
    assert response.provenance


def test_teaching_service_depth_changes_explanation_shape() -> None:
    service = TeachingService(retriever=build_rules_retriever())
    beginner = service.build_lesson(
        TeachingRequest(
            request_id='teach-2a',
            question='Explain attack rolls.',
            concept=TeachingConcept.ATTACK_ROLLS,
            depth=TeachingDepth.BEGINNER,
        )
    )
    intermediate = service.build_lesson(
        TeachingRequest(
            request_id='teach-2b',
            question='Explain attack rolls.',
            concept=TeachingConcept.ATTACK_ROLLS,
            depth=TeachingDepth.INTERMEDIATE,
        )
    )

    assert beginner.explanation.summary != intermediate.explanation.summary
    assert len(intermediate.explanation.key_points) >= len(beginner.explanation.key_points)
    assert any('damage' in hint.misconception.lower() for hint in intermediate.misconceptions)


def test_teaching_service_uses_reasoning_plan_and_small_fast_depth() -> None:
    registry = ModelRegistry.from_bindings(
        {
            ModelRole.PRIMARY_GENERATION: ModelRoleBinding(
                provider_name='fake',
                model_name='primary-teaching',
            ),
            ModelRole.REASONING: ModelRoleBinding(
                provider_name='fake',
                model_name='reasoning-teaching',
            ),
            ModelRole.SMALL_FAST: ModelRoleBinding(
                provider_name='fake',
                model_name='small-teaching',
            ),
        },
        clients={
            ModelRole.SMALL_FAST: ScriptedModelClient(
                role=ModelRole.SMALL_FAST,
                model_name='small-teaching',
                responder=lambda request: (
                    '{"depth":"INTERMEDIATE","confidence":0.84,'
                    '"rationale":"The learner asked for why the rule works."}'
                ),
            )
        },
    )
    service = TeachingService(
        retriever=build_rules_retriever(),
        model_registry=registry,
    )

    response = service.build_lesson(
        TeachingRequest(
            request_id='teach-3',
            question='Why do attack rolls happen before damage?',
            concept=TeachingConcept.ATTACK_ROLLS,
        )
    )

    assert response.depth == TeachingDepth.INTERMEDIATE
    assert response.teaching_plan is not None
    assert response.teaching_plan.learning_objectives
    assert any(trace.role == ModelRole.REASONING for trace in response.model_traces)
    assert any(trace.role == ModelRole.SMALL_FAST for trace in response.model_traces)


def test_teaching_service_falls_back_when_reasoning_payload_is_invalid() -> None:
    registry = ModelRegistry.from_bindings(
        {
            ModelRole.PRIMARY_GENERATION: ModelRoleBinding(
                provider_name='fake',
                model_name='primary-teaching',
            ),
            ModelRole.REASONING: ModelRoleBinding(
                provider_name='fake',
                model_name='reasoning-invalid',
            ),
        },
        clients={
            ModelRole.REASONING: ScriptedModelClient(
                role=ModelRole.REASONING,
                model_name='reasoning-invalid',
                responder=lambda request: 'invalid json',
            )
        },
    )
    service = TeachingService(
        retriever=build_rules_retriever(),
        model_registry=registry,
    )

    response = service.build_lesson(
        TeachingRequest(
            request_id='teach-4',
            question='Explain hit points.',
            concept=TeachingConcept.HIT_POINTS,
        )
    )

    assert response.teaching_plan is not None
    assert any(trace.outcome == 'teaching_plan_invalid' for trace in response.model_traces)


def test_teaching_service_rejects_unknown_topics() -> None:
    service = TeachingService()
    with pytest.raises(TeachingServiceError):
        service.build_lesson(
            TeachingRequest(
                request_id='teach-5',
                question='Explain mounted combat formations.',
            )
        )
