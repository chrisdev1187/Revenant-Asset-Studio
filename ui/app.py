from ui.tabs.library import LibraryTab
from ui.tabs.world_map import WorldMapTab
from ui.tabs.character_gallery import CharacterGalleryTab
from ui.tabs.equipment import EquipmentTab
from ui.tabs.sprites import SpritesTab
from ui.tabs.spells import SpellsTab
from ui.tabs.scripts import ScriptsTab
from ui.tabs.models import ModelsTab
from ui.tabs.sounds import SoundsTab
from ui.tabs.cinematix import CinematiXTab
from ui.tabs.ui_resources import UIResourcesTab
from ui.tabs.ahkuilon import AhkuilonTab
from ui.tabs.upscale import UpscaleTab
from ui.tabs.godot_export import GodotExportTab
from asset_studio_modernize import ModernizeTab
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from core.constants import *
from ui.widgets import *
import os, logging
from core.config import Config
from ui.theme import THEME, FONTS, apply_global_styles, enable_high_dpi
from ui.wizard import WelcomeWizard

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, config):
        self.config = config
        super().__init__(parent)
        self.title("RevEngine — Settings")
        self.configure(bg=BG_DARK)
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)

        self.config = config
        self._game_var    = tk.StringVar(value=str(self.config.game_dir))
        self._extract_var = tk.StringVar(value=str(self.config.extract_dir))
        self._renders_var = tk.StringVar(value=str(self.config.renders_dir))

        frm = tk.Frame(self, bg=BG_DARK, padx=24, pady=16)
        frm.pack(fill="both", expand=True)

        def _browse(var):
            d = filedialog.askdirectory(initialdir=var.get())
            if d:
                var.set(d)

        def _row(label, var, row, frm=frm, _browse=_browse):
            tk.Label(frm, text=label, bg=BG_DARK, fg=FG_DIM,
                     font=("Segoe UI", 9), anchor="w").grid(
                row=row, column=0, columnspan=2, sticky="w", pady=(10, 2))
            tk.Entry(frm, textvariable=var, bg=BG_PANEL, fg=FG_TEXT,
                     insertbackground=FG_TEXT, relief="flat", width=54,
                     font=("Segoe UI", 9)).grid(
                row=row+1, column=0, sticky="ew", padx=(0, 6))
            tk.Button(frm, text="Browse…", bg=BG_MID, fg=FG_TEXT,
                      relief="flat", font=("Segoe UI", 9),
                      command=lambda v=var: _browse(v)).grid(
                row=row+1, column=1, sticky="ew")

        _row("Game Directory", self._game_var, 0)
        _row("Extract Directory", self._extract_var, 2)
        _row("Export Directory (renders)", self._renders_var, 4)

        frm.columnconfigure(0, weight=1)

        btn_bar = tk.Frame(self, bg=BG_DARK, padx=24, pady=12)
        btn_bar.pack(fill="x")
        tk.Button(btn_bar, text="Cancel", bg=BG_MID, fg=FG_TEXT, relief="flat",
                  font=("Segoe UI", 9), command=self.destroy).pack(side="right", padx=(8, 0))
        tk.Button(btn_bar, text="Save", bg=ACCENT, fg="#000000", relief="flat",
                  font=("Segoe UI", 9, "bold"), command=self._save).pack(side="right")

    def _save(self):
        self.config.game_dir = Path(self._game_var.get())
        self.config.renders_dir = Path(self._renders_var.get())
        self.config.extract_dir = Path(self._extract_var.get())
        self.config.save()
        self.destroy()

