"""
CGSR .i2d Sprite Decoder — Revenant (1999)
===========================================

Format confirmed from original Cinematix C++ source (chunkcache.cpp / bitmapdata.h):

CHUNK BLOCK LAYOUT (confirmed)
  Each offset in the chunk table points to a chunk block with layout:
    [0:4]   4-byte cache ID  — read by game as cache key, skipped by decoder
    [4]     DL              — RLE escape byte  (chosen to be unused pixel value)
    [5]     DH              — LZ  escape byte  (chosen to be unused pixel value)
    [6:]    compressed pixel stream (8-bit palette indices)

COMPRESSED PIXEL STREAM (from ChunkDecompress inline ASM)
  Raw byte b (b != DL and b != DH):
      → literal pixel of palette index b

  DL escape:
      DL + 0x00            → EOL  (end of current row; row counter decremented)
      DL + (N | 0x80)      → skip (N & 0x7F) transparent pixels (advance output ptr)
      DL + N  + color      → RLE run: write N copies of color  (0 < N < 0x80)

  DH escape (LZ back-reference, 4-byte token total):
      DH + count + dist_lo + dist_hi
      → copy `count` bytes from DECOMPRESSED output at (di − dist − 4)
         where di   = current output position in the 64×64 chunk_buf
         and   dist = uint16 little-endian (dist_lo | dist_hi<<8)
      The −4 is a constant bias baked into the encoder (confirmed by depy/RevenantRE).
      Source is the LOCAL chunk_buf (decompressed output), NOT the compressed input.

PALETTE (confirmed from bitmapdata.h / SPalette struct)
  SPalette is embedded in the i2d at a self-relative OFFSET that lies 8 bytes
  before the SChunkHeader (chunk table type=5 field).
    palette_field_pos = ct_type_off − 8
    palette_abs       = palette_field_pos + uint32_le(payload[palette_field_pos])

  SPalette layout:
    [0:512]    256 × uint16 LE  X1R5G5B5  (WORD  colors[256])
    [512:1536] 256 × uint32 LE  ARGB      (DWORD rgbcolors[256])

  X1R5G5B5 → RGB888 conversion (DirectDraw RGB555 / X1R5G5B5):
    R = ((word >> 10) & 0x1F) << 3   ← R in HIGH bits (14-10)
    G = ((word >>  5) & 0x1F) << 3   ← G in MID  bits  (9-5)
    B = (  word       & 0x1F) << 3   ← B in LOW  bits  (4-0)

  .TN files (same stem alongside .i2d, or in the Thumbnails directory):
    768 bytes total; first 512 bytes = SPalette.colors[] (X1R5G5B5 palette),
    bytes 512-767 = ARGB data or thumbnail indices (not used for palette).
    Only the first 512 bytes are read for palette decoding.
    Palette index 0 = transparent (alpha=0 regardless of stored colour).

  Palette index 0 = transparent (alpha = 0).

CHUNK GRID
  Chunks are stored col-major left-to-right, top-to-bottom.
  idx = row * n_cols + col  →  x0 = col*64, y0 = row*64
  Empty chunk (offset == 0) = fully transparent tile.

Usage:
    from decoders.i2d import decode_i2d
    img = decode_i2d(Path("...Forest/forbirch001.i2d"))
    if img:
        img.save("output.png")
"""

from __future__ import annotations
import struct
from pathlib import Path
from typing import Optional, List

CHUNK_PX    = 64          # pixels per chunk tile (CHUNKWIDTH = CHUNKHEIGHT = 64)
CGSR_MAGIC  = b'CGSR'
CHUNK_TYPE  = 5           # SChunkHeader.type value for 8-bit compressed chunks

# ──────────────────────────────────────────────────────────────────────────────
#  PALETTE
# ──────────────────────────────────────────────────────────────────────────────

_PAL_CACHE: dict[str, list] = {}   # path-key → flat [R,G,B,…] 768 values


