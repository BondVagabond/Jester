from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import cast

from fastapi import Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from jester.ai import ModelRegistry, ModelRole, ModelSelection, ModelSelectionPolicy, build_model_registry
from jester.app.application import (
    LiveDmApplicationService,
    PrepApplicationService,
    TeachingApplicationService,
)
from jester.app.live_dm import LiveDmService
from jester.app.prep import PrepService
from jester.app.sessions import SessionService
from jester.app.teaching import TeachingService
from jester.config.settings import AppSettings, SettingsError, load_settings
from jester.corpus import CorpusStartupError, build_corpus_registry
from jester.observability import emit_json_log
from jester.retrieval import CorpusRegistry, InMemoryRetrievalCache, RetrievalOrchestrator
from jester.state import SessionRepository, SQLiteSessionRepository


class RateLimitDecision(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    allowed: bool
    reason: str | None = None


class RateLimiter:
    def check(self, *, key: str, route: str) -> RateLimitDecision:
        _ = key
        _ = route
        return RateLimitDecision(allowed=True)


@dataclass(frozen=True, slots=True)
class ServiceContainer:
    settings: AppSettings
    corpus_registry: CorpusRegistry
    session_repository: SessionRepository
    session_service: SessionService
    retrieval_orchestrator: RetrievalOrchestrator
    model_registry: ModelRegistry
    model_selection: ModelSelectionPolicy
    prep_service: PrepService
    teaching_service: TeachingService
    live_dm_service: LiveDmService
    prep_application_service: PrepApplicationService
    teaching_application_service: TeachingApplicationService
    live_dm_application_service: LiveDmApplicationService
    rate_limiter: RateLimiter


def build_container(
    *,
    settings: AppSettings | None = None,
    corpus_registry: CorpusRegistry | None = None,
    session_repository: SessionRepository | None = None,
    rate_limiter: RateLimiter | None = None,
) -> ServiceContainer:
    resolved_settings = settings or load_settings()

    try:
        registry = corpus_registry or build_corpus_registry(
            resolved_settings.corpora,
            ingestion_policy=resolved_settings.ingestion,
        )
        model_registry = build_model_registry(resolved_settings)
    except (CorpusStartupError, SettingsError, ValueError) as exc:
        raise RuntimeError(f'Jester startup failed: {exc}') from exc

    if not registry.list_allowed():
        raise RuntimeError('Jester startup failed: no allowed corpora were registered.')

    retrieval_orchestrator = RetrievalOrchestrator(
        registry,
        cache=InMemoryRetrievalCache(),
        cache_ttl_seconds=resolved_settings.retrieval.cache_ttl_seconds,
        bm25_weight=resolved_settings.retrieval.bm25_weight,
        vector_weight=resolved_settings.retrieval.vector_weight,
    )
    model_selection = ModelSelectionPolicy(model_registry)
    repository = session_repository or SQLiteSessionRepository(resolved_settings.state_store.sqlite_path)

    prep_service = PrepService(
        retriever=retrieval_orchestrator,
        policy=resolved_settings.output_validation,
        model_registry=model_registry,
        selection_policy=model_selection,
    )
    teaching_service = TeachingService(
        retriever=retrieval_orchestrator,
        policy=resolved_settings.output_validation,
        model_registry=model_registry,
        selection_policy=model_selection,
    )
    live_dm_service = LiveDmService(
        retriever=retrieval_orchestrator,
        policy=resolved_settings.output_validation,
        model_registry=model_registry,
        selection_policy=model_selection,
    )
    session_service = SessionService(repository)

    container = ServiceContainer(
        settings=resolved_settings,
        corpus_registry=registry,
        session_repository=repository,
        session_service=session_service,
        retrieval_orchestrator=retrieval_orchestrator,
        model_registry=model_registry,
        model_selection=model_selection,
        prep_service=prep_service,
        teaching_service=teaching_service,
        live_dm_service=live_dm_service,
        prep_application_service=PrepApplicationService(prep_service, repository),
        teaching_application_service=TeachingApplicationService(teaching_service),
        live_dm_application_service=LiveDmApplicationService(live_dm_service, repository),
        rate_limiter=rate_limiter or RateLimiter(),
    )
    emit_json_log(
        logging.getLogger('jester.api'),
        logging.INFO,
        'container_built',
        environment=resolved_settings.environment,
        state_db=str(resolved_settings.state_store.sqlite_path),
        prompt_root=str(resolved_settings.prompt_registry.prompt_root),
        registered_corpora=[
            {
                'corpus_id': registered.definition.corpus_id,
                'version': registered.definition.version,
                'documents': len(registered.documents),
                'profile': registered.definition.index_metadata.get('profile'),
            }
            for registered in registry.list_all()
        ],
        model_bindings={
            role.value: {
                'provider': binding.provider_name,
                'model': binding.model_name,
                'enabled': binding.enabled,
            }
            for role, binding in resolved_settings.ai.bindings().items()
        },
    )
    return container


def get_container(request: Request) -> ServiceContainer:
    container = getattr(request.app.state, 'container', None)
    if container is None:
        raise RuntimeError('API container is not configured.')
    return cast(ServiceContainer, container)


def get_tenant_id(
    request: Request,
    x_tenant_id: str | None = Header(default=None, alias='X-Tenant-ID'),
) -> str:
    container = get_container(request)
    tenant_id = (x_tenant_id or container.settings.api.default_tenant_id).strip()
    if not tenant_id:
        raise HTTPException(status_code=400, detail='Tenant ID must not be blank.')
    return tenant_id


def require_rate_limit(request: Request) -> None:
    container = get_container(request)
    client_host = request.client.host if request.client is not None else 'unknown'
    decision = container.rate_limiter.check(key=client_host, route=request.url.path)
    if not decision.allowed:
        raise HTTPException(status_code=429, detail=decision.reason or 'Rate limit exceeded.')


def request_context(request: Request) -> tuple[str, str]:
    request_id = str(getattr(request.state, 'request_id', 'missing-request-id'))
    trace_id = str(getattr(request.state, 'trace_id', request_id))
    return request_id, trace_id


def model_status_map(container: ServiceContainer) -> dict[str, ModelSelection]:
    return {
        role.value: container.model_selection.resolve(role)
        for role in (ModelRole.PRIMARY_GENERATION, ModelRole.REASONING, ModelRole.SMALL_FAST)
    }
