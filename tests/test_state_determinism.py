from __future__ import annotations

from jester.domain import ActionIntent, ActionType, Position
from jester.engine import initialize_combat, process_player_action
from tests.runtime_factory import build_session


def test_same_actions_produce_same_results_and_state() -> None:
    session_a = build_session(seed=101, session_id='session-a')
    session_b = build_session(seed=101, session_id='session-a')

    initialize_combat(session_a, ['pc-1', 'pc-2', 'npc-1'])
    initialize_combat(session_b, ['pc-1', 'pc-2', 'npc-1'])

    actions = [
        (
            'pc-1',
            ActionIntent(
                intent_id='a1',
                action_type=ActionType.ATTACK,
                target_id='npc-1',
            ),
        ),
        ('pc-1', ActionIntent(intent_id='a2', action_type=ActionType.END_TURN)),
        (
            'pc-2',
            ActionIntent(
                intent_id='a3',
                action_type=ActionType.MOVE,
                destination=Position(slot=2),
            ),
        ),
        ('pc-2', ActionIntent(intent_id='a4', action_type=ActionType.END_TURN)),
    ]

    results_a = [process_player_action(session_a, actor_id, intent) for actor_id, intent in actions]
    results_b = [process_player_action(session_b, actor_id, intent) for actor_id, intent in actions]

    assert [result.model_dump(mode='json') for result in results_a] == [
        result.model_dump(mode='json') for result in results_b
    ]
    assert session_a.model_dump(mode='json') == session_b.model_dump(mode='json')