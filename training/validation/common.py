from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

HASH_PATTERN = re.compile(r"^sha256:[a-f0-9]{64}$")


def _require_text(value: object, *, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} must not be blank.")
    return text


class PolicyCategory(StrEnum):
    TRAIN_AND_RAG = "train_and_rag"
    RAG_ONLY = "rag_only"
    REFERENCE_ONLY = "reference_only"
    BLOCKED = "blocked"


class SourceType(StrEnum):
    PUBLIC_DOMAIN_TEXT = "public_domain_text"
    INTERNAL_DOCUMENT = "internal_document"
    LICENSED_TEXT = "licensed_text"
    PARTNER_MATERIAL = "partner_material"
    RULEBOOK_EXCERPT = "rulebook_excerpt"
    WEBSITE = "website"
    WIKI = "wiki"
    FORUM = "forum"
    PDF = "pdf"
    MANUAL_DROP = "manual_drop"


class SourceOwner(StrEnum):
    JESTER = "jester"
    PUBLIC = "public"
    PARTNER = "partner"
    THIRD_PARTY = "third_party"
    UNKNOWN = "unknown"


class RightsBasis(StrEnum):
    OWNED_ORIGINAL = "owned_original"
    OWNED_OR_PUBLIC_DOMAIN = "owned_or_public_domain"
    LICENSED_FOR_TRAINING = "licensed_for_training"
    LICENSED_FOR_RAG_ONLY = "licensed_for_rag_only"
    INTERNAL_REFERENCE_ONLY = "internal_reference_only"
    UNKNOWN = "unknown"
    PROHIBITED = "prohibited"


class ReviewStatus(StrEnum):
    APPROVED = "approved"
    APPROVED_RAG_ONLY = "approved_rag_only"
    REFERENCE_ONLY = "reference_only"
    QUARANTINED = "quarantined"
    REMOVED = "removed"


class TaskFamily(StrEnum):
    NARRATION = "narration"
    TEACHING = "teaching"
    REASONING = "reasoning"
    ROUTING = "routing"


class SourceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: str = Field(min_length=3)
    title: str = Field(min_length=1)
    origin: str = Field(min_length=1)
    source_type: SourceType
    owner: SourceOwner
    license: str = Field(min_length=1)
    rights_basis: RightsBasis
    policy_category: PolicyCategory
    allowed_for_training: bool
    allowed_for_rag: bool
    collected_at: date
    reviewed_by: str = Field(min_length=1)
    review_status: ReviewStatus
    removal_contact: str = Field(min_length=1)
    removal_required: bool = False
    content_hash: str = Field(min_length=8)
    notes: str = Field(min_length=1)

    @field_validator(
        "source_id",
        "title",
        "origin",
        "license",
        "reviewed_by",
        "removal_contact",
        "notes",
        mode="before",
    )
    @classmethod
    def strip_required_text(cls, value: object, info: object) -> str:
        field_name = getattr(info, "field_name", "field")
        return _require_text(value, field_name=field_name)

    @field_validator("content_hash", mode="before")
    @classmethod
    def validate_hash(cls, value: object) -> str:
        text = _require_text(value, field_name="content_hash")
        if not HASH_PATTERN.fullmatch(text):
            raise ValueError("content_hash must be formatted as sha256:<64 lowercase hex chars>.")
        return text

    @model_validator(mode="after")
    def enforce_policy_rules(self) -> SourceManifest:
        if self.owner is SourceOwner.UNKNOWN and self.policy_category is not PolicyCategory.BLOCKED:
            raise ValueError("owner=unknown is only allowed for blocked sources.")
        if self.license == "unknown" and self.policy_category is not PolicyCategory.BLOCKED:
            raise ValueError("license=unknown is only allowed for blocked sources.")

        if self.policy_category is PolicyCategory.TRAIN_AND_RAG:
            if not self.allowed_for_training or not self.allowed_for_rag:
                raise ValueError("train_and_rag sources must allow both training and RAG.")
            if self.rights_basis not in {
                RightsBasis.OWNED_ORIGINAL,
                RightsBasis.OWNED_OR_PUBLIC_DOMAIN,
                RightsBasis.LICENSED_FOR_TRAINING,
            }:
                raise ValueError("train_and_rag sources require owned/public-domain/training rights.")
            if self.review_status is not ReviewStatus.APPROVED:
                raise ValueError("train_and_rag sources must have review_status=approved.")

        if self.policy_category is PolicyCategory.RAG_ONLY:
            if self.allowed_for_training or not self.allowed_for_rag:
                raise ValueError("rag_only sources must disable training and allow RAG.")
            if self.rights_basis is not RightsBasis.LICENSED_FOR_RAG_ONLY:
                raise ValueError("rag_only sources require rights_basis=licensed_for_rag_only.")
            if self.review_status is not ReviewStatus.APPROVED_RAG_ONLY:
                raise ValueError("rag_only sources must have review_status=approved_rag_only.")

        if self.policy_category is PolicyCategory.REFERENCE_ONLY:
            if self.allowed_for_training or self.allowed_for_rag:
                raise ValueError("reference_only sources must disable training and RAG.")
            if self.rights_basis is not RightsBasis.INTERNAL_REFERENCE_ONLY:
                raise ValueError("reference_only sources require rights_basis=internal_reference_only.")
            if self.review_status is not ReviewStatus.REFERENCE_ONLY:
                raise ValueError("reference_only sources must have review_status=reference_only.")

        if self.policy_category is PolicyCategory.BLOCKED:
            if self.allowed_for_training or self.allowed_for_rag:
                raise ValueError("blocked sources must disable training and RAG.")
            if self.rights_basis not in {RightsBasis.UNKNOWN, RightsBasis.PROHIBITED}:
                raise ValueError("blocked sources require rights_basis=unknown or prohibited.")
            if self.review_status not in {ReviewStatus.QUARANTINED, ReviewStatus.REMOVED}:
                raise ValueError("blocked sources must be quarantined or removed.")

        return self


class TrainingMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tone: str | None = None
    domain: str = Field(min_length=1)
    language: str = Field(min_length=2)
    citation_required: bool = False

    @field_validator("tone", "domain", "language", mode="before")
    @classmethod
    def strip_optional_text(cls, value: object, info: object) -> str | None:
        if value is None:
            return None
        field_name = getattr(info, "field_name", "field")
        return _require_text(value, field_name=field_name)


class TrainingRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    record_id: str = Field(min_length=3)
    source_id: str = Field(min_length=3)
    task_family: TaskFamily
    text: str = Field(min_length=1)
    metadata: TrainingMetadata
    allowed_for_training: bool
    allowed_for_rag: bool
    content_hash: str = Field(min_length=8)

    @field_validator("record_id", "source_id", "text", mode="before")
    @classmethod
    def strip_required_text(cls, value: object, info: object) -> str:
        field_name = getattr(info, "field_name", "field")
        return _require_text(value, field_name=field_name)

    @field_validator("content_hash", mode="before")
    @classmethod
    def validate_hash(cls, value: object) -> str:
        text = _require_text(value, field_name="content_hash")
        if not HASH_PATTERN.fullmatch(text):
            raise ValueError("content_hash must be formatted as sha256:<64 lowercase hex chars>.")
        return text


def load_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc.msg}") from exc


def iter_record_payloads(path: Path) -> Iterable[tuple[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                yield f"{path}:{line_number}", json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc.msg}") from exc
        return

    payload = load_json_file(path)
    if isinstance(payload, list):
        for index, item in enumerate(payload, start=1):
            yield f"{path}[{index}]", item
        return
    yield f"{path}", payload


def normalize_validation_error(prefix: str, exc: ValidationError) -> str:
    messages: list[str] = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error["loc"])
        messages.append(f"{prefix}: {location}: {error['msg']}")
    return "\n".join(messages)
