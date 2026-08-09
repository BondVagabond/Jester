from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Capability(StrEnum):
    INITIATIVE = 'initiative'
    ATTACK = 'attack'
    MOVEMENT = 'movement'
    DAMAGE = 'damage'
    HIT_POINTS = 'hit_points'
    CONDITIONS_BASIC = 'conditions_basic'
    OPPORTUNITY_ATTACK = 'opportunity_attack'
    REACTION = 'reaction'
    COVER = 'cover'
    CONCENTRATION = 'concentration'
    SPELLCASTING_BASIC = 'spellcasting_basic'
    ADVANTAGE = 'advantage'


class CapabilityResult(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    capability: Capability
    supported: bool
    reason: str = Field(min_length=1)
    matched_term: str | None = None

    @field_validator('reason', 'matched_term', mode='before')
    @classmethod
    def strip_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            raise ValueError('Capability text fields must not be blank.')
        return text


_SUPPORTED: dict[Capability, tuple[str, ...]] = {
    Capability.INITIATIVE: ('initiative', 'turn order', 'whose turn'),
    Capability.ATTACK: ('attack', 'strike', 'hit'),
    Capability.MOVEMENT: ('move', 'walk', 'run', 'slot'),
    Capability.DAMAGE: ('damage',),
    Capability.HIT_POINTS: ('hit points', 'hp'),
    Capability.CONDITIONS_BASIC: ('prone', 'unconscious'),
}

_UNSUPPORTED: dict[Capability, tuple[str, ...]] = {
    Capability.OPPORTUNITY_ATTACK: ('opportunity attack',),
    Capability.REACTION: ('reaction', 'ready an action'),
    Capability.COVER: ('cover', 'half cover', 'three quarters cover'),
    Capability.CONCENTRATION: ('concentration',),
    Capability.SPELLCASTING_BASIC: ('spell', 'cast ', 'spell slot', 'magic missile', 'fireball'),
    Capability.ADVANTAGE: ('advantage', 'disadvantage'),
}

_REASONS: dict[Capability, tuple[bool, str]] = {
    Capability.INITIATIVE: (True, 'Initiative order is implemented deterministically.'),
    Capability.ATTACK: (True, 'Basic attack resolution is implemented deterministically.'),
    Capability.MOVEMENT: (True, 'Abstract slot-based movement is implemented deterministically.'),
    Capability.DAMAGE: (True, 'Damage application is implemented deterministically.'),
    Capability.HIT_POINTS: (True, 'Hit points are part of canonical combat state.'),
    Capability.CONDITIONS_BASIC: (True, 'Prone and unconscious are the supported conditions.'),
    Capability.OPPORTUNITY_ATTACK: (False, 'Opportunity attacks are not implemented yet.'),
    Capability.REACTION: (False, 'Reactions are outside the supported deterministic rules scope.'),
    Capability.COVER: (False, 'Cover is not implemented in the abstract-position MVP engine.'),
    Capability.CONCENTRATION: (False, 'Concentration is not implemented yet.'),
    Capability.SPELLCASTING_BASIC: (False, 'Spellcasting is outside the current deterministic rules scope.'),
    Capability.ADVANTAGE: (False, 'Advantage and disadvantage are not implemented yet.'),
}


class RuleCapabilityRegistry:
    def evaluate_text(self, text: str) -> list[CapabilityResult]:
        normalized = _normalize(text)
        decisions: list[CapabilityResult] = []

        for capability, patterns in _UNSUPPORTED.items():
            match = _first_match(normalized, patterns)
            if match is None:
                continue
            decisions.append(self.get(capability, matched_term=match))

        if decisions:
            return decisions

        for capability, patterns in _SUPPORTED.items():
            match = _first_match(normalized, patterns)
            if match is None:
                continue
            decisions.append(self.get(capability, matched_term=match))
        return decisions

    def get(self, capability: Capability, *, matched_term: str | None = None) -> CapabilityResult:
        supported, reason = _REASONS[capability]
        return CapabilityResult(
            capability=capability,
            supported=supported,
            reason=reason,
            matched_term=matched_term,
        )

    def first_unsupported(self, text: str) -> CapabilityResult | None:
        for decision in self.evaluate_text(text):
            if not decision.supported:
                return decision
        return None


_DEFAULT_REGISTRY = RuleCapabilityRegistry()


def evaluate_capabilities(text: str) -> list[CapabilityResult]:
    return _DEFAULT_REGISTRY.evaluate_text(text)


def first_unsupported_capability(text: str) -> CapabilityResult | None:
    return _DEFAULT_REGISTRY.first_unsupported(text)


def get_capability(capability: Capability) -> CapabilityResult:
    return _DEFAULT_REGISTRY.get(capability)


def _normalize(text: str) -> str:
    return f" {' '.join(text.lower().split())} "


def _first_match(normalized: str, patterns: tuple[str, ...]) -> str | None:
    for pattern in patterns:
        if pattern in normalized:
            return pattern.strip()
    return None
