# Jester Repository Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate four unsynchronized folders on `F:\` into one coherent repository at `F:\Jester`, pushed to https://github.com/BondVagabond/Jester, preserving existing history.

**Architecture:** Build the merged tree in a scratch directory on the same volume, verify it fully in isolation, then land it into the existing clone as a single restructure commit. `F:\Jester` is not modified until Task 8, and nothing is deleted until the user says so. Two top-level packages — `jester/` (product platform) and `pipeline/` (data acquisition) — share one merged `training/`.

**Tech Stack:** Python 3.12, setuptools, pytest, ruff, mypy, git 2.55, robocopy (bulk file moves), PowerShell + Git Bash.

**Spec:** [2026-08-08-jester-consolidation-design.md](../specs/2026-08-08-jester-consolidation-design.md)

## Global Constraints

- **Nothing is deleted before Task 1's backup is verified.** All four source folders remain on disk until the user explicitly approves cleanup after Task 9.
- **No migration content enters or leaves `F:\Jester` before Task 8.** Tasks 2–7 build only in `F:\_JesterMigration\`; they must not create, modify, move, or delete any tracked or untracked file of the repository's working tree.
  - **Sole exception:** the agent-scratch directory `F:\Jester\.superpowers\sdd\` — ledgers, briefs, reports, review packages. These are git-ignored (Task 7), preserved across the swap (Task 8 Step 2 keep-list), and never form part of the committed tree. Their presence is expected; their absence would mean the execution record was lost.
  - Reading from `F:\Jester\Scraping\`, `Training\`, and `tests\` is required by Tasks 3, 4, and 6 and is not a modification.
- **Work lands on a branch**, `restructure/consolidate-streams`, not directly on `main`. The merge to `main` is Task 9 and requires explicit user approval. *(This differs from the spec's step 9, which committed straight to `main`. A 408-file restructure that deletes all 316 tracked paths deserves a reviewable branch; the end state — history preserved, new tree on top — is identical.)*
- **Latest work wins.** On any `training/` collision, Stream B (`F:\Jester\Training`) overwrites Stream A (`F:\Jester Code\training`). No prose splicing. 9 files affected, listed in Task 4.
- **Stream A's two colliding schemas are renamed, never deleted:** `source_manifest.schema.json` → `training_source.schema.json`, `dataset_manifest.schema.json` → `training_dataset.schema.json`.
- **Encoding:** all text files land as UTF-8 **without** BOM. **82** files in the merged tree carry one (46 `.py`, 26 `.md`, 7 `.yaml`, 2 `.json`, 1 `.txt`) — 45 from Stream A, 38 from Stream B. An earlier figure of 38 counted only Stream B.
- **Python floor:** `requires-python = ">=3.12"`. Local interpreter is 3.12.10.
- **Line length:** ruff `line-length = 120`, `target-version = "py312"`, `extend-exclude = ["archive"]`.
- **Data roots stay external and env-configured:** `JESTER_DATA_ROOT` (default `F:\JesterData`), `JESTER_RUNTIME_ROOT`, `JESTER_CANDIDATE_SOURCE_DIR`. No corpora, indexes, or run artifacts enter git.
- **`core.ignorecase=true`.** Two consequences, both confirmed in execution:
  - *Case-rename:* verify `git ls-files training` shows lowercase paths. In practice this was a **no-op** — `Training/` was never tracked, so git had no rename to record, and no `HEAD` path is `Training`. Verify; don't reflexively `git mv`.
  - *Gitignore anchoring:* every data-root pattern **must** carry a leading `/`. Unanchored patterns match at any depth and, case-insensitively, `Runtime/` silently swallows `pipeline/runtime/`. See the Task 7 `.gitignore` correction note.

## Paths

| Alias | Path |
|---|---|
| REPO | `F:\Jester` |
| SRC_A | `F:\Jester Code` |
| SRC_B | `F:\Jester` (its `Scraping/`, `Training/`, `tests/`) |
| BACKUP | `F:\_JesterBackup_2026-08-08` |
| SCRATCH | `F:\_JesterMigration` |
| HOLD | `F:\_JesterBackup_2026-08-08\repo-pre-restructure` |

Disk: 263 GB free on `F:`. Peak additional usage ~7 GB.

---

### Task 1: Backup all four folders and verify

**Files:**
- Create: `F:\_JesterBackup_2026-08-08\` (4 subtrees)
- Create: `F:\_JesterBackup_2026-08-08\MANIFEST.txt`

**Interfaces:**
- Consumes: nothing
- Produces: a verified backup at BACKUP. Every later task depends on this existing. Task 8 moves the original repo contents into `BACKUP\repo-pre-restructure`.

- [ ] **Step 1: Record source inventory before copying**

```powershell
$src = @{
  'Jester'             = 'F:\Jester'
  'JesterCode'         = 'F:\Jester Code'
  'JesterTrainingData' = 'F:\Jester Training data'
  'JesterData'         = 'F:\JesterData'
}
New-Item -ItemType Directory -Force 'F:\_JesterBackup_2026-08-08' | Out-Null
$lines = foreach ($k in $src.Keys | Sort-Object) {
  $f = Get-ChildItem -LiteralPath $src[$k] -Recurse -File -Force -ErrorAction SilentlyContinue
  "{0}`t{1}`t{2}" -f $k, $f.Count, ($f | Measure-Object Length -Sum).Sum
}
$lines | Out-File -Encoding utf8 'F:\_JesterBackup_2026-08-08\MANIFEST.txt'
Get-Content 'F:\_JesterBackup_2026-08-08\MANIFEST.txt'
```

Expected: 4 lines, `name<TAB>filecount<TAB>totalbytes`. Note the numbers — Step 3 compares against them.

- [ ] **Step 2: Copy all four trees**

`/MIR` mirrors, `/MT:16` parallelizes, `/R:2 /W:2` limits retry stalls, `/NFL /NDL` quiets output. Robocopy exit codes 0–7 are success; 8+ is failure.

```powershell
$pairs = @(
  @('F:\Jester',               'F:\_JesterBackup_2026-08-08\Jester'),
  @('F:\Jester Code',          'F:\_JesterBackup_2026-08-08\JesterCode'),
  @('F:\Jester Training data', 'F:\_JesterBackup_2026-08-08\JesterTrainingData'),
  @('F:\JesterData',           'F:\_JesterBackup_2026-08-08\JesterData')
)
foreach ($p in $pairs) {
  robocopy $p[0] $p[1] /MIR /MT:16 /R:2 /W:2 /NFL /NDL /NP | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy FAILED for $($p[0]) (exit $LASTEXITCODE)" }
  Write-Host "ok: $($p[0]) -> exit $LASTEXITCODE"
}
```

Expected: four `ok:` lines, no throw. Takes several minutes (3.5 GB).

- [ ] **Step 3: Verify the backup matches the manifest**

```powershell
$dst = @{
  'Jester'='F:\_JesterBackup_2026-08-08\Jester'
  'JesterCode'='F:\_JesterBackup_2026-08-08\JesterCode'
  'JesterTrainingData'='F:\_JesterBackup_2026-08-08\JesterTrainingData'
  'JesterData'='F:\_JesterBackup_2026-08-08\JesterData'
}
$fail = $false
foreach ($line in Get-Content 'F:\_JesterBackup_2026-08-08\MANIFEST.txt') {
  $n,$c,$b = $line -split "`t"
  $f = Get-ChildItem -LiteralPath $dst[$n] -Recurse -File -Force -ErrorAction SilentlyContinue
  $ac = $f.Count; $ab = ($f | Measure-Object Length -Sum).Sum
  $ok = ($ac -eq [int]$c) -and ($ab -eq [int64]$b)
  if (-not $ok) { $fail = $true }
  "{0,-20} src={1,-7} dst={2,-7} {3}" -f $n, $c, $ac, $(if($ok){'OK'}else{'MISMATCH'})
}
if ($fail) { throw 'BACKUP VERIFICATION FAILED - do not proceed' }
Write-Host 'Backup verified.'
```

Expected: 4 `OK` rows and `Backup verified.`

**GATE — if this throws, stop. Every later task assumes this backup is good.**

- [ ] **Step 4: No commit**

Nothing has entered git yet. The backup lives outside the repo by design.

---

### Task 2: Create the branch and scaffold Stream A into scratch

**Files:**
- Create: `F:\_JesterMigration\` populated from SRC_A
- Modify: REPO git state — new branch `restructure/consolidate-streams`

**Interfaces:**
- Consumes: verified BACKUP from Task 1
- Produces: SCRATCH containing `jester/`, `frontend/`, `tests/`, `docs/`, `prompts/`, `data/`, `archive/`, `pyproject.toml`, `Roadmap.md`. Tasks 3–7 build on this. Branch `restructure/consolidate-streams` is where Task 8 commits.

- [ ] **Step 1: Create the working branch**

```bash
cd /f/Jester && git checkout -b restructure/consolidate-streams && git branch --show-current
```

Expected: `restructure/consolidate-streams`. No files change — the stale tree and 30k untracked files are still present and untouched.

- [ ] **Step 2: Copy Stream A into scratch, excluding caches and build output**

```powershell
$XD = @('__pycache__','.mypy_cache','.pytest_cache','.ruff_cache','node_modules',
        '.benchmarks','.git','dist','dist-current','build','jester.egg-info','.venv','venv')
