from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from jester.api.schemas.common import ResponseMeta
from jester.app.contracts import LessonResponse, TeachingRequest


class TeachingApiRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    request: TeachingRequest


class TeachingApiResponse(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    meta: ResponseMeta
    lesson: LessonResponse
