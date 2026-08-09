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
