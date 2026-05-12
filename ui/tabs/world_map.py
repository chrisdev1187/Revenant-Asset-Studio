from PIL import Image
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple
ZoneKey = Tuple[str, int]
from ui.theme import THEME, FONTS
from core.constants import *
from ui.widgets import *
from core.parsers import *
class WorldMapTab(tk.Frame):
    def __init__(self, parent, config, status: StatusBar):
        self.cfg = config
        super().__init__(parent, bg=THEME["bg_mid"])
        self._status  = status
        self._photo   = None
        self._img     = None
        self._zoom    = 1.0
        self._zones   = []
        self._cur_zone = tk.StringVar(value="")
        self._cache    = {}      # zone -> PIL Image
        self._build_ui()
        self.after(100, self._init_load)

    def _build_ui(self):
        # ── Toolbar ──────────────────────────────────────────────────────────
        bar = tk.Frame(self, bg=THEME["bg_dark"], pady=4)
        bar.pack(fill="x")

        tk.Label(bar, text="Zone:", bg=THEME["bg_dark"], fg=THEME["fg_dim"],
                 font=FONTS["body"]).pack(side="left", padx=(10, 4))

        self._zone_combo = ttk.Combobox(bar, textvariable=self._cur_zone,
                                         state="readonly", width=32,
                                         font=FONTS["body"])
        self._zone_combo.pack(side="left", padx=4)
        self._zone_combo.bind("<<ComboboxSelected>>", self._on_zone_change)

        tk.Button(bar, text="Stitch Zone", command=self._stitch_current,
                  bg=ACCENT, fg="white", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10
                  ).pack(side="left", padx=8)

        tk.Button(bar, text="Save PNG", command=self._save_current,
                  bg=ACCENT2, fg="white", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10
                  ).pack(side="left", padx=4)

        self._extract_btn = tk.Button(
                  bar, text="⬇ Extract Modules", command=self._extract_missing_modules,
                  bg="#5a3070", fg="white", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10)
        self._extract_btn.pack(side="left", padx=4)

        # Zoom controls
        tk.Label(bar, text="Zoom:", bg=THEME["bg_dark"], fg=THEME["fg_dim"],
                 font=FONTS["body"]).pack(side="left", padx=(20, 4))
        for label, val in [("25%", 0.25), ("50%", 0.5), ("100%", 1.0)]:
            tk.Button(bar, text=label, bg=THEME["bg_panel"], fg=THEME["fg_text"], relief="flat",
                      font=FONTS["small"], padx=6,
                      command=lambda v=val: self._set_zoom(v)
                      ).pack(side="left", padx=2)

        self._tile_lbl = tk.Label(bar, text="", bg=THEME["bg_dark"], fg=THEME["fg_dim"],
                                   font=FONTS["small"])
        self._tile_lbl.pack(side="right", padx=12)

        # ── Scrollable canvas ─────────────────────────────────────────────────
        frame = tk.Frame(self, bg=THEME["bg_mid"])
        frame.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(frame, bg="#0a0a14", cursor="crosshair",
                                  highlightthickness=0)
        h_sb = ttk.Scrollbar(frame, orient="horizontal",
                               command=self._canvas.xview)
        v_sb = ttk.Scrollbar(frame, orient="vertical",
                               command=self._canvas.yview)
        self._canvas.configure(xscrollcommand=h_sb.set,
                                yscrollcommand=v_sb.set)
        h_sb.pack(side="bottom", fill="x")
        v_sb.pack(side="right",  fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._canvas.bind("<MouseWheel>", self._on_wheel)
        self._canvas.bind("<ButtonPress-2>",   self._pan_start)
        self._canvas.bind("<B2-Motion>",        self._pan_move)

        self._map_item  = None
        self._pan_start_x = 0
        self._pan_start_y = 0

    def _pan_start(self, e):
        self._canvas.scan_mark(e.x, e.y)

    def _pan_move(self, e):
        self._canvas.scan_dragto(e.x, e.y, gain=1)

    def _on_wheel(self, e):
        factor = 1.1 if e.delta > 0 else 0.9
        self._zoom = max(0.1, min(4.0, self._zoom * factor))
        self._refresh_display()

    def _init_load(self):
        # _zones now stores ZoneKey = (module_name, zone_number) tuples
        self._zones = get_all_zone_keys(self.cfg)

        # Count unextracted modules so we can prompt the user
        from core.parsers import get_unextracted_modules
        unextracted = get_unextracted_modules(self.cfg)
        if unextracted:
            hint = f"  ({len(unextracted)} unextracted module(s): {', '.join(unextracted[:4])}{'…' if len(unextracted)>4 else ''}  — click ⬇ Extract Modules)"
        else:
            hint = ""

        if not self._zones:
            self._status.set(
                "No automap tiles found. Run archive_extractor.py first, then restart." + hint)
            return

        def _label(mk: ZoneKey) -> str:
            module, z = mk
            name = ZONE_NAMES.get(z, f"Zone {z}")
            if module.lower() == "ahkuilon":
                return f"Zone {z}  —  {name}"
            return f"Zone {z}  —  {module}  ({name})"

        labels = [_label(mk) for mk in self._zones]
        self._zone_combo['values'] = labels
        self._zone_combo.current(0)

        modules_found = len(set(m for m, _ in self._zones))
        status_extra = f"  |  {hint.strip()}" if hint else ""
        self._status.set(
            f"{len(self._zones)} zone(s) across {modules_found} module(s) found{status_extra}")

        # Check for pre-rendered zone 0 (main world module)
        main_module = next((m for m, z in self._zones if m.lower() == "ahkuilon" and z == 0),
                           self._zones[0][0] if self._zones else "ahkuilon")
        cached_path = self.cfg.renders_dir / f"world_map_{main_module}_zone0.png"
        if not cached_path.exists():
            cached_path = self.cfg.renders_dir / "world_map_zone0.png"   # legacy name
        if cached_path.exists() and HAS_PIL:
            img = Image.open(cached_path)
            self._cache[(main_module, 0)] = img
            self._img = img
            self._zoom = 0.25
            self._refresh_display()
            tiles = get_automap_tiles(self.cfg, 0, main_module)
            self._tile_lbl.config(
                text=f"{main_module} Zone 0: {len(tiles)} tiles  |  {img.width}x{img.height}px")
        else:
            self._stitch_current()

    def _extract_missing_modules(self):
        """Extract any .rvm module files that haven't been extracted yet."""
        from core.parsers import get_unextracted_modules
        unextracted = get_unextracted_modules(self.cfg)
        if not unextracted:
            self._status.set("All modules already extracted.")
            return

        self._extract_btn.config(state="disabled", text="Extracting…")
        self._status.set(f"Extracting {len(unextracted)} module(s): {', '.join(unextracted)}…")

        def _worker(self=self, unextracted=unextracted):
            import zipfile as _zf
            done = []
            failed = []
            for stem in unextracted:
                # Try both Modules/ subdir and game root
                candidates = [
                    self.cfg.game_dir / "Modules" / f"{stem}.rvm",
                    self.cfg.game_dir / f"{stem}.rvm",
                ]
                src = next((p for p in candidates if p.exists()), None)
                if src is None:
                    failed.append(stem)
                    continue
                out_dir = self.cfg.extract_dir / stem
                try:
                    out_dir.mkdir(parents=True, exist_ok=True)
                    with _zf.ZipFile(src) as zf:
                        zf.extractall(out_dir)
                    done.append(stem)
                except Exception as e:
                    failed.append(f"{stem}({e})")
            self.after(0, self._on_extract_done, done, failed)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_extract_done(self, done, failed):
        self._extract_btn.config(state="normal", text="⬇ Extract Modules")
        if done:
            self._status.set(
                f"Extracted: {', '.join(done)}. Reloading zones…")
            # Reload the zone list now that new modules are available
            self._zones = get_all_zone_keys(self.cfg)

            def _label(mk: ZoneKey) -> str:
                module, z = mk
                name = ZONE_NAMES.get(z, f"Zone {z}")
                if module.lower() == "ahkuilon":
                    return f"Zone {z}  —  {name}"
                return f"Zone {z}  —  {module}  ({name})"

            self._zone_combo['values'] = [_label(mk) for mk in self._zones]
            if self._zones:
                self._zone_combo.current(0)
            msg = f"Extracted {len(done)} module(s). {len(self._zones)} zones now available."
            if failed:
                msg += f"  Failed: {', '.join(failed)}"
            self._status.set(msg)
        else:
            self._status.set(
                f"Extraction failed — .rvm files not found in {self.cfg.game_dir}/Modules/. "
                f"Failed: {', '.join(failed)}")


    def _current_zone_key(self) -> ZoneKey:
        """Return the (module, zone) key for the currently selected combobox entry."""
        idx = self._zone_combo.current()
        if 0 <= idx < len(self._zones):
            return self._zones[idx]
        return self._zones[0] if self._zones else ("ahkuilon", 0)

    def _on_zone_change(self, _=None):
        mk = self._current_zone_key()
        if mk in self._cache:
            self._img  = self._cache[mk]
            self._zoom = 0.25
            self._refresh_display()
            module, z = mk
            self._tile_lbl.config(
                text=f"{module} Zone {z}: {self._img.width}x{self._img.height}px (cached)")
        else:
            self._stitch_current()

    def _stitch_current(self):
        mk = self._current_zone_key()
        module, zone = mk
        self._status.set(f"Stitching {module} zone {zone}...")
        overlay = LoadingOverlay(self, text=f"Stitching {module} Zone {zone}...")

        def _worker(self=self, zone=zone, module=module, mk=mk, overlay=overlay):
            img = stitch_zone_map(self.cfg, zone, module)
            self.after(0, lambda: self._on_stitch_done(mk, img, overlay))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_stitch_done(self, mk: ZoneKey, img, overlay):
        overlay.destroy()
        module, zone = mk
        if img is None:
            self._status.set(f"No tiles found for {module} zone {zone}  (check Diagnose for tile counts)")
            return
        self._cache[mk] = img
        self._img   = img
        self._zoom  = 0.25
        self._refresh_display()
        tiles = get_automap_tiles(self.cfg, zone, module)
        self._tile_lbl.config(
            text=f"{module} Zone {zone}: {len(tiles)} tiles  |  {img.width}x{img.height}px")
        self._status.set(
            f"{module} zone {zone} stitched — {len(tiles)} tiles, {img.width}x{img.height}px")

    def _save_current(self):
        """Save the full-resolution stitched zone map as PNG (file dialog)."""
        if self._img is None:
            self._status.set("Nothing to save — stitch a zone first.")
            return
        module, zone = self._current_zone_key()
        self.cfg.renders_dir.mkdir(parents=True, exist_ok=True)
        default_name = f"world_map_{module}_zone{zone}.png"
        out = filedialog.asksaveasfilename(
            title="Save Zone Map as PNG",
            initialdir=str(self.cfg.renders_dir),
            initialfile=default_name,
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png"), ("All files", "*.*")],
        )
        if not out:
            return
        self._img.save(out)
        self._status.set(
            f"Saved: {Path(out).name}  ({self._img.width}×{self._img.height}px)"
        )

    def _export_all_zones(self):
        """Stitch and save every available zone to PNG in the renders folder."""
        if not self._zones:
            self._status.set("No zones found.")
            return
        self._export_all_btn.config(state="disabled", text="Exporting…")
        total = len(self._zones)
        self._status.set(f"Exporting {total} zones…")

        def _worker(self=self, total=total):
            self.cfg.renders_dir.mkdir(parents=True, exist_ok=True)
            for done, mk in enumerate(self._zones):
                module, z = mk
                self.after(0, lambda m=module, z=z, d=done: self._status.set(
                    f"Stitching {m} zone {z}… ({d}/{total})"))
                img = stitch_zone_map(self.cfg, z, module)
                if img:
                    out = self.cfg.renders_dir / f"world_map_{module}_zone{z}.png"
                    img.save(out)
                    self._cache[mk] = img
            self.after(0, self._on_export_all_done, total)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_export_all_done(self, count: int):
        self._export_all_btn.config(state="normal", text="Export All Zones")
        self._status.set(
            f"Export complete — {count} zone maps saved to {self.cfg.renders_dir}")

    def _show_diagnose(self):
        """Show a popup with full Automaps directory diagnostic info."""
        from core.parsers import all_automap_dirs, get_unextracted_modules
        win = tk.Toplevel(self)
        win.title("Automap Diagnostic")
        win.configure(bg=THEME["bg_dark"])
        win.geometry("700x540")

        tk.Label(win, text="AUTOMAP DIAGNOSTIC", bg=THEME["bg_dark"], fg=THEME["accent"],
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=14, pady=(12, 4))

        txt = tk.Text(win, bg="#0c0c14", fg=THEME["fg_text"], font=("Consolas", 9),
                      relief="flat", wrap="none")
        sb_y = ttk.Scrollbar(win, orient="vertical",   command=txt.yview)
        sb_x = ttk.Scrollbar(win, orient="horizontal", command=txt.xview)
        txt.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        sb_x.pack(side="bottom", fill="x")
        sb_y.pack(side="right",  fill="y")
        txt.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        txt.tag_configure("h",    foreground=ACCENT,  font=("Segoe UI", 9, "bold"))
        txt.tag_configure("ok",   foreground="#80e080")
        txt.tag_configure("warn", foreground="#e0c060")
        txt.tag_configure("dim",  foreground=FG_DIM)

        def w(line, tag="", txt=txt):
            txt.insert("end", line + "\n", tag)

        w(f"self.cfg.extract_dir : {self.cfg.extract_dir}", "dim")
        w(f"self.cfg.game_dir    : {self.cfg.game_dir}", "dim")
        w("")

        # --- Module directories ---
        w("MODULE DIRS WITH Automaps/", "h")
        amap_dirs = all_automap_dirs(self.cfg)
        if amap_dirs:
            for d in amap_dirs:
                bmps = list(d.rglob("*.bmp"))
                w(f"  ✓ {d}  ({len(bmps)} bmp files)", "ok")
        else:
            w("  NONE FOUND", "warn")
        w("")

        # --- Unextracted modules ---
        unext = get_unextracted_modules(self.cfg)
        w("UNEXTRACTED .rvm MODULES", "h")
        if unext:
            for m in unext:
                w(f"  ! {m}  ← click '⬇ Extract Modules' to extract", "warn")
        else:
            w("  All found modules are extracted", "ok")
        w("")

        # --- All bmp files found ---
        w("ALL BMP FILES FOUND (rglob)", "h")
        all_bmps: List[Path] = []
        for d in amap_dirs:
            all_bmps.extend(d.rglob("*.bmp"))
        all_bmps.sort()
        w(f"  Total: {len(all_bmps)}")

        zone_counts: dict = {}
        bad: List[str] = []
        for f in all_bmps:
            parts = f.stem.split('_')
            if len(parts) == 3:
                try:
                    z = int(parts[0])
                    zone_counts[z] = zone_counts.get(z, 0) + 1
                    continue
                except ValueError:
                    pass
            bad.append(f.name)

        w("")
        w("ZONE TILE COUNTS", "h")
        for z in sorted(zone_counts):
            w(f"  Zone {z:4d} : {zone_counts[z]:5d} tiles", "ok")

        if bad:
            w("")
            w(f"UNPARSEABLE FILENAMES ({len(bad)})", "h")
            for b in bad[:20]:
                w(f"  {b}", "warn")
            if len(bad) > 20:
                w(f"  … and {len(bad)-20} more", "dim")

        # --- Modules folder contents ---
        w("")
        w("MODULES FOLDER CONTENTS", "h")
        mdir = self.cfg.game_dir / "Modules"
        if mdir.exists():
            for f in sorted(mdir.iterdir()):
                w(f"  {f.name}  ({f.stat().st_size // 1024} KB)", "ok")
        else:
            w(f"  {mdir}  — NOT FOUND", "warn")
            w("  (town/orc-camp automaps live in Modules/*.rvm)", "dim")

        txt.configure(state="disabled")

    def _refresh_display(self):
        if self._img is None or not HAS_PIL:
            return
        w = max(1, int(self._img.width  * self._zoom))
        h = max(1, int(self._img.height * self._zoom))
        scaled = self._img.resize((w, h), Image.NEAREST)
        self._photo = ImageTk.PhotoImage(scaled)
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self._canvas.configure(scrollregion=(0, 0, w, h))


# ═══════════════════════════════════════════════════════════════════════════════
#  CHARACTER GALLERY TAB
# ═══════════════════════════════════════════════════════════════════════════════
