from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from pydantic import Field

from jester.app.contracts.common import AppDto, GeneratedTextBlock
from jester.processing.sanitizer import sanitize_content
from jester.prompts import load_prompt
from jester.validation import (
    OutputValidationPolicy,
    ValidationIssue,
    ValidationRule,
    validate_output,
)


class PromptGenerationError(RuntimeError):
    """Raised when a prompt-backed response cannot produce safe output."""


class PromptRenderRequest(AppDto):
    prompt_name: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    rendered_prompt: str = Field(min_length=1)
    template_values: dict[str, str] = Field(default_factory=dict)
    fallback_text: str | None = None


class PromptModelClient(Protocol):
    def generate(self, request: PromptRenderRequest) -> str:
        ...


def generate_prompt_block(
    *,
    prompt_name: str,
    prompt_version: str,
    template_values: Mapping[str, str],
    fallback_text: str,
    model_client: PromptModelClient | None = None,
    policy: OutputValidationPolicy | None = None,
    rules: Sequence[ValidationRule] | None = None,
) -> GeneratedTextBlock:
    try:
        prompt_spec = load_prompt(prompt_name, prompt_version)
        rendered_prompt = prompt_spec.template.format(**dict(template_values))
    except KeyError as exc:
        raise PromptGenerationError(
            f'Missing prompt template value {exc!s} for {prompt_name}/{prompt_version}.'
        ) from exc

    request = PromptRenderRequest(
        prompt_name=prompt_name,
        prompt_version=prompt_version,
        rendered_prompt=rendered_prompt,
        template_values={key: str(value) for key, value in template_values.items()},
        fallback_text=fallback_text,
    )

    if model_client is None:
        return _validated_fallback_block(
            request=request,
            fallback_text=fallback_text,
            policy=policy,
            rules=rules,
            issues=[],
        )

    raw_candidate = model_client.generate(request).strip()
    raw_validation = validate_output(raw_candidate, policy, rules=rules)
    if not raw_validation.is_valid:
        return _validated_fallback_block(
            request=request,
            fallback_text=fallback_text,
            policy=policy,
            rules=rules,
            issues=raw_validation.issues,
        )

    candidate_text = sanitize_content(raw_candidate)
    candidate_validation = validate_output(candidate_text, policy, rules=rules)
    if candidate_validation.is_valid:
        return GeneratedTextBlock(
            text=candidate_text,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            used_fallback=False,
            validation_passed=True,
            issues=candidate_validation.issues,
        )

    return _validated_fallback_block(
        request=request,
        fallback_text=fallback_text,
        policy=policy,
        rules=rules,
        issues=candidate_validation.issues,
    )


def _validated_fallback_block(
    *,
    request: PromptRenderRequest,
    fallback_text: str,
    policy: OutputValidationPolicy | None,
    rules: Sequence[ValidationRule] | None,
    issues: list[ValidationIssue],
) -> GeneratedTextBlock:
    fallback = sanitize_content(fallback_text.strip())
    fallback_validation = validate_output(fallback, policy, rules=rules)
    if not fallback_validation.is_valid:
        raise PromptGenerationError(
            f'Fallback text failed validation for {request.prompt_name}/{request.prompt_version}.'
        )

    return GeneratedTextBlock(
        text=fallback,
        prompt_name=request.prompt_name,
        prompt_version=request.prompt_version,
        used_fallback=True,
        validation_passed=True,
        issues=list(issues),
    )