robocopy 'F:\Jester Code' 'F:\_JesterMigration' /E /MT:16 /R:2 /W:2 /NFL /NDL /NP `
  /XD $XD /XF '*.pyc' '*.log' '*.sqlite3' | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed (exit $LASTEXITCODE)" }
Get-ChildItem 'F:\_JesterMigration' | Select-Object Name
```

Expected top level: `archive`, `data`, `docs`, `frontend`, `jester`, `prompts`, `pyproject.toml`, `README.md`, `Roadmap.md`, `tests`, `training`, `.gitignore`.

Note `training/` arrives here as Stream A's copy. Task 4 overwrites the 9 colliding files.

- [ ] **Step 3: Verify Stream A imports and tests pass in isolation**

Establishes the no-regression baseline. If Stream A is already broken, we need to know now, not after merging.

```bash
cd /f/_JesterMigration && python -m venv .venv && ./.venv/Scripts/python.exe -m pip install -q -e ".[dev]" && ./.venv/Scripts/python.exe -m pytest tests -q 2>&1 | tail -15
```

Expected: 29 test modules collected, all passing. Record the exact pass count — Task 7 compares against it.

If any Stream A test already fails, stop and report. Do not "fix" it as part of the migration; that conflates two changes.

- [ ] **Step 4: Commit nothing yet**

SCRATCH is outside the repo and not under version control. The first commit is Task 8.

---

### Task 3: Move Stream B pipeline code into `pipeline/`

**Files:**
- Create: `F:\_JesterMigration\pipeline\__init__.py`
- Create: `F:\_JesterMigration\pipeline\runtime\` (18 files, from `F:\Jester\Scraping\runtime`)
- Create: `F:\_JesterMigration\pipeline\rules\` (7 files, from `F:\Jester\Scraping\dnd_rules_pipeline`)
- Create: `F:\_JesterMigration\pipeline\pdf.py` (extracted from `Scraping\BatchPDFCleaner.py`)
- Create: `F:\_JesterMigration\archive\scraping\` (7 one-off scripts)

**Interfaces:**
- Consumes: SCRATCH from Task 2
- Produces:
  - `pipeline.pdf.extract_pdf_text(pdf_path: Path, do_ocr: bool = False, dpi: int = 300, ...) -> str`
  - `pipeline.pdf.ensure_ocr_ready() -> Optional[str]`
  - `pipeline.runtime.*` — all modules keep their existing names and relative imports
  - `pipeline.rules.dnd_rules_parser.{parse_into_segments, chunk_segments}`
  - `pipeline.rules.dnd_rules_cleaner.clean_html_text`
  - `pipeline.rules.dnd_rules_utils.{bayes_quality_posterior, score_rulesyness}`

  Task 6 rewrites imports to these paths. Names are unchanged from Stream B — only the package prefix moves.

- [ ] **Step 1: Copy runtime and rules into `pipeline/`**

```powershell
New-Item -ItemType Directory -Force 'F:\_JesterMigration\pipeline' | Out-Null
robocopy 'F:\Jester\Scraping\runtime' 'F:\_JesterMigration\pipeline\runtime' /E `
  /XD '__pycache__' /XF '*.pyc' /R:2 /W:2 /NFL /NDL /NP | Out-Null
robocopy 'F:\Jester\Scraping\dnd_rules_pipeline' 'F:\_JesterMigration\pipeline\rules' /E `
  /XD '__pycache__' /XF '*.pyc' /R:2 /W:2 /NFL /NDL /NP | Out-Null
