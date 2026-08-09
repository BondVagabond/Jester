from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from jester.ai import ModelSelection
from jester.retrieval import BackendStatus


class HealthStatusResponse(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    status: str = Field(min_length=1)


class DependencyHealthResponse(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    status: str = Field(min_length=1)
    database: str = Field(min_length=1)
    retrieval: str = Field(min_length=1)
    models: dict[str, ModelSelection] = Field(default_factory=dict)
    retrieval_backends: list[BackendStatus] = Field(default_factory=list)
