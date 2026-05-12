import tkinter as tk
import re
from tkinter import ttk, filedialog, messagebox
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from ui.theme import THEME, FONTS
from core.constants import *
from ui.widgets import *
from core.parsers import *
class ScriptsTab(tk.Frame):
    def __init__(self, parent, config, status: StatusBar):
        self.cfg = config
        super().__init__(parent, bg=THEME["bg_mid"])
        self._status  = status
        self._def_files: List[Path] = []
        self._build_ui()
        self.after(500, self._load_all)

    def _build_ui(self):
        bar = tk.Frame(self, bg=THEME["bg_dark"], pady=4)
        bar.pack(fill="x")
        self._search_var = tk.StringVar()
        tk.Label(bar, text="Search in files:", bg=THEME["bg_dark"], fg=THEME["fg_dim"],
                 font=FONTS["body"]).pack(side="left", padx=(10,4))
        tk.Entry(bar, textvariable=self._search_var,
                  bg=THEME["bg_panel"], fg=THEME["fg_text"], insertbackground=FG_TEXT,
                  font=FONTS["body"], relief="flat", width=30
                  ).pack(side="left", padx=4)
        tk.Button(bar, text="Search", command=self._do_search,
                  bg=ACCENT2, fg="white", relief="flat",
                  font=("Segoe UI", 9, "bold"), padx=8
                  ).pack(side="left", padx=4)
        tk.Button(bar, text="Export All .def", command=self._export_all,
                  bg=ACCENT3, fg="#000", relief="flat",
                  font=("Segoe UI", 9, "bold"), padx=8
                  ).pack(side="left", padx=4)
        self._count_lbl = tk.Label(bar, text="", bg=THEME["bg_dark"], fg=THEME["fg_dim"],
                                    font=FONTS["small"])
        self._count_lbl.pack(side="right", padx=12)

        pane = tk.PanedWindow(self, orient="horizontal", bg=THEME["bg_dark"],
                               sashwidth=6, sashrelief="flat")
        pane.pack(fill="both", expand=True)

        # File tree
        lf = tk.Frame(pane, bg=THEME["bg_mid"])
        pane.add(lf, minsize=220)
        tk.Label(lf, text=".DEF FILES", bg=THEME["bg_mid"], fg=THEME["accent"],
                 font=("Segoe UI", 9, "bold"), pady=4).pack(anchor="w", padx=8)
        self._file_lb = tk.Listbox(lf, bg=THEME["bg_panel"], fg=THEME["fg_text"],
                                    font=("Consolas", 9), selectmode="single",
                                    relief="flat", activestyle="dotbox",
                                    selectbackground=BG_CARD,
                                    selectforeground=ACCENT)
        sb_f = ttk.Scrollbar(lf, orient="vertical", command=self._file_lb.yview)
        self._file_lb.configure(yscrollcommand=sb_f.set)
        sb_f.pack(side="right", fill="y")
        self._file_lb.pack(fill="both", expand=True, padx=(4,0), pady=4)
        self._file_lb.bind("<<ListboxSelect>>", self._on_file_select)

        # Content + search results
        right = tk.Frame(pane, bg=THEME["bg_panel"])
        pane.add(right)

        # Search results
        self._results_frame = tk.Frame(right, bg=THEME["bg_dark"])
        self._results_tv = ttk.Treeview(self._results_frame,
                                         columns=("file","line","text"),
                                         show="headings", height=8)
        self._results_tv.heading("file", text="File", anchor="w")
        self._results_tv.heading("line", text="Line", anchor="center")
        self._results_tv.heading("text", text="Match", anchor="w")
        self._results_tv.column("file", width=140, stretch=False)
        self._results_tv.column("line", width=50,  stretch=False, anchor="center")
        self._results_tv.column("text", width=400, stretch=True)
        sb_r = ttk.Scrollbar(self._results_frame, orient="vertical",
                              command=self._results_tv.yview)
        self._results_tv.configure(yscrollcommand=sb_r.set)
        sb_r.pack(side="right", fill="y")
        self._results_tv.pack(fill="both", expand=True)
        self._results_tv.bind("<<TreeviewSelect>>", self._on_result_select)
        # Hidden by default

        # File content viewer
        self._content_frame = tk.Frame(right, bg=THEME["bg_panel"])
        self._content_frame.pack(fill="both", expand=True)

        hdr = tk.Frame(self._content_frame, bg=THEME["bg_dark"], pady=2)
        hdr.pack(fill="x")
        self._file_lbl = tk.Label(hdr, text="Select a file", bg=THEME["bg_dark"],
                                   fg=THEME["accent_light"], font=("Segoe UI", 9, "bold"))
        self._file_lbl.pack(side="left", padx=8)

        self._content_text = tk.Text(self._content_frame, bg=THEME["bg_panel"],
                                      fg=THEME["fg_text"], font=("Consolas", 9),
                                      relief="flat", state="disabled",
                                      wrap="none")
        sb_h = ttk.Scrollbar(self._content_frame, orient="horizontal",
                              command=self._content_text.xview)
        sb_v = ttk.Scrollbar(self._content_frame, orient="vertical",
                              command=self._content_text.yview)
        self._content_text.configure(xscrollcommand=sb_h.set,
                                      yscrollcommand=sb_v.set)
        sb_h.pack(side="bottom", fill="x")
        sb_v.pack(side="right",  fill="y")
        self._content_text.pack(fill="both", expand=True)

        # Syntax colours
        self._content_text.tag_configure("comment", foreground=FG_MUTED)
        self._content_text.tag_configure("keyword", foreground=ACCENT,
                                          font=("Consolas", 9, "bold"))
        self._content_text.tag_configure("string",  foreground=ACCENT3)
        self._content_text.tag_configure("define",  foreground=GOLD)
        self._content_text.tag_configure("number",  foreground=ACCENT2)
        self._content_text.tag_configure("highlight",background=GOLD,
                                          foreground="#000000")

    def _load_all(self):
        defs = sorted(self.cfg.extract_dir.rglob("*.def"))
        self._def_files = defs
        self._file_lb.delete(0, "end")
        for d in defs:
            rel = str(d.relative_to(self.cfg.extract_dir))
            self._file_lb.insert("end", rel)
        self._count_lbl.config(text=f"{len(defs)} .def files")
        self._status.set(f"Scripts: {len(defs)} .def files indexed")

    def _on_file_select(self, _):
        sel = self._file_lb.curselection()
        if not sel:
            return
        path = self._def_files[sel[0]]
        self._file_lbl.config(text=str(path.relative_to(self.cfg.extract_dir)))
        content = _read_def(path)
        self._render_content(content)

    def _render_content(self, content: str, highlight: str = ""):
        txt = self._content_text
        txt.configure(state="normal")
        txt.delete("1.0", "end")

        for lineno, line in enumerate(content.splitlines(), 1):
            start = txt.index("end")
            txt.insert("end", line + "\n")
            end = txt.index("end")

            # Syntax highlighting
            if line.strip().startswith("//"):
                txt.tag_add("comment", start, end)
            elif line.strip().startswith("#define"):
                txt.tag_add("define", start, end)
            elif re.search(r'\b(CHARACTER|WEAPON|ARMOR|SPELL|CLASS|BEGIN|END)\b', line):
                for m in re.finditer(r'\b(CHARACTER|WEAPON|ARMOR|SPELL|CLASS|BEGIN|END)\b', line):
                    s = f"{start}+{m.start()}c"
                    e = f"{start}+{m.end()}c"
                    txt.tag_add("keyword", s, e)
            # Strings
            for m in re.finditer(r'"[^"]*"', line):
                s = f"{start}+{m.start()}c"
                e = f"{start}+{m.end()}c"
                txt.tag_add("string", s, e)

        # Highlight search term
        if highlight:
            idx = "1.0"
            while True:
                idx = txt.search(highlight, idx, nocase=True, stopindex="end")
                if not idx:
                    break
                end = f"{idx}+{len(highlight)}c"
                txt.tag_add("highlight", idx, end)
                idx = end

        txt.configure(state="disabled")

    def _do_search(self):
        term = self._search_var.get().strip()
        if not term:
            self._results_frame.pack_forget()
            return

        matches = []
        for path in self._def_files:
            content = _read_def(path)
            for lineno, line in enumerate(content.splitlines(), 1):
                if term.lower() in line.lower():
                    matches.append((path, lineno, line.strip()))

        self._results_tv.delete(*self._results_tv.get_children())
        for path, lineno, text in matches[:500]:
            rel = str(path.relative_to(self.cfg.extract_dir))
            self._results_tv.insert("", "end", values=(rel, lineno, text),
                                     tags=(str(path),))

        self._results_frame.pack(fill="x", padx=4, pady=4)
        self._count_lbl.config(text=f"{len(matches)} matches for '{term}'")
        self._status.set(f"Found {len(matches)} matches for '{term}' across {len(self._def_files)} files")

    def _on_result_select(self, _):
        sel = self._results_tv.selection()
        if not sel:
            return
        vals = self._results_tv.item(sel[0], "values")
        rel_path_str = vals[0]
        lineno       = int(vals[1])
        term         = self._search_var.get().strip()

        path = self.cfg.extract_dir / rel_path_str
        if path.exists():
            # Find it in list
            for i, d in enumerate(self._def_files):
                if d == path:
                    self._file_lb.selection_clear(0, "end")
                    self._file_lb.selection_set(i)
                    self._file_lb.see(i)
                    break
            self._file_lbl.config(text=rel_path_str)
            content = _read_def(path)
            self._render_content(content, highlight=term)
            # Scroll to line
            self._content_text.configure(state="normal")
            self._content_text.see(f"{lineno}.0")
            self._content_text.configure(state="disabled")

    def _export_all(self):
        if not self._def_files:
            self._status.set("No .def files loaded")
            return
        dest = self.cfg.renders_dir / "Scripts"
        dest.mkdir(parents=True, exist_ok=True)
        ok = skip = 0
        for path in self._def_files:
            try:
                import shutil
                shutil.copy2(str(path), str(dest / path.name))
                ok += 1
            except Exception:
                skip += 1
        self._status.set(f"Scripts exported: {ok} files → {dest}")
