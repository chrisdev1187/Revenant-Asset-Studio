import tkinter as tk
import os
import re
from tkinter import ttk, filedialog, messagebox
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from ui.theme import THEME, FONTS
from core.constants import *
from ui.widgets import *
from core.parsers import *
class AhkuilonTab(tk.Frame):
    _AREAS = ["arakna", "cave", "dungeon", "forest", "keep",
              "labyrinth", "ruins", "town", "tower"]

    def __init__(self, parent, config, status: StatusBar):
        self.cfg = config
        super().__init__(parent, bg=THEME["bg_mid"])
        self._status   = status
        self._cur_path : Optional[Path] = None
        self._objects  : List[Dict] = []
        self._map_dots : List[Tuple] = []
        self._build_ui()
        self.after(300, self._load_files)

    def _build_ui(self):
        bar = tk.Frame(self, bg=THEME["bg_dark"], pady=4)
        bar.pack(fill="x")
        tk.Label(bar, text="Ahkuilon — Zone Scripts", bg=THEME["bg_dark"], fg=THEME["accent"],
                 font=FONTS["header"]).pack(side="left", padx=10)
        self._count_lbl = tk.Label(bar, text="", bg=THEME["bg_dark"], fg=THEME["fg_dim"],
                                   font=FONTS["small"])
        self._count_lbl.pack(side="left", padx=8)
        tk.Button(bar, text="Export Scripts", bg=ACCENT2, fg="#000",
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=8,
                  command=self._export_all).pack(side="right", padx=4)

        pane = tk.PanedWindow(self, orient="horizontal", bg=THEME["bg_dark"],
                              sashwidth=4)
        pane.pack(fill="both", expand=True)

        # Left: file tree
        left = tk.Frame(pane, bg=THEME["bg_panel"], width=200)
        pane.add(left, minsize=150)
        tk.Label(left, text="Scripts", bg=THEME["bg_panel"], fg=THEME["fg_dim"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8, pady=(4, 0))
        sb = ttk.Scrollbar(left, orient="vertical")
        sb.pack(side="right", fill="y")
        self._tv = ttk.Treeview(left, yscrollcommand=sb.set,
                                selectmode="browse", show="tree")
        sb.config(command=self._tv.yview)
        self._tv.pack(fill="both", expand=True)
        self._tv.bind("<<TreeviewSelect>>", self._on_select)

        # Right: text + map
        right = tk.Frame(pane, bg=THEME["bg_dark"])
        pane.add(right, minsize=500)

        v_pane = tk.PanedWindow(right, orient="vertical", bg=THEME["bg_dark"],
                                sashwidth=4)
        v_pane.pack(fill="both", expand=True)

        # Text viewer
        txt_frame = tk.Frame(v_pane, bg=THEME["bg_panel"])
        v_pane.add(txt_frame, minsize=200)

        info_bar = tk.Frame(txt_frame, bg=THEME["bg_mid"], pady=3)
        info_bar.pack(fill="x")
        self._file_lbl = tk.Label(info_bar, text="Select a script", bg=THEME["bg_mid"],
                                  fg=THEME["accent"], font=("Segoe UI", 10, "bold"))
        self._file_lbl.pack(side="left", padx=10)
        self._obj_lbl = tk.Label(info_bar, text="", bg=THEME["bg_mid"], fg=THEME["fg_dim"],
                                 font=FONTS["small"])
        self._obj_lbl.pack(side="left", padx=8)
        tk.Button(info_bar, text="Open in Explorer", bg=THEME["bg_mid"], fg=THEME["fg_dim"],
                  relief="flat", font=("Segoe UI", 8),
                  command=self._open_in_explorer).pack(side="right", padx=8)

        sb_h = ttk.Scrollbar(txt_frame, orient="horizontal")
        sb_h.pack(side="bottom", fill="x")
        sb_v = ttk.Scrollbar(txt_frame, orient="vertical")
        sb_v.pack(side="right", fill="y")
        self._txt = tk.Text(txt_frame, bg=THEME["bg_panel"], fg=THEME["fg_text"],
                            font=("Consolas", 9), wrap="none", relief="flat",
                            xscrollcommand=sb_h.set, yscrollcommand=sb_v.set,
                            state="disabled")
        self._txt.pack(fill="both", expand=True)
        sb_h.config(command=self._txt.xview)
        sb_v.config(command=self._txt.yview)

        self._txt.tag_configure("block",   foreground=ACCENT,
                                font=("Consolas", 9, "bold"))
        self._txt.tag_configure("trigger", foreground=ACCENT2,
                                font=("Consolas", 9, "bold"))
        self._txt.tag_configure("action",  foreground=ACCENT3)
        self._txt.tag_configure("cmd",     foreground=GOLD)
        self._txt.tag_configure("prop",    foreground=RED)
        self._txt.tag_configure("number",  foreground="#a8dadc")
        self._txt.tag_configure("comment", foreground=FG_MUTED,
                                font=("Consolas", 9, "italic"))
        self._txt.tag_configure("string",  foreground=ACCENT3)

        # Object map
        map_frame = tk.Frame(v_pane, bg=THEME["bg_dark"])
        v_pane.add(map_frame, minsize=160)

        map_bar = tk.Frame(map_frame, bg=THEME["bg_mid"], pady=3)
        map_bar.pack(fill="x")
        tk.Label(map_bar, text="Object Map  (CUBE triggers)", bg=THEME["bg_mid"],
                 fg=THEME["accent_light"], font=("Segoe UI", 9, "bold")).pack(side="left", padx=10)
        self._map_info = tk.Label(map_bar, text="", bg=THEME["bg_mid"], fg=THEME["fg_dim"],
                                  font=("Segoe UI", 8))
        self._map_info.pack(side="left", padx=8)

        self._map_canvas = tk.Canvas(map_frame, bg="#0a0a12", bd=0,
                                     highlightthickness=0)
        self._map_canvas.pack(fill="both", expand=True)
        self._map_canvas.bind("<Configure>", lambda e: self._draw_map())
        self._map_canvas.bind("<Motion>", self._on_map_hover)

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_files(self):
        self._tv.delete(*self._tv.get_children())
        ahk = self.cfg.ahkuilon
        total = 0

        scr_node = self._tv.insert("", "end", text="  Zone Scripts",
                                   open=True, tags=("cat",))
        for area in self._AREAS:
            p = ahk / f"{area}.s"
            if p.exists():
                self._tv.insert(scr_node, "end", text=f"  {area}.s",
                                values=(str(p),), tags=("script",))
                total += 1

        def_node = self._tv.insert("", "end", text="  Definitions",
                                   open=False, tags=("cat",))
        for p in sorted(ahk.glob("*.def")):
            self._tv.insert(def_node, "end", text=f"  {p.name}",
                            values=(str(p),), tags=("def",))
            total += 1

        self._tv.tag_configure("cat",    foreground=ACCENT2,
                               font=("Segoe UI", 9, "bold"))
        self._tv.tag_configure("script", foreground=ACCENT3,
                               font=("Consolas", 9))
        self._tv.tag_configure("def",    foreground=GOLD,
                               font=("Consolas", 9))
        self._count_lbl.config(text=f"{total} files")

    # ── Selection / display ───────────────────────────────────────────────────

    def _on_select(self, _=None):
        sel = self._tv.selection()
        if not sel:
            return
        vals = self._tv.item(sel[0], "values")
        if not vals:
            return
        path = Path(vals[0])
        if path == self._cur_path:
            return
        self._cur_path = path
        self._load_script(path)

    def _load_script(self, path: Path):
        self._file_lbl.config(text=path.name)
        try:
            content = path.read_text(encoding="latin-1")
        except Exception as e:
            self._status.set(f"Read error: {e}")
            return

        self._objects = parse_script_objects(content)
        lines = [l for l in content.splitlines() if l.strip()]
        self._obj_lbl.config(
            text=f"{len(self._objects)} CUBE objects  |  {len(lines)} lines")

        self._txt.configure(state="normal")
        self._txt.delete("1.0", "end")
        self._txt.insert("end", content)

        for tag, pat in _SCRIPT_KW.items():
            for m in pat.finditer(content):
                line = content[:m.start()].count('\n') + 1
                col  = m.start() - content[:m.start()].rfind('\n') - 1
                self._txt.tag_add(tag, f"{line}.{col}",
                                  f"{line}.{col + len(m.group())}")

        self._txt.configure(state="disabled")
        self._draw_map()
        self._status.set(f"{path.name}  —  {len(self._objects)} objects")

    def _open_in_explorer(self):
        if self._cur_path and self._cur_path.exists():
            os.startfile(str(self._cur_path.parent))

    # ── Object map ────────────────────────────────────────────────────────────

    def _draw_map(self):
        c = self._map_canvas
        c.delete("all")
        objs = self._objects
        cw = max(1, c.winfo_width())
        ch = max(1, c.winfo_height())

        if not objs:
            c.create_text(cw // 2, ch // 2, text="No CUBE objects in this script",
                          fill=FG_MUTED, font=FONTS["body"])
            return

        pad = 24
        xs = [o["cx"] for o in objs]
        ys = [o["cy"] for o in objs]
        mn_x, mx_x = min(xs), max(xs)
        mn_y, mx_y = min(ys), max(ys)
        dx = max(mx_x - mn_x, 1)
        dy = max(mx_y - mn_y, 1)
        sx = (cw - pad * 2) / dx
        sy = (ch - pad * 2) / dy
        scale = min(sx, sy)

        def px(x, pad=pad, mn_x=mn_x, scale=scale): return int(pad + (x - mn_x) * scale)
        def py(y, pad=pad, mn_y=mn_y, scale=scale): return int(pad + (y - mn_y) * scale)

        # Grid
        steps_x = max(1, dx // 8)
        steps_y = max(1, dy // 6)
        for gx in range(int(mn_x), int(mx_x) + 1, steps_x):
            x = px(gx)
            c.create_line(x, pad, x, ch - pad, fill=BORDER, width=1)
            c.create_text(x, ch - pad + 8, text=str(gx),
                          fill=FG_MUTED, font=("Segoe UI", 6), anchor="n")
        for gy in range(int(mn_y), int(mx_y) + 1, steps_y):
            y = py(gy)
            c.create_line(pad, y, cw - pad, y, fill=BORDER, width=1)
            c.create_text(pad - 2, y, text=str(gy),
                          fill=FG_MUTED, font=("Segoe UI", 6), anchor="e")

        # Dots
        self._map_dots = []
        for o in objs:
            x, y = px(o["cx"]), py(o["cy"])
            r = 5
            c.create_oval(x - r, y - r, x + r, y + r,
                          fill=ACCENT2, outline=ACCENT, width=1)
            self._map_dots.append((x, y, o["name"]))

        self._map_info.config(
            text=f"x {mn_x}…{mx_x}  y {mn_y}…{mx_y}  |  {len(objs)} objects")

    def _on_map_hover(self, event):
        if not self._map_dots:
            return
        nearest = min(self._map_dots,
                      key=lambda t: (t[0] - event.x) ** 2 + (t[1] - event.y) ** 2)
        dist_sq = (nearest[0] - event.x) ** 2 + (nearest[1] - event.y) ** 2
        if dist_sq < 400:
            self._map_info.config(text=f"  ▸  {nearest[2]}")

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_all(self):
        import shutil
        dest = self.cfg.renders_dir / "AhkuilonScripts"
        dest.mkdir(parents=True, exist_ok=True)
        ok = 0
        for p in list(self.cfg.ahkuilon.glob("*.s")) + list(self.cfg.ahkuilon.glob("*.def")):
            try:
                shutil.copy2(str(p), str(dest / p.name))
                ok += 1
            except Exception:
                pass
        self._status.set(f"Exported {ok} scripts → {dest}")
