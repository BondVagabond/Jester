from __future__ import annotations

from jester.domain import (
    AttackResult,
    Combatant,
    CombatState,
    ConditionType,
    DiceExpression,
    HitPointChange,
    RuleTraceEntry,
    Session,
    StateDelta,
)
from jester.engine.dice import DeterministicDiceRoller
from jester.engine.rules.conditions import has_condition
from jester.engine.rules.cover import cover_bonus_for_attack
from jester.engine.rules.death import build_defeat_condition_changes
from jester.engine.rules.modifiers import attack_total, distance_between_combatants


def validate_attack_action(
    combat_state: CombatState,
    actor_id: str,
    target_id: str | None,
) -> list[str]:
    if target_id is None:
        return ['Attack actions require target_id.']
    if target_id not in combat_state.combatants:
        return [f'Target {target_id!r} is not part of the active combat.']
    if target_id == actor_id:
        return ['Actors cannot target themselves with ATTACK.']

    actor = combat_state.combatants[actor_id]
    target = combat_state.combatants[target_id]
    if has_condition(target, ConditionType.UNCONSCIOUS):
        return []
    distance = distance_between_combatants(actor, target)
    if distance > actor.attack_range:
        return [f'Target {target_id!r} is out of range.']
    return []


def resolve_attack_action(
    session: Session,
    attacker: Combatant,
    target: Combatant,
    *,
    action_number: int,
) -> AttackResult:
    attack_roll_outcome = DeterministicDiceRoller.roll(
        DiceExpression(count=1, sides=20),
        seed=session.random_seed,
        namespace=(
            f'{session.session_id}:{action_number}:attack:'
            f'{attacker.combatant_id}:{target.combatant_id}'
        ),
    )
    attack_roll = attack_roll_outcome.individual_rolls[0]
    cover_bonus = cover_bonus_for_attack(attacker=attacker, target=target)
    adjusted_armor_class = target.armor_class + cover_bonus
    total = attack_total(attack_roll=attack_roll, attack_bonus=attacker.attack_bonus)
    hit = attack_roll == 20 or (attack_roll != 1 and total >= adjusted_armor_class)
    trace = [
        RuleTraceEntry(
            rule='attack.hit_check',
            detail=(
                f'Attack roll {attack_roll} + {attacker.attack_bonus} produced {total} '
                f'against AC {adjusted_armor_class}.'
            ),
            capability='attack',
        )
    ]

    if not hit:
        trace.append(
            RuleTraceEntry(
                rule='attack.miss',
                detail='The attack did not meet the target armor class.',
                capability='attack',
            )
        )
        return AttackResult(
            attacker_id=attacker.combatant_id,
            target_id=target.combatant_id,
            attack_roll=attack_roll,
            attack_total=total,
            target_armor_class=adjusted_armor_class,
            hit=False,
            damage_roll=0,
            damage_applied=0,
            state_delta=StateDelta(),
            rule_trace=trace,
        )

    damage_outcome = DeterministicDiceRoller.roll(
        attacker.damage,
        seed=session.random_seed,
        namespace=(
            f'{session.session_id}:{action_number}:damage:'
            f'{attacker.combatant_id}:{target.combatant_id}'
        ),
    )
    damage_total = max(0, damage_outcome.total)
    next_hp = max(0, target.current_hp - damage_total)
    damage_applied = target.current_hp - next_hp
    condition_changes = build_defeat_condition_changes(
        target=target,
        source_id=attacker.combatant_id,
        next_hp=next_hp,
    )
    state_delta = StateDelta(
        hit_point_changes=[
            HitPointChange(
                entity_id=target.combatant_id,
                previous_hp=target.current_hp,
                current_hp=next_hp,
            )
        ],
        condition_changes=condition_changes,
    )
    trace.append(
        RuleTraceEntry(
            rule='attack.damage',
            detail=f'Damage roll resolved to {damage_total}; applied {damage_applied} hit points.',
            capability='damage',
        )
    )
    if condition_changes:
        trace.append(
            RuleTraceEntry(
                rule='death.zero_hp',
                detail='Target reached zero hit points and gained the unconscious condition.',
                capability='conditions_basic',
            )
        )
    return AttackResult(
        attacker_id=attacker.combatant_id,
        target_id=target.combatant_id,
        attack_roll=attack_roll,
        attack_total=total,
        target_armor_class=adjusted_armor_class,
        hit=True,
        damage_roll=damage_total,
        damage_applied=damage_applied,
        state_delta=state_delta,
        rule_trace=trace,
    )
