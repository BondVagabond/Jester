# config.py
"""
Centralized configuration with tiny "config object" + environment overrides.
Back-compat: module-level constants remain available and are populated from CONFIG.

Override any mapped value using environment variables (see ENV_OVERRIDES).
Example:
  DM_MIN_WORDS=150 DM_OUTPUT_DIR=./out python pipeline.py
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import os
import re
from typing import Dict, Any


# ----------------------------
# 1) Defaults (sensible, same behavior as before)
# ----------------------------

_DEFAULTS: Dict[str, Any] = {
    # I/O
    "DEFAULT_INPUT_DIR": Path("."),
    "DEFAULT_INPUT_GLOB": "**/*.pdf",
    "DEFAULT_OUTPUT_DIR": Path("./cleaned"),

    # Chunking
    "MIN_WORDS": 120,
    "MAX_WORDS": 600,

    # Output schema/format
    "SCHEMA_VERSION": "1.0",
    "STRICT_JSONL": True,   # keep 1 JSON object per line by default
    "WRITE_PRETTY": False,  # human formatting OFF by default

    # ---- Random-encounter block handling (NEW) ----
    # Keep entire random-encounter sections intact by default (non-breaking).
    "EXTRACT_RANDOM_ENCOUNTERS": True,
    "RANDOM_ENCOUNTER_KEY": "random_encounters",
    # canonical dice pattern like "1d6", "2d8+1"
    "DICE_PATTERN": r"\b\d+d\d+(?:\+\d+)?\b",

    # ---- Text normalization policy (NEW) ----
    "NORMALIZE": {
        "unicode_form": "NFKC",
        "collapse_spaces": True,
        "strip_headers_footers": True,
        "keep_lists_as_lines": True,
    },

    # ---- Logging (NEW) ----
    "LOG_LEVEL": "INFO",    # DEBUG | INFO | WARNING | ERROR
    "LOG_FILE": "",         # empty => stdout only
    "LOG_JSON": False,      # plain text logs by default
}


# ----------------------------
# 2) Env overrides (single source of truth)
# ----------------------------
# Map environment variable -> config field name
ENV_OVERRIDES: Dict[str, str] = {
    "DM_INPUT_DIR": "DEFAULT_INPUT_DIR",
    "DM_INPUT_GLOB": "DEFAULT_INPUT_GLOB",
    "DM_OUTPUT_DIR": "DEFAULT_OUTPUT_DIR",
    "DM_MIN_WORDS": "MIN_WORDS",
    "DM_MAX_WORDS": "MAX_WORDS",
    "DM_SCHEMA_VERSION": "SCHEMA_VERSION",
    "DM_STRICT_JSONL": "STRICT_JSONL",
    "DM_WRITE_PRETTY": "WRITE_PRETTY",
    "DM_LOG_LEVEL": "LOG_LEVEL",
    "DM_LOG_FILE": "LOG_FILE",
    "DM_LOG_JSON": "LOG_JSON",
}


# ----------------------------
# 3) Tiny config object
# ----------------------------

@dataclass
class Config:
    # I/O
    DEFAULT_INPUT_DIR: Path
    DEFAULT_INPUT_GLOB: str
    DEFAULT_OUTPUT_DIR: Path

    # Chunking
    MIN_WORDS: int
    MAX_WORDS: int

    # Output schema/format
    SCHEMA_VERSION: str
    STRICT_JSONL: bool
    WRITE_PRETTY: bool

    # Random-encounter handling
    EXTRACT_RANDOM_ENCOUNTERS: bool
    RANDOM_ENCOUNTER_KEY: str
    DICE_PATTERN: str

    # Text normalization policy
    NORMALIZE: Dict[str, Any]

    # Logging
    LOG_LEVEL: str
    LOG_FILE: str
    LOG_JSON: bool

    # Convenience: compiled regex (not env-overridable, derived from DICE_PATTERN)
    def dice_regex(self):
        return re.compile(self.DICE_PATTERN, flags=re.IGNORECASE)


def _coerce(field_name: str, value: str) -> Any:
    """
    Coerce env string to the correct type based on the default value's type.
    Paths -> Path; bools accept 1/0/true/false; ints parsed; dicts unchanged.
    """
    default_value = _DEFAULTS[field_name]

    # Path
    if isinstance(default_value, Path):
        return Path(value)

    # Bool
    if isinstance(default_value, bool):
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    # Int
    if isinstance(default_value, int):
        try:
            return int(value)
        except ValueError:
            return default_value

    # Dict (leave as-is unless you add a parser later)
    if isinstance(default_value, dict):
        return default_value

    # Fallback: string
    return value


def _apply_env_overrides(base: Dict[str, Any]) -> Dict[str, Any]:
    updated = dict(base)
    for env_var, field_name in ENV_OVERRIDES.items():
        raw = os.environ.get(env_var)
        if raw is None:
            continue
        if field_name not in updated:
            continue  # ignore unknown mapping
        updated[field_name] = _coerce(field_name, raw)
    return updated


def _build_config() -> Config:
    merged = _apply_env_overrides(_DEFAULTS)
    return Config(
        DEFAULT_INPUT_DIR=merged["DEFAULT_INPUT_DIR"],
        DEFAULT_INPUT_GLOB=merged["DEFAULT_INPUT_GLOB"],
        DEFAULT_OUTPUT_DIR=merged["DEFAULT_OUTPUT_DIR"],
        MIN_WORDS=merged["MIN_WORDS"],
        MAX_WORDS=merged["MAX_WORDS"],
        SCHEMA_VERSION=merged["SCHEMA_VERSION"],
        STRICT_JSONL=merged["STRICT_JSONL"],
        WRITE_PRETTY=merged["WRITE_PRETTY"],
        EXTRACT_RANDOM_ENCOUNTERS=merged["EXTRACT_RANDOM_ENCOUNTERS"],
        RANDOM_ENCOUNTER_KEY=merged["RANDOM_ENCOUNTER_KEY"],
        DICE_PATTERN=merged["DICE_PATTERN"],
        NORMALIZE=merged["NORMALIZE"],
        LOG_LEVEL=merged["LOG_LEVEL"],
        LOG_FILE=merged["LOG_FILE"],
        LOG_JSON=merged["LOG_JSON"],
    )


# The live config object (constructed once at import).
CONFIG: Config = _build_config()


# ----------------------------
# 4) Back-compat module-level constants
# ----------------------------
# Existing code can keep importing these without change.
DEFAULT_INPUT_DIR: Path = CONFIG.DEFAULT_INPUT_DIR
DEFAULT_INPUT_GLOB: str = CONFIG.DEFAULT_INPUT_GLOB
DEFAULT_OUTPUT_DIR: Path = CONFIG.DEFAULT_OUTPUT_DIR

MIN_WORDS: int = CONFIG.MIN_WORDS
MAX_WORDS: int = CONFIG.MAX_WORDS

SCHEMA_VERSION: str = CONFIG.SCHEMA_VERSION
STRICT_JSONL: bool = CONFIG.STRICT_JSONL
WRITE_PRETTY: bool = CONFIG.WRITE_PRETTY

EXTRACT_RANDOM_ENCOUNTERS: bool = CONFIG.EXTRACT_RANDOM_ENCOUNTERS
RANDOM_ENCOUNTER_KEY: str = CONFIG.RANDOM_ENCOUNTER_KEY
DICE_PATTERN: str = CONFIG.DICE_PATTERN
DICE_REGEX = CONFIG.dice_regex()  # convenience

NORMALIZE: Dict[str, Any] = CONFIG.NORMALIZE

LOG_LEVEL: str = CONFIG.LOG_LEVEL
LOG_FILE: str = CONFIG.LOG_FILE
LOG_JSON: bool = CONFIG.LOG_JSON


# ----------------------------
# 5) Utilities
# ----------------------------
def as_dict() -> Dict[str, Any]:
    """Return the active CONFIG as a plain dict (paths rendered as strings)."""
    d = asdict(CONFIG)
    d["DEFAULT_INPUT_DIR"] = str(d["DEFAULT_INPUT_DIR"])
    d["DEFAULT_OUTPUT_DIR"] = str(d["DEFAULT_OUTPUT_DIR"])
    return d


def refresh_from_env() -> None:
    """
    Re-read environment variables and refresh CONFIG and module-level constants.
    Useful for GUIs that let users change env vars at runtime.
    """
    global CONFIG
    CONFIG = _build_config()

    global DEFAULT_INPUT_DIR, DEFAULT_INPUT_GLOB, DEFAULT_OUTPUT_DIR
    DEFAULT_INPUT_DIR = CONFIG.DEFAULT_INPUT_DIR
    DEFAULT_INPUT_GLOB = CONFIG.DEFAULT_INPUT_GLOB
    DEFAULT_OUTPUT_DIR = CONFIG.DEFAULT_OUTPUT_DIR

    global MIN_WORDS, MAX_WORDS
    MIN_WORDS = CONFIG.MIN_WORDS
    MAX_WORDS = CONFIG.MAX_WORDS

    global SCHEMA_VERSION, STRICT_JSONL, WRITE_PRETTY
    SCHEMA_VERSION = CONFIG.SCHEMA_VERSION
    STRICT_JSONL = CONFIG.STRICT_JSONL
    WRITE_PRETTY = CONFIG.WRITE_PRETTY

    global EXTRACT_RANDOM_ENCOUNTERS, RANDOM_ENCOUNTER_KEY, DICE_PATTERN, DICE_REGEX
    EXTRACT_RANDOM_ENCOUNTERS = CONFIG.EXTRACT_RANDOM_ENCOUNTERS
    RANDOM_ENCOUNTER_KEY = CONFIG.RANDOM_ENCOUNTER_KEY
    DICE_PATTERN = CONFIG.DICE_PATTERN
    DICE_REGEX = CONFIG.dice_regex()

    global NORMALIZE
    NORMALIZE = CONFIG.NORMALIZE

    global LOG_LEVEL, LOG_FILE, LOG_JSON
    LOG_LEVEL = CONFIG.LOG_LEVEL
    LOG_FILE = CONFIG.LOG_FILE
    LOG_JSON = CONFIG.LOG_JSON


def setup_logging() -> None:
    """
    Configure root logger according to config. Idempotent.
    LOG_LEVEL/LOG_FILE/LOG_JSON are taken from the active CONFIG.
    """
    import logging
    import logging.handlers
    import json as _json

    if getattr(setup_logging, "_configured", False):
        return

    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    logging.root.handlers[:] = []  # reset for clean re-config
    logging.root.setLevel(level)

    fmt = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"

    if LOG_JSON:
        class JsonFormatter(logging.Formatter):
            def format(self, record):
                payload = {
                    "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
                    "level": record.levelname,
                    "logger": record.name,
                    "msg": record.getMessage(),
                }
                if record.exc_info:
                    payload["exc_info"] = self.formatException(record.exc_info)
                return _json.dumps(payload, ensure_ascii=False)
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")

    handlers = []
    if LOG_FILE:
        fh = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
        )
        fh.setFormatter(formatter)
        handlers.append(fh)

    sh = logging.StreamHandler()
    sh.setFormatter(formatter)
    handlers.append(sh)

    for h in handlers:
        logging.root.addHandler(h)

    setup_logging._configured = True
