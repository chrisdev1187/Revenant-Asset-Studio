from __future__ import annotations
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from core.constants import *
from ui.widgets import *
from core.parsers import *
class UpscaleTab(tk.Frame):
    """Batch upscaler with per-asset results review, before/after compare, and redo."""

    # ── NVIDIA NIM FLUX text-to-image pipeline ────────────────────────────────
    # Endpoint: POST https://ai.api.nvidia.com/v1/genai/{model}
    # Response: {"artifacts": [{"base64": "..."}]}
    # Auth: NVIDIA_API_KEY in .env  (free key at build.nvidia.com)
    # NIM only accepts: prompt, width, height, seed — nothing else.
    # Valid dimensions (each axis must be from this list):
    #   768 832 896 960 1024 1088 1152 1216 1280 1344
    NIM_BASE_URL     = "https://ai.api.nvidia.com/v1/genai"
    NIM_MODEL        = "black-forest-labs/flux.1-schnell"   # fast batch
    NIM_MODEL_T2I    = "black-forest-labs/flux.1-dev"       # quality textures
    NIM_TEX_SIZE     = 1024
    NIM_VALID_SIZES  = (768, 832, 896, 960, 1024, 1088, 1152, 1216, 1280, 1344)
    DEFAULT_PROMPT   = (
        "retro fantasy RPG game asset, epic heroic lighting, "
        "rich color depth, sharp pixel-art detail, cinematic glow, "
        "dark fantasy atmosphere"
    )
    # Texture-specific prompt — prepended when generating model textures
    DEFAULT_TEX_PROMPT = (
        "4K PBR game texture, dark fantasy RPG character, physically based "
        "rendering, high detail surface material, ultra sharp, seamless, "
        "subsurface scattering, specular highlights, normal map detail"
    )
    DEFAULT_NEG      = (
        "blurry, low quality, dithering artifacts, washed out, flat, "
        "oversaturated, deformed, extra limbs, watermark"
    )
    _SMALL_PX        = 32   # sprites ≤ this skip FLUX → NEAREST resize
    _THUMB_PX        = 56   # thumbnail size in the results list
    _STATUS_COLORS = {"ok": ACCENT3, "flagged": "#f59e0b", "failed": RED}

    def __init__(self, parent, config, status: StatusBar):
        self.cfg = config
        super().__init__(parent, bg=BG_MID)
        self._status   = status
        self._stop     = False
        self._running  = False
        self._results: List[Dict] = []
        self._result_phs: List    = []   # PhotoImage refs — prevent GC
        self._sel_idx: Optional[int] = None
        self._redo_queue: List[int]  = []
        self._redo_chain = False
        self._ffmpeg_path: str = self._detect_ffmpeg() or ""
        self._build_ui()
        self.after(600, self._refresh_counts)

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Top toolbar
        bar = tk.Frame(self, bg=BG_DARK, pady=5)
        bar.pack(fill="x")
        tk.Label(bar, text="Asset Upscaler", bg=BG_DARK, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(side="left", padx=10)

        self._stop_btn = tk.Button(bar, text="Stop", bg=RED, fg="#fff",
                                   relief="flat", font=("Segoe UI", 9, "bold"),
                                   padx=10, command=self._stop_upscale,
                                   state="disabled")
        self._stop_btn.pack(side="right", padx=4)

        self._start_btn = tk.Button(bar, text="Start Upscale", bg=ACCENT3,
                                    fg="#000", relief="flat",
                                    font=("Segoe UI", 9, "bold"), padx=12,
                                    command=self._start_upscale)
        self._start_btn.pack(side="right", padx=4)

        tk.Label(bar, text="Scale:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 9)).pack(side="right", padx=(10, 2))
        self._scale_var = tk.StringVar(value="4")
        ttk.Combobox(bar, textvariable=self._scale_var, values=["2", "4"],
                     state="readonly", width=3).pack(side="right")

        # NIM strength/label hidden — pipeline uses Real-ESRGAN ncnn
        self._strength_var = tk.StringVar(value="0.65")

        # Horizontal split: left (categories) | right (results + compare)
        pane = tk.PanedWindow(self, orient="horizontal", bg=BG_DARK, sashwidth=4)
        pane.pack(fill="both", expand=True)

        # ── Left: category checklist ─────────────────────────────────────────
        left = tk.Frame(pane, bg=BG_PANEL, width=270)
        pane.add(left, minsize=200)
        tk.Label(left, text="Categories", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(8, 4))

        self._cats = {}
        for key, label in [("ui_panels",      "UI Panels"),
                            ("equip_icons",    "Equipment Icons"),
                            ("talisman_icons", "Talisman Icons"),
                            ("model_textures", "Model Textures"),
                            ("sprites",        "Sprites (clean)"),
                            ("cinematix",      "Cinematix  (SMK→MP4)")]:
            row = tk.Frame(left, bg=BG_PANEL)
            row.pack(fill="x", padx=8, pady=2)
            var = tk.BooleanVar(value=(key not in ("sprites", "cinematix")))
            tk.Checkbutton(row, variable=var, text=label,
                           bg=BG_PANEL, fg=FG_TEXT, selectcolor=BG_CARD,
                           activebackground=BG_PANEL, activeforeground=FG_TEXT,
                           font=("Segoe UI", 9), anchor="w").pack(side="left", fill="x", expand=True)
            cnt = tk.Label(row, text="…", bg=BG_PANEL, fg=FG_DIM, font=("Segoe UI", 8))
            cnt.pack(side="right", padx=4)
            tk.Button(row, text="▶1", bg=BG_CARD, fg=ACCENT2, relief="flat",
                      font=("Segoe UI", 7, "bold"), padx=3, pady=0,
                      cursor="hand2",
                      command=lambda k=key: self._test_single(k)).pack(side="right", padx=(0, 2))
            self._cats[key] = (var, cnt)

        # FFmpeg section (required for Cinematix)
        tk.Frame(left, bg=BORDER, height=1).pack(fill="x", padx=8, pady=(6, 2))
        ff_hdr = tk.Frame(left, bg=BG_PANEL)
        ff_hdr.pack(fill="x", padx=8, pady=(2, 0))
        tk.Label(ff_hdr, text="FFmpeg", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        self._ffmpeg_status_lbl = tk.Label(ff_hdr, bg=BG_PANEL,
                                            font=("Segoe UI", 8, "bold"))
        self._ffmpeg_status_lbl.pack(side="left", padx=4)

        ff_btns = tk.Frame(left, bg=BG_PANEL)
        ff_btns.pack(fill="x", padx=8, pady=1)
        self._install_btn = tk.Button(ff_btns, text="Install to project",
                                      bg=ACCENT2, fg="#000", relief="flat",
                                      font=("Segoe UI", 8, "bold"), padx=6,
                                      command=self._install_ffmpeg)
        self._install_btn.pack(side="left")
        tk.Button(ff_btns, text="Browse", bg=BG_CARD, fg=FG_TEXT,
                  relief="flat", font=("Segoe UI", 8), padx=4,
                  command=self._browse_ffmpeg).pack(side="left", padx=4)

        self._ffmpeg_path_var = tk.StringVar(value=self._ffmpeg_path)
        tk.Entry(left, textvariable=self._ffmpeg_path_var, bg=BG_CARD, fg=FG_DIM,
                 font=("Consolas", 7), relief="flat",
                 insertbackground=FG_TEXT).pack(fill="x", padx=8, pady=(1, 4))
        self._ffmpeg_path_var.trace_add("write",
                                         lambda *_: self._on_ffmpeg_path_changed())
        self._update_ffmpeg_status()

        tk.Frame(left, bg=BORDER, height=1).pack(fill="x", padx=8, pady=(2, 4))

        # ── Real-ESRGAN ncnn (video upscaler) ────────────────────────────────
        ncnn_hdr = tk.Frame(left, bg=BG_PANEL)
        ncnn_hdr.pack(fill="x", padx=8, pady=(2, 0))
        tk.Label(ncnn_hdr, text="Real-ESRGAN (Video)", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        self._ncnn_status_lbl = tk.Label(ncnn_hdr, bg=BG_PANEL,
                                          font=("Segoe UI", 8, "bold"))
        self._ncnn_status_lbl.pack(side="left", padx=4)

        ncnn_btns = tk.Frame(left, bg=BG_PANEL)
        ncnn_btns.pack(fill="x", padx=8, pady=1)
        self._ncnn_install_btn = tk.Button(
            ncnn_btns, text="Install to project",
            bg=ACCENT2, fg="#000", relief="flat",
            font=("Segoe UI", 8, "bold"), padx=6,
            command=self._install_ncnn)
        self._ncnn_install_btn.pack(side="left")

        ncnn_model_row = tk.Frame(left, bg=BG_PANEL)
        ncnn_model_row.pack(fill="x", padx=8, pady=(2, 1))
        tk.Label(ncnn_model_row, text="Model:", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(side="left")
        self._ncnn_model_var = tk.StringVar(value="realesrgan-x4plus-anime")
        ttk.Combobox(ncnn_model_row, textvariable=self._ncnn_model_var,
                     values=["realesrgan-x4plus-anime", "realesrgan-x4plus",
                             "realesrnet-x4plus"],
                     state="readonly", width=22).pack(side="left", padx=(4, 0))
        self._update_ncnn_status()

        # Frame step: how often to apply FLUX/ncnn (every N frames; gaps use LANCZOS)
        step_row = tk.Frame(left, bg=BG_PANEL)
        step_row.pack(fill="x", padx=8, pady=(2, 1))
        tk.Label(step_row, text="FLUX every N frames:", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(side="left")
        self._cine_step_var = tk.StringVar(value="4")
        ttk.Combobox(step_row, textvariable=self._cine_step_var,
                     values=["1", "2", "4", "8", "16"],
                     state="readonly", width=4).pack(side="left", padx=(4, 0))
        tk.Label(step_row, text="(1=all, 16=fast)", bg=BG_PANEL, fg=FG_MUTED,
                 font=("Segoe UI", 7)).pack(side="left", padx=4)

        tk.Frame(left, bg=BORDER, height=1).pack(fill="x", padx=8, pady=(4, 4))

        # ── NIM text-to-image (future) ────────────────────────────────────────
        tk.Label(left,
                 text="NIM text-to-image: coming soon",
                 bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 8, "italic")).pack(anchor="w", padx=10, pady=(2, 1))
        tk.Label(left,
                 text="Prompt-driven regeneration will replace ESRGAN\n"
                      "once NVIDIA exposes img2img endpoints.",
                 bg=BG_PANEL, fg=FG_MUTED,
                 font=("Segoe UI", 7), justify="left").pack(anchor="w", padx=10, pady=(0, 4))

        # Hidden Text widgets — kept so _get_prompt()/_get_neg() work when NIM re-enables
        self._prompt_txt = tk.Text(left, height=3, font=("Segoe UI", 8))
        self._prompt_txt.insert("1.0", self.DEFAULT_PROMPT)
        self._neg_txt = tk.Text(left, height=2, font=("Segoe UI", 8))
        self._neg_txt.insert("1.0", self.DEFAULT_NEG)
        self._key_lbl = tk.Label(left, text="", bg=BG_PANEL)

        tk.Frame(left, bg=BORDER, height=1).pack(fill="x", padx=8, pady=(2, 8))
        tk.Label(left, text="Output", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10)
        self._out_lbl = tk.Label(left, text="", bg=BG_PANEL, fg=FG_DIM,
                                 font=("Segoe UI", 8), wraplength=230, justify="left")
        self._out_lbl.pack(anchor="w", padx=10, pady=2)
        tk.Button(left, text="Open Folder", bg=BG_CARD, fg=FG_TEXT,
                  relief="flat", font=("Segoe UI", 8), padx=6,
                  command=self._open_output).pack(anchor="w", padx=10, pady=2)

        # ── Right: progress + results + compare ──────────────────────────────
        right = tk.Frame(pane, bg=BG_DARK)
        pane.add(right, minsize=500)

        # Progress strip
        prog_strip = tk.Frame(right, bg=BG_DARK, pady=3)
        prog_strip.pack(fill="x", padx=10, side="top")
        self._prog_lbl = tk.Label(prog_strip, text="Idle", bg=BG_DARK, fg=FG_DIM,
                                   font=("Segoe UI", 9))
        self._prog_lbl.pack(anchor="w")
        self._prog = ttk.Progressbar(prog_strip, orient="horizontal", mode="determinate")
        self._prog.pack(fill="x", pady=2)

        # System log (3 lines — errors, weights download status)
        self._log = tk.Text(right, bg=BG_DARK, fg=FG_DIM, font=("Consolas", 8),
                            height=3, wrap="none", state="disabled",
                            relief="flat", borderwidth=0, pady=1)
        self._log.pack(fill="x", padx=10, side="top")

        # Vertical pane: results list (top) | compare+redo (bottom)
        v_pane = tk.PanedWindow(right, orient="vertical", bg=BG_DARK, sashwidth=5)
        v_pane.pack(fill="both", expand=True)

        # ── Results list ──────────────────────────────────────────────────────
        res_outer = tk.Frame(v_pane, bg=BG_PANEL)
        v_pane.add(res_outer, minsize=120)

        res_hdr = tk.Frame(res_outer, bg=BG_MID, pady=3)
        res_hdr.pack(fill="x")
        tk.Label(res_hdr, text="Results", bg=BG_MID, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=8)
        self._res_count_lbl = tk.Label(res_hdr, text="0 items", bg=BG_MID, fg=FG_DIM,
                                       font=("Segoe UI", 8))
        self._res_count_lbl.pack(side="left", padx=4)
        tk.Button(res_hdr, text="Redo Flagged", bg=ACCENT, fg="#000",
                  relief="flat", font=("Segoe UI", 8, "bold"), padx=6,
                  command=self._redo_flagged).pack(side="right", padx=4)
        tk.Button(res_hdr, text="Clear", bg=BG_CARD, fg=FG_DIM,
                  relief="flat", font=("Segoe UI", 8), padx=6,
                  command=self._clear_results).pack(side="right", padx=4)

        # Column header row
        hdr = tk.Frame(res_outer, bg=BG_CARD, pady=2)
        hdr.pack(fill="x")
        for txt, anchor, expand, px in [
            ("Before/After", "w", False, (4, 2)),
            ("Name", "w", True, (2, 2)),
            ("Dimensions", "w", False, (2, 2)),
            ("Status", "center", False, (2, 4)),
            ("Actions", "center", False, (2, 8)),
        ]:
            tk.Label(hdr, text=txt, bg=BG_CARD, fg=FG_DIM,
                     font=("Segoe UI", 8, "bold"), anchor=anchor).pack(
                side="left", padx=px, fill="x" if expand else None, expand=expand)

        # Scrollable canvas for result cards
        res_body = tk.Frame(res_outer, bg=BG_PANEL)
        res_body.pack(fill="both", expand=True)
        self._res_canvas = tk.Canvas(res_body, bg=BG_PANEL, highlightthickness=0)
        res_sb = ttk.Scrollbar(res_body, orient="vertical", command=self._res_canvas.yview)
        res_sb.pack(side="right", fill="y")
        self._res_canvas.pack(side="left", fill="both", expand=True)
        self._res_canvas.configure(yscrollcommand=res_sb.set)

        self._results_inner = tk.Frame(self._res_canvas, bg=BG_PANEL)
        self._res_win = self._res_canvas.create_window((0, 0), window=self._results_inner,
                                                        anchor="nw")

        def _on_inner_cfg(e, self=self):
            self._res_canvas.configure(scrollregion=self._res_canvas.bbox("all"))

        def _on_canvas_cfg(e, self=self):
            self._res_canvas.itemconfig(self._res_win, width=self._res_canvas.winfo_width())

        self._results_inner.bind("<Configure>", _on_inner_cfg)
        self._res_canvas.bind("<Configure>", _on_canvas_cfg)
        self._res_canvas.bind("<MouseWheel>",
                              lambda e: self._res_canvas.yview_scroll(
                                  int(-1 * (e.delta / 120)), "units"))

        # ── Compare & Redo panel ──────────────────────────────────────────────
        cmp_outer = tk.Frame(v_pane, bg=BG_DARK)
        v_pane.add(cmp_outer, minsize=200)

        cmp_hdr = tk.Frame(cmp_outer, bg=BG_MID, pady=3)
        cmp_hdr.pack(fill="x")
        tk.Label(cmp_hdr, text="Compare & Redo", bg=BG_MID, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=8)
        self._cmp_name_lbl = tk.Label(cmp_hdr, text="Select a result above",
                                      bg=BG_MID, fg=FG_DIM, font=("Segoe UI", 9))
        self._cmp_name_lbl.pack(side="left", padx=8)

        cmp_body = tk.Frame(cmp_outer, bg=BG_DARK)
        cmp_body.pack(fill="both", expand=True)

        before_col = tk.Frame(cmp_body, bg=BG_DARK)
        before_col.pack(side="left", fill="both", expand=True, padx=(6, 3), pady=4)
        tk.Label(before_col, text="Before (original)", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(anchor="w")
        self._cmp_before = tk.Canvas(before_col, bg=BG_PANEL, highlightthickness=1,
                                      highlightbackground=BORDER)
        self._cmp_before.pack(fill="both", expand=True)

        after_col = tk.Frame(cmp_body, bg=BG_DARK)
        after_col.pack(side="left", fill="both", expand=True, padx=(3, 6), pady=4)
        tk.Label(after_col, text="After (upscaled)", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(anchor="w")
        self._cmp_after = tk.Canvas(after_col, bg=BG_PANEL, highlightthickness=1,
                                     highlightbackground=BORDER)
        self._cmp_after.pack(fill="both", expand=True)

        # Redo params bar
        params_bar = tk.Frame(cmp_outer, bg=BG_MID, pady=4)
        params_bar.pack(fill="x", side="bottom")

        tk.Label(params_bar, text="Strength:", bg=BG_MID, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(side="left", padx=(8, 2))
        self._redo_strength_var = tk.StringVar(value="0.65")
        ttk.Combobox(params_bar, textvariable=self._redo_strength_var,
                     values=["0.45", "0.55", "0.65", "0.75", "0.85"],
                     state="readonly", width=6).pack(side="left")

        tk.Label(params_bar, text="Scale:", bg=BG_MID, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(side="left", padx=(8, 2))
        self._redo_scale_var = tk.StringVar(value="4")
        ttk.Combobox(params_bar, textvariable=self._redo_scale_var,
                     values=["2", "4"], state="readonly", width=3).pack(side="left")

        tk.Button(params_bar, text="Open File", bg=BG_CARD, fg=FG_TEXT,
                  relief="flat", font=("Segoe UI", 8), padx=6,
                  command=self._open_selected).pack(side="right", padx=4)
        self._flag_btn = tk.Button(params_bar, text="Flag", bg="#f59e0b", fg="#000",
                                   relief="flat", font=("Segoe UI", 8, "bold"), padx=6,
                                   command=self._toggle_flag)
        self._flag_btn.pack(side="right", padx=4)
        tk.Button(params_bar, text="Redo This", bg=ACCENT3, fg="#000",
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=10,
                  command=self._redo_selected).pack(side="right", padx=4)

    # ── Basic helpers ─────────────────────────────────────────────────────────

    def _log_line(self, text: str):
        self._log.config(state="normal")
        self._log.insert("end", text + "\n")
        self._log.see("end")
        self._log.config(state="disabled")

    def _set_progress(self, done: int, total: int, msg: str = ""):
        self._prog["value"] = (done / total * 100) if total else 0
        self._prog_lbl.config(text=f"{msg}  {done}/{total}" if msg else f"{done}/{total}")

    def _open_output(self):
        out = self.cfg.renders_dir / "upscaled"
        if out.exists():
            os.startfile(str(out))

    def _refresh_counts(self):
        self._out_lbl.config(text=str(self.cfg.renders_dir / "upscaled"))
        ui_n  = sum(1 for _ in self.cfg.resources.glob("*.dat")) if self.cfg.resources.exists() else 0
        eq_n  = len(list((self.cfg.thumbnails / "Equip").glob("*.tn"))) if (self.cfg.thumbnails / "Equip").exists() else 0
        tal_n = len(list((self.cfg.thumbnails / "Magic").glob("*.tn"))) if (self.cfg.thumbnails / "Magic").exists() else 0
        i3d_n = len(list(self.cfg.imagery_assets.rglob("*.i3d"))) if self.cfg.imagery_assets.exists() else 0
        i2d_n = len(list(self.cfg.imagery_assets.rglob("*.i2d"))) if self.cfg.imagery_assets.exists() else 0
        smk_n = len(self._find_smk_files())
        self._cats["ui_panels"][1].config(text=f"{ui_n} files")
        self._cats["equip_icons"][1].config(text=f"{eq_n} icons")
        self._cats["talisman_icons"][1].config(text=f"{tal_n} icons")
        self._cats["model_textures"][1].config(text=f"{i3d_n} models")
        self._cats["sprites"][1].config(text=f"{i2d_n} sprites")
        self._cats["cinematix"][1].config(text=f"{smk_n} SMK")

    # ── Results management ────────────────────────────────────────────────────

    def _add_result(self, r: Dict):
        """Append a result card to the scrollable list. Called on main thread."""
        from PIL import ImageTk, Image as PILImage
        idx    = len(self._results)
        r["idx"] = idx
        self._results.append(r)

        row_bg = BG_PANEL if idx % 2 == 0 else BG_CARD
        row = tk.Frame(self._results_inner, bg=row_bg, pady=1, cursor="hand2")
        row.pack(fill="x")
        r["row_frame"] = row

        # Before thumbnail
        if r.get("before_pil"):
            ph_b = ImageTk.PhotoImage(r["before_pil"])
            self._result_phs.append(ph_b)
            tk.Label(row, image=ph_b, bg=row_bg, bd=0).pack(side="left", padx=(4, 0))
        else:
            tk.Label(row, text="  —  ", bg=row_bg, fg=FG_DIM,
                     font=("Segoe UI", 8), width=7).pack(side="left")

        tk.Label(row, text="→", bg=row_bg, fg=FG_DIM,
                 font=("Segoe UI", 9)).pack(side="left", padx=2)

        # After thumbnail
        if r.get("after_pil"):
            ph_a = ImageTk.PhotoImage(r["after_pil"])
            self._result_phs.append(ph_a)
            tk.Label(row, image=ph_a, bg=row_bg, bd=0).pack(side="left", padx=(0, 6))
        else:
            tk.Label(row, text="  —  ", bg=row_bg, fg=FG_DIM,
                     font=("Segoe UI", 8), width=7).pack(side="left")

        # Name + category
        tk.Label(row, text=f"[{r['cat']}]  {r['name']}", bg=row_bg, fg=FG_TEXT,
                 font=("Consolas", 8), anchor="w").pack(side="left", padx=4,
                                                         fill="x", expand=True)

        # Dimensions
        src_w, src_h = r.get("src_size", (0, 0))
        out_w, out_h = r.get("out_size", (0, 0))
        dims = f"{src_w}×{src_h}→{out_w}×{out_h}" if out_w else f"{src_w}×{src_h}"
        tk.Label(row, text=dims, bg=row_bg, fg=FG_DIM,
                 font=("Segoe UI", 8), width=16).pack(side="left", padx=2)

        # Status badge
        sl = tk.Label(row, text=r["status"].upper(), fg=self._STATUS_COLORS.get(r["status"], FG_DIM),
                      bg=row_bg, font=("Segoe UI", 8, "bold"), width=7)
        sl.pack(side="left", padx=4)
        r["status_lbl"] = sl

        # Action buttons
        tk.Button(row, text="Flag", bg=row_bg, fg="#f59e0b", relief="flat",
                  font=("Segoe UI", 8), padx=3,
                  command=lambda i=idx: self._flag_result(i)).pack(side="right", padx=2)
        tk.Button(row, text="Redo", bg=row_bg, fg=ACCENT2, relief="flat",
                  font=("Segoe UI", 8), padx=3,
                  command=lambda i=idx: self._redo_result(i)).pack(side="right", padx=2)

        # Click row → compare panel
        row.bind("<Button-1>", lambda e, i=idx: self._select_result(i))

        self._res_count_lbl.config(text=f"{len(self._results)} items")
        self._res_canvas.yview_moveto(1.0)

    def _select_result(self, idx: int):
        """Load result into the compare panel and sync redo params."""
        from PIL import Image as PILImage
        if idx >= len(self._results):
            return
        r = self._results[idx]
        self._sel_idx = idx

        # Highlight selected row (deselect others)
        for i, res in enumerate(self._results):
            bg = ACCENT2 if i == idx else (BG_PANEL if i % 2 == 0 else BG_CARD)
            rf = res.get("row_frame")
            if rf:
                try:
                    rf.config(bg=bg)
                    for w in rf.winfo_children():
                        w.config(bg=bg)
                except Exception:
                    pass

        self._cmp_name_lbl.config(text=f"{r['cat']} / {r['name']}")
        p = r.get("params", {})
        self._redo_strength_var.set(str(p.get("strength", "0.65")))
        self._redo_scale_var.set(str(p.get("scale", 4)))
        self._flag_btn.config(text="Unflag" if r["status"] == "flagged" else "Flag")

        # Load full-size images for compare (re-decode source, load output from disk)
        before_img = None
        try:
            fn = r.get("decode_fn")
            if fn:
                before_img = fn()
        except Exception:
            pass

        after_img = None
        try:
            op = r.get("out_path")
            if op and op.exists():
                after_img = PILImage.open(str(op))
        except Exception:
            pass

        self.after(10, lambda: self._draw_compare(self._cmp_before, before_img))
        self.after(10, lambda: self._draw_compare(self._cmp_after,  after_img))

    def _draw_compare(self, canvas: tk.Canvas, img):
        """Fit img into canvas, preserving aspect ratio. Up to 8x magnification."""
        from PIL import ImageTk, Image as PILImage
        canvas.delete("all")
        if img is None:
            canvas.create_text(max(canvas.winfo_width() // 2, 60), 40,
                               text="No image", fill=FG_DIM, font=("Segoe UI", 9))
            return
        cw = canvas.winfo_width()  or 300
        ch = canvas.winfo_height() or 200
        scale = min(cw / img.width, ch / img.height, 8.0)
        nw = max(1, int(img.width  * scale))
        nh = max(1, int(img.height * scale))
        display = img.resize((nw, nh), PILImage.NEAREST if scale > 1 else PILImage.LANCZOS)
        ph = ImageTk.PhotoImage(display)
        self._result_phs.append(ph)
        canvas.create_image(cw // 2, ch // 2, image=ph, anchor="center")

    def _flag_result(self, idx: int):
        r = self._results[idx]
        new_s = "ok" if r["status"] == "flagged" else "flagged"
        r["status"] = new_s
        r["status_lbl"].config(text=new_s.upper(), fg=self._STATUS_COLORS[new_s])
        if self._sel_idx == idx:
            self._flag_btn.config(text="Unflag" if new_s == "flagged" else "Flag")

    def _toggle_flag(self):
        if self._sel_idx is not None:
            self._flag_result(self._sel_idx)

    def _open_selected(self):
        if self._sel_idx is not None:
            p = self._results[self._sel_idx].get("out_path")
            if p and p.exists():
                os.startfile(str(p))

    def _clear_results(self):
        for w in self._results_inner.winfo_children():
            w.destroy()
        self._results.clear()
        self._result_phs.clear()
        self._sel_idx = None
        self._res_count_lbl.config(text="0 items")
        self._cmp_name_lbl.config(text="Select a result above")
        self._cmp_before.delete("all")
        self._cmp_after.delete("all")

    def _rebuild_card(self, idx: int):
        """Destroy and re-add a result card in-place after a redo."""
        r = self._results[idx]
        rf = r.get("row_frame")
        if rf:
            rf.destroy()
        # Temporarily remove from list so _add_result appends at end
        saved = self._results.pop(idx)
        # Re-insert at same slot
        self._results.insert(idx, saved)
        # Rebuild: destroy inner and recreate all cards
        for w in self._results_inner.winfo_children():
            w.destroy()
        all_results = list(self._results)
        self._results.clear()
        self._result_phs.clear()
        for res in all_results:
            self._add_result(res)

    # ── Single-file test ─────────────────────────────────────────────────────

    def _find_first_file(self, cat: str):
        """Return (cat, decode_fn, out_path) for first decodable asset, or None."""
        out_root = self.cfg.renders_dir / "upscaled"

        if cat == "ui_panels" and self.cfg.resources.exists():
            for dat in sorted(self.cfg.resources.glob("*.dat")):
                try:
                    raw = dat.read_bytes()
                    if len(raw) >= 20 and raw[:4] == b"CGSR":
                        return (cat,
                                lambda p=dat: _decode_dat_frame(p, 0),
                                out_root / cat / f"{dat.stem}_f0.png")
                except Exception:
                    pass

        elif cat == "equip_icons":
            eq_dir = self.cfg.thumbnails / "Equip"
            if eq_dir.exists():
                for tn in sorted(eq_dir.glob("*.tn")):
                    return (cat,
                            lambda p=tn: self._tn_to_image(p),
                            out_root / cat / f"{tn.stem}.png")

        elif cat == "talisman_icons":
            mag_dir = self.cfg.thumbnails / "Magic"
            if mag_dir.exists():
                for tn in sorted(mag_dir.glob("*.tn")):
                    return (cat,
                            lambda p=tn: self._tn_to_image(p),
                            out_root / cat / f"{tn.stem}.png")

        elif cat == "model_textures" and self.cfg.imagery_assets.exists():
            from decoders.i3d import decode_i3d_textures
            for i3d in sorted(self.cfg.imagery_assets.rglob("*.i3d")):
                try:
                    textures = decode_i3d_textures(i3d)
                    for ti, tex in enumerate(textures):
                        if tex is not None:
                            return (cat,
                                    lambda p=i3d, n=ti: self._decode_i3d_texture_n(p, n),
                                    out_root / cat / f"{i3d.stem}_t{ti}.png")
                except Exception:
                    pass

        elif cat == "sprites" and self.cfg.imagery_assets.exists():
            for i2d in sorted(self.cfg.imagery_assets.rglob("*.i2d")):
                return (cat,
                        lambda p=i2d: self._decode_sprite_safe(p),
                        out_root / cat / f"{i2d.stem}.png")

        elif cat == "cinematix":
            smks = self._find_smk_files()
            if smks:
                return (cat, None, smks[0])   # SMK handled separately in _test_single

        return None

    def _test_single(self, cat: str):
        """Upscale the first available file in *cat* and show it in the results list."""
        if self._running:
            self._status.set("Wait for current batch to finish")
            return

        job = self._find_first_file(cat)
        if job is None:
            self._status.set(f"No {cat} files found — check game directory")
            return

        cat, decode_fn, path = job
        scale    = int(self._scale_var.get())
        strength = float(self._strength_var.get())
        prompt   = self._get_prompt()
        neg      = self._get_neg()

        self._stop    = False
        self._running = True
        self._start_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")
        self._prog["value"] = 0
        self._prog_lbl.config(text=f"Testing {cat}…")

        def _worker(self=self, cat=cat, path=path, scale=scale, strength=strength, prompt=prompt, neg=neg, decode_fn=decode_fn):
            try:
                self.after(0, self._log_line,
                           f"[TEST {cat}]  {Path(path).name if cat == 'cinematix' else Path(path).name}")

                if cat == "cinematix":
                    ff = self._ffmpeg_path_var.get().strip()
                    if not ff:
                        self.after(0, self._log_line, "  Cinematix test skipped — FFmpeg not set")
                        return
                    out_root = self.cfg.renders_dir / "upscaled"
                    result = self._process_smk(path, scale, strength, prompt, neg, out_root)
                    if result:
                        self.after(0, self._add_result, result)
                    self.after(0, self._log_line, "  Cinematix test done")
                    return

                img = decode_fn()
                if img is None:
                    self.after(0, self._log_line, "  decode returned None — asset may be empty")
                    return

                self.after(0, self._log_line,
                           f"  source {img.width}×{img.height}  mode={img.mode}")

                out_path = Path(path)
                out_path.parent.mkdir(parents=True, exist_ok=True)

                up = self._upscale_with_ncnn(img, scale)
                up.save(str(out_path), format="PNG")

                self.after(0, self._log_line,
                           f"  → {up.width}×{up.height}  saved: {out_path.name}")
                self.after(0, self._add_result, {
                    "name":      out_path.stem,
                    "cat":       cat,
                    "decode_fn": decode_fn,
                    "out_path":  out_path,
                    "src_size":  (img.width, img.height),
                    "out_size":  (up.width,  up.height),
                    "before_pil": self._make_thumb(img),
                    "after_pil":  self._make_thumb(up),
                    "status":    "ok",
                    "params":    {"strength": strength, "scale": scale, "prompt": prompt},
                })
            except Exception as exc:
                import traceback
                self.after(0, self._log_line, f"  FAILED: {exc}")
                self.after(0, self._log_line, traceback.format_exc()[-600:])
            finally:
                self.after(0, self._on_done)

        threading.Thread(target=_worker, daemon=True).start()

    # ── Batch pipeline ────────────────────────────────────────────────────────

    def _start_upscale(self):
        if self._running:
            return
        selected = [k for k, (v, _) in self._cats.items() if v.get()]
        if not selected:
            self._status.set("Select at least one category")
            return
        self._stop    = False
        self._running = True
        self._start_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")
        self._prog["value"] = 0
        scale    = int(self._scale_var.get())
        strength = float(self._strength_var.get())
        prompt   = self._get_prompt()
        neg      = self._get_neg()
        threading.Thread(target=self._pipeline_worker,
                         args=(selected, scale, strength, prompt, neg), daemon=True).start()

    def _stop_upscale(self):
        self._stop = True
        self._status.set("Stopping after current asset…")

    def _pipeline_worker(self, selected: List[str], scale: int,
                          strength: float, prompt: str, neg: str):
        try:
            self._run_pipeline(selected, scale, strength, prompt, neg)
        except Exception as exc:
            self.after(0, self._log_line, f"FATAL: {exc}")
        finally:
            self.after(0, self._on_done)

    def _on_done(self):
        self._running = False
        self._start_btn.config(state="normal")
        self._stop_btn.config(state="disabled")
        self._prog["value"] = 100
        self._prog_lbl.config(text="Done")
        self._status.set("Upscale complete.")
        if self._redo_chain:
            self._redo_chain = False
            self._process_redo_queue()

    # ── Core worker ──────────────────────────────────────────────────────────

    def _snap_nim_size(self, px: int) -> int:
        """Snap px to the nearest allowed NIM dimension."""
        return min(self.NIM_VALID_SIZES, key=lambda s: abs(s - px))

    def _nim_generate(self, model: str, prompt: str, width: int, height: int,
                      seed: int = -1):
        """POST to NVIDIA NIM genai endpoint; return PIL RGBA image.

        NIM FLUX only accepts: prompt, width, height, seed.
        Width/height must each be in NIM_VALID_SIZES.
        Raises RuntimeError with the full API error body on failure.
        """
        import base64, io, requests as req
        from PIL import Image as PILImage

        api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "NVIDIA_API_KEY not set — add it to .env"
            )
        url     = f"{self.NIM_BASE_URL}/{model}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }
        payload = {
            "prompt": prompt,
            "width":  self._snap_nim_size(width),
            "height": self._snap_nim_size(height),
        }
        if seed >= 0:
            payload["seed"] = seed
        r = req.post(url, headers=headers, json=payload, timeout=180)
        if not r.ok:
            raise RuntimeError(
                f"NIM {r.status_code}: {r.text[:400]}"
            )
        b64 = r.json()["artifacts"][0]["base64"]
        return PILImage.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA")

    def _upscale_with_ncnn(self, img, scale: int):
        """
        Upscale a PIL image with Real-ESRGAN-ncnn-vulkan (Vulkan — works on Intel UHD).
        Falls back to PIL LANCZOS if the binary is not installed.
        """
        import subprocess, tempfile
        from PIL import Image as PILImage

        ncnn_exe = self._detect_ncnn()
        if not ncnn_exe:
            # Soft fallback — better than failing; user sees clean LANCZOS until ncnn installed
            w, h = img.width * scale, img.height * scale
            return img.resize((w, h), PILImage.LANCZOS)

        ncnn_model = self._ncnn_model_var.get()
        with tempfile.TemporaryDirectory(prefix="revengine_up_") as tmp:
            src = Path(tmp) / "src.png"
            out = Path(tmp) / "out.png"
            img.convert("RGBA").save(str(src))
            r = subprocess.run(
                [ncnn_exe,
                 "-i", str(src),
                 "-o", str(out),
                 "-n", ncnn_model,
                 "-s", str(scale),
                 "-f", "png",
                 "-g", "0"],
                capture_output=True, text=True, timeout=120,
            )
            if r.returncode != 0:
                raise RuntimeError(f"ncnn: {r.stderr[-300:]}")
            return PILImage.open(str(out)).convert("RGBA")

    def _enhance_with_flux(self, img, strength: float, prompt: str,
                            neg_prompt: str, scale: int):
        """
        Enhance one PIL Image via NVIDIA NIM FLUX.1-schnell (text-to-image).

        Tiny sprites (≤ _SMALL_PX) bypass FLUX → NEAREST resize.
        All others: snap target dims to nearest NIM-valid size.
        """
        from PIL import Image as PILImage

        if img.width <= self._SMALL_PX or img.height <= self._SMALL_PX:
            return img.resize((img.width * scale, img.height * scale), PILImage.NEAREST)

        tw = self._snap_nim_size(img.width  * scale)
        th = self._snap_nim_size(img.height * scale)

        return self._nim_generate(
            model  = self.NIM_MODEL,
            prompt = prompt,
            width  = tw,
            height = th,
        )

    def _generate_texture_flux(self, img, asset_stem: str,
                                user_prompt: str, neg_prompt: str):
        """
        Generate a 1024×1024 PBR texture via FLUX.1-dev text-to-image.

        Source textures are 64–256px RGB565 with no recoverable detail.
        Character name is derived from asset_stem ("locke_t0" → "locke").
        """
        clean = re.sub(r"[_\-]t\d+$", "", asset_stem)
        clean = clean.replace("_", " ").replace("-", " ")
        tex_prompt = (
            f"{self.DEFAULT_TEX_PROMPT}, character: {clean}. "
            f"{user_prompt}"
        )
        return self._nim_generate(
            model  = self.NIM_MODEL_T2I,
            prompt = tex_prompt,
            width  = self.NIM_TEX_SIZE,
            height = self.NIM_TEX_SIZE,
        )

    def _scale_pil_fast(self, img, scale: int):
        """Fast PIL resize for video frames (no API call)."""
        from PIL import Image as PILImage
        if img.width <= self._SMALL_PX or img.height <= self._SMALL_PX:
            return img.resize((img.width * scale, img.height * scale), PILImage.NEAREST)
        return img.resize((img.width * scale, img.height * scale), PILImage.LANCZOS)

    def _get_prompt(self) -> str:
        return self._prompt_txt.get("1.0", "end-1c").strip() or self.DEFAULT_PROMPT

    def _get_neg(self) -> str:
        return self._neg_txt.get("1.0", "end-1c").strip() or self.DEFAULT_NEG

    def _make_thumb(self, img):
        """Return a _THUMB_PX square thumbnail PIL Image."""
        from PIL import Image as PILImage
        t = self._THUMB_PX
        resample = PILImage.NEAREST if img.width <= t else PILImage.LANCZOS
        return img.resize((t, t), resample)

    def _run_pipeline(self, selected: List[str], scale: int,
                       strength: float, prompt: str, neg: str):
        from PIL import Image as PILImage

        ncnn_exe = self._detect_ncnn()
        self.after(0, self._log_line,
                   f"Real-ESRGAN-ncnn  model={self._ncnn_model_var.get()}  "
                   f"scale={scale}×  "
                   f"({'binary found' if ncnn_exe else 'LANCZOS fallback — install ncnn for ESRGAN'})")

        # Build job list: (cat, decode_fn, out_path)
        jobs = []
        out_root = self.cfg.renders_dir / "upscaled"

        if "ui_panels" in selected and self.cfg.resources.exists():
            out_dir = out_root / "ui_panels"
            for dat in sorted(self.cfg.resources.glob("*.dat")):
                try:
                    raw = dat.read_bytes()
                    if len(raw) < 20 or raw[:4] != b"CGSR":
                        continue
                    count = raw[4]
                    for fi in range(max(1, count)):
                        jobs.append(("ui_panels",
                                     lambda p=dat, f=fi: _decode_dat_frame(p, f),
                                     out_dir / f"{dat.stem}_f{fi}.png"))
                except Exception:
                    pass

        if "equip_icons" in selected:
            out_dir = out_root / "equip_icons"
            eq_dir  = self.cfg.thumbnails / "Equip"
            if eq_dir.exists():
                for tn in sorted(eq_dir.glob("*.tn")):
                    jobs.append(("equip_icons",
                                 lambda p=tn: self._tn_to_image(p),
                                 out_dir / f"{tn.stem}.png"))

        if "talisman_icons" in selected:
            out_dir  = out_root / "talisman_icons"
            mag_dir  = self.cfg.thumbnails / "Magic"
            if mag_dir.exists():
                for tn in sorted(mag_dir.glob("*.tn")):
                    jobs.append(("talisman_icons",
                                 lambda p=tn: self._tn_to_image(p),
                                 out_dir / f"{tn.stem}.png"))

        if "model_textures" in selected and self.cfg.imagery_assets.exists():
            out_dir = out_root / "model_textures"
            for i3d in sorted(self.cfg.imagery_assets.rglob("*.i3d")):
                try:
                    from decoders.i3d import decode_i3d_textures
                    textures = decode_i3d_textures(i3d)
                    for ti, tex in enumerate(textures):
                        if tex is not None:
                            jobs.append(("model_textures",
                                         lambda p=i3d, n=ti: self._decode_i3d_texture_n(p, n),
                                         out_dir / f"{i3d.stem}_t{ti}.png"))
                except Exception:
                    pass

        if "sprites" in selected and self.cfg.imagery_assets.exists():
            out_dir = out_root / "sprites"
            for i2d_p in sorted(self.cfg.imagery_assets.rglob("*.i2d")):
                jobs.append(("sprites",
                             lambda p=i2d_p: self._decode_sprite_safe(p),
                             out_dir / f"{i2d_p.stem}.png"))

        # Cinematix is handled separately (video pipeline, not per-frame jobs)
        cine_smks: List[Path] = []
        if "cinematix" in selected:
            ff = self._ffmpeg_path_var.get().strip()
            if not ff:
                self.after(0, self._log_line,
                           "Cinematix skipped — FFmpeg path not set. "
                           "Install FFmpeg and set path in left panel.")
            else:
                cine_smks = self._find_smk_files()
                if not cine_smks:
                    self.after(0, self._log_line,
                               "Cinematix: no SMK files found in game dirs")

        if not jobs and not cine_smks:
            self.after(0, self._log_line, "No assets found for selected categories")
            return

        total = len(jobs)
        self.after(0, self._log_line, f"{total} jobs queued")
        self.after(0, self._set_progress, 0, total, "Starting")

        ok = skip = 0
        for i, (cat, decode_fn, out_path) in enumerate(jobs, 1):
            if self._stop:
                self.after(0, self._log_line, "Stopped by user")
                break
            try:
                img = decode_fn()
                if img is None:
                    skip += 1
                    continue

                out_path.parent.mkdir(parents=True, exist_ok=True)

                up = self._upscale_with_ncnn(img, scale)

                up.save(str(out_path), format="PNG")
                ok += 1

                before_th = self._make_thumb(img)
                after_th  = self._make_thumb(up)
                self.after(0, self._add_result, {
                    "name":       out_path.stem,
                    "cat":        cat,
                    "decode_fn":  decode_fn,
                    "out_path":   out_path,
                    "src_size":   (img.width, img.height),
                    "out_size":   (up.width,  up.height),
                    "before_pil": before_th,
                    "after_pil":  after_th,
                    "status":     "ok",
                    "params":     {"strength": strength, "scale": scale, "prompt": prompt},
                })

            except Exception as exc:
                skip += 1
                self.after(0, self._log_line, f"SKIP {out_path.stem}: {exc}")
                self.after(0, self._add_result, {
                    "name":      out_path.stem,
                    "cat":       cat,
                    "decode_fn": decode_fn,
                    "out_path":  out_path,
                    "src_size":  (0, 0),
                    "status":    "failed",
                    "params":    {"strength": strength, "scale": scale, "prompt": prompt},
                })

            if i % 10 == 0 or i == total:
                self.after(0, self._set_progress, i, total, cat)

        # ── Cinematix video pipeline ──────────────────────────────────────────
        cine_ok = cine_skip = 0
        for smk in cine_smks:
            if self._stop:
                break
            try:
                result = self._process_smk(smk, scale, strength, prompt, neg, out_root)
                if result:
                    self.after(0, self._add_result, result)
                    cine_ok += 1
                else:
                    cine_skip += 1
            except Exception as exc:
                cine_skip += 1
                self.after(0, self._log_line, f"SMK failed [{smk.name}]: {exc}")

        total_ok   = ok   + cine_ok
        total_skip = skip + cine_skip
        self.after(0, self._log_line,
                   f"Done: {total_ok} ok  {total_skip} skipped  → {out_root}")
        self._status.set(f"Upscale: {total_ok} done, {total_skip} skipped")

    # ── Redo ─────────────────────────────────────────────────────────────────

    def _redo_result(self, idx: int):
        if self._running:
            self._status.set("Wait for current batch to finish")
            return
        r = self._results[idx]
        if not r.get("decode_fn"):
            return
        strength = float(self._redo_strength_var.get())
        scale    = int(self._redo_scale_var.get())
        prompt   = self._get_prompt()
        neg      = self._get_neg()

        self._running = True
        self._start_btn.config(state="disabled")
        self._prog["value"] = 0
        self._prog_lbl.config(text=f"Redoing {r['name']}…")

        def _worker():
            try:
                img = r["decode_fn"]()
                if img is None:
                    self.after(0, self._log_line, f"Redo: decode returned None for {r['name']}")
                    return
                up = self._upscale_with_ncnn(img, scale)
                r["out_path"].parent.mkdir(parents=True, exist_ok=True)
                up.save(str(r["out_path"]), format="PNG")

                r["src_size"]   = (img.width, img.height)
                r["out_size"]   = (up.width,  up.height)
                r["before_pil"] = self._make_thumb(img)
                r["after_pil"]  = self._make_thumb(up)
                r["status"]     = "ok"
                r["params"]     = {"strength": strength, "scale": scale, "prompt": prompt}

                self.after(0, self._rebuild_card, idx)
                if self._sel_idx == idx:
                    self.after(50, self._select_result, idx)
            except Exception as exc:
                self.after(0, self._log_line, f"Redo failed: {exc}")
            finally:
                self.after(0, self._on_done)

        threading.Thread(target=_worker, daemon=True).start()

    def _redo_selected(self):
        if self._sel_idx is not None:
            self._redo_result(self._sel_idx)

    def _redo_flagged(self):
        self._redo_queue = [i for i, r in enumerate(self._results) if r["status"] == "flagged"]
        if not self._redo_queue:
            self._status.set("No flagged items")
            return
        self._process_redo_queue()

    def _process_redo_queue(self):
        if not self._redo_queue:
            self._status.set("Redo flagged: complete")
            return
        idx = self._redo_queue.pop(0)
        self._redo_chain = True
        self._redo_result(idx)

    # ── FFmpeg helpers ────────────────────────────────────────────────────────

    def _detect_ffmpeg(self) -> Optional[str]:
        """Return path to ffmpeg executable or None if not found."""
        import shutil
        # 1. Project-local tools/ffmpeg.exe (installed via "Install to project")
        local = self.cfg.engine_dir / "tools" / "ffmpeg.exe"
        if local.exists():
            return str(local)
        # 2. System PATH
        p = shutil.which("ffmpeg")
        if p:
            return p
        # 3. Common Windows install locations
        for c in [
            Path("ffmpeg"),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WinGet/Links/ffmpeg.exe",
        ]:
            if c.exists():
                return str(c)
        return None

    def _update_ffmpeg_status(self):
        ff = self._ffmpeg_path_var.get().strip() if hasattr(self, "_ffmpeg_path_var") else self._ffmpeg_path
        found = self._probe_ffmpeg(ff)
        if found:
            self._ffmpeg_status_lbl.config(text="✓ found", fg=ACCENT3)
            if hasattr(self, "_install_btn"):
                self._install_btn.config(state="disabled", bg=BG_CARD, fg=FG_DIM)
        else:
            self._ffmpeg_status_lbl.config(text="✗ not found", fg=RED)
            if hasattr(self, "_install_btn"):
                self._install_btn.config(state="normal", bg=ACCENT2, fg="#000")

    @staticmethod
    def _probe_ffmpeg(ff: str) -> bool:
        """Return True if ff is a runnable ffmpeg binary."""
        import subprocess
        if not ff:
            return False
        try:
            r = subprocess.run([ff, "-version"], capture_output=True, timeout=5)
            return r.returncode == 0
        except Exception:
            return False

    def _on_ffmpeg_path_changed(self):
        self._ffmpeg_path = self._ffmpeg_path_var.get().strip()
        self._update_ffmpeg_status()

    def _browse_ffmpeg(self):
        p = filedialog.askopenfilename(
            title="Select ffmpeg.exe",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")])
        if p:
            self._ffmpeg_path_var.set(p)

    def _install_ffmpeg(self):
        """Download FFmpeg win64 binary to self.cfg.engine_dir/tools/ffmpeg.exe in a thread."""
        if self._running:
            self._status.set("Wait for current operation to finish")
            return
        self._install_btn.config(state="disabled", text="Installing…")
        threading.Thread(target=self._install_ffmpeg_worker, daemon=True).start()

    def _install_ffmpeg_worker(self):
        import zipfile, io
        FFMPEG_URL = (
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
            "ffmpeg-master-latest-win64-lgpl.zip"
        )
        dest = self.cfg.engine_dir / "tools" / "ffmpeg.exe"
        try:
            import requests as req
            self.after(0, self._log_line, "Downloading FFmpeg (~25 MB)…")

            resp = req.get(FFMPEG_URL, stream=True, timeout=60)
            resp.raise_for_status()

            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            chunks = []
            for chunk in resp.iter_content(chunk_size=1 << 16):  # 64 KB
                chunks.append(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    self.after(0, lambda p=pct: setattr(self._prog, "value", p)
                               if hasattr(self, "_prog") else None)

            self.after(0, self._log_line, "Extracting ffmpeg.exe…")
            data = b"".join(chunks)
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                # Find the ffmpeg.exe entry (inside bin/ subdirectory)
                entry = next((n for n in zf.namelist()
                              if n.endswith("/bin/ffmpeg.exe") or n == "ffmpeg.exe"), None)
                if not entry:
                    raise FileNotFoundError(
                        f"ffmpeg.exe not found in zip. Entries: {zf.namelist()[:10]}")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(entry))

            self.after(0, self._log_line, f"FFmpeg installed → {dest}")
            self.after(0, self._ffmpeg_path_var.set, str(dest))
            self.after(0, self._update_ffmpeg_status)
            self.after(0, self._refresh_counts)

        except Exception as exc:
            self.after(0, self._log_line, f"FFmpeg install failed: {exc}")
        finally:
            self.after(0, self._install_btn.config,
                       {"state": "normal", "text": "Install to project"})

    # ── Real-ESRGAN-ncnn-vulkan helpers ───────────────────────────────────────

    def _detect_ncnn(self) -> Optional[str]:
        """Return path to realesrgan-ncnn-vulkan.exe or None."""
        import shutil
        local = self.cfg.engine_dir / "tools" / "realesrgan-ncnn" / "realesrgan-ncnn-vulkan.exe"
        if local.exists():
            return str(local)
        ncnn_dir = self.cfg.engine_dir / "tools" / "realesrgan-ncnn"
        candidates = list(ncnn_dir.glob("*ncnn-vulkan*.exe"))
        if candidates:
            return str(candidates[0])
        p = shutil.which("realesrgan-ncnn-vulkan")
        return p

    def _update_ncnn_status(self):
        exe = self._detect_ncnn()
        if exe:
            self._ncnn_status_lbl.config(text="✓ found", fg=ACCENT3)
            self._ncnn_install_btn.config(state="disabled", bg=BG_CARD, fg=FG_DIM)
        else:
            self._ncnn_status_lbl.config(text="✗ not found", fg=RED)
            self._ncnn_install_btn.config(state="normal", bg=ACCENT2, fg="#000")

    def _install_ncnn(self):
        if self._running:
            self._status.set("Wait for current operation to finish")
            return
        self._ncnn_install_btn.config(state="disabled", text="Installing…")
        threading.Thread(target=self._install_ncnn_worker, daemon=True).start()

    def _install_ncnn_worker(self):
        import zipfile, io
        # Portable ncnn-vulkan binary — works on any NVIDIA/AMD/Intel GPU via Vulkan
        NCNN_URL = (
            "https://github.com/xinntao/Real-ESRGAN/releases/download/"
            "v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip"
        )
        dest_dir = self.cfg.engine_dir / "tools" / "realesrgan-ncnn"
        try:
            import requests as req
            self.after(0, self._log_line, "Downloading Real-ESRGAN-ncnn-vulkan (~30 MB)…")
            resp = req.get(NCNN_URL, stream=True, timeout=120)
            resp.raise_for_status()

            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            chunks = []
            for chunk in resp.iter_content(chunk_size=1 << 16):
                chunks.append(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    self.after(0, lambda p=pct: setattr(self._prog, "value", p)
                               if hasattr(self, "_prog") else None)

            self.after(0, self._log_line, "Extracting…")
            data = b"".join(chunks)
            dest_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = zf.namelist()
                # Detect common top-level directory prefix (handles both flat and nested zips)
                top = ""
                if names:
                    candidate = names[0].split("/")[0] + "/"
                    if all(n.startswith(candidate) or n == candidate.rstrip("/") for n in names):
                        top = candidate
                for member in names:
                    rel = member[len(top):]
                    if not rel:
                        continue
                    dest = dest_dir / rel
                    if member.endswith("/"):
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(zf.read(member))

            exe = dest_dir / "realesrgan-ncnn-vulkan.exe"
            self.after(0, self._log_line,
                       f"Real-ESRGAN-ncnn installed → {exe}")
            self.after(0, self._update_ncnn_status)

        except Exception as exc:
            self.after(0, self._log_line, f"ncnn install failed: {exc}")
        finally:
            self.after(0, self._ncnn_install_btn.config,
                       {"state": "normal", "text": "Install to project"})

    def _find_smk_files(self) -> List[Path]:
        """Collect all .smk/.SMK files from known game directories."""
        search_dirs = [
            self.cfg.game_dir / "Disk2",
            self.cfg.game_dir,
            self.cfg.extract_dir,
        ]
        seen: set = set()
        results: List[Path] = []
        for d in search_dirs:
            if not d.exists():
                continue
            for ext in ("*.smk", "*.SMK"):
                for f in d.rglob(ext):
                    if f not in seen:
                        seen.add(f)
                        results.append(f)
        return sorted(results)

    def _process_smk(self, smk: Path, scale: int, strength: float,
                      prompt: str, neg: str, out_root: Path) -> Optional[Dict]:
        """
        SMK → upscaled MP4.

        Fast path  (ncnn installed):
          FFmpeg extracts PNG frames → realesrgan-ncnn-vulkan batch-upscales
          the entire frames directory on the GPU in one call → FFmpeg re-encodes.

        Fallback (ncnn not installed):
          Single FFmpeg pass with pp=de/fd deblock + lanczos scale filter.
        """
        import subprocess, tempfile
        from PIL import Image as PILImage

        ff = self._ffmpeg_path_var.get().strip()
        if not ff:
            raise RuntimeError("FFmpeg path not set")

        ncnn_exe   = self._detect_ncnn()
        ncnn_model = self._ncnn_model_var.get()
        out_dir    = out_root / "cinematix"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_mp4    = out_dir / f"{smk.stem}_{scale}x.mp4"

        first_before = first_after = None

        if ncnn_exe:
            # ── Fast GPU path ─────────────────────────────────────────────────
            with tempfile.TemporaryDirectory(prefix="revengine_cine_") as tmp:
                frames_raw = Path(tmp) / "raw"
                frames_up  = Path(tmp) / "up"
                frames_raw.mkdir()
                frames_up.mkdir()

                # 1. Decode SMK → PNG frames (15 fps)
                self.after(0, self._log_line,
                           f"  [{smk.name}] Extracting frames…")
                r1 = subprocess.run(
                    [ff, "-y", "-i", str(smk), "-vf", "fps=15",
                     str(frames_raw / "%04d.png")],
                    capture_output=True, text=True, timeout=120)
                if r1.returncode != 0:
                    raise RuntimeError(f"FFmpeg extract: {r1.stderr[-300:]}")

                frame_paths = sorted(frames_raw.glob("*.png"))
                if not frame_paths:
                    raise RuntimeError("No frames extracted from SMK")

                first_before = PILImage.open(str(frame_paths[0])).copy()

                # 2. Batch upscale entire directory on GPU
                self.after(0, self._log_line,
                           f"  [{smk.name}] {len(frame_paths)} frames → "
                           f"Real-ESRGAN-ncnn ×{scale} ({ncnn_model})…")
                r2 = subprocess.run(
                    [ncnn_exe,
                     "-i", str(frames_raw),
                     "-o", str(frames_up),
                     "-n", ncnn_model,
                     "-s", str(scale),
                     "-f", "png",
                     "-g", "0"],       # GPU 0 (Vulkan — picks NVIDIA automatically)
                    capture_output=True, text=True, timeout=600)
                if r2.returncode != 0:
                    raise RuntimeError(f"ncnn: {r2.stderr[-300:]}")

                up_paths = sorted(frames_up.glob("*.png"))
                if up_paths:
                    first_after = PILImage.open(str(up_paths[0])).copy()

                # 3. Re-encode upscaled frames → H.264
                self.after(0, self._log_line,
                           f"  [{smk.name}] Encoding MP4…")
                r3 = subprocess.run(
                    [ff, "-y", "-framerate", "15",
                     "-i", str(frames_up / "%04d.png"),
                     "-c:v", "libx264", "-crf", "16", "-preset", "slow",
                     "-pix_fmt", "yuv420p", str(out_mp4)],
                    capture_output=True, text=True, timeout=300)
                if r3.returncode != 0:
                    raise RuntimeError(f"FFmpeg encode: {r3.stderr[-300:]}")

            method_tag = f"esrgan-ncnn:{ncnn_model}"

        else:
            # ── FLUX NIM frame-by-frame (cloud, no local GPU needed) ──────────
            flux_step = int(self._cine_step_var.get())
            self.after(0, self._log_line,
                       f"  [{smk.name}] No ncnn — FLUX NIM ×{scale} "
                       f"every {flux_step} frame(s)…")

            with tempfile.TemporaryDirectory(prefix="revengine_cine_") as tmp:
                frames_raw = Path(tmp) / "raw"
                frames_up  = Path(tmp) / "up"
                frames_raw.mkdir()
                frames_up.mkdir()

                # 1. Decode SMK → PNG frames
                r1 = subprocess.run(
                    [ff, "-y", "-i", str(smk), "-vf", "fps=15",
                     str(frames_raw / "%04d.png")],
                    capture_output=True, text=True, timeout=120)
                if r1.returncode != 0:
                    raise RuntimeError(f"FFmpeg extract: {r1.stderr[-300:]}")

                frame_paths = sorted(frames_raw.glob("*.png"))
                if not frame_paths:
                    raise RuntimeError("No frames extracted from SMK")

                n_frames = len(frame_paths)
                self.after(0, self._log_line,
                           f"  [{smk.name}] {n_frames} frames — "
                           f"FLUX on {(n_frames + flux_step - 1) // flux_step} "
                           f"key frames, LANCZOS fill…")

                # 2. Enhance key frames with FLUX, fill gaps with LANCZOS
                for fi, fp in enumerate(frame_paths):
                    if self._stop:
                        raise RuntimeError("Stopped by user")
                    img = PILImage.open(str(fp))
                    up = self._scale_pil_fast(img, scale)

                    out_fp = frames_up / fp.name
                    up.convert("RGB").save(str(out_fp), format="PNG")

                    if fi == 0:
                        first_before = img.copy()
                        first_after  = up.copy()

                    if fi % 20 == 0 or fi == n_frames - 1:
                        self.after(0, self._log_line,
                                   f"    [{smk.name}] {fi + 1}/{n_frames}…")

                # 3. Re-encode → MP4
                self.after(0, self._log_line, f"  [{smk.name}] Encoding MP4…")
                r3 = subprocess.run(
                    [ff, "-y", "-framerate", "15",
                     "-i", str(frames_up / "%04d.png"),
                     "-c:v", "libx264", "-crf", "16", "-preset", "slow",
                     "-pix_fmt", "yuv420p", str(out_mp4)],
                    capture_output=True, text=True, timeout=300)
                if r3.returncode != 0:
                    raise RuntimeError(f"FFmpeg encode: {r3.stderr[-300:]}")

            method_tag = f"flux-nim:step={flux_step}"

        self.after(0, self._log_line,
                   f"  [{smk.name}] Done [{method_tag}] → {out_mp4.name}")

        t = self._THUMB_PX
        before_th = first_before.resize((t, t), PILImage.LANCZOS) if first_before else None
        after_th  = first_after.resize((t, t),  PILImage.LANCZOS) if first_after  else None

        def _redo_decode_fn(smk_path=smk):
            import subprocess, tempfile
            ff2 = self._ffmpeg_path_var.get().strip()
            with tempfile.TemporaryDirectory() as td:
                out_f = Path(td) / "frame.png"
                subprocess.run([ff2, "-y", "-i", str(smk_path),
                                "-vframes", "1", str(out_f)],
                               capture_output=True)
                if out_f.exists():
                    return PILImage.open(str(out_f)).copy()
            return None

        src_w = first_before.width  if first_before else 0
        src_h = first_before.height if first_before else 0
        out_w = first_after.width   if first_after  else 0
        out_h = first_after.height  if first_after  else 0

        return {
            "name":       smk.stem,
            "cat":        "cinematix",
            "decode_fn":  _redo_decode_fn,
            "out_path":   out_mp4,
            "src_size":   (src_w, src_h),
            "out_size":   (out_w, out_h),
            "before_pil": before_th,
            "after_pil":  after_th,
            "status":     "ok",
            "params":     {"strength": strength, "scale": scale, "prompt": prompt},
            "_smk_path":  smk,
        }

    # ── Asset decode helpers ─────────────────────────────────────────────────

    @staticmethod
    def _tn_to_image(tn_path: Path):
        from PIL import Image as PILImage
        raw = tn_path.read_bytes()
        rgba = _decode_tn_pixels(raw)
        if rgba is None:
            return None
        return PILImage.frombytes("RGBA", (16, 16), rgba)

    @staticmethod
    def _decode_i3d_texture_n(i3d_path: Path, texture_idx: int):
        from decoders.i3d import decode_i3d_textures
        try:
            textures = decode_i3d_textures(i3d_path)
            return textures[texture_idx] if texture_idx < len(textures) else None
        except Exception:
            return None

    @staticmethod
    def _decode_sprite_safe(i2d_path: Path):
        try:
            from decoders.i2d import decode_i2d
            return decode_i2d(i2d_path)
        except Exception:
            return None


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════
