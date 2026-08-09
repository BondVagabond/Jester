from __future__ import annotations

import json
from pathlib import Path

from jester.ai import ModelRegistry, ModelRequest, ModelRole, ModelRoleBinding, ScriptedModelClient
from jester.app.contracts import LiveDmRequest, LiveDmRequestKind
from jester.app.live_dm import LiveDmService
from jester.domain import Session
from jester.engine import initialize_combat
from jester.state import SQLiteStateStore
from tests.runtime_factory import build_session


class _RecordingPrimaryResponder:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    def __call__(self, request: ModelRequest) -> str:
        self.requests.append(request)
        fallback_text = request.metadata.get('fallback_text', 'fallback')
        return str(fallback_text)


def _session_signature(session: Session) -> str:
    return json.dumps(session.model_dump(mode='json'), sort_keys=True)


def test_live_dm_action_path_uses_deterministic_engine() -> None:
    session = build_session()
    initialize_combat(session, ['pc-1', 'pc-2', 'npc-1'])
    service = LiveDmService()

    response = service.handle_request(
        LiveDmRequest(
            request_id='live-1',
            session_id=session.session_id,
            viewer_id='player-1',
            request_text='I attack the Goblin Lookout.',
        ),
        session=session,
    )

    assert response.request_kind == LiveDmRequestKind.MECHANICAL_ACTION
    assert response.resolution.engine_invoked is True
    assert response.resolution.state_mutated is True
    assert session.npcs['npc-1'].current_hp < 12
    assert response.narration is not None
    assert response.visible_session.scenes['scene-1'].dm_notes is None


def test_live_dm_action_path_records_small_fast_and_primary_traces() -> None:
    session = build_session()
    initialize_combat(session, ['pc-1', 'pc-2', 'npc-1'])
    registry = ModelRegistry.from_bindings(
        {
            ModelRole.PRIMARY_GENERATION: ModelRoleBinding(
                provider_name='fake',
                model_name='primary-live',
            ),
            ModelRole.SMALL_FAST: ModelRoleBinding(
                provider_name='fake',
                model_name='small-live',
            ),
        },
        clients={
            ModelRole.SMALL_FAST: ScriptedModelClient(
                role=ModelRole.SMALL_FAST,
                model_name='small-live',
                responder=lambda request: (
                    '{"request_kind":"MECHANICAL_ACTION","confidence":0.91,'
                    '"rationale":"The request is an in-combat attack."}'
                ),
            )
        },
    )
    service = LiveDmService(model_registry=registry)

    response = service.handle_request(
        LiveDmRequest(
            request_id='live-1b',
            session_id=session.session_id,
            viewer_id='player-1',
            request_text='I attack the Goblin Lookout.',
        ),
        session=session,
    )

    assert response.request_kind == LiveDmRequestKind.MECHANICAL_ACTION
    assert any(trace.role == ModelRole.SMALL_FAST for trace in response.model_traces)
    assert any(trace.role == ModelRole.PRIMARY_GENERATION for trace in response.model_traces)


def test_live_dm_informational_path_is_read_only() -> None:
    session = build_session()
    initialize_combat(session, ['pc-1', 'pc-2', 'npc-1'])
    before = _session_signature(session)
    service = LiveDmService()

    response = service.handle_request(
        LiveDmRequest(
            request_id='live-2',
            session_id=session.session_id,
            viewer_id='player-1',
            request_text='Whose turn is it?',
        ),
        session=session,
    )

    assert response.request_kind == LiveDmRequestKind.INFORMATIONAL_QUERY
    assert response.info_response is not None
    assert before == _session_signature(session)


def test_live_dm_prompt_assembly_stays_privacy_safe_for_players() -> None:
    session = build_session()
    initialize_combat(session, ['pc-1', 'pc-2', 'npc-1'])
    recorder = _RecordingPrimaryResponder()
    registry = ModelRegistry.from_bindings(
        {
            ModelRole.PRIMARY_GENERATION: ModelRoleBinding(
                provider_name='fake',
                model_name='primary-live',
            )
        },
        clients={
            ModelRole.PRIMARY_GENERATION: ScriptedModelClient(
                role=ModelRole.PRIMARY_GENERATION,
                model_name='primary-live',
                responder=recorder,
            )
        },
    )
    service = LiveDmService(model_registry=registry)

    response = service.handle_request(
        LiveDmRequest(
            request_id='live-2b',
            session_id=session.session_id,
            viewer_id='player-1',
            request_text='What do I see?',
        ),
        session=session,
    )

    assert response.info_response is not None
    rendered_prompt = recorder.requests[0].prompt
    assert 'secretly seeks the vault key' not in rendered_prompt
    assert 'waiting for reinforcements' not in rendered_prompt
    assert 'hidden lever' not in rendered_prompt


def test_live_dm_narrative_path_is_read_only() -> None:
    session = build_session()
    initialize_combat(session, ['pc-1', 'pc-2', 'npc-1'])
    before = _session_signature(session)
    service = LiveDmService()

    response = service.handle_request(
        LiveDmRequest(
            request_id='live-3',
            session_id=session.session_id,
            viewer_id='player-1',
            request_text='Describe the scene around us.',
        ),
        session=session,
    )

    assert response.request_kind == LiveDmRequestKind.NARRATIVE_REQUEST
    assert response.narration is not None
    assert before == _session_signature(session)


def test_live_dm_unsupported_rules_request_is_bounded() -> None:
    session = build_session()
    initialize_combat(session, ['pc-1', 'pc-2', 'npc-1'])
    before = _session_signature(session)
    service = LiveDmService()

    response = service.handle_request(
        LiveDmRequest(
            request_id='live-4',
            session_id=session.session_id,
            viewer_id='player-1',
            request_text='I cast fireball at the goblin.',
        ),
        session=session,
    )

    assert response.request_kind == LiveDmRequestKind.UNSUPPORTED
    assert response.resolution.unsupported_capabilities
    assert response.resolution.unsupported_capabilities[0].capability.value == 'SPELLCASTING'
    assert before == _session_signature(session)


def test_live_dm_info_response_is_stable_after_save_load_cycle(tmp_path: Path) -> None:
    session = build_session(session_id='persist-live')
    initialize_combat(session, ['pc-1', 'pc-2', 'npc-1'])
    store = SQLiteStateStore(tmp_path / 'live_state.sqlite3')
    store.save_session(session)
    service = LiveDmService(state_store=store)
    request = LiveDmRequest(
        request_id='live-5',
        session_id=session.session_id,
        viewer_id='player-1',
        request_text='Whose turn is it?',
    )

    before = service.handle_request(request)
    reloaded = store.load_session(session.session_id)
    after = service.handle_request(request, session=reloaded)

    assert before.model_dump(mode='json') == after.model_dump(mode='json')




