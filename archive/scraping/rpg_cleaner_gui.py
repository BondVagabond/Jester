
import os
import sys
import json
import threading
import queue
import subprocess
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_TITLE = "RPG Cleaner Pipeline"
PREFS_FILE = Path.home() / ".rpg_cleaner_gui_prefs.json"

DEFAULTS = {
    "input_dir": str(Path(".").resolve()),
    "input_glob": "**/*.pdf",
    "output_dir": str((Path("./cleaned")).resolve()),
    "min_words": 120,
    "max_words": 600,
    "format": "auto",
    "pretty_json": False,
    "schema_version": "1.0",
    "strict_jsonl": True,
    "write_pretty_env": False,
    "pipeline_path": "pipeline.py",
}

class App(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=(12,12,12,12))
        self.master.title(APP_TITLE)
        self.master.geometry("980x640")
        self.master.minsize(860, 560)
        self.queue = queue.Queue()
        self.proc = None
        self.read_thread = None
        self.stop_requested = False

        self.style = ttk.Style(self.master)
        self._setup_style()

        self.prefs = self._load_prefs()
        self._vars_from_prefs()

        # Layout: left config, right output/logs
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_left_panel()
        self._build_right_panel()

        self.pack(fill="both", expand=True)
        self.after(60, self._poll_queue)

    # ----------------- UI -----------------
    def _setup_style(self):
        try:
            # Use system theme where possible
            theme = self.style.theme_use()
        except:
            theme = "clam"
            self.style.theme_use("clam")
        # Subtle color tweaks for a "modern" feel with ttk
        self.style.configure("TFrame", background="#1e2019")
        self.style.configure("TLabelframe", background="#222F44", foreground="#cdd5d1")
        self.style.configure("TLabelframe.Label", foreground="#cdd5d1", background="#222F44", font=("Segoe UI", 10, "bold"))
        self.style.configure("TLabel", background="#222F44", foreground="#cdd5d1")
        self.style.configure("TButton", padding=6)
        self.style.configure("Accent.TButton", background="#222F44", foreground="#cdd5d1")
        self.style.configure("TCheckbutton", background="#222F44", foreground="#cdd5d1")
        self.style.configure("TEntry", fieldbackground="#222F44", foreground="#cdd5d1 ")
        self.style.configure("TCombobox", fieldbackground="#222F44", foreground="#cdd5d1")
        self.style.map("TButton", background=[("active", "#0ea5b7")])
        self.master.configure(bg="#1e2019")

    def _build_left_panel(self):
        left = ttk.Frame(self)
        left.grid(row=0, column=0, sticky="nsw", padx=(0,12))

        # Pipeline path
        pipe_frame = ttk.Labelframe(left, text="Program")
        pipe_frame.pack(fill="x", pady=(0,10))
        self.pipeline_var = tk.StringVar(value=self.prefs.get("pipeline_path", DEFAULTS["pipeline_path"]))
        ttk.Label(pipe_frame, text="pipeline.py path").pack(anchor="w")
        path_row = ttk.Frame(pipe_frame)
        path_row.pack(fill="x", pady=2)
        self.pipeline_entry = ttk.Entry(path_row, textvariable=self.pipeline_var)
        self.pipeline_entry.pack(side="left", fill="x", expand=True)
        ttk.Button(path_row, text="Browse", command=self._choose_pipeline).pack(side="left", padx=(6,0))

        # IO
        io = ttk.Labelframe(left, text="I/O")
        io.pack(fill="x", pady=(0,10))
        self.input_dir_var = tk.StringVar(value=self.prefs["input_dir"])
        self.input_glob_var = tk.StringVar(value=self.prefs["input_glob"])
        self.output_dir_var = tk.StringVar(value=self.prefs["output_dir"])

        self._folder_field(io, "Input directory", self.input_dir_var, self._choose_input_dir)
        self._text_field(io, "Input glob", self.input_glob_var)
        self._folder_field(io, "Output directory", self.output_dir_var, self._choose_output_dir)

        # Chunking
        chunk = ttk.Labelframe(left, text="Chunking")
        chunk.pack(fill="x", pady=(0,10))
        self.min_words_var = tk.IntVar(value=self.prefs["min_words"])
        self.max_words_var = tk.IntVar(value=self.prefs["max_words"])
        self._int_field(chunk, "Min words per chunk", self.min_words_var, 20, 5000, step=10)
        self._int_field(chunk, "Max words per chunk", self.max_words_var, 50, 10000, step=50)

        # Output
        out = ttk.Labelframe(left, text="Output")
        out.pack(fill="x", pady=(0,10))
        self.pretty_var = tk.BooleanVar(value=self.prefs["pretty_json"])
        self.format_var = tk.StringVar(value=self.prefs["format"])
        ttk.Checkbutton(out, text="Pretty-print JSON", variable=self.pretty_var).pack(anchor="w", pady=2)
        row = ttk.Frame(out)
        row.pack(fill="x", pady=(4,0))
        ttk.Label(row, text="Format").pack(side="left")
        self.format_combo = ttk.Combobox(row, state="readonly", textvariable=self.format_var,
                                         values=["auto", "json", "jsonl"], width=8)
        self.format_combo.pack(side="left", padx=(8,0))

        # Env Overrides
        adv = ttk.Labelframe(left, text="Env Overrides")
        adv.pack(fill="x", pady=(0,10))
        self.schema_var = tk.StringVar(value=self.prefs["schema_version"])
        self.strict_jsonl_var = tk.BooleanVar(value=self.prefs["strict_jsonl"])
        self.write_pretty_env_var = tk.BooleanVar(value=self.prefs["write_pretty_env"])
        self._text_field(adv, "SCHEMA_VERSION", self.schema_var)
        ttk.Checkbutton(adv, text="STRICT_JSONL (1 obj / line)", variable=self.strict_jsonl_var).pack(anchor="w")
        ttk.Checkbutton(adv, text="WRITE_PRETTY default", variable=self.write_pretty_env_var).pack(anchor="w")

        # Run Controls
        run = ttk.Frame(left)
        run.pack(fill="x", pady=(8,0))
        self.run_btn = ttk.Button(run, text="▶ Run", command=self._run_pipeline)
        self.run_btn.pack(side="left", fill="x", expand=True)
        self.stop_btn = ttk.Button(run, text="■ Stop", command=self._stop_pipeline, state="disabled")
        self.stop_btn.pack(side="left", padx=(8,0))

        # Save
        ttk.Button(left, text="Save Settings", command=self._save_prefs).pack(fill="x", pady=(10,0))

    def _build_right_panel(self):
        right = ttk.Frame(self)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        # Log
        log_box = ttk.Labelframe(right, text="Logs")
        log_box.grid(row=0, column=0, sticky="nsew", pady=(0,8))
        self.log = tk.Text(log_box, height=16, wrap="word", bg="#020617", fg="#e5e7eb", insertbackground="#e5e7eb")
        self.log.pack(fill="both", expand=True, padx=4, pady=4)

        # Output listing
        out_box = ttk.Labelframe(right, text="Output Files")
        out_box.grid(row=1, column=0, sticky="nsew")
        out_box.rowconfigure(0, weight=1)
        columns = ("path","size")
        self.tree = ttk.Treeview(out_box, columns=columns, show="headings", height=8)
        self.tree.heading("path", text="Path")
        self.tree.heading("size", text="Bytes")
        self.tree.column("path", width=560, anchor="w")
        self.tree.column("size", width=100, anchor="e")
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(out_box, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.grid(row=0, column=1, sticky="ns")
        btns = ttk.Frame(out_box)
        btns.grid(row=1, column=0, sticky="ew", pady=(6,0))
        ttk.Button(btns, text="Refresh", command=self._refresh_outputs).pack(side="left")
        ttk.Button(btns, text="Open Output Folder", command=self._open_output_dir).pack(side="left", padx=(6,0))

        self._refresh_outputs()

    # ----------------- Helpers -----------------
    def _folder_field(self, parent, label, var, command):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label).pack(anchor="w")
        inner = ttk.Frame(row)
        inner.pack(fill="x")
        ent = ttk.Entry(inner, textvariable=var)
        ent.pack(side="left", fill="x", expand=True)
        ttk.Button(inner, text="Browse", command=command).pack(side="left", padx=(6,0))

    def _text_field(self, parent, label, var):
        ttk.Label(parent, text=label).pack(anchor="w")
        ttk.Entry(parent, textvariable=var).pack(fill="x", pady=(0,4))

    def _int_field(self, parent, label, var, min_v, max_v, step=1):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=2)
        ttk.Label(row, text=label).pack(side="left")
        sp = ttk.Spinbox(row, from_=min_v, to=max_v, increment=step, textvariable=var, width=8)
        sp.pack(side="left", padx=(8,0))

    def _choose_input_dir(self):
        d = filedialog.askdirectory(initialdir=self.input_dir_var.get() or ".")
        if d: self.input_dir_var.set(d)

    def _choose_output_dir(self):
        d = filedialog.askdirectory(initialdir=self.output_dir_var.get() or ".")
        if d: self.output_dir_var.set(d)

    def _choose_pipeline(self):
        p = filedialog.askopenfilename(title="Select pipeline.py", filetypes=[("Python files","*.py"),("All files","*.*")])
        if p: self.pipeline_var.set(p)

    def _save_prefs(self):
        prefs = self._collect_prefs()
        try:
            with open(PREFS_FILE, "w", encoding="utf-8") as f:
                json.dump(prefs, f, indent=2)
            messagebox.showinfo("Saved", f"Settings saved to {PREFS_FILE}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save prefs: {e}")

    def _load_prefs(self):
        if PREFS_FILE.exists():
            try:
                with open(PREFS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                out = DEFAULTS.copy()
                out.update(data)
                return out
            except Exception:
                pass
        return DEFAULTS.copy()

    def _vars_from_prefs(self):
        pass

    def _collect_prefs(self):
        return {
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
            "pipeline_path": self.pipeline_var.get(),
        }

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
        env["DM_INPUT_DIR"] = prefs["input_dir"]
        env["DM_INPUT_GLOB"] = prefs["input_glob"]
        env["DM_OUTPUT_DIR"] = prefs["output_dir"]
        env["DM_MIN_WORDS"] = str(prefs["min_words"])
        env["DM_MAX_WORDS"] = str(prefs["max_words"])
        env["DM_SCHEMA_VERSION"] = prefs["schema_version"]
        env["DM_STRICT_JSONL"] = "1" if prefs["strict_jsonl"] else "0"
        env["DM_WRITE_PRETTY"] = "1" if prefs["write_pretty_env"] else "0"

        cmd = [sys.executable, prefs["pipeline_path"],
               "--input-dir", prefs["input_dir"],
               "--input-glob", prefs["input_glob"],
               "--output-dir", prefs["output_dir"],
               "--min-words", str(prefs["min_words"]),
               "--max-words", str(prefs["max_words"]),
               "--format", prefs["format"]]
        if prefs["pretty_json"]:
            cmd.append("--pretty-json")

        self._append_log(f"Command: {' '.join(cmd)}\n")
        self._append_log(f"Env(DM_*): { {k: env[k] for k in env if k.startswith('DM_')} }\n\n")

        try:
            self.proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=env
            )
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start pipeline: {e}")
            return

        self.stop_requested = False
        self.run_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.read_thread = threading.Thread(target=self._read_output, daemon=True)
        self.read_thread.start()

    def _stop_pipeline(self):
        if self.proc and self.proc.poll() is None:
            self.stop_requested = True
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
            self.queue.put(None)  # sentinel

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

    # ----------------- Outputs -----------------
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

def main():
    root = tk.Tk()
    app = App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
