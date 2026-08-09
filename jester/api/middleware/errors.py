from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from jester.api.schemas import ErrorPayload, ErrorResponse
from jester.app.live_dm import LiveDmServiceError
from jester.app.prep import PrepServiceError
from jester.app.teaching import TeachingServiceError
from jester.observability import emit_json_log
from jester.retrieval import RetrievalError, RetrievalUnavailableError
from jester.state import SessionConflictError, StateStoreError

RequestHandler = Callable[[Request], Awaitable[Response]]


async def error_normalization_middleware(request: Request, call_next: RequestHandler) -> Response:
    try:
        return await call_next(request)
    except RequestValidationError as exc:
        return _error_response(request, 422, 'validation_error', 'Request validation failed.', str(exc))
    except SessionConflictError as exc:
        return _error_response(request, 409, 'session_conflict', str(exc), str(exc))
    except TeachingServiceError as exc:
        return _error_response(request, 400, 'teaching_request_invalid', str(exc), str(exc))
    except LiveDmServiceError as exc:
        return _error_response(request, 400, 'live_dm_request_invalid', str(exc), str(exc))
    except PrepServiceError as exc:
        return _error_response(request, 503, 'prep_service_unavailable', str(exc), str(exc))
    except RetrievalUnavailableError as exc:
        return _error_response(request, 503, 'retrieval_unavailable', str(exc), str(exc))
    except RetrievalError as exc:
        return _error_response(request, 502, 'retrieval_error', str(exc), str(exc))
    except StateStoreError as exc:
        return _error_response(request, 500, 'state_store_error', str(exc), str(exc))
    except HTTPException as exc:
        return _error_response(
            request,
            exc.status_code,
            'http_error',
            str(exc.detail),
            str(exc.detail),
        )
    except Exception as exc:  # noqa: BLE001
        return _error_response(request, 500, 'internal_error', 'Internal server error.', str(exc))


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    detail: str,
) -> JSONResponse:
    request_id = str(getattr(request.state, 'request_id', 'unknown'))
    trace_id = str(getattr(request.state, 'trace_id', 'unknown'))
    emit_json_log(
        logging.getLogger('jester.api'),
        logging.ERROR if status_code >= 500 else logging.WARNING,
        'http_error',
        request_id=request_id,
        trace_id=trace_id,
        method=request.method,
        path=request.url.path,
        status_code=status_code,
        code=code,
        detail=detail,
    )
    payload = ErrorResponse(
        error=ErrorPayload(
            code=code,
            message=message,
            request_id=request_id,
            trace_id=trace_id,
            detail=detail,
        )
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode='json'))
