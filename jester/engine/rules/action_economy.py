from __future__ import annotations

from jester.domain import (
    ActionIntent,
    ActionType,
    Combatant,
    CombatState,
    ConditionType,
    MovementBudgetChange,
    Position,
    StateDelta,
    TurnChange,
)
from jester.engine.rules.conditions import has_condition


def validate_turn_actor(combat_state: CombatState, actor_id: str) -> list[str]:
    if not combat_state.active or combat_state.completed:
        return ['Combat is not active.']
    if actor_id not in combat_state.combatants:
        return [f'Actor {actor_id!r} is not part of the active combat.']
    current_id = combat_state.initiative.current_combatant_id
    if current_id != actor_id:
        return [f"It is not {actor_id}'s turn."]
    actor = combat_state.combatants[actor_id]
    if has_condition(actor, ConditionType.UNCONSCIOUS):
        return [f'Actor {actor_id!r} is unconscious and cannot act.']
    return []


def validate_action_basics(combat_state: CombatState, actor_id: str, intent: ActionIntent) -> list[str]:
    errors = validate_turn_actor(combat_state, actor_id)
    if errors:
        return errors
    if intent.action_type == ActionType.MOVE and intent.destination is None:
        return ['Move actions require a destination.']
    return []


def resolve_end_turn_state_delta(combat_state: CombatState) -> StateDelta:
    initiative = combat_state.initiative
    previous_id = initiative.current_combatant_id
    previous_round = combat_state.round_number
    next_index = (initiative.current_index + 1) % len(initiative.ordered_combatant_ids)
    current_round = previous_round + 1 if next_index == 0 else previous_round
    current_id = initiative.ordered_combatant_ids[next_index]
    next_combatant = combat_state.combatants[current_id]

    return StateDelta(
        movement_budget_changes=[
            MovementBudgetChange(
                entity_id=current_id,
                previous_remaining=next_combatant.movement_remaining,
                current_remaining=next_combatant.speed,
            )
        ],
        turn_change=TurnChange(
            previous_combatant_id=previous_id,
            current_combatant_id=current_id,
            previous_round_number=previous_round,
            current_round_number=current_round,
        ),
    )


def current_combatant(combat_state: CombatState) -> Combatant:
    return combat_state.combatants[combat_state.initiative.current_combatant_id]


def normalize_destination(destination: Position) -> Position:
    return destination.model_copy(deep=True)
