from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from core.constants import *
from ui.widgets import *
from core.parsers import *
class SpellsTab(tk.Frame):
    def __init__(self, parent, config, status: StatusBar):
        self.cfg = config
        super().__init__(parent, bg=BG_MID)
        self._status   = status
        self._spells   = []
        self._talis_ph : Dict[str, "ImageTk.PhotoImage"] = {}
        self._spell_ph : Dict[str, "ImageTk.PhotoImage"] = {}
        self._slot_ph  : Optional["ImageTk.PhotoImage"] = None   # spell slot badge
        self._variant_talis_widgets: list = []   # kept alive
        self._export_stop = False
        self._build_ui()
        self.after(400, self._load_all)

    def _build_ui(self):
        bar = tk.Frame(self, bg=BG_DARK, pady=4)
        bar.pack(fill="x")
        self._flt_var = tk.StringVar()
        tk.Label(bar, text="Filter:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 10)).pack(side="left", padx=(10, 4))
        tk.Entry(bar, textvariable=self._flt_var,
                 bg=BG_PANEL, fg=FG_TEXT, insertbackground=FG_TEXT,
                 font=("Segoe UI", 10), relief="flat", width=20
                 ).pack(side="left", padx=4)
        self._flt_var.trace_add("write", self._filter)
        self._export_btn = tk.Button(bar, text="Export All Icons", bg=ACCENT2,
                                     fg="#000", relief="flat",
                                     font=("Segoe UI", 9, "bold"), padx=8,
                                     command=self._export_all)
        self._export_btn.pack(side="right", padx=4)
        self._count_lbl = tk.Label(bar, text="", bg=BG_DARK, fg=FG_DIM,
                                   font=("Segoe UI", 9))
        self._count_lbl.pack(side="right", padx=12)

        pane = tk.PanedWindow(self, orient="horizontal", bg=BG_DARK,
                              sashwidth=6, sashrelief="flat")
        pane.pack(fill="both", expand=True)

        # ── Left: compact spell list ──────────────────────────────────────────
        lf = tk.Frame(pane, bg=BG_MID)
        pane.add(lf, minsize=240)
        cols = ("name", "mana", "type")
        self._tv = ttk.Treeview(lf, columns=cols, show="headings",
                                selectmode="browse")
        self._tv.heading("name", text="Spell",  anchor="w")
        self._tv.heading("mana", text="Mana",   anchor="center")
        self._tv.heading("type", text="Dmg Type", anchor="w")
        self._tv.column("name", width=180, stretch=True)
        self._tv.column("mana", width=50,  stretch=False, anchor="center")
        self._tv.column("type", width=80,  stretch=False)
        sb = ttk.Scrollbar(lf, orient="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._tv.pack(fill="both", expand=True)
        self._tv.bind("<<TreeviewSelect>>", self._on_select)

        # ── Right: rich detail card ───────────────────────────────────────────
        right = tk.Frame(pane, bg=BG_PANEL)
        pane.add(right, minsize=380)

        # Header row: icon + slot badge + name
        hdr = tk.Frame(right, bg=BG_PANEL, padx=10, pady=8)
        hdr.pack(fill="x")
        self._icon_lbl = tk.Label(hdr, bg=BG_PANEL)
        self._icon_lbl.pack(side="left", padx=(0, 4))
        self._slot_badge_lbl = tk.Label(hdr, bg=BG_PANEL)
        self._slot_badge_lbl.pack(side="left", padx=(0, 10))
        name_frame = tk.Frame(hdr, bg=BG_PANEL)
        name_frame.pack(side="left", fill="x", expand=True)
        self._spell_name_lbl = tk.Label(name_frame, text="Select a spell",
                                        bg=BG_PANEL, fg=FG_TEXT,
                                        font=("Segoe UI", 14, "bold"),
                                        anchor="w", wraplength=280)
        self._spell_name_lbl.pack(anchor="w")
        self._spell_desc_lbl = tk.Label(name_frame, text="",
                                        bg=BG_PANEL, fg=FG_DIM,
                                        font=("Segoe UI", 9), wraplength=280,
                                        justify="left", anchor="w")
        self._spell_desc_lbl.pack(anchor="w", pady=(2, 0))

        ttk.Separator(right).pack(fill="x")

        # Scrollable detail body
        scroll_frame = ScrollFrame(right, bg=BG_PANEL)
        scroll_frame.pack(fill="both", expand=True)
        self._body = scroll_frame.inner
        self._body.configure(bg=BG_PANEL)

    def _load_all(self):
        self._status.set("Parsing spell.def…")
        self._spells = parse_spell_def(self.cfg)
        if HAS_PIL:
            from core.parsers import load_talisman_icons, decode_dat_frame
            self._talis_ph = load_talisman_icons(self.cfg, size=28)
            # Load spell-slot badge from bottombar.dat frame 2 (42×42)
            slot_img = decode_dat_frame(self.cfg.resources / "bottombar.dat", 2, size=32)
            if slot_img:
                self._slot_ph = ImageTk.PhotoImage(slot_img)
        self._populate(self._spells)
        self._count_lbl.config(text=f"{len(self._spells)} spells")
        self._status.set(f"Spells loaded: {len(self._spells)}")

    def _populate(self, data: List[Dict]):
        self._tv.delete(*self._tv.get_children())
        for s in data:
            dt = DAMAGE_TYPE_NAMES.get(s.get("damage_type", ""), s.get("damage_type", "—"))
            self._tv.insert("", "end",
                values=(s["name"], s.get("mana", "—"), dt or "—"))

    def _filter(self, *_):
        flt = self._flt_var.get().strip().lower()
        filtered = ([s for s in self._spells if flt in s["name"].lower()]
                    if flt else self._spells)
        self._populate(filtered)
        self._count_lbl.config(text=f"{len(filtered)} / {len(self._spells)}")

    def _on_select(self, _):
        sel = self._tv.selection()
        if not sel:
            return
        name = self._tv.item(sel[0], "values")[0]
        s = next((x for x in self._spells if x["name"] == name), None)
        if s:
            self._show_detail(s)

    def _show_detail(self, s: Dict):
        # ── Header ───────────────────────────────────────────────────────────
        self._spell_name_lbl.config(text=s["name"])
        self._spell_desc_lbl.config(text=s.get("description", ""))

        # Icon + slot badge
        if HAS_PIL:
            icon_name = s.get("icon_name", s["name"])
            if icon_name not in self._spell_ph:
                from core.parsers import load_spell_icon
                img = load_spell_icon(self.cfg, icon_name, size=56)
                if img:
                    self._spell_ph[icon_name] = ImageTk.PhotoImage(img)
                else:
                    self._spell_ph[icon_name] = None
            ph = self._spell_ph.get(icon_name)
            if ph:
                self._icon_lbl.config(image=ph, width=0)
                self._icon_lbl._ph = ph
            else:
                self._icon_lbl.config(image="", text="?", fg=FG_MUTED,
                                      font=("Segoe UI", 22), width=3)
            # Slot badge: show bottombar slot frame if available
            if self._slot_ph:
                self._slot_badge_lbl.config(image=self._slot_ph)
                self._slot_badge_lbl._ph = self._slot_ph
            else:
                self._slot_badge_lbl.config(image="")

        # ── Body: clear and rebuild ───────────────────────────────────────────
        for w in self._body.winfo_children():
            w.destroy()
        self._variant_talis_widgets.clear()

        def _sect(txt, self=self):
            tk.Label(self._body, text=txt, bg=BG_PANEL, fg=ACCENT,
                     font=("Segoe UI", 9, "bold"), anchor="w"
                     ).pack(fill="x", padx=10, pady=(8, 2))

        def _row(k, v, self=self):
            f = tk.Frame(self._body, bg=BG_PANEL)
            f.pack(fill="x", padx=10, pady=1)
            tk.Label(f, text=f"{k}:", bg=BG_PANEL, fg=ACCENT2,
                     font=("Segoe UI", 9), width=16, anchor="w").pack(side="left")
            tk.Label(f, text=str(v), bg=BG_PANEL, fg=FG_TEXT,
                     font=("Consolas", 9), anchor="w").pack(side="left")

        # ── Stats ─────────────────────────────────────────────────────────────
        _sect("STATS")
        dt = DAMAGE_TYPE_NAMES.get(s.get("damage_type", ""), s.get("damage_type", ""))
        _row("Damage type", dt or "—")

        # Animation row with linked .i3d file
        anim = s.get("animation", "")
        if anim:
            model_file = _spell_anim_model(self.cfg, anim)
            af = tk.Frame(self._body, bg=BG_PANEL)
            af.pack(fill="x", padx=10, pady=1)
            tk.Label(af, text="Animation:", bg=BG_PANEL, fg=ACCENT2,
                     font=("Segoe UI", 9), width=16, anchor="w").pack(side="left")
            tk.Label(af, text=anim, bg=BG_PANEL, fg=FG_TEXT,
                     font=("Consolas", 9), anchor="w").pack(side="left")
            if model_file and model_file.exists():
                def _open_model(p=model_file):
                    import subprocess, os
                    if os.name == 'nt':
                        subprocess.Popen(["explorer", "/select,", str(p)])
                    else:
                        subprocess.Popen(["xdg-open", str(p.parent)])
                tk.Button(af, text=f"  {model_file.name}  ", bg=BG_CARD,
                          fg=ACCENT2, relief="flat", cursor="hand2",
                          font=("Segoe UI", 8), command=_open_model
                          ).pack(side="left", padx=6)
        else:
            _row("Animation", "—")

        if s.get("damage"):
            _row("Damage",  s["damage"])
        if s.get("duration"):
            _row("Duration", s["duration"])

        # ── Variants / Talisman combos ────────────────────────────────────────
        variants = s.get("variants", [])
        if variants:
            _sect(f"VARIANTS  ({len(variants)})")
            for v in variants:
                vf = tk.Frame(self._body, bg=BG_CARD,
                              highlightthickness=1, highlightbackground=BORDER)
                vf.pack(fill="x", padx=10, pady=3)

                # Variant name + mana
                hf = tk.Frame(vf, bg=BG_CARD)
                hf.pack(fill="x", padx=6, pady=(4, 2))
                tk.Label(hf, text=v["name"], bg=BG_CARD, fg=FG_TEXT,
                         font=("Segoe UI", 9, "bold")).pack(side="left")
                if v.get("mana"):
                    tk.Label(hf, text=f"  {v['mana']} mana",
                             bg=BG_CARD, fg=ACCENT2,
                             font=("Segoe UI", 8)).pack(side="left")
                if v.get("min_d") not in (None, "—") and v.get("max_d") not in (None, "—"):
                    tk.Label(hf, text=f"  dmg {v['min_d']}–{v['max_d']}",
                             bg=BG_CARD, fg=GOLD,
                             font=("Segoe UI", 8)).pack(side="left")

                # Talisman icon chain
                talis_str  = v.get("talismans", "")
                talis_names = v.get("talis_names", [])
                tf = tk.Frame(vf, bg=BG_CARD)
                tf.pack(fill="x", padx=6, pady=(0, 4))
                for letter, tname in zip(talis_str, talis_names):
                    ph = self._talis_ph.get(tname)
                    cell = tk.Frame(tf, bg=BG_CARD)
                    cell.pack(side="left", padx=3)
                    if ph:
                        lbl_i = tk.Label(cell, image=ph, bg=BG_CARD)
                        lbl_i.pack()
                        lbl_i._ph = ph
                        self._variant_talis_widgets.append(lbl_i)
                    tk.Label(cell, text=tname, bg=BG_CARD, fg=FG_DIM,
                             font=("Segoe UI", 7)).pack()

                if v.get("effect"):
                    ef = tk.Frame(vf, bg=BG_CARD)
                    ef.pack(fill="x", padx=6, pady=(0, 4))
                    tk.Label(ef, text="Effect:", bg=BG_CARD, fg=FG_MUTED,
                             font=("Segoe UI", 8)).pack(side="left")
                    tk.Label(ef, text=v["effect"], bg=BG_CARD, fg=ACCENT3,
                             font=("Consolas", 8)).pack(side="left", padx=4)

    # ── Batch export ──────────────────────────────────────────────────────────
    def _export_all(self):
        if not HAS_PIL:
            self._status.set("PIL not available")
            return
        if not self._spells:
            self._status.set("No spells loaded")
            return
        dest = self.cfg.renders_dir / "SpellIcons"
        dest.mkdir(parents=True, exist_ok=True)
        total = len(self._spells)
        self._export_stop = False
        self._export_btn.config(text="Stop", bg=RED,
                                command=lambda: setattr(self, '_export_stop', True))

        def _worker(self=self, dest=dest, total=total):
            ok = skip = 0
            from core.parsers import load_spell_icon
            for i, s in enumerate(self._spells, 1):
                if self._export_stop:
                    break
                icon_name = s.get("icon_name", s["name"])
                img = load_spell_icon(self.cfg, icon_name, size=64)
                if img:
                    out = dest / f"{icon_name}.png"
                    try:
                        img.save(str(out)); ok += 1
                    except Exception:
                        skip += 1
                else:
                    skip += 1
                if i % 10 == 0 or i == total:
                    self.after(0, lambda n=i: self._status.set(
                        f"Exporting spell icons: {n}/{total}…"))
            self.after(0, self._on_export_done, ok, skip, dest)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_export_done(self, ok: int, skip: int, dest: Path):
        self._export_btn.config(text="Export All Icons", bg=ACCENT2,
                                command=self._export_all)
        self._status.set(f"Spell icons: {ok} saved, {skip} skipped → {dest}")


def _spell_anim_model(cfg, anim_name: str) -> Optional[Path]:
    """Return the most relevant .i3d model file for a spell animation name."""
    chars_dir = cfg.imagery_assets / "Chars"
    candidates = {
        "invoke1": "invoker.i3d", "invoke2": "invoker.i3d",
        "invoke3": "invoker.i3d", "invoke4": "invoker.i3d",
        "invoke5": "invoker.i3d", "cinv1":   "invoker.i3d",
        "Vomit":   "zombie.i3d",
    }
    fname = candidates.get(anim_name)
    if fname:
        p = chars_dir / fname
        if p.exists():
            return p
    # Generic fallback: search for model whose name contains the anim name
    anim_lower = anim_name.lower()
    for f in chars_dir.glob("*.i3d"):
        if anim_lower in f.stem.lower():
            return f
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  SCRIPTS TAB
# ═══════════════════════════════════════════════════════════════════════════════
