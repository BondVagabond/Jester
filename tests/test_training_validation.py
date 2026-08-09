from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from training.validation.validate_record_eligibility import validate_record_eligibility
from training.validation.validate_training_source import validate_source_manifests

EXAMPLE_MANIFESTS = Path("training/manifests/examples")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, payloads: list[dict[str, Any]]) -> None:
    lines = [json.dumps(payload) for payload in payloads]
    path.write_text("\n".join(lines), encoding="utf-8")


def _source_manifest_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "source_id": "owned-source-001",
        "title": "Owned Internal Notes",
        "origin": "internal repo",
        "source_type": "internal_document",
        "owner": "jester",
        "license": "jester_internal",
        "rights_basis": "owned_original",
        "policy_category": "train_and_rag",
        "allowed_for_training": True,
        "allowed_for_rag": True,
        "collected_at": "2026-04-05",
        "reviewed_by": "platform-team",
        "review_status": "approved",
        "removal_contact": "not_applicable_owned_internal",
        "removal_required": False,
        "content_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "notes": "Owned and approved for narration and teaching."
    }
    payload.update(overrides)
    return payload


def _training_record_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "record_id": "rec-0001",
        "source_id": "myth-grimm-001",
        "task_family": "narration",
        "text": "A ruined keep stood above the marsh.",
        "metadata": {
            "tone": "dark_fantasy",
            "domain": "worldbuilding",
            "language": "en"
        },
        "allowed_for_training": True,
        "allowed_for_rag": True,
        "content_hash": "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    }
    payload.update(overrides)
    return payload


def test_example_source_manifests_validate() -> None:
    manifests = validate_source_manifests([EXAMPLE_MANIFESTS])
    assert len(manifests) == 8


def test_source_manifest_missing_license_fails(tmp_path: Path) -> None:
    manifest_path = tmp_path / "missing-license.json"
    payload = _source_manifest_payload()
    payload.pop("license")
    _write_json(manifest_path, payload)

    with pytest.raises(ValueError, match=r"license"):
        validate_source_manifests([manifest_path])


def test_source_manifest_unknown_owner_requires_blocked(tmp_path: Path) -> None:
    manifest_path = tmp_path / "unknown-owner.json"
    _write_json(manifest_path, _source_manifest_payload(owner="unknown"))

    with pytest.raises(ValueError, match=r"owner=unknown"):
        validate_source_manifests([manifest_path])


def test_blocked_source_cannot_be_marked_trainable(tmp_path: Path) -> None:
    manifest_path = tmp_path / "blocked-trainable.json"
    _write_json(
        manifest_path,
        _source_manifest_payload(
            source_id="blocked-source-001",
            owner="unknown",
            license="unknown",
            rights_basis="unknown",
            policy_category="blocked",
            allowed_for_training=True,
            allowed_for_rag=False,
            review_status="quarantined",
        ),
    )

    with pytest.raises(ValueError, match=r"blocked sources must disable training and RAG"):
        validate_source_manifests([manifest_path])


def test_record_eligibility_accepts_traceable_training_record(tmp_path: Path) -> None:
    records_path = tmp_path / "records.jsonl"
    _write_jsonl(records_path, [_training_record_payload()])

    records = validate_record_eligibility([EXAMPLE_MANIFESTS], [records_path])
    assert len(records) == 1


def test_record_missing_source_id_is_rejected(tmp_path: Path) -> None:
    records_path = tmp_path / "records.jsonl"
    payload = _training_record_payload()
    payload.pop("source_id")
    _write_jsonl(records_path, [payload])

    with pytest.raises(ValueError, match=r"source_id"):
        validate_record_eligibility([EXAMPLE_MANIFESTS], [records_path])


def test_record_invalid_task_family_is_rejected(tmp_path: Path) -> None:
    records_path = tmp_path / "records.jsonl"
    _write_jsonl(records_path, [_training_record_payload(task_family="combat")])

    with pytest.raises(ValueError, match=r"task_family"):
        validate_record_eligibility([EXAMPLE_MANIFESTS], [records_path])


def test_rag_only_source_cannot_back_training_record(tmp_path: Path) -> None:
    records_path = tmp_path / "records.jsonl"
    _write_jsonl(
        records_path,
        [
            _training_record_payload(
                source_id="rules-srd-001",
                allowed_for_training=True,
                allowed_for_rag=True,
            )
        ],
    )

    with pytest.raises(ValueError, match=r"not approved for training"):
        validate_record_eligibility([EXAMPLE_MANIFESTS], [records_path])


def test_training_record_schema_limits_task_families() -> None:
    schema = json.loads(Path("training/schemas/training_record.schema.json").read_text(encoding="utf-8"))

    assert schema["properties"]["task_family"]["enum"] == [
        "narration",
        "teaching",
        "reasoning",
        "routing",
    ]


def test_model_contract_schema_requires_answer_role_and_reasoning_context_support() -> None:
    schema = json.loads(Path("training/manifests/model_contract.schema.json").read_text(encoding="utf-8"))

    assert schema["properties"]["supported_task_families"]["items"]["enum"] == [
        "narration",
        "teaching",
        "reasoning",
        "routing",
    ]

    response_required_rules = schema["allOf"][0]["properties"]["response_envelope"]["properties"]["required_fields"][
        "allOf"
    ]
    required_fields = {rule["contains"]["const"] for rule in response_required_rules}
    assert {"answer", "role", "task_family"} <= required_fields

    reasoning_support = schema["allOf"][1]["then"]["properties"]["response_envelope"]["anyOf"]
    supported_fields = {
        branch["properties"][field_name]["contains"]["const"]
        for branch in reasoning_support
        for field_name in branch["properties"]
    }
    assert "used_context_ids" in supported_fields
