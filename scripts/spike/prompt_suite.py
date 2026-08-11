"""Prompt cases, fixture values and per-role checks for the Ollama spike harness."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from pydantic import BaseModel, ValidationError

from jester.ai import (
    CritiqueArtifact,
    IntentClassificationArtifact,
    ModelRole,
    PlanArtifact,
    TeachingDepthArtifact,
    TeachingPlanArtifact,
)
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

# Human-readable labels for the report table. Bijective with ModelRole - the
# harness only ever exercises these three roles.
ROLE_LABELS: dict[ModelRole, str] = {
    ModelRole.SMALL_FAST: 'router',
    ModelRole.REASONING: 'arbiter',
    ModelRole.PRIMARY_GENERATION: 'narrator',
}


def role_label(role: ModelRole) -> str:
    return ROLE_LABELS[role]


@dataclass(frozen=True)
class PromptCase:
    role: ModelRole
    prompt_name: str
    version: str
    expects_json: bool
    num_predict: int
    temperature: float
    # Per-case fixture overrides, consulted by render_prompt ahead of FIXTURES.
    # Needed because FIXTURES is keyed globally by variable name, but a couple
    # of prompts share a variable name (structured_summary) while needing
    # case-specific content - see teaching_explain_concept below.
    overrides: dict[str, str] = field(default_factory=dict)


# num_predict mirrors the max_tokens each prompt's production call site actually
# sends (see jester/ai/reasoning.py, jester/ai/classification.py, jester/ai/adapters.py
# and jester/app/orchestration/prompting.py):
#   - routing_live_dm_intent, teaching_depth: SmallFastClassifier._classify_json -> 256
#   - prep_plan, prep_critique, teaching_structure: ReasoningService.* -> 256
#   - live_dm_narration: RoleNarrationModelClient (build_narration path) -> 384
#   - live_dm_info_response, prep_npc, teaching_explain_concept: RolePromptModelClient
#     (generate_prompt_block / WorkspacePromptAssembler path) -> 512
SUITE: list[PromptCase] = [
    PromptCase(ModelRole.SMALL_FAST, 'routing_live_dm_intent', 'v1', True, 256, 0.0),
    PromptCase(ModelRole.SMALL_FAST, 'teaching_depth', 'v1', True, 256, 0.0),
    PromptCase(ModelRole.REASONING, 'prep_plan', 'v1', True, 256, 0.0),
    PromptCase(ModelRole.REASONING, 'prep_critique', 'v1', True, 256, 0.0),
    PromptCase(ModelRole.REASONING, 'teaching_structure', 'v1', True, 256, 0.0),
    PromptCase(ModelRole.PRIMARY_GENERATION, 'live_dm_narration', 'v1', False, 384, 0.2),
    PromptCase(ModelRole.PRIMARY_GENERATION, 'live_dm_info_response', 'v1', False, 512, 0.2),
    PromptCase(ModelRole.PRIMARY_GENERATION, 'prep_npc', 'v1', False, 512, 0.2),
    PromptCase(
        ModelRole.PRIMARY_GENERATION,
        'teaching_explain_concept',
        'v1',
        False,
        512,
        0.2,
        overrides={
            'structured_summary': (
                'Objective: explain how attack rolls resolve and how cover modifies AC. '
                'Sections: roll sequence (d20 plus ability modifier and proficiency vs AC), '
                'cover modifiers, worked example.'
            ),
        },
    ),
]


def render_prompt(case: PromptCase) -> tuple[str, dict[str, str]]:
    """Render a real prompt with fixture values. Returns (rendered, output_contract).

    Case-specific overrides win over the shared FIXTURES table, so two prompts that
    happen to share an input_contract variable name (e.g. structured_summary) do not
    have to share fixture content.
    """
    spec = load_prompt(case.prompt_name, case.version)
    values = {
        key: case.overrides.get(key, FIXTURES.get(key, f'[no fixture for {key}]'))
        for key in spec.input_contract
    }
    return spec.template.format(**values), dict(spec.output_contract)


# Real production validators for the JSON cases in SUITE, so a pass here means what
# production would accept. Every current JSON case has a corresponding artifact
# model; a case without one would fall back to the weaker key-presence check below.
_JSON_VALIDATORS: dict[str, type[BaseModel]] = {
    'routing_live_dm_intent': IntentClassificationArtifact,
    'teaching_depth': TeachingDepthArtifact,
    'prep_plan': PlanArtifact,
    'prep_critique': CritiqueArtifact,
    'teaching_structure': TeachingPlanArtifact,
}


def check_call(case: PromptCase, content: str, output_contract: dict[str, str]) -> bool:
    if case.expects_json:
        validator = _JSON_VALIDATORS.get(case.prompt_name)
        if validator is None:
            # No production artifact model exists for this prompt - fall back to a
            # key-presence check against the prompt's declared output_contract.
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                return False
            if not isinstance(parsed, dict):
                return False
            return all(key in parsed for key in output_contract)
        try:
            validator.model_validate_json(content)
        except (ValidationError, TypeError):
            # Some list-typed fields (e.g. PlanArtifact.steps) validate via a plain
            # `_normalize_text_list` helper that raises TypeError instead of ValueError
            # for a wrong-shaped value (e.g. a string where a list is expected).
            # Pydantic v2 only auto-wraps ValueError/AssertionError from validators
            # into ValidationError, so a malformed field of this kind reaches here as
            # a raw TypeError. Treated as a failed check, same as any other malformed
            # response - not silently propagated as a harness crash.
            return False
        return True
    return bool(validate_output(content).is_valid)