[System.IO.File]::WriteAllText('F:\_JesterMigration\pipeline\__init__.py',
  '"""Jester data acquisition pipeline."""' + [Environment]::NewLine,
  (New-Object System.Text.UTF8Encoding $false))
(Get-ChildItem 'F:\_JesterMigration\pipeline' -Recurse -File).Count
```

Expected: 26 files (18 runtime incl. `gui/`, 7 rules, 1 `__init__.py`).

- [ ] **Step 2: Create `pipeline/pdf.py` with the 8 closure functions**

Copy from `F:\Jester\Scraping\BatchPDFCleaner.py` verbatim — same bodies, no behavior change. The 8 functions are the AST-computed transitive call closure of `extract_pdf_text`; `chunk_text` is deliberately excluded (only the CLI calls it).

```python
"""PDF text extraction for the ingestion pipeline.

Extracted from the legacy BatchPDFCleaner CLI so that pipeline.runtime.pipeline
can depend on extraction without importing an argparse-based tool.
"""
from __future__ import annotations

import contextlib
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional

import pdfplumber

try:
    from pdf2image import convert_from_path  # requires poppler
except ImportError:  # pragma: no cover - optional OCR path
    convert_from_path = None

try:
    import pytesseract
except ImportError:  # pragma: no cover - optional OCR path
    pytesseract = None

HEADER_FOOTER_MAX_LINES = 3
HEADER_FOOTER_MIN_REPEATS = 0.6  # 60% of pages

# Copy verbatim from Scraping/BatchPDFCleaner.py, in this order:
#   normalize_text            (line 67)
#   dehyphenate               (line 74)
#   remove_page_numbers       (line 77)
#   identify_headers_footers  (line 85)
#   ensure_ocr_ready          (line 123)
#   page_to_text              (line 161)
#   ocr_single_page           (line 168)
#   extract_pdf_text          (line 182)
```

Preserve each function's body exactly. `identify_headers_footers` uses a function-local `from collections import Counter` at its line 86 — keep it local.

- [ ] **Step 3: Move the one-off scrapers to archive**

```powershell
New-Item -ItemType Directory -Force 'F:\_JesterMigration\archive\scraping' | Out-Null
$files = @('BatchPDFCleaner.py','BookCleaner.py','DNDCrawler','README.txt',
           'd_d_play_reports_transcripts_scraper_async_python (2).py',
           'dnd_statblock_toolkit_v3.py','dump_5eapi_async.py',
           'rpg_cleaner_gui.py','scrape_dd_reports.py')
