from __future__ import annotations

import logging

from fastapi import FastAPI

from jester.api.deps import ServiceContainer, build_container
from jester.api.frontend import register_frontend
from jester.api.middleware.auth import auth_middleware
from jester.api.middleware.errors import error_normalization_middleware
from jester.api.middleware.logging import logging_middleware
from jester.api.middleware.tracing import tracing_middleware
from jester.api.routers import (
    health_router,
    live_dm_router,
    prep_router,
    retrieval_router,
    sessions_router,
    teaching_router,
)
from jester.config.settings import AppSettings, load_settings


def create_app(
    *,
    settings: AppSettings | None = None,
    container: ServiceContainer | None = None,
) -> FastAPI:
    resolved_settings = settings or load_settings()
    logging.basicConfig(level=getattr(logging, resolved_settings.logging.level), force=False)
    app = FastAPI(title='Jester API', version='1.0.0')
    app.state.container = container or build_container(settings=resolved_settings)

    app.middleware('http')(error_normalization_middleware)
    app.middleware('http')(tracing_middleware)
    app.middleware('http')(auth_middleware)
    app.middleware('http')(logging_middleware)

    app.include_router(health_router)
    app.include_router(sessions_router)
    app.include_router(prep_router)
    app.include_router(teaching_router)
    app.include_router(live_dm_router)
    app.include_router(retrieval_router)
    register_frontend(app)
    return app


app = create_app()
