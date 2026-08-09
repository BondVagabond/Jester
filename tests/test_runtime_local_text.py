from types import SimpleNamespace
from typing import cast

from pipeline.runtime.models import ApprovedSource, JobRun
from pipeline.runtime.pipeline import process_text_document


def _fake_source() -> SimpleNamespace:
    manifest = {
        "source_id": "local_test_source",
        "source_type": "text",
        "license": "owned",
        "license_url": "",
        "rights_basis": "owned-by-jester",
        "allowed_for_training": True,
        "allowed_for_rag": True,
        "eligibility_class": "training_and_retrieval",
        "attribution_required": False,
        "attribution_text": "",
        "share_alike_required": False,
        "removal_required": False,
        "owner": "Jester",
        "version": "test-v1",
        "provenance_status": "complete",
    }
    return SimpleNamespace(source_id=manifest["source_id"], manifest=manifest)


def _fake_run() -> SimpleNamespace:
    return SimpleNamespace(run_id="run_test", job_id="crawl.test", started_at="2026-04-16T00:00:00Z")


def test_process_text_document_emits_valid_chunks() -> None:
    text = """
# Action Economy

This note explains how movement, attacks, and reaction timing create pressure in a fifth-edition encounter. The goal is not to copy a rulebook paragraph. The goal is to preserve a readable pattern for training and retrieval.

## Pressure

When the front line commits to a choke point, the back line gains time. When an enemy breaks that line, the whole round changes shape. A useful corpus sample should keep that cause and effect visible.

## Counterplay

Archers shift angles, defenders hold space, and casters decide whether to spend resources on control or damage. Those are distinct choices, and the pipeline should sectionize them into clean records before chunking them.
""".strip()

    result = process_text_document(
        source=cast(ApprovedSource, _fake_source()),
        run=cast(JobRun, _fake_run()),
        source_ref="F:/Jester/tests/fixtures/action-economy.md",
        text=text,
        title="Action Economy",
        original_filename="action-economy.md",
        acquisition_method="local_path",
        max_chunk_chars=240,
    )

    assert not result["validation_errors"]
    assert result["chunked"]
    assert all(record["char_count"] <= 240 for record in result["chunked"])
