from __future__ import annotations
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from ui.theme import THEME, FONTS
from core.constants import *
from ui.widgets import *
from core.parsers import *

THUMB_SIZE  = 48
CELL_W      = 72
CELL_H      = 66
GRID_COLS   = 8

def decode_tn_pixels(raw: bytes) -> Optional[bytes]:
    if len(raw) < 768: return None
    import struct
    pal = []
    for i in range(256):
        word = struct.unpack_from('<H', raw, i * 2)[0]
        r = ((word >> 10) & 0x1F) << 3
        g = ((word >>  5) & 0x1F) << 3
        b = ( word        & 0x1F) << 3
        pal.append((r, g, b))
    indices = raw[512:768]
    pixels  = bytearray(256 * 4)
    for j in range(256):
        idx = indices[j]
        r, g, b = pal[idx]
        a = 0 if idx == 0 else 255
        pixels[j * 4 : j * 4 + 4] = [r, g, b, a]
    return bytes(pixels)

def load_tn_image(tn_path: Path, size: int = 48, bg: tuple = (30, 42, 69)) -> Optional['Image.Image']:
    if not HAS_PIL: return None
    try:
        raw = tn_path.read_bytes()
        px = decode_tn_pixels(raw)
        if px is None: return None
        from PIL import Image
        rgba = Image.frombytes('RGBA', (16, 16), px)
        canvas = Image.new('RGB', (16, 16), bg)
        canvas.paste(rgba, mask=rgba.split()[3])
        return canvas.resize((size, size), Image.NEAREST)
    except Exception: return None

