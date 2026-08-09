"""Typed corpus loading and startup normalization contracts."""

from jester.corpus.jsonl import JsonlIntegrityError, load_corpus_jsonl
from jester.corpus.models import CorpusDocument
from jester.corpus.normalization import (
    CorpusNormalizationError,
    CorpusProfile,
    NormalizedCorpusChunk,
    normalize_corpus_payload,
)
from jester.corpus.startup import CorpusStartupError, build_corpus_registry, load_registered_corpus

__all__ = [
    'CorpusDocument',
    'CorpusNormalizationError',
    'CorpusProfile',
    'CorpusStartupError',
    'JsonlIntegrityError',
    'NormalizedCorpusChunk',
    'build_corpus_registry',
    'load_corpus_jsonl',
    'load_registered_corpus',
    'normalize_corpus_payload',
]
