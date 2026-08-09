from __future__ import annotations

from jester.domain import ActionIntent, ActionType
from jester.engine import initialize_combat, process_player_action
from tests.runtime_factory import build_session


def test_attack_applies_damage_and_updates_hit_points() -> None:
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

    assert result.attack_result is not None
    assert result.attack_result.damage_applied == result.attack_result.damage_roll
    assert session.npcs['npc-1'].current_hp == 12 - result.attack_result.damage_applied


def test_turn_order_is_enforced() -> None:
    session = build_session()
    initialize_combat(session, ['pc-1', 'pc-2', 'npc-1'])

    rejected = process_player_action(
        session,
        'pc-2',
        ActionIntent(
            intent_id='bad-turn',
            action_type=ActionType.ATTACK,
            target_id='npc-1',
        ),
    )

    assert rejected.status.value == 'REJECTED'
    assert rejected.errors == ["It is not pc-2's turn."]


def test_end_turn_advances_to_next_actor() -> None:
    session = build_session()
    combat = initialize_combat(session, ['pc-1', 'pc-2', 'npc-1'])
    first_actor = combat.initiative.current_combatant_id

    result = process_player_action(
        session,
        'pc-1',
        ActionIntent(intent_id='end-1', action_type=ActionType.END_TURN),
    )

    assert result.ended_turn is True
    assert result.state_delta.turn_change is not None
    assert result.state_delta.turn_change.previous_combatant_id == first_actor
    assert combat.initiative.current_combatant_id == 'pc-2'