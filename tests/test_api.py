from __future__ import annotations

from pathlib import Path

from jester.engine import initialize_combat
from tests.api_factory import build_test_client
from tests.asgi_client import request_json
from tests.runtime_factory import build_session


def test_health_endpoints_report_dependency_status(tmp_path: Path) -> None:
    app, _, _ = build_test_client(tmp_path)

    health = request_json(app, 'GET', '/health')
    dependencies = request_json(app, 'GET', '/health/dependencies')

    assert health.status_code == 200
    assert health.json_body['status'] == 'ok'
    assert dependencies.status_code == 200
    assert dependencies.json_body['database'] == 'ok'
    assert dependencies.json_body['retrieval'] == 'ok'


def test_sessions_and_live_dm_endpoints_round_trip_with_revision(tmp_path: Path) -> None:
    app, _, _ = build_test_client(tmp_path)
    session = build_session()
    initialize_combat(session, ['pc-1', 'pc-2', 'npc-1'])

    saved = request_json(
        app,
        'PUT',
        f'/api/v1/sessions/{session.session_id}',
        json_body={'session': session.model_dump(mode='json')},
    )
    assert saved.status_code == 200
    assert saved.json_body['revision'] == 1

    turn = request_json(
        app,
        'POST',
        '/api/v1/live-dm/turns',
        json_body={
            'request': {
                'request_id': 'turn-1',
                'session_id': session.session_id,
                'viewer_id': 'player-1',
                'request_text': 'attack goblin lookout',
                'include_narration': True,
            },
            'expected_revision': 1,
            'fast_path': True,
        },
    )

    assert turn.status_code == 200
    assert turn.json_body['session_revision'] == 2
    assert turn.json_body['response']['resolution']['state_mutated'] is True

    loaded = request_json(app, 'GET', f'/api/v1/sessions/{session.session_id}')
    assert loaded.status_code == 200
    assert loaded.json_body['revision'] == 2
    assert loaded.json_body['session']['action_counter'] == 1


def test_retrieval_debug_and_learning_endpoints_return_structured_payloads(tmp_path: Path) -> None:
    app, _, _ = build_test_client(tmp_path)

    debug = request_json(
        app,
        'POST',
        '/api/v1/retrieval/debug',
        json_body={'text': 'goblin lever', 'corpus': 'world', 'k': 2},
    )
    assert debug.status_code == 200
    assert debug.json_body['retrieval']['hits'][0]['doc_id'] == 'world-npc-1'

    teaching = request_json(
        app,
        'POST',
        '/api/v1/teaching',
        json_body={
            'request': {
                'request_id': 'teach-1',
                'question': 'Explain attack rolls to me',
                'include_practice': False,
            }
        },
    )
    assert teaching.status_code == 200
    assert teaching.json_body['lesson']['concept'] == 'ATTACK_ROLLS'

    prep = request_json(
        app,
        'POST',
        '/api/v1/prep',
        json_body={
            'request': {
                'request_id': 'prep-1',
                'artifact_type': 'NPC_BRIEF',
                'topic': 'Goblin Lookout',
                'goal': 'Create a table-ready NPC',
                'include_flavor_prose': False,
            }
        },
    )
    assert prep.status_code == 200
    assert prep.json_body['prep']['artifact_type'] == 'NPC_BRIEF'


def test_auth_middleware_rejects_missing_api_key(tmp_path: Path) -> None:
    app, _, _ = build_test_client(tmp_path, require_api_key=True)

    denied = request_json(app, 'GET', '/health')
    allowed = request_json(app, 'GET', '/health', headers={'X-API-Key': 'secret-key'})

    assert denied.status_code == 401
    assert allowed.status_code == 200

def test_session_bootstrap_and_visible_view_endpoints_are_privacy_safe(tmp_path: Path) -> None:
    app, _, _ = build_test_client(tmp_path)

    bootstrapped = request_json(
        app,
        'POST',
        '/api/v1/sessions/bootstrap',
        json_body={
            'session_name': 'Demo Frontend Session',
            'start_in_combat': True,
        },
    )
    assert bootstrapped.status_code == 200
    session_id = bootstrapped.json_body['session_id']
    assert bootstrapped.json_body['viewer_options'][0]['role'] == 'DM'

    visible = request_json(
        app,
        'GET',
        f'/api/v1/sessions/{session_id}/view?viewer_id=player-1',
    )
    assert visible.status_code == 200
    assert visible.json_body['view']['viewer_role'] == 'PLAYER'
    assert visible.json_body['view']['player_characters']['pc-1']['private_notes'] is not None
    assert visible.json_body['view']['player_characters']['pc-2']['private_notes'] is None
    assert visible.json_body['view']['recent_actions'] == []
