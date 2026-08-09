from __future__ import annotations

from jester.domain import (
    NPC,
    AttackResult,
    Combatant,
    CombatState,
    DiceExpression,
    InitiativeOrder,
    MovementResult,
    PlayerCharacter,
    Position,
    Session,
    StateDelta,
)
from jester.engine.dice import DeterministicDiceRoller
from jester.engine.rules import (
    current_combatant,
    merge_conditions,
    resolve_attack_action,
    resolve_end_turn_state_delta,
    resolve_movement_action,
)

ActorEntity = PlayerCharacter | NPC


def initialize_combat(
    session: Session,
    combatant_ids: list[str],
    *,
    combat_id: str | None = None,
) -> CombatState:
    if not combatant_ids:
        raise ValueError('Combat requires at least one combatant.')

    combatants: dict[str, Combatant] = {}
    for combatant_id in combatant_ids:
        entity = get_actor_entity(session, combatant_id)
        initiative_roll = DeterministicDiceRoller.roll(
            DiceExpression(count=1, sides=20),
            seed=session.random_seed,
            namespace=f'{session.session_id}:{session.current_scene_id}:initiative:{combatant_id}',
        )
        roll_value = initiative_roll.individual_rolls[0]
        total_value = roll_value + entity.initiative_modifier
        team_id = 'party'
        if not isinstance(entity, PlayerCharacter):
            team_id = entity.faction or 'hostile'
        combatants[combatant_id] = Combatant(
            combatant_id=combatant_id,
            entity_id=entity.entity_id,
            name=entity.name,
            controller_id=getattr(entity, 'controller_id', None),
            is_player_controlled=isinstance(entity, PlayerCharacter),
            team_id=team_id,
            armor_class=entity.armor_class,
            max_hp=entity.max_hp,
            current_hp=entity.current_hp,
            initiative_modifier=entity.initiative_modifier,
            initiative_roll=roll_value,
            initiative_total=total_value,
            attack_bonus=entity.attack_bonus,
            attack_range=entity.attack_range,
            damage=entity.damage,
            speed=entity.speed,
            movement_remaining=entity.speed,
            position=entity.scene_position.model_copy(deep=True),
            conditions=[condition.model_copy(deep=True) for condition in entity.conditions],
        )

    ordered = sorted(
        combatants.values(),
        key=lambda combatant: (
            -combatant.initiative_total,
            -combatant.initiative_roll,
            combatant.combatant_id,
        ),
    )
    state = CombatState(
        combat_id=combat_id or f'{session.session_id}-combat-{session.action_counter + 1}',
        scene_id=session.current_scene_id,
        initiative=InitiativeOrder(
            ordered_combatant_ids=[combatant.combatant_id for combatant in ordered],
            current_index=0,
        ),
        combatants=combatants,
        round_number=1,
        active=True,
        completed=False,
    )
    session.combat_state = state
    return state


def get_current_combatant(combat_state: CombatState) -> Combatant:
    return current_combatant(combat_state)


def get_actor_entity(session: Session, actor_id: str) -> ActorEntity:
    if actor_id in session.player_characters:
        return session.player_characters[actor_id]
    if actor_id in session.npcs:
        return session.npcs[actor_id]
    raise KeyError(f'Unknown actor {actor_id!r}.')


def resolve_attack(
    session: Session,
    attacker: Combatant,
    target: Combatant,
    *,
    action_number: int,
) -> AttackResult:
    return resolve_attack_action(
        session,
        attacker,
        target,
        action_number=action_number,
    )


def resolve_movement(actor: Combatant, destination: Position) -> MovementResult:
    return resolve_movement_action(actor, destination)


def resolve_end_turn(combat_state: CombatState) -> StateDelta:
    return resolve_end_turn_state_delta(combat_state)


def apply_state_delta(session: Session, state_delta: StateDelta) -> None:
    combat_state = session.combat_state
    if combat_state is None:
        raise ValueError('Cannot apply state delta without an active combat state.')

    for hp_change in state_delta.hit_point_changes:
        combatant = combat_state.combatants[hp_change.entity_id]
        combatant.current_hp = hp_change.current_hp
        entity = get_actor_entity(session, hp_change.entity_id)
        entity.current_hp = hp_change.current_hp

    for position_change in state_delta.position_changes:
        combatant = combat_state.combatants[position_change.entity_id]
        combatant.position = position_change.current_position.model_copy(deep=True)
        entity = get_actor_entity(session, position_change.entity_id)
        entity.scene_position = position_change.current_position.model_copy(deep=True)

    for condition_change in state_delta.condition_changes:
        combatant = combat_state.combatants[condition_change.entity_id]
        updated_conditions = merge_conditions(
            combatant.conditions,
            condition_change.added,
            condition_change.removed,
        )
        combatant.conditions = updated_conditions
        entity = get_actor_entity(session, condition_change.entity_id)
        entity.conditions = [condition.model_copy(deep=True) for condition in updated_conditions]

    for movement_change in state_delta.movement_budget_changes:
        combatant = combat_state.combatants[movement_change.entity_id]
        combatant.movement_remaining = movement_change.current_remaining

    if state_delta.turn_change is not None:
        next_id = state_delta.turn_change.current_combatant_id
        initiative = combat_state.initiative
        initiative.current_index = initiative.ordered_combatant_ids.index(next_id)
        combat_state.round_number = state_delta.turn_change.current_round_number
