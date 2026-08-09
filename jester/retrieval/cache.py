from __future__ import annotations

import json
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol

from jester.retrieval.contracts import RetrievalQuery
from jester.retrieval.diagnostics import RetrievalResponse


class RetrievalCache(Protocol):
    def get(self, query: RetrievalQuery) -> RetrievalResponse | None:
        ...

    def set(self, query: RetrievalQuery, response: RetrievalResponse, ttl_seconds: int) -> None:
        ...

    def invalidate(self, *, corpus_id: str | None = None) -> None:
        ...


@dataclass(slots=True)
class _CacheEntry:
    response: RetrievalResponse
    expires_at: float
    corpus_id: str | None


class InMemoryRetrievalCache:
    def __init__(self) -> None:
        self._entries: dict[str, _CacheEntry] = {}

    def get(self, query: RetrievalQuery) -> RetrievalResponse | None:
        key = _cache_key(query)
        entry = self._entries.get(key)
        if entry is None:
            return None
        if time.monotonic() >= entry.expires_at:
            self._entries.pop(key, None)
            return None
        return entry.response

    def set(self, query: RetrievalQuery, response: RetrievalResponse, ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        key = _cache_key(query)
        self._entries[key] = _CacheEntry(
            response=response,
            expires_at=time.monotonic() + ttl_seconds,
            corpus_id=query.corpus,
        )

    def invalidate(self, *, corpus_id: str | None = None) -> None:
        if corpus_id is None:
            self._entries.clear()
            return
        stale = [key for key, entry in self._entries.items() if entry.corpus_id == corpus_id]
        for key in stale:
            self._entries.pop(key, None)


def _cache_key(query: RetrievalQuery) -> str:
    payload = query.model_dump(mode='json')
    stable = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return sha256(stable.encode('utf-8')).hexdigest()
