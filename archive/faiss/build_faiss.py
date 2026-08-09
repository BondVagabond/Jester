

#build_faiss.py — Jester (updated)
#----------------------------------
#Builds metadata JSONL with stable id/type and (optionally) FAISS indexes for
#rules and world corpora. Safe to run in metadata-only mode if FAISS or the
#embedding model isn't available.

#USAGE (PowerShell one-line):
#  python build_faiss.py --rules_files "F:\Jester\cleaned\rules\**\*.jsonl" --world_files "F:\Jester\cleaned\world\**\*.jsonl" --out_dir "F:\Jester\faiss"

#USAGE (PowerShell multiline):
#  python "F:\Jester\updated\build_faiss.py" `
#    --rules_files "F:\Jester\cleaned\rules\**\*.jsonl" `
#    --world_files "F:\Jester\cleaned\world\**\*.jsonl" `
#    --out_dir "F:\Jester\faiss" `
#    --embed --model "sentence-transformers/all-MiniLM-L6-v2"

#Outputs (depending on what you pass in):
#  - rules.meta.jsonl, world.meta.jsonl
#  - rules.index.faiss, world.index.faiss (if --embed)
#  - rules.ids.json,   world.ids.json   (id → row mapping)

#Env:
#  BUILD_FAISS_LOGFILE (default: jester_build_faiss.log)


import os, json, glob, hashlib, logging, argparse, math
from pathlib import Path
from typing import List, Dict, Any, Iterable, Tuple

