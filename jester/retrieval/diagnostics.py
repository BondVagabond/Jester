from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from jester.retrieval.contracts import FilterValue, RetrievalHit


class BackendDiagnostic(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    backend_name: str = Field(min_length=1)
    corpus_id: str = Field(min_length=1)
    latency_ms: int = Field(default=0, ge=0)
    available: bool = True
    degraded: bool = False
    hits_returned: int = Field(default=0, ge=0)
    rejected_artifacts: list[str] = Field(default_factory=list)
    error: str | None = None


class RetrievalDiagnostics(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    request_id: str | None = None
    session_id: str | None = None
    tenant_id: str | None = None
    query_text: str = Field(min_length=1)
    requested_k: int = Field(ge=1)
    corpora_considered: list[str] = Field(default_factory=list)
    filters_applied: dict[str, FilterValue] | None = None
    cache_hit: bool = False
    degraded: bool = False
    failure_messages: list[str] = Field(default_factory=list)
    backend_diagnostics: list[BackendDiagnostic] = Field(default_factory=list)
    rerank_strategy: str = Field(default='lexical_coverage', min_length=1)


class RetrievalResponse(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    hits: list[RetrievalHit] = Field(default_factory=list)
    diagnostics: RetrievalDiagnostics
