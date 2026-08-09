from __future__ import annotations

from jester.domain import Combatant, Position


def distance_between_positions(left: Position, right: Position) -> int:
    return abs(left.slot - right.slot)


def distance_between_combatants(left: Combatant, right: Combatant) -> int:
    return distance_between_positions(left.position, right.position)


def movement_cost(origin: Position, destination: Position) -> int:
    return distance_between_positions(origin, destination)


def attack_total(*, attack_roll: int, attack_bonus: int) -> int:
    return attack_roll + attack_bonus
