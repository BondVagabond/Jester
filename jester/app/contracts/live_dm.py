from __future__ import annotations

from pydantic import Field

from jester.ai.contracts import ModelTraceRecord
from jester.app.capabilities import CapabilityDecision
from jester.app.contracts.common import AppDto, GeneratedTextBlock, LiveDmRequestKind, ViewerRole
from jester.domain.enums import ActionStatus, ActionType, ConditionType, MemoryScope


class LiveDmRequest(AppDto):
    request_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    viewer_id: str = Field(min_length=1)
    request_text: str = Field(min_length=1)
    actor_id: str | None = None
    include_narration: bool = True


class VisibleConditionView(AppDto):
    kind: ConditionType
    source_id: str | None = None
    note: str | None = None


class VisiblePositionView(AppDto):
    slot: int


class VisibleCampaignView(AppDto):
    campaign_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)


class VisiblePartyView(AppDto):
    party_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    member_ids: list[str] = Field(default_factory=list)
    shared_notes: str | None = None


class VisiblePlayerCharacterView(AppDto):
    entity_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    controller_id: str = Field(min_length=1)
    character_class: str = Field(min_length=1)
    level: int = Field(ge=1)
    armor_class: int = Field(ge=1)
    max_hp: int = Field(ge=1)
    current_hp: int = Field(ge=0)
    position: VisiblePositionView
    conditions: list[VisibleConditionView] = Field(default_factory=list)
    private_notes: str | None = None


class VisibleNpcView(AppDto):
    entity_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    faction: str | None = None
    armor_class: int = Field(ge=1)
    max_hp: int = Field(ge=1)
    current_hp: int = Field(ge=0)
    position: VisiblePositionView
    conditions: list[VisibleConditionView] = Field(default_factory=list)
    dm_notes: str | None = None


class VisibleLocationView(AppDto):
    location_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    connected_location_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    dm_notes: str | None = None


class VisibleSceneView(AppDto):
    scene_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    location_id: str = Field(min_length=1)
    party_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    participant_ids: list[str] = Field(default_factory=list)
    active: bool = True
    dm_notes: str | None = None


class VisibleCombatantView(AppDto):
    combatant_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    is_player_controlled: bool
    team_id: str = Field(min_length=1)
    armor_class: int = Field(ge=1)
    max_hp: int = Field(ge=1)
    current_hp: int = Field(ge=0)
    attack_range: int = Field(ge=1)
    speed: int = Field(ge=0)
    movement_remaining: int = Field(ge=0)
    position: VisiblePositionView
    conditions: list[VisibleConditionView] = Field(default_factory=list)


class VisibleCombatStateView(AppDto):
    combat_id: str = Field(min_length=1)
    scene_id: str = Field(min_length=1)
    round_number: int = Field(ge=1)
    active: bool
    completed: bool
    initiative_order: list[str] = Field(default_factory=list)
    current_combatant_id: str = Field(min_length=1)
    combatants: dict[str, VisibleCombatantView] = Field(default_factory=dict)


class VisibleMemoryRecord(AppDto):
    record_id: str | None = None
    scope: MemoryScope
    content: str = Field(min_length=1)
    entity_id: str | None = None
    owner_id: str | None = None
    sequence_number: int | None = Field(default=None, ge=1)
    tags: list[str] = Field(default_factory=list)


class VisibleActionLogEntry(AppDto):
    sequence_number: int = Field(ge=1)
    status: ActionStatus
    action_type: ActionType
    actor_id: str = Field(min_length=1)
    actor_name: str = Field(min_length=1)
    target_id: str | None = None
    target_name: str | None = None
    summary: str = Field(min_length=1)
    state_changed: bool


class VisibleSessionView(AppDto):
    session_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    viewer_id: str | None = None
    viewer_role: ViewerRole
    current_scene_id: str = Field(min_length=1)
    action_counter: int = Field(ge=0)
    campaign: VisibleCampaignView
    party: VisiblePartyView
    scenes: dict[str, VisibleSceneView] = Field(default_factory=dict)
    player_characters: dict[str, VisiblePlayerCharacterView] = Field(default_factory=dict)
    npcs: dict[str, VisibleNpcView] = Field(default_factory=dict)
    locations: dict[str, VisibleLocationView] = Field(default_factory=dict)
    combat_state: VisibleCombatStateView | None = None
    memory: list[VisibleMemoryRecord] = Field(default_factory=list)
    recent_actions: list[VisibleActionLogEntry] = Field(default_factory=list)


class NarrationBlock(GeneratedTextBlock):
    pass


class RulesResolutionSummary(AppDto):
    request_kind: LiveDmRequestKind
    engine_invoked: bool = False
    state_mutated: bool = False
    action_status: ActionStatus | None = None
    action_type: ActionType | None = None
    actor_id: str | None = None
    target_id: str | None = None
    errors: list[str] = Field(default_factory=list)
    unsupported_capabilities: list[CapabilityDecision] = Field(default_factory=list)


class LiveDmTurnResponse(AppDto):
    request_kind: LiveDmRequestKind
    visible_session: VisibleSessionView
    resolution: RulesResolutionSummary
    narration: NarrationBlock | None = None
    info_response: GeneratedTextBlock | None = None
    model_traces: list[ModelTraceRecord] = Field(default_factory=list)
