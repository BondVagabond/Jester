from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from jester.api.schemas.common import ResponseMeta
from jester.app.contracts import ViewerRole, VisibleSessionView
from jester.app.session_templates import SessionTemplateId
from jester.domain import Session


class UpsertSessionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    session: Session
    expected_revision: int | None = Field(default=None, ge=1)


class SessionRecordResponse(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    meta: ResponseMeta
    session: Session
    revision: int = Field(ge=1)
    campaign_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)


class SessionSummary(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    session_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    name: str = Field(min_length=1)


class SessionListResponse(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    meta: ResponseMeta
    sessions: list[SessionSummary] = Field(default_factory=list)


class SessionViewerOption(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    viewer_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    role: ViewerRole


class BootstrapSessionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    session_name: str | None = Field(default=None, min_length=1)
    template_id: SessionTemplateId = SessionTemplateId.COPPER_VAULT
    start_in_combat: bool = True


class BootstrapSessionResponse(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    meta: ResponseMeta
    session: Session
    revision: int = Field(ge=1)
    campaign_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    viewer_options: list[SessionViewerOption] = Field(default_factory=list)


class VisibleSessionRecordResponse(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    meta: ResponseMeta
    session_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    view: VisibleSessionView
    viewer_options: list[SessionViewerOption] = Field(default_factory=list)

