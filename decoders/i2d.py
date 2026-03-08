"""
CGSR .i2d Sprite Decoder — Revenant (1999)
===========================================

Format summary (reverse-engineered):
  - CGSR header: 88 bytes
      0x48/0x4A  = width / height (pixels)
      0x18       = state count
  - After header: state payload containing ≥1 chunk table per state
  - Chunk table: 32-byte pre-header, then uint32 type/width_chunks/height_chunks/table_sz,
                 followed by (width_chunks × height_chunks) uint32 offsets
  - Each offset is relative to the chunk table start; zero = empty/transparent chunk
  - Each non-zero chunk block starts with 2 DLE bytes: DL (RLE escape), DH (LZ escape)
  - Pixel stream (8-bit palette indices):
      raw byte b   → literal pixel of index b
      b == DL      → RLE run:  next byte = special command or (count, color) follows
          DL + 0xC0 → skip to start of next row
          DL + N    → RLE run: N = count, next byte = color index (paint N pixels)
      b == DH      → LZ back-ref (2 extra bytes skipped; not yet implemented)
  - Color index 0x00 = transparent (alpha = 0)
  - Chunk grid: each tile is CHUNK_PX × CHUNK_PX pixels (64 px)
  - Palette: extracted from same-directory .bmp files, else Windows VGA fallback

Usage:
    from decoders.i2d import decode_i2d
    img = decode_i2d(Path("...Forest/forbirch001.i2d"))
    if img:
        img.save("output.png")
"""

from __future__ import annotations
import struct
from pathlib import Path
from typing import Optional

CHUNK_PX    = 64          # pixels per chunk tile
CGSR_MAGIC  = b'CGSR'
CHUNK_TYPE  = 5           # i2d chunk table type marker

# ──────────────────────────────────────────────────────────────────────────────
#  PALETTE
# ──────────────────────────────────────────────────────────────────────────────

_PAL_CACHE: dict[str, list] = {}   # folder → [r,g,b, r,g,b, …]  (768 values)


def _vga_palette() -> list[int]:
    """Return the 256-colour Windows VGA palette as flat [R,G,B,…] list."""
    # Standard 18-colour VGA palette for first 16 + extended grayscale fill
    vga = [
        0,0,0,        0,0,168,      0,168,0,      0,168,168,
        168,0,0,      168,0,168,    168,84,0,     168,168,168,
        84,84,84,     84,84,252,    84,252,84,    84,252,252,
        252,84,84,    252,84,252,   252,252,84,   252,252,252,
    ]
    # Fill remaining 240 entries with a generated ramp
    for i in range(240):
        v = int(i * 255 / 239)
        vga += [v, v, v]
    return vga[:768]


def _load_palette_from_dir(folder: Path) -> list[int]:
    """Try to load a shared 256-colour palette from any .bmp in the same folder."""
    key = str(folder)
    if key in _PAL_CACHE:
        return _PAL_CACHE[key]
    try:
        from PIL import Image
        for bmp in folder.iterdir():
            if bmp.suffix.lower() == '.bmp':
                img = Image.open(bmp)
                if img.mode == 'P':
                    raw_pal = img.getpalette()   # up to 768 ints
                    if raw_pal and len(raw_pal) >= 3:
                        # Pad to 768 if shorter
                        pal = list(raw_pal) + [0] * (768 - len(raw_pal))
                        _PAL_CACHE[key] = pal[:768]
                        return _PAL_CACHE[key]
                elif img.mode in ('RGB', 'RGBA'):
                    # Build an approximate palette from the image's colours
                    pass
    except Exception:
        pass
    pal = _vga_palette()
    _PAL_CACHE[key] = pal
    return pal


def _make_rgba_palette(pal_flat: list[int]) -> list[tuple]:
    """Convert flat [R,G,B,…] to list of (R,G,B,A) tuples; index 0 = transparent."""
    rgba = []
    for i in range(256):
        r = pal_flat[i * 3]     if i * 3 < len(pal_flat) else 0
        g = pal_flat[i * 3 + 1] if i * 3 + 1 < len(pal_flat) else 0
        b = pal_flat[i * 3 + 2] if i * 3 + 2 < len(pal_flat) else 0
        a = 0 if i == 0 else 255     # index 0 = transparent
        rgba.append((r, g, b, a))
    return rgba


