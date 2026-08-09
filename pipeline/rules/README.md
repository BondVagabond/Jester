
# D&D Rules Cleaner/Parser/Extractor (Standalone)

Purpose-built for extracting *rules-oriented* text from D&D PDFs/HTML, normalizing it,
chunking it into AI-friendly segments, and exporting JSONL suitable for embedding or LLM ingestion.

### Output JSONL schema per line
```json
{
  "id": "<sha1>",
  "source": "/path/to/file.pdf",
  "page_from": 1,
  "page_to": 8,
  "heading": "Combat",
  "text": "...chunk...",
  "doc_type": "rules",
  "rules_score": 7.5
}
```
