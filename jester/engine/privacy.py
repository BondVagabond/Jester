from __future__ import annotations

from typing import Any

from jester.app.visibility import build_visible_session_view
from jester.domain import Session


def get_visible_state(session: Session, viewer_id: str | None) -> dict[str, Any]:
    payload = build_visible_session_view(session, viewer_id).model_dump(mode='json')
    memory_records = payload['memory']
    payload['memory'] = {'records': memory_records}
    return payload