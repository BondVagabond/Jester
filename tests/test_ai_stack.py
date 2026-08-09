from __future__ import annotations

from jester.ai import (
    ModelRegistry,
    ModelRole,
    ModelRoleBinding,
    ModelSelectionPolicy,
    ModelTraceRecord,
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