def _bgr555_to_rgb888(data: bytes) -> List[int]:
    """Convert 256 × uint16-LE X1R5G5B5 words (512 bytes) to flat [R,G,B,…] list.

    DirectDraw X1R5G5B5 / RGB555 bit layout (confirmed empirically):
      bits 14-10 = R  (5 bits, high)
      bits  9-5  = G  (5 bits, mid)
      bits  4-0  = B  (5 bits, low)
    Each component is scaled to 8-bit by left-shifting 3 (e.g. 0x1F → 0xF8).
    """
    result: List[int] = []
    for i in range(256):
        word = struct.unpack_from('<H', data, i * 2)[0]
        r = ((word >> 10) & 0x1F) << 3   # R in HIGH bits (14-10)
        g = ((word >>  5) & 0x1F) << 3   # G in MID  bits  (9-5)
        b = ( word        & 0x1F) << 3   # B in LOW  bits  (4-0)
        result.extend([r, g, b])
    return result


def _vga_palette() -> List[int]:
    """Windows VGA 256-colour palette as flat [R,G,B,…] fallback."""
    vga = [
        0,0,0,        0,0,168,      0,168,0,      0,168,168,
        168,0,0,      168,0,168,    168,84,0,     168,168,168,
        84,84,84,     84,84,252,    84,252,84,    84,252,252,
        252,84,84,    252,84,252,   252,252,84,   252,252,252,
    ]
    for i in range(240):
        v = int(i * 255 / 239)
        vga += [v, v, v]
    return vga[:768]


def _load_palette(path: Path,
                  payload: bytes,
                  ct_type_off: int) -> List[int]:
    """
    Load the 256-colour palette for `path` as a flat [R,G,B,…] list (768 values).

    Palette format (confirmed by SPalette struct in bitmapdata.h):
      SPalette.colors[256]  — 512 bytes of 256 × uint16 LE X1R5G5B5 words
        bits 14-10 = R,  bits 9-5 = G,  bits 4-0 = B
      Embedded via self-relative OFFSET at (ct_type_off − 8) in the payload.

    .TN files alongside the .i2d also begin with the same 512-byte X1R5G5B5
    palette block (bytes 512-767 are something else — thumbnail or ARGB partial).
    We only read the first 512 bytes of a .tn file for palette use.

    Priority:
      1. Embedded palette in the i2d payload  (512-byte X1R5G5B5)
      2. Same-stem .TN / .tn file alongside the i2d  (first 512 bytes)
      3. Same-stem .tn in the Thumbnails sibling directory  (first 512 bytes)
      4. VGA fallback
    """
    cache_key = str(path)
    if cache_key in _PAL_CACHE:
        return _PAL_CACHE[cache_key]

    def _store(pal: List[int]) -> List[int]:
        _PAL_CACHE[cache_key] = pal
        return pal

    # 1 ── Embedded palette (self-relative OFFSET 8 bytes before chunk table type)
    try:
        pal_field = ct_type_off - 8
        if 0 <= pal_field and pal_field + 4 <= len(payload):
            pal_rel = struct.unpack_from('<I', payload, pal_field)[0]
            pal_abs = pal_field + pal_rel
            if pal_abs + 512 <= len(payload):
                raw = payload[pal_abs: pal_abs + 512]
                if any(raw):
                    return _store(_bgr555_to_rgb888(raw))
    except Exception:
        pass

    # 2 ── Same-directory .TN file (same stem as the .i2d)
    for ext in ('.TN', '.tn', '.Tn'):
        tn = path.with_suffix(ext)
        if tn.exists():
            try:
                tn_data = tn.read_bytes()
                if len(tn_data) >= 512 and any(tn_data[:512]):
                    return _store(_bgr555_to_rgb888(tn_data[:512]))
            except Exception:
                pass

    # 3 ── Thumbnails sibling directory (e.g. Imagery/../Thumbnails/<stem>.tn)
    try:
        thumbnails = path.parent.parent / 'Thumbnails'
        if not thumbnails.exists():
            thumbnails = path.parent.parent.parent / 'Thumbnails'
        if thumbnails.exists():
            for ext in ('.tn', '.TN'):
                tn = thumbnails / (path.stem + ext)
                if not tn.exists():
                    tn = (thumbnails / path.stem.lower()).with_suffix(ext)
                if tn.exists():
                    tn_data = tn.read_bytes()
                    if len(tn_data) >= 512 and any(tn_data[:512]):
                        return _store(_bgr555_to_rgb888(tn_data[:512]))
    except Exception:
        pass

    # 4 ── VGA fallback
    return _store(_vga_palette())


