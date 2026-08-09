from __future__ import annotations

from jester.app.visibility import build_visible_session_view
from jester.domain import MemoryRecord, MemoryScope
from jester.engine import add_memory
from tests.runtime_factory import build_session


def test_visible_session_view_enforces_privacy_boundaries() -> None:
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

    dm_view = build_visible_session_view(session, None)
    player_view = build_visible_session_view(session, 'player-1')

    assert dm_view.scenes['scene-1'].dm_notes is not None
    assert player_view.scenes['scene-1'].dm_notes is None
    assert player_view.player_characters['pc-1'].private_notes is not None
    assert player_view.player_characters['pc-2'].private_notes is None
    assert len(dm_view.memory) == 3
    assert len(player_view.memory) == 2
    assert all(record.scope != MemoryScope.DM_PRIVATE for record in player_view.memory)