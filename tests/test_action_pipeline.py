from __future__ import annotations

from jester.domain import ActionIntent, ActionType, Position
from jester.engine import initialize_combat, process_player_action
from tests.runtime_factory import build_session


def test_invalid_action_is_rejected_without_state_change() -> None:
    session = build_session()
    initialize_combat(session, ['pc-1', 'pc-2', 'npc-1'])
    before = session.model_dump(mode='json')

    result = process_player_action(
        session,
        'pc-1',
        ActionIntent(
            intent_id='move-too-far',
            action_type=ActionType.MOVE,
            destination=Position(slot=10),
        ),
    )

    assert result.status.value == 'REJECTED'
    assert session.model_dump(mode='json') == before


def test_valid_move_updates_state() -> None:
    session = build_session()
    initialize_combat(session, ['pc-1', 'pc-2', 'npc-1'])

    result = process_player_action(
        session,
        'pc-1',
        ActionIntent(
            intent_id='move-1',
            action_type=ActionType.MOVE,
            destination=Position(slot=2),
        ),
    )

    assert result.status.value == 'APPLIED'
    assert result.movement_result is not None
    assert session.player_characters['pc-1'].scene_position.slot == 2
    assert session.combat_state is not None
    assert session.combat_state.combatants['pc-1'].movement_remaining == 4