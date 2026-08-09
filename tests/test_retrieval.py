from __future__ import annotations

import json
from pathlib import Path

from jester.retrieval.service import BM25RetrievalService


def _write_corpus(path: Path) -> None:
    rows: list[dict[str, object]] = [
        {
            "doc_id": "world-1",
            "chunk_id": "world-1:1",
            "title": "Goblin_Cave.md",
            "text": "Goblins guard a narrow cave entrance with crude traps.",
            "source": "world/goblin_cave.md",
            "corpus": "world",
            "tags": ["ambush", "cave"],
        },
        {
            "doc_id": "world-2",
            "chunk_id": "world-2:1",
            "title": "Harbor_Market.md",
            "text": "Merchants crowd the harbor market with fish, rope, and lantern oil.",
            "source": "world/harbor_market.md",
            "corpus": "world",
            "tags": ["city", "trade"],
        },
        {
            "doc_id": "rule-1",
            "chunk_id": "rule-1:1",
            "title": "Armor_Class.txt",
            "text": "Armor class represents how difficult a creature is to hit.",
            "source": "rules/armor_class.txt",
            "corpus": "rules",
            "tags": ["combat", "defense"],
        },
        {
            "doc_id": "artifact-1",
            "chunk_id": "artifact-1:1",
            "title": "manifest.jsonl",
            "text": "generated manifest output for watchdog pipeline",
            "source": "generated/manifest.jsonl",
            "corpus": "world",
            "tags": ["artifact"],
        },
    ]
    lines = [json.dumps(row) for row in rows]
    path.write_text("\n".join(lines), encoding="utf-8")



def test_retrieval_is_deterministic_and_excludes_artifacts(tmp_path: Path) -> None:
    corpus_path = tmp_path / "corpus.jsonl"
    _write_corpus(corpus_path)
    service = BM25RetrievalService.from_jsonl(corpus_path)

    first = service.retrieve("goblin cave ambush", corpus="world", k=3)
    second = service.retrieve("goblin cave ambush", corpus="world", k=3)

    assert [document.doc_id for document in first] == [document.doc_id for document in second]
    assert first[0].doc_id == "world-1"
    assert all(document.doc_id != "artifact-1" for document in first)



def test_retrieval_supports_filters(tmp_path: Path) -> None:
    corpus_path = tmp_path / "corpus.jsonl"
    _write_corpus(corpus_path)
    service = BM25RetrievalService.from_jsonl(corpus_path)

    results = service.retrieve(
        "armor class hit",
        corpus="rules",
        filters={"tags": ["defense"]},
        k=2,
    )

    assert [document.doc_id for document in results] == ["rule-1"]
