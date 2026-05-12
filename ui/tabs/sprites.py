from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from core.constants import *
from ui.widgets import *
from core.parsers import *
from ui.tabs.models import (
    _get_sprite_categories, _load_tn_image,
    GRID_COLS, THUMB_SIZE, CELL_W, CELL_H,
)
class SpritesTab(tk.Frame):
    """Browse all sprite thumbnails by category; click to decode full i2d."""

    def __init__(self, parent, config, status: StatusBar):
        self.cfg = config
        super().__init__(parent, bg=BG_MID)
        self._status      = status
        self._cats        = _get_sprite_categories(self.cfg)
        self._cat         = tk.StringVar(value=self._cats[0] if self._cats else "")
        self._ph_cache: dict[str, "ImageTk.PhotoImage"] = {}
        self._full_img    = None      # current detail PIL image
        self._full_ph     = None
        self._tn_items: list[tuple[Path, Path]] = []   # (tn_path, i2d_path)
        self._sel_name    = tk.StringVar(value="")
        self._export_stop = False     # flag to cancel running export
        self._build_ui()
        if self._cats:
            self.after(200, lambda: self._load_category(self._cats[0]))

    # ── UI construction ──────────────────────────────────────────────────────
    def _build_ui(self):
        # Top toolbar
        bar = tk.Frame(self, bg=BG_DARK, pady=4)
        bar.pack(fill="x")
        tk.Label(bar, text="Category:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 10)).pack(side="left", padx=(12, 4))
        self._cat_cb = ttk.Combobox(bar, textvariable=self._cat,
                                    values=self._cats, state="readonly", width=14)
        self._cat_cb.pack(side="left", padx=(0, 10))
        self._cat_cb.bind("<<ComboboxSelected>>", self._on_cat_change)

        self._count_lbl = tk.Label(bar, text="", bg=BG_DARK, fg=FG_DIM,
                                    font=("Segoe UI", 9))
        self._count_lbl.pack(side="left", padx=10)

        # Right-side buttons
        tk.Button(bar, text="Save PNG", bg=BG_PANEL, fg=FG_TEXT,
                  relief="flat", padx=8,
                  command=self._save_full_png).pack(side="right", padx=4)
        self._export_btn = tk.Button(bar, text="Export All", bg=ACCENT2,
                                     fg="white", relief="flat", padx=8,
                                     command=self._export_all)
        self._export_btn.pack(side="right", padx=4)

        # Main split: grid left | detail right
        paned = tk.PanedWindow(self, orient="horizontal", bg=BG_DARK,
                               sashwidth=4, sashrelief="flat")
        paned.pack(fill="both", expand=True)

        # ── Left: scrollable thumbnail grid ──────────────────────────────────
        left = tk.Frame(paned, bg=BG_MID)
        paned.add(left, minsize=200)

        self._canvas = tk.Canvas(left, bg=BG_MID, highlightthickness=0)
        vsb = ttk.Scrollbar(left, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._canvas.bind("<Configure>", self._on_resize)
        self._canvas.bind("<MouseWheel>", lambda e: self._canvas.yview_scroll(
            -1 if e.delta > 0 else 1, "units"))

        # inner frame inside canvas for the grid
        self._inner = tk.Frame(self._canvas, bg=BG_MID)
        self._win_id = self._canvas.create_window((0, 0), window=self._inner,
                                                   anchor="nw")
        self._inner.bind("<Configure>",
                         lambda e: self._canvas.configure(
                             scrollregion=self._canvas.bbox("all")))

        # ── Right: detail panel ───────────────────────────────────────────────
        right = tk.Frame(paned, bg=BG_PANEL, width=340)
        paned.add(right, minsize=240)

        tk.Label(right, textvariable=self._sel_name, bg=BG_PANEL, fg=ACCENT2,
                 font=("Segoe UI", 11, "bold"), anchor="center").pack(
                     fill="x", pady=(10, 4))

        self._dim_lbl = tk.Label(right, text="", bg=BG_PANEL, fg=FG_DIM,
                                  font=("Segoe UI", 9))
        self._dim_lbl.pack(fill="x", padx=10)

        # Image canvas for the decoded sprite
        self._detail_canvas = tk.Canvas(right, bg=BG_MID, highlightthickness=1,
                                         highlightbackground=BG_DARK)
        self._detail_canvas.pack(fill="both", expand=True, padx=10, pady=10)

        self._decode_lbl = tk.Label(right, text="", bg=BG_PANEL, fg=FG_DIM,
                                     font=("Segoe UI", 8))
        self._decode_lbl.pack(pady=(0, 6))

    # ── Category loading ─────────────────────────────────────────────────────
    def _on_cat_change(self, _=None):
        self._load_category(self._cat.get())

    def _load_category(self, cat: str):
        tn_dir  = self.cfg.thumbnails / cat
        img_dir = self.cfg.imagery_assets / cat
        if not tn_dir.exists():
            self._status.set(f"No thumbnails for {cat}")
            return

        self._status.set(f"Loading {cat} thumbnails…")
        self._ph_cache.clear()

        # Collect (tn_path, i2d_path) pairs
        # On Windows glob("*.tn") already matches .TN (case-insensitive FS),
        # so combining both patterns produces duplicates — deduplicate by stem.
        _seen: set[str] = set()
        tn_files: list[Path] = []
        for f in sorted(tn_dir.iterdir()):
            if f.suffix.lower() == ".tn" and f.stem.lower() not in _seen:
                _seen.add(f.stem.lower())
                tn_files.append(f)
        # Build a lowercase stem→path index for i2d files in img_dir (fast lookup)
        i2d_index: dict[str, Path] = {}
        if img_dir.exists():
            for f in img_dir.iterdir():
                if f.suffix.lower() == ".i2d":
                    i2d_index[f.stem.lower()] = f

        pairs: list[tuple[Path, Path]] = []
        for tn in tn_files:
            i2d = i2d_index.get(tn.stem.lower(), Path(""))
            pairs.append((tn, i2d))
        self._tn_items = pairs

        self._count_lbl.config(text=f"{len(pairs)} sprites")
        self._rebuild_grid()
        self._status.set(f"{cat}: {len(pairs)} sprites")

    def _rebuild_grid(self):
        # Clear old widgets
        for w in self._inner.winfo_children():
            w.destroy()
        self._ph_cache.clear()

        ncols = max(1, GRID_COLS)
        for idx, (tn_path, i2d_path) in enumerate(self._tn_items):
            row = idx // ncols
            col = idx % ncols
            cell = tk.Frame(self._inner, bg=BG_MID,
                            width=CELL_W, height=CELL_H)
            cell.grid_propagate(False)
            cell.grid(row=row, column=col, padx=2, pady=2)

            # Thumbnail image
            img = _load_tn_image(tn_path, THUMB_SIZE)
            if img and HAS_PIL:
                ph = ImageTk.PhotoImage(img)
                self._ph_cache[str(tn_path)] = ph
                lbl = tk.Label(cell, image=ph, bg=BG_MID, cursor="hand2")
                lbl._photo = ph
                lbl.pack(pady=(3, 0))
            else:
                ph = None
                lbl = tk.Label(cell, text="?", bg=BG_MID, fg=FG_DIM,
                               width=4, height=3)
                lbl.pack(pady=(3, 0))

            # Name label (truncated)
            name = tn_path.stem[:11]
            tk.Label(cell, text=name, bg=BG_MID, fg=FG_TEXT,
                     font=("Segoe UI", 7), anchor="center").pack()

            # Bind click
            for w in (cell, lbl):
                w.bind("<Button-1>",
                       lambda e, tp=tn_path, ip=i2d_path: self._on_click(tp, ip))

        # Update scroll region
        self._inner.update_idletasks()
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    # ── Sprite click → decode ────────────────────────────────────────────────
    def _on_click(self, tn_path: Path, i2d_path: Path):
        name = tn_path.stem
        self._sel_name.set(name)
        self._decode_lbl.config(text="Decoding…")
        self._status.set(f"Decoding {name}…")

        def _worker(self=self, tn_path=tn_path, i2d_path=i2d_path):
            # Try full i2d decode first
            img = None
            if i2d_path.is_file():
                try:
                    from decoders.i2d import decode_i2d
                    img = decode_i2d(i2d_path)
                except Exception:
                    pass
            # Fallback: scale up the .tn thumbnail
            if img is None:
                img = _load_tn_image(tn_path, 128)
                label_txt = f"Preview: {tn_path.name}  (no i2d decode)"
            else:
                label_txt = f"{img.width}×{img.height}px  |  {i2d_path.name}"
            self.after(0, lambda: self._show_detail(img, label_txt))

        import threading
        threading.Thread(target=_worker, daemon=True).start()

    def _show_detail(self, img, label_txt: str):
        if img is None:
            self._decode_lbl.config(text="Decode failed")
            return
        self._full_img = img
        # Fit into the detail canvas
        cw = self._detail_canvas.winfo_width()  or 300
        ch = self._detail_canvas.winfo_height() or 300
        scale = min(cw / max(img.width, 1), ch / max(img.height, 1), 4.0)
        dw = max(1, int(img.width  * scale))
        dh = max(1, int(img.height * scale))

        disp = img.resize((dw, dh), Image.NEAREST)
        # Composite onto dark background
        bg = Image.new("RGBA", (dw, dh), (20, 20, 30, 255))
        if disp.mode == "RGBA":
            bg.paste(disp, (0, 0), disp)
        else:
            bg.paste(disp.convert("RGBA"), (0, 0))
        ph = ImageTk.PhotoImage(bg)
        self._full_ph = ph

        self._detail_canvas.delete("all")
        self._detail_canvas.create_image(cw // 2, ch // 2,
                                          anchor="center", image=ph)
        self._detail_canvas.configure(scrollregion=self._detail_canvas.bbox("all"))
        self._dim_lbl.config(text=f"{img.width}×{img.height} px")
        self._decode_lbl.config(text=label_txt)
        self._status.set(label_txt)

    def _on_resize(self, _=None):
        w = self._canvas.winfo_width()
        self._canvas.itemconfig(self._win_id, width=w)

    def _export_all(self):
        """Batch-decode and save all sprites in the current category as PNGs."""
        if not self._tn_items:
            self._status.set("No sprites loaded — select a category first")
            return
        cat  = self._cat.get()
        dest = self.cfg.renders_dir / cat
        dest.mkdir(parents=True, exist_ok=True)

        total = len(self._tn_items)
        self._export_stop = False
        self._export_btn.config(text="Stop", command=self._stop_export,
                                bg=RED)

        def _worker(self=self, cat=cat, dest=dest, total=total):
            ok = skip = 0
            for n, (tn_path, i2d_path) in enumerate(self._tn_items, 1):
                if self._export_stop:
                    break
                out = dest / f"{tn_path.stem}.png"
                img = None
                # Try full i2d decode first
                if i2d_path.is_file():
                    try:
                        from decoders.i2d import decode_i2d
                        img = decode_i2d(i2d_path)
                    except Exception:
                        pass
                # Fallback: scale up the .tn thumbnail (48×48)
                if img is None:
                    img = _load_tn_image(tn_path, 64)
                if img:
                    try:
                        img.save(str(out))
                        ok += 1
                    except Exception:
                        skip += 1
                else:
                    skip += 1
                if n % 20 == 0 or n == total:
                    self.after(0, lambda n=n: self._status.set(
                        f"Exporting {cat}: {n}/{total}…"))
            self.after(0, self._on_export_done, ok, skip, dest)

        threading.Thread(target=_worker, daemon=True).start()

    def _stop_export(self):
        self._export_stop = True

    def _on_export_done(self, ok: int, skip: int, dest: Path):
        self._export_btn.config(text="Export All", command=self._export_all,
                                bg=ACCENT2)
        self._status.set(
            f"Export done: {ok} saved, {skip} skipped → {dest}")

    def _save_full_png(self):
        if self._full_img is None:
            self._status.set("Nothing to save — click a sprite first")
            return
        self.cfg.renders_dir.mkdir(exist_ok=True)
        name = self._sel_name.get() or "sprite"
        out = self.cfg.renders_dir / f"{name}.png"
        try:
            self._full_img.save(str(out))
            self._status.set(f"Saved: {out.name}")
        except Exception as e:
            self._status.set(f"Save failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  SOUNDS TAB
# ═══════════════════════════════════════════════════════════════════════════════

from decoders.i2d import decode_i2d, decode_i2d_info
