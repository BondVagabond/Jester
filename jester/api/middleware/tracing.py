from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

RequestHandler = Callable[[Request], Awaitable[Response]]


async def tracing_middleware(request: Request, call_next: RequestHandler) -> Response:
    request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
    trace_id = request.headers.get('X-Trace-ID') or request_id
    request.state.request_id = request_id
    request.state.trace_id = trace_id
    response = await call_next(request)
    response.headers['X-Request-ID'] = request_id
    response.headers['X-Trace-ID'] = trace_id
    return response
