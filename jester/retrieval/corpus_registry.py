from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from jester.corpus.jsonl import load_corpus_jsonl
from jester.corpus.models import CorpusDocument
from jester.ingestion.filtering import IngestionPolicy


class CorpusRegistryError(ValueError):
    """Raised when corpus registration is invalid."""


class CorpusDefinition(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    corpus_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    index_metadata: dict[str, Any] = Field(default_factory=dict)
    allowed: bool = True

    @field_validator('corpus_id', 'version', 'source_type', mode='before')
    @classmethod
    def strip_required_text(cls, value: object) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError('Corpus definition fields must not be blank.')
        return text


class RegisteredCorpus(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    definition: CorpusDefinition
    documents: tuple[CorpusDocument, ...]


class CorpusRegistry:
    def __init__(self) -> None:
        self._corpora: dict[str, RegisteredCorpus] = {}

    def register(
        self,
        definition: CorpusDefinition,
        documents: list[CorpusDocument],
    ) -> None:
        if definition.corpus_id in self._corpora:
            existing = self._corpora[definition.corpus_id]
            if existing.definition.version != definition.version:
                raise CorpusRegistryError(
                    f'Corpus {definition.corpus_id!r} already registered with version '
                    f'{existing.definition.version!r}.'
                )
            raise CorpusRegistryError(f'Corpus {definition.corpus_id!r} is already registered.')
        for document in documents:
            if document.corpus not in (None, definition.corpus_id):
                raise CorpusRegistryError(
                    f'Document {document.doc_id!r} has corpus {document.corpus!r} but was '
                    f'registered under {definition.corpus_id!r}.'
                )
        normalized = [
            document.model_copy(update={'corpus': definition.corpus_id})
            for document in documents
        ]
        self._corpora[definition.corpus_id] = RegisteredCorpus(
            definition=definition,
            documents=tuple(normalized),
        )

    def register_jsonl(
        self,
        *,
        definition: CorpusDefinition,
        path: Path,
        policy: IngestionPolicy | None = None,
    ) -> None:
        self.register(definition, load_corpus_jsonl(path, policy=policy))

    def get(self, corpus_id: str) -> RegisteredCorpus:
        try:
            return self._corpora[corpus_id]
        except KeyError as exc:
            raise CorpusRegistryError(f'Corpus {corpus_id!r} is not registered.') from exc

    def list_allowed(self) -> list[RegisteredCorpus]:
        return [registered for registered in self._corpora.values() if registered.definition.allowed]

    def list_all(self) -> list[RegisteredCorpus]:
        return list(self._corpora.values())
