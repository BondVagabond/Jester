from __future__ import annotations

from jester.domain import Combatant
from jester.engine.rules.capability import Capability, CapabilityResult, get_capability


def cover_bonus_for_attack(*, attacker: Combatant, target: Combatant) -> int:
    _ = attacker
    _ = target
    return 0


def cover_capability() -> CapabilityResult:
    return get_capability(Capability.COVER)
