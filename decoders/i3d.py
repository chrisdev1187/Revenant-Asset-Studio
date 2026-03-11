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
    [+0 : +56]  Section table  — 7 × 8-byte entries (uint32 offset, uint32 count)
      entry 0: [+0 :+8 ]  (header / metadata block)
      entry 1: [+8 :+16]  offset=vertex_data_offset, count=vertex_count   (CONFIRMED)
      entry 2: [+16:+24]  offset=face_data_offset,   count=face_count      (CONFIRMED)
      entries 3-6: additional data sections (UVs, normals, materials, etc.)
    [+56 : vertex_start]  metadata (name string, bounding sphere, etc.)
    [vertex_start : face_start]  vertex_count × stride bytes of vertex data
    [face_start : face_end]      face_count × 6 bytes (uint16 triplets)

  Section offsets are relative to payload_start.
  Primary decode uses these directly; heuristic scan is fallback only.

  Vertex format (stride 32 — D3DFVF_XYZ | D3DFVF_NORMAL | D3DFVF_TEX1):
    [+0:12]  float32 x, y, z    ← world-space position
    [+12:24] float32 nx, ny, nz ← surface normal (unit vector)
    [+24:32] float32 u, v       ← texture UV coordinates

  Face format:
    3 × uint16 per triangle (vertex indices, 0-based)

Geometry detection — two-pass strategy:
  Pass 1 (section-table): read section[1].offset and section[2].offset directly.
    Validate that the derived vertex and face buffers contain plausible data.
    Use if valid.
  Pass 2 (heuristic scan, fallback):
    1. Scan payload in steps of 6 bytes for a run of face_count valid uint16
       triplets (indices < vc, at least one index > 1 to reject zero-filled blocks).
    2. Working backwards from face_start, find vertex stride by verifying
       vc*stride bytes of valid float triples end exactly at face_start.
    3. Prefer stride=32 (standard D3D7); fallback chain: 28,40,36,44,24,48,20,16.

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
    vertices      : List[Tuple[float, float, float]]   # (x, y, z) per vertex
    faces         : List[Tuple[int,   int,   int  ]]   # triangle indices (0-based)
    normals       : List[Tuple[float, float, float]]   # (nx, ny, nz) per vertex
    uvs           : List[Tuple[float, float]]          # (u, v) per vertex
    stride        : int                                # detected vertex stride (bytes)
    vert_count    : int                                # vertex count from section table
    idx_count     : int                                # face count from section table
    path          : Path                               # source .i3d file
    decode_method : str = "unknown"                    # "section_table" or "scan"


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _valid_coord(v: float) -> bool:
    return math.isfinite(v) and abs(v) < MAX_COORD

def _valid_uv(v: float) -> bool:
    return math.isfinite(v) and -10.0 <= v <= 10.0

def _valid_normal(v: float) -> bool:
    return math.isfinite(v) and -2.0 <= v <= 2.0


def _validate_vertex_block(raw: bytes, vstart: int, vc: int, stride: int,
                            n_check: int = 32) -> int:
    """
    Validate that a proposed vertex block contains plausible XYZ floats.
    Returns a quality score (0 = invalid, >0 = valid with that confidence).
    """
    if vstart < 0 or vstart + vc * stride > len(raw):
        return 0

    quality = 0
    check   = min(vc, n_check)
    for i in range(check):
        voff = vstart + i * stride
        if voff + 12 > len(raw):
            return 0
        x, y, z = struct.unpack_from('<fff', raw, voff)
        if not (_valid_coord(x) and _valid_coord(y) and _valid_coord(z)):
            return 0
        if abs(x) > 0.001 or abs(y) > 0.001 or abs(z) > 0.001:
            quality += 1

    return quality


def _validate_face_block(raw: bytes, fstart: int, fc: int, vc: int) -> int:
    """
    Validate that a proposed face block contains plausible index triplets.
    Returns max_index seen (>1 = valid, 0 = invalid / all-zero sentinels).
    """
    if fstart < 0 or fstart + fc * 6 > len(raw):
        return 0

    max_idx = 0
    for i in range(fc):
        foff = fstart + i * 6
        a, b, c = struct.unpack_from('<HHH', raw, foff)
        if a >= vc or b >= vc or c >= vc:
            return 0
        if a > max_idx: max_idx = a
        if b > max_idx: max_idx = b
        if c > max_idx: max_idx = c

    return max_idx


