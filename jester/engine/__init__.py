from __future__ import annotations

from typing import Any

__all__ = [
    'DeterministicNarrationModel',
    'DeterministicScenarioEngine',
    'NarrationGenerationError',
    'NarrationRequest',
    'NarrationResponse',
    'ScenarioRunResult',
    'ScenarioStep',
    'add_memory',
    'build_narration',
    'generate_narration',
    'get_visible_state',
    'initialize_combat',
    'process_player_action',
    'query_memory',
    'resolve_attack',
]


def __getattr__(name: str) -> Any:
    if name in {'initialize_combat', 'resolve_attack'}:
        from jester.engine import combat as _combat_module

        return getattr(_combat_module, name)
    if name in {'add_memory', 'query_memory'}:
        from jester.engine import memory as _memory_module

        return getattr(_memory_module, name)
    if name in {
        'DeterministicNarrationModel',
        'NarrationGenerationError',
        'NarrationRequest',
        'NarrationResponse',
        'build_narration',
        'generate_narration',
    }:
        from jester.engine import narration as _narration_module

        return getattr(_narration_module, name)
    if name == 'process_player_action':
        from jester.engine import pipeline as _pipeline_module

        return getattr(_pipeline_module, name)
    if name == 'get_visible_state':
        from jester.engine import privacy as _privacy_module

        return getattr(_privacy_module, name)
    if name in {'DeterministicScenarioEngine', 'ScenarioRunResult', 'ScenarioStep'}:
        from jester.engine import scenario as _scenario_module

        return getattr(_scenario_module, name)
    raise AttributeError(name)
