from __future__ import annotations

from pydantic import Field, model_validator

from jester.domain.base import DomainModel
from jester.domain.combat import Condition, DiceExpression, Position


class Campaign(DomainModel):
    campaign_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    party_id: str = Field(min_length=1)
    location_ids: list[str] = Field(default_factory=list)
    scene_ids: list[str] = Field(default_factory=list)
    session_ids: list[str] = Field(default_factory=list)


class Party(DomainModel):
    party_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    member_ids: list[str] = Field(default_factory=list)
    shared_notes: str | None = None


class Location(DomainModel):
    location_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    connected_location_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    dm_notes: str | None = None


class Scene(DomainModel):
    scene_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    location_id: str = Field(min_length=1)
    party_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    participant_ids: list[str] = Field(default_factory=list)
    active: bool = True
    dm_notes: str | None = None


class ActorEntity(DomainModel):
    entity_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    armor_class: int = Field(ge=1)
    max_hp: int = Field(ge=1)
    current_hp: int = Field(ge=0)
    initiative_modifier: int = 0
    attack_bonus: int = 0
    attack_range: int = Field(default=1, ge=1)
    damage: DiceExpression = Field(default_factory=DiceExpression)
    speed: int = Field(default=6, ge=0)
    scene_position: Position = Field(default_factory=Position)
    conditions: list[Condition] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_actor(self) -> ActorEntity:
        if self.current_hp > self.max_hp:
            raise ValueError("current_hp cannot exceed max_hp.")
        return self


class PlayerCharacter(ActorEntity):
    controller_id: str = Field(min_length=1)
    character_class: str = Field(min_length=1)
    level: int = Field(default=1, ge=1)
    private_notes: str | None = None


class NPC(ActorEntity):
    faction: str | None = None
    dm_notes: str | None = None
