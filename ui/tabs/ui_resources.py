from PIL import Image
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from ui.theme import THEME, FONTS
from core.constants import *
from ui.widgets import *
from core.parsers import *
class UIResourcesTab(tk.Frame):
    _THUMB = 80   # element tile size
    _BG_W  = 480  # preview max width
    _BG_H  = 320  # preview max height

    def __init__(self, parent, config, status: StatusBar):
        self.cfg = config
        super().__init__(parent, bg=THEME["bg_mid"])
        self._status      = status
        self._dat_files   : Dict[str, Path] = {}
        self._raw_imgs    : List[Optional["Image.Image"]] = []
        self._thumb_phs   : List["ImageTk.PhotoImage"] = []
        self._cur_file    : Optional[Path] = None
        self._cur_frame   : int = 0
        self._bg_idx      : int = 0
        self._anim_id     : Optional[str] = None
        self._playing     : bool = False
        self._fps_var     : tk.IntVar
        self._export_stop : bool = False
        self._build_ui()
        self.after(300, self._load_files)

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Top toolbar
        bar = tk.Frame(self, bg=THEME["bg_dark"], pady=4)
        bar.pack(fill="x")
        tk.Label(bar, text="UI Resources", bg=THEME["bg_dark"], fg=THEME["accent"],
                 font=FONTS["header"]).pack(side="left", padx=10)
        self._count_lbl = tk.Label(bar, text="", bg=THEME["bg_dark"], fg=THEME["fg_dim"],
                                   font=FONTS["small"])
        self._count_lbl.pack(side="left", padx=6)
        tk.Button(bar, text="Export All UI", bg=ACCENT3, fg="#000",
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=8,
                  command=self._export_all).pack(side="right", padx=4)
        tk.Button(bar, text="Export Frames", bg=ACCENT2, fg="#000",
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=8,
                  command=self._export_file).pack(side="right", padx=4)

        # Horizontal split: tree | content
        pane = tk.PanedWindow(self, orient="horizontal", bg=THEME["bg_dark"],
                              sashwidth=4, sashpad=0)
        pane.pack(fill="both", expand=True)

        # ── Left: category tree ──────────────────────────────────────────────
        left = tk.Frame(pane, bg=THEME["bg_panel"], width=220)
        pane.add(left, minsize=160)
        tk.Label(left, text="Files", bg=THEME["bg_panel"], fg=THEME["fg_dim"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8, pady=(4, 0))
        sb_tv = ttk.Scrollbar(left, orient="vertical")
        sb_tv.pack(side="right", fill="y")
        self._tv = ttk.Treeview(left, yscrollcommand=sb_tv.set,
                                selectmode="browse", show="tree")
        sb_tv.config(command=self._tv.yview)
        self._tv.pack(fill="both", expand=True)
        self._tv.bind("<<TreeviewSelect>>", self._on_select)

        # ── Right: vertical split — preview top, tile grid bottom ────────────
        right = tk.Frame(pane, bg=THEME["bg_dark"])
        pane.add(right, minsize=500)

        v_pane = tk.PanedWindow(right, orient="vertical", bg=THEME["bg_dark"],
                                sashwidth=5)
        v_pane.pack(fill="both", expand=True)

        # ─ Preview panel ─────────────────────────────────────────────────────
        preview_outer = tk.Frame(v_pane, bg=THEME["bg_dark"])
        v_pane.add(preview_outer, minsize=180)

        # Info + animate controls on one bar above the canvas
        pbar = tk.Frame(preview_outer, bg=THEME["bg_mid"], pady=3)
        pbar.pack(fill="x")
        self._file_lbl = tk.Label(pbar, text="Select a file", bg=THEME["bg_mid"],
                                  fg=THEME["accent"], font=("Segoe UI", 10, "bold"))
        self._file_lbl.pack(side="left", padx=10)
        self._info_lbl = tk.Label(pbar, text="", bg=THEME["bg_mid"], fg=THEME["fg_dim"],
                                  font=FONTS["small"])
        self._info_lbl.pack(side="left", padx=6)

        self._fps_var = tk.IntVar(value=8)
        self._play_btn = tk.Button(pbar, text="▶ Animate", bg=THEME["bg_mid"],
                                   fg=THEME["fg_text"], relief="flat",
                                   font=("Segoe UI", 8), padx=6,
                                   command=self._toggle_play)
        self._play_btn.pack(side="right", padx=4)
        tk.Spinbox(pbar, from_=1, to=30, textvariable=self._fps_var,
                   bg=THEME["bg_panel"], fg=THEME["fg_text"], buttonbackground=BG_MID,
                   relief="flat", width=3,
                   font=("Segoe UI", 8)).pack(side="right", padx=(0, 2))
        tk.Label(pbar, text="fps", bg=THEME["bg_mid"], fg=THEME["fg_dim"],
                 font=("Segoe UI", 8)).pack(side="right")

        # Large preview canvas (background / selected element)
        self._preview_canvas = tk.Canvas(preview_outer, bg="#080812",
                                         bd=0, highlightthickness=0)
        self._preview_canvas.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        self._preview_canvas.bind("<Configure>", lambda e: self._draw_preview())

        # ─ Tile grid ─────────────────────────────────────────────────────────
        grid_outer = tk.Frame(v_pane, bg=THEME["bg_dark"])
        v_pane.add(grid_outer, minsize=120)

        gbar = tk.Frame(grid_outer, bg=THEME["bg_mid"], pady=2)
        gbar.pack(fill="x")
        self._grid_lbl = tk.Label(gbar, text="Elements", bg=THEME["bg_mid"],
                                  fg=THEME["accent_light"], font=("Segoe UI", 9, "bold"))
        self._grid_lbl.pack(side="left", padx=10)
        self._frame_nav = tk.Label(gbar, text="", bg=THEME["bg_mid"], fg=THEME["fg_dim"],
                                   font=("Segoe UI", 8))
        self._frame_nav.pack(side="left", padx=6)

        h_sb = ttk.Scrollbar(grid_outer, orient="horizontal")
        h_sb.pack(side="bottom", fill="x")
        v_sb = ttk.Scrollbar(grid_outer, orient="vertical")
        v_sb.pack(side="right", fill="y")
        self._grid_canvas = tk.Canvas(grid_outer, bg=THEME["bg_dark"], bd=0,
                                      highlightthickness=0,
                                      xscrollcommand=h_sb.set,
                                      yscrollcommand=v_sb.set)
        self._grid_canvas.pack(fill="both", expand=True)
        h_sb.config(command=self._grid_canvas.xview)
        v_sb.config(command=self._grid_canvas.yview)
        self._grid_inner = tk.Frame(self._grid_canvas, bg=THEME["bg_dark"])
        self._grid_win = self._grid_canvas.create_window(
            (0, 0), window=self._grid_inner, anchor="nw")
        self._grid_inner.bind("<Configure>", lambda e:
            self._grid_canvas.configure(
                scrollregion=self._grid_canvas.bbox("all")))
        self._grid_canvas.bind("<Configure>", lambda e:
            self._grid_canvas.itemconfig(self._grid_win, width=e.width))

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_files(self):
        self._dat_files.clear()
        for p in sorted(self.cfg.resources.glob("*.dat")):
            self._dat_files[p.stem.lower()] = p
        for p in sorted(self.cfg.imagery.glob("*.dat")):
            if p.stem.lower() not in self._dat_files:
                self._dat_files[p.stem.lower()] = p

        stem_to_cat: Dict[str, str] = {}
        for cat, stems in _UI_CATEGORIES.items():
            for s in stems:
                stem_to_cat[s.lower()] = cat

        buckets: Dict[str, List[tuple]] = {c: [] for c in _UI_CATEGORIES}
        buckets["Misc"] = []
        from core.parsers import scan_dat_frames
        for stem, path in sorted(self._dat_files.items()):
            cat = stem_to_cat.get(stem, "Misc")
            n = scan_dat_frames(path)
            buckets.setdefault(cat, []).append((stem, path, n))

        self._tv.delete(*self._tv.get_children())
        total = 0
        for cat in list(_UI_CATEGORIES.keys()) + ["Misc"]:
            items = buckets.get(cat, [])
            if not items:
                continue
            node = self._tv.insert("", "end",
                                   text=f"  {cat}  ({len(items)})",
                                   open=False, tags=("cat",))
            for stem, path, n in items:
                tag = f"  {stem}.dat" + (f"  [{n}f]" if n else "  [?]")
                self._tv.insert(node, "end", text=tag,
                                values=(str(path),), tags=("file",))
                total += 1

        self._tv.tag_configure("cat",  foreground=ACCENT2,
                               font=("Segoe UI", 9, "bold"))
        self._tv.tag_configure("file", foreground=FG_TEXT,
                               font=FONTS["small"])
        self._count_lbl.config(text=f"{total} .dat files")

    # ── Selection / display ───────────────────────────────────────────────────

    def _on_select(self, _=None):
        sel = self._tv.selection()
        if not sel:
            return
        vals = self._tv.item(sel[0], "values")
        if not vals:
            return
        path = Path(vals[0])
        if path != self._cur_file:
            self._stop_anim()
            self._cur_file = path
            self._show_file(path)

    def _show_file(self, path: Path):
        self._stop_anim()
        self._file_lbl.config(text=path.name)
        self._info_lbl.config(text="Decoding…")
        for w in self._grid_inner.winfo_children():
            w.destroy()
        self._raw_imgs.clear()
        self._thumb_phs.clear()
        self._cur_frame = 0

        from core.parsers import scan_dat_frames
        n = scan_dat_frames(path)
        if not HAS_PIL or n == 0:
            self._info_lbl.config(text="Not CGSR / PIL unavailable")
            self._preview_canvas.delete("all")
            return

        # Decode all frames using fast BGR555 path
        for i in range(n):
            img = decode_dat_frame(path, i)
            # If standard decoder got it, convert pixels via fast path for large images
            self._raw_imgs.append(img)

        valid = [(i, img) for i, img in enumerate(self._raw_imgs) if img]
        if not valid:
            self._info_lbl.config(text=f"{n} frames — no decodable images")
            self._preview_canvas.delete("all")
            return

        # Background = largest image by area
        self._bg_idx, bg_img = max(valid, key=lambda t: t[1].width * t[1].height)

        # Detect font file: all images narrow & short (glyph sheet)
        all_glyphs = all(img.width <= 24 and img.height <= 32 for _, img in valid)
        if all_glyphs and len(valid) >= 20:
            self._show_font_map(valid)
            return

        # Info bar
        n_elem = len(valid) - 1
        self._info_lbl.config(
            text=f"{bg_img.width}×{bg_img.height} BG  |  "
                 f"{n_elem} element{'s' if n_elem != 1 else ''}  |  {n} frames")
        self._grid_lbl.config(text="Elements")

        # Build tile grid (only valid images shown)
        THUMB = self._THUMB
        cw = self._grid_canvas.winfo_width() or (8 * (THUMB + 10))
        cols = max(1, cw // (THUMB + 10))

        for gi, (fi, img) in enumerate(valid):
            is_bg = (fi == self._bg_idx)
            t = img.copy()
            t.thumbnail((THUMB, THUMB))
            ph = ImageTk.PhotoImage(t)
            self._thumb_phs.append(ph)

            hl_bg   = ACCENT  if is_bg else BG_CARD
            hl_brd  = ACCENT  if is_bg else BORDER
            fg_lbl  = "#000"  if is_bg else FG_DIM

            cell = tk.Frame(self._grid_inner, bg=hl_bg,
                            highlightthickness=2,
                            highlightbackground=hl_brd)
            cell.grid(row=gi // cols, column=gi % cols, padx=4, pady=4)

            img_lbl = tk.Label(cell, image=ph, bg=hl_bg,
                               width=THUMB, height=THUMB)
            img_lbl.image = ph
            img_lbl.pack(padx=2, pady=(2, 0))

            tag  = "BG" if is_bg else f"f{fi}"
            dims = f"{img.width}×{img.height}"
            tk.Label(cell, text=f"{tag}  {dims}", bg=hl_bg, fg=fg_lbl,
                     font=("Segoe UI", 7, "bold" if is_bg else "normal")).pack(pady=(0, 2))

            for w in (img_lbl, cell):
                w.bind("<Button-1>", lambda e, idx=fi: self._select_frame(idx))

        self._frame_nav.config(text=f"{len(valid)} images")
        self._select_frame(self._bg_idx)

    def _show_font_map(self, valid: List[Tuple[int, "Image.Image"]]):
        """Display glyph sheet — one tile per character glyph in ASCII order."""
        self._grid_lbl.config(text="Font Glyphs")
        # ASCII printable starts at 32 (space); glyph f1 = ASCII 32
        # gamefont.dat frame 0 is metadata, frames 1..86 = glyphs for ASCII 32..117
        COLS = 16
        for gi, (fi, img) in enumerate(valid):
            char_code = 31 + fi   # frame 1 → ASCII 32 = space
            char = chr(char_code) if 32 <= char_code <= 126 else "?"
            scale = max(1, 40 // max(img.width, img.height, 1))
            nw, nh = img.width * scale, img.height * scale
            ph = ImageTk.PhotoImage(img.resize((nw, nh), Image.NEAREST))
            self._thumb_phs.append(ph)

            cell = tk.Frame(self._grid_inner, bg=BG_CARD,
                            highlightthickness=1, highlightbackground=BORDER)
            cell.grid(row=gi // COLS, column=gi % COLS, padx=2, pady=2)

            tk.Label(cell, image=ph, bg=BG_CARD,
                     width=40, height=40).pack()
            tk.Label(cell, text=f"'{char}'", bg=BG_CARD, fg=THEME["accent_light"],
                     font=("Consolas", 7)).pack()
            cell._ph = ph

        total = len(valid)
        self._info_lbl.config(text=f"{total} glyphs  (font)")
        self._frame_nav.config(text=f"ASCII {32}–{31+total}")
        # Show first glyph in preview
        self._select_frame(valid[0][0] if valid else 0)

    def _select_frame(self, idx: int):
        self._cur_frame = idx
        n = len(self._raw_imgs)
        self._frame_nav.config(text=f"f{idx}  |  {n} frames")
        self._draw_preview()

    def _draw_preview(self):
        c = self._preview_canvas
        c.delete("all")
        imgs = self._raw_imgs
        if not imgs or self._cur_frame >= len(imgs):
            return
        img = imgs[self._cur_frame]
        if not img:
            cw, ch = max(1, c.winfo_width()), max(1, c.winfo_height())
            c.create_text(cw // 2, ch // 2,
                          text="(metadata frame — no image)",
                          fill=FG_MUTED, font=FONTS["body"])
            return
        cw = max(1, c.winfo_width())
        ch = max(1, c.winfo_height())
        # Never upscale beyond 2× for crisp pixel art; downscale freely
        scale = min(cw / img.width, ch / img.height, 2.0)
        nw = max(1, int(img.width  * scale))
        nh = max(1, int(img.height * scale))
        mode = Image.NEAREST if scale >= 1.5 else Image.LANCZOS
        ph = ImageTk.PhotoImage(img.resize((nw, nh), mode))
        c.create_image(cw // 2, ch // 2, image=ph, anchor="center")
        c._ph = ph
        # Dimension overlay bottom-left
        c.create_text(8, ch - 8,
                      text=f"{img.width}×{img.height}",
                      fill=FG_DIM, font=("Segoe UI", 8), anchor="sw")

    # ── Animation ─────────────────────────────────────────────────────────────

    def _toggle_play(self):
        if self._playing:
            self._stop_anim()
        else:
            self._start_anim()

    def _start_anim(self):
        valid = [i for i, img in enumerate(self._raw_imgs) if img]
        if len(valid) < 2:
            return
        self._anim_valid = valid
        self._anim_vi    = 0
        self._playing    = True
        self._play_btn.config(text="■ Stop")
        self._anim_tick()

    def _anim_tick(self):
        if not self._playing:
            return
        self._anim_vi = (self._anim_vi + 1) % len(self._anim_valid)
        self._select_frame(self._anim_valid[self._anim_vi])
        delay = max(33, 1000 // max(1, self._fps_var.get()))
        self._anim_id = self.after(delay, self._anim_tick)

    def _stop_anim(self):
        self._playing = False
        self._play_btn.config(text="▶ Animate")
        if self._anim_id:
            self.after_cancel(self._anim_id)
            self._anim_id = None

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_file(self):
        if not self._cur_file or not self._raw_imgs:
            self._status.set("No file selected")
            return
        dest = self.cfg.renders_dir / "UI" / self._cur_file.stem
        dest.mkdir(parents=True, exist_ok=True)
        ok = 0
        for i, img in enumerate(self._raw_imgs):
            if img:
                try:
                    img.save(str(dest / f"frame_{i:03d}.png"))
                    ok += 1
                except Exception:
                    pass
        self._status.set(f"Exported {ok} frames → {dest}")

    def _export_all(self):
        if not self._dat_files:
            self._status.set("No files loaded")
            return
        self._export_stop = False
        dest_root = self.cfg.renders_dir / "UI"
        files = sorted(self._dat_files.items())
        total = len(files)

        def _worker(self=self, files=files, dest_root=dest_root, total=total):
            ok_files = ok_frames = 0
            from core.parsers import scan_dat_frames, decode_dat_frame
            for i, (stem, path) in enumerate(files, 1):
                if self._export_stop:
                    break
                n = scan_dat_frames(path)
                if n == 0:
                    continue
                dest = dest_root / stem
                dest.mkdir(parents=True, exist_ok=True)
                for fi in range(n):
                    img = decode_dat_frame(path, fi)
                    if img:
                        try:
                            img.save(str(dest / f"frame_{fi:03d}.png"))
                            ok_frames += 1
                        except Exception:
                            pass
                ok_files += 1
                self.after(0, lambda i=i: self._status.set(
                    f"Exporting UI: {i}/{total} files…"))
            self.after(0, lambda: self._status.set(
                f"UI export done — {ok_files} files, {ok_frames} frames → {dest_root}"))

        threading.Thread(target=_worker, daemon=True).start()
