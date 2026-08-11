from __future__ import annotations

import pytest
from pydantic import ValidationError

from jester.ai import (
    ModelRegistry,
    ModelResponse,
    ModelRole,
    ModelRoleBinding,
    ModelSelectionPolicy,
    ModelTraceRecord,
    PlanArtifact,
    ReasoningService,
    ScriptedModelClient,
)


def test_model_selection_resolves_distinct_clients_per_role() -> None:
    registry = ModelRegistry.from_bindings(
        {
            ModelRole.PRIMARY_GENERATION: ModelRoleBinding(
                provider_name='fake',
                model_name='primary-test',
            ),
            ModelRole.REASONING: ModelRoleBinding(
                provider_name='fake',
                model_name='reasoning-test',
            ),
            ModelRole.SMALL_FAST: ModelRoleBinding(
                provider_name='fake',
                model_name='small-test',
            ),
        },
        clients={
            ModelRole.PRIMARY_GENERATION: ScriptedModelClient(
                role=ModelRole.PRIMARY_GENERATION,
                model_name='primary-test',
                responder=lambda request: str(request.metadata.get('fallback_text', 'primary')),
            ),
            ModelRole.REASONING: ScriptedModelClient(
                role=ModelRole.REASONING,
                model_name='reasoning-test',
                responder=lambda request: '{"objective":"x","assumptions":[],"steps":["y"],"success_criteria":["z"]}',
            ),
            ModelRole.SMALL_FAST: ScriptedModelClient(
                role=ModelRole.SMALL_FAST,
                model_name='small-test',
                responder=lambda request: (
                    '{"mode":"DM_PREP","subtask":"npc_brief",'
                    '"confidence":0.9,"rationale":"router"}'
                ),
            ),
        },
    )
    selector = ModelSelectionPolicy(registry)

    assert selector.require(ModelRole.PRIMARY_GENERATION).selection.model_name == 'primary-test'
    assert selector.require(ModelRole.REASONING).selection.model_name == 'reasoning-test'
    assert selector.require(ModelRole.SMALL_FAST).selection.model_name == 'small-test'


def test_reasoning_service_falls_back_when_plan_payload_is_invalid() -> None:
    registry = ModelRegistry.from_bindings(
        {
            ModelRole.REASONING: ModelRoleBinding(
                provider_name='fake',
                model_name='invalid-plan',
            )
        },
        clients={
            ModelRole.REASONING: ScriptedModelClient(
                role=ModelRole.REASONING,
                model_name='invalid-plan',
                responder=lambda request: 'not json',
            )
        },
    )
    service = ReasoningService(ModelSelectionPolicy(registry))
    traces: list[ModelTraceRecord] = []

    plan = service.build_prep_plan(
        artifact_type='NPC_BRIEF',
        topic='Goblin Lookout',
        goal='Prepare a tense negotiation.',
        inputs_used=['topic:Goblin Lookout', 'goal:Prepare a tense negotiation.'],
        retrieved_context='Goblin Lookout: The goblin knows about the tunnel lever.',
        trace_sink=traces,
    )

    assert plan.steps
    assert any(trace.outcome == 'plan_invalid' and trace.fallback_triggered for trace in traces)


def test_plan_artifact_reports_wrong_typed_list_field_as_validation_error() -> None:
    # Well-formed JSON whose 'steps' is a string rather than a list. Pydantic only
    # converts ValueError and AssertionError raised inside a validator into a
    # ValidationError; anything else propagates to the caller untouched.
    with pytest.raises(ValidationError):
        PlanArtifact.model_validate_json(
            '{"objective":"x","assumptions":[],"steps":"not-a-list","success_criteria":["z"]}'
        )


def test_model_response_reports_non_mapping_token_usage_as_validation_error() -> None:
    with pytest.raises(ValidationError):
        ModelResponse(
            role=ModelRole.REASONING,
            content='text',
            provider_name='fake',
            model_name='m',
            latency_ms=1,
            token_usage=['not', 'a', 'mapping'],
        )


def test_reasoning_service_falls_back_when_a_plan_field_has_the_wrong_type() -> None:
    # A real qwen3.5:4b response shaped like this crashed the request instead of
    # degrading, because the wrong-type guard raised TypeError and the service
    # only catches ValidationError.
    registry = ModelRegistry.from_bindings(
        {
            ModelRole.REASONING: ModelRoleBinding(
                provider_name='fake',
                model_name='wrong-typed-plan',
            )
        },
        clients={
            ModelRole.REASONING: ScriptedModelClient(
                role=ModelRole.REASONING,
                model_name='wrong-typed-plan',
                responder=lambda request: (
                    '{"objective":"x","assumptions":[],'
                    '"steps":"not-a-list","success_criteria":["z"]}'
                ),
            )
        },
    )
    service = ReasoningService(ModelSelectionPolicy(registry))
    traces: list[ModelTraceRecord] = []

    plan = service.build_prep_plan(
        artifact_type='NPC_BRIEF',
        topic='Goblin Lookout',
        goal='Prepare a tense negotiation.',
        inputs_used=['topic:Goblin Lookout'],
        retrieved_context='Goblin Lookout: The goblin knows about the tunnel lever.',
        trace_sink=traces,
    )

    assert plan.steps
    assert any(trace.outcome == 'plan_invalid' and trace.fallback_triggered for trace in traces)


def test_reasoning_service_produces_structured_critique_artifact() -> None:
    registry = ModelRegistry.from_bindings(
        {
            ModelRole.REASONING: ModelRoleBinding(
                provider_name='fake',
                model_name='reasoning-default',
            )
        }
    )
    service = ReasoningService(ModelSelectionPolicy(registry))

    critique = service.critique_prep_output(
        artifact_type='NPC_BRIEF',
        topic='Goblin Lookout',
        goal='Prepare a tense negotiation.',
        draft_text='Brief.',
        trace_sink=[],
    )

    assert critique.violations
    assert critique.revision_instructions