def _make_rgba_palette(pal_flat: List[int]) -> List[tuple]:
    """Convert flat [R,G,B,…] to list of (R,G,B,A) tuples; index 0 = transparent."""
    rgba = []
    for i in range(256):
        r = pal_flat[i * 3]     if i * 3     < len(pal_flat) else 0
        g = pal_flat[i * 3 + 1] if i * 3 + 1 < len(pal_flat) else 0
        b = pal_flat[i * 3 + 2] if i * 3 + 2 < len(pal_flat) else 0
        a = 0 if i == 0 else 255
        rgba.append((r, g, b, a))
    return rgba


# ──────────────────────────────────────────────────────────────────────────────
#  CHUNK TABLE FINDER
# ──────────────────────────────────────────────────────────────────────────────

def _find_chunk_table(payload: bytes,
                      n_cols_min: int,
                      n_rows_min: int) -> Optional[tuple]:
    """
    Scan payload for SChunkHeader: uint32 type=5, followed by nc and nr.
    Returns (ct_type_off, nc, nr) on success, or None.

    The stored nc/nr may differ from ceil(width/64) × ceil(height/64) — some
    files store padded grid dimensions.  We accept any SChunkHeader where:
      nc >= n_cols_min  (grid covers full sprite width)
      nr >= n_rows_min  (grid covers full sprite height)
      nc and nr are plausible (1–32)

    Validation:
      nc*nr > 1: at least one block offset must be non-zero and within bounds.
      nc*nr == 1: single chunk — data starts directly at SChunkHeader+16.
    """
    limit = len(payload) - 20   # minimum: 16-byte header + at least 4 bytes
    for i in range(32, limit, 4):
        if struct.unpack_from('<I', payload, i)[0] != CHUNK_TYPE:
            continue
        nc = struct.unpack_from('<I', payload, i + 4)[0]
        nr = struct.unpack_from('<I', payload, i + 8)[0]
        if not (1 <= nc <= 32 and 1 <= nr <= 32):
            continue
        # Accept nc/nr within ±2 of expected.  The game sometimes pads to the
        # next even number, or a sprite declares height > n_rows*CHUNK_PX with
        # the extra rows being transparent (bottom rows beyond the grid).
        if (nc < max(1, n_cols_min - 2) or
                nr < max(1, n_rows_min - 2)):
            continue
        n_chunks = nc * nr
        if n_chunks == 1:
            # Single chunk: data starts directly at SChunkHeader+12 (no offset table)
            if i + 18 <= len(payload):   # need ≥ 6 bytes after 12-byte header
                return (i, nc, nr)
        else:
            offsets_start = i + 12       # SChunkHeader is 12 bytes: [type][nc][nr]
            if offsets_start + n_chunks * 4 > len(payload):
                continue
            # Each offset is self-relative from its own field position.
            # abs = (offsets_start + k*4) + entry_value
            for k in range(n_chunks):
                field_pos = offsets_start + k * 4
                off = struct.unpack_from('<I', payload, field_pos)[0]
                abs_pos = field_pos + off
                if 0 < abs_pos < len(payload):
                    return (i, nc, nr)   # found a valid table
    return None


# ──────────────────────────────────────────────────────────────────────────────
#  CHUNK DECOMPRESSOR  (faithful port of chunkcache.cpp ChunkDecompress ASM)
# ──────────────────────────────────────────────────────────────────────────────

