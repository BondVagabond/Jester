#
#
# query_faiss.py — Jester (updated)
# ----------------------------------
# Queries your built FAISS index + metadata. Falls back to simple keyword search
# when FAISS/embeddings aren't available.
#
# USAGE (PowerShell):
#   python query_faiss.py --store "F:\Jester\faiss" --which world --q "ancient forest druid" --k 5
#
# Outputs top-k matches to console; optionally write JSON lines.
# Env:
#   QUERY_FAISS_LOGFILE (default: jester_query_faiss.log)


import os, json, logging, argparse, re
from pathlib import Path
from typing import List, Dict, Any, Tuple

logger = logging.getLogger("query_faiss")
if not logger.handlers:
    _fh = logging.FileHandler(os.environ.get("QUERY_FAISS_LOGFILE", "jester_query_faiss.log"), encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(_fh)
logger.setLevel(logging.INFO)

def _maybe_import_embeddings(model_name: str):
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(model_name)
    except Exception as e:
        logger.warning("Embeddings unavailable: %s", e)
        return None

def _maybe_import_faiss():
    try:
        import faiss  # type: ignore
        return faiss
    except Exception as e:
        logger.warning("FAISS unavailable: %s", e)
        return None

def load_meta(meta_path: str) -> List[Dict[str,Any]]:
    rows = []
    with open(meta_path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, start=1):
            line = line.strip()
            if not line: continue
            row = json.loads(line)
            for k in ("id","type","page_content"):
                if k not in row:
                    raise RuntimeError(f"Meta row missing {k} at {meta_path}:{ln}")
            rows.append(row)
    return rows

def bm25_like(query: str, rows: List[Dict[str,Any]], topk:int=5) -> List[Tuple[int, float]]:
    # Very simple keyword score as a fallback
    q = re.findall(r"[A-Za-z0-9']+", query.lower())
    scores = []
    for idx, r in enumerate(rows):
        txt = (r.get("title","") + " " + r.get("page_content","")).lower()
        s = 0
        for t in q:
            s += txt.count(t)
        scores.append((idx, float(s)))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:topk]

def search(store: str, which: str, q: str, k:int=5, model_name="sentence-transformers/all-MiniLM-L6-v2"):
    store = Path(store)
    meta_path = store / f"{which}.meta.jsonl"
    ids_path  = store / f"{which}.ids.json"
    index_path = store / f"{which}.index.faiss"

    rows = load_meta(str(meta_path))
    results = []

    faiss = _maybe_import_faiss()
    model = _maybe_import_embeddings(model_name)

    if faiss and model and index_path.exists() and ids_path.exists():
        import numpy as np
        from sentence_transformers import util as st_util

        with open(ids_path, "r", encoding="utf-8") as f:
            idmap = json.load(f)["ids"]

        # Load index
        index = faiss.read_index(str(index_path))
        # Encode query
        q_vec = model.encode([q], convert_to_numpy=True, normalize_embeddings=True).astype("float32")
        # Search
        D, I = index.search(q_vec, k)
        for score, idx in zip(D[0], I[0]):
            if idx < 0 or idx >= len(idmap): 
                continue
            rid = idmap[idx]
            # locate row by id (could be optimized with dict)
            # build dict for quick lookup
            # one-time map
            # (acceptable for small/medium corpora)
            for row in rows:
                if row["id"] == rid:
                    results.append((row, float(score)))
                    break
    else:
        logger.info("Falling back to keyword scoring (no FAISS/embeddings).")
        for idx, score in bm25_like(q, rows, topk=k):
            results.append((rows[idx], score))

    return results[:k]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", required=True, help="Directory with *.meta.jsonl and optional *.index.faiss/*.ids.json")
    ap.add_argument("--which", choices=["rules","world"], required=True, help="Which corpus to query")
    ap.add_argument("--q", required=True, help="Query string")
    ap.add_argument("--k", type=int, default=5, help="Top K results")
    ap.add_argument("--out_jsonl", default=None, help="Optional output JSONL of results")
    ap.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2", help="Embedding model (if available)")
    args = ap.parse_args()

    res = search(store=args.store, which=args.which, q=args.q, k=args.k, model_name=args.model)
    for i, (row, score) in enumerate(res, 1):
        print(f"[{i}] score={score:.4f} id={row['id']} title={row.get('title','(untitled)')}")
        snippet = row.get("page_content","").replace("\n"," ")[:220]
        print(f"    {snippet}...")

    if args.out_jsonl:
        with open(args.out_jsonl, "w", encoding="utf-8") as f:
            for row, score in res:
                f.write(json.dumps({"score": score, **row}, ensure_ascii=False) + "\n")
        print(f"Wrote {args.out_jsonl}")

if __name__ == "__main__":
    main()
