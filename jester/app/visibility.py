from __future__ import annotations

from jester.app.contracts.common import ViewerRole
from jester.app.contracts.live_dm import (
    VisibleActionLogEntry,
    VisibleCampaignView,
    VisibleCombatantView,
    VisibleCombatStateView,
    VisibleConditionView,
    VisibleLocationView,
    VisibleMemoryRecord,
    VisibleNpcView,
    VisiblePartyView,
    VisiblePlayerCharacterView,
    VisiblePositionView,
    VisibleSceneView,
    VisibleSessionView,
)
from jester.domain import ActionResult, Session
from jester.domain.combat import Condition
from jester.domain.enums import ActionStatus, ActionType
from jester.domain.memory import MemoryRecord

_RECENT_ACTION_LIMIT = 8


def build_visible_session_view(session: Session, viewer_id: str | None) -> VisibleSessionView:
    viewer_role, normalized_viewer_id = _resolve_viewer(session, viewer_id)

    scenes = {
        scene_id: VisibleSceneView(
            scene_id=scene.scene_id,
            campaign_id=scene.campaign_id,
            location_id=scene.location_id,
            party_id=scene.party_id,
            name=scene.name,
            summary=scene.summary,
            participant_ids=list(scene.participant_ids),
            active=scene.active,
            dm_notes=scene.dm_notes if viewer_role == ViewerRole.DM else None,
        )
        for scene_id, scene in session.scenes.items()
    }
    player_characters = {
        entity_id: VisiblePlayerCharacterView(
            entity_id=pc.entity_id,
            name=pc.name,
            controller_id=pc.controller_id,
            character_class=pc.character_class,
            level=pc.level,
            armor_class=pc.armor_class,
            max_hp=pc.max_hp,
            current_hp=pc.current_hp,
            position=VisiblePositionView(slot=pc.scene_position.slot),
            conditions=[_build_condition_view(condition) for condition in pc.conditions],
            private_notes=(
                pc.private_notes
                if viewer_role == ViewerRole.DM or pc.controller_id == normalized_viewer_id
                else None
            ),
        )
        for entity_id, pc in session.player_characters.items()
    }
    npcs = {
        entity_id: VisibleNpcView(
            entity_id=npc.entity_id,
            name=npc.name,
            faction=npc.faction,
            armor_class=npc.armor_class,
            max_hp=npc.max_hp,
            current_hp=npc.current_hp,
            position=VisiblePositionView(slot=npc.scene_position.slot),
            conditions=[_build_condition_view(condition) for condition in npc.conditions],
            dm_notes=npc.dm_notes if viewer_role == ViewerRole.DM else None,
        )
        for entity_id, npc in session.npcs.items()
    }
    locations = {
        location_id: VisibleLocationView(
            location_id=location.location_id,
            name=location.name,
            description=location.description,
            connected_location_ids=list(location.connected_location_ids),
            tags=list(location.tags),
            dm_notes=location.dm_notes if viewer_role == ViewerRole.DM else None,
        )
        for location_id, location in session.locations.items()
    }
    combat_state = None
    if session.combat_state is not None:
        combat_state = VisibleCombatStateView(
            combat_id=session.combat_state.combat_id,
            scene_id=session.combat_state.scene_id,
            round_number=session.combat_state.round_number,
            active=session.combat_state.active,
            completed=session.combat_state.completed,
            initiative_order=list(session.combat_state.initiative.ordered_combatant_ids),
            current_combatant_id=session.combat_state.initiative.current_combatant_id,
            combatants={
                combatant_id: VisibleCombatantView(
                    combatant_id=combatant.combatant_id,
                    name=combatant.name,
                    is_player_controlled=combatant.is_player_controlled,
                    team_id=combatant.team_id,
                    armor_class=combatant.armor_class,
                    max_hp=combatant.max_hp,
                    current_hp=combatant.current_hp,
                    attack_range=combatant.attack_range,
                    speed=combatant.speed,
                    movement_remaining=combatant.movement_remaining,
                    position=VisiblePositionView(slot=combatant.position.slot),
                    conditions=[_build_condition_view(condition) for condition in combatant.conditions],
                )
                for combatant_id, combatant in session.combat_state.combatants.items()
            },
        )

    visible_memory = [
        VisibleMemoryRecord(
            record_id=record.record_id,
            scope=record.scope,
            content=record.content,
            entity_id=record.entity_id,
            owner_id=record.owner_id if viewer_role == ViewerRole.DM else None,
            sequence_number=record.sequence_number,
            tags=list(record.tags),
        )
        for record in session.memory.records
        if _record_visible_to_viewer(record, viewer_role, normalized_viewer_id)
    ]

    return VisibleSessionView(
        session_id=session.session_id,
        campaign_id=session.campaign_id,
        name=session.name,
        viewer_id=normalized_viewer_id,
        viewer_role=viewer_role,
        current_scene_id=session.current_scene_id,
        action_counter=session.action_counter,
        campaign=VisibleCampaignView(
            campaign_id=session.campaign.campaign_id,
            name=session.campaign.name,
            description=session.campaign.description,
        ),
        party=VisiblePartyView(
            party_id=session.party.party_id,
            campaign_id=session.party.campaign_id,
            member_ids=list(session.party.member_ids),
            shared_notes=session.party.shared_notes,
        ),
        scenes=scenes,
        player_characters=player_characters,
        npcs=npcs,
        locations=locations,
        combat_state=combat_state,
        memory=visible_memory,
        recent_actions=_build_recent_actions(session),
    )


