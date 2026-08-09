from __future__ import annotations

import re
from collections import Counter

from jester.corpus.models import CorpusDocument
from jester.processing.sanitizer import sanitize_content
from jester.retrieval.contracts import FilterValue

TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")


def tokenize(text: str) -> tuple[str, ...]:
    return tuple(TOKEN_RE.findall(sanitize_content(text).lower()))


def build_term_frequencies(document: CorpusDocument) -> Counter[str]:
    combined_text = sanitize_content(f'{document.title}\n{document.text}')
    return Counter(tokenize(combined_text))


def matches_filters(
    document: CorpusDocument,
    filters: dict[str, FilterValue] | None,
) -> bool:
    if filters is None:
        return True
    for key, expected in filters.items():
        actual = getattr(document, key, None)
        if isinstance(actual, list):
            actual_values = {value.lower() for value in actual}
            if isinstance(expected, list):
                expected_values = {value.lower() for value in expected}
                if actual_values.isdisjoint(expected_values):
                    return False
            else:
                if expected.lower() not in actual_values:
                    return False
            continue

        if isinstance(expected, list):
            if actual not in expected:
                return False
            continue

        if actual != expected:
            return False
    return True