def _decode_chunk(payload: bytes,
                  chunk_abs: int,
                  chunk_end: int,
                  pixels: bytearray,
                  stride: int,
                  x0: int, y0: int,
                  img_w: int, img_h: int) -> None:
    """
    Decode one compressed chunk and paint palette indices into `pixels`.

    Parameters
    ----------
    payload    : full i2d payload (needed for cross-chunk LZ back-references)
    chunk_abs  : absolute start of this chunk block in payload (incl. 4-byte ID)
    chunk_end  : exclusive end of chunk data in payload
    pixels     : flat bytearray, img_w × img_h palette indices
    stride     : == img_w
    x0, y0     : top-left pixel of this chunk on the canvas
    img_w/h    : canvas dimensions (for bounds checking)
    """
    if chunk_abs + 6 > len(payload):
        return

    chunk_end = min(chunk_end, len(payload))   # never read past payload end
    dl = payload[chunk_abs + 4]   # RLE escape byte
    dh = payload[chunk_abs + 5]   # LZ  escape byte
    i  = chunk_abs + 6            # absolute index into payload

    # Chunk-local 64×64 palette-index buffer (all 0 = transparent initially)
    chunk_buf = bytearray(CHUNK_PX * CHUNK_PX)
    di = 0    # linear output position in chunk_buf (0..4095)
    y  = 0    # row counter — incremented ONLY by EOL tokens (mirrors ASM ECX)
              # The encoder guarantees exactly CHUNKWIDTH pixels of output per
              # row before emitting EOL, so _put/_skip never need to wrap y.

    def _put(color: int) -> None:
        nonlocal di
        if di < CHUNK_PX * CHUNK_PX:
            chunk_buf[di] = color
        di += 1

    def _skip(n: int) -> None:
        nonlocal di
        di += n

    while i < chunk_end and y < CHUNK_PX:
        b = payload[i]; i += 1

        if b == dl:
            # ── RLE escape ────────────────────────────────────────────────
            if i >= chunk_end:
                break
            cmd = payload[i]; i += 1

            if cmd == 0:
                # EOL — sole row-counter advance (mirrors ASM 'dec ecx').
                # Pad di to the true next-row boundary in case a transparent
                # skip left us short (the encoder may omit trailing row skips).
                row_end = (y + 1) * CHUNK_PX
                if di < row_end:
                    di = row_end
                y += 1

            elif cmd & 0x80:
                # Transparent skip: advance output by (cmd & 0x7F) pixels
                _skip(cmd & 0x7F)

            else:
                # RLE run: write cmd copies of the next byte
                if i >= chunk_end:
                    break
                color = payload[i]; i += 1
                for _ in range(cmd):
                    _put(color)

        elif b == dh:
            # ── LZ back-reference ─────────────────────────────────────────
            # Token: [DH][count][dist_lo][dist_hi]   (4 bytes total)
            # Source is chunk_buf (decompressed output) at position di - dist - 4.
            # The -4 bias is confirmed by depy/RevenantRE.
            if i + 2 > chunk_end:
                i = min(i + 3, chunk_end)
                break
            count = payload[i];       i += 1
            dist  = payload[i] | (payload[i + 1] << 8); i += 2

            lz_src = di - dist - 4
            for k in range(count):
                src_val = chunk_buf[lz_src + k] if 0 <= lz_src + k < CHUNK_PX * CHUNK_PX else 0
                _put(src_val)

        else:
            # ── Raw pixel ─────────────────────────────────────────────────
            _put(b)

    # ── Copy non-zero chunk_buf pixels → canvas ──────────────────────────
    for cy in range(CHUNK_PX):
        py = y0 + cy
        if py >= img_h:
            break
        for cx in range(CHUNK_PX):
            px = x0 + cx
            if px >= img_w:
                break
            v = chunk_buf[cy * CHUNK_PX + cx]
            if v:
                pixels[py * stride + px] = v


# ──────────────────────────────────────────────────────────────────────────────
#  HDR_SIZE=84 (TBitmapData IMAGE LIST) DECODER
# ──────────────────────────────────────────────────────────────────────────────

