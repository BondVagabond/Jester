
from __future__ import annotations
import json, os
from pathlib import Path
from typing import Dict, Any, Iterable

class JSONLWriter:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.fp = path.open("w", encoding="utf-8")
    def write(self, rec: Dict[str, Any]):
        self.fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.fp.flush()
    def close(self):
        self.fp.close()
