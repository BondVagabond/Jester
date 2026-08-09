from __future__ import annotations

from jester.engine.rules.capability import Capability, CapabilityResult, get_capability


def concentration_capability() -> CapabilityResult:
    return get_capability(Capability.CONCENTRATION)
