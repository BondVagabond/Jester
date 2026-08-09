from __future__ import annotations

import json
from pathlib import Path

import pytest

from jester.corpus.jsonl import JsonlIntegrityError, load_corpus_jsonl


def test_invalid_jsonl_fails_loudly(tmp_path: Path) -> None:
    corpus_path = tmp_path / "corpus.jsonl"
    corpus_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "doc_id": "world-1",
                        "chunk_id": "world-1:1",
                        "title": "Goblin_Cave.md",
                        "text": "Goblins guard a narrow cave entrance.",
                        "source": "world/goblin_cave.md",
                    }
                ),
                "{broken-json}",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(JsonlIntegrityError, match=r"Invalid JSON at .*:2"):
        load_corpus_jsonl(corpus_path)


def test_missing_required_document_fields_fail_loudly(tmp_path: Path) -> None:
    corpus_path = tmp_path / "corpus.jsonl"
    corpus_path.write_text(
        json.dumps(
            {
                "doc_id": "world-1",
                "chunk_id": "world-1:1",
                "title": "Goblin_Cave.md",
                "text": "Goblins guard a narrow cave entrance.",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(JsonlIntegrityError, match=r"Invalid corpus document"):
        load_corpus_jsonl(corpus_path)
