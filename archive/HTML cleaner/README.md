# HTML -> Cleaned JSONL Pipeline

This pipeline extracts, cleans, and scores local HTML, TXT, JSON, and JSONL files to keep transcript or session-report style content while rejecting obvious statblocks, build guides, and table-heavy reference pages.

## Quick start

```bash
python -m venv venv
# Windows: venv\Scripts\activate
# Linux/Mac: source venv/bin/activate

pip install -U pip
pip install -r requirements.txt

# Optional: NLTK data for named-entity features
python - << "PY"
import nltk
[nltk.download(x, quiet=True) for x in ["punkt","averaged_perceptron_tagger","maxent_ne_chunker","words"]]
PY

python html_pipeline.py --in-dir ./html --glob "**/*.html" --out ./out --save-text --save-clean --fit-gmm
```

## Outputs

- `out/_artifacts/reports.jsonl`: all results
- `out/_artifacts/reports_clean.jsonl`: accepted targets
- `out/_artifacts/reports_rejects.jsonl`: rejected docs with reasons
- optional sidecar `.txt` and `.clean.txt` files next to the output directory root

Each JSON record contains fields like:

```json
{
  "url": "...",
  "title": "...",
  "text": "...",
  "ts": 1700000000,
  "source_domain": "localfile",
  "is_target": true,
  "confidence": 0.83,
  "features": { "dialogue_lines": 12, "dice_hits": 5 },
  "bayes": { "bf10": 5.2, "conf_heur": 0.71, "conf_bayes": 0.84, "conf_gmm": 0.65 }
}
```

## Notes

- `html_pipeline.py` now looks for `keywords.json` relative to the `HTML cleaner` directory rather than the caller's current working directory.
- `html_cleaner.py` degrades gracefully when optional packages like `nltk` or `numpy` are unavailable.
- Artifact reports are written under `_artifacts` so they are easier to exclude from downstream indexing.

## Tips

- Use `--include` to narrow the run to likely transcript folders or filenames.
- `--fit-gmm` can improve confidence when you have a mixed corpus, but the heuristic and Bayes scorer still work without it.
