
# Jester Watchdog

A comprehensive watchdog for your LLM data pipeline. It inspects generated JSONL records and surfaces issues like:
- Missing `id`/`type` seeds (seed integrity)
- Prompt near-duplicates (batching/context reuse)
- Output near-duplicates (mode collapse)
- Stock/safeguard opener detection
- Entropy and repetition ratios
- Debug flags (e.g., `debug.safeguard_used`)
- Cache prompt-hash bucket sizes
- Schema presence of required top-level fields

## Install / Use

This is a pure-Python package—no external deps.

```
python -m jester_watchdog.cli --in path/to/out.jsonl --out path/to/report/watchdog
```

Artifacts:
- `watchdog.json` — machine-readable results
- `watchdog.html` — human-friendly report with summaries

## Environment

- `JESTER_WATCHDOG_LOGFILE`: path to a log file (default `jester_watchdog.log`)

## Integrations

- Ensure your generators write a `debug` object with `safeguard_used` when a fallback is used.
- Make sure each record has: `seed`, `prompt`, `assistant`.

## Extending

Add custom checks to `checks.py` and include them in `AVAILABLE_CHECKS`.
