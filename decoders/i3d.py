"""
RevEngine - i3d Geometry Decoder
=================================
Decodes Revenant (1999) .i3d 3D model geometry.

File structure (reverse-engineered):

  CGSR header (variable size):
    [0:4]   'CGSR' magic
    [4:8]   version flags (0x01000000)
    [8:12]  content_size  ← payload_start = file_size - content_size
    [12:16] content_size (duplicate)
    [16:20] hdr_size (84 for 1-state; grows with extra states)
    [20:24] state_count (animation states)
    [24:28] mesh_count (usually 1)
    [28:104] first STIL state entry (76 bytes, includes bounding box)
    [104 + (state_count-1)*76 :]  additional state entries (one per extra state)

  Payload starts at: file_size - content_size_field
    [+0 : +56]  Section table  — 7 × 8-byte entries (offset, count)
      [+12]  uint32  vertex_count   ← section[1].count  (CONFIRMED)
      [+20]  uint32  face_count     ← section[2].count  (triangles, CONFIRMED)
    [+56 : vertex_start]  metadata (name string, bounding sphere, etc.)
    [vertex_start : face_start]  vertex_count × stride bytes of vertex data
    [face_start : face_end]      face_count × 6 bytes (uint16 triplets)

  Vertex format (stride 32 — D3DFVF_XYZ | D3DFVF_NORMAL | D3DFVF_TEX1):
    [+0:12]  float32 x, y, z    ← world-space position
    [+12:24] float32 nx, ny, nz ← surface normal (unit vector)
    [+24:32] float32 u, v       ← texture UV coordinates

  Face format:
    3 × uint16 per triangle (vertex indices, 0-based)

Geometry detection:
  1. payload_start = file_size - content_size_field
  2. vertex_count = payload[+12], face_count = payload[+20]
  3. Scan payload for a run of face_count valid uint16 triplets (indices < vc,
     at least one index > 1 to reject zero-filled sentinel blocks)
  4. Working backwards from face_start, find vertex stride by verifying
     vc*stride bytes of valid float triples end exactly at face_start
  5. Prefer stride=32 (standard D3D7); fallback chain: 28,40,36,44,24,48,20,16

COVERAGE: 577/622 files decoded (45 have fc=0 — particles/effects).
"""

from __future__ import annotations
import struct
import math
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List, Tuple

CGSR_MAGIC = b'CGSR'

# Vertex stride preference: 32 first (most common D3D7 FVF for pos+normal+uv)
VALID_STRIDES = (32, 28, 40, 36, 44, 24, 48, 20, 16)

MAX_COORD = 50_000.0


# ─── Data class ───────────────────────────────────────────────────────────────

@dataclass
class I3DGeometry:
    vertices   : List[Tuple[float, float, float]]  # (x, y, z) per vertex
    faces      : List[Tuple[int,   int,   int  ]]  # triangle indices (0-based)
    stride     : int                               # detected vertex stride (bytes)
    vert_count : int                               # vertex count from section table
    idx_count  : int                               # face count from section table
    path       : Path                              # source .i3d file


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _valid_coord(v: float) -> bool:
    return math.isfinite(v) and abs(v) < MAX_COORD


def _find_geometry(
    raw: bytes,
    payload_start: int,
    vc: int,
    fc: int,
) -> Optional[Tuple[int, int, int]]:
    """
    Locate vertex and face data by first finding the face index block, then
    walking back to identify the vertex buffer and stride.

    Returns (vertex_start, stride, face_start) or None.
    """
    n_face_bytes = fc * 6
    best_result  = None
    best_quality = -1

    scan_end = len(raw) - n_face_bytes
    for fstart in range(payload_start + 48, scan_end, 2):
        n_ok    = 0
        off     = fstart
        max_idx = 0

        while n_ok < fc and off + 6 <= len(raw):
            a, b, c = struct.unpack_from('<HHH', raw, off)
            if a < vc and b < vc and c < vc:
                n_ok += 1
                off  += 6
                if a > max_idx: max_idx = a
                if b > max_idx: max_idx = b
                if c > max_idx: max_idx = c
            else:
                break

        # Require all fc faces found, and at least one non-trivial index (> 1)
        # to reject zero-filled sentinel regions
        if n_ok < fc or max_idx <= 1:
            continue

        # Try each stride to find a valid vertex buffer ending here
        for stride in VALID_STRIDES:
            vstart = fstart - vc * stride
            if vstart < payload_start:
                continue

            ok      = True
            quality = 0
            for i in range(min(vc, 8)):
                voff = vstart + i * stride
                if voff + 12 > len(raw):
                    ok = False
                    break
                x, y, z = struct.unpack_from('<fff', raw, voff)
                if not (_valid_coord(x) and _valid_coord(y) and _valid_coord(z)):
                    ok = False
                    break
                if abs(x) > 0.001 or abs(y) > 0.001 or abs(z) > 0.001:
                    quality += 1

            if ok:
                total_quality = quality * 100 + max_idx
                if total_quality > best_quality:
                    best_quality = total_quality
                    best_result  = (vstart, stride, fstart)
                break  # accepted; continue scanning for potentially better block

    return best_result


