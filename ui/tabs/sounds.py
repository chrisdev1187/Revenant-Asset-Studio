import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from core.constants import *
from ui.widgets import *
from core.parsers import *
class SoundsTab(tk.Frame):
    """Browse and play all game audio: music tracks + voice/SFX MP3s."""

    def __init__(self, parent, config, status: StatusBar):
        self.cfg = config
        super().__init__(parent, bg=BG_MID)
        self._status       = status
        self._sounds: List[Dict] = []
        self._current_proc = None
        self._build_ui()
        self.after(600, self._load_all)

    def _build_ui(self):
        bar = tk.Frame(self, bg=BG_DARK, pady=4)
        bar.pack(fill="x")

        tk.Label(bar, text="Filter:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 10)).pack(side="left", padx=(10, 4))
        self._flt_var = tk.StringVar()
        tk.Entry(bar, textvariable=self._flt_var,
                 bg=BG_PANEL, fg=FG_TEXT, insertbackground=FG_TEXT,
                 font=("Segoe UI", 10), relief="flat", width=28
                 ).pack(side="left", padx=4)
        self._flt_var.trace_add("write", self._filter)

        tk.Button(bar, text="▶ Play", bg=ACCENT3, fg="#000", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10,
                  command=self._play_selected).pack(side="left", padx=8)
        tk.Button(bar, text="■ Stop", bg=RED, fg="white", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10,
                  command=self._stop).pack(side="left", padx=2)

        self._count_lbl = tk.Label(bar, text="", bg=BG_DARK, fg=FG_DIM,
                                   font=("Segoe UI", 9))
        self._count_lbl.pack(side="right", padx=12)

        pane = tk.PanedWindow(self, orient="horizontal", bg=BG_DARK,
                              sashwidth=6, sashrelief="flat")
        pane.pack(fill="both", expand=True)

        tv_f = tk.Frame(pane, bg=BG_MID)
        pane.add(tv_f, minsize=560)
        cols = ("name", "cat", "size")
        self._tv = ttk.Treeview(tv_f, columns=cols, show="headings",
                                selectmode="browse")
        self._tv.heading("name", text="File",     anchor="w")
        self._tv.heading("cat",  text="Category", anchor="w")
        self._tv.heading("size", text="KB",        anchor="center")
        self._tv.column("name", width=320, stretch=True)
        self._tv.column("cat",  width=120, stretch=False)
        self._tv.column("size", width=60,  stretch=False, anchor="center")
        sb = ttk.Scrollbar(tv_f, orient="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._tv.pack(fill="both", expand=True)
        self._tv.bind("<Double-Button-1>", lambda e: self._play_selected())

        # Detail panel
        det = tk.Frame(pane, bg=BG_PANEL, padx=12, pady=12)
        pane.add(det, minsize=200)
        tk.Label(det, text="SOUND DETAILS", bg=BG_PANEL, fg=ACCENT2,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Separator(det).pack(fill="x", pady=6)
        self._det_lbl = tk.Label(det, text="Select a file to preview",
                                 bg=BG_PANEL, fg=FG_DIM,
                                 font=("Segoe UI", 9), wraplength=180,
                                 justify="left", anchor="w")
        self._det_lbl.pack(anchor="w")

    def _load_all(self):
        self._status.set("Scanning sound files…")
        sounds = []
        # Music OGG tracks
        for snd_dir in self.cfg.extract_dir.rglob("Sound"):
            if not snd_dir.is_dir():
                continue
            for f in sorted(snd_dir.iterdir()):
                if f.suffix.lower() in ('.ogg', '.wav'):
                    cat = "Music" if f.suffix.lower() == '.ogg' else "SFX"
                    sounds.append({"name": f.name, "cat": cat,
                                   "path": f, "size_kb": f.stat().st_size // 1024})
            # English voice / SFX subfolder
            eng = snd_dir / "english"
            if eng.is_dir():
                for f in sorted(eng.iterdir()):
                    if f.suffix.lower() in ('.mp3', '.wav', '.ogg'):
                        sounds.append({"name": f.name, "cat": "Voice/SFX",
                                       "path": f, "size_kb": f.stat().st_size // 1024})
        self._sounds = sounds
        self._populate(sounds)
        self._count_lbl.config(text=f"{len(sounds)} sounds")
        self._status.set(f"Sounds: {len(sounds)} files indexed")

    def _populate(self, data: List[Dict]):
        self._tv.delete(*self._tv.get_children())
        for s in data:
            self._tv.insert("", "end",
                values=(s["name"], s["cat"], s["size_kb"]),
                tags=(str(s["path"]),))

    def _filter(self, *_):
        flt = self._flt_var.get().strip().lower()
        filtered = ([s for s in self._sounds
                     if flt in s["name"].lower() or flt in s["cat"].lower()]
                    if flt else self._sounds)
        self._populate(filtered)
        self._count_lbl.config(text=f"{len(filtered)} / {len(self._sounds)}")

    def _selected_path(self) -> Optional[Path]:
        sel = self._tv.selection()
        if not sel:
            return None
        tags = self._tv.item(sel[0], "tags")
        return Path(tags[0]) if tags else None

    def _play_selected(self):
        p = self._selected_path()
        if p is None or not p.exists():
            self._status.set("Select a sound file first.")
            return
        self._stop()
        self._status.set(f"Playing: {p.name}")
        self._det_lbl.config(text=f"{p.name}\n{p.stat().st_size // 1024} KB")
        import subprocess, sys
        try:
            if sys.platform == "win32":
                import os
                os.startfile(str(p))
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except Exception as e:
            self._status.set(f"Playback error: {e}")

    def _stop(self):
        if self._current_proc and self._current_proc.poll() is None:
            try:
                self._current_proc.terminate()
            except Exception:
                pass
        self._current_proc = None


# ═══════════════════════════════════════════════════════════════════════════════
#  CINEMATIX TAB
# ═══════════════════════════════════════════════════════════════════════════════
