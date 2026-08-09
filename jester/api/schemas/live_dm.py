from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from jester.api.schemas.common import ResponseMeta
from jester.app.contracts import LiveDmRequest, LiveDmTurnResponse


class LiveDmTurnCommand(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    request: LiveDmRequest
    expected_revision: int | None = Field(default=None, ge=1)
    fast_path: bool = False


class LiveDmTurnApiResponse(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    meta: ResponseMeta
    response: LiveDmTurnResponse
    session_revision: int = Field(ge=1)
