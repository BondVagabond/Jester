from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from jester.validation import ValidationIssue


class AppDto(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    schema_version: int = Field(default=1, ge=1)


class Mode(StrEnum):
    DM_PREP = 'DM_PREP'
    PLAYER_TEACHING = 'PLAYER_TEACHING'
    LIVE_DM = 'LIVE_DM'


class ViewerRole(StrEnum):
    DM = 'DM'
    PLAYER = 'PLAYER'


class PrepArtifactType(StrEnum):
    NPC_BRIEF = 'NPC_BRIEF'
    TOWN_BRIEF = 'TOWN_BRIEF'
    ENCOUNTER_OUTLINE = 'ENCOUNTER_OUTLINE'
    SESSION_PREP_PACKET = 'SESSION_PREP_PACKET'
    QUEST_HOOK = 'QUEST_HOOK'


class TeachingDepth(StrEnum):
    BEGINNER = 'BEGINNER'
    INTERMEDIATE = 'INTERMEDIATE'


class TeachingConcept(StrEnum):
    ABILITY_CHECKS = 'ABILITY_CHECKS'
    ATTACK_ROLLS = 'ATTACK_ROLLS'
    DAMAGE = 'DAMAGE'
    INITIATIVE = 'INITIATIVE'
    TURNS = 'TURNS'
    HIT_POINTS = 'HIT_POINTS'
    BASIC_ACTIONS = 'BASIC_ACTIONS'


class LiveDmRequestKind(StrEnum):
    MECHANICAL_ACTION = 'MECHANICAL_ACTION'
    INFORMATIONAL_QUERY = 'INFORMATIONAL_QUERY'
    NARRATIVE_REQUEST = 'NARRATIVE_REQUEST'
    UNSUPPORTED = 'UNSUPPORTED'


class ProvenanceReference(AppDto):
    doc_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    title: str = Field(min_length=1)
    score: float
    excerpt: str | None = None

    @field_validator('doc_id', 'chunk_id', 'source', 'title', mode='before')
    @classmethod
    def strip_required_text(cls, value: object) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError('Provenance fields must not be blank.')
        return text


class GeneratedTextBlock(AppDto):
    text: str = Field(min_length=1)
    prompt_name: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    used_fallback: bool = False
    validation_passed: bool = True
    issues: list[ValidationIssue] = Field(default_factory=list)

    @field_validator('text', 'prompt_name', 'prompt_version', mode='before')
    @classmethod
    def strip_required_text(cls, value: object) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError('Generated text fields must not be blank.')
        return text