foreach ($f in $files) {
  Copy-Item -LiteralPath "F:\Jester\Scraping\$f" `
            -Destination "F:\_JesterMigration\archive\scraping\$f" -Force
}
(Get-ChildItem 'F:\_JesterMigration\archive\scraping' -File).Count
```

Expected: 9. `statlogs.log` and `__init__.py` are intentionally not copied — the log is a build artifact, and the package `__init__.py` does not apply to an archive folder.

**Note on the three root scripts.** `BatchPDFCleaner.py`, `BookCleaner.py`, and `dump_5eapi_async.py` exist both at `HEAD` (repo root) and on disk under `Scraping/`, and the two copies have **diverged** — these were edited after the last commit, not just moved. The disk versions are the newer ones and are what gets archived, per "latest work wins". The `HEAD` versions stay reachable at `git show 8ff8407:<file>`.

- [ ] **Step 3b: Rescue `scrape_btn_names.py` from history**

This file is tracked at `HEAD` (5113 bytes) but exists **nowhere on disk** — not in `F:\Jester`, not in `F:\Jester Code`. If it is not restored, the restructure commit removes it and it becomes reachable only through git history.

```bash
cd /f/Jester && git show HEAD:scrape_btn_names.py > /f/_JesterMigration/archive/scraping/scrape_btn_names.py && wc -c /f/_JesterMigration/archive/scraping/scrape_btn_names.py
```

Expected: `5113`. The archive folder now holds 10 files.

If you would rather let it live in history alone, skip this step and adjust Step 3's expected count back to 9 — but make that a decision, not an oversight.

- [ ] **Step 4: Trim the archived CLI to import from `pipeline.pdf`**

In `F:\_JesterMigration\archive\scraping\BatchPDFCleaner.py`, delete the 8 moved functions and the two constants, then add below the existing stdlib imports:

```python
from pipeline.pdf import ensure_ocr_ready, extract_pdf_text
```

Retained here: `FileResult`, `ErrorRecord`, `atomic_write_text`, `chunk_text`, `filter_names`, `readable_dir`, `writable_dir`, `write_outputs`, `process_one`, `parse_args`, `_STOP`, `_sigint_handler`, `main`, `DEFAULT_WORKERS`. `main` calls `ensure_ocr_ready`; `process_one` calls `extract_pdf_text` — both now come from the import.

Remove the now-unused `import pdfplumber` and the `pdf2image`/`pytesseract` guarded imports from the CLI; keep `unicodedata` and `re` only if `chunk_text` or the retained functions still use them.

- [ ] **Step 5: Verify the split is sound**

```bash
cd /f/_JesterMigration && ./.venv/Scripts/python.exe -m pip install -q pdfplumber && ./.venv/Scripts/python.exe -c "
import ast,sys
src=open('pipeline/pdf.py',encoding='utf-8').read()
t=ast.parse(src)
have={n.name for n in t.body if isinstance(n,ast.FunctionDef)}
want={'normalize_text','dehyphenate','remove_page_numbers','identify_headers_footers',
      'ensure_ocr_ready','page_to_text','ocr_single_page','extract_pdf_text'}
assert have==want, f'missing={want-have} extra={have-want}'
names={n.id for n in ast.walk(t) if isinstance(n,ast.Name)}
import builtins
undef=names-have-set(dir(builtins))-{'Path','Dict','List','Optional','pdfplumber',
  'convert_from_path','pytesseract','contextlib','re','unicodedata','Counter',
  'HEADER_FOOTER_MAX_LINES','HEADER_FOOTER_MIN_REPEATS'}
print('unresolved names:', sorted(n for n in undef if not n.startswith('_')) or 'none')
import pipeline.pdf as m
print('imports OK; callable:', callable(m.extract_pdf_text), callable(m.ensure_ocr_ready))
"
```

Expected: `unresolved names: none` and `imports OK; callable: True True`.

- [ ] **Step 6: No commit**

Still in SCRATCH, outside git.

---

### Task 4: Merge `training/`

**Files:**
- Modify: `F:\_JesterMigration\training\` — 9 files overwritten, 2 renamed, 61 added
- Result: 93 files (7 overwritten in place, 3 renamed, 63 added)

**Interfaces:**
- Consumes: SCRATCH `training/` (Stream A's copy, from Task 2)
- Produces:
  - `training.validation.{validate_manifest, manifest_allows_collection}` — Stream B's, used by `pipeline.runtime.manifests` and `pipeline.runtime.gui_server`
  - `training.validation.{validate_record, validate_records}` — used by `pipeline.runtime.pipeline` and `pipeline.runtime.discovery`
  - `training.validation.validate_candidate_manifest` — used by `pipeline.runtime.discovery`
  - `training/manifests/source_manifest.schema.json` — the acquisition schema, 31 live manifests validate against it

  Task 6's import rewrites target these exact names.

- [ ] **Step 1: Rename Stream A's two colliding schemas before the overwrite**

Do this first. If the overlay runs first, Stream B's files land on top and A's are lost.

```powershell
$m = 'F:\_JesterMigration\training\manifests'
Move-Item "$m\source_manifest.schema.json"  "$m\training_source.schema.json"  -Force
Move-Item "$m\dataset_manifest.schema.json" "$m\training_dataset.schema.json" -Force
Get-ChildItem $m -File | Select-Object -ExpandProperty Name
```

Expected: `model_contract.schema.json`, `training_dataset.schema.json`, `training_source.schema.json` (plus the `examples/` subdir).

- [ ] **Step 2: Overlay Stream B — latest work wins on all 9 collisions**

`/E` copies the tree; without `/XO` or `/XN`, robocopy overwrites unconditionally, which is what "latest wins" requires here.

```powershell
robocopy 'F:\Jester\Training' 'F:\_JesterMigration\training' /E `
  /XD '__pycache__' /XF '*.pyc' /R:2 /W:2 /NFL /NDL /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed (exit $LASTEXITCODE)" }
(Get-ChildItem 'F:\_JesterMigration\training' -Recurse -File).Count
```

Expected: **92**.

Only **7** of the 9 collisions overwrite in place; the other 2 paths were vacated by
Step 1's rename, so Stream B's copies land as new files. `29 + 70 - 7 = 92`.

The 9 colliding files: `README.md`, `__init__.py`, `validation/__init__.py`, `validation/validate_source_manifest.py`, `policy/data_governance.md`, `policy/licensing_rules.md`, `policy/training_eligibility.md`, `manifests/source_manifest.schema.json`, `manifests/dataset_manifest.schema.json`.

- [ ] **Step 3: Verify the merge composition**

```bash
cd /f/_JesterMigration && python -c "
import os,json,glob
T='training'
n=sum(len([f for f in fn if not f.endswith('.pyc')])
      for dp,dn,fn in os.walk(T) if '__pycache__' not in dp)
print('total files:', n); assert n==92, n
for p in ['manifests/training_source.schema.json','manifests/training_dataset.schema.json',
          'manifests/model_contract.schema.json','schemas/training_record.schema.json',
          'validation/common.py','validation/validate_record_eligibility.py',
          'policy/removal_and_audit.md','policy/base_model_selection.md','quarantine/README.md']:
    assert os.path.exists(os.path.join(T,p)), 'LOST Stream A file: '+p
print('Stream A unique files: all present')
assert len(glob.glob(T+'/contracts/*.md'))==5
assert len(glob.glob(T+'/manifests/examples/*.json'))==8
assert len(glob.glob(T+'/sources/approved/*.json'))==31
assert len(glob.glob(T+'/local_artifacts/dnd5e_owned/*.md'))==20
print('counts OK: contracts=5 examples=8 approved=31 artifacts=20')
sch=json.load(open(T+'/manifests/source_manifest.schema.json',encoding='utf-8-sig'))
req=set(sch['required'])
assert 'seed_urls' in sch['properties'], 'wrong schema won - Stream A overwrote Stream B'
bad=[f for f in glob.glob(T+'/sources/approved/*.json')
     if req - set(json.load(open(f,encoding='utf-8-sig')))]
print(f'manifests validating: {31-len(bad)}/31'); assert not bad, bad
"
```

Expected: `total files: 92`, all assertions pass, `manifests validating: 31/31`.

**GATE — a count other than 92, or any lost Stream A file, means the overlay misfired. Re-copy from BACKUP and retry.**

- [ ] **Step 4: No commit**

---

### Task 5: Normalize encodings

**Files:**
- Modify: 82 files across `jester/`, `training/`, `tests/`, `prompts/`, `pipeline/`, `archive/scraping/`, and `README.md` — strip UTF-8 BOM

**Interfaces:**
- Consumes: SCRATCH after Task 4
- Produces: no BOM anywhere in the tree. Prevents a `\ufeff` on line 1 of every Stream B document making all future diffs noisy.

- [ ] **Step 1: Strip BOMs tree-wide**

```bash
cd /f/_JesterMigration && python -c "
import os
SKIP={'.git','.venv','node_modules','__pycache__','.mypy_cache','.pytest_cache','.ruff_cache'}
EXT={'.py','.md','.json','.txt','.js','.html','.css','.yaml','.yml','.toml'}
fixed=[]
for dp,dn,fn in os.walk('.'):
    dn[:]=[d for d in dn if d not in SKIP]
    for f in fn:
        if os.path.splitext(f)[1] not in EXT: continue
        p=os.path.join(dp,f)
        b=open(p,'rb').read()
        if b.startswith(b'\xef\xbb\xbf'):
            open(p,'wb').write(b[3:]); fixed.append(p)
print(f'stripped {len(fixed)} BOMs')
for p in sorted(fixed): print('  ',p)
"
```

Expected: `stripped 82 BOMs` — 46 `.py`, 26 `.md`, 7 `.yaml`, 2 `.json`, 1 `.txt`.

If the count differs, report it rather than adjusting the expectation; the tree has changed across tasks and the number is a measurement, not a constant.

- [ ] **Step 2: Verify none remain and nothing was corrupted**

```bash
cd /f/_JesterMigration && python -c "
import os
SKIP={'.git','.venv','node_modules','__pycache__','.mypy_cache','.pytest_cache','.ruff_cache'}
bad=[]
for dp,dn,fn in os.walk('.'):
    dn[:]=[d for d in dn if d not in SKIP]
    for f in fn:
        p=os.path.join(dp,f)
        try:
            if open(p,'rb').read(3)==b'\xef\xbb\xbf': bad.append(p)
        except OSError: pass
print('remaining BOMs:', bad or 'none'); assert not bad
import ast,glob
for p in glob.glob('training/**/*.py',recursive=True)+glob.glob('pipeline/**/*.py',recursive=True):
    ast.parse(open(p,encoding='utf-8').read())
print('all pipeline/ and training/ .py files still parse')
import json
for p in glob.glob('training/**/*.json',recursive=True):
    json.load(open(p,encoding='utf-8'))
print('all training/ .json files still parse')
"
```

Expected: `remaining BOMs: none`, both parse confirmations.

- [ ] **Step 3: No commit**

---

### Task 6: Rewrite the 14 cross-package imports

**Files:**
- Modify: `pipeline/runtime/discovery.py:13,14`
- Modify: `pipeline/runtime/gui_server.py:14`
- Modify: `pipeline/runtime/manifests.py:7`
- Modify: `pipeline/runtime/pipeline.py:7,9,10,11,475`
- Modify: `archive/scraping/scrape_dd_reports.py:19,20,21`
- Create: `F:\_JesterMigration\tests\test_dnd_rules_parser.py` (from SRC_B, import rewritten)
- Create: `F:\_JesterMigration\tests\test_runtime_local_text.py` (from SRC_B, import rewritten)

**Interfaces:**
- Consumes: `pipeline.*` and `training.*` names produced by Tasks 3 and 4
- Produces: a tree where `import jester, pipeline, training` all resolve. Task 7 runs the full suite against it.

- [ ] **Step 1: Copy Stream B's two test modules in**

```powershell
Copy-Item 'F:\Jester\tests\test_dnd_rules_parser.py'  'F:\_JesterMigration\tests\' -Force
Copy-Item 'F:\Jester\tests\test_runtime_local_text.py' 'F:\_JesterMigration\tests\' -Force
```

No name collision with Stream A's 29 modules — verified.

- [ ] **Step 2: Apply the rewrites**

Exact old → new, all 15:

| File | Old | New |
|---|---|---|
| `pipeline/runtime/discovery.py` | `from Training.validation import validate_records` | `from training.validation import validate_records` |
| `pipeline/runtime/discovery.py` | `from Training.validation.validate_candidate_source import validate_candidate_manifest` | `from training.validation.validate_candidate_source import validate_candidate_manifest` |
| `pipeline/runtime/gui_server.py` | `from Training.validation.validate_source_manifest import manifest_allows_collection, validate_manifest` | `from training.validation.validate_source_manifest import manifest_allows_collection, validate_manifest` |
| `pipeline/runtime/manifests.py` | `from Training.validation.validate_source_manifest import manifest_allows_collection, validate_manifest` | `from training.validation.validate_source_manifest import manifest_allows_collection, validate_manifest` |
| `pipeline/runtime/pipeline.py` | `from Training.validation import validate_records` | `from training.validation import validate_records` |
| `pipeline/runtime/pipeline.py` | `from Scraping.dnd_rules_pipeline.dnd_rules_cleaner import clean_html_text` | `from pipeline.rules.dnd_rules_cleaner import clean_html_text` |
| `pipeline/runtime/pipeline.py` | `from Scraping.dnd_rules_pipeline.dnd_rules_parser import chunk_segments, parse_into_segments` | `from pipeline.rules.dnd_rules_parser import chunk_segments, parse_into_segments` |
| `pipeline/runtime/pipeline.py` | `from Scraping.dnd_rules_pipeline.dnd_rules_utils import bayes_quality_posterior, score_rulesyness` | `from pipeline.rules.dnd_rules_utils import bayes_quality_posterior, score_rulesyness` |
| `pipeline/runtime/pipeline.py:475` | `from Scraping.BatchPDFCleaner import extract_pdf_text` | `from pipeline.pdf import extract_pdf_text` |
| `archive/scraping/scrape_dd_reports.py` | `from Scraping.runtime.crawler import run_crawl_once` | `from pipeline.runtime.crawler import run_crawl_once` |
| `archive/scraping/scrape_dd_reports.py` | `from Scraping.runtime.models import DEFAULT_RUNTIME_ROOT` | `from pipeline.runtime.models import DEFAULT_RUNTIME_ROOT` |
| `archive/scraping/scrape_dd_reports.py` | `from Scraping.runtime.state_store import RuntimeStateStore` | `from pipeline.runtime.state_store import RuntimeStateStore` |
| `tests/test_dnd_rules_parser.py` | `from Scraping.dnd_rules_pipeline.dnd_rules_parser import chunk_segments` | `from pipeline.rules.dnd_rules_parser import chunk_segments` |
| `tests/test_runtime_local_text.py` | `from Scraping.runtime.pipeline import process_text_document` | `from pipeline.runtime.pipeline import process_text_document` |

Scripted, since the mapping is mechanical:

```bash
cd /f/_JesterMigration && python -c "
import re,glob
SUBS=[(r'\bfrom Training\.validation\b','from training.validation'),
      (r'\bfrom Scraping\.dnd_rules_pipeline\.','from pipeline.rules.'),
      (r'\bfrom Scraping\.runtime\.','from pipeline.runtime.'),
      (r'\bfrom Scraping\.BatchPDFCleaner import','from pipeline.pdf import')]
tot=0
for p in glob.glob('pipeline/**/*.py',recursive=True)+glob.glob('tests/*.py')+glob.glob('archive/scraping/*.py'):
    s=o=open(p,encoding='utf-8').read()
    for pat,rep in SUBS: s=re.sub(pat,rep,s)
    if s!=o:
        n=sum(1 for a,b in zip(o.splitlines(),s.splitlines()) if a!=b)
        open(p,'w',encoding='utf-8',newline='').write(s); tot+=n
        print(f'{n:2d}  {p}')
print('lines changed:',tot)
"
```

Expected: 14 lines changed across 7 files.

- [ ] **Step 3: Verify no stale references remain**

```bash
cd /f/_JesterMigration && grep -rn -E "\b(from|import) (Scraping|Training)\b" --include=*.py . | grep -v "^./.venv/" || echo "no stale imports"
```

Expected: `no stale imports`.

- [ ] **Step 4: Verify all three packages import**

```bash
cd /f/_JesterMigration && ./.venv/Scripts/python.exe -c "
import jester, pipeline, training
import pipeline.runtime.pipeline, pipeline.runtime.discovery
import pipeline.runtime.gui_server, pipeline.runtime.manifests
import pipeline.rules.dnd_rules_parser, pipeline.pdf
import training.validation
from training.validation import validate_manifest, validate_records, validate_candidate_manifest
print('all imports resolve')
"
```

Expected: `all imports resolve`. Requires Task 7's dependency additions if `aiohttp`/`bs4` are missing — if this fails on a missing third-party module, do Task 7 Step 1 first, then return here.

- [ ] **Step 5: No commit**

---

### Task 7: Packaging, gitignore, README, full verification

**Files:**
- Modify: `F:\_JesterMigration\pyproject.toml`
- Create: `F:\_JesterMigration\.gitignore` (replaces Stream A's)
- Create: `F:\_JesterMigration\README.md` (replaces Stream A's)

**Interfaces:**
- Consumes: the complete merged tree from Tasks 3–6
- Produces: an installable, lint-clean, test-passing tree ready to land. Task 8 copies it as-is.

- [ ] **Step 1: Update `pyproject.toml`**

Four changes to Stream A's file:

```toml
dependencies = [
  "aiohttp>=3.9,<4.0",
  "beautifulsoup4>=4.12,<5.0",
  "fastapi>=0.115,<1.0",
  "httpx>=0.27,<1.0",
  "pdfplumber>=0.11,<1.0",
  "pydantic>=2.7,<3.0",
  "PyYAML>=6.0,<7.0",
  "trafilatura>=1.12,<2.0",
  "uvicorn>=0.30,<1.0",
]

[project.optional-dependencies]
dev = [
  "mypy>=1.11,<2.0",
  "pytest>=8.2,<9.0",
  "ruff>=0.6,<1.0",
]
ocr = [
  "pdf2image>=1.17,<2.0",
  "pytesseract>=0.3.10,<1.0",
]

[tool.setuptools.packages.find]
include = ["jester*", "pipeline*", "training*"]

[tool.mypy]
python_version = "3.12"
strict = true
plugins = ["pydantic.mypy"]
packages = ["jester", "pipeline", "training", "tests"]

[[tool.mypy.overrides]]
module = ["pipeline.*", "training.*"]
ignore_errors = true
```

The `ocr` extra is separate because `pdf2image` and `pytesseract` need external binaries (poppler, tesseract) and are already guarded imports.

The mypy override is deliberate, visible debt: Stream B has never been type-checked and will not pass `--strict`. Tightening it is tracked as follow-up, not part of this migration.

- [ ] **Step 2: Write `.gitignore`**

```gitignore
__pycache__/
*.pyc
.mypy_cache/
.pytest_cache/
.ruff_cache/
.benchmarks/
.venv/
venv/
*.egg-info/
node_modules/
dist/
build/
*.log
*.sqlite3

# Data roots and generated artifacts - see README
/out/
/faiss/
/debug/
/logs/
/RAG_index/
/Runtime/

# Agent scratch (SDD ledger, briefs, review packages)
.superpowers/
```

> **Correction (found during Task 8 execution).** These six patterns were originally written
> unanchored (`out/`, `faiss/`, `Runtime/`, …). A gitignore pattern with no leading slash
> matches **at every depth**, and this repo has `core.ignorecase=true`, so:
>
> - `Runtime/` silently matched `pipeline/runtime/` — **all 18 files**, the core of Stream B
> - `faiss/` silently matched `archive/faiss/` — 3 files
>
> The first `git add -A` staged **387** instead of 408, and nothing would have errored: the
> commit would simply have been missing the crawler, GUI server, discovery engine, and staging
> pipeline. The leading `/` anchors each pattern to the repository root, which is what was
> always meant.
>
> This is precisely the failure the staged-count gate exists to catch — the count was wrong by
> 21 and that discrepancy is the only signal there was.

- [ ] **Step 3: Write `README.md`**

Replace Stream A's. Must cover: the two packages and what each does; the three env vars with defaults; that ~460 MB of corpora live outside the repo at `F:\JesterData` and `F:\Jester Training data`; and — stated plainly — that **those corpora are currently backed up by nothing**, with the one-off `F:\_JesterBackup_2026-08-08` snapshot explicitly not a backup strategy.

```markdown
# Jester

Two packages:

- **`jester/`** — the product platform: FastAPI backend, deterministic rules and
  game-state engine, multi-role AI orchestration, and a typed React frontend with
  Prep, Teaching, and Live DM workspaces.
- **`pipeline/`** — data acquisition: async crawler, discovery engine, sectionize
  and chunk pipeline, quarantine, and SQLite runtime state.

`training/` holds the shared governance layer — source manifests, policy, schemas,
and validators that both packages depend on.

## Setup

    python -m venv .venv
    .venv\Scripts\pip install -e ".[dev]"
    .venv\Scripts\pytest

Python 3.12+. For PDF OCR, also install `.[ocr]` plus poppler and tesseract.

## Data roots

Corpora, indexes, and run artifacts live **outside** this repo:

| Variable | Default |
|---|---|
| `JESTER_DATA_ROOT` | `F:\JesterData` |
| `JESTER_RUNTIME_ROOT` | `$JESTER_DATA_ROOT/runtime` |
| `JESTER_CANDIDATE_SOURCE_DIR` | `$JESTER_DATA_ROOT/candidate_sources` |

Roughly 460 MB of corpora sit at `F:\JesterData` and `F:\Jester Training data`.

> **These are not backed up.** `F:\_JesterBackup_2026-08-08` is a one-off snapshot
> taken during the repository consolidation, not an ongoing backup. Losing that
> volume loses the corpora. Setting up real backup is outstanding work.
```

- [ ] **Step 4: Reinstall and run the full suite**

```bash
cd /f/_JesterMigration && ./.venv/Scripts/python.exe -m pip install -q -e ".[dev]" && ./.venv/Scripts/python.exe -m pytest tests -q 2>&1 | tail -20
```

Expected: 31 modules collected, all passing. The 29 Stream A counts must match Task 2 Step 3 exactly — any drop is a regression caused by the merge, not a pre-existing failure.

- [ ] **Step 5: Lint and type-check**

```bash
cd /f/_JesterMigration && ./.venv/Scripts/python.exe -m ruff check . && ./.venv/Scripts/python.exe -m mypy 2>&1 | tail -5
```

Expected: ruff clean; mypy passes on `jester` with `pipeline`/`training` errors suppressed by the override.

If ruff flags Stream B files (it has never been linted), fix only mechanical issues — import order, unused imports, whitespace. Do **not** make behavioral changes. If a fix looks behavioral, add the rule to a per-file ignore and note it for follow-up.

**GATE — do not proceed to Task 8 until tests and lint pass.**

- [ ] **Step 6: No commit**

---

### Task 8: Land the tree into the repo

**Files:**
- Modify: `F:\Jester` — remove stale tree, install merged tree
- Move: current `F:\Jester` contents (except `.git`) → `F:\_JesterBackup_2026-08-08\repo-pre-restructure`

**Interfaces:**
- Consumes: the verified SCRATCH tree from Task 7; branch from Task 2
- Produces: a staged restructure in `F:\Jester` on `restructure/consolidate-streams`, ready to commit.

- [ ] **Step 1: Confirm branch and preserve the spec and plan**

```bash
cd /f/Jester && git branch --show-current && cp -r docs/superpowers /f/_JesterMigration/docs/ && ls /f/_JesterMigration/docs/superpowers/specs /f/_JesterMigration/docs/superpowers/plans
```

Expected: `restructure/consolidate-streams`, and both this plan and the spec now present in SCRATCH so they survive the swap.

- [ ] **Step 2: Move the old working tree aside**

Same-volume move, so it is a fast rename, not a copy. `.git` stays.

`.superpowers` is preserved alongside `.git`: it holds this execution's ledger, briefs, and review packages. Moving it aside mid-run destroys the recovery record at the exact moment it matters most.

```powershell
$hold = 'F:\_JesterBackup_2026-08-08\repo-pre-restructure'
$keep = @('.git', '.superpowers')
New-Item -ItemType Directory -Force $hold | Out-Null
Get-ChildItem 'F:\Jester' -Force | Where-Object { $keep -notcontains $_.Name } | ForEach-Object {
  Move-Item -LiteralPath $_.FullName -Destination $hold -Force
}
Get-ChildItem 'F:\Jester' -Force | Select-Object -ExpandProperty Name
```

Expected: `.git` and `.superpowers`, nothing else.

- [ ] **Step 3: Copy the merged tree in**

```powershell
robocopy 'F:\_JesterMigration' 'F:\Jester' /E /MT:16 /R:2 /W:2 /NFL /NDL /NP `
  /XD '.venv' '__pycache__' '.mypy_cache' '.pytest_cache' '.ruff_cache' 'node_modules' `
  /XF '*.pyc' | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed (exit $LASTEXITCODE)" }
Get-ChildItem 'F:\Jester' -Force | Select-Object -ExpandProperty Name
```

Expected: `.git`, `.gitignore`, `archive`, `data`, `docs`, `frontend`, `jester`, `pipeline`, `prompts`, `pyproject.toml`, `README.md`, `Roadmap.md`, `tests`, `training`.

- [ ] **Step 4: Stage everything and handle the case-rename**

`core.ignorecase=true` means `Training` → `training` is invisible to git. Stage first, then check.

```bash
cd /f/Jester && git add -A && git ls-files training | head -3 && echo "---" && git ls-files | grep -c "^Training/" || echo "0 uppercase Training paths (good)"
```

Expected: lowercase `training/...` paths, and `0 uppercase Training paths (good)`.

If uppercase paths persist:

```bash
cd /f/Jester && git mv training training_tmp && git mv training_tmp training && git add -A && git ls-files training | head -3
```

- [ ] **Step 5: Inspect what is staged before committing**

```bash
cd /f/Jester && echo "staged files: $(git ls-files | wc -l)" && echo "deleted: $(git diff --cached --diff-filter=D --name-only | wc -l)" && echo "added: $(git diff --cached --diff-filter=A --name-only | wc -l)" && echo "--- leaks check ---" && git ls-files | grep -E "(^|/)(venv|\.venv|node_modules)/|\.pyc$|\.sqlite3$|^out/|^faiss/|^debug/|^logs/" | head || echo "no leaks"
```

Expected: **408 staged files**, **316 deleted**, `no leaks`.

316 is every path in `HEAD` — none survives into the new tree, because everything either moved (`npcgen/` → `archive/npcgen/`) or was dropped (`.idea/`, the 0-byte `python`).

Breakdown, so a wrong total is diagnosable rather than just wrong:

| Source | Files |
|---|---:|
| Stream A, excluding its `training/` | 274 |
| `training/` merged | 93 |
| `pipeline/` (18 runtime + 7 rules + `__init__.py` + `pdf.py`) | 27 |
| `archive/` (incl. `scraping/` 10 and `faiss/` 3) | 58 |
| `tests/` from Stream B | 2 |
| `docs/superpowers/` (spec + plan) | 2 |
| **Total** | **408** |

**GATE — if staged count is in the thousands, `.gitignore` is not taking effect. Run `git rm -r --cached .` then `git add -A` and re-check. Do not commit a 30,000-file tree.**

- [ ] **Step 6: No commit yet**

Task 9 commits, after a final review of the staged diff.

---

### Task 9: Commit, push, verify, and hand off the merge decision

**Files:**
- Modify: `F:\Jester` git history — one commit on `restructure/consolidate-streams`
- Modify: remote `origin` — new branch pushed

**Interfaces:**
- Consumes: staged tree from Task 8
- Produces: a pushed branch. The merge to `main` is the user's decision, not this plan's.

- [ ] **Step 1: Review the staged change summary**

```bash
cd /f/Jester && git diff --cached --stat | tail -20 && echo "=== top-level dirs staged ===" && git ls-files | awk -F/ '{print $1}' | sort | uniq -c | sort -rn
```

Expected top-level: `jester`, `frontend`, `training`, `archive`, `pipeline`, `tests`, `docs`, `prompts`, `data`, plus root files. No `npcgen`, no `Scraping`, no `Training` (uppercase), no `venv`.

- [ ] **Step 2: Commit**

```bash
cd /f/Jester && git commit -q -F - <<'MSG'
Restructure: consolidate platform and pipeline into one tree

Merge four unsynchronized folders into a single coherent repository.

- jester/    product platform, from F:\Jester Code (unchanged)
- pipeline/  data acquisition, from F:\Jester\Scraping
             runtime/ + rules/, plus pdf.py extracted from the
             BatchPDFCleaner CLI, which pipeline.py depends on
- training/  merged governance layer, 93 files. On all 9 collisions
             the newer stream (F:\Jester\Training) wins; Stream A's
             two colliding schemas are renamed rather than dropped:
               source_manifest  -> training_source.schema.json
               dataset_manifest -> training_dataset.schema.json
- archive/   npcgen, faiss, and the one-off scrapers

Also: rewrote 14 cross-package imports, stripped 82 UTF-8 BOMs, added
a .gitignore (there was none), declared previously-undeclared deps
(aiohttp, beautifulsoup4, trafilatura, pdfplumber), and dropped an
accidental copy of the Python 3.13 stdlib from out/.

Corpora stay outside the repo, located via JESTER_DATA_ROOT.

pipeline/ and training/ are exempted from mypy --strict for now;
tightening that is follow-up work.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
MSG
git log --oneline -3
```

Expected: the new commit, then `8ff8407 Needs cleaning`, then `0771db4 init commit` — history preserved.

- [ ] **Step 3: Verify a fresh clone works**

The real test: does the committed tree stand on its own, independent of anything left over in the working directory?

```bash
rm -rf /f/_JesterCloneTest && git clone -q --branch restructure/consolidate-streams /f/Jester /f/_JesterCloneTest && cd /f/_JesterCloneTest && echo "cloned files: $(git ls-files | wc -l)" && python -m venv .venv && ./.venv/Scripts/python.exe -m pip install -q -e ".[dev]" && JESTER_DATA_ROOT="F:\\JesterData" ./.venv/Scripts/python.exe -c "import jester, pipeline, training; print('imports OK')" && ./.venv/Scripts/python.exe -m pytest tests -q 2>&1 | tail -5
```

Expected: 408 files, `imports OK`, 31 modules passing.

**GATE — this is the last check before anything reaches GitHub.**

- [ ] **Step 4: Push the branch**

```bash
cd /f/Jester && git push -u origin restructure/consolidate-streams
```

Expected: branch created on `origin`. `main` is untouched — `origin/main` still points at `8ff8407`.

- [ ] **Step 5: Clean up the clone test**

```bash
rm -rf /f/_JesterCloneTest && echo "removed"
```

- [ ] **Step 6: Hand the merge decision to the user**

Report: branch pushed, gate results, staged counts. Then ask whether to merge to `main`, and offer the PR URL:

    https://github.com/BondVagabond/Jester/compare/main...restructure/consolidate-streams

**Do not merge or push to `main` without explicit approval.** Do not delete `F:\_JesterBackup_2026-08-08`, `F:\_JesterMigration`, `F:\Jester Code`, `F:\Jester Training data`, or `F:\JesterData` — the user decides when those go, after they are satisfied with the result.

---

## Post-migration follow-ups

Not part of this plan. Surface them when it lands:

1. **Type-check `pipeline/` and `training/`** — remove the `ignore_errors` override from `pyproject.toml` and fix what surfaces.
2. **Back up the corpora** — ~460 MB at `F:\JesterData` and `F:\Jester Training data` has no backup. This is the largest unmitigated risk in the project and the migration does not address it.
3. **Reconcile governance fields** — decide whether the 31 live acquisition manifests should carry Stream A's `content_hash`, `reviewed_by`, `policy_category`, and `task_family`, or whether the two schemas stay permanently separate.
4. **Delete the holding folders** once confident: `F:\_JesterMigration`, `F:\_JesterBackup_2026-08-08`.

## Rollback

At any point before Task 9 Step 4 (the push), the repo can be restored:

```powershell
Get-ChildItem 'F:\Jester' -Force | Where-Object { $_.Name -ne '.git' } |
  Remove-Item -Recurse -Force
robocopy 'F:\_JesterBackup_2026-08-08\repo-pre-restructure' 'F:\Jester' /E /MT:16 /NFL /NDL /NP
cd F:\Jester; git checkout main; git branch -D restructure/consolidate-streams
```

After the push, add `git push origin --delete restructure/consolidate-streams`. Since nothing lands on `main` until the user approves, `origin/main` stays at `8ff8407` throughout and no published history is ever rewritten.
