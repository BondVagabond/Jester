from __future__ import annotations

from jester.domain import MemoryRecord, MemoryScope
from jester.engine import add_memory, get_visible_state
from tests.runtime_factory import build_session


def test_dm_and_players_receive_different_views() -> None:
    session = build_session()
    add_memory(
        session,
        MemoryRecord(
            scope=MemoryScope.PUBLIC,
            content='The corridor is damp.',
            entity_id='scene-1',
        ),
    )
    add_memory(
        session,
        MemoryRecord(
            scope=MemoryScope.PARTY,
            content='The party saw fresh tracks.',
            entity_id='scene-1',
        ),
    )
    add_memory(
        session,
        MemoryRecord(
            scope=MemoryScope.PLAYER_PRIVATE,
            content='Aria notices a hidden engraving.',
            entity_id='pc-1',
            owner_id='player-1',
        ),
    )
    add_memory(
        session,
        MemoryRecord(
            scope=MemoryScope.DM_PRIVATE,
            content='A trap will spring on round two.',
            entity_id='scene-1',
        ),
    )

    dm_view = get_visible_state(session, None)
    player_one_view = get_visible_state(session, 'player-1')
    player_two_view = get_visible_state(session, 'player-2')

    assert len(dm_view['memory']['records']) == 4
    assert len(player_one_view['memory']['records']) == 3
    assert len(player_two_view['memory']['records']) == 2
    assert player_one_view['player_characters']['pc-1']['private_notes'] is not None
    assert player_one_view['player_characters']['pc-2']['private_notes'] is None
    assert player_two_view['player_characters']['pc-1']['private_notes'] is None
    assert player_one_view['scenes']['scene-1']['dm_notes'] is None
    assert dm_view['scenes']['scene-1']['dm_notes'] is not None