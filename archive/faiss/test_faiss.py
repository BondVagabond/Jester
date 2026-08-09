# test_faiss.py
# Unified FAISS validator: unit tests + quick CLI query
# Run unit tests:  python test_faiss.py
# Quick query:     python test_faiss.py --index "F:\Jester\faiss\rules.index" --meta "F:\Jester\faiss\rules_texts.jsonl" --query "How do opportunity attacks work?"

import os
import sys
import json
import argparse
import unittest
from typing import List, Optional, Tuple

# ---- Optional deps (handled gracefully) ----
def _try_imports():
    mods = {}
    try:
        import faiss
        mods["faiss"] = faiss
    except Exception as e:
        mods["faiss_err"] = e

    try:
        import numpy as np
        mods["np"] = np
    except Exception as e:
        mods["np_err"] = e

    # Sentence Transformers is optional (only needed for semantic query tests)
    try:
        from sentence_transformers import SentenceTransformer
        mods["SentenceTransformer"] = SentenceTransformer
    except Exception as e:
        mods["SentenceTransformer_err"] = e

    return mods

MODS = _try_imports()


# ---- Utilities ----
def load_index(index_path: str):
    if "faiss" not in MODS:
        raise RuntimeError(f"faiss not available: {MODS.get('faiss_err')}")
    faiss = MODS["faiss"]
    if not os.path.exists(index_path):
        raise FileNotFoundError(f"Index not found: {index_path}")
    index = faiss.read_index(index_path)
    return index

