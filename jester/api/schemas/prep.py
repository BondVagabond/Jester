from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from jester.api.schemas.common import ResponseMeta
from jester.app.contracts import PrepRequest, PrepResponse


class PrepApiRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    request: PrepRequest


class PrepApiResponse(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    meta: ResponseMeta
    prep: PrepResponse