def _decode_comp0(raw: bytes, width: int, height: int,
                  use_alpha: bool) -> Optional["Image"]:
    """
    Decode a hdr_size=84 CGSR sprite (TBitmapData image-list payload).

    Unlike compressed sprites (hdr_size>84) which embed TBitmapData fields
    in the CGSR header, these files have a minimal 84-byte CGSR header and
    store TBitmapData structures directly in the payload.

    TBitmapData layout (bitmapdata.h):
      +0…+68  metadata fields (width, height, flags, palette OFFSET, …)
      +72     data8[1]  ← pixel data starts here (raw or with embedded SChunkHeader)

    Two pixel-data formats are distinguished by TBitmapData.flags:
      flags & 0x4000 == 0  → raw 8-bit palette-indexed pixels (datasize = w×h)
      flags & 0x4000 == 1  → compressed: SChunkHeader type=5 at data8[0]
                              SChunkHeader: [type=5][n_cols][n_rows][unk] (16 bytes)
                              For n_chunks>1: offset table at data8[16..16+n_chunks*4]
                              For n_chunks=1: chunk data starts directly at data8[16]
                              Chunk offsets relative to ct_base = data8_start − 32.

    SPalette (1536 bytes) is located via self-relative OFFSET at TBitmapData+64:
      pal_abs = (TBitmapData_offset + 64) + uint32(TBitmapData+64)
    """
    from PIL import Image

    hdr_size = struct.unpack_from('<H', raw, 0x10)[0]
    payload   = raw[hdr_size:]

    # ── Find TBitmapData matching (width, height) ─────────────────────────────
    # Scan for int32 pair (width, height) at 4-byte aligned offsets.
    # Accept palsize=1536 (8-bit indexed) or palsize=0 with datasize=w*h*2
    # (16-bit BGR555 direct pixels, no embedded palette).
    # Some files store TBitmapData dimensions ±4 from the CGSR header dims
    # (due to sprite trimming); we try exact match first, then close match.
    fs: Optional[int] = None
    fs_mode: str = ''                  # '8bit' or '16bit'
    fs_w: int = width
    fs_h: int = height

    def _try_find(tol: int) -> None:
        nonlocal fs, fs_mode, fs_w, fs_h
        for i in range(0, len(payload) - 72, 4):
            w2 = struct.unpack_from('<i', payload, i    )[0]
            h2 = struct.unpack_from('<i', payload, i + 4)[0]
            if abs(w2 - width) > tol or abs(h2 - height) > tol:
                continue
            if w2 <= 0 or h2 <= 0:
                continue
            palsize  = struct.unpack_from('<I', payload, i + 60)[0]
            datasize = struct.unpack_from('<I', payload, i + 68)[0]
            if palsize == 1536 and 0 < datasize < len(payload):
                fs = i; fs_mode = '8bit'; fs_w = w2; fs_h = h2; return
            if palsize == 0 and datasize == w2 * h2 * 2 and i + 72 + datasize <= len(payload):
                fs = i; fs_mode = '16bit'; fs_w = w2; fs_h = h2; return

    _try_find(0)               # exact match first
    if fs is None:
        _try_find(4)           # allow up to ±4px difference in each dimension
    if fs is None:
        return None

    flags    = struct.unpack_from('<I', payload, fs + 16)[0]
    datasize = struct.unpack_from('<I', payload, fs + 68)[0]
    data8_start = fs + 72

    # ── 16-bit X1R5G5B5 direct pixels (no palette) ───────────────────────────
    if fs_mode == '16bit':
        px_data = payload[data8_start: data8_start + datasize]
        img     = Image.new('RGBA', (fs_w, fs_h), (0, 0, 0, 0))
        px_load = img.load()
        for y in range(fs_h):
            for x in range(fs_w):
                word = struct.unpack_from('<H', px_data, (y * fs_w + x) * 2)[0]
                r = ((word >> 10) & 0x1F) << 3   # R in HIGH bits (14-10)
                g = ((word >>  5) & 0x1F) << 3   # G in MID  bits  (9-5)
                b = ( word        & 0x1F) << 3   # B in LOW  bits  (4-0)
                a = 0 if word == 0 else 255
                if not use_alpha:
                    a = 255
                px_load[x, y] = (r, g, b, a)
        # Crop/pad to declared CGSR dimensions
        return img.crop((0, 0, width, height))

    pal_rel  = struct.unpack_from('<I', payload, fs + 64)[0]
    pal_abs  = (fs + 64) + pal_rel
    if pal_abs + 512 > len(payload):
        return None

    pal_flat = _bgr555_to_rgb888(payload[pal_abs: pal_abs + 512])  # X1R5G5B5
    rgba_pal = _make_rgba_palette(pal_flat)

    if flags & 0x4000:
        # ── Compressed: SChunkHeader type=5 embedded at data8[0] ─────────────
        # SChunkHeader layout in data8:
        #   [0:4]  type=5, [4:8] n_cols, [8:12] n_rows
        #   [12:]  for n_chunks>1: offset table (n_chunks uint32 self-relative offsets)
        #          for n_chunks=1: chunk data starts here directly

        n_cols   = (fs_w + CHUNK_PX - 1) // CHUNK_PX
        n_rows   = (fs_h + CHUNK_PX - 1) // CHUNK_PX
        n_chunks = n_cols * n_rows

        canvas_w = n_cols * CHUNK_PX
        canvas_h = n_rows * CHUNK_PX
        pixels   = bytearray(canvas_w * canvas_h)

        if n_chunks == 1:
            # Single chunk: data starts at data8[12] (no offset table entry)
            chunk_abs = data8_start + 12
            chunk_end = data8_start + datasize
            if chunk_abs + 6 <= len(payload):
                _decode_chunk(payload, chunk_abs, chunk_end,
                              pixels, canvas_w, 0, 0, canvas_w, canvas_h)
        else:
            # Multi-chunk: offset table at data8[12..12+n_chunks*4]
            # Each entry is SELF-RELATIVE: abs = field_position + entry_value
            offsets_start = data8_start + 12      # in payload coords

            offsets = [
                struct.unpack_from('<I', payload, offsets_start + k * 4)[0]
                for k in range(n_chunks)
            ]

            for idx, off in enumerate(offsets):
                if off == 0:
                    continue
                col = idx % n_cols
                row = idx // n_cols
                field_pos = offsets_start + idx * 4
                abs_off   = field_pos + off
                if abs_off < 0 or abs_off + 6 >= len(payload):
                    continue
                chunk_end = len(payload)
                for next_idx in range(idx + 1, n_chunks):
                    next_field = offsets_start + next_idx * 4
                    next_off   = offsets[next_idx]
                    if next_off > 0:
                        cand = next_field + next_off
                        if cand > abs_off:
                            chunk_end = cand
                            break
                _decode_chunk(payload, abs_off, chunk_end,
                              pixels, canvas_w,
                              col * CHUNK_PX, row * CHUNK_PX,
                              canvas_w, canvas_h)

        out     = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
        px_load = out.load()
        for py in range(canvas_h):
            for px in range(canvas_w):
                r, g, b, a = rgba_pal[pixels[py * canvas_w + px]]
                if not use_alpha:
                    a = 255
                px_load[px, py] = (r, g, b, a)
        return out.crop((0, 0, width, height))

    else:
        # ── Uncompressed: raw 8-bit indexed pixels ────────────────────────────
        if data8_start + datasize > len(payload):
            return None
        px_data = payload[data8_start: data8_start + datasize]

        img     = Image.new('RGBA', (fs_w, fs_h), (0, 0, 0, 0))
        px_load = img.load()
        for y in range(fs_h):
            for x in range(fs_w):
                idx = y * fs_w + x
                if idx >= len(px_data):
                    break
                r, g, b, a = rgba_pal[px_data[idx]]
                if not use_alpha:
                    a = 255
                px_load[x, y] = (r, g, b, a)
        # Crop/pad to declared CGSR dimensions
        return img.crop((0, 0, width, height))


