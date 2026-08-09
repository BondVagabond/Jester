from __future__ import annotations

import json
from pathlib import Path

from jester.domain import ActionIntent, ActionType, MemoryRecord, MemoryScope
from jester.engine import (
    add_memory,
    generate_narration,
    get_visible_state,
    initialize_combat,
    process_player_action,
)
from jester.state import SQLiteStateStore
from tests.runtime_factory import build_session


def test_save_and_load_session_round_trip(tmp_path: Path) -> None:
    session = build_session()
    initialize_combat(session, ['pc-1', 'pc-2', 'npc-1'])
    add_memory(
        session,
        MemoryRecord(
            scope=MemoryScope.PUBLIC,
            content='The vault door is cracked.',
            entity_id='location-1',
        ),
    )
    result = process_player_action(
        session,
        'pc-1',
        ActionIntent(
            intent_id='attack-1',
            action_type=ActionType.ATTACK,
            target_id='npc-1',
        ),
    )
    assert result.status.value == 'APPLIED'

    store = SQLiteStateStore(tmp_path / 'state.sqlite3')
    store.save_session(session)
    loaded = store.load_session(session.session_id)

    assert loaded.model_dump(mode='json') == session.model_dump(mode='json')


def test_generate_narration_is_read_only() -> None:
    session = build_session()
    initialize_combat(session, ['pc-1', 'pc-2', 'npc-1'])
    result = process_player_action(
        session,
        'pc-1',
        ActionIntent(
            intent_id='attack-1',
            action_type=ActionType.ATTACK,
            target_id='npc-1',
        ),
    )
    visible_state = get_visible_state(session, 'player-1')
    before = json.dumps(visible_state, sort_keys=True)

    narration = generate_narration(visible_state, result)
    after = json.dumps(visible_state, sort_keys=True)

    assert narration
    assert before == after