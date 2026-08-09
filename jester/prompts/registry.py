from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class PromptNotFoundError(FileNotFoundError):
    """Raised when a prompt asset cannot be resolved."""


class PromptValidationError(ValueError):
    """Raised when a prompt asset fails schema validation."""


class PromptSpec(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    purpose: str = Field(min_length=1, validation_alias=AliasChoices('purpose', 'description'))
    input_contract: dict[str, Any]
    output_contract: dict[str, Any]
    constraints: list[str]
    template: str = Field(min_length=1)

    @property
    def description(self) -> str:
        return self.purpose

    @field_validator('name', 'version', 'purpose', 'template', mode='before')
    @classmethod
    def strip_required_text(cls, value: object) -> str:
        text = str(value).strip()
        if not text:
            raise ValueError('Prompt fields must not be blank.')
        return text

    @field_validator('input_contract', 'output_contract', mode='before')
    @classmethod
    def require_non_empty_mapping(cls, value: object) -> dict[str, Any]:
        if not isinstance(value, dict) or not value:
            raise TypeError('Prompt contracts must be non-empty mappings.')
        return value

    @field_validator('constraints', mode='before')
    @classmethod
    def normalize_constraints(cls, value: object) -> list[str]:
        if not isinstance(value, list) or not value:
            raise TypeError('constraints must be a non-empty list[str].')
        constraints = [str(item).strip() for item in value if str(item).strip()]
        if not constraints:
            raise ValueError('constraints must not be empty.')
        return constraints


def _default_prompt_root() -> Path:
    return Path(__file__).resolve().parents[2] / 'prompts'


def load_prompt(name: str, version: str, *, prompt_root: Path | None = None) -> PromptSpec:
    root = (prompt_root or _default_prompt_root()).expanduser().resolve()
    if not root.exists():
        raise PromptNotFoundError(f'Prompt root does not exist: {root}')

    asset_name = f'{name}_{version}.yaml'
    matches = sorted(root.glob(f'*/{asset_name}'))
    if not matches:
        raise PromptNotFoundError(
            f'Prompt {name!r} with version {version!r} was not found under {root}.'
        )
    if len(matches) > 1:
        raise PromptValidationError(
            f'Prompt {name!r} with version {version!r} resolved to multiple assets: {matches}'
        )

    with matches[0].open('r', encoding='utf-8') as handle:
        payload = yaml.safe_load(handle)

    if not isinstance(payload, dict):
        raise PromptValidationError(f'Prompt asset must be a YAML object: {matches[0]}')

    spec = PromptSpec.model_validate(payload)
    if spec.name != name or spec.version != version:
        raise PromptValidationError(
            f'Prompt asset identity mismatch in {matches[0]}: expected '
            f'{name!r}/{version!r}, received {spec.name!r}/{spec.version!r}.'
        )
    return spec