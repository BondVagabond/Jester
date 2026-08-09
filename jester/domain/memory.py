from __future__ import annotations

from pydantic import Field, model_validator

from jester.domain.base import DomainModel
from jester.domain.enums import MemoryScope


class MemoryRecord(DomainModel):
    record_id: str | None = None
    scope: MemoryScope
    content: str = Field(min_length=1)
    entity_id: str | None = None
    owner_id: str | None = None
    created_by_actor_id: str | None = None
    sequence_number: int | None = Field(default=None, ge=1)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scope_rules(self) -> MemoryRecord:
        if self.scope == MemoryScope.PLAYER_PRIVATE and not self.owner_id:
            raise ValueError("PLAYER_PRIVATE memory requires owner_id.")
        return self


class Memory(DomainModel):
    next_sequence: int = Field(default=1, ge=1)
    records: list[MemoryRecord] = Field(default_factory=list)
