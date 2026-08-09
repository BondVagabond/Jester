# Jester Repository Consolidation — Design

**Date:** 2026-08-08
**Status:** Approved, pending implementation plan
**Target remote:** https://github.com/BondVagabond/Jester

## Problem

Jester's work is spread across four unsynchronized folders on `F:\`. The git repo tracks
almost none of it.

| Folder | Size | Git | On GitHub | Last active |
|---|---:|---|---|---|
| `F:\Jester` | 3.2 GB | yes (`main`) | partially, stale | 2026-04-16 |
| `F:\Jester Code` | 135 MB | no | no | 2026-04-05 |
| `F:\Jester Training data` | 216 MB | no | no | 2025-10-13 |
| `F:\JesterData` | 37 MB | no | no | 2026-04-17 |

`origin/main` and local `HEAD` are both at `8ff8407` — nothing is unpushed. The repo simply
tracks the wrong tree: 316 files at `HEAD` (317 in the index, counting a staged 0-byte
add), of which 304 are the old `npcgen` tool (297 of those a
checked-in `node_modules/`), 4 are loose root scrapers, and 2 are 0-byte artifacts
(`python`, `Scraping/DNDCrawler`). Only 8 tracked files still exist on disk. Meanwhile
29,898 files are untracked, and there is no `.gitignore` at all.

### Two work streams, not one

**Stream A — product platform** (`F:\Jester Code`, through 2026-04-05)
`jester/` package with 16 subpackages, typed React frontend (Prep / Teaching / Live DM),
29 test modules, contract-heavy `training/`, `pyproject.toml` with `mypy --strict`.

**Stream B — data acquisition pipeline** (`F:\Jester\Scraping` + `Training` + `F:\JesterData`,
through 2026-04-17) — the newer stream. Async crawler, GUI server, discovery engine,
sectionize/chunk pipeline, quarantine, SQLite runtime state, 31 approved source manifests,
20 owned-corpus artifacts.

The streams overlap in `training/` and have diverged there. That is the only part of the
merge that is not mechanical.

## Decisions

| # | Decision | Choice |
|---|---|---|
| 1 | Repo topology | One repo, two top-level packages: `jester/` + `pipeline/`, shared `training/` |
| 2 | Git history | Preserve; commit restructure on top of `8ff8407` |
| 3 | Data + artifacts | Stay out of git; located via env vars, documented in README |
| 4 | Repo location | `F:\Jester` — reuse the existing clone and remote |
| 5 | Schema collision | Keep both, renamed apart — no forced migration |
| 6 | Pipeline layout | `pipeline/` holds active code only; one-off scrapers to `archive/scraping/` |
| 7 | `training/` conflicts | Latest work wins — Stream B, outright, no prose splicing |

## 1. Target structure

```
F:\Jester\
  jester/            # Stream A platform, unchanged
  frontend/          # Stream A React app, unchanged
  pipeline/
    runtime/         # 18 files from Scraping/runtime, incl. gui/
    rules/           # 6 files from Scraping/dnd_rules_pipeline
    pdf.py           # extract_pdf_text + helpers, rescued (see §4)
  training/          # merged, 93 files (see §3)
  tests/             # 31 modules (29 from A, 2 from B) + 5 helpers
  docs/              # incl. this spec
  prompts/  data/
  archive/
    npcgen/  faiss/  dm_cleaner/  "HTML cleaner"/
    "Phase 3 Generators"/  jester_watchdog/
    scraping/        # BookCleaner, rpg_cleaner_gui, dnd_statblock_toolkit_v3,
                     #   dump_5eapi_async, scrape_dd_reports, DNDCrawler,
                     #   d_d_play_reports…(2).py, BatchPDFCleaner CLI shell
  pyproject.toml  .gitignore  README.md  Roadmap.md
```

## 2. What is discarded

