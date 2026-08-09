from __future__ import annotations

from jester.engine.rules.capability import Capability, CapabilityResult, get_capability


def reaction_capability() -> CapabilityResult:
    return get_capability(Capability.REACTION)
