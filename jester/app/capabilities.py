from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from jester.app.contracts.common import AppDto
from jester.engine.rules.capability import Capability as EngineCapability
from jester.engine.rules.capability import CapabilityResult
from jester.engine.rules.capability import evaluate_capabilities as evaluate_engine_capabilities


class Capability(StrEnum):
    INITIATIVE = 'INITIATIVE'
    BASIC_ATTACK = 'BASIC_ATTACK'
    BASIC_MOVEMENT = 'BASIC_MOVEMENT'
    DAMAGE = 'DAMAGE'
    HIT_POINTS = 'HIT_POINTS'
    PRONE_UNCONSCIOUS = 'PRONE_UNCONSCIOUS'
    SPELLCASTING = 'SPELLCASTING'
    REACTIONS = 'REACTIONS'
    OPPORTUNITY_ATTACKS = 'OPPORTUNITY_ATTACKS'
    ADVANTAGE = 'ADVANTAGE'
    CONCENTRATION = 'CONCENTRATION'
    COVER = 'COVER'


class CapabilityDecision(AppDto):
    capability: Capability
    supported: bool
    reason: str = Field(min_length=1)
    matched_term: str | None = None


_ENGINE_TO_APP: dict[EngineCapability, Capability] = {
    EngineCapability.INITIATIVE: Capability.INITIATIVE,
    EngineCapability.ATTACK: Capability.BASIC_ATTACK,
    EngineCapability.MOVEMENT: Capability.BASIC_MOVEMENT,
    EngineCapability.DAMAGE: Capability.DAMAGE,
    EngineCapability.HIT_POINTS: Capability.HIT_POINTS,
    EngineCapability.CONDITIONS_BASIC: Capability.PRONE_UNCONSCIOUS,
    EngineCapability.SPELLCASTING_BASIC: Capability.SPELLCASTING,
    EngineCapability.REACTION: Capability.REACTIONS,
    EngineCapability.OPPORTUNITY_ATTACK: Capability.OPPORTUNITY_ATTACKS,
    EngineCapability.ADVANTAGE: Capability.ADVANTAGE,
    EngineCapability.CONCENTRATION: Capability.CONCENTRATION,
    EngineCapability.COVER: Capability.COVER,
}


def evaluate_capabilities(text: str) -> list[CapabilityDecision]:
    return [_to_decision(result) for result in evaluate_engine_capabilities(text)]


def first_unsupported_capability(text: str) -> CapabilityDecision | None:
    for decision in evaluate_capabilities(text):
        if not decision.supported:
            return decision
    return None


def _to_decision(result: CapabilityResult) -> CapabilityDecision:
    return CapabilityDecision(
        capability=_ENGINE_TO_APP[result.capability],
        supported=result.supported,
        reason=result.reason,
        matched_term=result.matched_term,
    )