class AssetStudio(tk.Tk):
    def __init__(self, config):
        self.config = config
        super().__init__()
        self.config.load()
        self.title("RevEngine  —  Revenant Asset Encyclopedia")

        # Professional Geometry
        enable_high_dpi(self)
        self.geometry("1440x900")
        self.configure(bg=THEME["bg_dark"])
        self.resizable(True, True)

        # Styles
        apply_global_styles(self)

        if not self.config.config_path.exists() or not self.config.extract_dir.exists():
            self.withdraw() # Hide main window
            WelcomeWizard(self, self.config, on_complete=self._on_wizard_complete)
        else:
            self._init_app()

    def _on_wizard_complete(self):
        self.deiconify()
        self._init_app()

    def _init_app(self):
        self._build_ui()
        self._bind_shortcuts()
        # Update header counts after brief delay
        self.after(2000, self._update_counts)

    def _build_ui(self):
        # ── Menu bar ─────────────────────────────────────────────────────────
        self._build_menu()

        # ── Header ───────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=THEME["bg_dark"], pady=12)
        hdr.pack(fill="x")

        # Logo/Brand
        tk.Label(hdr, text="REVENGINE", bg=THEME["bg_dark"], fg=THEME["accent_light"],
                 font=FONTS["title"]).pack(side="left", padx=(24, 12))

        tk.Label(hdr, text="Encyclopedia",
                 bg=THEME["bg_dark"], fg=THEME["fg_dim"],
                 font=FONTS["header"]).pack(side="left", pady=(4, 0))

        # Asset counts (filled after load)
        self._hdr_counts = tk.Label(hdr, text="Analyzing Library...",
                                     bg=THEME["bg_dark"], fg=THEME["success"],
                                     font=FONTS["small"])
        self._hdr_counts.pack(side="right", padx=24)

        # ── Status bar ───────────────────────────────────────────────────────
        self._status = StatusBar(self)
        self._status.pack(side="bottom", fill="x")

        ttk.Separator(self).pack(side="bottom", fill="x")

        # ── Main notebook ────────────────────────────────────────────────────
        self._nb = ttk.Notebook(self)
        self._nb.pack(fill="both", expand=True, padx=0, pady=0)

        self._lib_tab = LibraryTab(self._nb, self.config, self._status)
        self._map_tab = WorldMapTab(self._nb, self.config, self._status)
        self._char_tab  = CharacterGalleryTab(self._nb, self.config, self._status)
        self._equip_tab = EquipmentTab(self._nb, self.config, self._status)
        self._spr_tab   = SpritesTab(self._nb, self.config, self._status)
        self._spell_tab = SpellsTab(self._nb, self.config, self._status)
        self._scr_tab   = ScriptsTab(self._nb, self.config, self._status)
        self._mod_tab   = ModelsTab(self._nb, self.config, self._status)
        self._snd_tab   = SoundsTab(self._nb, self.config, self._status)
        self._cine_tab  = CinematiXTab(self._nb, self.config, self._status)
        self._ui_tab    = UIResourcesTab(self._nb, self.config, self._status)
        self._ahk_tab     = AhkuilonTab(self._nb, self.config, self._status)
        self._upscale_tab = UpscaleTab(self._nb, self.config, self._status)
        self._godot_tab = GodotExportTab(self._nb, self.config, self._status)
        from asset_studio_modernize import ModernizeTab
        self._modernize_tab  = ModernizeTab(self._nb, self.config, self._status)

        self._nb.add(self._lib_tab,      text="  Library  ")
        self._nb.add(self._map_tab,      text="  World Map  ")
        self._nb.add(self._char_tab,     text="  Characters  ")
        self._nb.add(self._equip_tab,    text="  Equipment  ")
        self._nb.add(self._spr_tab,      text="  Sprites  ")
        self._nb.add(self._spell_tab,    text="  Spells  ")
        self._nb.add(self._scr_tab,      text="  Scripts  ")
        self._nb.add(self._mod_tab,      text="  3D Models  ")
        self._nb.add(self._snd_tab,      text="  Sounds  ")
        self._nb.add(self._cine_tab,     text="  Cinematix  ")
        self._nb.add(self._ui_tab,       text="  UI Resources  ")
        self._nb.add(self._ahk_tab,      text="  Ahkuilon  ")
        self._nb.add(self._upscale_tab,   text="  Upscale  ")
        self._nb.add(self._godot_tab,     text="  Godot Export  ")
        self._nb.add(self._modernize_tab, text="  Modernize 3D  ")


    def _update_counts(self):
        try:
            i3d_count = len(list(self.config.imagery_assets.rglob("*.i3d")))
            bmp_count = len(list(self.config.imagery_assets.rglob("*.bmp")))
            def_count = len(list(self.config.extract_dir.rglob("*.def")))
            mp3_count = len(list(self.config.extract_dir.rglob("*.mp3")))
            ogg_count = len(list(self.config.extract_dir.rglob("*.ogg")))
            self._hdr_counts.config(
                text=f"{i3d_count} models  |  {bmp_count} sprites  |  "
                     f"{def_count} scripts  |  {mp3_count + ogg_count} sounds")
        except Exception:
            pass

    # ── Menu ─────────────────────────────────────────────────────────────────

    def _build_menu(self):
        M = dict(bg=BG_MID, fg=FG_TEXT, activebackground=BG_CARD,
                 activeforeground=FG_TEXT, relief="flat")
        menubar = tk.Menu(self, **M, borderwidth=0)
        self.configure(menu=menubar)

        # File
        file_m = tk.Menu(menubar, tearoff=0, **M)
        menubar.add_cascade(label="File", menu=file_m)
        file_m.add_command(label="Open Game Dir",
                           command=lambda: self.config.game_dir.exists() and os.startfile(str(self.config.game_dir)))
        file_m.add_command(label="Open Extract Dir",
                           command=lambda: self.config.extract_dir.exists() and os.startfile(str(self.config.extract_dir)))
        file_m.add_command(label="Open Export Dir",
                           command=self._open_export_dir)
        file_m.add_separator()
        file_m.add_command(label="Settings…\tCtrl+,", command=lambda: SettingsDialog(self, self.config))
        file_m.add_separator()
        file_m.add_command(label="Exit\tCtrl+Q", command=self.destroy)

        # View — jump to tab
        view_m = tk.Menu(menubar, tearoff=0, **M)
        menubar.add_cascade(label="View", menu=view_m)
        _tabs = ["World Map", "Characters", "Equipment", "Sprites",
                 "Spells", "Scripts", "3D Models", "Sounds", "Cinematix",
                 "UI Resources", "Ahkuilon", "Upscale", "Godot Export", "Modernize 3D"]
        for i, name in enumerate(_tabs):
            view_m.add_command(label=name, command=lambda i=i: self._nb.select(i))

        exp_m = tk.Menu(menubar, tearoff=0, **M)
        menubar.add_cascade(label="Export", menu=exp_m)
        exp_m.add_command(label="Export Current Tab\tCtrl+E",
                          command=self._export_current_tab)
        exp_m.add_separator()
        exp_m.add_command(label="Characters (portraits)…",
                          command=lambda: self._char_tab._export_all())
        exp_m.add_command(label="Weapons (icons)…",
                          command=lambda: self._equip_tab._export_all_weapons())
        exp_m.add_command(label="Armors (icons)…",
                          command=lambda: self._equip_tab._export_all_armors())
        exp_m.add_command(label="Spell Icons…",
                          command=lambda: self._spell_tab._export_all())
        exp_m.add_command(label="Scripts (.def files)…",
                          command=lambda: self._scr_tab._export_all())
        exp_m.add_command(label="Models (OBJ batch)…",
                          command=lambda: self._mod_tab._batch_export_obj())
        exp_m.add_command(label="Sprites (current category)…",
                          command=lambda: self._spr_tab._export_all())
        exp_m.add_command(label="UI Resources (all .dat frames)…",
                          command=lambda: self._ui_tab._export_all())
        exp_m.add_command(label="Ahkuilon Scripts…",
                          command=lambda: self._ahk_tab._export_all())
        exp_m.add_separator()
        exp_m.add_command(label="Export All Assets…",
                          command=self._export_all_assets)

        # Help
        help_m = tk.Menu(menubar, tearoff=0, **M)
        menubar.add_cascade(label="Help", menu=help_m)
        help_m.add_command(label="Keyboard Shortcuts", command=self._show_shortcuts)
        help_m.add_command(label="About\tF1", command=self._show_about)

    def _bind_shortcuts(self):
        self.bind_all("<Control-q>", lambda e: self.destroy())
        self.bind_all("<Control-comma>", lambda e: SettingsDialog(self, self.config))
        self.bind_all("<Control-e>", lambda e: self._export_current_tab())
        self.bind_all("<F1>", lambda e: self._show_about())

    def _open_export_dir(self):
        self.config.renders_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(self.config.renders_dir))

    # ── Export dispatch ───────────────────────────────────────────────────────

    def _export_current_tab(self):
        idx = self._nb.index("current")
        dispatch = {
            0: self._map_tab._save_current,
            1: self._char_tab._export_all,
            2: self._equip_tab._export_all_weapons,
            3: self._spr_tab._export_all,
            4: self._spell_tab._export_all,
            5: self._scr_tab._export_all,
            6: self._mod_tab._batch_export_obj,
            9: self._ui_tab._export_all,
            10: self._ahk_tab._export_all,
        }
        fn = dispatch.get(idx)
        if fn:
            fn()
        else:
            self._status.set("No batch export for this tab — use the tab's own controls")

    def _export_all_assets(self):
        steps = [
            ("Characters",   self._char_tab._export_all),
            ("Weapons",      self._equip_tab._export_all_weapons),
            ("Armors",       self._equip_tab._export_all_armors),
            ("Scripts",      self._scr_tab._export_all),
            ("Spell Icons",  self._spell_tab._export_all),
            ("Models (OBJ)", self._mod_tab._batch_export_obj),
            ("UI Resources", self._ui_tab._export_all),
            ("Ahkuilon",     self._ahk_tab._export_all),
        ]
        total = len(steps)

        def _run(idx=0, total=total, steps=steps, self=self):
            if idx >= total:
                self._status.set("Export All complete — check export directories")
                return
            name, fn = steps[idx]
            self._status.set(f"Exporting {name}… ({idx + 1}/{total})")
            try:
                fn()
            except Exception as e:
                log.warning("Export All: %s failed: %s", name, e)
            self.after(150, _run, idx + 1)

        _run()

    # ── Help dialogs ─────────────────────────────────────────────────────────

    def _show_about(self):
        messagebox.showinfo(
            "About RevEngine",
            "RevEngine Asset Studio\n"
            "Revenant (1999) Game Encyclopedia\n\n"
            "Assets © Cinematix Studios / GOG release\n"
            "Viewer: RevEngine project",
            parent=self,
        )

    def _show_shortcuts(self):
        win = tk.Toplevel(self)
        win.title("Keyboard Shortcuts")
        win.configure(bg=BG_DARK)
        win.resizable(False, False)
        win.transient(self)
        rows = [
            ("Ctrl+E",   "Export Current Tab"),
            ("Ctrl+,",   "Settings"),
            ("Ctrl+Q",   "Exit"),
            ("F1",       "About"),
        ]
        for r, (key, desc) in enumerate(rows):
            tk.Label(win, text=key, bg=BG_DARK, fg=ACCENT,
                     font=("Consolas", 10, "bold"), width=10, anchor="e").grid(
                row=r, column=0, padx=(20, 10), pady=6)
            tk.Label(win, text=desc, bg=BG_DARK, fg=FG_TEXT,
                     font=("Segoe UI", 10), anchor="w").grid(
                row=r, column=1, sticky="w", padx=(0, 20))
