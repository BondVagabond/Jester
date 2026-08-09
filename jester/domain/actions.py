from __future__ import annotations

from pydantic import Field

from jester.domain.base import DomainModel
from jester.domain.combat import Condition, Position
from jester.domain.enums import ActionStatus, ActionType


class RuleTraceEntry(DomainModel):
    rule: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    capability: str | None = None


class ActionIntent(DomainModel):
    intent_id: str = Field(min_length=1)
    action_type: ActionType
    target_id: str | None = None
    destination: Position | None = None
    note: str | None = None


class HitPointChange(DomainModel):
    entity_id: str = Field(min_length=1)
    previous_hp: int = Field(ge=0)
    current_hp: int = Field(ge=0)


class PositionChange(DomainModel):
    entity_id: str = Field(min_length=1)
    previous_position: Position
    current_position: Position


class ConditionChange(DomainModel):
    entity_id: str = Field(min_length=1)
    added: list[Condition] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)


class MovementBudgetChange(DomainModel):
    entity_id: str = Field(min_length=1)
    previous_remaining: int = Field(ge=0)
    current_remaining: int = Field(ge=0)


class TurnChange(DomainModel):
    previous_combatant_id: str = Field(min_length=1)
    current_combatant_id: str = Field(min_length=1)
    previous_round_number: int = Field(ge=1)
    current_round_number: int = Field(ge=1)


class StateDelta(DomainModel):
    hit_point_changes: list[HitPointChange] = Field(default_factory=list)
    position_changes: list[PositionChange] = Field(default_factory=list)
    condition_changes: list[ConditionChange] = Field(default_factory=list)
    movement_budget_changes: list[MovementBudgetChange] = Field(default_factory=list)
    turn_change: TurnChange | None = None


class AttackResult(DomainModel):
    attacker_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    attack_roll: int = Field(ge=1, le=20)
    attack_total: int
    target_armor_class: int = Field(ge=1)
    hit: bool
    damage_roll: int = Field(ge=0)
    damage_applied: int = Field(ge=0)
    state_delta: StateDelta = Field(default_factory=StateDelta)
    rule_trace: list[RuleTraceEntry] = Field(default_factory=list)


class MovementResult(DomainModel):
    actor_id: str = Field(min_length=1)
    previous_position: Position
    current_position: Position
    distance_travelled: int = Field(ge=0)
    movement_remaining: int = Field(ge=0)
    state_delta: StateDelta = Field(default_factory=StateDelta)
    rule_trace: list[RuleTraceEntry] = Field(default_factory=list)


class ActionResult(DomainModel):
    sequence_number: int | None = Field(default=None, ge=1)
    status: ActionStatus = ActionStatus.REJECTED
    action_type: ActionType
    actor_id: str = Field(min_length=1)
    target_id: str | None = None
    errors: list[str] = Field(default_factory=list)
    attack_result: AttackResult | None = None
    movement_result: MovementResult | None = None
    ended_turn: bool = False
    state_delta: StateDelta = Field(default_factory=StateDelta)
    rule_trace: list[RuleTraceEntry] = Field(default_factory=list)
