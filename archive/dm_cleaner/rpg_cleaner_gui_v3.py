
import os
import sys
import json
import threading
import queue
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_TITLE = "RPG Cleaner Pipeline — Advanced GUI"
PREFS_FILE = Path.home() / ".rpg_cleaner_gui_prefs_v2.json"

DEFAULTS = {
    # Program / pipeline
    "pipeline_path": "pipeline.py",
    "input_dir": str(Path(".").resolve()),
    "input_glob": "**/*.pdf",
    "output_dir": str((Path("./cleaned")).resolve()),
    "min_words": 120,
    "max_words": 600,
    "format": "auto",
    "pretty_json": False,

    # Config / structure
    "schema_version": "1.0",
    "strict_jsonl": True,
    "write_pretty_env": False,
    "acts_enabled": True,

    # Extractor (env-based)
    "ocr_enabled": False,
    "ocr_lang": "eng",
    "ocr_engine": "tesseract",
    "ocr_dpi": 300,
    "fix_rotation": True,
    "smart_ocr": True,
    "text_density_threshold": 0.0005,
    "extract_timeout_sec": 180,
    "max_pages": 2000,
    "max_file_mb": 250,

    # Cleaner AI & screening
    "sem_dedup_enabled": False,
    "sem_dedup_model": "sentence-transformers/all-MiniLM-L6-v2",
    "sem_dedup_thresh": 0.92,
    "filter_toxic": False,
    "filter_nsfw": False,
    "filter_action": "flag",
    "bias_lexicon_path": "",

    # Logging
    "log_level": "INFO",
    "log_json": False,
    "log_file": "",

    # Debug & reports
    "debug_dir": "",
    "report_enabled": False,
    "report_dir": str((Path("./reports")).resolve()),

    # Doc ID policy
    "doc_id_policy": "stem",  # or hash_stem
}

