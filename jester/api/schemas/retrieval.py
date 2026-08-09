from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from jester.api.schemas.common import ResponseMeta
from jester.retrieval import RetrievalResponse


class RetrievalDebugRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    text: str = Field(min_length=1)
    corpus: str | None = None
    filters: dict[str, str | list[str]] | None = None
    k: int = Field(default=5, ge=1, le=25)
    allow_degraded: bool = True


class RetrievalDebugResponse(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    meta: ResponseMeta
    retrieval: RetrievalResponse