logger = logging.getLogger("build_faiss")
if not logger.handlers:
    _fh = logging.FileHandler(os.environ.get("BUILD_FAISS_LOGFILE", "jester_build_faiss.log"), encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(_fh)
logger.setLevel(logging.INFO)

def chunk_text(text: str, max_chars: int = 1200, overlap: int = 120) -> List[str]:
    text = text.replace("\r\n", "\n")
    parts = []
    i = 0
    n = len(text)
    while i < n:
        j = min(n, i + max_chars)
        parts.append(text[i:j])
        if j == n: break
        i = max(0, j - overlap)
    return parts

def infer_type_from_path(path: str) -> str:
    p = os.path.basename(path).lower()
    if "world" in p:
        return "world"
    if "rule" in p or "rules" in p:
        return "rule"
    logger.warning("Could not infer type from %r; defaulting to 'world'", path)
    return "world"

def doc_record(source: str, chunk_idx: int, title: str, page: str, extra: dict, type_hint: str) -> dict:
    sha = hashlib.sha1(f"{source}::{chunk_idx}".encode("utf-8")).hexdigest()[:16]
    rec = {
        "id": f"{type_hint}:{sha}",
        "type": type_hint,
        "title": title,
        "page_content": page,
        "source": source,
        "chunk_idx": chunk_idx,
        "doc_type": extra.get("doc_type", "txt"),
    }
    rec.update(extra)
    return rec

def iter_files(globs: List[str]) -> Iterable[str]:
    for g in globs or []:
        for fp in glob.glob(g, recursive=True):
            yield fp

def build_meta(files: List[str], out_meta_path: str, type_hint: str, max_chars:int=1200) -> int:
    Path(out_meta_path).parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with open(out_meta_path, "w", encoding="utf-8") as meta_f:
        for fp in files:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    txt = f.read()
            except Exception as e:
                logger.error("Skip unreadable file %s: %s", fp, e)
                continue
            chunks = chunk_text(txt, max_chars=max_chars, overlap=120)
            base = os.path.basename(fp)
            th = type_hint or infer_type_from_path(fp)
            for i, ch in enumerate(chunks):
                extra = {"doc_type": os.path.splitext(base)[1].lstrip("."), "meta_source_file": base}
                rec = doc_record(fp, i, title=base, page=ch, extra=extra, type_hint=th)
                meta_f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                count += 1
    logger.info("Wrote %d rows -> %s", count, out_meta_path)
    return count

# ---- Optional embedding & FAISS helpers ----

def _maybe_import_embeddings(model_name: str):
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(model_name)
    except Exception as e:
        logger.warning("Embeddings unavailable (install sentence-transformers). Running metadata-only. %s", e)
        return None

def _maybe_import_faiss():
    try:
        import faiss  # type: ignore
        return faiss
    except Exception as e:
        logger.warning("FAISS unavailable. Running metadata-only. %s", e)
        return None

def embed_corpus(model, texts: List[str], batch_size: int=64, normalize: bool=True):
    if model is None:
        return None
    import numpy as np
    embs = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        v = model.encode(batch, convert_to_numpy=True, normalize_embeddings=normalize)
        embs.append(v)
    if not embs:
        return np.zeros((0, 384), dtype="float32")
    return np.vstack(embs).astype("float32")

def write_faiss_index(index_path: str, ids_path: str, meta_path: str, model_name: str, batch: int=64, normalize: bool=True):
    faiss = _maybe_import_faiss()
    model = _maybe_import_embeddings(model_name)
    if faiss is None or model is None:
        logger.info("Skipping FAISS build for %s (missing deps).", meta_path)
        return False

    # Load metas
    texts, ids = [], []
    with open(meta_path, "r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            texts.append(row.get("page_content",""))
            ids.append(row["id"])
    if not texts:
        logger.warning("No rows to embed for %s", meta_path)
        return False

    vecs = embed_corpus(model, texts, batch_size=batch, normalize=normalize)
    import numpy as np
    d = vecs.shape[1]
    index = faiss.IndexFlatIP(d)
    index.add(vecs)
    faiss.write_index(index, index_path)
    with open(ids_path, "w", encoding="utf-8") as f:
        json.dump({"ids": ids}, f, ensure_ascii=False, indent=2)
    logger.info("Wrote FAISS index -> %s (%d vectors). Mapping -> %s", index_path, len(ids), ids_path)
    return True

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules_files", nargs="*", help="Glob(s) for rule files")
    ap.add_argument("--world_files", nargs="*", help="Glob(s) for world files")
    ap.add_argument("--out_dir", required=True, help="Output dir for meta and (optionally) FAISS index")
    ap.add_argument("--max_chars", type=int, default=1200, help="Chunk size in characters")
    ap.add_argument("--embed", action="store_true", help="Also build FAISS indexes (requires faiss + sentence-transformers)")
    ap.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2", help="Embedding model name")
    ap.add_argument("--batch", type=int, default=64, help="Embedding batch size")
    ap.add_argument("--no-normalize", action="store_true", help="Do not L2-normalize embeddings")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rules_files = list(iter_files(args.rules_files))
    world_files = list(iter_files(args.world_files))
    logger.info("Found %d rule files, %d world files", len(rules_files), len(world_files))

    # Build meta
    rules_meta = out_dir / "rules.meta.jsonl"
    world_meta = out_dir / "world.meta.jsonl"
    if rules_files:
        build_meta(rules_files, str(rules_meta), type_hint="rule", max_chars=args.max_chars)
    if world_files:
        build_meta(world_files, str(world_meta), type_hint="world", max_chars=args.max_chars)

    if args.embed:
        # Build FAISS indexes
        if rules_files:
            write_faiss_index(
                index_path=str(out_dir / "rules.index.faiss"),
                ids_path=str(out_dir / "rules.ids.json"),
                meta_path=str(rules_meta),
                model_name=args.model,
                batch=args.batch,
                normalize=not args.no_normalize
            )
        if world_files:
            write_faiss_index(
                index_path=str(out_dir / "world.index.faiss"),
                ids_path=str(out_dir / "world.ids.json"),
                meta_path=str(world_meta),
                model_name=args.model,
                batch=args.batch,
                normalize=not args.no_normalize
            )

    logger.info("Done. Meta at %s. Indexes (if requested) in %s", out_dir, out_dir)

if __name__ == "__main__":
    main()