def load_texts_from_jsonl(meta_path: str) -> List[str]:
    if not os.path.exists(meta_path):
        raise FileNotFoundError(f"Metadata not found: {meta_path}")
    texts = []
    with open(meta_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            obj = json.loads(line)
            # Expect "text" field, but fall back gracefully
            if "text" in obj:
                texts.append(obj["text"])
            elif "content" in obj:
                texts.append(obj["content"])
            else:
                texts.append(json.dumps(obj))  # last resort
    return texts

def embed_query(query: str, model_name: str):
    if "SentenceTransformer" not in MODS:
        raise RuntimeError(
            f"sentence-transformers not available. Install with: pip install sentence-transformers\n"
            f"Import error: {MODS.get('SentenceTransformer_err')}"
        )
    SentenceTransformer = MODS["SentenceTransformer"]
    model = SentenceTransformer(model_name)
    vec = model.encode([query])
    return vec.astype("float32")

def do_search(index, query_vec, k=5):
    return index.search(query_vec, k)

def try_int(x) -> Optional[int]:
    try:
        return int(x)
    except Exception:
        return None


# ---- Default paths (feel free to change) ----
DEFAULT_RULES_INDEX = r"F:\Jester\faiss\rules.index"
DEFAULT_RULES_META  = r"F:\Jester\faiss\rules_texts.jsonl"

DEFAULT_NARR_INDEX  = r"F:\Jester\faiss\narrator.index"
DEFAULT_NARR_META   = r"F:\Jester\faiss\narrator_texts.jsonl"

DEFAULT_MODEL = "all-MiniLM-L6-v2"  # small, fast, decent


# ---- Unit Tests ----
class TestFAISSCommon(unittest.TestCase):
    """Base test providing helpers; subclasses set self.index_path and self.meta_path"""
    index_path: Optional[str] = None
    meta_path: Optional[str] = None

    @classmethod
    def setUpClass(cls):
        cls.faiss = MODS.get("faiss")
        cls.np = MODS.get("np")
        if not cls.faiss or not cls.np:
            raise unittest.SkipTest("faiss or numpy not available in environment.")

        if cls.index_path is None:
            raise unittest.SkipTest("No index_path declared in subclass.")

        # Load index once per class
        cls.index = load_index(cls.index_path)

        # Metadata optional
        cls.texts = None
        if cls.meta_path and os.path.exists(cls.meta_path):
            try:
                cls.texts = load_texts_from_jsonl(cls.meta_path)
            except Exception:
                # Don’t fail the whole suite if metadata is malformed—just skip metadata-based tests
                cls.texts = None

    def test_index_is_trained_and_not_empty(self):
        self.assertTrue(self.index.is_trained, "Index is not trained.")
        self.assertGreater(self.index.ntotal, 0, "Index is empty (ntotal=0).")

    def test_random_vector_search_runs(self):
        d = self.index.d
        q = MODS["np"].random.random((1, d)).astype("float32")
        D, I = do_search(self.index, q, k=5)
        self.assertEqual(I.shape[1], 5, "Search did not return k results.")
        # ids may be -1 for IVF if empty; ensure at least something plausible if ntotal > 0
        self.assertTrue(any(i >= 0 for i in I[0]), "All returned IDs are -1.")

    def test_metadata_alignment_if_available(self):
        if self.texts is None:
            self.skipTest("No metadata loaded; skipping alignment test.")
        # Minimal sanity: top id is within text range
        d = self.index.d
        q = MODS["np"].random.random((1, d)).astype("float32")
        D, I = do_search(self.index, q, k=1)
        top_id = try_int(I[0][0])
        self.assertIsNotNone(top_id, "Top ID is not an integer.")
        self.assertGreaterEqual(top_id, 0, "Top ID < 0.")
        self.assertLess(top_id, len(self.texts), "Top ID >= number of metadata texts.")

    def test_semantic_search_if_model_available(self):
        if "SentenceTransformer" not in MODS:
            self.skipTest("sentence-transformers not available; skipping semantic test.")
        if self.texts is None:
            self.skipTest("No metadata; semantic test needs text mapping.")

        # A generic D&D-ish query; change per index subclass
        query = getattr(self, "sample_query", "rules")
        vec = embed_query(query, DEFAULT_MODEL)
        D, I = do_search(self.index, vec, k=3)

        # Ensure we got some valid IDs and can print corresponding texts
        valid = [i for i in I[0] if 0 <= i < len(self.texts)]
        self.assertTrue(len(valid) > 0, "Semantic search returned no valid IDs.")


class TestRulesIndex(TestFAISSCommon):
    index_path = DEFAULT_RULES_INDEX
    meta_path = DEFAULT_RULES_META
    sample_query = "How do opportunity attacks work in D&D?"


class TestNarratorIndex(TestFAISSCommon):
    index_path = DEFAULT_NARR_INDEX
    meta_path = DEFAULT_NARR_META
    sample_query = "Describe a spooky forest clearing at midnight."


# ---- CLI for ad-hoc querying ----
def run_cli(index_path: str,
            meta_path: Optional[str],
            query: str,
            model_name: str,
            k: int):
    index = load_index(index_path)

    texts = None
    if meta_path and os.path.exists(meta_path):
        try:
            texts = load_texts_from_jsonl(meta_path)
        except Exception as e:
            print(f"[warn] Failed to load metadata {meta_path}: {e}")

    if query.strip():
        if "SentenceTransformer" in MODS:
            vec = embed_query(query, model_name)
        else:
            # Fall back to random vector (worse, but lets you check pipeline quickly)
            print("[warn] sentence-transformers missing; using a random vector instead.")
            d = index.d
            vec = MODS["np"].random.random((1, d)).astype("float32")
        D, I = do_search(index, vec, k=k)
        print(f"\nTop {k} results for: {query!r}")
        for rank, (dist, idx) in enumerate(zip(D[0], I[0]), start=1):
            print(f"\n#{rank}  id={idx}  distance={dist:.6f}")
            if texts and 0 <= idx < len(texts):
                snippet = texts[idx]
                if len(snippet) > 600:
                    snippet = snippet[:600] + "..."
                print(snippet)
    else:
        print("No --query provided; nothing to search.")


def parse_args(argv: List[str]) -> Tuple[argparse.Namespace, bool]:
    parser = argparse.ArgumentParser(
        description="FAISS unit tests + quick query CLI. "
                    "Run without flags to execute unit tests. "
                    "Provide --query to run a one-off semantic search."
    )
    parser.add_argument("--index", type=str, help="Path to FAISS index file")
    parser.add_argument("--meta", type=str, help="Path to metadata JSONL (ID→text)")
    parser.add_argument("--query", type=str, default="", help="Query text for quick search")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="SentenceTransformer model name")
    parser.add_argument("-k", type=int, default=5, help="Top-K neighbors to retrieve")

    args, unknown = parser.parse_known_args(argv)

    # If any CLI search flags are present, we run in CLI mode; otherwise run unit tests.
    cli_mode = bool(args.query or args.index or args.meta)
    return args, cli_mode


if __name__ == "__main__":
    args, cli_mode = parse_args(sys.argv[1:])

    if cli_mode:
        # Resolve index/meta with reasonable defaults if only one is provided
        index_path = args.index or (DEFAULT_RULES_INDEX if os.path.exists(DEFAULT_RULES_INDEX) else DEFAULT_NARR_INDEX)
        meta_path = args.meta or (DEFAULT_RULES_META if os.path.exists(DEFAULT_RULES_META) else DEFAULT_NARR_META)
        run_cli(index_path, meta_path, args.query, args.model, args.k)
    else:
        # Run unittest test suite
        unittest.main(argv=[sys.argv[0]], verbosity=2)
