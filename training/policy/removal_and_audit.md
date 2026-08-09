# Removal And Audit Policy

## Removal readiness

Every manifest must include a `removal_contact`. This can be:

- a rights holder contact
- a partner operations contact
- `not_applicable_public_domain`
- `not_applicable_owned_internal`

The goal is not to imply every source can be removed. The goal is to record the correct operational path if a review or takedown is needed.

## Removal workflow

1. Mark the manifest under review.
2. Move associated raw artifacts to quarantine or denylist them in the export pipeline.
3. Identify dependent datasets by `source_id` and `content_hash`.
4. Rebuild affected dataset manifests and adapters without the removed source.
5. Preserve the audit trail showing when and why the source was removed.

## Audit requirements

Auditability requires that the repository or controlled storage can answer:

- which source produced a given training record
- who reviewed that source
- what rights basis justified use
- which datasets consumed the source
- whether the source hash changed after approval

## Hash consistency

`content_hash` is the primary duplicate and drift detector.

- identical hashes with different `source_id` values are treated as duplicates until reviewed
- the same `source_id` with different hashes requires a new review or versioned manifest update
- records and dataset manifests should carry forward hashes so audit tools can traverse the lineage

## Retention

Blocked and removed manifests should remain in the audit history unless legal counsel requires deletion. Silent deletion destroys traceability and makes later compliance review harder.
