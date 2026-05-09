"""
RevEngine — Modernize 3D Tab
=============================
Tkinter tab that runs the full old-to-modern character pipeline:

  Step 1  Decode .i3d
  Step 2  Export base .gltf (correct local bone transforms)
  Step 3  Upscale texture  (realesrgan-ncnn-vulkan, GPU)
  Step 4  Generate normal map  (Sobel, Python)
  Step 5  Generate roughness map  (luminance, Python)
  Step 6  Blender headless: CC subdivide + shade smooth + AO bake + PBR wire
  Step 7  Done — output .glb with all maps

Reuses UpscaleTab's ncnn-vulkan binary detection pattern.
"""

from __future__ import annotations
import datetime
import logging
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import ttk, filedialog

log = logging.getLogger("RevEngine.Modernize")

# Colour palette — mirrors asset_studio.py constants
BG_DARK  = "#1a1a2e"
BG_MID   = "#16213e"
BG_PANEL = "#0f3460"
BG_CARD  = "#1a1a3e"
FG_TEXT  = "#e0e0e0"
FG_DIM   = "#a0a0b0"
FG_MUTED = "#606070"
ACCENT   = "#e94560"
ACCENT2  = "#00b4d8"
ACCENT3  = "#06d6a0"
RED      = "#ff4444"
BORDER   = "#2a2a4e"

# Locate the project root relative to this file
_HERE       = Path(__file__).resolve().parent
ENGINE_DIR  = _HERE
BLENDER_EXE = Path("C:/Program Files/Blender Foundation/Blender 5.1/blender.exe")
PIPELINE_PY = ENGINE_DIR / "tools" / "modernize_pipeline.py"
NCNN_EXE    = ENGINE_DIR / "tools" / "realesrgan-ncnn" / "realesrgan-ncnn-vulkan.exe"
OUT_DIR     = ENGINE_DIR / "test_renders_hd"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


def _detect_ncnn() -> Optional[str]:
    # Check canonical path first
    if NCNN_EXE.exists():
        return str(NCNN_EXE)
    # Glob for any *ncnn-vulkan*.exe in the tools directory (handles truncated zip extractions)
    ncnn_dir = ENGINE_DIR / "tools" / "realesrgan-ncnn"
    candidates = list(ncnn_dir.glob("*ncnn-vulkan*.exe"))
    if candidates:
        return str(candidates[0])
    # System PATH fallback
    found = shutil.which("realesrgan-ncnn-vulkan")
    return found


def _detect_blender() -> Optional[str]:
    if BLENDER_EXE.exists():
        return str(BLENDER_EXE)
    found = shutil.which("blender")
    return found


def _list_gpu_options() -> list[tuple[str, str]]:
    """
    Return list of (label, g_flag) pairs for the GPU selector.

    Detection strategy:
      1. wmic (Windows) — enumerates all GPU adapters with real names
      2. Fallback       — static GPU 0/1/2 labels if wmic unavailable

    ncnn-vulkan assigns GPU indices in the order Vulkan enumerates them,
    which generally matches the Windows adapter order. The default=auto
    option (-g auto) lets the binary choose the best GPU itself.
    """
    options = [("Auto — let ncnn pick best GPU", "auto")]

    # --- Windows WMI probe ---------------------------------------------------
    try:
        r = subprocess.run(
            ["wmic", "path", "win32_VideoController", "get", "name"],
            capture_output=True, text=True, timeout=6,
        )
        lines = [l.strip() for l in r.stdout.splitlines()
                 if l.strip() and l.strip().lower() != "name"]
        for idx, name in enumerate(lines):
            vendor = ""
            nl = name.lower()
            if "nvidia" in nl:
                vendor = "Nvidia"
            elif "amd" in nl or "radeon" in nl:
                vendor = "AMD"
            elif "intel" in nl:
                vendor = "Intel"
            label = f"GPU {idx} — {name}" + (f" ({vendor})" if vendor else "")
            options.append((label, str(idx)))
    except Exception:
        # wmic not available (non-Windows or permission issue) — static fallback
        options += [
            ("GPU 0 — Primary GPU (Nvidia/AMD/Intel via Vulkan)", "0"),
            ("GPU 1 — Secondary GPU", "1"),
        ]

    options.append(("CPU only  (slow — no GPU required)", "-1"))
    return options