class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=(12,12,12,12))
        self.master.title(APP_TITLE)
        self.master.geometry("1100x720")
        self.master.minsize(980, 620)
        self.queue = queue.Queue()
        self.proc = None
        self.read_thread = None

        self.style = ttk.Style(self.master)
        self._setup_style()

        self.prefs = self._load_prefs()
        self._vars_from_prefs()

        self._build_layout()
        self.pack(fill="both", expand=True)
        self.after(60, self._poll_queue)

    # ----------------- UI -----------------
    def _setup_style(self):
        try:
            theme = self.style.theme_use()
        except:
            self.style.theme_use("clam")
        self.style.configure("TFrame", background="#0f172a")
        self.style.configure("TLabelframe", background="#0f172a", foreground="#e5e7eb")
        self.style.configure("TLabelframe.Label", foreground="#e5e7eb", background="#0f172a", font=("Segoe UI", 10, "bold"))
        self.style.configure("TLabel", background="#0f172a", foreground="#e5e7eb")
        self.style.configure("TButton", padding=6)
        self.style.configure("TCheckbutton", background="#0f172a", foreground="#e5e7eb")
        self.style.configure("TEntry", fieldbackground="#0b1324", foreground="#e5e7eb")
        self.style.configure("TCombobox", fieldbackground="#0b1324", foreground="#e5e7eb")
        self.master.configure(bg="#0f172a")

    def _build_layout(self):
        # Main split: left controls (tabs) and right log/output
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        left = ttk.Frame(self)
        left.grid(row=0, column=0, sticky="nsw", padx=(0,12))

        # Program frame (top)
        prog = ttk.Labelframe(left, text="Program")
        prog.pack(fill="x", pady=(0,8))
        self.pipeline_var = tk.StringVar(value=self.prefs["pipeline_path"])
        ttk.Label(prog, text="pipeline.py path").pack(anchor="w")
        row = ttk.Frame(prog); row.pack(fill="x", pady=2)
        ttk.Entry(row, textvariable=self.pipeline_var).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="Browse", command=self._choose_pipeline).pack(side="left", padx=(6,0))

        # Tabs for configuration
        self.tabs = ttk.Notebook(left)
        self.tabs.pack(fill="both", expand=True, pady=(6,0))

        self._tab_pipeline()
        self._tab_extractor()
        self._tab_cleaner()
        self._tab_logging()

        # Run controls
        run = ttk.Frame(left); run.pack(fill="x", pady=(10,0))
        self.run_btn = ttk.Button(run, text="▶ Run Pipeline", command=self._run_pipeline)
        self.stop_btn = ttk.Button(run, text="■ Stop", command=self._stop_pipeline, state="disabled")
        self.run_btn.pack(side="left", fill="x", expand=True)
        self.stop_btn.pack(side="left", padx=(8,0))
        ttk.Button(left, text="Save Settings", command=self._save_prefs).pack(fill="x", pady=(8,0))

        # Right: logs + outputs
        right = ttk.Frame(self)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        log_box = ttk.Labelframe(right, text="Logs")
        log_box.grid(row=0, column=0, sticky="nsew", pady=(0,8))
        self.log = tk.Text(log_box, height=14, wrap="word", bg="#020617", fg="#e5e7eb", insertbackground="#e5e7eb")
        self.log.pack(fill="both", expand=True, padx=4, pady=4)

        out_box = ttk.Labelframe(right, text="Output Files")
        out_box.grid(row=1, column=0, sticky="nsew")
        out_box.rowconfigure(0, weight=1)
        columns = ("path","size")
        self.tree = ttk.Treeview(out_box, columns=columns, show="headings", height=8)
        self.tree.heading("path", text="Path")
        self.tree.heading("size", text="Bytes")
        self.tree.column("path", width=640, anchor="w")
        self.tree.column("size", width=100, anchor="e")
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(out_box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.grid(row=0, column=1, sticky="ns")
        btns = ttk.Frame(out_box); btns.grid(row=1, column=0, sticky="ew", pady=(6,0))
        ttk.Button(btns, text="Refresh", command=self._refresh_outputs).pack(side="left")
        ttk.Button(btns, text="Open Output Folder", command=self._open_output_dir).pack(side="left", padx=(6,0))

        self._refresh_outputs()

    # ----- tabs -----
    def _tab_pipeline(self):
        t = ttk.Frame(self.tabs); self.tabs.add(t, text="Pipeline")
        # I/O
        io = ttk.Labelframe(t, text="I/O"); io.pack(fill="x", pady=6)
        self.input_dir_var = tk.StringVar(value=self.prefs["input_dir"])
        self.input_glob_var = tk.StringVar(value=self.prefs["input_glob"])
        self.output_dir_var = tk.StringVar(value=self.prefs["output_dir"])
        self._folder_field(io, "Input directory", self.input_dir_var, self._choose_input_dir)
        self._text_field(io, "Input glob", self.input_glob_var)
        self._folder_field(io, "Output directory", self.output_dir_var, self._choose_output_dir)

        # Chunking
        ch = ttk.Labelframe(t, text="Chunking"); ch.pack(fill="x", pady=6)
        self.min_words_var = tk.IntVar(value=self.prefs["min_words"])
        self.max_words_var = tk.IntVar(value=self.prefs["max_words"])
        self._int_field(ch, "Min words per chunk", self.min_words_var, 20, 10000, 10)
        self._int_field(ch, "Max words per chunk", self.max_words_var, 50, 20000, 50)

        # Output
        out = ttk.Labelframe(t, text="Output"); out.pack(fill="x", pady=6)
        self.pretty_var = tk.BooleanVar(value=self.prefs["pretty_json"])
        self.format_var = tk.StringVar(value=self.prefs["format"])
        ttk.Checkbutton(out, text="Pretty-print JSON", variable=self.pretty_var).pack(anchor="w")
        row = ttk.Frame(out); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Format").pack(side="left")
        cb = ttk.Combobox(row, state="readonly", textvariable=self.format_var, values=["auto","json","jsonl"], width=8)
        cb.pack(side="left", padx=(8,0))

        # Structure & schema
        sc = ttk.Labelframe(t, text="Schema & Structure"); sc.pack(fill="x", pady=6)
        self.schema_var = tk.StringVar(value=self.prefs["schema_version"])
        ttk.Label(sc, text="SCHEMA_VERSION").pack(anchor="w")
        ttk.Entry(sc, textvariable=self.schema_var).pack(fill="x", pady=(0,4))
        self.acts_enabled_var = tk.BooleanVar(value=self.prefs["acts_enabled"])
        ttk.Checkbutton(sc, text="Enable 7-Act Structure", variable=self.acts_enabled_var).pack(anchor="w")
        self.strict_jsonl_var = tk.BooleanVar(value=self.prefs["strict_jsonl"])
        ttk.Checkbutton(sc, text="STRICT_JSONL (1 object/line)", variable=self.strict_jsonl_var).pack(anchor="w")
        self.write_pretty_env_var = tk.BooleanVar(value=self.prefs["write_pretty_env"])
        ttk.Checkbutton(sc, text="WRITE_PRETTY default", variable=self.write_pretty_env_var).pack(anchor="w")

        # Doc IDs
        did = ttk.Labelframe(t, text="Doc ID Policy"); did.pack(fill="x", pady=6)
        self.doc_id_policy_var = tk.StringVar(value=self.prefs["doc_id_policy"])
        ttk.Radiobutton(did, text="Stem", variable=self.doc_id_policy_var, value="stem").pack(anchor="w")
        ttk.Radiobutton(did, text="Hash+Stem", variable=self.doc_id_policy_var, value="hash_stem").pack(anchor="w")

        # Reports & debug
        rep = ttk.Labelframe(t, text="Reports & Debug"); rep.pack(fill="x", pady=6)
        self.report_enabled_var = tk.BooleanVar(value=self.prefs["report_enabled"])
        ttk.Checkbutton(rep, text="Write per-file quality report", variable=self.report_enabled_var).pack(anchor="w")
        self.report_dir_var = tk.StringVar(value=self.prefs["report_dir"])
        self._folder_field(rep, "Report directory", self.report_dir_var, lambda: self._choose_dir_for_var(self.report_dir_var))
        self.debug_dir_var = tk.StringVar(value=self.prefs["debug_dir"])
        self._folder_field(rep, "Debug artifacts directory (optional)", self.debug_dir_var, lambda: self._choose_dir_for_var(self.debug_dir_var))

    def _tab_extractor(self):
        t = ttk.Frame(self.tabs); self.tabs.add(t, text="Extractor")
        # OCR
        ocr = ttk.Labelframe(t, text="OCR"); ocr.pack(fill="x", pady=6)
        self.ocr_enabled_var = tk.BooleanVar(value=self.prefs["ocr_enabled"])
        ttk.Checkbutton(ocr, text="Enable OCR fallback", variable=self.ocr_enabled_var).pack(anchor="w")
        self.ocr_lang_var = tk.StringVar(value=self.prefs["ocr_lang"])
        self.ocr_engine_var = tk.StringVar(value=self.prefs["ocr_engine"])
        self.ocr_dpi_var = tk.IntVar(value=self.prefs["ocr_dpi"])
        self._text_field(ocr, "OCR language (e.g., eng)", self.ocr_lang_var)
        self._text_field(ocr, "OCR engine", self.ocr_engine_var)
        row = ttk.Frame(ocr); row.pack(fill="x", pady=2)
        ttk.Label(row, text="OCR DPI").pack(side="left")
        ttk.Spinbox(row, from_=72, to=600, increment=24, textvariable=self.ocr_dpi_var, width=8).pack(side="left", padx=(8,0))

        # Rotation & smart OCR
        fix = ttk.Labelframe(t, text="Rotation & Smart OCR"); fix.pack(fill="x", pady=6)
        self.fix_rotation_var = tk.BooleanVar(value=self.prefs["fix_rotation"])
        ttk.Checkbutton(fix, text="Auto-fix rotated pages", variable=self.fix_rotation_var).pack(anchor="w")
        self.smart_ocr_var = tk.BooleanVar(value=self.prefs["smart_ocr"])
        ttk.Checkbutton(fix, text="Smart OCR (density-based)", variable=self.smart_ocr_var).pack(anchor="w")
        row = ttk.Frame(fix); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Text density threshold").pack(side="left")
        self.text_density_threshold_var = tk.DoubleVar(value=self.prefs["text_density_threshold"])
        ttk.Entry(row, textvariable=self.text_density_threshold_var, width=10).pack(side="left", padx=(8,0))

        # Guardrails
        grd = ttk.Labelframe(t, text="Guardrails"); grd.pack(fill="x", pady=6)
        self.extract_timeout_var = tk.IntVar(value=self.prefs["extract_timeout_sec"])
        self.max_pages_var = tk.IntVar(value=self.prefs["max_pages"])
        self.max_file_mb_var = tk.IntVar(value=self.prefs["max_file_mb"])
        self._int_field(grd, "Timeout (sec)", self.extract_timeout_var, 0, 3600, 10)
        self._int_field(grd, "Max pages", self.max_pages_var, 10, 20000, 10)
        self._int_field(grd, "Max file size (MB)", self.max_file_mb_var, 10, 2000, 10)

    def _tab_cleaner(self):
        t = ttk.Frame(self.tabs); self.tabs.add(t, text="Cleaner / AI")
        # Semantic dedup
        sem = ttk.Labelframe(t, text="Semantic Dedup"); sem.pack(fill="x", pady=6)
        self.sem_enabled_var = tk.BooleanVar(value=self.prefs["sem_dedup_enabled"])
        ttk.Checkbutton(sem, text="Enable semantic near-duplicate removal", variable=self.sem_enabled_var).pack(anchor="w")
        self.sem_model_var = tk.StringVar(value=self.prefs["sem_dedup_model"])
        self.sem_thresh_var = tk.DoubleVar(value=self.prefs["sem_dedup_thresh"])
        self._text_field(sem, "SentenceTransformer model", self.sem_model_var)
        row = ttk.Frame(sem); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Similarity threshold (0-1)").pack(side="left")
        ttk.Entry(row, textvariable=self.sem_thresh_var, width=10).pack(side="left", padx=(8,0))

        # Safety filters
        saf = ttk.Labelframe(t, text="Safety Filters"); saf.pack(fill="x", pady=6)
        self.filter_toxic_var = tk.BooleanVar(value=self.prefs["filter_toxic"])
        self.filter_nsfw_var  = tk.BooleanVar(value=self.prefs["filter_nsfw"])
        ttk.Checkbutton(saf, text="Toxicity filter", variable=self.filter_toxic_var).pack(anchor="w")
        ttk.Checkbutton(saf, text="NSFW filter", variable=self.filter_nsfw_var).pack(anchor="w")
        self.filter_action_var = tk.StringVar(value=self.prefs["filter_action"])
        row = ttk.Frame(saf); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Action").pack(side="left")
        ttk.Combobox(row, state="readonly", textvariable=self.filter_action_var,
                     values=["flag","drop"], width=8).pack(side="left", padx=(8,0))

        # Bias lexicon
        lex = ttk.Labelframe(t, text="Bias Lexicon"); lex.pack(fill="x", pady=6)
        self.bias_lexicon_var = tk.StringVar(value=self.prefs["bias_lexicon_path"])
        self._file_field(lex, "Bias lexicon file (optional)", self.bias_lexicon_var)

    def _tab_logging(self):
        t = ttk.Frame(self.tabs); self.tabs.add(t, text="Logging")
        self.log_level_var = tk.StringVar(value=self.prefs["log_level"])
        self.log_json_var  = tk.BooleanVar(value=self.prefs["log_json"])
        self.log_file_var  = tk.StringVar(value=self.prefs["log_file"])

        row = ttk.Frame(t); row.pack(fill="x", pady=2)
        ttk.Label(row, text="Log level").pack(side="left")
        ttk.Combobox(row, state="readonly", textvariable=self.log_level_var,
                     values=["DEBUG","INFO","WARNING","ERROR"], width=10).pack(side="left", padx=(8,0))
        ttk.Checkbutton(t, text="Structured JSON logs", variable=self.log_json_var).pack(anchor="w", pady=(4,0))
        self._file_field(t, "Log file (optional)", self.log_file_var)

    # ----------------- Helpers -----------------
    def _folder_field(self, parent, label, var, command):
        row = ttk.Frame(parent); row.pack(fill="x", pady=2)
        ttk.Label(row, text=label).pack(anchor="w")
        row2 = ttk.Frame(parent); row2.pack(fill="x")
        ttk.Entry(row2, textvariable=var).pack(side="left", fill="x", expand=True)
        ttk.Button(row2, text="Browse", command=command).pack(side="left", padx=(6,0))

    def _file_field(self, parent, label, var):
        row = ttk.Frame(parent); row.pack(fill="x", pady=2)
        ttk.Label(row, text=label).pack(anchor="w")
        row2 = ttk.Frame(parent); row2.pack(fill="x")
        ttk.Entry(row2, textvariable=var).pack(side="left", fill="x", expand=True)
        ttk.Button(row2, text="Browse", command=lambda: self._choose_file_for_var(var)).pack(side="left", padx=(6,0))

    def _text_field(self, parent, label, var):
        ttk.Label(parent, text=label).pack(anchor="w")
        ttk.Entry(parent, textvariable=var).pack(fill="x", pady=(0,4))

    def _int_field(self, parent, label, var, minv, maxv, step):
        row = ttk.Frame(parent); row.pack(fill="x", pady=2)
        ttk.Label(row, text=label).pack(side="left")
        ttk.Spinbox(row, from_=minv, to=maxv, increment=step, textvariable=var, width=8).pack(side="left", padx=(8,0))

    def _choose_input_dir(self):
        d = filedialog.askdirectory(initialdir=self.input_dir_var.get() or ".")
        if d: self.input_dir_var.set(d)

    def _choose_output_dir(self):
        d = filedialog.askdirectory(initialdir=self.output_dir_var.get() or ".")
        if d: self.output_dir_var.set(d)

    def _choose_dir_for_var(self, var):
        d = filedialog.askdirectory(initialdir=var.get() or ".")
        if d: var.set(d)

    def _choose_pipeline(self):
        p = filedialog.askopenfilename(title="Select pipeline.py", filetypes=[("Python files","*.py"),("All files","*.*")])
        if p: self.pipeline_var.set(p)

    def _choose_file_for_var(self, var):
        p = filedialog.askopenfilename(title="Select file", filetypes=[("All files","*.*")])
        if p: var.set(p)

    # ----------------- Run / Stop -----------------
    def _run_pipeline(self):
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("Running", "Pipeline is already running.")
            return

        prefs = self._collect_prefs()
        if not Path(prefs["pipeline_path"]).exists():
            messagebox.showerror("pipeline.py not found", "Please set a valid path to pipeline.py.")
            return

        # environment overrides
        env = os.environ.copy()
        # Core config
        env["DM_INPUT_DIR"] = prefs["input_dir"]
        env["DM_INPUT_GLOB"] = prefs["input_glob"]
        env["DM_OUTPUT_DIR"] = prefs["output_dir"]
        env["DM_MIN_WORDS"] = str(prefs["min_words"])
        env["DM_MAX_WORDS"] = str(prefs["max_words"])
        env["DM_SCHEMA_VERSION"] = prefs["schema_version"]
        env["DM_STRICT_JSONL"] = "1" if prefs["strict_jsonl"] else "0"
        env["DM_WRITE_PRETTY"] = "1" if prefs["write_pretty_env"] else "0"
        env["DM_ACT_STRUCTURE_ENABLED"] = "1" if prefs["acts_enabled"] else "0"
        env["DM_DOC_ID_POLICY"] = prefs["doc_id_policy"]

        # Extractor envs
        env["DM_OCR_ENABLED"] = "1" if prefs["ocr_enabled"] else "0"
        env["DM_OCR_LANG"] = prefs["ocr_lang"]
        env["DM_OCR_ENGINE"] = prefs["ocr_engine"]
        env["DM_OCR_DPI"] = str(prefs["ocr_dpi"])
        env["DM_FIX_ROTATION"] = "1" if prefs["fix_rotation"] else "0"
        env["DM_SMART_OCR"] = "1" if prefs["smart_ocr"] else "0"
        env["DM_TEXT_DENSITY_THRESHOLD"] = str(prefs["text_density_threshold"])
        env["DM_EXTRACT_TIMEOUT_SEC"] = str(prefs["extract_timeout_sec"])
        env["DM_MAX_PAGES"] = str(prefs["max_pages"])
        env["DM_MAX_FILE_MB"] = str(prefs["max_file_mb"])

        # Cleaner AI & screening
        env["DM_SEM_DEDUP_ENABLED"] = "1" if prefs["sem_dedup_enabled"] else "0"
        env["DM_SEM_DEDUP_MODEL"] = prefs["sem_dedup_model"]
        env["DM_SEM_DEDUP_THRESH"] = str(prefs["sem_dedup_thresh"])
        env["DM_FILTER_TOXIC"] = "1" if prefs["filter_toxic"] else "0"
        env["DM_FILTER_NSFW"] = "1" if prefs["filter_nsfw"] else "0"
        env["DM_FILTER_ACTION"] = prefs["filter_action"]
        if prefs["bias_lexicon_path"]:
            env["DM_BIAS_LEXICON"] = prefs["bias_lexicon_path"]

        # Logging
        env["DM_LOG_LEVEL"] = prefs["log_level"]
        env["DM_LOG_JSON"] = "1" if prefs["log_json"] else "0"
        if prefs["log_file"]:
            env["DM_LOG_FILE"] = prefs["log_file"]

        # Build command
        cmd = [sys.executable, prefs["pipeline_path"],
               "--input-dir", prefs["input_dir"],
               "--input-glob", prefs["input_glob"],
               "--output-dir", prefs["output_dir"],
               "--min-words", str(prefs["min_words"]),
               "--max-words", str(prefs["max_words"]),
               "--format", prefs["format"]]
        if prefs["pretty_json"]:
            cmd.append("--pretty-json")

        # Report/Debug are implemented inside cleaner; pipeline may not pass them through.
        if prefs["report_enabled"]:
            env["DM_REPORT_DIR"] = prefs["report_dir"]
        if prefs["debug_dir"]:
            env["DM_DEBUG_DIR"] = prefs["debug_dir"]

        self._append_log(f"Command: {' '.join(cmd)}\n")
        dm = {k: env[k] for k in env if k.startswith("DM_")}
        self._append_log(f"Environment (DM_*): {json.dumps(dm, indent=2)}\n\n")

        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=env
            )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start pipeline: {e}")
            return

        self.run_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.read_thread = threading.Thread(target=self._read_output, daemon=True)
        self.read_thread.start()

    def _stop_pipeline(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
        else:
            self._append_log("No running process.\n")

    def _read_output(self):
        try:
            for line in self.proc.stdout:
                self.queue.put(line.rstrip("\n"))
        finally:
            rc = self.proc.wait()
            self.queue.put(f"\n[Process exited with code {rc}]")
            self.queue.put(None)

    def _poll_queue(self):
        try:
            while True:
                item = self.queue.get_nowait()
                if item is None:
                    self.run_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    self._refresh_outputs()
                    break
                else:
                    self._append_log(item + "\n")
        except queue.Empty:
            pass
        self.after(60, self._poll_queue)

    def _append_log(self, text):
        self.log.insert("end", text)
        self.log.see("end")

    # ----------------- Output listing -----------------
    def _refresh_outputs(self):
        self.tree.delete(*self.tree.get_children())
        out_dir = Path(self.output_dir_var.get())
        if not out_dir.exists():
            return
        files = sorted(p for p in out_dir.glob("**/*") if p.is_file())
        for p in files:
            try:
                size = p.stat().st_size
                rel = str(p.relative_to(out_dir))
            except Exception:
                size = 0; rel = str(p)
            self.tree.insert("", "end", values=(rel, size))

    def _open_output_dir(self):
        d = self.output_dir_var.get()
        if not d:
            return
        path = Path(d)
        if not path.exists():
            messagebox.showinfo("Missing", "Output directory does not exist yet.")
            return
        if sys.platform.startswith("win"):
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.call(["open", str(path)])
        else:
            subprocess.call(["xdg-open", str(path)])

    # ----------------- Prefs -----------------
    def _load_prefs(self):
        if PREFS_FILE.exists():
            try:
                data = json.loads(PREFS_FILE.read_text(encoding="utf-8"))
                out = DEFAULTS.copy(); out.update(data)
                return out
            except Exception:
                pass
        return DEFAULTS.copy()

    def _vars_from_prefs(self):
        pass

    def _collect_prefs(self):
        return {
            "pipeline_path": self.pipeline_var.get(),

            "input_dir": self.input_dir_var.get(),
            "input_glob": self.input_glob_var.get(),
            "output_dir": self.output_dir_var.get(),
            "min_words": int(self.min_words_var.get()),
            "max_words": int(self.max_words_var.get()),
            "format": self.format_var.get(),
            "pretty_json": bool(self.pretty_var.get()),

            "schema_version": self.schema_var.get(),
            "strict_jsonl": bool(self.strict_jsonl_var.get()),
            "write_pretty_env": bool(self.write_pretty_env_var.get()),
            "acts_enabled": bool(self.acts_enabled_var.get()),

            "ocr_enabled": bool(self.ocr_enabled_var.get()),
            "ocr_lang": self.ocr_lang_var.get(),
            "ocr_engine": self.ocr_engine_var.get(),
            "ocr_dpi": int(self.ocr_dpi_var.get()),
            "fix_rotation": bool(self.fix_rotation_var.get()),
            "smart_ocr": bool(self.smart_ocr_var.get()),
            "text_density_threshold": float(self.text_density_threshold_var.get()),
            "extract_timeout_sec": int(self.extract_timeout_var.get()),
            "max_pages": int(self.max_pages_var.get()),
            "max_file_mb": int(self.max_file_mb_var.get()),

            "sem_dedup_enabled": bool(self.sem_enabled_var.get()),
            "sem_dedup_model": self.sem_model_var.get(),
            "sem_dedup_thresh": float(self.sem_thresh_var.get()),

            "filter_toxic": bool(self.filter_toxic_var.get()),
            "filter_nsfw": bool(self.filter_nsfw_var.get()),
            "filter_action": self.filter_action_var.get(),
            "bias_lexicon_path": self.bias_lexicon_var.get(),

            "log_level": self.log_level_var.get(),
            "log_json": bool(self.log_json_var.get()),
            "log_file": self.log_file_var.get(),

            "debug_dir": self.debug_dir_var.get(),
            "report_enabled": bool(self.report_enabled_var.get()),
            "report_dir": self.report_dir_var.get(),

            "doc_id_policy": self.doc_id_policy_var.get(),
        }

    def _save_prefs(self):
        prefs = self._collect_prefs()
        try:
            PREFS_FILE.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
            messagebox.showinfo("Saved", f"Settings saved to {PREFS_FILE}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save prefs: {e}")

def main():
    root = tk.Tk()
    app = App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
