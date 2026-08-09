from __future__ import annotations

from jester.domain import ActionIntent, ActionResult, ActionStatus, ActionType, Session
from jester.engine.combat import apply_state_delta, resolve_attack, resolve_end_turn, resolve_movement
from jester.engine.rules import validate_action_basics, validate_attack_action, validate_movement_action


def process_player_action(
    session: Session,
    actor_id: str,
    intent: ActionIntent,
) -> ActionResult:
    errors = _validate_action(session, actor_id, intent)
    if errors:
        return ActionResult(
            status=ActionStatus.REJECTED,
            action_type=intent.action_type,
            actor_id=actor_id,
            target_id=intent.target_id,
            errors=errors,
            rule_trace=[],
        )

    combat_state = session.combat_state
    if combat_state is None:
        raise ValueError('Validated actions require an active combat state.')

    action_number = session.action_counter + 1
    actor = combat_state.combatants[actor_id]

    if intent.action_type == ActionType.ATTACK:
        if intent.target_id is None:
            raise ValueError('Validated attack must have a target_id.')
        target = combat_state.combatants[intent.target_id]
        attack_result = resolve_attack(session, actor, target, action_number=action_number)
        apply_state_delta(session, attack_result.state_delta)
        result = ActionResult(
            sequence_number=action_number,
            status=ActionStatus.APPLIED,
            action_type=intent.action_type,
            actor_id=actor_id,
            target_id=intent.target_id,
            attack_result=attack_result,
            state_delta=attack_result.state_delta,
            rule_trace=list(attack_result.rule_trace),
        )
    elif intent.action_type == ActionType.MOVE:
        if intent.destination is None:
            raise ValueError('Validated move must have a destination.')
        movement_result = resolve_movement(actor, intent.destination)
        apply_state_delta(session, movement_result.state_delta)
        result = ActionResult(
            sequence_number=action_number,
            status=ActionStatus.APPLIED,
            action_type=intent.action_type,
            actor_id=actor_id,
            movement_result=movement_result,
            state_delta=movement_result.state_delta,
            rule_trace=list(movement_result.rule_trace),
        )
    elif intent.action_type == ActionType.END_TURN:
        state_delta = resolve_end_turn(combat_state)
        apply_state_delta(session, state_delta)
        result = ActionResult(
            sequence_number=action_number,
            status=ActionStatus.APPLIED,
            action_type=intent.action_type,
            actor_id=actor_id,
            ended_turn=True,
            state_delta=state_delta,
            rule_trace=[],
        )
    else:
        raise ValueError(f'Unsupported action type {intent.action_type!r}.')

    session.action_counter = action_number
    session.action_history.append(result)
    return result


def _validate_action(session: Session, actor_id: str, intent: ActionIntent) -> list[str]:
    combat_state = session.combat_state
    if combat_state is None:
        return ['Combat is not active.']

    errors = validate_action_basics(combat_state, actor_id, intent)
    if errors:
        return errors

    if intent.action_type == ActionType.ATTACK:
        return validate_attack_action(combat_state, actor_id, intent.target_id)
    if intent.action_type == ActionType.MOVE:
        if intent.destination is None:
            return ['Move actions require a destination.']
        actor = combat_state.combatants[actor_id]
        return validate_movement_action(actor, intent.destination)
    if intent.action_type == ActionType.END_TURN:
        return []
    return [f'Unsupported action type {intent.action_type!r}.']
