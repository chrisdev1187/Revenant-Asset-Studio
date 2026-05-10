import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from core.constants import *
from ui.widgets import *
from core.parsers import *
class CinematiXTab(tk.Frame):
    """Browse and launch all Smacker (.SMK) video files."""

    def __init__(self, parent, config, status: StatusBar):
        self.cfg = config
        super().__init__(parent, bg=BG_MID)
        self._status = status
        self._videos: List[Dict] = []
        self._build_ui()
        self.after(300, self._load_all)

    def _build_ui(self):
        bar = tk.Frame(self, bg=BG_DARK, pady=4)
        bar.pack(fill="x")
        tk.Label(bar, text="Revenant FMV / Cinematix Videos", bg=BG_DARK,
                 fg=FG_DIM, font=("Segoe UI", 10)).pack(side="left", padx=10)
        tk.Button(bar, text="▶ Play", bg=ACCENT, fg="white", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10,
                  command=self._play_selected).pack(side="left", padx=8)
        self._count_lbl = tk.Label(bar, text="", bg=BG_DARK, fg=FG_DIM,
                                   font=("Segoe UI", 9))
        self._count_lbl.pack(side="right", padx=12)

        pane = tk.PanedWindow(self, orient="horizontal", bg=BG_DARK,
                              sashwidth=6, sashrelief="flat")
        pane.pack(fill="both", expand=True)

        tv_f = tk.Frame(pane, bg=BG_MID)
        pane.add(tv_f, minsize=400)
        cols = ("name", "size", "path")
        self._tv = ttk.Treeview(tv_f, columns=cols, show="headings",
                                selectmode="browse")
        self._tv.heading("name", text="Video File", anchor="w")
        self._tv.heading("size", text="Size (MB)",  anchor="center")
        self._tv.heading("path", text="Location",   anchor="w")
        self._tv.column("name", width=240, stretch=False)
        self._tv.column("size", width=80,  stretch=False, anchor="center")
        self._tv.column("path", width=300, stretch=True)
        sb = ttk.Scrollbar(tv_f, orient="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._tv.pack(fill="both", expand=True)
        self._tv.bind("<Double-Button-1>", lambda e: self._play_selected())

        det = tk.Frame(pane, bg=BG_PANEL, padx=14, pady=12)
        pane.add(det, minsize=240)
        tk.Label(det, text="VIDEO INFO", bg=BG_PANEL, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Separator(det).pack(fill="x", pady=6)
        self._det_lbl = tk.Label(det, text="Select a video to preview info",
                                 bg=BG_PANEL, fg=FG_DIM, font=("Segoe UI", 9),
                                 wraplength=200, justify="left", anchor="w")
        self._det_lbl.pack(anchor="w")
        tk.Label(det, text="\nDouble-click or press ▶ Play to open\nwith the system's default video player\n(install VLC for best SMK support).",
                 bg=BG_PANEL, fg=FG_MUTED, font=("Segoe UI", 8),
                 justify="left").pack(anchor="w", pady=8)

    def _load_all(self):
        self._status.set("Scanning for SMK video files…")
        seen: set = set()
        videos = []
        search_dirs = [Path("Disk2")] + [self.cfg.game_dir, self.cfg.extract_dir]
        for d in search_dirs:
            if not d.exists():
                continue
            for f in d.rglob("*.smk"):
                key = f.name.upper()
                if key not in seen:
                    seen.add(key)
                    videos.append({"name": f.name,
                                   "path": f,
                                   "size_mb": f.stat().st_size / (1024 * 1024)})
            for f in d.rglob("*.SMK"):
                key = f.name.upper()
                if key not in seen:
                    seen.add(key)
                    videos.append({"name": f.name,
                                   "path": f,
                                   "size_mb": f.stat().st_size / (1024 * 1024)})
        videos.sort(key=lambda x: x["name"].upper())
        self._videos = videos
        self._tv.delete(*self._tv.get_children())
        for v in videos:
            self._tv.insert("", "end",
                values=(v["name"], f"{v['size_mb']:.1f}", str(v["path"].parent)),
                tags=(str(v["path"]),))
        self._count_lbl.config(text=f"{len(videos)} video(s)")
        if videos:
            self._status.set(f"Cinematix: {len(videos)} SMK video(s) found")
        else:
            self._status.set("No SMK videos found — check GOG install path")

    def _play_selected(self):
        sel = self._tv.selection()
        if not sel:
            self._status.set("Select a video first.")
            return
        tags = self._tv.item(sel[0], "tags")
        if not tags:
            return
        p = Path(tags[0])
        if not p.exists():
            self._status.set(f"File not found: {p}")
            return
        import sys, os
        self._det_lbl.config(
            text=f"{p.name}\n{p.stat().st_size / (1024*1024):.1f} MB\n{p.parent}")
        self._status.set(f"Opening: {p.name}")
        try:
            if sys.platform == "win32":
                os.startfile(str(p))
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(p)])
        except Exception as e:
            self._status.set(f"Could not open video: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  UI Resources CATEGORIES
# ═══════════════════════════════════════════════════════════════════════════════

_UI_CATEGORIES: Dict[str, List[str]] = {
    "Menus":        ["splash", "menus", "selstarttex", "selstartnotex",
                     "ingamemenutex", "ingamemenunotex", "death", "credits",
                     "demo", "exit"],
    "Save / Load":  ["loadgametex", "loadgamenotex", "loadgamealpha", "loadbar",
                     "savegametex", "savegamenotex", "savegamealpha",
                     "userinfonotex", "userinfotex"],
    "Character":    ["createchartex", "createcharnotex", "createcharalpha"],
    "HUD":          ["bottombar", "health", "stamina", "startbar",
                     "statusbar", "statusbarnotex", "sidepane",
                     "sidebartabs", "sidebartabsnotex"],
    "Inventory":    ["inventory", "equippane", "equipscr", "intrface",
                     "book", "buysell", "gamedata", "scroll", "spellscroll",
                     "spellpane", "spellicons", "automap"],
    "Dialog":       ["dialog", "dlg", "dlgfont", "dlgfonts"],
    "Fonts":        ["gamefont", "sysfont", "scrlfont", "smlfont", "gnrmfont"],
    "Multiplayer":  ["hostgame", "joingame", "connect", "mpingame",
                     "mpingamenotex", "mpingametex"],
    "Gold / Items": ["medgold", "medgoldg", "medgoldglow", "medgolds",
                     "medgoldsel", "medgoldshad", "medgoldsilv",
                     "smallgold", "smallgoldg", "smallgoldglow", "smallgolds",
                     "smallgoldsel", "smallgoldshad", "smallgoldsilv"],
    "Widgets":      ["widgetstex", "widgetsnotex", "widgetsalpha", "imagery"],
    "Editor (GCK)": ["editor"],
}
