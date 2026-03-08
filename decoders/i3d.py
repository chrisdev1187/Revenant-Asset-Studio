"""
RevEngine - i3d Geometry Decoder
=================================
Decodes Revenant (1999) .i3d 3D model geometry.

Format (partially reverse-engineered — heuristic stride detection):

  CGSR header (84 bytes) — see decoders/cgsr.py for full field list
  Animation state table  — state_count × 76 bytes each
  Geometry section       — starts at offset 84 + state_count × 76

  Geometry section layout:
    [0x00]  uint32  h0           — flags / section type (purpose unclear)
    [0x04]  uint32  vertex_count — CONFIRMED: second uint32 = vertex count
    [0x08]  uint32  h2           — index or face count (see stride detection)
    [0x0C+] bytes   vertex data  — vertex_count × stride bytes
            bytes   index data   — uint16 triplets (triangle indices)

  Vertex stride detection:
    available = len(geom_section) - 12
    Try interpreting h2 as index count (each index = uint16):
      rem = available - h2 * 2
      if rem / vertex_count ∈ VALID_STRIDES → use that stride
    Also try h2 as face count (face = 3 indices):
      rem = available - h2 * 6
      if rem / vertex_count ∈ VALID_STRIDES → use that stride
    Fallback: stride = 32 (common D3D7 FVF with pos+normal+UV)

  Vertex format (at detected stride):
    float32 x   ← position
    float32 y
    float32 z
    ...rest...  ← normal, UV, colour (not decoded here)

  Face format:
    3 × uint16 per triangle (vertex indices, 0-based)

WARNING:
  Geometry decoding is heuristic. It will produce some output for most
  models but may be incorrect for unusual vertex layouts. Sanity-checks
  (finite float values, index < vertex_count) prevent crashes.
"""

from __future__ import annotations
import struct
import math
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Tuple

CGSR_MAGIC   = b'CGSR'
HEADER_SIZE  = 0x54       # 84 bytes
ENTRY_SIZE   = 76         # animation state table entry size

# Common Direct3D vertex strides (bytes) for 1999-era D3D7 games
VALID_STRIDES = (12, 16, 20, 24, 28, 32, 36, 40, 48)


# ─── Data class ──────────────────────────────────────────────────────────────

@dataclass
class I3DGeometry:
    vertices   : List[Tuple[float, float, float]]  # (x, y, z) per vertex
    faces      : List[Tuple[int,   int,   int  ]]  # triangle indices (0-based)
    stride     : int                               # detected vertex stride
    vert_count : int                               # h1 from geometry header
    idx_count  : int                               # h2 from geometry header
    path       : Path                              # source .i3d file


# ─── Geometry decoder ────────────────────────────────────────────────────────

def decode_i3d_geometry(path: Path) -> Optional[I3DGeometry]:
    """
    Parse the geometry section of a CGSR .i3d file.
    Returns I3DGeometry, or None if the file cannot be parsed.
    """
    try:
        raw = path.read_bytes()
    except Exception:
        return None

    if len(raw) < HEADER_SIZE or raw[:4] != CGSR_MAGIC:
        return None

    state_count = struct.unpack_from('<I', raw, 0x18)[0]
    geom_start  = HEADER_SIZE + state_count * ENTRY_SIZE

    if geom_start + 12 > len(raw):
        return None

    geom = raw[geom_start:]
    h0           = struct.unpack_from('<I', geom, 0)[0]   # noqa: F841
    vertex_count = struct.unpack_from('<I', geom, 4)[0]
    h2           = struct.unpack_from('<I', geom, 8)[0]

    if vertex_count == 0 or vertex_count > 300_000:
        return None

    available = len(geom) - 12   # bytes available after the 12-byte section header

    # ── Stride detection ────────────────────────────────────────────────────
    stride     = None
    idx_count  = 0

    # Interpretations of h2 to try (as index count or face count):
    #   h2 as raw index count     → each index is a uint16 = 2 bytes
    #   h2 as face count          → each face = 3 indices = 6 bytes
    #   0 indices (pure vertex blob)
    for try_idx_bytes in (h2 * 2, h2 * 6, 0):
        if try_idx_bytes < 0 or try_idx_bytes > available:
            continue
        rem = available - try_idx_bytes
        if vertex_count == 0:
            continue
        q, r = divmod(rem, vertex_count)
        if r == 0 and q in VALID_STRIDES:
            stride    = q
            idx_count = try_idx_bytes // 2   # number of uint16 index values
            break

    if stride is None:
        # Fallback: assume stride=32 (most common D3D7 FVF) and no index buffer
        stride    = 32
        idx_count = 0

    # ── Parse vertices ───────────────────────────────────────────────────────
    vertices: List[Tuple[float, float, float]] = []
    voff = 12
    for _ in range(vertex_count):
        if voff + 12 > len(geom):
            break
        x, y, z = struct.unpack_from('<fff', geom, voff)
        # Sanity-check: reject NaN/Inf and absurd world-space values
        if (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)
                and abs(x) < 1e5 and abs(y) < 1e5 and abs(z) < 1e5):
            vertices.append((x, y, z))
        else:
            vertices.append((0.0, 0.0, 0.0))
        voff += stride

    if not vertices:
        return None

    # ── Parse face indices (uint16 triplets) ─────────────────────────────────
    faces: List[Tuple[int, int, int]] = []
    if idx_count >= 3:
        foff  = 12 + vertex_count * stride
        n_tri = min(idx_count // 3, (len(geom) - foff) // 6)
        for _ in range(n_tri):
            if foff + 6 > len(geom):
                break
            a, b, c = struct.unpack_from('<HHH', geom, foff)
            if a < len(vertices) and b < len(vertices) and c < len(vertices):
                faces.append((a, b, c))
            foff += 6

    return I3DGeometry(
        vertices=vertices,
        faces=faces,
        stride=stride,
        vert_count=vertex_count,
        idx_count=h2,
        path=path,
    )


# ─── OBJ exporter ────────────────────────────────────────────────────────────

def export_obj(geom: I3DGeometry, out_path: Path) -> bool:
    """
    Export I3DGeometry as a Wavefront OBJ file.
    Returns True on success, False on error.
    """
    try:
        lines = [
            f"# RevEngine — Revenant (1999) i3d export",
            f"# Source  : {geom.path.name}",
            f"# Vertices: {len(geom.vertices)}",
            f"# Faces   : {len(geom.faces)}",
            f"# Stride  : {geom.stride} bytes (heuristic)",
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