# ──────────────────────────────────────────────────────────────────────────────
#  PUBLIC API
# ──────────────────────────────────────────────────────────────────────────────

def decode_i2d(path: Path, use_alpha: bool = True) -> Optional["Image"]:
    """
    Decode a CGSR .i2d file and return a PIL RGBA Image, or None on failure.

    Parameters
    ----------
    path      : path to the .i2d file
    use_alpha : if True, index 0 → transparent; else all pixels fully opaque
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

    hdr_size  = struct.unpack_from('<H', raw, 0x10)[0]
    width     = struct.unpack_from('<H', raw, 0x48)[0]
    height    = struct.unpack_from('<H', raw, 0x4A)[0]
    if width == 0 or height == 0 or hdr_size >= len(raw):
        return None

    # ── hdr_size=84: try TBitmapData image-list format first ───────────────
    # Some hdr_size=84 files store TBitmapData structs in the payload;
    # others are standard compressed sprites with a SChunkHeader.
    # Try _decode_comp0 first; if it returns None, fall through to the
    # standard SChunkHeader decoder below.
    if hdr_size == 84:
        result = _decode_comp0(raw, width, height, use_alpha)
        if result is not None:
            return result
        # Fall through: try standard compressed decoder

    payload = raw[hdr_size:]

    n_cols_min = (width  + CHUNK_PX - 1) // CHUNK_PX
    n_rows_min = (height + CHUNK_PX - 1) // CHUNK_PX

    # ── Locate SChunkHeader (type=5 scan) ───────────────────────────────────
    result_ct = _find_chunk_table(payload, n_cols_min, n_rows_min)
    if result_ct is None:
        # No SChunkHeader found — try TBitmapData decoder as final fallback.
        # This handles larger-hdr_size files whose payloads use TBitmapData
        # rather than the standard chunked-compressed format.
        return _decode_comp0(raw, width, height, use_alpha)

    ct_type_off, n_cols, n_rows = result_ct   # use ACTUAL stored grid dims
    n_chunks      = n_cols * n_rows
    # SChunkHeader is 12 bytes: [type(4)][nc(4)][nr(4)]
    # Offset table starts immediately after at ct_type_off+12.
    # Each entry is SELF-RELATIVE: abs = field_position + entry_value
    offsets_start = ct_type_off + 12          # block[0] field starts here

    # ── Load palette ─────────────────────────────────────────────────────────
    pal_flat  = _load_palette(path, payload, ct_type_off)
    rgba_pal  = _make_rgba_palette(pal_flat)

    # ── Allocate palette-index canvas ────────────────────────────────────────
    canvas_w = n_cols * CHUNK_PX
    canvas_h = n_rows * CHUNK_PX
    pixels   = bytearray(canvas_w * canvas_h)    # all 0 = transparent

    # ── Decode each chunk ────────────────────────────────────────────────────
    if n_chunks == 1:
        # Single chunk: data starts directly at SChunkHeader+12 (no offset table)
        chunk_abs = offsets_start          # = ct_type_off + 12
        _decode_chunk(payload, chunk_abs, len(payload),
                      pixels, canvas_w, 0, 0, canvas_w, canvas_h)
    else:
        if offsets_start + n_chunks * 4 > len(payload):
            return None

        offsets = [
            struct.unpack_from('<I', payload, offsets_start + k * 4)[0]
            for k in range(n_chunks)
        ]

        for idx, off in enumerate(offsets):
            if off == 0:
                continue                         # empty / transparent tile
            col = idx % n_cols
            row = idx // n_cols
            # Self-relative: abs = field_position + entry_value
            field_pos = offsets_start + idx * 4
            abs_off   = field_pos + off
            if abs_off < 0 or abs_off + 6 >= len(payload):
                continue

            # Determine chunk data end: next non-zero chunk's abs position
            chunk_end = len(payload)
            for next_idx in range(idx + 1, n_chunks):
                next_field = offsets_start + next_idx * 4
                next_off   = offsets[next_idx]
                if next_off > 0:
                    cand = next_field + next_off
                    if cand > abs_off:
                        chunk_end = cand
                        break

            _decode_chunk(
                payload, abs_off, chunk_end,
                pixels, canvas_w,
                col * CHUNK_PX, row * CHUNK_PX,
                canvas_w, canvas_h
            )

    # ── Convert palette-index canvas → RGBA image ────────────────────────────
    out      = Image.new('RGBA', (canvas_w, canvas_h), (0, 0, 0, 0))
    px_data  = out.load()
    for py in range(canvas_h):
        for px in range(canvas_w):
            idx8     = pixels[py * canvas_w + px]
            r, g, b, a = rgba_pal[idx8]
            if not use_alpha:
                a = 255
            px_data[px, py] = (r, g, b, a)

    # Crop to declared sprite dimensions (PIL fills out-of-bounds with transparent)
    return out.crop((0, 0, width, height))


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
        n_cols_min = (width  + CHUNK_PX - 1) // CHUNK_PX
        n_rows_min = (height + CHUNK_PX - 1) // CHUNK_PX
        payload    = raw[hdr_size:]
        ct_result  = _find_chunk_table(payload, n_cols_min, n_rows_min)
        n_cols     = ct_result[1] if ct_result else n_cols_min
        n_rows     = ct_result[2] if ct_result else n_rows_min
        return {
            'width':    width,
            'height':   height,
            'x_offset': x_off,
            'y_offset': y_off,
            'pix_fmt':  hex(pix_fmt),
            'n_chunks': n_cols * n_rows,
            'n_cols':   n_cols,
            'n_rows':   n_rows,
            'ct_found': ct_result is not None,
            'file_size': len(raw),
        }
    except Exception:
        return {}
