from __future__ import annotations

from pydantic import Field, model_validator

from jester.ai.contracts import CritiqueArtifact, ModelTraceRecord, PlanArtifact
from jester.app.contracts.common import (
    AppDto,
    GeneratedTextBlock,
    PrepArtifactType,
    ProvenanceReference,
)


class PrepRequest(AppDto):
    request_id: str = Field(min_length=1)
    artifact_type: PrepArtifactType
    topic: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    request_text: str | None = None
    campaign_id: str | None = None
    session_id: str | None = None
    retrieval_query: str | None = None
    context_notes: list[str] = Field(default_factory=list)
    include_flavor_prose: bool = True


class PrepArtifactBase(AppDto):
    artifact_id: str = Field(min_length=1)
    artifact_type: PrepArtifactType
    purpose: str = Field(min_length=1)
    inputs_used: list[str] = Field(default_factory=list)
    provenance: list[ProvenanceReference] = Field(default_factory=list)
    prose: GeneratedTextBlock | None = None


class NPCBrief(PrepArtifactBase):
    artifact_type: PrepArtifactType = PrepArtifactType.NPC_BRIEF
    name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    motivation: str = Field(min_length=1)
    secret: str = Field(min_length=1)
    mannerism: str = Field(min_length=1)
    encounter_hooks: list[str] = Field(default_factory=list)


class TownBrief(PrepArtifactBase):
    artifact_type: PrepArtifactType = PrepArtifactType.TOWN_BRIEF
    name: str = Field(min_length=1)
    atmosphere: str = Field(min_length=1)
    tensions: list[str] = Field(default_factory=list)
    landmarks: list[str] = Field(default_factory=list)
    notable_npcs: list[str] = Field(default_factory=list)


class EncounterOutline(PrepArtifactBase):
    artifact_type: PrepArtifactType = PrepArtifactType.ENCOUNTER_OUTLINE
    name: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    enemies: list[str] = Field(default_factory=list)
    terrain_features: list[str] = Field(default_factory=list)
    escalation: str = Field(min_length=1)
    rewards: list[str] = Field(default_factory=list)


class QuestHook(PrepArtifactBase):
    artifact_type: PrepArtifactType = PrepArtifactType.QUEST_HOOK
    title: str = Field(min_length=1)
    premise: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    stakes: str = Field(min_length=1)
    complication: str = Field(min_length=1)


class SessionPrepPacket(PrepArtifactBase):
    artifact_type: PrepArtifactType = PrepArtifactType.SESSION_PREP_PACKET
    title: str = Field(min_length=1)
    outline_steps: list[str] = Field(default_factory=list)
    npc_briefs: list[NPCBrief] = Field(default_factory=list)
    town_brief: TownBrief | None = None
    encounter_outline: EncounterOutline | None = None
    quest_hooks: list[QuestHook] = Field(default_factory=list)


class PrepResponse(AppDto):
    artifact_type: PrepArtifactType
    npc_brief: NPCBrief | None = None
    town_brief: TownBrief | None = None
    encounter_outline: EncounterOutline | None = None
    quest_hook: QuestHook | None = None
    session_prep_packet: SessionPrepPacket | None = None
    plan: PlanArtifact | None = None
    critique: CritiqueArtifact | None = None
    model_traces: list[ModelTraceRecord] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_single_payload(self) -> PrepResponse:
        values = [
            self.npc_brief,
            self.town_brief,
            self.encounter_outline,
            self.quest_hook,
            self.session_prep_packet,
        ]
        present = sum(value is not None for value in values)
        if present != 1:
            raise ValueError('PrepResponse must contain exactly one populated artifact payload.')
        return self

