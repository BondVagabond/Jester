from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from jester.processing.sanitizer import looks_like_filename


class OutputValidationPolicy(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    allow_urls: bool = False
    enable_anachronism_check: bool = True


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: str = Field(min_length=1)

    @field_validator('severity')
    @classmethod
    def validate_severity(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {'error', 'warning'}:
            raise ValueError("severity must be either 'error' or 'warning'.")
        return normalized


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)

    is_valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


class ValidationRule(Protocol):
    def evaluate(self, text: str, policy: OutputValidationPolicy) -> list[ValidationIssue]:
        ...


class EmptyOutputRule:
    def evaluate(self, text: str, policy: OutputValidationPolicy) -> list[ValidationIssue]:
        del policy
        if text.strip():
            return []
        return [
            ValidationIssue(
                code='empty_output',
                message='Output must not be blank.',
                severity='error',
            )
        ]


class RegexRule:
    def __init__(
        self,
        *,
        code: str,
        message: str,
        pattern: re.Pattern[str],
        severity: str = 'error',
    ) -> None:
        self._code = code
        self._message = message
        self._pattern = pattern
        self._severity = severity

    def evaluate(self, text: str, policy: OutputValidationPolicy) -> list[ValidationIssue]:
        del policy
        if not self._pattern.search(text):
            return []
        return [
            ValidationIssue(
                code=self._code,
                message=self._message,
                severity=self._severity,
            )
        ]


class FilenameLeakageRule:
    _pattern = re.compile(
        r'(?i)\b[a-z0-9][a-z0-9_. -]*\.'
        r'(?:csv|faiss|html?|jsonl?|log|md|markdown|pdf|rst|txt|ya?ml)\b'
    )

    def evaluate(self, text: str, policy: OutputValidationPolicy) -> list[ValidationIssue]:
        del policy
        for match in self._pattern.finditer(text):
            if looks_like_filename(match.group(0)):
                return [
                    ValidationIssue(
                        code='filename_leakage',
                        message='Detected filename leakage in user-facing output.',
                        severity='error',
                    )
                ]
        return []


class UrlLeakageRule:
    _pattern = re.compile(r'(?i)\b(?:https?://|www\.)\S+\b')

    def evaluate(self, text: str, policy: OutputValidationPolicy) -> list[ValidationIssue]:
        if policy.allow_urls or not self._pattern.search(text):
            return []
        return [
            ValidationIssue(
                code='url_leakage',
                message='Detected URL leakage in user-facing output.',
                severity='error',
            )
        ]


class AnachronismRule:
    _pattern = re.compile(
        r'(?i)\b(?:email|google|internet|laptop|podcast|smartphone|streaming|usb|wi-fi|wifi)\b'
    )

    def evaluate(self, text: str, policy: OutputValidationPolicy) -> list[ValidationIssue]:
        if not policy.enable_anachronism_check or not self._pattern.search(text):
            return []
        return [
            ValidationIssue(
                code='anachronism',
                message='Detected modern or anachronistic language in output.',
                severity='error',
            )
        ]


PATH_PATTERN = re.compile(r'(?i)\b[a-z]:[\\/][^\s]+|(?<!:)(?:/[^/\s]+){2,}')
TOOLING_PATTERN = re.compile(
    r'(?i)\b(?:manifest|pipeline|watchdog)\b|\breports?\.jsonl\b|\bmanifest\.jsonl\b'
)

DEFAULT_RULES: tuple[ValidationRule, ...] = (
    EmptyOutputRule(),
    RegexRule(
        code='path_leakage',
        message='Detected filesystem path leakage in user-facing output.',
        pattern=PATH_PATTERN,
    ),
    FilenameLeakageRule(),
    UrlLeakageRule(),
    RegexRule(
        code='tooling_leakage',
        message='Detected system or tooling terms in user-facing output.',
        pattern=TOOLING_PATTERN,
    ),
    AnachronismRule(),
)



def validate_output(
    text: str,
    policy: OutputValidationPolicy | None = None,
    *,
    rules: Sequence[ValidationRule] | None = None,
) -> ValidationResult:
    active_policy = policy or OutputValidationPolicy()
    active_rules = tuple(rules or DEFAULT_RULES)

    issues: list[ValidationIssue] = []
    seen_codes: set[str] = set()
    for rule in active_rules:
        for issue in rule.evaluate(text, active_policy):
            if issue.code in seen_codes:
                continue
            seen_codes.add(issue.code)
            issues.append(issue)

    is_valid = not any(issue.severity == 'error' for issue in issues)
    return ValidationResult(is_valid=is_valid, issues=issues)