def _resolve_viewer(session: Session, viewer_id: str | None) -> tuple[ViewerRole, str | None]:
    if viewer_id is None or viewer_id == session.dm_id:
        return ViewerRole.DM, viewer_id
    if viewer_id not in session.player_ids:
        raise ValueError(f'Viewer {viewer_id!r} is not part of session {session.session_id!r}.')
    return ViewerRole.PLAYER, viewer_id


def _build_condition_view(condition: Condition) -> VisibleConditionView:
    return VisibleConditionView(
        kind=condition.kind,
        source_id=condition.source_id,
        note=condition.note,
    )


def _record_visible_to_viewer(
    record: MemoryRecord,
    viewer_role: ViewerRole,
    viewer_id: str | None,
) -> bool:
    if viewer_role == ViewerRole.DM:
        return True
    if record.scope.value in {'PUBLIC', 'PARTY'}:
        return True
    if record.scope.value == 'PLAYER_PRIVATE':
        return record.owner_id == viewer_id
    return False


def _build_recent_actions(session: Session) -> list[VisibleActionLogEntry]:
    recent_results = session.action_history[-_RECENT_ACTION_LIMIT:]
    entries: list[VisibleActionLogEntry] = []
    for index, result in enumerate(recent_results, start=max(1, len(session.action_history) - len(recent_results) + 1)):
        sequence_number = result.sequence_number or index
        actor_name = _entity_name(session, result.actor_id) or result.actor_id
        target_name = _entity_name(session, result.target_id)
        entries.append(
            VisibleActionLogEntry(
                sequence_number=sequence_number,
                status=result.status,
                action_type=result.action_type,
                actor_id=result.actor_id,
                actor_name=actor_name,
                target_id=result.target_id,
                target_name=target_name,
                summary=_build_action_summary(result, actor_name=actor_name, target_name=target_name),
                state_changed=_state_changed(result),
            )
        )
    return entries


def _entity_name(session: Session, entity_id: str | None) -> str | None:
    if entity_id is None:
        return None
    if entity_id in session.player_characters:
        return session.player_characters[entity_id].name
    if entity_id in session.npcs:
        return session.npcs[entity_id].name
    return entity_id


def _build_action_summary(
    result: ActionResult,
    *,
    actor_name: str,
    target_name: str | None,
) -> str:
    if result.status == ActionStatus.REJECTED:
        if result.errors:
            return result.errors[0]
        return f'{actor_name} could not complete {result.action_type.value.replace("_", " ").lower()}.'

    if result.action_type == ActionType.ATTACK and result.attack_result is not None:
        if result.attack_result.hit:
            return (
                f'{actor_name} hit {target_name or result.target_id or "the target"} '
                f'for {result.attack_result.damage_applied} damage.'
            )
        return f'{actor_name} missed {target_name or result.target_id or "the target"}.'

    if result.action_type == ActionType.MOVE and result.movement_result is not None:
        return f'{actor_name} moved to slot {result.movement_result.current_position.slot}.'

    if result.action_type == ActionType.END_TURN:
        return f'{actor_name} ended the turn.'

    return f'{actor_name} resolved {result.action_type.value.replace("_", " ").lower()}.'


def _state_changed(result: ActionResult) -> bool:
    if result.status != ActionStatus.APPLIED:
        return False
    delta = result.state_delta
    return bool(
        delta.hit_point_changes
        or delta.position_changes
        or delta.condition_changes
        or delta.movement_budget_changes
        or delta.turn_change is not None
        or result.ended_turn
    )

