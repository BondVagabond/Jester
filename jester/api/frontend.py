from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_FRONTEND_ROOT = Path(__file__).resolve().parents[2] / 'frontend'
_FRONTEND_CANDIDATES = (
    _FRONTEND_ROOT / 'dist-current',
    _FRONTEND_ROOT / 'dist',
)
_BACKEND_PREFIXES = ('api', 'health', 'docs', 'redoc', 'openapi.json')


def register_frontend(app: FastAPI) -> None:
    frontend_dir = next((path for path in _FRONTEND_CANDIDATES if (path / 'index.html').exists()), None)
    if frontend_dir is None:
        return

    index_path = frontend_dir / 'index.html'
    assets_path = frontend_dir / 'assets'
    if assets_path.exists():
        app.mount('/assets', StaticFiles(directory=assets_path), name='frontend-assets')

    async def serve_root() -> FileResponse:
        return FileResponse(index_path)

    async def serve_spa(full_path: str) -> FileResponse:
        normalized = full_path.strip('/')
        if any(normalized == prefix or normalized.startswith(f'{prefix}/') for prefix in _BACKEND_PREFIXES):
            raise HTTPException(status_code=404, detail='Not found.')

        if normalized:
            candidate = (frontend_dir / normalized).resolve()
            if frontend_dir in candidate.parents and candidate.is_file():
                return FileResponse(candidate)
        return FileResponse(index_path)

    app.add_api_route('/', serve_root, methods=['GET'], include_in_schema=False)
    app.add_api_route('/{full_path:path}', serve_spa, methods=['GET'], include_in_schema=False)
