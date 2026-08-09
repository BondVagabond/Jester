
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
DnD Statblock Toolkit V3 (single-file)
=====================================

- Extract text from PDFs (prefers native text; OCR optional fallback)
- Normalize text (Unicode NFKC, ligatures, zero-widths, NBSP, soft hyphens)
- Robust statblock parser for Monsters, NPCs, PCs (works on character sheets)
- Batch ingest a folder into ONE JSON file
- Probe a single file (debug which extractor/signals matched)
- Simple Tkinter GUI with Start/Stop and live logs
- Rich logging (per-file extractor char counts, signals, snippets)
- Debug dump to save normalized raw text

Usage
-----
CLI subcommands:
  - probe  : Inspect a single file
  - ingest : Ingest a folder into one JSON/YAML
  - gui    : Launch a simple GUI

Examples
--------
Probe:
  python dnd_statblock_toolkit_v3.py probe "D:\\dnd5E\\Lore\\Playable_Characters\\Dragonborn Sorcerer 1.pdf"

Ingest:
  python dnd_statblock_toolkit_v3.py ingest "D:\\dnd5E\\Lore\\Playable_Characters" \
    --pattern "*.pdf,*.txt" --recursive \
    --output "D:\\out\\statblocks.json" \
    --log-file "D:\\out\\statlogs.log" --log-level DEBUG \
    --debug-dump "D:\\out\\debug_text" \
    --min-signals 0 --no-skip-on-zero

GUI:
  python dnd_statblock_toolkit_v3.py gui
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import threading
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ----------------------- Optional deps, guarded imports -----------------------
try:
    import yaml  # PyYAML for optional YAML output
except Exception:
    yaml = None

# PDF extractors (all optional — we try what's available)
_have_pdfplumber = False
_have_pdfminer = False
_have_pytesseract = False
_have_poppler = False  # for pdftotext

try:
    import pdfplumber  # type: ignore
    _have_pdfplumber = True
except Exception:
    pass

try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text  # type: ignore
    _have_pdfminer = True
except Exception:
    pass

try:
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore
    _have_pytesseract = True
except Exception:
    pass

# Check for pdftotext (Poppler)
import shutil
if shutil.which("pdftotext"):
    _have_poppler = True

# ------------------------------ Logging helpers -------------------------------
LOGGER_NAME = "statblock"
log = logging.getLogger(LOGGER_NAME)

def setup_logging(level="INFO", log_file: Optional[str] = None):
    level_num = getattr(logging, str(level).upper(), logging.INFO)
    log.setLevel(level_num)
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    # Clear existing handlers to avoid duplicates
    for h in list(log.handlers):
        log.removeHandler(h)

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(level_num)
    sh.setFormatter(fmt)
    log.addHandler(sh)

    if log_file:
        # Ensure parent exists
        _ensure_parent_dir(log_file)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(level_num)
        fh.setFormatter(fmt)
        log.addHandler(fh)

# ------------------------------ Path utilities --------------------------------
def _ensure_parent_dir(path_str: Optional[str]):
    if not path_str:
        return
    p = Path(path_str)
    parent = p if p.suffix == "" else p.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        log.warning("Could not create parent dir for %s: %s", path_str, e)

def _glob_folder(folder: str, pattern: str, recursive: bool) -> List[str]:
    patterns = [p.strip() for p in (pattern or "*").split(",") if p.strip()]
    files: List[str] = []
    for pat in patterns:
        if recursive:
            files.extend([str(p) for p in Path(folder).rglob(pat)])
        else:
            files.extend([str(p) for p in Path(folder).glob(pat)])
    # Dedup and keep only files
    uniq = []
    seen = set()
    for f in files:
        if f not in seen and Path(f).is_file():
            uniq.append(f); seen.add(f)
    return uniq

# ------------------------- Text normalization (v2.1) --------------------------
LIGATURES = {
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl",
    "\u00ae": "(R)",
}

