from __future__ import annotations

from fastapi import APIRouter, Depends

from jester.ai import ModelRole
from jester.api.deps import ServiceContainer, get_container
from jester.api.schemas import DependencyHealthResponse, HealthStatusResponse

_CONTAINER = Depends(get_container)

router = APIRouter(tags=['health'])


@router.get('/health', response_model=HealthStatusResponse)
def health() -> HealthStatusResponse:
    return HealthStatusResponse(status='ok')


@router.get('/health/dependencies', response_model=DependencyHealthResponse)
def dependency_health(
    container: ServiceContainer = _CONTAINER,
) -> DependencyHealthResponse:
    db_ok = container.session_repository.check_health()
    retrieval_backends = container.retrieval_orchestrator.backend_statuses()
    retrieval_ok = bool(container.corpus_registry.list_allowed()) and any(
        status.available for status in retrieval_backends
    )
    model_statuses = {
        role.value: container.model_selection.resolve(role)
        for role in (ModelRole.PRIMARY_GENERATION, ModelRole.REASONING, ModelRole.SMALL_FAST)
    }
    models_ok = all(status.available or not status.enabled for status in model_statuses.values())
    status = 'ok' if db_ok and retrieval_ok and models_ok else 'degraded'
    return DependencyHealthResponse(
        status=status,
        database='ok' if db_ok else 'degraded',
        retrieval='ok' if retrieval_ok else 'degraded',
        models=model_statuses,
        retrieval_backends=retrieval_backends,
    )
