from PIL import Image, ImageTk
import re
import struct
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from ui.theme import THEME, FONTS
from core.constants import *
from ui.widgets import *
from core.parsers import *
class ModelsTab(tk.Frame):
    def __init__(self, parent, config, status: StatusBar):
        self.cfg = config
        super().__init__(parent, bg=THEME["bg_mid"])
        self._status = status
        self._models  : List[Dict] = []
        self._build_ui()
        self.after(600, self._load_all)

    def _build_ui(self):
        bar = tk.Frame(self, bg=THEME["bg_dark"], pady=4)
        bar.pack(fill="x")
        self._flt_var = tk.StringVar()
        tk.Label(bar, text="Filter:", bg=THEME["bg_dark"], fg=THEME["fg_dim"],
                 font=FONTS["body"]).pack(side="left", padx=(10,4))
        tk.Entry(bar, textvariable=self._flt_var,
                  bg=THEME["bg_panel"], fg=THEME["fg_text"], insertbackground=FG_TEXT,
                  font=FONTS["body"], relief="flat", width=24
                  ).pack(side="left", padx=4)
        self._flt_var.trace_add("write", self._filter)
        self._batch_btn = tk.Button(bar, text="Batch Export OBJ", bg=ACCENT3,
                                     fg="#000", relief="flat",
                                     font=("Segoe UI", 9, "bold"), padx=8,
                                     command=self._batch_export_obj)
        self._batch_btn.pack(side="right", padx=4)
        self._count_lbl = tk.Label(bar, text="", bg=THEME["bg_dark"], fg=THEME["fg_dim"],
                                    font=FONTS["small"])
        self._count_lbl.pack(side="right", padx=12)

        pane = tk.PanedWindow(self, orient="horizontal", bg=THEME["bg_dark"],
                               sashwidth=6, sashrelief="flat")
        pane.pack(fill="both", expand=True)

        tv_f = tk.Frame(pane, bg=THEME["bg_mid"])
        pane.add(tv_f, minsize=460)

        cols = ("name","folder","size","anims","verts")
        self._tv = ttk.Treeview(tv_f, columns=cols, show="headings",
                                  selectmode="browse")
        self._tv.heading("name",   text="Model File",   anchor="w")
        self._tv.heading("folder", text="Folder",       anchor="w")
        self._tv.heading("size",   text="Size (KB)",    anchor="center")
        self._tv.heading("anims",  text="Anim States",  anchor="center")
        self._tv.heading("verts",  text="Est. Verts",   anchor="center")
        self._tv.column("name",   width=200, stretch=True)
        self._tv.column("folder", width=100, stretch=False)
        self._tv.column("size",   width=70,  stretch=False, anchor="center")
        self._tv.column("anims",  width=80,  stretch=False, anchor="center")
        self._tv.column("verts",  width=80,  stretch=False, anchor="center")
        sb = ttk.Scrollbar(tv_f, orient="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._tv.pack(fill="both", expand=True)
        self._tv.bind("<<TreeviewSelect>>", self._on_select)

        # Detail panel (right): metadata top + 3D viewer bottom + OBJ export
        det = tk.Frame(pane, bg=THEME["bg_panel"])
        pane.add(det, minsize=300)

        # Header row
        hdr = tk.Frame(det, bg=THEME["bg_panel"], padx=10, pady=6)
        hdr.pack(fill="x")
        tk.Label(hdr, text="MODEL DETAILS", bg=THEME["bg_panel"], fg=THEME["accent"],
                 font=FONTS["header"]).pack(side="left")
        tk.Button(hdr, text="Export glTF", bg=ACCENT2, fg="#000000",
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=8,
                  command=self._export_gltf).pack(side="right", padx=(0, 4))
        tk.Button(hdr, text="Export OBJ", bg=ACCENT3, fg="#000000",
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=8,
                  command=self._export_obj).pack(side="right")

        ttk.Separator(det).pack(fill="x")

        # ── Animation controls bar ────────────────────────────────────────
        anim_bar = tk.Frame(det, bg=THEME["bg_dark"], padx=8, pady=4)
        anim_bar.pack(fill="x")

        tk.Label(anim_bar, text="State:", bg=THEME["bg_dark"], fg=THEME["fg_dim"],
                 font=FONTS["small"]).pack(side="left")

        self._state_var = tk.StringVar(value="[0] Bind pose")
        self._state_cb  = ttk.Combobox(anim_bar, textvariable=self._state_var,
                                        state="readonly", width=22,
                                        font=FONTS["small"])
        self._state_cb.pack(side="left", padx=(4, 8))
        self._state_cb.bind("<<ComboboxSelected>>", self._on_state_select)

        # Frame scrubber (shown only for multi-frame states)
        self._frame_var = tk.IntVar(value=0)
        self._frame_lbl = tk.Label(anim_bar, text="Frame:", bg=THEME["bg_dark"], fg=THEME["fg_dim"],
                                    font=FONTS["small"])
        self._frame_scale = tk.Scale(anim_bar, variable=self._frame_var,
                                      from_=0, to=0, orient="horizontal",
                                      bg=THEME["bg_dark"], fg=THEME["fg_text"], highlightthickness=0,
                                      troughcolor=BG_PANEL, activebackground=ACCENT,
                                      length=80, showvalue=True,
                                      command=self._on_frame_change)

        # Play / Stop buttons
        self._play_btn = tk.Button(anim_bar, text="▶ Play", bg=THEME["bg_mid"], fg=THEME["fg_text"],
                                    relief="flat", font=FONTS["small"], padx=6,
                                    command=self._anim_play)
        self._stop_btn = tk.Button(anim_bar, text="■ Stop", bg=THEME["bg_mid"], fg=THEME["fg_text"],
                                    relief="flat", font=FONTS["small"], padx=6,
                                    command=self._anim_stop)
        self._play_btn.pack(side="left", padx=(0, 2))
        self._stop_btn.pack(side="left", padx=(0, 8))

        self._fps_var = tk.IntVar(value=8)
        tk.Label(anim_bar, text="FPS:", bg=THEME["bg_dark"], fg=THEME["fg_dim"],
                 font=FONTS["small"]).pack(side="left")
        tk.Spinbox(anim_bar, textvariable=self._fps_var, from_=1, to=30,
                   width=3, bg=THEME["bg_panel"], fg=THEME["fg_text"], relief="flat",
                   font=FONTS["small"]).pack(side="left", padx=(2, 0))

        self._anim_job  = None   # after() job id
        self._anim_frame = 0     # current playback frame

        ttk.Separator(det).pack(fill="x")

        # Vertical split: metadata text (top) + 3D viewer (bottom)
        vpane = tk.PanedWindow(det, orient="vertical", bg=THEME["bg_dark"],
                               sashwidth=5, sashrelief="flat")
        vpane.pack(fill="both", expand=True)

        meta_frame = tk.Frame(vpane, bg=THEME["bg_panel"], padx=8, pady=4)
        vpane.add(meta_frame, minsize=100)
        self._det_text = tk.Text(meta_frame, bg=THEME["bg_panel"], fg=THEME["fg_text"],
                                  font=("Consolas", 9), relief="flat",
                                  state="disabled", wrap="word", height=7)
        self._det_text.pack(fill="both", expand=True)
        self._det_text.tag_configure("h",   foreground=ACCENT,  font=("Segoe UI", 10, "bold"))
        self._det_text.tag_configure("kv",  foreground=ACCENT2, font=FONTS["small"])
        self._det_text.tag_configure("list",foreground=ACCENT3, font=("Consolas", 8))

        self._viewer = ModelViewer3D(vpane)
        vpane.add(self._viewer, minsize=200)

        self._current_geom    = None   # holds last decoded I3DGeometry
        self._current_texture = None   # holds last loaded PIL texture (for export)
        self._current_path    = None   # path of currently selected model

    def _load_all(self):
        self._status.set("Scanning i3d model files...")
        models = []
        seen   = set()
        for f in self.cfg.imagery_assets.rglob("*.i3d"):
            key = f.name.lower()
            if key in seen:
                continue
            seen.add(key)
            anim_count = parse_i3d_anim_count(f)
            # Quick vertex count: Layout A = sec[1].count, Layout B = sec[1].rel
            verts = 0
            try:
                raw = f.read_bytes()
                if len(raw) >= 28 and raw[:4] == b'CGSR':
                    hdrsize    = struct.unpack_from('<I', raw, 16)[0]
                    geom_start = 20 + hdrsize
                    if geom_start + 24 <= len(raw):
                        sec1_rel = struct.unpack_from('<I', raw, geom_start + 8)[0]     # Layout B vc
                        sec1_cnt = struct.unpack_from('<I', raw, geom_start + 8 + 4)[0] # Layout A vc
                        sec2_cnt = struct.unpack_from('<I', raw, geom_start + 16 + 4)[0]
                        verts = sec1_cnt if sec2_cnt > 0 else sec1_rel
            except Exception:
                pass
            models.append({
                "name":   f.name,
                "folder": f.parent.name,
                "path":   f,
                "size_kb": f.stat().st_size // 1024,
                "anims":  anim_count,
                "verts":  verts,
            })

        self._models = sorted(models, key=lambda x: x["anims"], reverse=True)
        self._populate(self._models)
        self._count_lbl.config(text=f"{len(self._models)} models")
        self._status.set(f"3D Models: {len(self._models)} i3d files indexed")

    def _populate(self, data: List[Dict]):
        self._tv.delete(*self._tv.get_children())
        for m in data:
            self._tv.insert("", "end",
                values=(m["name"], m["folder"],
                        m["size_kb"], m["anims"],
                        m["verts"] if m["verts"] else "?"))

    def _filter(self, *_):
        flt = self._flt_var.get().strip().lower()
        filtered = [m for m in self._models
                    if flt in m["name"].lower() or flt in m["folder"].lower()
                    ] if flt else self._models
        self._populate(filtered)
        self._count_lbl.config(text=f"{len(filtered)} / {len(self._models)}")

    def _on_select(self, _):
        sel = self._tv.selection()
        if not sel:
            return
        name = self._tv.item(sel[0], "values")[0]
        m = next((x for x in self._models if x["name"] == name), None)
        if not m:
            return

        self._anim_stop()
        self._current_path = m["path"]

        # Load animation state list via fast decoder
        from decoders.i3d import list_anim_states
        anim_states = list_anim_states(m["path"])

        # Populate state combobox
        state_entries = ["[0] Bind pose (T-pose)"]
        for s in anim_states:
            tag = "cycle" if s.anim_type == 0 else "pose"
            nf  = f" ×{s.nframes}f" if s.anim_type == 0 and s.nframes > 0 else ""
            state_entries.append(f"[{s.index + 1}] {s.name}  ({tag}{nf})")
        self._state_cb["values"] = state_entries
        self._state_cb.current(0)
        self._frame_var.set(0)
        self._frame_scale.config(to=0)
        self._frame_lbl.pack_forget()
        self._frame_scale.pack_forget()

        # Fill metadata panel
        txt = self._det_text
        txt.configure(state="normal")
        txt.delete("1.0", "end")
        txt.insert("end", f"{m['name']}\n", "h")

        def row(k, v, txt=txt):
            txt.insert("end", f"  {k:<20}", "kv")
            txt.insert("end", f"{v}\n")

        row("Folder",      m["folder"])
        row("File size",   f"{m['size_kb']:,} KB  ({m['path'].stat().st_size:,} bytes)")
        row("Anim states", str(len(anim_states)) if anim_states else "0")

        if anim_states:
            txt.insert("end", f"\nAnimation States ({len(anim_states)}):\n", "kv")
            for s in anim_states:
                tag = "cycle" if s.anim_type == 0 else "pose"
                nf  = f" ×{s.nframes}f" if s.anim_type == 0 and s.nframes > 0 else ""
                txt.insert("end", f"  [{s.index:>2}] {s.name}  ({tag}{nf})\n", "list")

        txt.configure(state="disabled")

        # Async geometry decode → 3D viewer
        self._decode_model(m["path"])

    def _on_state_select(self, _=None):
        """User selected a new animation state from the combobox."""
        if self._current_geom is None:
            return
        self._anim_stop()
        idx = self._state_cb.current()   # 0 = bind pose, 1..N = state 0..N-1
        self._apply_state(idx)

    def _apply_state(self, combo_idx: int, frame: int = 0):
        """Apply combo_idx (0=bind-pose, 1..N = anim state 0..N-1) at given frame."""
        geom = self._current_geom
        if geom is None:
            return
        from decoders.i3d import load_state
        if combo_idx == 0:
            ok = load_state(geom, 0, 0)   # bind pose
        else:
            state_idx = combo_idx - 1     # index into anim_states list
            ok = load_state(geom, state_idx, frame)

        if ok:
            # Update frame scrubber visibility
            if combo_idx > 0:
                st = geom.anim_states[combo_idx - 1]
                max_f = max(0, (st.nframes or 1) - 1)
            else:
                max_f = 0

            if max_f > 0:
                self._frame_lbl.pack(side="left", padx=(8, 2))
                self._frame_scale.config(to=max_f)
                self._frame_scale.pack(side="left")
            else:
                self._frame_lbl.pack_forget()
                self._frame_scale.pack_forget()

            has_uvs = len(geom.uvs) == len(geom.vertices)
            has_nrm = len(geom.normals) == len(geom.vertices)
            extras  = (["+normals"] if has_nrm else []) + (["+UVs"] if has_uvs else [])
            state_label = "bind" if combo_idx == 0 else geom.anim_states[combo_idx - 1].name
            info = (f"{len(geom.vertices):,} verts  ·  {len(geom.faces):,} faces"
                    f"  ·  state: {state_label}"
                    + (f"  ·  frame {frame}" if max_f > 0 else "")
                    + ("  ·  " + " ".join(extras) if extras else ""))
            # Preserve textures and face_tex_indices across state changes
            stored_tex = self._viewer._textures if self._viewer._textures else None
            stored_fti = (geom.face_tex_indices
                          if geom.face_tex_indices else None)
            self._viewer.load(geom.vertices, geom.faces, info,
                              normals=geom.normals if has_nrm else None,
                              uvs=geom.uvs if has_uvs else None,
                              textures=stored_tex,
                              face_tex_indices=stored_fti)

    def _on_frame_change(self, val=None):
        """Frame scrubber moved."""
        self._anim_stop()
        frame = self._frame_var.get()
        combo_idx = self._state_cb.current()
        self._apply_state(combo_idx, frame)

    def _anim_play(self):
        """Start animation playback for multi-frame states."""
        if self._current_geom is None:
            return
        combo_idx = self._state_cb.current()
        if combo_idx == 0:
            return
        geom = self._current_geom
        st = geom.anim_states[combo_idx - 1]
        nf = max(1, st.nframes or 1)
        if nf <= 1:
            return
        self._anim_stop()
        self._anim_frame = self._frame_var.get()
        self._play_btn.config(relief="sunken")
        self._anim_tick(combo_idx, nf)

    def _anim_tick(self, combo_idx: int, nf: int):
        fps = max(1, self._fps_var.get())
        self._apply_state(combo_idx, self._anim_frame)
        self._frame_var.set(self._anim_frame)
        self._anim_frame = (self._anim_frame + 1) % nf
        self._anim_job = self.after(int(1000 / fps), self._anim_tick, combo_idx, nf)

    def _anim_stop(self):
        if self._anim_job is not None:
            self.after_cancel(self._anim_job)
            self._anim_job = None
        self._play_btn.config(relief="flat")



    def _decode_model(self, path: Path):
        """Decode geometry + texture for the given .i3d file and update viewer."""
        self._current_geom    = None
        self._current_texture = None
        self._viewer.load([], [], "Decoding…")

        def _worker(p=path, self=self):
            log.info("Loading model: %s", p.name)
            try:
                from decoders.i3d import decode_i3d_geometry
                geom = decode_i3d_geometry(p)
            except Exception as exc:
                log.error("Geometry decode failed for %s: %s", p.name, exc)
                geom = None

            # Load all embedded textures (or sidecar)
            textures = ModelViewer3D.load_textures_for(p)
            tex = textures[0] if textures else None

            self._current_geom    = geom
            self._current_texture = tex
            if geom:
                log.info("  %s: %d verts, %d faces, %d states, %d tex, rig=%s",
                         p.name, len(geom.vertices), len(geom.faces),
                         len(geom.anim_states), len(textures),
                         f"{geom.rig.num_bones} bones" if geom.rig else "none")
                has_uvs = len(geom.uvs) == len(geom.vertices)
                has_nrm = len(geom.normals) == len(geom.vertices)
                ntex = len(textures)
                tex_tag = f"  ·  +{ntex} tex" if ntex else ""
                extras  = (["+normals"] if has_nrm else []) + (["+UVs"] if has_uvs else [])
                extras_str = ("  ·  " + " ".join(extras)) if extras else ""
                n_states = len(geom.anim_states)
                info = (f"{len(geom.vertices):,} verts  ·  "
                        f"{len(geom.faces):,} faces  ·  "
                        f"{n_states} anim states{extras_str}{tex_tag}")
            else:
                info = "Geometry format not detected"

            def _update(self=self, geom=geom, info=info, textures=textures):
                self._viewer.load(
                    geom.vertices if geom else [],
                    geom.faces    if geom else [],
                    info,
                    normals          = geom.normals          if (geom and len(geom.normals)==len(geom.vertices)) else None,
                    uvs              = geom.uvs              if (geom and len(geom.uvs)    ==len(geom.vertices)) else None,
                    textures         = textures              if textures else None,
                    face_tex_indices = geom.face_tex_indices if geom else None,
                )
                if self._state_cb.current() != 0:
                    self._state_cb.current(0)
            self.after(0, _update)

        threading.Thread(target=_worker, daemon=True).start()



    def _export_obj(self):
        """Save current model as Wavefront OBJ (+ .mtl and texture .png if available)."""
        if self._current_geom is None:
            self._status.set("No geometry — select a model and wait for decode first")
            return
        geom = self._current_geom
        tex  = self._current_texture
        default_name = geom.path.stem + ".obj"
        out = filedialog.asksaveasfilename(
            title="Export OBJ",
            initialdir=str(Path.home() / "Desktop"),
            initialfile=default_name,
            defaultextension=".obj",
            filetypes=[("Wavefront OBJ", "*.obj"), ("All files", "*.*")],
        )
        if not out:
            return
        from decoders.i3d import export_obj
        if export_obj(geom, Path(out), texture=tex):
            tex_note = " + texture" if tex else ""
            self._status.set(f"OBJ saved: {Path(out).name}  "
                             f"({len(geom.vertices):,} verts, {len(geom.faces):,} faces{tex_note})")
        else:
            self._status.set("OBJ export failed")

    def _export_gltf(self):
        """Export current model as glTF 2.0 — skeleton + all animation clips + textures."""
        if self._current_geom is None:
            self._status.set("No geometry — select a model and wait for decode first")
            return
        geom = self._current_geom
        if geom.rig is None:
            self._status.set("No rig data — old-format model cannot be exported as glTF")
            return

        default_name = geom.path.stem + ".gltf"
        out = filedialog.asksaveasfilename(
            title="Export glTF 2.0 (rigged + animated)",
            initialdir=str(Path.home() / "Desktop"),
            initialfile=default_name,
            defaultextension=".gltf",
            filetypes=[("glTF 2.0", "*.gltf"), ("All files", "*.*")],
        )
        if not out:
            return

        textures = getattr(self._viewer, '_textures', [])
        out_path  = Path(out)
        self._status.set(f"Exporting {geom.path.stem}… (baking animations, may take a moment)")

        def _worker():
            log.info("glTF export start: %s -> %s", geom.path.name, out_path)
            try:
                from decoders.gltf_export import export_gltf
                ok = export_gltf(
                    geom, textures, out_path,
                    status_cb=lambda msg: (
                        log.info("  %s", msg),
                        self.after(0, lambda m=msg: self._status.set(m)),
                    ),
                )
                n_anim = len(geom.anim_states)
                nb     = geom.rig.num_bones
                if ok:
                    sz_kb = out_path.stat().st_size // 1024
                    log.info("glTF export done: %s (%d KB)", out_path.name, sz_kb)
                    msg = (f"glTF saved: {out_path.name}  "
                           f"({len(geom.vertices):,} verts · {nb} bones · {n_anim} anim states)")
                else:
                    log.warning("glTF export returned False")
                    msg = "glTF export failed"
            except Exception as e:
                log.exception("glTF export error for %s", geom.path.name)
                msg = f"glTF export error: {e}"
            self.after(0, lambda m=msg: self._status.set(m))

        threading.Thread(target=_worker, daemon=True).start()

    def _batch_export_obj(self):
        """Export all currently listed models as OBJ files."""
        models = self._models if self._models else []
        if not models:
            self._status.set("No models loaded")
            return
        dest = self.cfg.renders_dir / "Models_OBJ"
        dest.mkdir(parents=True, exist_ok=True)
        total = len(models)
        self._batch_btn.config(text="Stop batch…", bg=RED,
                               command=lambda: setattr(self, '_batch_stop', True))
        self._batch_stop = False

        def _worker(self=self, models=models, dest=dest, total=total):
            ok = skip = 0
            for i, m in enumerate(models, 1):
                if getattr(self, '_batch_stop', False):
                    break
                path = m.get("path")
                if not path or not path.is_file():
                    skip += 1; continue
                out = dest / f"{path.stem}.obj"
                try:
                    from decoders.i3d import decode_i3d_geometry, export_obj
                    geom = decode_i3d_geometry(path)
                    if geom and export_obj(geom, out):
                        ok += 1
                    else:
                        skip += 1
                except Exception:
                    skip += 1
                if i % 10 == 0 or i == total:
                    self.after(0, lambda n=i: self._status.set(
                        f"Batch OBJ: {n}/{total}…"))
            self.after(0, self._on_batch_done, ok, skip, dest)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_batch_done(self, ok: int, skip: int, dest: Path):
        self._batch_btn.config(text="Batch Export OBJ", bg=ACCENT3,
                               command=self._batch_export_obj)
        self._status.set(f"Batch OBJ: {ok} exported, {skip} skipped → {dest}")