# ─── Geometry decoder ─────────────────────────────────────────────────────────

def decode_i3d_geometry(path: Path) -> Optional[I3DGeometry]:
    """
    Parse the geometry section of a CGSR .i3d file.
    Returns I3DGeometry on success, or None if parsing fails.
    """
    try:
        raw = path.read_bytes()
    except Exception:
        return None

    if len(raw) < 32 or raw[:4] != CGSR_MAGIC:
        return None

    # Payload starts at file_size - content_size_field
    content_size  = struct.unpack_from('<I', raw, 8)[0]
    payload_start = len(raw) - content_size

    if payload_start < 0 or payload_start + 24 > len(raw):
        return None

    # Section table fields: vertex_count at [+12], face_count at [+20]
    vc = struct.unpack_from('<I', raw, payload_start + 12)[0]
    fc = struct.unpack_from('<I', raw, payload_start + 20)[0]

    if vc == 0 or vc > 300_000 or fc == 0:
        return None

    result = _find_geometry(raw, payload_start, vc, fc)
    if result is None:
        return None

    vstart, stride, fstart = result

    # ── Parse vertices ────────────────────────────────────────────────────────
    vertices: List[Tuple[float, float, float]] = []
    for i in range(vc):
        voff = vstart + i * stride
        if voff + 12 > len(raw):
            vertices.append((0.0, 0.0, 0.0))
            continue
        x, y, z = struct.unpack_from('<fff', raw, voff)
        if _valid_coord(x) and _valid_coord(y) and _valid_coord(z):
            vertices.append((x, y, z))
        else:
            vertices.append((0.0, 0.0, 0.0))

    # ── Parse face indices ────────────────────────────────────────────────────
    faces: List[Tuple[int, int, int]] = []
    for i in range(fc):
        foff = fstart + i * 6
        if foff + 6 > len(raw):
            break
        a, b, c = struct.unpack_from('<HHH', raw, foff)
        if a < vc and b < vc and c < vc:
            faces.append((a, b, c))

    if not vertices:
        return None

    return I3DGeometry(
        vertices   = vertices,
        faces      = faces,
        stride     = stride,
        vert_count = vc,
        idx_count  = fc,
        path       = path,
    )


# ─── OBJ exporter ─────────────────────────────────────────────────────────────

def export_obj(geom: I3DGeometry, out_path: Path) -> bool:
    """
    Export I3DGeometry as a Wavefront OBJ file.
    Returns True on success, False on error.
    """
    try:
        lines = [
            f"# RevEngine - Revenant (1999) i3d export",
            f"# Source  : {geom.path.name}",
            f"# Vertices: {len(geom.vertices)}",
            f"# Faces   : {len(geom.faces)}",
            f"# Stride  : {geom.stride} bytes",
            f"",
            f"o {geom.path.stem}",
            f"",
        ]
        for x, y, z in geom.vertices:
            lines.append(f"v {x:.6f} {y:.6f} {z:.6f}")
        lines.append("")
        for a, b, c in geom.faces:
            lines.append(f"f {a + 1} {b + 1} {c + 1}")   # OBJ is 1-indexed

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines), encoding="ascii")
        return True
    except Exception:
        return False