- The stale tracked tree: `npcgen/` (304 files), root scrapers, `.idea/`
- 0-byte commits `python` and `Scraping/DNDCrawler`
- `out/pycache/Program Files/WindowsApps/…` — an accidental copy of the Python 3.13 stdlib,
  a large share of `out/`'s 707 MB
- All caches: `venv/` (2.2 GB), `__pycache__`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`,
  `.benchmarks`, `node_modules/`, `jester.egg-info`, `jester_state.sqlite3`

Nothing is deleted before the §7 backup exists.

## 3. The `training/` merge

**93 files.** Stream A has 29, Stream B has 70, and 9 paths collide.

The naive union is 90 (61 B-only + 20 A-only + 9 collisions). The result is **92**, and the
+2 is not an error — it is §3.2's rename. Moving Stream A's two colliding schemas to
`training_source` / `training_dataset` puts them on paths that exist in neither stream, which
in turn lets Stream B's `source_manifest` / `dataset_manifest` land as new files rather than
overwrites. So only **7** of the 9 collisions actually overwrite in place:

```
29 (Stream A) + 70 (Stream B) − 7 (true in-place overwrites) = 92
(+1 for the validator rename in §3.2 = 93 final)
```

Verified set-identical to that expectation: 0 files missing, 0 unexpected extras.

### 3.1 Conflicts — Stream B wins

| File | Stream B | Stream A | Basis |
|---|---:|---:|---|
| `README.md` | 6426 B | 1465 B | newer, 5× more developed |
| `policy/data_governance.md` | 128 ln | 70 ln | enumerated rules vs prose summary |
| `policy/licensing_rules.md` | 87 ln | 52 ln | explicit license/rights value lists |
| `policy/training_eligibility.md` | 71 ln | 51 ln | concrete decision table |
| `manifests/source_manifest.schema.json` | **31/31 live manifests valid** | **0/31 valid** | load-bearing |
| `manifests/dataset_manifest.schema.json` | pipeline stages | training splits | matches live pipeline |
| `validation/validate_source_manifest.py` | 10441 B | 3595 B | validates the winning schema |
| `__init__.py` | 35 B | 80 B | consistency with B |
| `validation/__init__.py` | 381 B | 62 B | exports B's validators |

The schema result is decisive and was measured, not assumed: every one of the 31 approved
source manifests satisfies Stream B's `required` set; none satisfies Stream A's, which
demands `content_hash`, `origin`, `policy_category`, `removal_contact`, `reviewed_by`,
and `title`.

Stream A's three policy docs are **replaced, not spliced**. They are differently-worded
takes on the same policy; hand-merging prose would produce a document neither stream
reviewed. Per decision 7, latest work wins.

### 3.2 Stream A's schemas — renamed, not dropped

The two schemas serve a genuinely different stage and survive under non-colliding names:

- `manifests/source_manifest.schema.json` (A) → `manifests/training_source.schema.json`
- `manifests/dataset_manifest.schema.json` (A) → `manifests/training_dataset.schema.json`

> **Correction (found during Task 4 execution).** This section originally treated the merge
> as a file-level union — pick a winner per colliding path. That is wrong, because Stream A's
> governance layer is a **stack**, not a set of files:
>
> ```
> training_source.schema.json  ->  validate_training_source.py  ->  validate_record_eligibility.py
>                                                              \->  common.py
> ```
>
> Renaming only the schema while letting Stream B win the *validator* left
> `validate_record_eligibility.py` importing `validate_source_manifests` from a module that no
> longer defined it. `pytest` went from 176 passed to a collection error. The two validators
> have disjoint APIs, so this was never a version conflict — it was the schema collision one
> layer up.
>
> **The rename therefore extends to the validator:**
>
> - `validation/validate_source_manifest.py` (A) → `validation/validate_training_source.py`
>
> Its two importers repoint to the new module name — one line each, no semantic change.
> Stream B keeps the canonical `source_manifest` / `validate_source_manifest` names for the
> acquisition path. Result: **93 files**, not 92.
>
> The general rule this exposes: when resolving a collision, check whether the losing file is
> depended on by a file the union rule *retains*. A file-level winner-picking rule is not
> sufficient on its own.

Stream B's are **acquisition**-shaped: `seed_urls`, `allowed_domains`, `host_policy`,
`quarantine_rules`, `artifact_path`, `stage`, `pipeline_version`.
Stream A's are **training-governance**-shaped: `content_hash`, `reviewed_by`,
`policy_category`, `task_family`, `lineage`, `split`, `role`, `record_schema`.
They share only 10 and 5 properties respectively — versions of different things, not
different versions of one thing.

### 3.3 Union — carried across intact

**Stream A contributes 20 files:** `contracts/` (5), `schemas/training_record.schema.json`,
`manifests/model_contract.schema.json`, `manifests/examples/` (8),
`policy/removal_and_audit.md`, `policy/base_model_selection.md`, `quarantine/README.md`,
`validation/common.py`, `validation/validate_record_eligibility.py`.

**Stream B contributes 61 files:** `sources/approved/` (31 manifests),
`local_artifacts/dnd5e_owned/` (20 corpus docs) + its generator, `sources/CATALOG.md`,
`sources/README.md`, `manifests/candidate_source.schema.json`, `policy/redaction_policy.md`,
`validation/validate_candidate_source.py`, `validation/validate_corpus_record.py`,
`build_faiss.py`, `query_faiss.py`.

### 3.4 Encoding

Normalize the whole merged tree to UTF-8 **without** BOM. Skipping this leaves a `\ufeff` on
line 1 of the affected files and makes every future diff noisy.

> **Correction (found during Task 5 setup).** This section originally read "Stream B's
> markdown is UTF-8 **with BOM**; Stream A's is not," and the plan put the count at 38. Both
> were wrong, because the original scan only walked Stream B's trees (`Scraping/`, `Training/`,
> `tests/`) and never looked at `F:\Jester Code`. Measured across both streams:
>
> | source | BOM files | breakdown |
> |---|---:|---|
> | Stream A (`F:\Jester Code`) | **45** | 37 `.py`, 7 `.yaml`, 1 `.md` \u2014 incl. 29 in `jester/`, 7 in `prompts/`, 8 in `tests/` |
> | Stream B \u2014 `Training/` | 32 | 25 `.md`, 4 `.py`, 2 `.json`, 1 `.txt` |
> | Stream B \u2014 `Scraping/` | 6 | 6 `.py` |
> | **merged tree total** | **82** | 46 `.py`, 26 `.md`, 7 `.yaml`, 2 `.json`, 1 `.txt` |
>
> So it is Stream **A** that carries most of the BOMs, and mostly in `.py` files \u2014 the reverse
> of what this section claimed.
>
> **Consequence for \u00a71:** `jester/` is annotated "Stream A platform, unchanged". That remains
> true of its *logic* but not of its *bytes* \u2014 29 of its files lose a BOM here. BOM removal is
> semantically inert for Python, and the 176-test baseline is the proof; but "unchanged" should
> be read as "no behavioural change", not "byte-identical".

## 4. `BatchPDFCleaner` is load-bearing

`Scraping/runtime/pipeline.py:475` does `from Scraping.BatchPDFCleaner import extract_pdf_text`.
Archiving the module wholesale would break PDF ingestion. Split it:

The split boundary is the transitive dependency closure of `extract_pdf_text`, computed from
the AST rather than eyeballed.

> **Correction (found during Task 3 execution).** The closure was first computed by walking
> only `ast.FunctionDef` and matching `ast.Call` → `ast.Name` against function names. That is
> **function-only** and blind to classes and module constants. It missed that
> `extract_pdf_text` constructs `ErrorRecord` (an `ast.ClassDef`) in six exception branches.
> The corrected closure walks every `ast.Name` reference against all module-level bindings.

**→ `pipeline/pdf.py`** — 8 functions: `extract_pdf_text`, `page_to_text`, `ocr_single_page`,
`ensure_ocr_ready`, `normalize_text`, `dehyphenate`, `remove_page_numbers`,
`identify_headers_footers`; the constants `HEADER_FOOTER_MAX_LINES`,
`HEADER_FOOTER_MIN_REPEATS`; and **the `ErrorRecord` dataclass**, which moves here because
the moved code constructs it.

**→ `archive/scraping/BatchPDFCleaner.py`** — the rest: `FileResult`, `atomic_write_text`,
`chunk_text`, `filter_names`, `readable_dir`, `writable_dir`, `write_outputs`, `process_one`,
`parse_args`, `main`, `_sigint_handler`, `DEFAULT_WORKERS`. It needs three symbols back:

```python
from pipeline.pdf import ErrorRecord, ensure_ocr_ready, extract_pdf_text
```

`ErrorRecord` must be defined in **exactly one** place. `process_one` declares
`error_sink: List[ErrorRecord]`, hands that list to `extract_pdf_text` — which appends to it —
and then appends to it itself. Two separate class definitions would put two nominally
distinct types in one list, breaking `isinstance` and any type-based dispatch downstream.

`chunk_text` is **not** in the closure — it is called only by the CLI's `write_outputs`
path and stays with the archived tool.

## 5. Import rewrites — 14 statements, 7 files

`Scraping.*` → `pipeline.*`, `Training.*` → `training.*`:

| File | Lines |
|---|---|
| `pipeline/runtime/discovery.py` | 13, 14 |
| `pipeline/runtime/gui_server.py` | 14 |
| `pipeline/runtime/manifests.py` | 7 |
| `pipeline/runtime/pipeline.py` | 7, 9, 10, 11, 475 |
| `archive/scraping/scrape_dd_reports.py` | 19, 20, 21 |
| `tests/test_dnd_rules_parser.py` | 1 |
| `tests/test_runtime_local_text.py` | 3 |

Line 475 additionally retargets to `pipeline.pdf` per §4. Relative imports inside
`runtime/` (`from .models import …`) are unaffected.

### 5.1 Windows case-rename hazard

`core.ignorecase=true` in this clone. `Training` → `training` differs only in case, so git
records **nothing** and the rename is silently lost — then breaks on any case-sensitive
checkout (CI, Linux, Docker). Required two-step:

```bash
git mv Training training_tmp && git mv training_tmp training
```

Verify with `git ls-files training` — it must show lowercase paths before committing.

## 6. Packaging

Base `pyproject.toml` from Stream A. Four changes:

- `[tool.setuptools.packages.find] include` → `["jester*", "pipeline*", "training*"]`
- `[tool.mypy] packages` → add `pipeline`, `training`
- dependencies → add `aiohttp`, `beautifulsoup4`, `trafilatura`, `pdfplumber`
  (Stream B's, currently undeclared anywhere)
- new optional extra `ocr = ["pdf2image", "pytesseract"]` — both are already guarded
  imports in `BatchPDFCleaner` and require external binaries (poppler, tesseract)

`[tool.ruff] extend-exclude = ["archive"]` is already correct.

### 6.1 Typing

Stream A is `mypy --strict`. Stream B has never been type-checked and will not pass. Add a
per-module override so the merge is not blocked on a typing cleanup:

```toml
[[tool.mypy.overrides]]
module = ["pipeline.*", "training.*"]
ignore_errors = true
```

Tightening this is follow-up work, tracked separately. It is a deliberate, visible debt
marker — not a silent exemption.

## 7. Data, config, and `.gitignore`

No corpora, indexes, or run artifacts enter git. Roots are already env-configurable in
`pipeline/runtime/models.py`:

| Variable | Default |
|---|---|
| `JESTER_DATA_ROOT` | `F:\JesterData` |
| `JESTER_RUNTIME_ROOT` | `$JESTER_DATA_ROOT/runtime` |
| `JESTER_CANDIDATE_SOURCE_DIR` | `$JESTER_DATA_ROOT/candidate_sources` |

New `.gitignore` = Stream A's, plus `venv/`, `.venv/`, `out/`, `faiss/`, `debug/`, `logs/`,
`RAG_index/`, `Runtime/`, `.benchmarks/`, `*.sqlite3`, `*.egg-info/`.

README must state that ~460 MB of corpora live outside the repo at `F:\JesterData` and
`F:\Jester Training data`, and that **they are currently backed up by nothing**. Arranging
that backup is out of scope here but should not stay unaddressed.

## 8. Migration sequence

Built in a scratch tree; `F:\Jester` is not modified until step 6.

1. Back up all four folders to `F:\_JesterBackup_2026-08-08\`. Verify by file count and size.
2. Scaffold scratch tree from Stream A: `jester/`, `frontend/`, `tests/`, `docs/`,
   `prompts/`, `data/`, `archive/`, `pyproject.toml`.
3. Overlay Stream B: `pipeline/runtime/`, `pipeline/rules/`; split out `pipeline/pdf.py` (§4);
   one-off scrapers to `archive/scraping/`.
4. Merge `training/` per §3 — B wins the 9 conflicts, A's 2 schemas renamed, 81 union files
   copied, BOMs normalized.
5. Rewrite the 14 imports (§5). Apply `pyproject.toml` changes (§6). Write `.gitignore`
   and README.
6. Verify in scratch: `pip install -e .[dev]`, both suites, `ruff check`. **Gate — do not
   proceed on failure.**
7. In `F:\Jester`: `git rm -r --cached` the stale tree, move old contents aside, copy the
   verified tree in, handle the case-rename (§5.1), `git add -A`.
8. Inspect `git status` before committing — expect 408 files, not 30,000.
9. One commit on `main`, push to `origin/main`.

## 9. Verification gates

- [ ] 31 test modules collected; 29 Stream A tests still pass (no regression)
- [ ] 2 Stream B tests pass against rewritten imports
- [ ] all 31 approved manifests validate against merged `source_manifest.schema.json`
- [ ] `python -c "import jester, pipeline, training"` succeeds
- [ ] `ruff check .` clean; `mypy` passes on `jester` with overrides in place
- [ ] `git ls-files | wc -l` = 408 measured (274 Stream A excl. training + 93 training + 27 pipeline
      + 10 archived scrapers + 2 tests + 2 docs); 316 deletions staged; no `venv/`,
      `node_modules/`, `*.pyc`, `*.sqlite3` tracked
- [ ] `git ls-files training` shows lowercase paths
- [ ] fresh `git clone` into a temp dir imports cleanly with `JESTER_DATA_ROOT` set
- [ ] `git log` retains `8ff8407` and `0771db4`

## 10. Risks

| Risk | Mitigation |
|---|---|
| Case-rename silently dropped | §5.1 two-step; explicit `git ls-files` gate |
| Stream A regressions from shared `training/` | Its validators are separate modules; full suite is a gate |
| Hidden dependency on an archived scraper | `BatchPDFCleaner` was found by grep; same sweep run over `archive/scraping/` before step 7 |
| BOM churn | Normalize in step 4, before first commit |
| 3.5 GB working set during migration | Backup and scratch tree on `F:` (51 TB free) |
| Data loss | Nothing deleted before step 1 backup; all four folders retained until gates pass |

## Out of scope

- Typing cleanup for `pipeline/` and `training/` (§6.1)
- Backup strategy for the 460 MB of corpora (§7)
- Reconciling Stream A's governance fields into live manifests (decision 5 defers this)
- Any behavior change to either stream — this is a move-and-merge only
