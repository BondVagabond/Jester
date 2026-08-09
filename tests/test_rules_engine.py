from __future__ import annotations

from jester.domain import ActionIntent, ActionType
from jester.engine import DeterministicScenarioEngine, ScenarioStep, initialize_combat, process_player_action
from jester.engine.rules import Capability, evaluate_capabilities, get_capability
from tests.runtime_factory import build_session


def test_capability_registry_reports_supported_and_unsupported_rules() -> None:
    supported = get_capability(Capability.ATTACK)
    unsupported = evaluate_capabilities('Can I cast fireball as a reaction with concentration?')
    unsupported_capabilities = {decision.capability for decision in unsupported if not decision.supported}

    assert supported.supported is True
    assert Capability.SPELLCASTING_BASIC in unsupported_capabilities
    assert Capability.REACTION in unsupported_capabilities
    assert Capability.CONCENTRATION in unsupported_capabilities


def test_scenario_engine_is_replayable() -> None:
    session = build_session(seed=23)
    initialize_combat(session, ['pc-1', 'pc-2', 'npc-1'])
    engine = DeterministicScenarioEngine()
    steps = [
        ScenarioStep(
            actor_id='pc-1',
            intent=ActionIntent(
                intent_id='attack-1',
                action_type=ActionType.ATTACK,
                target_id='npc-1',
            ),
        ),
        ScenarioStep(
            actor_id='pc-1',
            intent=ActionIntent(
                intent_id='end-turn-1',
                action_type=ActionType.END_TURN,
            ),
        ),
    ]

    first = engine.run(session, steps)
    second = engine.run(session, steps)

    assert first.final_session.model_dump(mode='json') == second.final_session.model_dump(mode='json')
    assert [result.status for result in first.results] == [result.status for result in second.results]


def test_attack_resolution_records_rule_trace_and_zero_hp_condition() -> None:
    session = build_session()
    session.npcs['npc-1'].current_hp = 1
    initialize_combat(session, ['pc-1', 'pc-2', 'npc-1'])

    result = process_player_action(
        session,
        'pc-1',
        ActionIntent(
            intent_id='attack-1',
            action_type=ActionType.ATTACK,
            target_id='npc-1',
        ),
    )

    assert result.attack_result is not None
    assert any(trace.rule == 'attack.hit_check' for trace in result.rule_trace)
    assert any(condition.kind.value == 'UNCONSCIOUS' for condition in session.npcs['npc-1'].conditions)
