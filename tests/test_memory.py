from __future__ import annotations

from jester.domain import MemoryRecord, MemoryScope
from jester.engine import add_memory, query_memory
from tests.runtime_factory import build_session


def test_query_memory_returns_scoped_entity_records_in_order() -> None:
    session = build_session()
    add_memory(
        session,
        MemoryRecord(
            scope=MemoryScope.PUBLIC,
            content='First clue.',
            entity_id='npc-1',
        ),
    )
    add_memory(
        session,
        MemoryRecord(
            scope=MemoryScope.PUBLIC,
            content='Second clue.',
            entity_id='npc-1',
        ),
    )
    add_memory(
        session,
        MemoryRecord(
            scope=MemoryScope.PARTY,
            content='Shared clue.',
            entity_id='npc-1',
        ),
    )

    public_records = query_memory(session, MemoryScope.PUBLIC, 'npc-1')
    assert [record.content for record in public_records] == ['First clue.', 'Second clue.']