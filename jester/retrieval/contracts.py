from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

type FilterValue = str | list[str]


class RetrievalError(RuntimeError):
    """Raised when retrieval cannot complete safely."""


class RetrievalUnavailableError(RetrievalError):
    """Raised when no retrieval backend can satisfy the request."""


class RetrievedDocument(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    doc_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    score: float
    source: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    corpus_id: str | None = None

    @field_validator('doc_id', 'chunk_id', 'title', 'text', 'source', mode='before')
    @classmethod
    def strip_required_text(cls, value: object) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError('Retrieved document fields must not be blank.')
        return text

    @field_validator('corpus_id', mode='before')
    @classmethod
    def strip_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator('tags', mode='before')
    @classmethod
    def normalize_tags(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        raise TypeError('tags must be a list[str] or null.')


class ProvenanceEntry(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    backend_name: str = Field(min_length=1)
    corpus_id: str = Field(min_length=1)
    corpus_version: str = Field(min_length=1)
    source: str = Field(min_length=1)


class RetrievalScoreBreakdown(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    fused_score: float = 0.0
    rerank_score: float = 0.0
    backend_scores: dict[str, float] = Field(default_factory=dict)
    backend_ranks: dict[str, int] = Field(default_factory=dict)


class RetrievalHit(RetrievedDocument):
    score_breakdown: RetrievalScoreBreakdown = Field(default_factory=RetrievalScoreBreakdown)
    provenance: list[ProvenanceEntry] = Field(default_factory=list)

    def as_document(self) -> RetrievedDocument:
        return RetrievedDocument(
            doc_id=self.doc_id,
            chunk_id=self.chunk_id,
            title=self.title,
            text=self.text,
            score=self.score,
            source=self.source,
            tags=list(self.tags),
            corpus_id=self.corpus_id,
        )


class RetrievalQuery(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    text: str = Field(min_length=1)
    corpus: str | None = None
    filters: dict[str, FilterValue] | None = None
    k: int = Field(default=5, ge=1, le=50)
    request_id: str | None = None
    session_id: str | None = None
    tenant_id: str | None = None
    enable_cache: bool = True
    allow_degraded: bool = True
    debug: bool = False


class BackendStatus(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    backend_name: str = Field(min_length=1)
    available: bool = True
    degraded: bool = False
    index_version: str | None = None
    detail: str | None = None


class BackendSearchResult(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    backend_name: str = Field(min_length=1)
    hits: list[RetrievalHit] = Field(default_factory=list)
    latency_ms: int = Field(default=0, ge=0)
    available: bool = True
    degraded: bool = False
    error: str | None = None
    rejected_artifacts: list[str] = Field(default_factory=list)


class RetrievalService(Protocol):
    def retrieve(
        self,
        query: str,
        *,
        corpus: str | None = None,
        filters: dict[str, FilterValue] | None = None,
        k: int = 5,
    ) -> list[RetrievedDocument]:
        ...


class QueryRetriever(Protocol):
    def search(self, query: RetrievalQuery) -> list[RetrievedDocument]:
        ...


class RetrievalBackend(Protocol):
    backend_name: str

    def status(self) -> BackendStatus:
        ...

    def search_with_diagnostics(self, query: RetrievalQuery) -> BackendSearchResult:
        ...