# ──────────────────────────────────────────────────────────────────────────────
#  CHUNK TABLE FINDER
# ──────────────────────────────────────────────────────────────────────────────

def _find_chunk_table(payload: bytes, n_cols: int, n_rows: int) -> Optional[int]:
    """
    Scan payload for chunk table header: uint32 type=5, n_cols, n_rows.
    Returns the offset of the type=5 field within payload, or None.
    The pre-header (32 bytes before type) is NOT part of what we return.

    Validation: at least one block offset must be non-zero AND within the
    payload bounds relative to ct_base (= found_offset - 32).  This prevents
    false-positive matches where [5, 1, 1] appears in unrelated data.
    """
    n_chunks = n_cols * n_rows
    # We need at least: type(4) + w(4) + h(4) + sz(4) + n_chunks*4 bytes
    min_size = 16 + n_chunks * 4
    limit = len(payload) - min_size
    for i in range(32, limit, 4):   # i >= 32 so ct_base = i-32 >= 0
        if (struct.unpack_from('<I', payload, i)[0]     == CHUNK_TYPE and
            struct.unpack_from('<I', payload, i + 4)[0] == n_cols     and
            struct.unpack_from('<I', payload, i + 8)[0] == n_rows):
            # Validate: at least one offset must point inside the payload
            ct_base = i - 32
            max_valid = len(payload) - ct_base
            offsets_start = i + 16
            valid = False
            for k in range(n_chunks):
                off = struct.unpack_from('<I', payload, offsets_start + k * 4)[0]
                if 0 < off < max_valid:
                    valid = True
                    break
            if valid or n_chunks == 0:
                return i
    return None


# ──────────────────────────────────────────────────────────────────────────────
#  CHUNK DECOMPRESSOR
# ──────────────────────────────────────────────────────────────────────────────

def _decode_chunk(data: bytes,
                  pixels: bytearray,
                  stride: int,
                  x0: int, y0: int,
                  img_w: int, img_h: int):
    """
    Decode one compressed chunk and write palette indices into `pixels`.

    `pixels` is a flat bytearray of size img_w × img_h (palette indices).
    `stride` = img_w.
    """
    if len(data) < 2:
        return

    dl = data[0]   # RLE escape byte
    dh = data[1]   # LZ escape byte (skip for now)
    i  = 2

    x, y = 0, 0

    while i < len(data):
        if y >= CHUNK_PX:
            break

        b = data[i]; i += 1

        if b == dl:
            # ── RLE escape ────────────────────────────────────────────────
            if i >= len(data):
                break
            cmd = data[i]; i += 1

            if cmd == 0xC0:
                # Skip to start of next row
                y += 1
                x  = 0

            else:
                # (cmd=count, color=next byte) RLE run
                count = cmd
                if i >= len(data):
                    break
                color = data[i]; i += 1
                for _ in range(count):
                    if x < CHUNK_PX and y < CHUNK_PX:
                        px = x0 + x
                        py = y0 + y
                        if 0 <= px < img_w and 0 <= py < img_h:
                            pixels[py * stride + px] = color
                    x += 1
                    if x >= CHUNK_PX:
                        x  = 0
                        y += 1
                        if y >= CHUNK_PX:
                            break

        elif b == dh:
            # ── LZ back-reference (skip — not yet implemented) ────────────
            i += 2

        else:
            # ── Raw pixel ─────────────────────────────────────────────────
            if x < CHUNK_PX and y < CHUNK_PX:
                px = x0 + x
                py = y0 + y
                if 0 <= px < img_w and 0 <= py < img_h:
                    pixels[py * stride + px] = b
            x += 1
            if x >= CHUNK_PX:
                x  = 0
                y += 1


# ──────────────────────────────────────────────────────────────────────────────
#  PUBLIC API
# ──────────────────────────────────────────────────────────────────────────────