# ─── Primary decode: section table offsets ────────────────────────────────────

def _try_section_table(raw: bytes, payload_start: int, vc: int,
                       fc: int) -> Optional[Tuple[int, int, int, str]]:
    """
    Attempt to locate vertex/face data using the section table offsets at
    payload[+8] and payload[+16].  These are byte offsets relative to
    payload_start.

    Returns (vstart, stride, fstart, "section_table") or None.
    """
    if payload_start + 24 > len(raw):
        return None

    sec1_off = struct.unpack_from('<I', raw, payload_start + 8 )[0]
    sec2_off = struct.unpack_from('<I', raw, payload_start + 16)[0]

    # Sanity: offsets must be positive, distinct, and fit within the file.
    if sec1_off == 0 or sec2_off == 0:
        return None
    if sec1_off >= sec2_off:
        return None

    vstart_candidate = payload_start + sec1_off
    fstart_candidate = payload_start + sec2_off

    if fstart_candidate + fc * 6 > len(raw):
        return None

    # Validate face block first (cheaper)
    max_idx = _validate_face_block(raw, fstart_candidate, fc, vc)
    if max_idx <= 1:
        return None

    # Derive stride from the gap between vertex and face blocks.
    gap = fstart_candidate - vstart_candidate
    if gap <= 0:
        return None

    # Try the exact stride implied by the gap first.
    exact_stride = gap // vc if vc > 0 else 0
    ordered_strides = list(VALID_STRIDES)
    if exact_stride in ordered_strides:
        ordered_strides.remove(exact_stride)
        ordered_strides.insert(0, exact_stride)

    for stride in ordered_strides:
        vstart = fstart_candidate - vc * stride
        if vstart < payload_start:
            continue
        q = _validate_vertex_block(raw, vstart, vc, stride)
        if q > 0:
            return (vstart, stride, fstart_candidate, "section_table")

    return None


# ─── Fallback decode: heuristic scan ──────────────────────────────────────────

def _try_scan(raw: bytes, payload_start: int, vc: int,
              fc: int) -> Optional[Tuple[int, int, int, str]]:
    """
    Scan the payload for a valid face index block, then walk back to find
    the vertex buffer and stride.

    Steps by 6 bytes (face triplet alignment) to reduce false positives.
    Returns (vstart, stride, fstart, "scan") or None.
    """
    n_face_bytes = fc * 6
    best_result  = None
    best_quality = -1

    scan_end = len(raw) - n_face_bytes
    # Step by 6: face triplets are 6-byte aligned within their block.
    for fstart in range(payload_start + 56, scan_end, 6):
        max_idx = _validate_face_block(raw, fstart, fc, vc)
        if max_idx <= 1:
            continue

        # Try each stride to find a valid vertex buffer ending here.
        for stride in VALID_STRIDES:
            vstart = fstart - vc * stride
            if vstart < payload_start:
                continue
            q = _validate_vertex_block(raw, vstart, vc, stride)
            if q > 0:
                total_quality = q * 1000 + max_idx
                if total_quality > best_quality:
                    best_quality = total_quality
                    best_result  = (vstart, stride, fstart, "scan")
                break  # accepted this fstart; keep scanning for better block

    return best_result


