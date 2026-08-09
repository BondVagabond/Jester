from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ResponseMeta(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    request_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    session_id: str | None = None
    degraded: bool = False
    warnings: list[str] = Field(default_factory=list)

    @field_validator('request_id', 'trace_id', 'tenant_id', 'session_id', mode='before')
    @classmethod
    def strip_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            raise ValueError('Metadata fields must not be blank.')
        return text


class ErrorPayload(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    request_id: str | None = None
    trace_id: str | None = None
    detail: str | None = None

    @field_validator('code', 'message', 'request_id', 'trace_id', 'detail', mode='before')
    @classmethod
    def strip_text(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            raise ValueError('Error payload text fields must not be blank.')
        return text


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    error: ErrorPayload
