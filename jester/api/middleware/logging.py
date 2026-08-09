from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from jester.observability import emit_json_log

RequestHandler = Callable[[Request], Awaitable[Response]]


async def logging_middleware(request: Request, call_next: RequestHandler) -> Response:
    start = time.perf_counter()
    response = await call_next(request)
    latency_ms = int((time.perf_counter() - start) * 1000)
    emit_json_log(
        logging.getLogger('jester.api'),
        logging.INFO,
        'http_request_completed',
        request_id=str(getattr(request.state, 'request_id', 'unknown')),
        trace_id=str(getattr(request.state, 'trace_id', 'unknown')),
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        latency_ms=latency_ms,
        tenant_id=request.headers.get('X-Tenant-ID'),
    )
    response.headers['X-Latency-MS'] = str(latency_ms)
    return response