# ─── Full geometry decode ──────────────────────────────────────────────────────

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

    # Section table: vertex_count at [+12], face_count at [+20]
    vc = struct.unpack_from('<I', raw, payload_start + 12)[0]
    fc = struct.unpack_from('<I', raw, payload_start + 20)[0]

    if vc == 0 or vc > 300_000 or fc == 0:
        return None

    # ── Locate geometry: section table first, heuristic scan as fallback ──────
    result = _try_section_table(raw, payload_start, vc, fc)
    if result is None:
        result = _try_scan(raw, payload_start, vc, fc)
    if result is None:
        return None

    vstart, stride, fstart, method = result

    # ── Parse vertices, normals, and UVs ─────────────────────────────────────
    vertices : List[Tuple[float, float, float]] = []
    normals  : List[Tuple[float, float, float]] = []
    uvs      : List[Tuple[float, float]]        = []

    has_normals = (stride >= 24)
    has_uvs     = (stride >= 32)

    for i in range(vc):
        voff = vstart + i * stride
        if voff + 12 > len(raw):
            vertices.append((0.0, 0.0, 0.0))
            normals.append((0.0, 1.0, 0.0))
            uvs.append((0.0, 0.0))
            continue

        x, y, z = struct.unpack_from('<fff', raw, voff)
        if _valid_coord(x) and _valid_coord(y) and _valid_coord(z):
            vertices.append((x, y, z))
        else:
            vertices.append((0.0, 0.0, 0.0))

        if has_normals and voff + 24 <= len(raw):
            nx, ny, nz = struct.unpack_from('<fff', raw, voff + 12)
            if _valid_normal(nx) and _valid_normal(ny) and _valid_normal(nz):
                normals.append((nx, ny, nz))
            else:
                normals.append((0.0, 1.0, 0.0))
        else:
            normals.append((0.0, 1.0, 0.0))

        if has_uvs and voff + 32 <= len(raw):
            u, v = struct.unpack_from('<ff', raw, voff + 24)
            if _valid_uv(u) and _valid_uv(v):
                uvs.append((u, v))
            else:
                uvs.append((0.0, 0.0))
        else:
            uvs.append((0.0, 0.0))

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
        vertices      = vertices,
        faces         = faces,
        normals       = normals,
        uvs           = uvs,
        stride        = stride,
        vert_count    = vc,
        idx_count     = fc,
        path          = path,
        decode_method = method,
    )


# ─── OBJ exporter ─────────────────────────────────────────────────────────────

def export_obj(geom: I3DGeometry, out_path: Path) -> bool:
    """
    Export I3DGeometry as a Wavefront OBJ file (with normals and UVs).
    Returns True on success, False on error.
    """
    try:
        has_uvs     = any(u != 0.0 or v != 0.0 for u, v in geom.uvs)
        has_normals = any(nx != 0.0 or ny != 1.0 or nz != 0.0
                          for nx, ny, nz in geom.normals)

        lines = [
            f"# RevEngine - Revenant (1999) i3d export",
            f"# Source        : {geom.path.name}",
            f"# Vertices      : {len(geom.vertices)}",
            f"# Faces         : {len(geom.faces)}",
            f"# Stride        : {geom.stride} bytes",
            f"# Decode method : {geom.decode_method}",
            f"# Has normals   : {has_normals}",
            f"# Has UVs       : {has_uvs}",
            f"",
            f"o {geom.path.stem}",
            f"",
        ]

        for x, y, z in geom.vertices:
            lines.append(f"v {x:.6f} {y:.6f} {z:.6f}")
        lines.append("")

        if has_uvs:
            for u, v in geom.uvs:
                lines.append(f"vt {u:.6f} {1.0 - v:.6f}")   # flip V for OBJ convention
            lines.append("")

        if has_normals:
            for nx, ny, nz in geom.normals:
                lines.append(f"vn {nx:.6f} {ny:.6f} {nz:.6f}")
            lines.append("")

        if has_uvs and has_normals:
            for a, b, c in geom.faces:
                a1, b1, c1 = a + 1, b + 1, c + 1
                lines.append(f"f {a1}/{a1}/{a1} {b1}/{b1}/{b1} {c1}/{c1}/{c1}")
        elif has_normals:
            for a, b, c in geom.faces:
                a1, b1, c1 = a + 1, b + 1, c + 1
                lines.append(f"f {a1}//{a1} {b1}//{b1} {c1}//{c1}")
        elif has_uvs:
            for a, b, c in geom.faces:
                a1, b1, c1 = a + 1, b + 1, c + 1
                lines.append(f"f {a1}/{a1} {b1}/{b1} {c1}/{c1}")
        else:
            for a, b, c in geom.faces:
                lines.append(f"f {a + 1} {b + 1} {c + 1}")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines), encoding="ascii")
        return True
    except Exception:
        return False
