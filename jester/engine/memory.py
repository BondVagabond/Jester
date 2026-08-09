from __future__ import annotations

from jester.domain import Memory, MemoryRecord, MemoryScope, Session


def add_memory(session: Session, record: MemoryRecord) -> MemoryRecord:
    stored_record = record.model_copy(
        update={
            'record_id': record.record_id or f'memory-{session.memory.next_sequence}',
            'sequence_number': record.sequence_number or session.memory.next_sequence,
        }
    )
    updated_memory = Memory(
        next_sequence=session.memory.next_sequence + 1,
        records=[*session.memory.records, stored_record],
    )
    session.memory = updated_memory
    return stored_record


def query_memory(
    session: Session,
    scope: MemoryScope,
    entity_id: str | None,
) -> list[MemoryRecord]:
    results = [
        record
        for record in session.memory.records
        if record.scope == scope and (entity_id is None or record.entity_id == entity_id)
    ]
    return sorted(
        results,
        key=lambda record: record.sequence_number or 0,
    )
