from __future__ import annotations

from jester.ai import ModelRegistry, ModelRequest, ModelRole, ModelRoleBinding, ScriptedModelClient
from jester.app.contracts import PrepArtifactType, PrepRequest
from jester.app.prep import PrepService
from jester.app.prompting import PromptRenderRequest
from tests.app_factory import build_world_retriever
from tests.runtime_factory import build_session


class UnsafePrepModel:
    def generate(self, request: PromptRenderRequest) -> str:
        del request
        return 'See manifest.jsonl for the full answer.'


class _SequencedPrimaryResponder:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.requests: list[ModelRequest] = []

    def __call__(self, request: ModelRequest) -> str:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self._responses) - 1)
        return self._responses[index]


def test_prep_service_builds_retrieval_backed_npc_brief() -> None:
    service = PrepService(retriever=build_world_retriever())
    response = service.create_artifact(
        PrepRequest(
            request_id='prep-1',
            artifact_type=PrepArtifactType.NPC_BRIEF,
            topic='Goblin Lookout',
            goal='Prepare a tense interaction scene.',
            request_text='Create an NPC brief for the goblin lookout.',
        ),
        session=build_session(),
    )

    assert response.npc_brief is not None
    assert response.npc_brief.provenance
    assert response.npc_brief.name == 'Goblin Lookout'
    assert 'lever' in response.npc_brief.secret.lower()


def test_prep_service_uses_validator_backed_fallback_for_unsafe_prose() -> None:
    service = PrepService(
        retriever=build_world_retriever(),
        model_client=UnsafePrepModel(),
    )
    response = service.create_artifact(
        PrepRequest(
            request_id='prep-2',
            artifact_type=PrepArtifactType.TOWN_BRIEF,
            topic='Copper Vault Entrance',
            goal='Prepare the opening location.',
        ),
        session=build_session(),
    )

    assert response.town_brief is not None
    assert response.town_brief.prose is not None
    assert response.town_brief.prose.used_fallback is True
    assert 'manifest.jsonl' not in response.town_brief.prose.text.lower()


def test_prep_service_builds_session_prep_packet() -> None:
    service = PrepService(retriever=build_world_retriever())
    response = service.create_artifact(
        PrepRequest(
            request_id='prep-3',
            artifact_type=PrepArtifactType.SESSION_PREP_PACKET,
            topic='Copper Vault',
            goal='Prepare the next session with one clear throughline.',
        ),
        session=build_session(),
    )

    assert response.session_prep_packet is not None
    assert len(response.session_prep_packet.outline_steps) == 4
    assert response.session_prep_packet.encounter_outline is not None
    assert response.session_prep_packet.npc_briefs
    assert response.session_prep_packet.quest_hooks


def test_prep_service_runs_plan_generate_critique_refine_loop() -> None:
    responder = _SequencedPrimaryResponder(
        [
            'Brief.',
            'Goblin Lookout guards the tunnel lever and can bargain for time while the session goal advances.',
        ]
    )
    registry = ModelRegistry.from_bindings(
        {
            ModelRole.PRIMARY_GENERATION: ModelRoleBinding(
                provider_name='fake',
                model_name='primary-prep',
            ),
            ModelRole.REASONING: ModelRoleBinding(
                provider_name='fake',
                model_name='reasoning-prep',
            ),
        },
        clients={
            ModelRole.PRIMARY_GENERATION: ScriptedModelClient(
                role=ModelRole.PRIMARY_GENERATION,
                model_name='primary-prep',
                responder=responder,
            )
        },
    )
    service = PrepService(
        retriever=build_world_retriever(),
        model_registry=registry,
    )

    response = service.create_artifact(
        PrepRequest(
            request_id='prep-4',
            artifact_type=PrepArtifactType.NPC_BRIEF,
            topic='Goblin Lookout',
            goal='Prepare a tense interaction scene.',
        ),
        session=build_session(),
    )

    assert response.plan is not None
    assert response.critique is not None
    assert response.critique.violations
    assert response.npc_brief is not None
    assert response.npc_brief.prose is not None
    assert response.npc_brief.prose.text != 'Brief.'
    assert 'goblin lookout' in response.npc_brief.prose.text.lower()
    assert any(trace.outcome == 'prep_refinement_validated' for trace in response.model_traces)


def test_prep_service_falls_back_when_reasoning_role_is_disabled() -> None:
    registry = ModelRegistry.from_bindings(
        {
            ModelRole.PRIMARY_GENERATION: ModelRoleBinding(
                provider_name='fake',
                model_name='primary-prep',
            ),
            ModelRole.REASONING: ModelRoleBinding(
                provider_name='fake',
                model_name='reasoning-prep',
                enabled=False,
            ),
        }
    )
    service = PrepService(
        retriever=build_world_retriever(),
        model_registry=registry,
    )

    response = service.create_artifact(
        PrepRequest(
            request_id='prep-5',
            artifact_type=PrepArtifactType.QUEST_HOOK,
            topic='Stolen Key Rumor',
            goal='Prepare a strong opening lead.',
        ),
        session=build_session(),
    )

    assert response.plan is not None
    assert any(trace.outcome == 'plan_fallback' for trace in response.model_traces)
    assert any(trace.outcome == 'critique_fallback' for trace in response.model_traces)




