from __future__ import annotations
import re
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
import threading
from ui.theme import THEME, FONTS
from ui.widgets import StatusBar, add_tooltip, LoadingOverlay
from archive_extractor import extract_archive, REVENANT_ARCHIVES
from core.config import Config

class LibraryTab(tk.Frame):
    def __init__(self, parent, config: Config, status: StatusBar):
        super().__init__(parent, bg=THEME["bg_mid"])
        self.cfg = config
        self._status = status
        self._build_ui()

    def _build_ui(self):
        # Toolbar
        bar = tk.Frame(self, bg=THEME["bg_dark"], pady=8)
        bar.pack(fill="x")

        tk.Label(bar, text="Archive Management", bg=THEME["bg_dark"],
                 fg=THEME["accent_light"], font=FONTS["header"]).pack(side="left", padx=20)

        # Main Content
        self._main = tk.Frame(self, bg=THEME["bg_mid"], padx=20, pady=20)
        self._main.pack(fill="both", expand=True)

        # Archive List
        self._tree = ttk.Treeview(self._main, columns=("status", "size"), show="headings", height=10)
        self._tree.heading("status", text="Status")
        self._tree.heading("size", text="Size")
        self._tree.pack(fill="both", expand=True)

        # Action Buttons
        btn_f = tk.Frame(self._main, bg=THEME["bg_mid"], pady=10)
        btn_f.pack(fill="x")

        self._btn_extract = tk.Button(btn_f, text="Extract All Archives", bg=THEME["accent"],
                                      fg="white", relief="flat", font=FONTS["body_bold"],
                                      padx=20, command=self._extract_all)
        self._btn_extract.pack(side="left")
        add_tooltip(self._btn_extract, "Unpacks .RVR and .RVI files into the extracted folder.")

        self._refresh()

    def _refresh(self):
        self._tree.delete(*self._tree.get_children())
        for ext, desc in REVENANT_ARCHIVES.items():
            for f in self.cfg.game_dir.glob(f"*{ext}"):
                out_dir = self.cfg.extract_dir / f.stem
                status = "Extracted" if out_dir.exists() and any(out_dir.iterdir()) else "Not Extracted"
                size = f"{f.stat().st_size / (1024*1024):.1f} MB"
                self._tree.insert("", "end", text=f.name, values=(status, size))

    def _extract_all(self):
        self._btn_extract.config(state="disabled")
        self._status.set("Extracting archives...", "info")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        archives = []
        for ext in REVENANT_ARCHIVES:
            for f in self.cfg.game_dir.glob(f"*{ext}"):
                archives.append(f)

        total = len(archives)
        for i, arc in enumerate(archives):
            self.after(0, lambda name=arc.name: self._status.set(f"Extracting {name}...", "info"))
            self.after(0, lambda p=(i/total)*100: self._status.progress(p))

            out_dir = self.cfg.extract_dir / arc.stem
            extract_archive(arc, out_dir, overwrite=True)

        self.after(0, self._on_done)

    def _on_done(self):
        self._btn_extract.config(state="normal")
        self._status.set("Extraction complete!", "success")
        self._status.progress(0, visible=False)
        self._refresh()
        messagebox.showinfo("Extraction", "All archives have been extracted successfully.")