def decode_i2d(path: Path, use_alpha: bool = True) -> Optional["Image"]:
    """
    Decode a CGSR .i2d file and return a PIL RGBA Image, or None on failure.

    Parameters
    ----------
    path       : path to the .i2d file
    use_alpha  : if True, index 0 → transparent; else all pixels fully opaque
    """
    try:
        from PIL import Image
    except ImportError:
        return None

    try:
        raw = path.read_bytes()
    except Exception:
        return None

    if len(raw) < 88 or raw[:4] != CGSR_MAGIC:
        return None

    hdr_size = struct.unpack_from('<H', raw, 0x10)[0]
    width    = struct.unpack_from('<H', raw, 0x48)[0]
    height   = struct.unpack_from('<H', raw, 0x4A)[0]

    if width == 0 or height == 0:
        return None

    payload = raw[hdr_size:]

    n_cols   = (width  + CHUNK_PX - 1) // CHUNK_PX
    n_rows   = (height + CHUNK_PX - 1) // CHUNK_PX
    n_chunks = n_cols * n_rows

    # ── Locate chunk table ──────────────────────────────────────────────────
    ct_type_off = _find_chunk_table(payload, n_cols, n_rows)
    if ct_type_off is None:
        return None

    # The "chunk table start" for offset calculations is 32 bytes BEFORE type field.
    # Offsets in the block array are relative to that 32-byte-earlier position.
    ct_base = ct_type_off - 32

    # table_size field at type+12; offsets start at type+16
    offsets_start = ct_type_off + 16
    if offsets_start + n_chunks * 4 > len(payload):
        return None

    offsets = [
        struct.unpack_from('<I', payload, offsets_start + k * 4)[0]
        for k in range(n_chunks)
    ]

    # ── Build palette ────────────────────────────────────────────────────────
    pal_flat = _load_palette_from_dir(path.parent)
    rgba_pal = _make_rgba_palette(pal_flat)

    # ── Allocate pixel buffer (8-bit palette indices) ────────────────────────
    canvas_w = n_cols * CHUNK_PX
    canvas_h = n_rows * CHUNK_PX
    pixels   = bytearray(canvas_w * canvas_h)   # 0 = transparent

    # ── Decode each chunk ────────────────────────────────────────────────────
    for idx, off in enumerate(offsets):
        if off == 0 or off > len(payload):
            continue
        col = idx % n_cols
        row = idx // n_cols
        abs_off = ct_base + off
        if abs_off < 0 or abs_off >= len(payload):
            continue

        # Determine chunk data size: next non-zero offset - current offset
        chunk_end = len(payload) - ct_base
        for next_off in offsets[idx + 1:]:
            if 0 < next_off <= len(payload):
                chunk_end = next_off
                break
        chunk_data = payload[abs_off: ct_base + chunk_end]

        _decode_chunk(
            chunk_data, pixels, canvas_w,
            col * CHUNK_PX, row * CHUNK_PX,
            canvas_w, canvas_h
        )

    # ── Convert to RGBA using palette ────────────────────────────────────────
    out = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
    px_data = out.load()
    for py in range(canvas_h):
        for px in range(canvas_w):
            idx8 = pixels[py * canvas_w + px]
            r, g, b, a = rgba_pal[idx8]
            if not use_alpha:
                a = 255
            px_data[px, py] = (r, g, b, a)

    # Crop to actual sprite dimensions
    out = out.crop((0, 0, width, height))
    return out


def decode_i2d_info(path: Path) -> dict:
    """Return header info dict without decoding pixels."""
    try:
        raw = path.read_bytes()
        if len(raw) < 88 or raw[:4] != CGSR_MAGIC:
            return {}
        hdr_size = struct.unpack_from('<H', raw, 0x10)[0]
        width    = struct.unpack_from('<H', raw, 0x48)[0]
        height   = struct.unpack_from('<H', raw, 0x4A)[0]
        x_off    = struct.unpack_from('<H', raw, 0x4C)[0]
        y_off    = struct.unpack_from('<H', raw, 0x4E)[0]
        pix_fmt  = struct.unpack_from('<I', raw, 0x50)[0]
        n_cols   = (width  + CHUNK_PX - 1) // CHUNK_PX
        n_rows   = (height + CHUNK_PX - 1) // CHUNK_PX
        payload  = raw[hdr_size:]
        ct_off   = _find_chunk_table(payload, n_cols, n_rows)
        return {
            "width":    width,
            "height":   height,
            "x_offset": x_off,
            "y_offset": y_off,
            "pix_fmt":  hex(pix_fmt),
            "n_chunks": n_cols * n_rows,
            "n_cols":   n_cols,
            "n_rows":   n_rows,
            "ct_found": ct_off is not None,
            "file_size": len(raw),
        }
    except Exception:
        return {}
