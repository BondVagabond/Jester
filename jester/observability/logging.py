from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any


def emit_json_log(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    payload = {
        'timestamp': datetime.now(UTC).isoformat(),
        'event': event,
        **fields,
    }
    logger.log(level, json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str))
