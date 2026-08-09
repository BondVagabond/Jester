import os, json, glob, logging
from typing import List, Dict, Any
import numpy as np
import pandas as pd

from context_safety import is_index_artifact, sanitize_prompt_title

LOGFILE = os.environ.get("SEED_UTILS_LOGFILE", "jester_debug.log")

logger = logging.getLogger("seed_utils")
if not logger.handlers:
    _fh = logging.FileHandler(LOGFILE, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger.addHandler(_fh)
logger.setLevel(logging.INFO)

class SeedError(RuntimeError):
    #Raised when seed metadata is missing, malformed, or cannot be sampled.
    pass

class SeedStore:
    #
    # Loads all FAISS companion metadata (*.meta.jsonl) in store_path and provides sampling helpers.
    #
    # Typical use:
    #     world_store = SeedStore(index_path="F:\\Jester\\faiss", store_path="F:\\Jester\\faiss")
    #     worlds = world_store.sample_by_type("world", k=3)
    #
    #     rules_store = SeedStore(index_path="F:\\Jester\\faiss", store_path="F:\\Jester\\faiss")
    #     rules = rules_store.sample_by_type("rule", k=3)

    def __init__(self, index_path: str, store_path: str):
        self.index_path = index_path
        self.store_path = store_path
        self.meta_rows: List[Dict[str, Any]] = []
        self._load_all()

    def _discover_all_meta_paths(self) -> List[str]:
        #
        # Return a sorted list of all *.meta.jsonl files under store_path.
        #
        pattern = os.path.join(self.store_path, "*.meta.jsonl")
        paths = glob.glob(pattern)
        paths.sort()
        if not paths:
            raise SeedError(f"No metadata files found matching '*.meta.jsonl' under {self.store_path!r}")
        logger.info("Discovered %d meta files: %s", len(paths), [os.path.basename(p) for p in paths])
        return paths

    def _load_all(self) -> None:
        #
        # Load and validate ALL meta files we discover.
        # Required row keys: 'id', 'type', 'page_content'.
        #
        total = 0
        skipped_artifacts = 0
        for meta_path in self._discover_all_meta_paths():
            logger.info("Loading meta: %s", meta_path)
            with open(meta_path, "r", encoding="utf-8") as f:
                for ln, line in enumerate(f, start=1):
                    s = line.strip()
                    if not s:
                        continue
                    try:
                        row = json.loads(s)
                    except Exception as e:
                        raise SeedError(f"Invalid JSON at {meta_path}:{ln}: {e}")

                    missing = [k for k in ("id", "type", "page_content") if k not in row]
                    if missing:
                        raise SeedError(f"Meta row missing {missing} at {meta_path}:{ln}")

                    if is_index_artifact(row):
                        skipped_artifacts += 1
                        continue

                    sanitized_title = sanitize_prompt_title(row.get("title"))
                    if sanitized_title:
                        row["title"] = sanitized_title

                    self.meta_rows.append(row)
                    total += 1

        if not self.meta_rows:
            raise SeedError("No metadata rows loaded. Check your FAISS build.")
        logger.info(
            "Loaded %d metadata rows across %d file(s). Skipped %d artifact row(s).",
            total,
            len(self._discover_all_meta_paths()),
            skipped_artifacts,
        )

    def sample_by_type(self, typ: str, k: int) -> List[Dict[str, Any]]:
        #
        # Return up to k random rows where row['type'] == typ.
        #
        pool = [e for e in self.meta_rows if e.get("type") == typ]
        if not pool:
            have_types = sorted({e.get("type") for e in self.meta_rows})
            raise SeedError(f"No rows with type='{typ}'. Available types: {have_types}")
        import random
        random.shuffle(pool)
        return pool[:k]

    def sample_random(self, k: int) -> List[Dict[str, Any]]:
        #Return up to k random rows from all metadata.
        import random
        if not self.meta_rows:
            raise SeedError("No metadata to sample from.")
        pool = list(self.meta_rows)
        random.shuffle(pool)
        return pool[:k]