class SpritesTab(tk.Frame):
    def __init__(self, parent, config, status: StatusBar):
        self.cfg = config
        super().__init__(parent, bg=THEME["bg_mid"])
        self._status      = status
        self._cats        = get_sprite_categories(self.cfg)
        self._cat         = tk.StringVar(value=self._cats[0] if self._cats else "")
        self._ph_cache: dict[str, "ImageTk.PhotoImage"] = {}
        self._full_img    = None
        self._full_ph     = None
        self._tn_items: list[tuple[Path, Path]] = []
        self._sel_name    = tk.StringVar(value="")
        self._export_stop = False
        self._build_ui()
        if self._cats:
            self.after(200, lambda: self._load_category(self._cats[0]))

    def _build_ui(self):
        bar = tk.Frame(self, bg=THEME["bg_dark"], pady=4)
        bar.pack(fill="x")
        tk.Label(bar, text="Category:", bg=THEME["bg_dark"], fg=THEME["fg_dim"], font=FONTS["body"]).pack(side="left", padx=(12, 4))
        self._cat_cb = ttk.Combobox(bar, textvariable=self._cat, values=self._cats, state="readonly", width=14)
        self._cat_cb.pack(side="left", padx=(0, 10))
        self._cat_cb.bind("<<ComboboxSelected>>", self._on_cat_change)
        self._count_lbl = tk.Label(bar, text="", bg=THEME["bg_dark"], fg=THEME["fg_dim"], font=FONTS["small"])
        self._count_lbl.pack(side="left", padx=10)
        tk.Button(bar, text="Save PNG", bg=THEME["bg_panel"], fg=THEME["fg_text"], relief="flat", padx=8, command=self._save_full_png).pack(side="right", padx=4)
        self._export_btn = tk.Button(bar, text="Export All", bg=THEME["accent_light"], fg="white", relief="flat", padx=8, command=self._export_all)
        self._export_btn.pack(side="right", padx=4)

        paned = tk.PanedWindow(self, orient="horizontal", bg=THEME["bg_dark"], sashwidth=4, sashrelief="flat")
        paned.pack(fill="both", expand=True)
        left = tk.Frame(paned, bg=THEME["bg_mid"])
        paned.add(left, minsize=200)
        self._canvas = tk.Canvas(left, bg=THEME["bg_mid"], highlightthickness=0)
        vsb = ttk.Scrollbar(left, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._canvas.bind("<Configure>", self._on_resize)
        self._inner = tk.Frame(self._canvas, bg=THEME["bg_mid"])
        self._win_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>", lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))

        right = tk.Frame(paned, bg=THEME["bg_panel"], width=340)
        paned.add(right, minsize=240)
        tk.Label(right, textvariable=self._sel_name, bg=THEME["bg_panel"], fg=THEME["accent_light"], font=FONTS["header"], anchor="center").pack(fill="x", pady=(10, 4))
        self._dim_lbl = tk.Label(right, text="", bg=THEME["bg_panel"], fg=THEME["fg_dim"], font=FONTS["small"])
        self._dim_lbl.pack(fill="x", padx=10)
        self._detail_canvas = tk.Canvas(right, bg=THEME["bg_mid"], highlightthickness=1, highlightbackground=THEME["bg_dark"])
        self._detail_canvas.pack(fill="both", expand=True, padx=10, pady=10)
        self._decode_lbl = tk.Label(right, text="", bg=THEME["bg_panel"], fg=THEME["fg_dim"], font=("Segoe UI", 8))
        self._decode_lbl.pack(pady=(0, 6))

    def _on_cat_change(self, _=None):
        self._load_category(self._cat.get())

    def _load_category(self, cat: str):
        tn_dir, img_dir = self.cfg.thumbnails / cat, self.cfg.imagery_assets / cat
        if not tn_dir.exists():
            self._status.set(f"No thumbnails for {cat}")
            return
        self._ph_cache.clear()
        _seen, tn_files = set(), []
        for f in sorted(tn_dir.iterdir()):
            if f.suffix.lower() == ".tn" and f.stem.lower() not in _seen:
                _seen.add(f.stem.lower()); tn_files.append(f)
        i2d_index = {f.stem.lower(): f for f in img_dir.iterdir() if f.suffix.lower() == ".i2d"} if img_dir.exists() else {}
        self._tn_items = [(tn, i2d_index.get(tn.stem.lower(), Path(""))) for tn in tn_files]
        self._count_lbl.config(text=f"{len(self._tn_items)} sprites")
        self._rebuild_grid()

    def _rebuild_grid(self):
        for w in self._inner.winfo_children(): w.destroy()
        ncols = max(1, GRID_COLS)
        for idx, (tn_path, i2d_path) in enumerate(self._tn_items):
            cell = tk.Frame(self._inner, bg=THEME["bg_mid"], width=CELL_W, height=CELL_H)
            cell.grid_propagate(False); cell.grid(row=idx//ncols, column=idx%ncols, padx=2, pady=2)
            img = load_tn_image(tn_path, THUMB_SIZE)
            if img and HAS_PIL:
                from PIL import ImageTk
                ph = ImageTk.PhotoImage(img); self._ph_cache[str(tn_path)] = ph
                lbl = tk.Label(cell, image=ph, bg=THEME["bg_mid"], cursor="hand2")
                lbl._photo = ph; lbl.pack(pady=(3, 0))
            else:
                lbl = tk.Label(cell, text="?", bg=THEME["bg_mid"], fg=THEME["fg_dim"], width=4, height=3)
                lbl.pack(pady=(3, 0))
            tk.Label(cell, text=tn_path.stem[:11], bg=THEME["bg_mid"], fg=THEME["fg_text"], font=("Segoe UI", 7)).pack()
            for w in (cell, lbl): w.bind("<Button-1>", lambda e, tp=tn_path, ip=i2d_path: self._on_click(tp, ip))

    def _on_click(self, tn_path: Path, i2d_path: Path):
        self._sel_name.set(tn_path.stem); self._status.set(f"Decoding {tn_path.stem}…")
        def _worker():
            img = None
            if i2d_path.is_file():
                try:
                    from decoders.i2d import decode_i2d
                    img = decode_i2d(i2d_path)
                except Exception: pass
            if img is None: img = load_tn_image(tn_path, 128); txt = f"Preview: {tn_path.name} (no i2d)"
            else: txt = f"{img.width}×{img.height}px | {i2d_path.name}"
            self.after(0, lambda: self._show_detail(img, txt))
        threading.Thread(target=_worker, daemon=True).start()

    def _show_detail(self, img, label_txt):
        if img is None: return
        self._full_img = img; cw, ch = self._detail_canvas.winfo_width() or 300, self._detail_canvas.winfo_height() or 300
        scale = min(cw / max(img.width, 1), ch / max(img.height, 1), 4.0)
        from PIL import Image, ImageTk
        disp = img.resize((int(img.width * scale), int(img.height * scale)), Image.NEAREST)
        bg = Image.new("RGBA", disp.size, (20, 20, 30, 255))
        bg.paste(disp, (0, 0), disp if disp.mode == "RGBA" else None)
        ph = ImageTk.PhotoImage(bg); self._full_ph = ph
        self._detail_canvas.delete("all"); self._detail_canvas.create_image(cw // 2, ch // 2, anchor="center", image=ph)
        self._dim_lbl.config(text=f"{img.width}×{img.height} px"); self._decode_lbl.config(text=label_txt)

    def _on_resize(self, _=None): self._canvas.itemconfig(self._win_id, width=self._canvas.winfo_width())

    def _export_all(self):
        cat, dest = self._cat.get(), self.cfg.renders_dir / self._cat.get()
        dest.mkdir(parents=True, exist_ok=True); self._export_stop = False
        self._export_btn.config(text="Stop", bg=THEME["danger"], command=lambda: setattr(self, '_export_stop', True))
        def _worker():
            ok = skip = 0
            for n, (tn, i2d) in enumerate(self._tn_items, 1):
                if self._export_stop: break
                img = None
                if i2d.is_file():
                    try:
                        from decoders.i2d import decode_i2d
                        img = decode_i2d(i2d)
                    except Exception: pass
                if img is None: img = load_tn_image(tn, 64)
                if img:
                    try: img.save(str(dest / f"{tn.stem}.png")); ok += 1
                    except Exception: skip += 1
                if n % 20 == 0: self.after(0, lambda n=n: self._status.set(f"Exporting {cat}: {n}/{len(self._tn_items)}…"))
            self.after(0, lambda: (self._export_btn.config(text="Export All", bg=THEME["accent_light"], command=self._export_all), self._status.set(f"Export done: {ok} saved → {dest}")))
        threading.Thread(target=_worker, daemon=True).start()

    def _save_full_png(self):
        if not self._full_img: return
        out = self.cfg.renders_dir / f"{self._sel_name.get()}.png"
        try: self._full_img.save(str(out)); self._status.set(f"Saved: {out.name}")
        except Exception as e: self._status.set(f"Save failed: {e}")
