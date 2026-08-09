# Redaction Policy

## Purpose

The redaction layer prevents private, sensitive, or accidental high-risk data from
crossing into retrieval indexes or training exports.

## Content Classes

Automatically redact or quarantine when found:

- email addresses
- phone numbers
- street addresses
- access tokens and API keys
- payment data
- government identifiers
- player real names when logs are intended to stay pseudonymous
- private links that reveal account or storage access

## Actions

`Redact`
- replace the sensitive span with a typed marker such as `[REDACTED_EMAIL]`
- preserve enough surrounding text for retrieval and audit

`Quarantine`
- block the record from downstream use
- require manual review

## Mandatory Quarantine Cases

- raw user uploads with unknown ownership
- campaign logs containing personal data
- records that still contain secrets after automated redaction
- records under removal request

## Measurement

The cleaning stage must report:

- redaction count by class
- whether redaction changed the text
- whether the record was quarantined after redaction

If a cleaning pass is a no-op, that must be reported explicitly.

## Training-Specific Rule

Redacted content is not automatically training-safe. Training eligibility still depends on
license, rights basis, explicit consent where required, and provenance completeness.
