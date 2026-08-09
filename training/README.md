# Training And Corpus Governance Backbone

This directory is the canonical home for Jester's legally safe, provenance-complete,
and validation-first corpus pipeline.

The immediate goal is not to preserve legacy behavior. The goal is to create a hard
compliance and traceability boundary in front of every future retrieval index and
training export.

## Non-Negotiable Rules

- No source manifest, no collection.
- No provenance, no training.
- Unknown rights status is not a warning. It is a quarantine event.
- Retrieval-only and training-eligible data must remain separable at every stage.
- Validation failures must stop export, not downgrade silently.

## Training Lifecycle

1. Register a source manifest before crawling, scraping, importing, or accepting uploads.
2. Collect raw artifacts with rights, host policy, and acquisition metadata attached at ingest time.
3. Extract text with extractor name, version, page spans, fallback flags, and page-level errors.
4. Clean text while recording measurable deltas:
   - URLs removed
   - HTML removed
   - boilerplate removed
   - token delta
   - repeated-pass delta
   - no-op flag
5. Sectionize with document-level QA:
   - no multi-page document may collapse to <= 1 section unless explicitly exempted
   - null headings must be rejected or explicitly allowed
6. Chunk with size ceilings, parent linkage, and heading inheritance.
7. Validate stage output against the canonical record contract.
8. Build a dataset manifest for retrieval or training export.
9. Export retrieval corpora and indexes only from validated chunk records.
10. Export training corpora only from validated chunk records whose provenance is complete and whose rights status is explicitly training-eligible.
11. On removal request, quarantine affected records immediately, mark them for purge, and rebuild downstream datasets from manifests.

## Directory Model

This sprint adds:

- `Training/policy/`: governance, licensing, eligibility, and redaction rules
- `Training/manifests/`: JSON schemas for source and dataset manifests
- `Training/validation/`: validators for manifests and corpus records`r`n- `Training/sources/`: approved source manifests, candidate review records, and source quarantine

Planned next:

- `Training/sources/`: checked-in manifest instances
- `Training/datasets/`: dataset manifests and export metadata
- `Training/quarantine/`: isolated records blocked from retrieval and training

## Canonical Record Contract

Every record written after collection must carry the same governance core:

```json
{
  "record_id": "chunk:src_srd_5_2_1:000123",
  "stage": "chunked",
  "source_id": "src_srd_5_2_1",
  "source_type": "pdf",
  "source": "F:/Jester/out/raw/srd_cc_v5_2_1.pdf",
  "license": "cc-by-4.0",
  "rights_basis": "open-license",
  "allowed_for_training": true,
  "allowed_for_rag": true,
  "eligibility_class": "training_and_retrieval",
  "removal_required": false,
  "collection_date": "2026-04-04T00:00:00Z",
  "owner": "Wizards of the Coast / CC release",
  "content_hash": "sha256:...",
  "version": "src_srd_5_2_1@2026-04-04",
  "pipeline_version": "corpus-v2",
  "provenance_status": "complete"
}
```

## Stage Requirements

`raw`
- Required blocks: `acquisition`, raw artifact location, HTTP/file metadata, host policy id.
- Must capture robots result, user-agent, final URL/path, and collection timestamp.

`extracted`
- Must preserve raw parent linkage and extractor metadata.
- Required fields: `extractor_name`, `extractor_version`, `page_from`, `page_to`, `page_errors`, `fallback_flags`.

`cleaned`
- Must preserve extracted parent linkage.
- Required fields: `cleaning_metrics`, `rejection_flags`, `quality_posterior`, `quality_flags`.
- `cleaning_metrics` must distinguish a real transformation from a no-op pass.

`sectionized`
- Must preserve cleaned parent linkage.
- Required fields: `document_id`, `section_id`, `section_index`, `section_count`, `heading`, `text`.
- Multi-page documents with `section_count <= 1` are rejected unless `section_exempt` is true and documented.

`chunked`
- Must preserve section parent linkage.
- Required fields: `chunk_id`, `parent_section_id`, `chunk_index`, `heading`, `text`, `char_count`, `chunk_size_ceiling`.
- Oversized chunks are rejected.

`indexed`
- Must preserve chunk parent linkage and the dataset lineage that created the index row.
- Required fields: `dataset_id`, `index_name`, `embedding_model`, `vector_store`, `chunk_id`.

## Mandatory QA Gates

- Reject multi-page docs with `<= 1` section unless explicitly exempted.
- Reject chunks above the configured size ceiling.
- Reject null or empty headings unless explicitly allowed.
- Reject or quarantine records with missing `license` or `rights_basis`.
- Reject training export when `allowed_for_training` is false or provenance is incomplete.
- Reject cleaned records that still contain wrapper JSON leakage, HTML tags, or unclassified boilerplate.
- Report removed URLs, removed HTML, removed boilerplate, token delta, and repeated-pass delta.
- Distinguish successful cleaning from a no-op cleaning pass.
- Fail incremental export if aggregate rebuilds are not idempotent.

## Legacy To Canonical Mapping

The next sprint should absorb the strongest existing pieces instead of rewriting them blindly:

- reuse retry/resume logic from `Scraping/dump_5eapi_async.py`
- reuse domain scoping and site-specific extractors from `Scraping/scrape_dd_reports.py`
- reuse atomic writes, OCR fallback, and error reporting from `Scraping/BatchPDFCleaner.py`
- reuse extractor selection ideas from `Scraping/dnd_statblock_toolkit_v3.py`
- preserve useful provenance fields from `Scraping/dnd_rules_pipeline/dnd_rules_utils.py`

The following behaviors must not survive into the canonical path:

- fail-open robots handling
- null headings
- one-section one-chunk collapse
- wrapper JSON leaking into "clean" text
- aggregate rebuilds from partial incremental state
- blind FAISS chunking of raw JSONL text

## Exit Gate For Training Export

A training export is valid only if all of the following are true:

- every contributing source has a valid source manifest
- every contributing record has complete provenance
- every contributing record is classified as `training_and_retrieval`
- every contributing record passed stage validation
- every contributing record is clear of removal requests
- dataset manifest validation passes in strict mode

