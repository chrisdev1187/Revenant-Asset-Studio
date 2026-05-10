import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import math
import threading
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from core.constants import *
from ui.widgets import *
from core.parsers import *
class ModelViewer3D(tk.Frame):
    """
    Orthographic 3D viewer for i3d geometry.
    Supports flat-shaded and UV-textured rendering modes.
    Drag to rotate, scroll wheel to zoom.
    Falls back to a point cloud when no face data is available.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_DARK, **kwargs)
        self._verts            : List[tuple] = []
        self._faces            : List[tuple] = []
        self._normals          : List[tuple] = []
        self._uvs              : List[tuple] = []
        self._texture           = None   # first PIL.Image (kept for export compat)
        self._textures         : list  = []   # all PIL.Images, indexed by face_tex_indices
        self._face_tex_indices : List[int] = []
        self._photo_ref = None         # keep ImageTk.PhotoImage alive
        self._az     = 0.5
        self._el     = 0.1
        self._zoom   = 1.0
        self._drag   = None
        self._mode_var = tk.StringVar(value="textured")
        self._build()

    def _build(self):
        # ── Top toolbar ───────────────────────────────────────────────────────
        toolbar = tk.Frame(self, bg=BG_DARK)
        toolbar.pack(fill="x", side="top")

        tk.Label(toolbar, text="Render:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(side="left", padx=(6, 2))
        for label, val in [("Shaded", "shaded"), ("Textured", "textured")]:
            tk.Radiobutton(toolbar, text=label, variable=self._mode_var, value=val,
                           bg=BG_DARK, fg=FG_TEXT, selectcolor=BG_PANEL,
                           activebackground=BG_DARK, font=("Segoe UI", 8),
                           command=self._redraw).pack(side="left", padx=2)

        self._canvas = tk.Canvas(self, bg="#07070f", highlightthickness=0,
                                 cursor="fleur")
        self._canvas.pack(fill="both", expand=True)
        self._info_lbl = tk.Label(self, text="Select a model to view",
                                  bg=BG_DARK, fg=FG_MUTED,
                                  font=("Segoe UI", 8))
        self._info_lbl.pack(pady=(2, 4))

        self._canvas.bind("<ButtonPress-1>",  self._drag_start)
        self._canvas.bind("<B1-Motion>",       self._drag_move)
        self._canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, '_drag', None))
        self._canvas.bind("<MouseWheel>",      self._on_wheel)
        self._canvas.bind("<Configure>",       lambda e: self._redraw())

    def load(self, verts: list, faces: list, info: str = "",
             normals: list = None, uvs: list = None, texture=None,
             textures: list = None, face_tex_indices: list = None):
        self._verts   = verts
        self._faces   = faces
        self._normals = normals or []
        self._uvs     = uvs or []
        if textures is not None:
            self._textures = textures
            self._texture  = textures[0] if textures else None
        elif texture is not None:
            self._texture  = texture
            self._textures = [texture]
        self._face_tex_indices = face_tex_indices or []
        self._photo_ref = None
        self._az     = 0.5
        self._el     = 0.1
        self._zoom   = 1.0
        self._info_lbl.config(text=info or ("No geometry" if not verts else ""))
        self._redraw()

    def reload(self, verts: list, faces: list, info: str = "",
               normals: list = None, uvs: list = None):
        """Like load() but preserves current rotation/zoom and texture."""
        self._verts   = verts
        self._faces   = faces
        self._normals = normals or []
        self._uvs     = uvs or []
        self._photo_ref = None
        self._info_lbl.config(text=info or ("No geometry" if not verts else ""))
        self._redraw()

    @staticmethod
    def load_textures_for(i3d_path) -> list:
        """
        Load all textures for an .i3d file.
        Priority:
          1. Sidecar file (.bmp/.png/.tga) — returned as a single-element list
          2. All embedded DirectDraw textures from the .i3d itself
        Returns a list of PIL RGBA Images (may be empty).
        """
        try:
            from PIL import Image as _Image
            p = Path(i3d_path)
            for ext in (".bmp", ".BMP", ".png", ".PNG", ".tga", ".TGA"):
                candidate = p.with_suffix(ext)
                if candidate.exists():
                    return [_Image.open(candidate).convert("RGBA")]
        except Exception:
            pass
        try:
            from decoders.i3d import decode_i3d_textures
            return decode_i3d_textures(Path(i3d_path))
        except Exception:
            pass
        return []

    @staticmethod
    def load_texture_for(i3d_path) -> "Optional[object]":
        """Single-texture backward-compat wrapper around load_textures_for."""
        textures = ModelViewer3D.load_textures_for(i3d_path)
        return textures[0] if textures else None

    def _drag_start(self, e):
        self._drag = (e.x, e.y, self._az, self._el)

    def _drag_move(self, e):
        if not self._drag:
            return
        x0, y0, az0, el0 = self._drag
        self._az = az0 + (e.x - x0) * 0.008
        self._el = max(-1.5, min(1.5, el0 - (e.y - y0) * 0.008))
        self._redraw()

    def _on_wheel(self, e):
        self._zoom = max(0.05, min(20.0, self._zoom * (1.1 if e.delta > 0 else 0.9)))
        self._redraw()

    def _redraw(self):
        mode = self._mode_var.get()
        if mode == "textured" and self._textures and self._uvs:
            self._redraw_textured()
        else:
            self._redraw_shaded()

    def _redraw_shaded(self):
        c  = self._canvas
        cw = c.winfo_width()  or 300
        ch = c.winfo_height() or 240
        c.delete("all")

        if not self._verts:
            c.create_text(cw // 2, ch // 2, text="No geometry decoded",
                          fill=FG_MUTED, font=("Segoe UI", 10))
            return

        # ── Centre mesh on bounding-box centroid ───────────────────────────
        xs_r = [v[0] for v in self._verts]
        ys_r = [v[1] for v in self._verts]
        zs_r = [v[2] for v in self._verts]
        cx_r = (max(xs_r) + min(xs_r)) / 2
        cy_r = (max(ys_r) + min(ys_r)) / 2
        cz_r = (max(zs_r) + min(zs_r)) / 2

        # After bind-pose bone transforms, Z is world-up (feet≈z0, head≈z60).
        # Map Z→up (Y screen), X→horizontal, Y→depth so character stands upright.
        verts_c = [(x - cx_r, z - cz_r, y - cy_r) for x, y, z in self._verts]

        # ── Stable scale (rotation-invariant, from raw extents) ────────────
        mesh_span = max(max(xs_r)-min(xs_r), max(ys_r)-min(ys_r),
                        max(zs_r)-min(zs_r), 1e-6)
        scale = self._zoom * min(cw, ch) * 0.42 / mesh_span

        # ── Rotate ─────────────────────────────────────────────────────────
        az, el = self._az, self._el
        caz, saz = math.cos(az), math.sin(az)
        cel, sel = math.cos(el), math.sin(el)

        rot = []
        for x, y, z in verts_c:
            rx =  x * caz + z * saz
            ry =  y
            rz = -x * saz + z * caz
            rot.append((rx, ry * cel - rz * sel, ry * sel + rz * cel))

        # ── Rotate stored vertex normals (same transform, Z-up swap) ───────
        has_normals = len(self._normals) == len(self._verts)
        rot_nrm = []
        if has_normals:
            for nx, ny, nz in self._normals:
                # Match vertex swap: world (nx,ny,nz) → display (nx, nz, ny)
                nx2, ny2, nz2 = nx, nz, ny
                rnx =  nx2 * caz + nz2 * saz
                rny =  ny2
                rnz = -nx2 * saz + nz2 * caz
                rot_nrm.append((rnx, rny * cel - rnz * sel, rny * sel + rnz * cel))

        # ── Screen projection ──────────────────────────────────────────────
        cx2 = cw // 2;  cy2 = ch // 2
        pts = [(cx2 + v[0] * scale, cy2 - v[1] * scale, v[2]) for v in rot]

        # ── Light ──────────────────────────────────────────────────────────
        lx, ly, lz = 0.57, 0.74, 0.37   # pre-normalised

        # ── Build face list ────────────────────────────────────────────────
        if self._faces:
            face_data = []
            for face in self._faces:
                a, b, fi = face
                if a >= len(pts) or b >= len(pts) or fi >= len(pts):
                    continue
                ax, ay, az_ = pts[a]
                bx, by, bz_ = pts[b]
                fx, fy, fz_ = pts[fi]

                # Normal: use stored vertex normals (average of 3) when available
                # — these are always correct regardless of face winding order.
                # Fall back to computed face normal only if no normals stored.
                if has_normals:
                    na = rot_nrm[a]; nb = rot_nrm[b]; nc = rot_nrm[fi]
                    fnx = (na[0]+nb[0]+nc[0]) / 3
                    fny = (na[1]+nb[1]+nc[1]) / 3
                    fnz = (na[2]+nb[2]+nc[2]) / 3
                    nlen = math.sqrt(fnx*fnx + fny*fny + fnz*fnz) or 1.0
                    fnx /= nlen; fny /= nlen; fnz /= nlen
                else:
                    ra = rot[a]; rb = rot[b]; rc = rot[fi]
                    e1 = (rb[0]-ra[0], rb[1]-ra[1], rb[2]-ra[2])
                    e2 = (rc[0]-ra[0], rc[1]-ra[1], rc[2]-ra[2])
                    fnx = e1[1]*e2[2] - e1[2]*e2[1]
                    fny = e1[2]*e2[0] - e1[0]*e2[2]
                    fnz = e1[0]*e2[1] - e1[1]*e2[0]
                    nlen = math.sqrt(fnx*fnx + fny*fny + fnz*fnz) or 1.0
                    fnx /= nlen; fny /= nlen; fnz /= nlen

                # fnz > 0 means normal faces toward viewer = front face
                front = fnz > 0.0

                # Lighting: use abs dot so back faces still shade (not solid black)
                diff = abs(fnx*lx + fny*ly + fnz*lz)
                if front:
                    light = 0.22 + 0.73 * diff
                else:
                    light = 0.05 + 0.18 * diff   # back faces much darker

                r_c = int(min(255, 40  + light * 145))
                g_c = int(min(255, 75  + light * 135))
                b_c = int(min(255, 130 + light * 105))

                depth = (az_ + bz_ + fz_) / 3
                face_data.append((front, depth, ax, ay, bx, by, fx, fy,
                                   f"#{r_c:02x}{g_c:02x}{b_c:02x}"))

            # Two-pass draw: back faces first (no outline), front faces on top
            # This guarantees front faces are never buried by back faces,
            # fixing the "crystal / inside-out" artefact caused by mixed winding.
            back  = sorted((f for f in face_data if not f[0]), key=lambda f:  f[1])
            front = sorted((f for f in face_data if     f[0]), key=lambda f:  f[1])

            for _, _d, ax, ay, bx, by, fx, fy, fill in back:
                c.create_polygon(ax, ay, bx, by, fx, fy,
                                 fill=fill, outline="", width=0)
            for _, _d, ax, ay, bx, by, fx, fy, fill in front:
                c.create_polygon(ax, ay, bx, by, fx, fy,
                                 fill=fill, outline="#1a2a3a", width=1)
        else:
            r = max(1, int(scale * 0.05))
            for px, py, _ in pts:
                c.create_oval(px-r, py-r, px+r, py+r, fill="#5080d0", outline="")

        c.create_text(6, 6, text="Drag to rotate  ·  Scroll to zoom",
                      anchor="nw", fill=FG_MUTED, font=("Segoe UI", 8))

    # ─── Textured render (PIL affine-UV software rasterizer) ─────────────────

    def _redraw_textured(self):
        """
        Render with proper per-triangle affine UV mapping using PIL.Image.transform.
        Each triangle gets its own texture patch via the inverse-affine mapping,
        then is composited onto the framebuffer with a triangular alpha mask.
        """
        c  = self._canvas
        cw = c.winfo_width()  or 300
        ch = c.winfo_height() or 240

        try:
            from PIL import Image as PILImage, ImageDraw as PILDraw, ImageEnhance
        except ImportError:
            self._redraw_shaded()
            return

        if not self._verts or not self._faces or not self._textures or not self._uvs:
            self._redraw_shaded()
            return

        # Pre-tile each texture 3×3 so UV coordinates in [-1, 2] map cleanly.
        # Many playable characters use tiling UVs (e.g. u=-1 to 1.25) for
        # repeating armour/cloth patterns.  Hard clamping destroys those.
        # With 3 tiles: _uvt(x) = (x + 1) / 3 maps [-1, 2] → [0, 1] inside
        # the tiled texture, which covers the full observed UV range.
        NTILES = 3
        textures_tiled = []
        for t in self._textures:
            t_rgb = t.convert("RGB")
            tw_b, th_b = t_rgb.size
            tiled = PILImage.new("RGB", (tw_b * NTILES, th_b * NTILES))
            for ty in range(NTILES):
                for tx in range(NTILES):
                    tiled.paste(t_rgb, (tx * tw_b, ty * th_b))
            textures_tiled.append(tiled)

        uvs = self._uvs
        face_tex = self._face_tex_indices

        # ── Same Z-up rotation pipeline as shaded ─────────────────────────────
        xs_r = [v[0] for v in self._verts]
        ys_r = [v[1] for v in self._verts]
        zs_r = [v[2] for v in self._verts]
        cx_r = (max(xs_r) + min(xs_r)) / 2
        cy_r = (max(ys_r) + min(ys_r)) / 2
        cz_r = (max(zs_r) + min(zs_r)) / 2
        mesh_span = max(max(xs_r)-min(xs_r), max(ys_r)-min(ys_r),
                        max(zs_r)-min(zs_r), 1e-6)
        scale = self._zoom * min(cw, ch) * 0.42 / mesh_span

        az, el = self._az, self._el
        caz, saz = math.cos(az), math.sin(az)
        cel, sel = math.cos(el), math.sin(el)

        rot = []
        for x, y, z in self._verts:
            x2, y2, z2 = x - cx_r, z - cz_r, y - cy_r   # Z-up mapping
            rx =  x2 * caz + z2 * saz
            ry =  y2
            rz = -x2 * saz + z2 * caz
            rot.append((rx, ry * cel - rz * sel, ry * sel + rz * cel))

        has_normals = len(self._normals) == len(self._verts)
        rot_nrm = []
        if has_normals:
            for nx, ny, nz in self._normals:
                nx2, ny2, nz2 = nx, nz, ny
                rnx =  nx2 * caz + nz2 * saz
                rny =  ny2
                rnz = -nx2 * saz + nz2 * caz
                rot_nrm.append((rnx, rny * cel - rnz * sel, rny * sel + rnz * cel))

        cx2 = cw // 2;  cy2 = ch // 2
        pts = [(cx2 + v[0] * scale, cy2 - v[1] * scale, v[2]) for v in rot]

        lx, ly, lz = 0.57, 0.74, 0.37

        # ── Collect and depth-sort visible (front-facing) faces ───────────────
        # _uvt maps raw UV x (range [-1, 2]) to [0, 1] inside the 3×3 tiled
        # texture.  Clamp with tiny margin to handle IEEE rounding at borders.
        def _uvt(x): return max(0.0, min(1.0, (x + 1.0) / NTILES))

        face_list = []
        for face_idx, (a, b, fi) in enumerate(self._faces):
            if a >= len(pts) or b >= len(pts) or fi >= len(pts):
                continue
            ax, ay, az_ = pts[a];  bx, by, bz_ = pts[b];  fx, fy, fz_ = pts[fi]

            if has_normals and a < len(rot_nrm):
                na = rot_nrm[a]; nb = rot_nrm[b]; nc = rot_nrm[fi]
                fnx = (na[0]+nb[0]+nc[0])/3; fny = (na[1]+nb[1]+nc[1])/3; fnz = (na[2]+nb[2]+nc[2])/3
            else:
                ra = rot[a]; rb = rot[b]; rc = rot[fi]
                e1 = (rb[0]-ra[0], rb[1]-ra[1], rb[2]-ra[2])
                e2 = (rc[0]-ra[0], rc[1]-ra[1], rc[2]-ra[2])
                fnx = e1[1]*e2[2]-e1[2]*e2[1]; fny = e1[2]*e2[0]-e1[0]*e2[2]; fnz = e1[0]*e2[1]-e1[1]*e2[0]

            nlen = math.sqrt(fnx*fnx+fny*fny+fnz*fnz) or 1.0
            fnx /= nlen; fny /= nlen; fnz /= nlen

            if fnz <= 0.0:   # backface cull
                continue

            diff  = fnx*lx + fny*ly + fnz*lz
            light = 0.25 + 0.75 * max(0.0, diff)
            depth = (az_ + bz_ + fz_) / 3

            ua = _uvt(uvs[a][0])  if a  < len(uvs) else 1/3.; va = _uvt(uvs[a][1])  if a  < len(uvs) else 1/3.
            ub = _uvt(uvs[b][0])  if b  < len(uvs) else 1/3.; vb = _uvt(uvs[b][1])  if b  < len(uvs) else 1/3.
            uf = _uvt(uvs[fi][0]) if fi < len(uvs) else 1/3.; vf = _uvt(uvs[fi][1]) if fi < len(uvs) else 1/3.

            t_idx = face_tex[face_idx] if face_idx < len(face_tex) else 0
            face_list.append((depth, ax, ay, bx, by, fx, fy,
                               ua, va, ub, vb, uf, vf, light, t_idx))

        face_list.sort(key=lambda f: f[0])   # back→front (depth only, all front-facing)

        # ── Rasterize to PIL image with per-triangle affine UV mapping ────────
        img = PILImage.new("RGB", (cw, ch), "#07070f")

        for (depth, ax, ay, bx, by, fx, fy,
             ua, va, ub, vb, uf, vf, light, t_idx) in face_list:

            # Select tiled texture for this face group
            if t_idx < 0 or t_idx >= len(textures_tiled):
                continue   # no-texture group — skip
            tex = textures_tiled[t_idx]
            tw, th = tex.size

            # Bounding box (clamped to canvas)
            xlo = max(0, int(min(ax, bx, fx)))
            xhi = min(cw, int(max(ax, bx, fx)) + 2)
            ylo = max(0, int(min(ay, by, fy)))
            yhi = min(ch, int(max(ay, by, fy)) + 2)
            bbw = xhi - xlo;  bbh = yhi - ylo
            if bbw <= 0 or bbh <= 0:
                continue

            # Inverse affine: dest (x_bb, y_bb) → source (tu, tv)
            det = ax*(by - fy) + bx*(fy - ay) + fx*(ay - by)
            if abs(det) < 0.5:
                continue

            A = (ua*(by-fy) + ub*(fy-ay) + uf*(ay-by)) * tw / det
            B = (ua*(fx-bx) + ub*(ax-fx) + uf*(bx-ax)) * tw / det
            C = (ua*(bx*fy-fx*by) + ub*(fx*ay-ax*fy) + uf*(ax*by-bx*ay)) * tw / det
            D = (va*(by-fy) + vb*(fy-ay) + vf*(ay-by)) * th / det
            E = (va*(fx-bx) + vb*(ax-fx) + vf*(bx-ax)) * th / det
            F = (va*(bx*fy-fx*by) + vb*(fx*ay-ax*fy) + vf*(ax*by-bx*ay)) * th / det

            C2 = A * xlo + B * ylo + C
            F2 = D * xlo + E * ylo + F

            try:
                patch = tex.transform((bbw, bbh), PILImage.AFFINE,
                                      data=(A, B, C2, D, E, F2),
                                      resample=PILImage.BILINEAR)
            except Exception:
                continue

            if light != 1.0:
                patch = ImageEnhance.Brightness(patch).enhance(light)

            mask = PILImage.new("L", (bbw, bbh), 0)
            PILDraw.Draw(mask).polygon(
                [(ax-xlo, ay-ylo), (bx-xlo, by-ylo), (fx-xlo, fy-ylo)], fill=255)

            img.paste(patch, (xlo, ylo), mask)

        PILDraw.Draw(img).text((6, 6),
            "Drag to rotate  ·  Scroll to zoom  ·  [Textured]",
            fill=(80, 100, 130))

        # ── Display ───────────────────────────────────────────────────────────
        from PIL import ImageTk
        photo = ImageTk.PhotoImage(img)
        self._photo_ref = photo
        c.delete("all")
        c.create_image(0, 0, anchor="nw", image=photo)


# ═══════════════════════════════════════════════════════════════════════════════
#  3D MODELS TAB
# ═══════════════════════════════════════════════════════════════════════════════
