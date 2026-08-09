from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse

from jester.api.deps import get_container
from jester.api.schemas import ErrorPayload, ErrorResponse

RequestHandler = Callable[[Request], Awaitable[JSONResponse]]


async def auth_middleware(request: Request, call_next: RequestHandler) -> JSONResponse:
    container = get_container(request)
    if not container.settings.api.require_api_key:
        return await call_next(request)

    provided = request.headers.get('X-API-Key', '').strip()
    if provided and provided in container.settings.api.api_keys:
        return await call_next(request)

    error = ErrorResponse(
        error=ErrorPayload(
            code='unauthorized',
            message='A valid API key is required.',
            request_id=str(getattr(request.state, 'request_id', 'unknown')),
            trace_id=str(getattr(request.state, 'trace_id', 'unknown')),
        )
    )
    return JSONResponse(status_code=401, content=error.model_dump(mode='json'))