def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    for k, v in LIGATURES.items():
        s = s.replace(k, v)
    s = s.replace("\u00ad", "")     # soft hyphen
    s = s.replace("\u00a0", " ")    # NBSP
    s = s.replace("\u200b", "")     # ZWSP
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    s = s.replace("\u2018", "'").replace("\u2019", "'")
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    # Strip odd controls but keep newlines/tabs
    s = "".join(ch if (ch >= " " or ch in "\n\t") else " " for ch in s)
    # Compact excessive spaces
    s = re.sub(r"[ \t]+", " ", s)
    return s

# ------------------------------- Extractors -----------------------------------
def _read_with_pdfplumber(path: str) -> str:
    if not _have_pdfplumber:
        return ""
    try:
        import pdfplumber
        txt_parts = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                txt_parts.append(page.extract_text() or "")
        return "\n".join(txt_parts)
    except Exception as e:
        log.debug("pdfplumber failed on %s: %s", path, e)
        return ""

def _read_with_pdfminer(path: str) -> str:
    if not _have_pdfminer:
        return ""
    try:
        return pdfminer_extract_text(path) or ""
    except Exception as e:
        log.debug("pdfminer failed on %s: %s", path, e)
        return ""

def _read_with_pdftotext(path: str) -> str:
    if not _have_poppler:
        return ""
    try:
        import subprocess, tempfile
        with tempfile.TemporaryDirectory() as td:
            out_txt = Path(td, "out.txt")
            cmd = ["pdftotext", "-layout", path, str(out_txt)]
            subprocess.run(cmd, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if out_txt.exists():
                return out_txt.read_text(encoding="utf-8", errors="ignore")
            return ""
    except Exception as e:
        log.debug("pdftotext failed on %s: %s", path, e)
        return ""

def _read_with_ocr(path: str, dpi: int = 300, psm: int = 3, oem: Optional[int] = None) -> str:
    if not _have_pytesseract:
        return ""
    try:
        # Render each page to image via pdfplumber (if available) or fallback to PIL-convert
        texts = []
        if _have_pdfplumber:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    img = page.to_image(resolution=dpi).original
                    txt = pytesseract.image_to_string(img, config=f"--psm {psm}" + ("" if oem is None else f" --oem {oem}"))
                    texts.append(txt or "")
        else:
            # Very simple fallback: rely on pdftotext images doesn't apply; skip
            return ""
        return "\n".join(texts)
    except Exception as e:
        log.debug("OCR failed on %s: %s", path, e)
        return ""

def extract_text_safely(path: str, force_ocr: bool=False, ocr_psm: int=3, ocr_oem: Optional[int]=None, ocr_dpi: int=300) -> Tuple[str, Dict[str,int]]:
    counts: Dict[str,int] = {}
    text: str = ""

    if not force_ocr:
        t1 = _read_with_pdfplumber(path); counts["pdfplumber"] = len(t1)
        t2 = _read_with_pdfminer(path);   counts["pdfminer"]   = len(t2)
        t3 = _read_with_pdftotext(path);  counts["pdftotext"]  = len(t3)
        # Choose the longest
        text = max((t1, t2, t3), key=len, default="")
    if (not text) and _have_pytesseract:
        t4 = _read_with_ocr(path, dpi=ocr_dpi, psm=ocr_psm, oem=ocr_oem); counts["ocr"] = len(t4)
        text = t4

    norm = normalize_text(text)
    log.debug("extract_text: %s counts=%s chosen_len=%d", path, counts, len(norm))
    return norm, counts

# ------------------------------ Signal detection ------------------------------
SIG_PATTERNS = [
    r"\barmor\s*class\b",
    r"\bhit\s*points?\b",
    r"\bspeed\b",
    r"\bsaving\s*throws?\b",
    r"\bskills?\b",
    r"\bsenses?\b",
    r"\blanguages?\b",
    r"\bchallenge\b|\blevel\b",
    r"\bspellcasting\b",
    # Ability quick hits (compact)
    r"\bstr\b\s*\d{1,2}", r"\bdex\b\s*\d{1,2}", r"\bcon\b\s*\d{1,2}",
    r"\bint\b\s*\d{1,2}", r"\bwis\b\s*\d{1,2}", r"\bcha\b\s*\d{1,2}",
    # OCR noisy variants with spaces between letters: A r m o r  C l a s s
    r"a\s*r\s*m\s*o\s*r\s*c\s*l\s*a\s*s\s*s",
    r"h\s*i\s*t\s*p\s*o\s*i\s*n\s*t\s*s?",
    r"s\s*p\s*e\s*e\s*d",
]
SIG_REGEXES = [re.compile(p, re.I) for p in SIG_PATTERNS]

def count_signals(text: str) -> int:
    hits = sum(1 for rx in SIG_REGEXES if rx.search(text))
    return hits

# ---------------------------- Parser (V3 tolerant) ----------------------------
ABILITY_KEYS = ["str","dex","con","int","wis","cha"]

def _search(pattern, text, flags=re.I|re.M):
    try:
        return re.search(pattern, text, flags)
    except re.error as e:
        log.debug("Regex error %r: %s", pattern, e)
        return None

def _findall(pattern, text, flags=re.I|re.M):
    try:
        return re.findall(pattern, text, flags) or []
    except re.error as e:
        log.debug("Regex error %r: %s", pattern, e)
        return []

def _group1(m): return m.group(1) if m and m.group(1) is not None else None

def _split_commas(v: Optional[str]) -> List[str]:
    if not v: return []
    return [p.strip() for p in re.split(r",|;", v) if p and p.strip()]

def collect_damage_profile(text: str) -> Dict[str, List[str]]:
    def collect(label_regex):
        m = _search(rf"(?:^{label_regex}\s*:?\s*|\b{label_regex}\s*:?\s*)([^\n]+)", text)
        vals = [s.strip().lower() for s in _split_commas(_group1(m))]
        return vals
    return {
        "resistances": collect(r"damage\s*resistances|resistances"),
        "immunities": collect(r"damage\s*immunities|immunities"),
        "vulnerabilities": collect(r"damage\s*vulnerabilities|vulnerabilities"),
        "condition_immunities": collect(r"condition\s*immunities"),
    }

def parse_actions_section(text: str, header_regex: str) -> List[str]:
    hdr = _search(rf"^\s*(?:{header_regex})\s*:?[\r\n]+", text)
    if not hdr:
        return []
    start = hdr.end()
    tail = text[start:]
    stop = _search(r"^\s*[A-Z][A-Z \-/]{2,}\s*:?[\r\n]+", tail)
    chunk = tail[:stop.start()] if stop else tail
    if not chunk:
        return []
    entries = re.split(r"\n(?=[A-Z][^\n]{0,60}?\.|\*\*|—|–)|;\s*(?=[A-Z])", chunk)
    return [e.strip() for e in entries if e and e.strip()]

def parse_character_sheet_style(text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    ac = _group1(_search(r"\bArmor\s*Class\s+(\d+)", text))
    if ac: out["ac"] = int(ac)
    hp = _group1(_search(r"\bHit\s*Points?\s+(\d+)", text))
    if hp: out["hp"] = int(hp)
    speed = _group1(_search(r"\bSpeed\s+([^\n]+)", text))
    if speed: out["speed"] = speed.strip()

    abilities: Dict[str,int] = {}
    for ab in ABILITY_KEYS:
        m = _search(rf"\b{ab.upper()}\s+(\d+)\s*(?:\([+-]?\d+\))?", text)
        if m:
            abilities[ab] = int(m.group(1))
    if abilities:
        out["abilities"] = abilities

    saves = _group1(_search(r"\bSaving\s*Throws?\s*([^\n]+)", text))
    if saves:
        out["saving_throws"] = [s.strip() for s in re.split(r",|;", saves) if s.strip()]

    skills = _group1(_search(r"\bSkills?\s*([^\n]+)", text))
    if skills:
        out["skills"] = [s.strip() for s in re.split(r",|;", skills) if s.strip()]

    senses = _group1(_search(r"\bSenses?\s*([^\n]+)", text))
    if senses:
        out["senses"] = senses.strip()

    langs = _group1(_search(r"\bLanguages?\s*([^\n]+)", text))
    if langs:
        out["languages"] = [s.strip() for s in re.split(r",|;", langs) if s.strip()]

    # Attacks
    attacks = _findall(r"(?m)^[A-Z][A-Za-z' \-/]+?\.\s*(?:Melee|Ranged).*?Attack:.*", text)
    if attacks:
        out["attacks"] = attacks[:8]
    return out

def parse_statblock(text: str, source_file: Optional[str] = None) -> Dict[str, Any]:
    result: Dict[str, Any] = {"source": source_file}

    # Light signals to report
    signals = {
        "Armor Class": bool(_search(r"\bArmor\s*Class\b", text)),
        "Hit Points": bool(_search(r"\bHit\s*Points?\b", text)),
        "Speed": bool(_search(r"\bSpeed\b", text)),
        "Saving Throws": bool(_search(r"\bSaving\s*Throws?\b", text)),
        "Skills": bool(_search(r"\bSkills?\b", text)),
        "Senses": bool(_search(r"\bSenses?\b", text)),
        "Languages": bool(_search(r"\bLanguages?\b", text)),
        "Spellcasting": bool(_search(r"\bSpellcasting\b", text)),
    }
    result["_signals"] = signals

    # Character-sheet style (works for many PCs/NPCs)
    cs = parse_character_sheet_style(text)
    result.update(cs)

    # Damage profile (safe)
    dmg = collect_damage_profile(text)
    for k, v in dmg.items():
        if v:
            result[k] = v

    # Sections (safe)
    traits = parse_actions_section(text, r"traits|features|special\s*traits")
    if traits: result["traits"] = traits
    actions = parse_actions_section(text, r"actions")
    if actions: result["actions"] = actions
    reactions = parse_actions_section(text, r"reactions")
    if reactions: result["reactions"] = reactions
    legendary = parse_actions_section(text, r"legendary\s*actions")
    if legendary: result["legendary_actions"] = legendary

    return result

# ------------------------------- Serialization --------------------------------
def prune(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: prune(v) for k, v in x.items() if v not in (None, [], {}, "")}
    if isinstance(x, list):
        return [prune(v) for v in x if v not in (None, [], {}, "")]
    return x

# --------------------------------- CLI ops ------------------------------------
def probe_file(path: str, force_ocr=False, ocr_psm=3, ocr_oem=None, ocr_dpi=300, snippet=1000):
    text, counts = extract_text_safely(path, force_ocr=force_ocr, ocr_psm=ocr_psm, ocr_oem=ocr_oem, ocr_dpi=ocr_dpi)
    sigs = count_signals(text)
    log.info("PROBE: %s", path)
    log.info("Extractor char counts: %s", counts)
    log.info("Signals matched: %d", sigs)
    sample = text[:snippet].replace("\n", "\\n")
    log.info("Snippet: %s...", sample)

def ingest_folder(folder: str, pattern: str="*.pdf", recursive: bool=True,
                  output: Optional[str]=None, out_format: str="json",
                  min_signals: int=1, skip_on_zero: bool=False,
                  force_ocr: bool=False, ocr_psm: int=3, ocr_oem: Optional[int]=None, ocr_dpi: int=300,
                  log_level: str="INFO", log_file: Optional[str]=None,
                  debug_dump: Optional[str]=None) -> int:
    # Prepare logging & dirs
    setup_logging(level=log_level, log_file=log_file)
    if output:
        _ensure_parent_dir(output)
    if debug_dump:
        Path(debug_dump).mkdir(parents=True, exist_ok=True)

    files = _glob_folder(folder, pattern, recursive)
    if not files:
        log.warning("No files matched in %s with pattern %s", folder, pattern)
        return 1

    results: List[Dict[str,Any]] = []
    kept = 0
    skipped = 0

    for i, path in enumerate(files, 1):
        try:
            text, counts = extract_text_safely(path, force_ocr=force_ocr, ocr_psm=ocr_psm, ocr_oem=ocr_oem, ocr_dpi=ocr_dpi)
            sigs = count_signals(text)
            log.info("[%d/%d] %s | counts=%s | signals=%d", i, len(files), path, counts, sigs)

            if debug_dump:
                # save normalized text
                outp = Path(debug_dump) / (Path(path).stem + ".txt")
                try:
                    outp.write_text(text, encoding="utf-8", errors="ignore")
                except Exception as e:
                    log.warning("Failed to write debug dump for %s: %s", path, e)

            if min_signals and sigs < min_signals and skip_on_zero:
                skipped += 1
                log.info("SKIP (signals=%d < %d): %s", sigs, min_signals, path)
                continue

            parsed = parse_statblock(text, source_file=path)
            # Decide keep: core presence
            has_core = bool(parsed.get("ac") or parsed.get("hp") or (
                isinstance(parsed.get("abilities"), dict) and len(parsed["abilities"]) >= 3
            ) or parsed.get("actions") or parsed.get("traits"))
            if not has_core and skip_on_zero:
                skipped += 1
                log.info("SKIP (too sparse after parse): %s", path)
                continue

            results.append(prune(parsed))
            kept += 1
        except Exception as e:
            log.exception("ERROR parsing %s: %s", path, e)
            skipped += 1

    log.info("DONE. kept=%d skipped=%d total=%d", kept, skipped, len(files))

    if output:
        try:
            if out_format.lower() == "yaml":
                if not yaml:
                    log.warning("PyYAML not installed; writing JSON instead.")
                    Path(output).write_text(json.dumps(results, indent=2), encoding="utf-8")
                else:
                    Path(output).write_text(yaml.safe_dump(results, sort_keys=False, allow_unicode=True), encoding="utf-8")
            else:
                Path(output).write_text(json.dumps(results, indent=2), encoding="utf-8")
            log.info("Wrote %d records -> %s", len(results), output)
        except Exception as e:
            log.error("Failed writing output %s: %s", output, e)
            return 2

    return 0

# ----------------------------------- GUI --------------------------------------
def run_gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext

    root = tk.Tk()
    root.title("DnD Statblock Toolkit V3")

    # Vars
    folder_var = tk.StringVar(value="")
    pattern_var = tk.StringVar(value="*.pdf")
    recursive_var = tk.BooleanVar(value=True)
    output_var = tk.StringVar(value="statblocks.json")
    format_var = tk.StringVar(value="json")
    minsignals_var = tk.IntVar(value=1)
    skip_zero_var = tk.BooleanVar(value=False)
    force_ocr_var = tk.BooleanVar(value=False)
    ocr_psm_var = tk.IntVar(value=3)
    ocr_dpi_var = tk.IntVar(value=300)
    loglevel_var = tk.StringVar(value="INFO")
    logfile_var = tk.StringVar(value="statlogs.log")
    debugdump_var = tk.StringVar(value="")

    # Layout helpers
    def row(lbl, widget, r):
        tk.Label(root, text=lbl, anchor="w").grid(row=r, column=0, sticky="w", padx=8, pady=4)
        widget.grid(row=r, column=1, sticky="we", padx=8, pady=4)

    root.columnconfigure(1, weight=1)

    # Widgets
    ent_folder = tk.Entry(root, textvariable=folder_var)
    btn_browse = tk.Button(root, text="Browse...", command=lambda: folder_var.set(filedialog.askdirectory() or folder_var.get()))
    tk.Label(root, text="Input Folder:").grid(row=0, column=0, sticky="w", padx=8, pady=4)
    ent_folder.grid(row=0, column=1, sticky="we", padx=8, pady=4)
    btn_browse.grid(row=0, column=2, padx=8, pady=4)

    row("Pattern(s):", tk.Entry(root, textvariable=pattern_var), 1)
    row("Recursive:", tk.Checkbutton(root, variable=recursive_var), 2)
    row("Output file:", tk.Entry(root, textvariable=output_var), 3)

    tk.Label(root, text="Format:").grid(row=4, column=0, sticky="w", padx=8, pady=4)
    tk.OptionMenu(root, format_var, "json", "yaml").grid(row=4, column=1, sticky="w", padx=8, pady=4)

    row("Min signals:", tk.Spinbox(root, from_=0, to=20, textvariable=minsignals_var, width=6), 5)
    row("Skip on low signals:", tk.Checkbutton(root, variable=skip_zero_var), 6)

    row("Force OCR:", tk.Checkbutton(root, variable=force_ocr_var), 7)
    row("OCR PSM:", tk.Spinbox(root, from_=0, to=13, textvariable=ocr_psm_var, width=6), 8)
    row("OCR DPI:", tk.Spinbox(root, from_=72, to=600, textvariable=ocr_dpi_var, width=6), 9)

    row("Log level:", tk.OptionMenu(root, loglevel_var, "DEBUG","INFO","WARNING","ERROR"), 10)
    row("Log file:", tk.Entry(root, textvariable=logfile_var), 11)
    row("Debug dump dir:", tk.Entry(root, textvariable=debugdump_var), 12)

    txt_log = scrolledtext.ScrolledText(root, height=16, wrap="word")
    txt_log.grid(row=13, column=0, columnspan=3, sticky="nsew", padx=8, pady=8)
    root.rowconfigure(13, weight=1)

    # Buttons
    btn_frame = tk.Frame(root)
    btn_frame.grid(row=14, column=0, columnspan=3, sticky="we", padx=8, pady=8)
    btn_start = tk.Button(btn_frame, text="Start", width=12)
    btn_stop  = tk.Button(btn_frame, text="Stop", width=12, state="disabled")
    btn_start.pack(side="left", padx=4)
    btn_stop.pack(side="left", padx=4)

    # Redirect logging to GUI
    class TkHandler(logging.Handler):
        def emit(self, record):
            msg = self.format(record)
            txt_log.after(0, lambda m=msg: (txt_log.insert("end", m + "\n"), txt_log.see("end")))

    gui_logger = logging.getLogger(LOGGER_NAME)
    gui_logger.setLevel(logging.INFO)
    handler = TkHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    gui_logger.addHandler(handler)

    # Start/Stop logic
    stop_flag = {"stop": False}
    worker = {"thread": None}

    def start_job():
        if not folder_var.get().strip():
            messagebox.showerror("Missing input", "Please choose an input folder.")
            return
        btn_start.config(state="disabled")
        btn_stop.config(state="normal")
        stop_flag["stop"] = False

        def job():
            try:
                setup_logging(level=loglevel_var.get(), log_file=logfile_var.get())
                _ensure_parent_dir(output_var.get())
                if debugdump_var.get().strip():
                    Path(debugdump_var.get()).mkdir(parents=True, exist_ok=True)
                files = _glob_folder(folder_var.get(), pattern_var.get(), recursive_var.get())
                if not files:
                    log.warning("No files matched. Check folder/pattern.")
                    return
                log.info("Found %d files", len(files))
                results = []
                kept = skipped = 0
                for idx, path in enumerate(files, 1):
                    if stop_flag["stop"]:
                        log.info("Stopping at user request...")
                        break
                    text, counts = extract_text_safely(path, force_ocr=force_ocr_var.get(),
                                                       ocr_psm=int(ocr_psm_var.get() or 3),
                                                       ocr_oem=None, ocr_dpi=int(ocr_dpi_var.get() or 300))
                    sigs = count_signals(text)
                    log.info("[%d/%d] %s | counts=%s | signals=%d", idx, len(files), path, counts, sigs)

                    if debugdump_var.get().strip():
                        try:
                            Path(debugdump_var.get(), Path(path).stem + ".txt").write_text(text, encoding="utf-8")
                        except Exception as e:
                            log.warning("Debug dump failed for %s: %s", path, e)

                    if int(minsignals_var.get() or 0) and sigs < int(minsignals_var.get() or 0) and bool(skip_zero_var.get()):
                        skipped += 1
                        log.info("SKIP (signals=%d < %d): %s", sigs, int(minsignals_var.get() or 0), path)
                        continue

                    parsed = parse_statblock(text, source_file=path)
                    has_core = bool(parsed.get("ac") or parsed.get("hp") or (
                        isinstance(parsed.get("abilities"), dict) and len(parsed["abilities"]) >= 3
                    ) or parsed.get("actions") or parsed.get("traits"))
                    if not has_core and bool(skip_zero_var.get()):
                        skipped += 1
                        log.info("SKIP (too sparse after parse): %s", path)
                        continue

                    results.append(prune(parsed))
                    kept += 1

                # Write output
                if output_var.get().strip():
                    try:
                        outp = Path(output_var.get())
                        if format_var.get().lower() == "yaml":
                            if yaml:
                                outp.write_text(yaml.safe_dump(results, sort_keys=False, allow_unicode=True), encoding="utf-8")
                            else:
                                log.warning("PyYAML not installed; writing JSON instead.")
                                outp.write_text(json.dumps(results, indent=2), encoding="utf-8")
                        else:
                            outp.write_text(json.dumps(results, indent=2), encoding="utf-8")
                        log.info("Wrote %d records -> %s", len(results), outp)
                    except Exception as e:
                        log.error("Failed to write output: %s", e)
                log.info("DONE. kept=%d skipped=%d", kept, skipped)
            except Exception as e:
                log.exception("GUI job crashed: %s", e)
            finally:
                btn_start.config(state="normal")
                btn_stop.config(state="disabled")

        t = threading.Thread(target=job, daemon=True)
        worker["thread"] = t
        t.start()

    def stop_job():
        stop_flag["stop"] = True

    btn_start.config(command=start_job)
    btn_stop.config(command=stop_job)

    root.minsize(760, 520)
    root.mainloop()

# ------------------------------------ Main ------------------------------------
def main(argv: List[str]):
    ap = argparse.ArgumentParser(description="DnD Statblock Toolkit V3 (single-file)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_probe = sub.add_parser("probe", help="Probe a single file")
    ap_probe.add_argument("path")
    ap_probe.add_argument("--force-ocr", action="store_true")
    ap_probe.add_argument("--ocr-psm", type=int, default=3)
    ap_probe.add_argument("--ocr-oem", type=int, default=None)
    ap_probe.add_argument("--ocr-dpi", type=int, default=300)
    ap_probe.add_argument("--log-level", default="INFO")
    ap_probe.add_argument("--log-file", default=None)
    ap_probe.add_argument("--snippet", type=int, default=1000)

    ap_ing = sub.add_parser("ingest", help="Ingest a folder to one JSON/YAML")
    ap_ing.add_argument("folder")
    ap_ing.add_argument("--pattern", default="*.pdf")
    ap_ing.add_argument("--recursive", action="store_true", default=True)
    ap_ing.add_argument("--output", default="statblocks.json")
    ap_ing.add_argument("--format", choices=["json","yaml"], default="json")
    ap_ing.add_argument("--min-signals", type=int, default=1)
    ap_ing.add_argument("--no-skip-on-zero", action="store_true", help="Do not skip even when below min-signals")
    ap_ing.add_argument("--force-ocr", action="store_true")
    ap_ing.add_argument("--ocr-psm", type=int, default=3)
    ap_ing.add_argument("--ocr-oem", type=int, default=None)
    ap_ing.add_argument("--ocr-dpi", type=int, default=300)
    ap_ing.add_argument("--log-level", default="INFO")
    ap_ing.add_argument("--log-file", default=None)
    ap_ing.add_argument("--debug-dump", default=None)

    ap_gui = sub.add_parser("gui", help="Launch GUI")

    args = ap.parse_args(argv)

    if args.cmd == "probe":
        setup_logging(level=args.log_level, log_file=args.log_file)
        probe_file(args.path, force_ocr=args.force_ocr, ocr_psm=args.ocr_psm, ocr_oem=args.ocr_oem, ocr_dpi=args.ocr_dpi, snippet=args.snippet)
        return

    if args.cmd == "ingest":
        rc = ingest_folder(
            args.folder, pattern=args.pattern, recursive=args.recursive,
            output=args.output, out_format=args.format,
            min_signals=args.min_signals, skip_on_zero=not args.no_skip_on_zero,
            force_ocr=args.force_ocr, ocr_psm=args.ocr_psm, ocr_oem=args.ocr_oem, ocr_dpi=args.ocr_dpi,
            log_level=args.log_level, log_file=args.log_file, debug_dump=args.debug_dump
        )
        sys.exit(rc)

    if args.cmd == "gui":
        setup_logging(level="INFO", log_file=None)
        run_gui()
        return

if __name__ == "__main__":
    main(sys.argv[1:])
