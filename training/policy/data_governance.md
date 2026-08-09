# Data Governance Policy

## Scope

This policy applies to all crawling, scraping, extraction, cleaning, sectionization,
chunking, indexing, retrieval corpora, and training corpora in this repository.

## Source Registration

- Every source must have a source manifest before collection starts.
- Every source manifest must declare:
  - source owner
  - source type
  - license
  - rights basis
  - eligibility class
  - collection policy
  - removal handling
- Missing manifests are a hard failure, not a backlog item.

## Eligibility Classes

Each source and each downstream record must be classified as exactly one of:

- `training_and_retrieval`
- `retrieval_only`
- `neither`

Derived rules:

- `training_and_retrieval` means `allowed_for_training=true` and `allowed_for_rag=true`
- `retrieval_only` means `allowed_for_training=false` and `allowed_for_rag=true`
- `neither` means both flags are false

No other class is allowed.

## Default Decisions

`DND`-adjacent material
- Official copyrighted rulebooks, adventures, and similar commercial texts are excluded from training by default.
- Official open releases with a clear training-safe license may be marked `training_and_retrieval`.
- Fan wikis, blogs, transcripts, and play reports are `retrieval_only` unless explicit written training rights exist.

`User uploads` and `campaign logs`
- Never training-eligible by default.
- Default class is `retrieval_only` for workspace-scoped use if the content is not sensitive.
- They may become `training_and_retrieval` only with explicit opt-in, documented ownership or permission, and redaction review.

`Missing provenance`
- Default class is `neither`.
- The record must be quarantined immediately.

## Provenance Requirements

The following fields are mandatory on every stage record:

- `source_id`
- `source_type`
- `license`
- `rights_basis`
- `allowed_for_training`
- `allowed_for_rag`
- `removal_required`
- `collection_date`
- `owner`
- `content_hash`
- `version`

Useful existing fields that must survive where applicable:

- `source`
- `page_from`
- `page_to`
- `heading` or `title`
- `doc_type`
- `extractor_name`
- `quality_posterior`
- `quality_flags`
- `rejection_flags`
- `fallback_flags`
- `chunk_id`
- `parent_id`

## Quarantine Rules

The quarantine path is a first-class output, not a trash can.

A source or record must be quarantined if any of the following are true:

- missing or unknown `license`
- missing or unknown `rights_basis`
- disputed ownership
- removal request received
- provenance incomplete
- sensitive data or redaction failure
- crawler policy violation

Quarantined content:

- must not enter retrieval indexes
- must not enter training exports
- must retain lineage so the cause can be audited

## Removal Requests

Removal requests must create three actions:

1. immediate quarantine of the source and all derived records
2. a tombstone entry recording the request, date, and scope
3. downstream rebuild of affected datasets and indexes

`removal_required=true` blocks both retrieval and training.

## Versioning And Reprocessing

- `version` must identify both the source snapshot and the pipeline version that produced a record.
- `content_hash` must be recalculated at each stage.
- Reprocessing must create a new dataset manifest and preserve parent lineage.
- Incremental reruns are valid only if aggregate outputs are idempotent with respect to unchanged inputs.

## Refusal Behavior

The system must refuse:

- collection from unregistered sources
- training export from records with incomplete provenance
- training export from records whose rights status is unknown, false, or quarantined
- retrieval export from quarantined or removal-required records
