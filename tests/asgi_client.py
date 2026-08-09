from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI
from starlette.types import Message, Receive, Scope, Send


@dataclass(frozen=True, slots=True)
class AsgiResponse:
    status_code: int
    json_body: dict[str, Any]
    headers: dict[str, str]


def request_json(
    app: FastAPI,
    method: str,
    path: str,
    *,
    json_body: Any | None = None,
    headers: Mapping[str, str] | None = None,
) -> AsgiResponse:
    return asyncio.run(
        _request_json(
            app,
            method,
            path,
            json_body=json_body,
            headers=headers,
        )
    )


async def _request_json(
    app: FastAPI,
    method: str,
    path: str,
    *,
    json_body: Any | None = None,
    headers: Mapping[str, str] | None = None,
) -> AsgiResponse:
    split = urlsplit(path)
    raw_body = b'' if json_body is None else json.dumps(json_body).encode('utf-8')
    header_items = {
        'host': 'testserver',
        **{key.lower(): value for key, value in dict(headers or {}).items()},
    }
    if json_body is not None:
        header_items.setdefault('content-type', 'application/json')
        header_items.setdefault('content-length', str(len(raw_body)))

    scope: Scope = {
        'type': 'http',
        'asgi': {'version': '3.0'},
        'http_version': '1.1',
        'method': method.upper(),
        'scheme': 'http',
        'path': split.path,
        'raw_path': split.path.encode('utf-8'),
        'query_string': split.query.encode('utf-8'),
        'headers': [
            (key.encode('latin-1'), value.encode('latin-1')) for key, value in header_items.items()
        ],
        'client': ('127.0.0.1', 50000),
        'server': ('testserver', 80),
    }

    sent_messages: list[Message] = []
    request_sent = False

    async def receive() -> Message:
        nonlocal request_sent
        if request_sent:
            return {'type': 'http.disconnect'}
        request_sent = True
        return {'type': 'http.request', 'body': raw_body, 'more_body': False}

    async def send(message: Message) -> None:
        sent_messages.append(message)

    await app(scope, cast_receive(receive), cast_send(send))

    start = next(message for message in sent_messages if message['type'] == 'http.response.start')
    body = b''.join(
        bytes(message.get('body', b''))
        for message in sent_messages
        if message['type'] == 'http.response.body'
    )
    response_headers = {
        key.decode('latin-1'): value.decode('latin-1')
        for key, value in start.get('headers', [])
    }
    payload = {} if not body else json.loads(body.decode('utf-8'))
    return AsgiResponse(
        status_code=int(start['status']),
        json_body=payload,
        headers=response_headers,
    )


def cast_receive(receive: Receive) -> Receive:
    return receive


def cast_send(send: Send) -> Send:
    return send