# ---------------------------------------------------------------------------
# ModernizeTab
# ---------------------------------------------------------------------------

class ModernizeTab(tk.Frame):
    """
    Full 8-step model modernization tab with real-time progress + log.
    """

    STEP_LABELS = [
        "Decode .i3d",
        "Export base gltf",
        "Upscale texture (ncnn-vulkan)",
        "Generate normal map",
        "Generate roughness map",
        "Blender: subdivide + AO bake",
        "Done",
    ]

    def __init__(self, parent, status_bar):
        super().__init__(parent, bg=BG_DARK)
        self._status   = status_bar
        self._running  = False
        self._stop_evt = threading.Event()
        self._blender_proc: Optional[subprocess.Popen] = None
        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self):
        pane = tk.PanedWindow(self, orient="horizontal", bg=BG_DARK,
                              sashwidth=5, sashrelief="flat")
        pane.pack(fill="both", expand=True)

        # ── Left panel ───────────────────────────────────────────────────────
        left = tk.Frame(pane, bg=BG_PANEL, width=260)
        left.pack_propagate(False)
        pane.add(left, minsize=220)

        tk.Label(left, text="MODERNIZE 3D", bg=BG_PANEL, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
        tk.Label(left, text="Old-to-modern pipeline", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(anchor="w", padx=10, pady=(0, 6))

        tk.Frame(left, bg=BORDER, height=1).pack(fill="x", padx=8, pady=4)

        # Model path
        tk.Label(left, text="Model (.i3d)", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=10)
        model_row = tk.Frame(left, bg=BG_PANEL)
        model_row.pack(fill="x", padx=10, pady=(2, 4))
        self._model_var = tk.StringVar()
        tk.Entry(model_row, textvariable=self._model_var, bg=BG_CARD, fg=FG_TEXT,
                 font=("Consolas", 8), relief="flat",
                 insertbackground=FG_TEXT).pack(side="left", fill="x", expand=True)
        tk.Button(model_row, text="…", bg=BG_MID, fg=FG_TEXT, relief="flat",
                  font=("Segoe UI", 8), padx=4,
                  command=self._browse_model).pack(side="right", padx=(2, 0))

        # Output dir
        tk.Label(left, text="Output folder", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=10)
        out_row = tk.Frame(left, bg=BG_PANEL)
        out_row.pack(fill="x", padx=10, pady=(2, 4))
        self._out_var = tk.StringVar(value=str(OUT_DIR))
        tk.Entry(out_row, textvariable=self._out_var, bg=BG_CARD, fg=FG_TEXT,
                 font=("Consolas", 8), relief="flat",
                 insertbackground=FG_TEXT).pack(side="left", fill="x", expand=True)
        tk.Button(out_row, text="…", bg=BG_MID, fg=FG_TEXT, relief="flat",
                  font=("Segoe UI", 8), padx=4,
                  command=self._browse_out).pack(side="right", padx=(2, 0))

        tk.Frame(left, bg=BORDER, height=1).pack(fill="x", padx=8, pady=6)

        # ── Options ──────────────────────────────────────────────────────────
        tk.Label(left, text="Pipeline steps", bg=BG_PANEL, fg=ACCENT2,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=10, pady=(0, 4))

        # Subdivide
        self._do_subdiv = tk.BooleanVar(value=True)
        r1 = tk.Frame(left, bg=BG_PANEL)
        r1.pack(fill="x", padx=10, pady=1)
        tk.Checkbutton(r1, text="Subdivide (CC)", variable=self._do_subdiv,
                       bg=BG_PANEL, fg=FG_TEXT, selectcolor=BG_CARD,
                       activebackground=BG_PANEL, font=("Segoe UI", 8)).pack(side="left")
        tk.Label(r1, text="levels:", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(side="left", padx=(8, 2))
        self._levels_var = tk.IntVar(value=2)
        tk.Spinbox(r1, from_=1, to=4, width=3, textvariable=self._levels_var,
                   bg=BG_CARD, fg=FG_TEXT, relief="flat",
                   font=("Segoe UI", 8)).pack(side="left")

        # Upscale
        self._do_upscale = tk.BooleanVar(value=True)
        r2 = tk.Frame(left, bg=BG_PANEL)
        r2.pack(fill="x", padx=10, pady=1)
        tk.Checkbutton(r2, text="Upscale texture", variable=self._do_upscale,
                       bg=BG_PANEL, fg=FG_TEXT, selectcolor=BG_CARD,
                       activebackground=BG_PANEL, font=("Segoe UI", 8)).pack(side="left")
        tk.Label(r2, text="scale:", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(side="left", padx=(8, 2))
        self._scale_var = tk.StringVar(value="4")
        ttk.Combobox(r2, textvariable=self._scale_var, values=["2", "4"],
                     state="readonly", width=3,
                     font=("Segoe UI", 8)).pack(side="left")

        # GPU selector — ncnn-vulkan works on Nvidia/AMD/Intel via Vulkan + CPU fallback
        gpu_opts   = _list_gpu_options()
        gpu_labels = [label for label, _ in gpu_opts]
        self._gpu_flag_map = {label: flag for label, flag in gpu_opts}
        self._gpu_var = tk.StringVar(value=gpu_labels[0])
        rg = tk.Frame(left, bg=BG_PANEL)
        rg.pack(fill="x", padx=10, pady=(0, 3))
        tk.Label(rg, text="  GPU:", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(side="left")
        self._gpu_combo = ttk.Combobox(
            rg, textvariable=self._gpu_var,
            values=gpu_labels, state="readonly",
            width=28, font=("Segoe UI", 8),
        )
        self._gpu_combo.pack(side="left", padx=(4, 0))
        tk.Button(rg, text="↻", bg=BG_MID, fg=FG_DIM, relief="flat",
                  font=("Segoe UI", 8), padx=3,
                  command=self._refresh_gpus).pack(side="left", padx=(2, 0))

        # Normal map
        self._do_normal = tk.BooleanVar(value=True)
        r3 = tk.Frame(left, bg=BG_PANEL)
        r3.pack(fill="x", padx=10, pady=1)
        tk.Checkbutton(r3, text="Normal map (Sobel)", variable=self._do_normal,
                       bg=BG_PANEL, fg=FG_TEXT, selectcolor=BG_CARD,
                       activebackground=BG_PANEL, font=("Segoe UI", 8)).pack(side="left")
        tk.Label(r3, text="str:", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(side="left", padx=(6, 2))
        self._nmap_str = tk.DoubleVar(value=2.0)
        tk.Spinbox(r3, from_=0.5, to=5.0, increment=0.5, width=4,
                   textvariable=self._nmap_str, bg=BG_CARD, fg=FG_TEXT,
                   relief="flat", font=("Segoe UI", 8)).pack(side="left")

        # AO bake
        self._do_ao = tk.BooleanVar(value=True)
        r4 = tk.Frame(left, bg=BG_PANEL)
        r4.pack(fill="x", padx=10, pady=1)
        tk.Checkbutton(r4, text="Bake AO (Blender)", variable=self._do_ao,
                       bg=BG_PANEL, fg=FG_TEXT, selectcolor=BG_CARD,
                       activebackground=BG_PANEL, font=("Segoe UI", 8)).pack(side="left")
        tk.Label(r4, text="res:", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(side="left", padx=(8, 2))
        self._ao_res = tk.StringVar(value="512")
        ttk.Combobox(r4, textvariable=self._ao_res, values=["256", "512", "1024"],
                     state="readonly", width=5,
                     font=("Segoe UI", 8)).pack(side="left")

        tk.Frame(left, bg=BORDER, height=1).pack(fill="x", padx=8, pady=8)

        # ── Action buttons ────────────────────────────────────────────────────
        btn_row = tk.Frame(left, bg=BG_PANEL)
        btn_row.pack(fill="x", padx=10, pady=2)
        self._run_btn = tk.Button(btn_row, text="▶  Run", bg=ACCENT3, fg="#000",
                                   relief="flat", font=("Segoe UI", 9, "bold"),
                                   padx=10, command=self._on_run)
        self._run_btn.pack(side="left", padx=(0, 4))
        self._stop_btn = tk.Button(btn_row, text="⏹", bg=BG_MID, fg=FG_DIM,
                                    relief="flat", font=("Segoe UI", 9),
                                    padx=6, state="disabled", command=self._on_stop)
        self._stop_btn.pack(side="left", padx=(0, 4))
        tk.Button(btn_row, text="📁", bg=BG_MID, fg=FG_DIM, relief="flat",
                  font=("Segoe UI", 9), padx=6,
                  command=self._open_out).pack(side="left")

        # ncnn status
        ncnn_ok = bool(_detect_ncnn())
        blender_ok = bool(_detect_blender())
        status_txt = (
            ("✓ ncnn" if ncnn_ok else "✗ ncnn (LANCZOS fallback)") +
            "  " +
            ("✓ Blender" if blender_ok else "✗ Blender (subdivide/AO disabled)")
        )
        status_fg = ACCENT3 if (ncnn_ok and blender_ok) else ACCENT
        tk.Label(left, text=status_txt, bg=BG_PANEL, fg=status_fg,
                 font=("Segoe UI", 7), wraplength=230, justify="left"
                 ).pack(anchor="w", padx=10, pady=(6, 0))

        # ── Right panel ───────────────────────────────────────────────────────
        right = tk.Frame(pane, bg=BG_DARK)
        pane.add(right, minsize=400)

        # Progress strip
        prog_strip = tk.Frame(right, bg=BG_DARK, pady=4)
        prog_strip.pack(fill="x", padx=12, side="top")
        self._prog_lbl = tk.Label(prog_strip, text="Idle", bg=BG_DARK, fg=FG_DIM,
                                   font=("Segoe UI", 9))
        self._prog_lbl.pack(anchor="w")
        self._prog = ttk.Progressbar(prog_strip, orient="horizontal",
                                      mode="determinate", maximum=100)
        self._prog.pack(fill="x", pady=2)

        # Log panel
        log_hdr = tk.Frame(right, bg=BG_MID, pady=3)
        log_hdr.pack(fill="x", padx=0, side="top")
        tk.Label(log_hdr, text="Pipeline Log", bg=BG_MID, fg=ACCENT2,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=10)
        tk.Button(log_hdr, text="Clear", bg=BG_CARD, fg=FG_DIM,
                  relief="flat", font=("Segoe UI", 8), padx=6,
                  command=self._clear_log).pack(side="right", padx=6)

        log_body = tk.Frame(right, bg=BG_DARK)
        log_body.pack(fill="both", expand=True, padx=0)

        self._log = tk.Text(log_body, bg=BG_DARK, fg=FG_TEXT,
                            font=("Consolas", 8), wrap="none",
                            state="disabled", relief="flat",
                            borderwidth=0, pady=4)
        log_sb_y = ttk.Scrollbar(log_body, orient="vertical", command=self._log.yview)
        log_sb_x = ttk.Scrollbar(log_body, orient="horizontal", command=self._log.xview)
        self._log.configure(yscrollcommand=log_sb_y.set, xscrollcommand=log_sb_x.set)

        log_sb_y.pack(side="right", fill="y")
        log_sb_x.pack(side="bottom", fill="x")
        self._log.pack(fill="both", expand=True)

        # Tag colours
        self._log.tag_configure("ok",   foreground=ACCENT3)
        self._log.tag_configure("err",  foreground=RED)
        self._log.tag_configure("warn", foreground=ACCENT)
        self._log.tag_configure("info", foreground=FG_DIM)
        self._log.tag_configure("step", foreground=ACCENT2)

    # ── Browse / open helpers ─────────────────────────────────────────────────

    def _browse_model(self):
        chars_dir = ENGINE_DIR / "extracted" / "imagery" / "Imagery" / "Chars"
        init_dir  = str(chars_dir) if chars_dir.exists() else str(ENGINE_DIR / "extracted")
        p = filedialog.askopenfilename(
            title="Select .i3d model",
            initialdir=init_dir,
            filetypes=[("i3d files", "*.i3d"), ("All files", "*.*")],
        )
        if p:
            self._model_var.set(p)

    def _browse_out(self):
        p = filedialog.askdirectory(title="Select output folder")
        if p:
            self._out_var.set(p)

    def _open_out(self):
        out = Path(self._out_var.get())
        if out.exists():
            os.startfile(str(out))

    def _refresh_gpus(self):
        """Re-probe ncnn-vulkan GPU list and update the combobox."""
        gpu_opts   = _list_gpu_options()
        gpu_labels = [label for label, _ in gpu_opts]
        self._gpu_flag_map = {label: flag for label, flag in gpu_opts}
        self._gpu_combo["values"] = gpu_labels
        if self._gpu_var.get() not in gpu_labels:
            self._gpu_var.set(gpu_labels[0])
        self._log_line(f"GPUs detected: {', '.join(gpu_labels)}", "info")

    # ── Log helpers ───────────────────────────────────────────────────────────

    def _log_line(self, text: str, tag: str = "info"):
        def _do():
            self._log.config(state="normal")
            self._log.insert("end", f"{_ts()}  {text}\n", tag)
            self._log.see("end")
            self._log.config(state="disabled")
        self.after(0, _do)

    def _log_ok(self,   msg): self._log_line(f"[OK]   {msg}", "ok")
    def _log_err(self,  msg): self._log_line(f"[ERR]  {msg}", "err")
    def _log_warn(self, msg): self._log_line(f"[WARN] {msg}", "warn")
    def _log_step(self, msg): self._log_line(f"───  {msg}", "step")

    def _clear_log(self):
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")

    # ── Progress helper ───────────────────────────────────────────────────────

    def _set_progress(self, done: int, total: int, msg: str = ""):
        def _do():
            pct = int(done / total * 100) if total else 0
            self._prog["value"] = pct
            label = f"Step {done}/{total} — {msg}" if msg else f"{done}/{total}"
            self._prog_lbl.config(text=label)
        self.after(0, _do)

    # ── Button handlers ───────────────────────────────────────────────────────

    def _on_run(self):
        model = self._model_var.get().strip()
        if not model:
            self._log_err("No model selected")
            return
        if not Path(model).exists():
            self._log_err(f"File not found: {model}")
            return
        if self._running:
            return

        self._running = True
        self._stop_evt.clear()
        self._run_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        self._prog["value"] = 0
        self._prog_lbl.config(text="Starting…")

        threading.Thread(target=self._worker, args=(Path(model),), daemon=True).start()

    def _on_stop(self):
        self._stop_evt.set()
        if self._blender_proc:
            try:
                self._blender_proc.terminate()
            except Exception:
                pass
        self._log_warn("Stop requested — waiting for current step to finish…")

    def _on_done(self):
        self._running = False
        self._run_btn.config(state="normal")
        self._stop_btn.config(state="disabled")

    # ── Worker thread ─────────────────────────────────────────────────────────

    def _worker(self, i3d_path: Path):
        try:
            out_dir = Path(self._out_var.get())
            out_dir.mkdir(parents=True, exist_ok=True)

            stem = i3d_path.stem
            tmp  = Path(tempfile.mkdtemp(prefix="revengine_mod_"))

            # Count enabled steps
            steps = (
                1 +  # decode always
                1 +  # export gltf always
                (1 if self._do_upscale.get() else 0) +
                (1 if self._do_normal.get()  else 0) +
                (1 if self._do_normal.get()  else 0) +  # roughness goes with normal
                (1 if (self._do_subdiv.get() or self._do_ao.get()) else 0)
            )
            done = 0

            # ── Step 1: Decode ────────────────────────────────────────────────
            self._set_progress(done, steps, "Decode .i3d")
            self._log_step("Decode .i3d")
            from decoders.i3d import decode_i3d_geometry, decode_i3d_textures
            geom     = decode_i3d_geometry(i3d_path)
            textures = decode_i3d_textures(i3d_path)
            if geom is None:
                raise RuntimeError(f"Failed to decode {i3d_path.name}")
            nv = len(geom.vertices)
            nb = geom.rig.num_bones if geom.rig else 0
            na = len(geom.anim_states)
            done += 1
            self._log_ok(f"Decoded {i3d_path.name}  ({nv}v  {nb}b  {na} anims)")
            if self._stop_evt.is_set(): raise StopIteration

            # ── Step 2: Export base gltf ──────────────────────────────────────
            self._set_progress(done, steps, "Export base gltf")
            self._log_step("Export base gltf")
            from decoders.gltf_export import export_gltf
            gltf_path = tmp / f"{stem}.gltf"
            export_gltf(geom, textures, gltf_path)
            kb = gltf_path.stat().st_size // 1024
            done += 1
            self._log_ok(f"Base gltf: {kb} KB")
            if self._stop_evt.is_set(): raise StopIteration

            # ── Step 3: Upscale texture ───────────────────────────────────────
            upscaled_tex_path = ""
            if self._do_upscale.get() and textures:
                self._set_progress(done, steps, "Upscale texture (ncnn-vulkan)")
                self._log_step("Upscale texture")
                scale = int(self._scale_var.get())
                raw_tex_path = tmp / f"{stem}_diffuse_raw.png"
                textures[0].save(str(raw_tex_path))
                upscaled_tex_path = str(out_dir / f"{stem}_diffuse.png")
                self._upscale_texture(str(raw_tex_path), upscaled_tex_path, scale)
                done += 1
                self._log_ok(f"Upscaled {textures[0].size[0]}×{textures[0].size[1]} → "
                             f"{textures[0].size[0]*scale}×{textures[0].size[1]*scale}")
                if self._stop_evt.is_set(): raise StopIteration

            # Choose source for map generation (upscaled if available, else raw)
            from PIL import Image as _PIL
            src_for_maps = (_PIL.open(upscaled_tex_path).convert("RGBA")
                            if upscaled_tex_path and Path(upscaled_tex_path).exists()
                            else (textures[0] if textures else None))

            # ── Steps 4 + 5: Normal + Roughness maps ──────────────────────────
            normal_path = roughness_path = ""
            if self._do_normal.get() and src_for_maps:
                from decoders.pbr_maps import generate_normal_map, generate_roughness_map

                self._set_progress(done, steps, "Generate normal map")
                self._log_step("Generate normal map (Sobel)")
                strength   = float(self._nmap_str.get())
                normal_img = generate_normal_map(src_for_maps, strength=strength)
                normal_path = str(out_dir / f"{stem}_normal.png")
                normal_img.save(normal_path)
                done += 1
                self._log_ok(f"Normal map → {Path(normal_path).name}")

                self._set_progress(done, steps, "Generate roughness map")
                self._log_step("Generate roughness map")
                rough_img = generate_roughness_map(src_for_maps)
                roughness_path = str(out_dir / f"{stem}_roughness.png")
                rough_img.save(roughness_path)
                done += 1
                self._log_ok(f"Roughness map → {Path(roughness_path).name}")

                if self._stop_evt.is_set(): raise StopIteration

            # ── Step 6: Blender ───────────────────────────────────────────────
            out_glb = out_dir / f"{stem}_modern.glb"
            if self._do_subdiv.get() or self._do_ao.get():
                self._set_progress(done, steps, "Blender: subdivide + AO bake")
                self._log_step("Blender: CC subdivide + AO bake + PBR wire")
                self._run_blender(
                    gltf_path, out_glb,
                    levels        = self._levels_var.get(),
                    ao_size       = int(self._ao_res.get()) if self._do_ao.get() else 0,
                    upscaled_tex  = upscaled_tex_path,
                    normal_map    = normal_path,
                    roughness_map = roughness_path,
                )
                done += 1
                self._log_ok(f"Blender done → {out_glb.name}")
            else:
                # No Blender — just copy the base gltf as output
                import shutil as _sh
                out_glb_gltf = out_dir / f"{stem}_modern.gltf"
                _sh.copy(str(gltf_path), str(out_glb_gltf))
                out_glb = out_glb_gltf
                self._log_ok(f"Skipped Blender — output: {out_glb.name}")

            # ── Done ─────────────────────────────────────────────────────────
            self._set_progress(steps, steps, "Complete ✓")
            self._log_ok(f"Output: {out_glb}")
            self.after(0, self._status.set, f"Modernize complete: {out_glb.name}")

        except StopIteration:
            self._log_line("[ STOPPED ]", "warn")
            self.after(0, self._status.set, "Modernize stopped")
        except Exception as exc:
            log.exception("Modernize pipeline error")
            self._log_err(str(exc))
            self.after(0, self._status.set, "Modernize failed — see log")
        finally:
            self.after(0, self._on_done)

    # ── Texture upscale (ncnn-vulkan) ─────────────────────────────────────────

    def _upscale_texture(self, src_path: str, dst_path: str, scale: int):
        from PIL import Image as _PIL
        ncnn = _detect_ncnn()

        # Resolve GPU flag from combobox selection
        selected_label = self._gpu_var.get()
        g_flag = self._gpu_flag_map.get(selected_label, "0")
        is_cpu = g_flag == "-1"

        if not ncnn:
            self._log_warn("realesrgan-ncnn-vulkan not found — using LANCZOS fallback")
            img = _PIL.open(src_path)
            img.resize((img.width * scale, img.height * scale),
                       _PIL.LANCZOS).save(dst_path)
            return

        backend = "CPU" if is_cpu else f"GPU {g_flag} (Vulkan)"
        self._log_line(
            f"  ncnn-vulkan  model=realesrgan-x4plus-anime  "
            f"scale={scale}×  backend={backend}",
            "info",
        )
        if is_cpu:
            self._log_warn("CPU mode selected — upscaling will be slow (no GPU)")

        r = subprocess.run(
            [ncnn, "-i", src_path, "-o", dst_path,
             "-n", "realesrgan-x4plus-anime",
             "-s", str(scale), "-f", "png", "-g", g_flag],
            capture_output=True, text=True, timeout=600,  # longer timeout for CPU
        )
        if r.returncode != 0:
            raise RuntimeError(f"ncnn upscale failed: {r.stderr[-400:]}")

    # ── Blender subprocess ────────────────────────────────────────────────────

    def _run_blender(self, gltf_path: Path, out_glb: Path, levels: int,
                     ao_size: int, upscaled_tex: str,
                     normal_map: str, roughness_map: str):
        blender = _detect_blender()
        if not blender:
            raise RuntimeError("Blender not found — install Blender 4.0+ and add to PATH")

        cmd = [
            blender, "--background",
            "--python", str(PIPELINE_PY),
            "--",
            "--input",  str(gltf_path),
            "--output", str(out_glb),
            "--levels", str(levels),
            "--ao-size", str(ao_size),
        ]
        if upscaled_tex:
            cmd += ["--upscaled-tex", upscaled_tex]
        if normal_map:
            cmd += ["--normal-map", normal_map]
        if roughness_map:
            cmd += ["--roughness-map", roughness_map]
        if not self._do_ao.get():
            cmd.append("--no-ao")

        self._blender_proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        # Stream output line-by-line → log panel
        for line in iter(self._blender_proc.stdout.readline, ""):
            line = line.rstrip()
            if not line:
                continue
            if self._stop_evt.is_set():
                self._blender_proc.terminate()
                raise StopIteration
            # Categorise for colouring
            if line.startswith("[OK]"):
                self._log_ok(line[5:])
            elif "Error" in line or "error" in line:
                self._log_err(line)
            elif line.startswith("  [WARN]"):
                self._log_warn(line[8:])
            elif "INFO: Finished glTF" in line or "Blender quit" in line:
                self._log_line(line, "ok")
            else:
                self._log_line(line, "info")

        self._blender_proc.wait()
        rc = self._blender_proc.returncode
        self._blender_proc = None
        if rc not in (0, None) and not self._stop_evt.is_set():
            raise RuntimeError(f"Blender exited with code {rc}")
