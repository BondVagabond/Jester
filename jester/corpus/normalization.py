# ruff: noqa: I001
from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator

from jester.corpus.models import CorpusDocument
from jester.processing.sanitizer import SanitizationError, sanitize_content, sanitize_title

_TEXT_KEYS = ('text', 'content', 'page_content', 'desc', 'body', 'rule_text', 'excerpt')
_TITLE_KEYS = ('title', 'name', 'heading', 'topic', 'label')
_DOC_ID_KEYS = ('doc_id', 'id', 'slug', 'source_id')
_CHUNK_ID_KEYS = ('chunk_id', 'chunk_idx', 'chunk', 'segment_id')
_SOURCE_KEYS = ('source', 'source_file', 'path', 'uri')
_TAG_KEYS = ('tags', 'keywords', 'topic_tags')


class CorpusProfile(StrEnum):
    ARBITER = 'arbiter'
    NARRATOR = 'narrator'


class CorpusNormalizationError(ValueError):
    """Raised when corpus content cannot be normalized safely."""


class NormalizedCorpusChunk(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    corpus_name: str = Field(min_length=1)
    doc_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source: str = Field(min_length=1)
    metadata: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)

    @field_validator('corpus_name', 'doc_id', 'chunk_id', 'title', 'text', 'source', mode='before')
    @classmethod
    def strip_required_text(cls, value: object) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError('Normalized corpus fields must not be blank.')
        return text

    @field_validator('metadata', mode='before')
    @classmethod
    def normalize_metadata(cls, value: object) -> dict[str, str]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise TypeError('Corpus metadata must be a mapping of string values.')
        normalized: dict[str, str] = {}
        for key, item in value.items():
            key_text = str(key).strip()
            item_text = str(item).strip()
            if key_text and item_text:
                normalized[key_text] = item_text
        return normalized

    @field_validator('tags', mode='before')
    @classmethod
    def normalize_tags(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            raw_values = value.split(',')
        elif isinstance(value, list):
            raw_values = [str(item) for item in value]
        else:
            raise TypeError('Corpus tags must be a list of strings, comma-delimited string, or null.')

        tags: list[str] = []
        seen: set[str] = set()
        for raw in raw_values:
            cleaned = str(raw).strip().lower()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            tags.append(cleaned)
        return tags

    def to_document(self) -> CorpusDocument:
        return CorpusDocument(
            doc_id=self.doc_id,
            chunk_id=self.chunk_id,
            title=self.title,
            text=self.text,
            source=self.source,
            corpus=self.corpus_name,
            tags=self.tags,
        )


def normalize_corpus_payload(
    payload: Mapping[str, object],
    *,
    corpus_name: str,
    profile: CorpusProfile,
    default_source_prefix: str,
) -> NormalizedCorpusChunk:
    if not isinstance(payload, Mapping):
        raise CorpusNormalizationError('Corpus rows must be JSON objects.')

    raw_text = _first_text(payload, _TEXT_KEYS)
    if raw_text is None:
        raise CorpusNormalizationError('Corpus rows must provide text-like content.')

    raw_title = _first_text(payload, _TITLE_KEYS)
    raw_doc_id = _first_text(payload, _DOC_ID_KEYS)
    source = _first_text(payload, _SOURCE_KEYS)

    doc_id = _normalize_identifier(raw_doc_id or raw_title or source or _stable_identifier(payload))
    chunk_id = _normalize_identifier(_first_text(payload, _CHUNK_ID_KEYS) or f'{doc_id}:1')
    resolved_source = _normalize_source_path(source or f'{default_source_prefix}/{doc_id}.md')

    try:
        title = sanitize_title(raw_title or doc_id)
    except SanitizationError as exc:
        raise CorpusNormalizationError(f'Corpus title could not be sanitized for {doc_id!r}.') from exc

    text = sanitize_content(raw_text)
    if not text:
        raise CorpusNormalizationError(f'Corpus text became empty after sanitization for {doc_id!r}.')

    metadata = _build_metadata(payload, profile)
    metadata.setdefault('profile', profile.value)
    metadata.setdefault('corpus_name', corpus_name)
    tags = _build_tags(payload, profile)

    return NormalizedCorpusChunk(
        corpus_name=corpus_name,
        doc_id=doc_id,
        chunk_id=chunk_id,
        title=title,
        text=text,
        source=resolved_source,
        metadata=metadata,
        tags=tags,
    )


def _first_text(payload: Mapping[str, object], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _build_metadata(payload: Mapping[str, object], profile: CorpusProfile) -> dict[str, str]:
    metadata: dict[str, str] = {}
    raw_metadata = payload.get('metadata')
    if isinstance(raw_metadata, Mapping):
        for key, value in raw_metadata.items():
            key_text = str(key).strip()
            value_text = str(value).strip()
            if key_text and value_text:
                metadata[key_text] = value_text

    for key in ('chapter', 'concept', 'region', 'scene', 'faction', 'tone', 'stakes', 'feature'):
        value = payload.get(key)
        if value is None:
            continue
        value_text = str(value).strip()
        if value_text:
            metadata.setdefault(key, value_text)

    metadata.setdefault('profile', profile.value)
    return metadata


def _build_tags(payload: Mapping[str, object], profile: CorpusProfile) -> list[str]:
    raw_values: list[str] = []
    for key in _TAG_KEYS:
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            raw_values.extend(str(item) for item in value)
        else:
            raw_values.extend(str(value).split(','))

    raw_values.append(profile.value)
    tags: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        cleaned = re.sub(r'\s+', '_', str(raw).strip().lower())
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        tags.append(cleaned)
    return tags


def _normalize_identifier(value: str) -> str:
    cleaned = re.sub(r'[^a-zA-Z0-9:_-]+', '-', value.strip())
    cleaned = re.sub(r'-{2,}', '-', cleaned).strip('-')
    if not cleaned:
        raise CorpusNormalizationError('Could not derive a stable identifier for a corpus row.')
    return cleaned.lower()


def _stable_identifier(payload: Mapping[str, object]) -> str:
    digest = hashlib.sha256(
        repr(sorted((str(key), str(value)) for key, value in payload.items())).encode('utf-8')
    ).hexdigest()
    return digest[:16]




def _normalize_source_path(value: str) -> str:
    text = value.strip().replace('\\', '/')
    if not text:
        raise CorpusNormalizationError('Corpus source paths must not be blank.')
    return text
