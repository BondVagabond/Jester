from __future__ import annotations

from pydantic import Field, model_validator

from jester.domain.base import DomainModel
from jester.domain.enums import ConditionType


class DiceExpression(DomainModel):
    count: int = Field(default=1, ge=1, le=20)
    sides: int = Field(default=6, ge=2, le=100)
    modifier: int = 0


class Position(DomainModel):
    slot: int = 0


class Condition(DomainModel):
    kind: ConditionType
    source_id: str | None = None
    note: str | None = None


class InitiativeOrder(DomainModel):
    ordered_combatant_ids: list[str] = Field(min_length=1)
    current_index: int = Field(default=0, ge=0)

    @property
    def current_combatant_id(self) -> str:
        return self.ordered_combatant_ids[self.current_index]

    @model_validator(mode="after")
    def validate_current_index(self) -> InitiativeOrder:
        if self.current_index >= len(self.ordered_combatant_ids):
            raise ValueError("current_index must reference an initiative entry.")
        return self


class Combatant(DomainModel):
    combatant_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    controller_id: str | None = None
    is_player_controlled: bool = False
    team_id: str = Field(default="neutral", min_length=1)
    armor_class: int = Field(ge=1)
    max_hp: int = Field(ge=1)
    current_hp: int = Field(ge=0)
    initiative_modifier: int = 0
    initiative_roll: int = Field(default=0, ge=0)
    initiative_total: int = Field(default=0, ge=0)
    attack_bonus: int = 0
    attack_range: int = Field(default=1, ge=1)
    damage: DiceExpression = Field(default_factory=DiceExpression)
    speed: int = Field(default=6, ge=0)
    movement_remaining: int = Field(default=6, ge=0)
    position: Position = Field(default_factory=Position)
    conditions: list[Condition] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_combatant(self) -> Combatant:
        if self.current_hp > self.max_hp:
            raise ValueError("current_hp cannot exceed max_hp.")
        if self.movement_remaining > self.speed:
            raise ValueError("movement_remaining cannot exceed speed.")
        return self


class CombatState(DomainModel):
    combat_id: str = Field(min_length=1)
    scene_id: str = Field(min_length=1)
    initiative: InitiativeOrder
    combatants: dict[str, Combatant]
    round_number: int = Field(default=1, ge=1)
    active: bool = True
    completed: bool = False

    @model_validator(mode="after")
    def validate_combat_state(self) -> CombatState:
        initiative_ids = set(self.initiative.ordered_combatant_ids)
        combatant_ids = set(self.combatants.keys())
        if initiative_ids != combatant_ids:
            raise ValueError("Combatant IDs must match initiative order IDs.")
        return self
