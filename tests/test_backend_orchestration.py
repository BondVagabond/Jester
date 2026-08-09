from __future__ import annotations

from pathlib import Path

import pytest

from jester.ai import ModelRole
from jester.app.application import LiveDmApplicationService, PrepApplicationService
from jester.app.contracts import LiveDmRequest, PrepArtifactType, PrepRequest, TeachingRequest
from jester.app.live_dm import LiveDmService
from jester.app.orchestration import ServiceWarningCode, WorkspaceRoutingPolicy
from jester.app.prep import PrepService
from jester.app.teaching import TeachingService
from jester.engine import initialize_combat
from jester.state import SessionConflictError, SQLiteSessionRepository
from tests.app_factory import build_rules_retriever, build_world_retriever
from tests.runtime_factory import build_session


def test_workspace_routing_policy_maps_core_backend_tasks_to_expected_roles() -> None:
    prep_prose = WorkspaceRoutingPolicy.prep_prose(PrepArtifactType.NPC_BRIEF)
    teaching_answer = WorkspaceRoutingPolicy.teaching_answer()
    live_dm_rules = WorkspaceRoutingPolicy.live_dm_rules_explanation()
    live_dm_narration = WorkspaceRoutingPolicy.live_dm_narration()
    live_dm_mechanics = WorkspaceRoutingPolicy.live_dm_mechanics()

    assert prep_prose.model_role == ModelRole.PRIMARY_GENERATION
    assert prep_prose.prompt_name == 'prep_npc'
    assert teaching_answer.model_role == ModelRole.REASONING
    assert teaching_answer.prompt_name == 'teaching_explain_concept'
    assert live_dm_rules.model_role == ModelRole.REASONING
    assert live_dm_rules.prompt_name == 'live_dm_rules_explanation'
    assert live_dm_narration.model_role == ModelRole.PRIMARY_GENERATION
    assert live_dm_narration.prompt_name == 'live_dm_narration'
    assert live_dm_mechanics.deterministic is True
    assert live_dm_mechanics.model_role is None


def test_teaching_service_execute_marks_authored_fallback_when_retrieval_is_empty() -> None:
    service = TeachingService(retriever=None)

    result = service.execute(
        TeachingRequest(
            request_id='teach-orch-1',
            question='Explain initiative.',
        )
    )

    assert any(warning.code == ServiceWarningCode.RETRIEVAL_UNAVAILABLE for warning in result.warnings)
    assert any(warning.code == ServiceWarningCode.AUTHORED_FALLBACK_USED for warning in result.warnings)
    assert result.debug.retrieved[0].hits == []


def test_live_dm_application_service_rejects_stale_revision(tmp_path: Path) -> None:
    repository = SQLiteSessionRepository(tmp_path / 'state.sqlite3')
    session = build_session(session_id='orch-session')
    initialize_combat(session, ['pc-1', 'pc-2', 'npc-1'])
    repository.create_session(session, tenant_id='default')
    app_service = LiveDmApplicationService(LiveDmService(retriever=build_rules_retriever()), repository)

    with pytest.raises(SessionConflictError):
        app_service.execute_turn(
            LiveDmRequest(
                request_id='live-orch-1',
                session_id=session.session_id,
                viewer_id='player-1',
                request_text='attack goblin lookout',
            ),
            tenant_id='default',
            expected_revision=2,
            fast_path=False,
            narration_enabled=True,
        )


def test_live_dm_execute_turn_separates_mechanics_and_rules_explanation() -> None:
    session = build_session(session_id='orch-live')
    initialize_combat(session, ['pc-1', 'pc-2', 'npc-1'])
    service = LiveDmService(retriever=build_rules_retriever())

    result = service.execute_turn(
        LiveDmRequest(
            request_id='live-orch-2',
            session_id=session.session_id,
            viewer_id='player-1',
            request_text='attack goblin lookout',
        ),
        session=session,
    )

    assert result.response.resolution.engine_invoked is True
    assert result.response.info_response is not None
    assert result.response.narration is not None
    assert result.response.resolution.state_mutated is True
    assert any(route.task.value == 'live_dm.rules_explanation' for route in result.debug.routes)


def test_prep_application_service_loads_session_context_before_execution(tmp_path: Path) -> None:
    repository = SQLiteSessionRepository(tmp_path / 'prep-state.sqlite3')
    session = build_session(session_id='orch-prep')
    repository.create_session(session, tenant_id='default')
    app_service = PrepApplicationService(
        prep_service=PrepService(retriever=build_world_retriever()),
        session_repository=repository,
    )

    result = app_service.execute(
        PrepRequest(
            request_id='prep-orch-1',
            artifact_type=PrepArtifactType.NPC_BRIEF,
            topic='Goblin Lookout',
            goal='Prepare a table-ready lookout scene.',
            session_id=session.session_id,
        ),
        tenant_id='default',
    )

    assert result.response.npc_brief is not None
    assert result.debug.routes[0].task.value == 'prep.retrieval'
