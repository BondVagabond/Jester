from __future__ import annotations

from pydantic import Field, model_validator

from jester.domain.actions import ActionResult
from jester.domain.base import DomainModel
from jester.domain.combat import CombatState
from jester.domain.entities import NPC, Campaign, Location, Party, PlayerCharacter, Scene
from jester.domain.memory import Memory


class Session(DomainModel):
    session_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    dm_id: str = Field(min_length=1)
    player_ids: list[str] = Field(default_factory=list)
    campaign: Campaign
    party: Party
    current_scene_id: str = Field(min_length=1)
    scenes: dict[str, Scene]
    player_characters: dict[str, PlayerCharacter]
    npcs: dict[str, NPC]
    locations: dict[str, Location]
    combat_state: CombatState | None = None
    memory: Memory = Field(default_factory=Memory)
    action_history: list[ActionResult] = Field(default_factory=list)
    action_counter: int = Field(default=0, ge=0)
    random_seed: int = 0
    active: bool = True

    @model_validator(mode='after')
    def validate_session(self) -> Session:
        if self.campaign.campaign_id != self.campaign_id:
            raise ValueError('campaign_id must match embedded campaign.')
        if self.campaign.party_id != self.party.party_id:
            raise ValueError('Campaign party_id must match embedded party.')
        if self.current_scene_id not in self.scenes:
            raise ValueError('current_scene_id must exist in scenes.')
        for member_id in self.party.member_ids:
            if member_id not in self.player_characters:
                raise ValueError('All party members must exist in player_characters.')
        controllers = {pc.controller_id for pc in self.player_characters.values()}
        for controller_id in self.player_ids:
            if controller_id not in controllers:
                raise ValueError(
                    'player_ids must map to at least one player character controller.'
                )
        return self