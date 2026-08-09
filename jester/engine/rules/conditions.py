from __future__ import annotations

from jester.domain import Combatant, Condition, ConditionChange, ConditionType


def has_condition(combatant: Combatant, condition_type: ConditionType) -> bool:
    return any(condition.kind == condition_type for condition in combatant.conditions)


def merge_conditions(
    current_conditions: list[Condition],
    added: list[Condition],
    removed: list[str],
) -> list[Condition]:
    removed_set = set(removed)
    remaining = [
        condition.model_copy(deep=True)
        for condition in current_conditions
        if condition.kind not in removed_set
    ]
    existing_kinds = {condition.kind for condition in remaining}
    for condition in added:
        if condition.kind in existing_kinds:
            continue
        remaining.append(condition.model_copy(deep=True))
        existing_kinds.add(condition.kind)
    return remaining


def build_condition_change(
    *,
    entity_id: str,
    added: list[Condition] | None = None,
    removed: list[str] | None = None,
) -> ConditionChange:
    return ConditionChange(
        entity_id=entity_id,
        added=list(added or []),
        removed=list(removed or []),
    )
