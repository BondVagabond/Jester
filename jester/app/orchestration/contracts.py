from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator

from jester.ai.contracts import ModelRole, ModelTraceRecord
from jester.app.contracts.common import AppDto, GeneratedTextBlock
from jester.app.contracts.live_dm import LiveDmTurnResponse
from jester.app.contracts.prep import PrepResponse
from jester.app.contracts.teaching import LessonResponse
from jester.retrieval.diagnostics import RetrievalDiagnostics


class WorkspaceName(StrEnum):
    PREP = 'prep'
    TEACHING = 'teaching'
    LIVE_DM = 'live_dm'


class WorkspaceTask(StrEnum):
    PREP_RETRIEVAL = 'prep.retrieval'
    PREP_PLAN = 'prep.plan'
    PREP_PROSE = 'prep.prose'
    PREP_CRITIQUE = 'prep.critique'
    PREP_REFINE = 'prep.refine'
    TEACHING_RETRIEVAL = 'teaching.retrieval'
    TEACHING_PLAN = 'teaching.plan'
    TEACHING_ANSWER = 'teaching.answer'
    TEACHING_PRACTICE = 'teaching.practice'
    LIVE_DM_CLASSIFICATION = 'live_dm.classification'
    LIVE_DM_INFO = 'live_dm.info'
    LIVE_DM_RULES_EXPLANATION = 'live_dm.rules_explanation'
    LIVE_DM_NARRATION = 'live_dm.narration'
    LIVE_DM_MECHANICS = 'live_dm.mechanics'


class OrchestrationLane(StrEnum):
    NARRATOR = 'narrator'
    ARBITER = 'arbiter'
    CLASSIFIER = 'classifier'
    DETERMINISTIC = 'deterministic'


class ServiceWarningCode(StrEnum):
    RETRIEVAL_UNAVAILABLE = 'retrieval_unavailable'
    RETRIEVAL_DEGRADED = 'retrieval_degraded'
    AUTHORED_FALLBACK_USED = 'authored_fallback_used'
    GENERATION_FALLBACK_USED = 'generation_fallback_used'
    MODEL_UNAVAILABLE = 'model_unavailable'
    INVALID_ACTION = 'invalid_action'
    UNSUPPORTED_CAPABILITY = 'unsupported_capability'
    NARRATION_DISABLED = 'narration_disabled'
    SESSION_CONFLICT = 'session_conflict'
    STALE_REVISION = 'stale_revision'
    DETERMINISTIC_ONLY = 'deterministic_only'


class ServiceWarning(AppDto):
    code: ServiceWarningCode
    message: str = Field(min_length=1)
    degraded: bool = False

    @field_validator('message', mode='before')
    @classmethod
    def strip_message(cls, value: object) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError('Service warning messages must not be blank.')
        return text


class RouteSelection(AppDto):
    workspace: WorkspaceName
    task: WorkspaceTask
    lane: OrchestrationLane
    model_role: ModelRole | None = None
    prompt_name: str | None = None
    prompt_version: str | None = None
    corpus_id: str | None = None
    retrieval_top_k: int = Field(default=3, ge=1, le=10)
    deterministic: bool = False

    @field_validator('prompt_name', 'prompt_version', 'corpus_id', mode='before')
    @classmethod
    def strip_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class RetrievedContextItem(AppDto):
    doc_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source: str = Field(min_length=1)
    score: float
    excerpt: str = Field(min_length=1)
    corpus_id: str | None = None

    @field_validator('doc_id', 'chunk_id', 'title', 'source', 'excerpt', 'corpus_id', mode='before')
    @classmethod
    def strip_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            raise ValueError('Retrieved context text fields must not be blank.')
        return text


class RetrievedContext(AppDto):
    route: RouteSelection
    query_text: str = Field(min_length=1)
    hits: list[RetrievedContextItem] = Field(default_factory=list)
    warnings: list[ServiceWarning] = Field(default_factory=list)
    diagnostics: RetrievalDiagnostics | None = None

    @field_validator('query_text', mode='before')
    @classmethod
    def strip_query_text(cls, value: object) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError('RetrievedContext query_text must not be blank.')
        return text


class GenerationRequest(AppDto):
    route: RouteSelection
    template_values: dict[str, str] = Field(default_factory=dict)
    fallback_text: str = Field(min_length=1)

    @field_validator('fallback_text', mode='before')
    @classmethod
    def strip_fallback_text(cls, value: object) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError('Generation fallback text must not be blank.')
        return text


class GenerationResponse(AppDto):
    route: RouteSelection
    block: GeneratedTextBlock
    warnings: list[ServiceWarning] = Field(default_factory=list)
    traces: list[ModelTraceRecord] = Field(default_factory=list)


class WorkspaceDebugInfo(AppDto):
    workspace: WorkspaceName
    primary_task: WorkspaceTask
    routes: list[RouteSelection] = Field(default_factory=list)
    retrieved: list[RetrievedContext] = Field(default_factory=list)
    warnings: list[ServiceWarning] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PrepServiceResult(AppDto):
    response: PrepResponse
    warnings: list[ServiceWarning] = Field(default_factory=list)
    debug: WorkspaceDebugInfo


class TeachingServiceResult(AppDto):
    response: LessonResponse
    warnings: list[ServiceWarning] = Field(default_factory=list)
    debug: WorkspaceDebugInfo


class LiveDmServiceResult(AppDto):
    response: LiveDmTurnResponse
    warnings: list[ServiceWarning] = Field(default_factory=list)
    debug: WorkspaceDebugInfo
    state_mutated: bool = False


def warning_codes(warnings: list[ServiceWarning]) -> list[str]:
    return [warning.code.value for warning in warnings]


def is_degraded(warnings: list[ServiceWarning]) -> bool:
    return any(warning.degraded for warning in warnings)
