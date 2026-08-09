from __future__ import annotations

from jester.domain import MovementBudgetChange, MovementResult, Position, PositionChange, RuleTraceEntry, StateDelta
from jester.domain.combat import Combatant
from jester.engine.rules.modifiers import movement_cost


def validate_movement_action(actor: Combatant, destination: Position) -> list[str]:
    distance = movement_cost(actor.position, destination)
    if distance > actor.movement_remaining:
        return ['Requested movement exceeds remaining movement budget.']
    return []


def resolve_movement_action(actor: Combatant, destination: Position) -> MovementResult:
    distance = movement_cost(actor.position, destination)
    movement_remaining = actor.movement_remaining - distance
    state_delta = StateDelta(
        position_changes=[
            PositionChange(
                entity_id=actor.combatant_id,
                previous_position=actor.position.model_copy(deep=True),
                current_position=destination.model_copy(deep=True),
            )
        ],
        movement_budget_changes=[
            MovementBudgetChange(
                entity_id=actor.combatant_id,
                previous_remaining=actor.movement_remaining,
                current_remaining=movement_remaining,
            )
        ],
    )
    return MovementResult(
        actor_id=actor.combatant_id,
        previous_position=actor.position.model_copy(deep=True),
        current_position=destination.model_copy(deep=True),
        distance_travelled=distance,
        movement_remaining=movement_remaining,
        state_delta=state_delta,
        rule_trace=[
            RuleTraceEntry(
                rule='movement.basic',
                detail=f'Moved {distance} slots and reduced remaining movement to {movement_remaining}.',
                capability='movement',
            )
        ],
    )
