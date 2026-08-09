from __future__ import annotations

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


class CorpusDocument(BaseModel):
    """Sanitized corpus record ready for deterministic retrieval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    doc_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    source: str = Field(min_length=1)
    corpus: str | None = None
    tags: list[str] = Field(default_factory=list)

    @field_validator("doc_id", "chunk_id", "title", "text", "source", mode="before")
    @classmethod
    def strip_required_text(cls, value: object) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError("Field must not be blank.")
        return text

    @field_validator("corpus", mode="before")
    @classmethod
    def strip_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            tags = [segment.strip() for segment in value.split(",") if segment.strip()]
            return tags
        if isinstance(value, list):
            tags = [str(item).strip() for item in value if str(item).strip()]
            return tags
        raise TypeError("tags must be a list[str], comma-delimited string, or null.")


class RawCorpusDocument(BaseModel):
    """Flexible document input model for legacy JSONL sources."""

    model_config = ConfigDict(extra="allow", frozen=True)

    doc_id: str = Field(validation_alias=AliasChoices("doc_id", "id"))
    chunk_id: str = Field(validation_alias=AliasChoices("chunk_id", "chunk_idx", "id"))
    title: str | None = None
    text: str = Field(validation_alias=AliasChoices("text", "page_content", "content", "desc"))
    source: str
    corpus: str | None = Field(default=None, validation_alias=AliasChoices("corpus", "type"))
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def derive_defaults(cls, value: object) -> object:
        if not isinstance(value, dict):
            raise TypeError("Corpus rows must be JSON objects.")

        payload = dict(value)
        if payload.get("title") in (None, ""):
            payload["title"] = (
                payload.get("name")
                or payload.get("full_name")
                or payload.get("doc_id")
                or payload.get("id")
            )
        if payload.get("chunk_id") in (None, "") and payload.get("chunk_idx") is None:
            payload["chunk_id"] = payload.get("id") or payload.get("doc_id")
        return payload

    @field_validator("doc_id", "chunk_id", "text", "source", mode="before")
    @classmethod
    def strip_required_text(cls, value: object) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError("Field must not be blank.")
        return text

    @field_validator("title", "corpus", mode="before")
    @classmethod
    def strip_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [segment.strip() for segment in value.split(",") if segment.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        raise TypeError("tags must be a list[str], comma-delimited string, or null.")
