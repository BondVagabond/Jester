"""Prompt cases, fixture values and per-role checks for the Ollama spike harness."""

from __future__ import annotations

import json
from dataclasses import dataclass

from jester.prompts.registry import load_prompt
from jester.validation import validate_output

# Fixture values keyed by input_contract variable name. Prompts share variable
# names, so one table covers the whole suite. Values are deliberately realistic -
# invented prompts would not answer the question the spike exists to answer.
FIXTURES: dict[str, str] = {
    'state_summary': (
        'Scene: the Copper Vault, a smugglers hideout beneath the old customs house. '
        'Party: Aria (fighter, 24/30 HP), Bram (cleric, 19/22 HP). '
        'Enemies: Goblin Lookout (7/12 HP, prone). Round 2, Aria to act.'
    ),
    'action_summary': 'Aria attacks the Goblin Lookout with a longsword and hits for 7 slashing damage.',
    'retrieved_context': (
        'Attack Roll Sequence: roll d20, add ability modifier and proficiency, compare to AC. '
        'Damage Step: on a hit, roll the weapon damage die and add the ability modifier.'
    ),
    'artifact_type': 'NPC_BRIEF',
    'topic': 'Sera Duskwater, harbourmaster of Stonebridge',
    'goal': 'Give the party a reason to investigate the missing cargo manifest',
    'inputs_used': 'campaign notes, previous session summary',
    'draft_text': (
        'Sera Duskwater runs the Stonebridge docks with a firm hand and a soft spot for '
        'stray cats. She knows more about the missing cargo manifest than she lets on.'
    ),
    'structured_summary': (
        'Objective: introduce Sera Duskwater as a lead for the missing cargo manifest. '
        'Sections: role, motivation, hook to investigate.'
    ),
    'concept': 'ATTACK_ROLLS',
    'question': 'How does cover affect an attack roll?',
    'prerequisites': 'ability modifiers, proficiency bonus, and reading a character sheet',
    'misconceptions': 'Players often assume any attack that hits deals maximum damage.',
    'retrieved_rules': (
        'Attack Roll Sequence: roll d20, add ability modifier and proficiency, compare to AC. '
        'Cover grants +2 (half cover) or +5 (three-quarters cover) to AC.'
    ),
    'request_text': 'I want to sneak past the guards and reach the vault door.',
    'fallback_kind': 'MECHANICAL_ACTION',
    'depth': 'STANDARD',
    'fallback_depth': 'INTERMEDIATE',
    'lesson_focus': 'attack rolls and armour class',
}


@dataclass(frozen=True)
class PromptCase:
    role: str
    prompt_name: str
    version: str
    expects_json: bool
    num_predict: int
    temperature: float


SUITE: list[PromptCase] = [
    PromptCase('router', 'routing_live_dm_intent', 'v1', True, 256, 0.0),
    PromptCase('router', 'teaching_depth', 'v1', True, 256, 0.0),
    PromptCase('arbiter', 'prep_plan', 'v1', True, 512, 0.0),
    PromptCase('arbiter', 'prep_critique', 'v1', True, 512, 0.0),
    PromptCase('arbiter', 'teaching_structure', 'v1', True, 512, 0.0),
    PromptCase('narrator', 'live_dm_narration', 'v1', False, 384, 0.2),
    PromptCase('narrator', 'live_dm_info_response', 'v1', False, 384, 0.2),
    PromptCase('narrator', 'prep_npc', 'v1', False, 512, 0.2),
    PromptCase('narrator', 'teaching_explain_concept', 'v1', False, 512, 0.2),
]


def render_prompt(name: str, version: str) -> tuple[str, dict[str, str]]:
    """Render a real prompt with fixture values. Returns (rendered, output_contract)."""
    spec = load_prompt(name, version)
    values = {key: FIXTURES.get(key, f'[no fixture for {key}]') for key in spec.input_contract}
    return spec.template.format(**values), dict(spec.output_contract)


def check_call(case: PromptCase, content: str, output_contract: dict[str, str]) -> bool:
    if case.expects_json:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return False
        if not isinstance(parsed, dict):
            return False
        return all(key in parsed for key in output_contract)
    return bool(validate_output(content).is_valid)
