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
class EquipmentTab(tk.Frame):
    def __init__(self, parent, config, status: StatusBar):
        self.cfg = config
        super().__init__(parent, bg=THEME["bg_mid"])
        self._status  = status
        self._weapons = []
        self._armors  = []
        self._build_ui()
        self.after(300, self._load_all)

    def _build_ui(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=4, pady=4)

        self._wpn_frame = tk.Frame(nb, bg=THEME["bg_mid"])
        self._arm_frame = tk.Frame(nb, bg=THEME["bg_mid"])
        nb.add(self._wpn_frame, text=f"  Weapons  ")
        nb.add(self._arm_frame, text=f"  Armour   ")

        self._build_weapon_panel(self._wpn_frame)
        self._build_armor_panel (self._arm_frame)

    def _build_weapon_panel(self, parent):
        # Toolbar
        bar = tk.Frame(parent, bg=THEME["bg_dark"], pady=4)
        bar.pack(fill="x")
        self._wpn_filter_var = tk.StringVar()
        tk.Label(bar, text="Filter:", bg=THEME["bg_dark"], fg=THEME["fg_dim"],
                 font=FONTS["body"]).pack(side="left", padx=(10,4))
        tk.Entry(bar, textvariable=self._wpn_filter_var,
                  bg=THEME["bg_panel"], fg=THEME["fg_text"], insertbackground=FG_TEXT,
                  font=FONTS["body"], relief="flat", width=20
                  ).pack(side="left", padx=4)
        self._wpn_filter_var.trace_add("write", self._filter_weapons)
        tk.Button(bar, text="Export All Icons", bg=ACCENT2, fg="#000",
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=8,
                  command=self._export_all_weapons).pack(side="right", padx=4)
        self._wpn_count = tk.Label(bar, text="", bg=THEME["bg_dark"], fg=THEME["fg_dim"],
                                    font=FONTS["small"])
        self._wpn_count.pack(side="right", padx=12)

        # Table + detail pane
        pane = tk.PanedWindow(parent, orient="horizontal", bg=THEME["bg_dark"],
                               sashwidth=6, sashrelief="flat")
        pane.pack(fill="both", expand=True)

        # Treeview
        tv_frame = tk.Frame(pane, bg=THEME["bg_mid"])
        pane.add(tv_frame, minsize=400)

        cols = ("name","type","dmg","value","min_str")
        self._wpn_tv = ttk.Treeview(tv_frame, columns=cols, show="headings",
                                      selectmode="browse")
        self._wpn_tv.heading("name",    text="Weapon",         anchor="w")
        self._wpn_tv.heading("type",    text="Type",           anchor="w")
        self._wpn_tv.heading("dmg",     text="Damage",         anchor="center")
        self._wpn_tv.heading("value",   text="Value",          anchor="center")
        self._wpn_tv.heading("min_str", text="Min STR",        anchor="center")
        self._wpn_tv.column("name",    width=200, stretch=True)
        self._wpn_tv.column("type",    width=110, stretch=False)
        self._wpn_tv.column("dmg",     width=60,  stretch=False, anchor="center")
        self._wpn_tv.column("value",   width=70,  stretch=False, anchor="center")
        self._wpn_tv.column("min_str", width=65,  stretch=False, anchor="center")

        sb = ttk.Scrollbar(tv_frame, orient="vertical",
                            command=self._wpn_tv.yview)
        self._wpn_tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._wpn_tv.pack(fill="both", expand=True)
        self._wpn_tv.bind("<<TreeviewSelect>>", self._on_weapon_select)

        # Detail
        det = tk.Frame(pane, bg=THEME["bg_panel"], padx=12, pady=12)
        pane.add(det, minsize=220)
        tk.Label(det, text="WEAPON DETAILS", bg=THEME["bg_panel"], fg=THEME["gold"],
                 font=FONTS["header"]).pack(anchor="w")
        ttk.Separator(det).pack(fill="x", pady=6)
        self._wpn_detail = tk.Text(det, bg=THEME["bg_panel"], fg=THEME["fg_text"],
                                    font=("Consolas", 9), relief="flat",
                                    state="disabled", wrap="word", height=20)
        self._wpn_detail.pack(fill="both", expand=True)
        self._wpn_detail.tag_configure("h",  foreground=GOLD, font=("Segoe UI",10,"bold"))
        self._wpn_detail.tag_configure("kv", foreground=ACCENT2, font=("Segoe UI",9))

        # tn thumbnail display
        self._wpn_img_lbl = tk.Label(det, bg=THEME["bg_panel"])
        self._wpn_img_lbl.pack(pady=4)

    def _build_armor_panel(self, parent):
        bar = tk.Frame(parent, bg=THEME["bg_dark"], pady=4)
        bar.pack(fill="x")
        self._arm_filter_var = tk.StringVar()
        tk.Label(bar, text="Filter:", bg=THEME["bg_dark"], fg=THEME["fg_dim"],
                 font=FONTS["body"]).pack(side="left", padx=(10,4))
        tk.Entry(bar, textvariable=self._arm_filter_var,
                  bg=THEME["bg_panel"], fg=THEME["fg_text"], insertbackground=FG_TEXT,
                  font=FONTS["body"], relief="flat", width=20
                  ).pack(side="left", padx=4)
        self._arm_filter_var.trace_add("write", self._filter_armors)
        tk.Button(bar, text="Export All Icons", bg=ACCENT2, fg="#000",
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=8,
                  command=self._export_all_armors).pack(side="right", padx=4)
        self._arm_count = tk.Label(bar, text="", bg=THEME["bg_dark"], fg=THEME["fg_dim"],
                                    font=FONTS["small"])
        self._arm_count.pack(side="right", padx=12)

        pane = tk.PanedWindow(parent, orient="horizontal", bg=THEME["bg_dark"],
                               sashwidth=6, sashrelief="flat")
        pane.pack(fill="both", expand=True)

        tv_frame = tk.Frame(pane, bg=THEME["bg_mid"])
        pane.add(tv_frame, minsize=400)

        cols = ("name","slot","prot","value","min_str")
        self._arm_tv = ttk.Treeview(tv_frame, columns=cols, show="headings",
                                      selectmode="browse")
        self._arm_tv.heading("name",  text="Armour",    anchor="w")
        self._arm_tv.heading("slot",  text="Slot",      anchor="w")
        self._arm_tv.heading("prot",  text="Protection",anchor="center")
        self._arm_tv.heading("value", text="Value",     anchor="center")
        self._arm_tv.heading("min_str",text="Min STR",  anchor="center")
        self._arm_tv.column("name",   width=220, stretch=True)
        self._arm_tv.column("slot",   width=90,  stretch=False)
        self._arm_tv.column("prot",   width=80,  stretch=False, anchor="center")
        self._arm_tv.column("value",  width=70,  stretch=False, anchor="center")
        self._arm_tv.column("min_str",width=65,  stretch=False, anchor="center")

        sb2 = ttk.Scrollbar(tv_frame, orient="vertical",
                             command=self._arm_tv.yview)
        self._arm_tv.configure(yscrollcommand=sb2.set)
        sb2.pack(side="right", fill="y")
        self._arm_tv.pack(fill="both", expand=True)
        self._arm_tv.bind("<<TreeviewSelect>>", self._on_armor_select)

        det2 = tk.Frame(pane, bg=THEME["bg_panel"], padx=12, pady=12)
        pane.add(det2, minsize=220)
        tk.Label(det2, text="ARMOUR DETAILS", bg=THEME["bg_panel"], fg=THEME["success"],
                 font=FONTS["header"]).pack(anchor="w")
        ttk.Separator(det2).pack(fill="x", pady=6)
        self._arm_detail = tk.Text(det2, bg=THEME["bg_panel"], fg=THEME["fg_text"],
                                    font=("Consolas", 9), relief="flat",
                                    state="disabled", wrap="word", height=20)
        self._arm_detail.pack(fill="both", expand=True)
        self._arm_detail.tag_configure("h",  foreground=ACCENT3, font=("Segoe UI",10,"bold"))
        self._arm_detail.tag_configure("kv", foreground=ACCENT2, font=("Segoe UI",9))

        # tn thumbnail display
        self._arm_img_lbl = tk.Label(det2, bg=THEME["bg_panel"])
        self._arm_img_lbl.pack(pady=4)

    def _load_all(self):
        self._status.set("Parsing weapon.def...")
        self._weapons = parse_weapon_def(self.cfg)
        self._status.set("Parsing armor.def...")
        self._armors  = parse_armor_def(self.cfg)
        self._populate_weapons(self._weapons)
        self._populate_armors (self._armors)
        self._wpn_count.config(text=f"{len(self._weapons)} weapons")
        self._arm_count.config(text=f"{len(self._armors)} armour pieces")
        self._status.set(
            f"Equipment loaded: {len(self._weapons)} weapons, {len(self._armors)} armour pieces")

    def _populate_weapons(self, data: List[Dict]):
        self._wpn_tv.delete(*self._wpn_tv.get_children())
        for w in sorted(data, key=lambda x: -x["damage"]):
            self._wpn_tv.insert("", "end",
                values=(w["name"], w["type_name"],
                        w["damage"], w["value"], w["min_str"]),
                tags=(w["name"],))

    def _populate_armors(self, data: List[Dict]):
        self._arm_tv.delete(*self._arm_tv.get_children())
        for a in sorted(data, key=lambda x: -x["protection"]):
            self._arm_tv.insert("", "end",
                values=(a["name"], a["slot_name"],
                        a["protection"], a["value"], a["min_str"]),
                tags=(a["name"],))

    def _filter_weapons(self, *_):
        flt = self._wpn_filter_var.get().strip().lower()
        filtered = [w for w in self._weapons
                    if flt in w["name"].lower() or flt in w["type_name"].lower()
                    ] if flt else self._weapons
        self._populate_weapons(filtered)
        self._wpn_count.config(text=f"{len(filtered)} / {len(self._weapons)}")

    def _filter_armors(self, *_):
        flt = self._arm_filter_var.get().strip().lower()
        filtered = [a for a in self._armors
                    if flt in a["name"].lower() or flt in a["slot_name"].lower()
                    ] if flt else self._armors
        self._populate_armors(filtered)
        self._arm_count.config(text=f"{len(filtered)} / {len(self._armors)}")

    def _on_weapon_select(self, _):
        sel = self._wpn_tv.selection()
        if not sel:
            return
        vals = self._wpn_tv.item(sel[0], "values")
        name = vals[0]
        w = next((x for x in self._weapons if x["name"] == name), None)
        if not w:
            return
        txt = self._wpn_detail
        txt.configure(state="normal")
        txt.delete("1.0", "end")
        txt.insert("end", f"{w['name']}\n", "h")

        def row(k, v, txt=txt):
            txt.insert("end", f"  {k:<18}", "kv")
            txt.insert("end", f"{v}\n")

        row("Type",         w["type_name"])
        row("Damage",       str(w["damage"]))
        row("Damage Mod",   str(w["damage_mod"]))
        row("Value (gold)", str(w["value"]))
        row("Min Strength", str(w["min_str"]))
        row("Poison",       str(w["poison"]))
        row("Combining",    str(w["combining"]))
        txt.configure(state="disabled")

        # Try to load .tn thumbnail
        self._load_equip_tn(name.lower(), self._wpn_img_lbl)

    def _on_armor_select(self, _):
        sel = self._arm_tv.selection()
        if not sel:
            return
        vals = self._arm_tv.item(sel[0], "values")
        name = vals[0]
        a = next((x for x in self._armors if x["name"] == name), None)
        if not a:
            return
        txt = self._arm_detail
        txt.configure(state="normal")
        txt.delete("1.0", "end")
        txt.insert("end", f"{a['name']}\n", "h")

        def row(k, v, txt=txt):
            txt.insert("end", f"  {k:<18}", "kv")
            txt.insert("end", f"{v}\n")

        row("Slot",         a["slot_name"])
        row("Protection",   str(a["protection"]))
        row("Value (gold)", str(a["value"]))
        row("Min Strength", str(a["min_str"]))
        row("Min Constit.", str(a["min_con"]))
        row("Stealth",      str(a["stealth"]))
        row("Resist Poison",str(a["resist_psn"]))
        row("Combining",    str(a["combining"]))
        txt.configure(state="disabled")

        # Try to load .tn thumbnail
        self._load_equip_tn(name.lower(), self._arm_img_lbl)

    def _load_equip_tn(self, name: str, lbl: tk.Label):
        """Load .tn thumbnail for equipment: exact match first, then prefix."""
        if not HAS_PIL:
            return
        equip_dir = self.cfg.thumbnails / "Equip"
        if not equip_dir.exists():
            lbl.config(image="")
            return
        norm = name.lower().replace(" ", "").replace("-", "").replace("'", "")
        best: Optional[Path] = None
        best_score = 999
        for f in equip_dir.iterdir():
            if f.suffix.lower() != '.tn':
                continue
            fn = f.stem.lower().replace(" ", "").replace("-", "").replace("'", "")
            if fn == norm:
                best = f
                break
            # prefix match — prefer shorter distance
            if fn.startswith(norm) or norm.startswith(fn):
                score = abs(len(fn) - len(norm))
                if score < best_score:
                    best = f
                    best_score = score
        if best is None:
            lbl.config(image="")
            return
        try:
            raw = best.read_bytes()
            from core.parsers import decode_tn_pixels
            px  = decode_tn_pixels(raw)
            if px is not None:
                rgba = Image.frombytes('RGBA', (16, 16), px)
                bg   = Image.new('RGB', (16, 16), (30, 42, 69))
                bg.paste(rgba, mask=rgba.split()[3])
                img  = bg.resize((64, 64), Image.NEAREST)
                ph   = ImageTk.PhotoImage(img)
                lbl.config(image=ph)
                lbl._photo = ph
                return
        except Exception:
            pass
        lbl.config(image="")

    def _export_all_weapons(self):
        self._export_equip_icons(self._weapons, "Weapons")

    def _export_all_armors(self):
        self._export_equip_icons(self._armors, "Armors")

    def _export_equip_icons(self, items: list, folder: str):
        if not HAS_PIL or not items:
            self._status.set(f"No {folder.lower()} loaded")
            return
        equip_dir = self.cfg.thumbnails / "Equip"
        dest = self.cfg.renders_dir / folder
        dest.mkdir(parents=True, exist_ok=True)
        ok = skip = 0
        for item in items:
            name = item["name"]
            norm = name.lower().replace(" ", "").replace("-", "").replace("'", "")
            best = None; best_score = 999
            for f in equip_dir.iterdir():
                if f.suffix.lower() != '.tn':
                    continue
                fn = f.stem.lower().replace(" ", "").replace("-", "").replace("'", "")
                if fn == norm:
                    best = f; break
                if fn.startswith(norm) or norm.startswith(fn):
                    score = abs(len(fn) - len(norm))
                    if score < best_score:
                        best = f; best_score = score
            if best:
                from core.parsers import load_tn_image
                img = load_tn_image(best, 64)
                if img:
                    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)
                    try:
                        img.save(str(dest / f"{safe}.png")); ok += 1
                    except Exception:
                        skip += 1
                    continue
            skip += 1
        self._status.set(f"{folder} icons exported: {ok} saved, {skip} skipped → {dest}")


# ═══════════════════════════════════════════════════════════════════════════════
#  SPELLS TAB  (reworked: icons + talisman combos + variants)
# ═══════════════════════════════════════════════════════════════════════════════
