from __future__ import annotations

from jester.domain import Combatant, Condition, ConditionChange, ConditionType
from jester.engine.rules.conditions import has_condition


def build_defeat_condition_changes(
    *,
    target: Combatant,
    source_id: str,
    next_hp: int,
) -> list[ConditionChange]:
    if next_hp != 0 or has_condition(target, ConditionType.UNCONSCIOUS):
        return []
    return [
        ConditionChange(
            entity_id=target.combatant_id,
            added=[Condition(kind=ConditionType.UNCONSCIOUS, source_id=source_id)],
            removed=[],
        )
    ]
