"""
RevEngine - CGSR Format Decoder
================================
Handles both .i2d (sprite) and .i3d (3D model) CGSR files.

CGSR Header (84 bytes):
  0x00 magic       "CGSR"
  0x04 type        0x01=2D sprite, 0x00=3D model
  0x07 version     always 0x01
  0x08 data_size   uint32 LE
  0x0C unc_size    uint32 LE
  0x10 hdr_size    uint16 LE (=84)
  0x12 flags       uint16 LE
  0x14 subtype     uint32 LE
  0x18 state_count uint32 LE  (anim states for i3d, 1 for i2d)
  0x1C state_name  36-byte null-padded string (default state name)
  0x40 bounds_type uint32 LE  (always 2 in tested files)
  0x44 bounds_pad  uint32 LE  (always 0)
  0x48 width       uint16 LE
  0x4A height      uint16 LE
  0x4C x_offset    uint16 LE  (world-space anchor)
  0x4E y_offset    uint16 LE
  0x50 pixel_flags uint32 LE  (runtime D3D surface flags - not an offset!)

I3D Animation State Table Entry (76 bytes each, starting at payload+0):
  0x00-0x13  (20 bytes): entry header (flags, transition data)
  0x14-0x4B  (null-terminated name, padded to fill 76 bytes)
"""

import struct
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List

CGSR_MAGIC   = b'CGSR'
HEADER_SIZE  = 0x54   # 84 bytes
ENTRY_SIZE   = 76     # animation state entry size
NAME_OFFSET  = 20     # name position within each entry


# ─── Data Classes ───────────────────────────────────────────────────────────

@dataclass
class CGSRHeader:
    magic:       bytes
    type_byte:   int    # 0x01=2D, 0x00=3D
    version:     int
    data_size:   int
    state_count: int    # animation state count (i3d) or 1 (i2d)
    state_name:  str    # default animation state name
    width:       int    # sprite width (i2d) or bounding box (i3d)
    height:      int
    x_offset:    int
    y_offset:    int
    pixel_flags: int    # runtime D3D flags (not a file offset)


@dataclass
class AnimState:
    index:  int
    name:   str
    header: bytes   # 20-byte pre-name header bytes


@dataclass
class GeometryInfo:
    offset:        int    # offset from file start
    header_ints:   tuple  # first 3 uint32 values
    estimated_verts: int  # second uint32 (likely vertex count)
    raw_size:      int


@dataclass
class CGSRFile:
    path:       Path
    header:     CGSRHeader
    raw:        bytes     # full file bytes
    # i3d specific
    anim_states: List[AnimState] = field(default_factory=list)
    geometry:    Optional[GeometryInfo] = None
    # i2d specific
    thumbnail:   Optional[bytes] = None  # loaded separately from .tn file


# ─── Parser ──────────────────────────────────────────────────────────────────

def parse(path: Path) -> Optional[CGSRFile]:
    """Parse a CGSR file (.i2d or .i3d). Returns CGSRFile or None."""
    try:
        raw = path.read_bytes()
    except IOError:
        return None

    if len(raw) < HEADER_SIZE or raw[:4] != CGSR_MAGIC:
        return None

    h = _parse_header(raw)
    f = CGSRFile(path=path, header=h, raw=raw)

    if h.type_byte == 0x00:     # .i3d
        _parse_i3d(f)
    else:                        # .i2d
        _load_thumbnail(f)

    return f


def _parse_header(raw: bytes) -> CGSRHeader:
    type_byte   = raw[4]
    version     = raw[7]
    data_size   = struct.unpack_from('<I', raw, 0x08)[0]
    state_count = struct.unpack_from('<I', raw, 0x18)[0]
    state_name  = raw[0x1C:0x40].split(b'\x00')[0].decode('ascii', 'replace')
    width, height = struct.unpack_from('<HH', raw, 0x48)
    x_off, y_off  = struct.unpack_from('<HH', raw, 0x4C)
    pixel_flags   = struct.unpack_from('<I', raw, 0x50)[0]

    return CGSRHeader(
        magic=raw[:4], type_byte=type_byte, version=version,
        data_size=data_size, state_count=state_count,
        state_name=state_name, width=width, height=height,
        x_offset=x_off, y_offset=y_off, pixel_flags=pixel_flags,
    )


def _parse_i3d(f: CGSRFile):
    """Parse animation state table and geometry info for .i3d files."""
    payload = f.raw[HEADER_SIZE:]
    count   = f.header.state_count

    for i in range(count):
        off    = i * ENTRY_SIZE
        entry  = payload[off:off + ENTRY_SIZE]
        if len(entry) < ENTRY_SIZE:
            break
        pre    = entry[:NAME_OFFSET]
        name   = entry[NAME_OFFSET:].split(b'\x00')[0].decode('ascii', 'replace')
        f.anim_states.append(AnimState(index=i, name=name, header=pre))

    # Geometry section starts right after the animation state table
    geom_payload_off = count * ENTRY_SIZE
    geom_file_off    = HEADER_SIZE + geom_payload_off
    geom_data        = payload[geom_payload_off:]

    if len(geom_data) >= 12:
        h0, h1, h2 = struct.unpack_from('<III', geom_data, 0)
        f.geometry = GeometryInfo(
            offset=geom_file_off,
            header_ints=(h0, h1, h2),
            estimated_verts=h1,      # second uint32 empirically matches vertex count
            raw_size=len(geom_data),
        )


def _load_thumbnail(f: CGSRFile):
    """Try to load the companion .tn thumbnail file for .i2d sprites."""
    tn_path = f.path.with_suffix('.tn')
    if not tn_path.exists():
        tn_path = f.path.with_suffix('.TN')
    if tn_path.exists():
        f.thumbnail = tn_path.read_bytes()


# ─── Thumbnail Rendering ─────────────────────────────────────────────────────

def thumbnail_to_image(tn_bytes: bytes, scale: int = 1):
    """
    Convert raw .tn thumbnail bytes to PIL Image.
    Format: 16x16 pixels, raw RGB888 (no header).
    Returns PIL Image or None.
    """
    try:
        from PIL import Image
        if len(tn_bytes) < 768:
            return None
        img = Image.frombytes('RGB', (16, 16), tn_bytes[:768])
        if scale > 1:
            img = img.resize((16 * scale, 16 * scale), Image.NEAREST)
        return img
    except Exception:
        return None


def thumbnail_to_tk(tn_bytes: bytes, scale: int = 8):
    """Convert .tn bytes to tkinter PhotoImage (for GUI display)."""
    img = thumbnail_to_image(tn_bytes, scale)
    if img is None:
        return None
    try:
        from PIL import ImageTk
        return ImageTk.PhotoImage(img)
    except Exception:
        return None


# ─── Summary ──────────────────────────────────────────────────────────────────

def describe(f: CGSRFile) -> str:
    h = f.header
    lines = [
        f"File:   {f.path.name}",
        f"Type:   {'2D Sprite' if h.type_byte else '3D Model'}",
        f"Size:   {len(f.raw):,} bytes",
        f"Dims:   {h.width} x {h.height}",
        f"Anchor: ({h.x_offset}, {h.y_offset})",
    ]
    if f.anim_states:
        lines += [
            f"States: {len(f.anim_states)} animation states",
            f"Default: '{h.state_name}'",
        ]
    if f.geometry:
        lines += [
            f"Geometry offset: {f.geometry.offset:,}",
            f"Est. vertices: {f.geometry.estimated_verts:,}",
        ]
    return "\n".join(lines)
