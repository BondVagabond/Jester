\
import argparse, json, os, sys, math, re
from typing import List, Dict, Any
import numpy as np
import pandas as pd
import faiss
from sentence_transformers import SentenceTransformer

# ===== Runtime environment integrity check =====
def _assert_env_integrity(require_featuretools: bool = False):
    import importlib, sys
    required = ["numpy", "pandas", "sklearn", "nltk"]
    if require_featuretools:
        required.append("featuretools")
    missing = []
    for mod in required:
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(mod)
    if missing:
        raise RuntimeError(
            "Missing required dependencies: " + ", ".join(missing) +
            ". Install via `pip install -r requirements.txt`."
        )
    # NLTK resource check
    import nltk
    needed = [
        ("tokenizers/punkt", "punkt"),
        ("taggers/averaged_perceptron_tagger", "averaged_perceptron_tagger"),
        ("chunkers/maxent_ne_chunker", "maxent_ne_chunker"),
        ("corpora/words", "words"),
    ]
    for path, res in needed:
        try:
            nltk.data.find(path)
        except LookupError:
            raise RuntimeError(
                f"Missing NLTK resource: {res}. Run the NLTK downloader before executing."
            )

_assert_env_integrity(require_featuretools=False)


# Optional deps
try:
    import nltk
    from nltk import ne_chunk, pos_tag, word_tokenize
    from nltk.tree import Tree as NltkTree
except Exception:
    nltk = None
    ne_chunk = pos_tag = word_tokenize = NltkTree = None

def read_meta(path: str) -> List[Dict[str, Any]]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows

def _query_entities(q: str) -> List[str]:
    if nltk is None:
        return []
    try:
        toks = word_tokenize(q)
        tags = pos_tag(toks)
        chunks = ne_chunk(tags, binary=False)
        ents = []
        for c in chunks:
            if isinstance(c, NltkTree):
                ents.append(" ".join(tok for tok, _ in c.leaves()))
        return ents
    except Exception:
        return []

def _bayes_rerank(base_scores: np.ndarray, docs: List[Dict[str, Any]], query_ents: List[str]) -> np.ndarray:
    \"\"\"Bayesian reweighting: combine vector score with an entity-match likelihood.
    We model p(relevant|score, ents) ∝ exp(alpha*score) * (1 + beta * entity_overlap)
    \"\"\"
    alpha, beta = 1.0, 0.6
    out = base_scores.copy()
    qset = {e.lower() for e in query_ents}
    for i, d in enumerate(docs):
        ents = [e.split(':', 1)[-1].lower() for e in d.get("ner", [])]
        overlap = len(qset.intersection(set(ents)))
        out[i] = math.exp(alpha * base_scores[i]) * (1.0 + beta * overlap)
    # convert back to a ranking score (log)
    return np.log(out + 1e-9)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", required=True, help="Path to .faiss index")
    ap.add_argument("--meta", required=True, help="Path to .meta.jsonl")
    ap.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--out-csv", default=None, help="If set, write reranked results to this CSV path")
    ap.add_argument("query", nargs="+", help="Search query string")
    args = ap.parse_args()
    query = " ".join(args.query)

    # load
    index = faiss.read_index(args.index)
    meta = read_meta(args.meta)
    model = SentenceTransformer(args.model)

    # encode & search
    q = model.encode([query], convert_to_numpy=True)
    faiss.normalize_L2(q)
    scores, idxs = index.search(q, args.k * 4)  # search a bit deeper before re-rank

    # build docs list
    docs = [meta[idx] for idx in idxs[0]]
    base_scores = scores[0]

    # NER-aware Bayesian reranking
    qents = _query_entities(query)
    reranked = _bayes_rerank(base_scores, docs, qents)
    order = np.argsort(-reranked)[: args.k]

    print(f"\\nQuery: {query}")
    print("="*80)
    for rank, i in enumerate(order, start=1):
        score = reranked[i]
        doc = docs[i]
        print(f"[{rank}] score={score:.4f}  source={doc.get('source')}  title={doc.get('title')}  chunk={doc.get('chunk_idx')}")
        print(doc.get("page_content", "")[:600].strip())
        if doc.get("ner"):
            print("  NER:", ", ".join(doc["ner"][:6]))
        print("-"*80)

if __name__ == "__main__":
    main()
