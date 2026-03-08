# Revenant Reverse Engineering Log

> **Purpose:** This document is the authoritative technical record of the RevEngine project.
> It must be updated every time new code is written or a new discovery is made.
> It is written so the entire project can be reconstructed from this document alone
> if all source code is lost.
>
> **Git history:** 5 commits, all on 2026-03-08 by chrisdev1187
> (christiaanbothma47@gmail.com). Full day of research + iteration.

---

## Project Overview

**Game:** Revenant (1999) by Cinematix Studios / Eidos Interactive
**Platform:** Windows 95/98, DirectDraw 7 / Direct3D 7
**Goal:** Reverse-engineer the game's proprietary asset formats and build a complete
asset extraction, decoding, and visualization system in Python.

### Final Asset Counts (as scanned by the tool at runtime)

| Asset type | Count |
|------------|-------|
| i3d 3D models | 612 |
| i2d sprites (browseable) | 5,500+ |
| Characters (char.def) | 60 |
| Weapons (weapon.def) | 60 |
| Armour pieces (armor.def) | 207 |
| Spells (spell.def) | 74 |
| Automap tiles (Zone 0) | 750 (25×60 grid, 1600×3840 px stitched) |
| Character portraits | 4 playable (100×100 RGB BMP) |
| Equipment thumbnails | 141 .tn files in Thumbnails/Equip/ |

### Directory Layout

```
C:/GOG Games/Revenant/
├── Revenant.exe             ← Game executable
├── *.rvr                    ← Resource archives (ZIP)
├── *.rvi                    ← Imagery archives (ZIP)
├── *.rvm / Modules/*.rvm    ← Map/module archives (ZIP)
├── _extracted/              ← Output from archive_extractor.py / setup.py
│   ├── imagery/             ← Extracted from imagery.rvi
│   │   ├── Imagery/         ← .i2d sprites, .i3d models, .bmp files
│   │   │   ├── Forest/
│   │   │   ├── Town/
│   │   │   ├── Dungeon/
│   │   │   ├── Cave/
│   │   │   ├── Keep/
│   │   │   ├── KeepInt/
│   │   │   ├── Ruin/
│   │   │   ├── Labyrnth/
│   │   │   ├── TownInt/
│   │   │   ├── Misc/
│   │   │   ├── Chars/       ← Character .i3d + portrait .bmp files
│   │   │   ├── Equip/       ← Equipment .i2d sprites
│   │   │   └── char.def, weapon.def, armor.def
│   │   └── Thumbnails/      ← .tn palette/thumbnail files
│   │       ├── Forest/
│   │       ├── Equip/       ← 141 equipment thumbnails
│   │       └── ...
│   ├── resources/           ← Extracted from resources.rvr
│   │   └── spell.def
│   └── Ahkuilon/            ← Extracted from Ahkuilon.rvm
│       ├── Map/             ← X_Y_Z.DAT map chunks (9,722 chunks)
│       └── Automaps/        ← Zone_Y_X.bmp automap tiles
└── RevEngine/               ← Our project directory
    ├── REVENANT_REVERSE_ENGINEERING.md   ← THIS FILE
    ├── archive_extractor.py
    ├── cgsr_decoder.py       ← Early prototype (superseded)
    ├── asset_studio.py       ← Main GUI — 7 tabs, 1959 lines
    ├── map_parser.py
    ├── test_tn.py
    ├── texture_extractor_guide.md
    ├── requirements.txt      ← Pillow, numpy
    ├── setup.py              ← One-shot installer + extractor
    ├── test_renders/         ← PNG test output + pre-rendered maps
    └── decoders/
        ├── __init__.py
        ├── cgsr.py           ← Refined CGSR header + i3d parser
        └── i2d.py            ← Full sprite decoder (primary, 321 lines)
```

---

## Game Format Research

### Archive Formats

All three Revenant archive types are **standard ZIP files with renamed extensions**.
No custom compression, no encryption. Open directly with Python `zipfile`.

| Extension | Description | Default location |
|-----------|-------------|-----------------|
| `.rvr`    | Resources archive (scripts, .def files) | Game root |
| `.rvi`    | Imagery archive (.i2d, .i3d, .bmp, .tn) | Game root |
| `.rvm`    | Map/module archive (map chunks, automaps) | `Modules/` |

---

### CGSR File Format — Overview

All game graphics use the proprietary **CGSR** container.
Magic bytes: `CGSR` (0x43 0x47 0x53 0x52).

| Extension | Content | type_byte |
|-----------|---------|-----------|
| `.i2d`    | 2D sprite / texture | 0x01 |
| `.i3d`    | 3D model + animations | 0x00 |

---

### CGSR Header — 84 bytes (0x54)

| Offset | Size | Type | Field | Notes |
|--------|------|------|-------|-------|
| 0x00   | 4    | bytes | magic | `CGSR` |
| 0x04   | 1    | uint8 | type_byte | 0x01=2D, 0x00=3D |
| 0x05   | 1    | uint8 | *(pad)* | always 0x00 |
| 0x06   | 1    | uint8 | *(pad)* | always 0x00 |
| 0x07   | 1    | uint8 | version | always 0x01 |
| 0x08   | 4    | uint32 LE | data_size | bytes after header |
| 0x0C   | 4    | uint32 LE | uncompressed_size | |
| 0x10   | 2    | uint16 LE | header_size | = 0x54 = 84 |
| 0x12   | 2    | uint16 LE | flags | |
| 0x14   | 4    | uint32 LE | sub_type | render flags |
| 0x18   | 4    | uint32 LE | state_count | anim states (i3d) / 1 (i2d) |
| 0x1C   | 36   | char[] | state_name | null-terminated, padded to 36 |
| 0x40   | 4    | uint32 LE | bounds_type | always 2 in tested files |
| 0x44   | 4    | uint32 LE | bounds_pad | always 0 |
| 0x48   | 2    | uint16 LE | width | pixels |
| 0x4A   | 2    | uint16 LE | height | pixels |
| 0x4C   | 2    | uint16 LE | x_offset | world-space anchor |
| 0x4E   | 2    | uint16 LE | y_offset | world-space anchor |
| 0x50   | 4    | uint32 LE | pixel_flags | **runtime DirectDraw surface flags — NOT a file offset** |

> **CRITICAL WARNING:** The value at 0x50 (e.g. `0x2088`, `0x1400`) is a DirectDraw 7
> surface capability bitmask written by the game engine at runtime. Early analysis
> mistakenly treated this as a pixel data offset — it is NOT. Never seek to this value.

**Payload starts at offset 0x54 (84). All .i2d / .i3d data follows immediately.**

---

### `.i2d` Sprite Format — Full Specification

`.i2d` files use two different payload formats depending on the CGSR header size.
Most files use **SChunkHeader compressed chunks** with an **8-bit paletted** pixel format.
Some files (especially equipment sprites) use a **TBitmapData image-list** payload.
A few files use **16-bit BGR555 direct pixels** (shadow overlays, stain textures).

#### Two Payload Formats

| `hdr_size` | Discriminator | Pixel data |
|------------|---------------|------------|
| Any (≥84)  | SChunkHeader type=5 found in payload | 8-bit indexed, RLE+LZ compressed |
| Any (≥84)  | SChunkHeader NOT found; TBitmapData found; `flags & 0x4000 == 0` | 8-bit indexed, uncompressed |
| Any (≥84)  | SChunkHeader NOT found; TBitmapData found; `flags & 0x4000 != 0` | 8-bit indexed, compressed (embedded SChunkHeader) |
| Any (≥84)  | TBitmapData found; `palsize == 0` and `datasize == w*h*2` | 16-bit BGR555 direct |

**Decode priority:**
1. If `hdr_size == 84`: try TBitmapData decoder first; if it returns None, fall through.
2. Scan for SChunkHeader in payload.
3. If SChunkHeader not found: try TBitmapData decoder as final fallback.

#### Palette Source

Priority order for palette resolution:
1. **Embedded SPalette** at `payload[pal_field + pal_rel]` — self-relative OFFSET.
   In standard SChunkHeader format: `pal_field = ct_type_off - 8`.
   In TBitmapData format: `pal_field = (TBitmapData_offset + 64)`.
   SPalette is 1536 bytes: `[0:512]` = 256 × uint16 LE **X1R5G5B5**, `[512:1536]` = 256 × uint32 ARGB32.
   Only the first 512 bytes are used for decoding.
2. **Same-directory `.TN` / `.tn` file** alongside the `.i2d` (first 512 bytes = X1R5G5B5)
3. **Thumbnails sibling directory** `.tn` file matching the `.i2d` stem (first 512 bytes)
4. **Windows VGA 16-colour + grayscale ramp** (last resort)

**X1R5G5B5 → RGB888 (DirectDraw RGB555):**
`R = ((word>>10) & 0x1F)<<3`,  `G = ((word>>5) & 0x1F)<<3`,  `B = (word & 0x1F)<<3`
(R in HIGH bits 14-10, G in MID bits 9-5, B in LOW bits 4-0. Confirmed empirically via comparison renders.)
**Palette index 0 = transparent (alpha=0) in all formats.**

#### Chunk Grid Layout

The canvas is divided into **64×64 pixel tiles** (chunks):
```
CHUNK_PX = 64
n_cols   = actual value from SChunkHeader (may differ from ceil(width/64) by ±2)
n_rows   = actual value from SChunkHeader (may differ from ceil(height/64) by ±2)
n_chunks = n_cols × n_rows
```
Canvas is `n_cols × 64` wide, `n_rows × 64` tall; final image is cropped to `(width, height)`.
PIL's `crop()` fills out-of-bounds regions with transparent (0,0,0,0) automatically.

**IMPORTANT:** The SChunkHeader n_cols/n_rows is NOT always `ceil(width/64)`.
Some files pad to the next even number or the next power of 2. Some files store
n_cols/n_rows SMALLER than `ceil(width/64)` (in which case the sprite is
effectively clipped at `n_cols*64` pixels width, with remaining pixels transparent).
Always use the values FROM the SChunkHeader, not computed from width/height.

#### Chunk Table Location (SChunkHeader)

The chunk table is NOT at a fixed offset. Must be located by scanning the payload:

```
Scan payload starting at offset 32, step 4 bytes:
  Look for: [uint32 = 5] [uint32 = nc] [uint32 = nr]
  Accept if: nc >= max(1, ceil(width/64) - 2) AND nr >= max(1, ceil(height/64) - 2)
  AND 1 <= nc, nr <= 32

When found at position i (ct_type_off = i):
  ct_base       = i - 32        (32 bytes of pre-header before the type=5 field)
  offsets_start = i + 16        (type[4] + n_cols[4] + n_rows[4] + table_sz[4])

Returns: (ct_type_off, nc, nr) — use stored nc/nr for canvas allocation
```

**Single-chunk special case (nc*nr == 1):**
No offset table entry. Chunk data starts DIRECTLY at SChunkHeader+16.
The bytes at `offsets_start` are the first 4 bytes of chunk data (cache ID),
NOT an offset pointer. This is a special encoding chosen when the sprite fits
in a single 64×64 tile.

**Multi-chunk validation:**
After finding the `[5, nc, nr]` pattern with nc*nr > 1, verify that at least one of the
nc*nr uint32 offsets at `offsets_start` is non-zero AND less than `len(payload) - ct_base`.
Without this check, bogus `[5,1,1]` patterns in unrelated data produce empty output.

#### Chunk Offset Table

After `offsets_start` (multi-chunk only): `n_chunks` × uint32 LE values.
Each value is an offset **relative to `ct_base`** (the 32-byte pre-header position).

```
off = offsets[idx]
if off == 0:
    → skip (empty/transparent chunk, leave pixels as 0)
abs_off = ct_base + off         ← byte position in payload
```

Chunk data size: determined by the next non-zero offset in the table, minus current.
Last chunk: extends to end of payload (clamped with `min(chunk_end, len(payload))`).

#### TBitmapData Image-List Format

Used when no SChunkHeader is present (or for `hdr_size=84` files as first path).
**TBitmapData struct** (72-byte header at a 4-byte aligned position in payload):

| Offset | Size | Field | Notes |
|--------|------|-------|-------|
| +0     | 4    | width (int32) | Matches CGSR header (±4px tolerance) |
| +4     | 4    | height (int32) | Matches CGSR header (±4px tolerance) |
| +16    | 4    | flags (uint32) | `& 0x4000` → compressed data in data8; else raw 8-bit pixels |
| +60    | 4    | palsize (uint32) | 1536 = embedded SPalette; 0 = no palette (16-bit pixels) |
| +64    | 4    | pal_rel (uint32) | Self-relative OFFSET to SPalette: `pal_abs = (fs+64) + pal_rel` |
| +68    | 4    | datasize (uint32) | Pixel data size; `== w*h` for 8-bit uncompressed, `== w*h*2` for 16-bit |
| +72    | var  | data8[] | Pixel data (8-bit indexed or 16-bit BGR555 or embedded SChunkHeader) |

**Scan algorithm:**
```python
for i in range(0, len(payload) - 72, 4):
    w2, h2 = unpack('<ii', payload[i:i+8])
    if abs(w2 - width) <= 4 and abs(h2 - height) <= 4 and w2 > 0 and h2 > 0:
        palsize  = unpack('<I', payload[i+60:i+64])[0]
        datasize = unpack('<I', payload[i+68:i+72])[0]
        if palsize == 1536 and 0 < datasize < len(payload):
            # 8-bit indexed; check flags for compressed vs raw
        if palsize == 0 and datasize == w2 * h2 * 2:
            # 16-bit BGR555 direct pixels
```

**Compressed TBitmapData** (flags & 0x4000):
data8 starts with an embedded SChunkHeader [type=5][nc][nr][unk].
- If nc*nr == 1: chunk data starts at data8[16] directly (same single-chunk special case)
- If nc*nr > 1: offset table at data8[16:], `ct_base = data8_start - 32`

#### Chunk RLE Compression Format

Each chunk block layout:
```
chunk_abs + 0-3: 4-byte cache ID (ignored by decoder)
chunk_abs + 4:   DL  (RLE escape byte — value varies per chunk)
chunk_abs + 5:   DH  (LZ  escape byte — value varies per chunk)
chunk_abs + 6..: compressed pixel stream
```

Pixel stream (decodes into a local 64×64 chunk_buf; advance left→right, wrap at x≥64):
```
byte b:
  b == DL  →  RLE escape:
                cmd = next byte
                if cmd == 0x00:
                  → EOL: y += 1, x = 0
                elif cmd & 0x80:
                  → transparent skip: advance x by (cmd & 0x7F)
                else:
                  count = cmd; color = next byte
                  → paint `count` copies of palette index `color`
  b == DH  →  LZ back-reference (4-byte token):
                count = next byte
                dist  = uint16_LE(next 2 bytes)
                p_dh  = absolute position of DH byte in payload
                src   = p_dh - dist
                → copy `count` bytes from payload[src..src+count] into chunk_buf
  else     →  literal pixel: paint 1 pixel with palette index b
```

After decoding, non-zero pixels from chunk_buf are copied to the canvas.
`chunk_end = min(chunk_end, len(payload))` must be clamped to avoid IndexError.

#### Full Decode Procedure

```python
# 1. Parse header (84 bytes)
width  = struct.unpack_from('<H', raw, 0x48)[0]
height = struct.unpack_from('<H', raw, 0x4A)[0]
hdr_sz = struct.unpack_from('<H', raw, 0x10)[0]   # = 84
payload = raw[hdr_sz:]

# 2. Attempt TBitmapData path first (hdr_sz==84 or as fallback for any size)
result = decode_comp0(raw, width, height)
if result is not None:
    return result   # Done — TBitmapData decoded successfully

# 3. Find chunk table (validated scanner — may differ from ceil(dim/64) by ±2)
n_cols_min = (width  + 63) // 64
n_rows_min = (height + 63) // 64
found = find_chunk_table(payload, n_cols_min, n_rows_min)
if found is None:
    return None
ct_type_off, n_cols, n_rows = found   # ← use STORED dims, not computed
ct_base     = ct_type_off - 32
n_chunks    = n_cols * n_rows

# 4. Load palette from embedded SPalette (8 bytes before ct_type_off)
rgba_pal = load_palette(payload, ct_type_off, path)

# 5. Allocate canvas (palette indices, 0 = transparent)
canvas_w = n_cols * 64
canvas_h = n_rows * 64
pixels = bytearray(canvas_w * canvas_h)

# 6. Decode each chunk into canvas
if n_chunks == 1:
    # Single chunk: data starts directly at SChunkHeader+16 (no offset table)
    decode_chunk(payload, ct_type_off + 16, len(payload),
                 pixels, canvas_w, 0, 0, canvas_w, canvas_h)
else:
    offsets_start = ct_type_off + 16
    offsets = [struct.unpack_from('<I', payload, offsets_start + k*4)[0]
               for k in range(n_chunks)]
    for idx, off in enumerate(offsets):
        if off == 0: continue
        col, row = idx % n_cols, idx // n_cols
        abs_off  = ct_base + off
        # chunk_end = next non-zero offset (or payload end)
        chunk_end = len(payload) - ct_base
        for nxt in offsets[idx + 1:]:
            if 0 < nxt <= len(payload): chunk_end = nxt; break
        decode_chunk(payload, abs_off, ct_base + chunk_end,
                     pixels, canvas_w, col*64, row*64, canvas_w, canvas_h)

# 7. Apply palette → RGBA, crop to actual dimensions
out = Image.new('RGBA', (canvas_w, canvas_h), (0,0,0,0))
# ... apply rgba_pal[pixels[...]] for each pixel ...
out = out.crop((0, 0, width, height))
```

---

### `.tn` File Format

- **Size:** Exactly 768 bytes
- **Format:** Raw binary, no header.
  - **Bytes 0–511:** 256 × uint16 LE **X1R5G5B5** — the 256-colour sprite palette
    (`SPalette.colors[]`). R in bits 14-10, G in bits 9-5, B in bits 4-0.
  - **Bytes 512–767:** ARGB/thumbnail index data (not used for palette decoding).
- **Palette use:** Only the first **512 bytes** are read for `.i2d` decoding (decoded as X1R5G5B5).
- **Thumbnail use:** The full 768 bytes are re-interpreted as `Image.frombytes('RGB', (16,16), data)`
  for the 16×16 thumbnail grid (this is a visual approximation — the bytes aren't true RGB888).
- **Location:** `_extracted/imagery/Thumbnails/<Category>/` matching `.i2d` stem name.
- **Windows gotcha:** On Windows, `glob("*.tn")` and `glob("*.TN")` both match the
  same file (case-insensitive FS), causing duplicates. Must use `iterdir()` with a
  `seen` set keyed on `f.stem.lower()` to deduplicate.

---

### `.i3d` 3D Model Format

`.i3d` files store 3D character/object models with named animation states.
Geometry decoding (vertices, faces, UVs) is **not yet implemented**.

#### Animation State Table

Immediately follows the 84-byte header (payload offset 0).
Number of entries = `state_count` from header offset 0x18.

**Each entry: 76 bytes**
```
[0x00 - 0x13]  20 bytes  : flags / transition data (not fully decoded)
[0x14 - 0x4B]  56 bytes  : null-terminated state name, zero-padded
```

Known state name examples: `still`, `start`, `walk`, `run`, `attack`,
`die`, `turn`, `block`, `cast`, `hit`, `jump`

#### Geometry Section

Immediately after animation state table:
```
geom_file_offset = 84 + (state_count × 76)
```

First 12 bytes of geometry section:
```
h0, h1, h2 = struct.unpack('<III', geom_data)
```
Empirically, `h1` (second uint32) approximates vertex count.

Full geometry format (vertices/faces/UVs) still needs reverse engineering.

---

### MAP Chunk Format

Files named `X_Y_Z.DAT` where X, Y = world grid coords, Z = vertical layer.

| Offset | Size | Description |
|--------|------|-------------|
| 0x00   | 4    | Magic = `MAP ` (0x4D 0x41 0x50 0x20) |
| 0x04   | 4    | uint32 LE: format version |
| 0x08   | 2    | uint16 LE: unknown flags |
| 0x0A   | 2    | uint16 LE: tile count or flags |
| 0x10+  | var  | Chunk data (not yet decoded) |

**World stats (Ahkuilon):** 9,722 total chunks, world spans 67×32 chunk area.

---

### Automap Tile Format

- **Path:** `_extracted/Ahkuilon/Automaps/`
- **Filename:** `Zone_Y_X.bmp` — standard Windows BMP
- **Tile size:** 64×64 px (resizable in viewer)
- **Zone 0 (Ahkuilon main):** 750 tiles, 25×60 grid → stitched = **1600×3840 px**
- **Y coordinates are signed.** `0_-10_25.bmp` = zone 0, row -10, col 25.
  Originally broken because `.isdigit()` rejects negative numbers. Fixed in commit 2
  by replacing with `int()` + try/except.
- **Stitching:** Normalize both axes: `col = x_val - min_x`, `row = y_val - min_y`

---

### Script / Data Definition Files (.def)

Plain text, `latin-1` encoding, block-structured:

```
CHARACTER "Goblin"
BEGIN
  CLASS   "Humanoid"
  GROUPS  "Enemies,Monsters"
  ENEMIES "Player"
  SIGHT   5, 10, 180
  BLOCK   25
  WEAPONDAMAGE  8
  ATTACK  ...
  IMPACT  ...
END
```

| File | Location | Content |
|------|----------|---------|
| `char.def` | `imagery/` | 60 characters: CLASS, GROUPS, SIGHT, BLOCK, WEAPONDAMAGE, ATTACK, IMPACT |
| `weapon.def` | `imagery/` | 60 weapons: BASICMODS (slot, type, dmg, combining, poison, value, dmgmod, minstr) |
| `armor.def` | `imagery/` | 207 armour: BASICMODS (slot, protection, combining, resist_psn, stealth, value, minstr, mincon) |
| `spell.def` | `resources/` | 74 spells: MANA, DAMAGE, DURATION, DESCRIPTION |

WEAPON_TYPE map: `{0:"Hand/Claw", 1:"Knife/Dagger", 2:"Sword", 3:"Bludgeon", 4:"Axe", 5:"Staff/Polearm", 6:"Bow", 7:"Crossbow"}`

ARMOR_SLOT map: `{2:"Chest", 3:"Head", 4:"Weapon", 5:"Shield", 6:"Gauntlet", 7:"Ring1", 8:"Ring2", 9:"Legs", 10:"Boots", 11:"Amulet"}`

---

## Reverse Engineering Discoveries

### Discovery 1: Archives are Plain ZIPs
`.rvr`, `.rvi`, `.rvm` open directly with Python `zipfile`. No custom decompression.

### Discovery 2: CGSR Header = Fixed 84 bytes
`header_size` field at 0x10 always reads `0x54`. Payload always at byte 84.

### Discovery 3: pixel_flags at 0x50 is NOT a File Offset
Value at 0x50 (e.g. `0x2088`, `0x1400`) looks like a small number and was initially
mistaken for a pixel data seek offset. It is a DirectDraw 7 surface capability bitmask
stored by the runtime. Using it as a seek position produces garbage or crashes.

### Discovery 4: Pixel Format is 8-bit Paletted, NOT 16-bit Direct Color
Early attempts used RGB565 and ARGB1555 (standard for late-90s D3D). All produced
noise. The actual format is 8-bit palette indices. The palette is stored externally
in `.tn` files, not embedded in the `.i2d` file itself.

### Discovery 5: .tn Files are Palettes AND Thumbnails
A `.tn` file (768 bytes) has dual purpose:
- **Bytes 0–511 (X1R5G5B5):** 256 × uint16 LE palette → decoded as R=bits14-10, G=bits9-5, B=bits4-0
- **Thumbnail:** All 768 bytes re-interpreted as `Image.frombytes('RGB', (16,16), data)` for
  a rough 16×16 preview grid (not accurate RGB88, but acceptable for thumbnails)

### Discovery 6: Chunk Table NOT at Fixed Offset
The chunk table must be found by scanning for the `[5, n_cols, n_rows]` signature.
There is a 32-byte pre-header before the type=5 field; `ct_base = type_field_pos - 32`
is the base from which all chunk offsets are relative.

### Discovery 7: DL + 0xC0 = Skip to Next Row (not a count)
In the RLE stream, `DL` followed by `0xC0` means "advance to the start of the next
row" — NOT a (count=192, color=next) run. Without this special case, sprites render
with massive horizontal smearing.

### Discovery 8: Chunk Table Has ~130 False Positives Without Validation
The pattern `[5, 1, 1]` (type=5, 1 col, 1 row) appears in random binary data.
Validating that at least one offset is non-zero AND within payload bounds eliminates
all false positives and causes those sprites to correctly return `None`.
Discovered after noticing many single-chunk sprites producing zero-pixel canvases.

### Discovery 9: Automap Y-Coordinates Are Signed
Tile filenames like `0_-10_25.bmp` have negative Y values. Python's `.isdigit()`
returns `False` for `-10`, breaking the zone stitcher (produced a 64px image instead
of 1600×3840). Fixed with `int()` + try/except. Zone 0 stitches to 750 tiles.

### Discovery 10: Windows glob() Duplicates .tn Files
On Windows (case-insensitive filesystem), scanning with both `glob("*.tn")` and
`glob("*.TN")` returns the same file twice. This caused duplicate sprites in the
browser grid and doubled loading time. Fixed by using `iterdir()` with a
`seen: set[str]` keyed on `f.stem.lower()`.

### Discovery 11: i2d Lookup Was O(n²)
Original SpritesTab code called `iterdir()` for every sprite to find its `.i2d`
companion. For 5,500+ sprites this is extremely slow. Fixed by building a
`stem.lower() → Path` dict once per category load (O(n)), then doing O(1) lookups.

### Discovery 12: i3d Animation State Entry = 76 bytes, Name at Byte 20
Each animation state entry in the `.i3d` payload is exactly 76 bytes.
The state name (null-terminated ASCII) starts at byte 20 within the entry.
The preceding 20 bytes contain flags and transition data not yet decoded.

### Discovery 13: i3d Geometry Stride Detection (Heuristic)
The geometry section begins with 3 uint32 values (h0, h1=vertex_count, h2).
h2 is either an index count or face count. By trying both interpretations
(h2 × 2 bytes for raw indices, or h2 × 6 bytes for faces as triplets of uint16)
and checking if the remaining bytes divide evenly by vertex_count into a "nice"
stride (12, 16, 20, 24, 28, 32, 36, 40, 48), the correct vertex layout can often
be detected automatically. Fallback: assume stride=32 (most common D3D7 FVF).

### Discovery 14: LZ Back-Reference Format (Confirmed from ChunkDecompress ASM)
The DH escape in `.i2d` chunk compression initiates a **4-byte token** (DH + 3 bytes):
- `count` (1 byte) — number of bytes to copy (1–255)
- `dist` (2 bytes, uint16 LE) — distance back in the **raw payload** from the DH byte

```
p_dh = absolute offset of DH byte in payload
src  = p_dh - dist
copy payload[src : src+count] into chunk_buf
```

Back-references span the **whole payload buffer** (cross-chunk), not just the local chunk.
A chunk-local 64×64 buffer is used during decode; non-zero pixels overwrite the canvas.
Out-of-bounds src (src < 0) → transparent pixel (palette index 0).

### Discovery 15: Sprites Browser Missing Chars + Equip Categories
The original `SPRITE_CATS` list hardcoded only environment categories (Forest, Town,
Dungeon, etc.). Both `Chars` and `Equip` exist as subdirectories in `Thumbnails/`
and contain the character sprites and equipment icons. Fixed by discovering categories
dynamically from the filesystem with `_get_sprite_categories()`.

### Discovery 16: hdr_size=84 Files Use TWO Different Formats
Initial assumption: all `hdr_size=84` files use TBitmapData format. Wrong.
Some `hdr_size=84` files use the standard SChunkHeader compressed format.
The correct decode order for ALL files is:
1. If `hdr_size == 84`: try TBitmapData decoder first; if it returns `None`, fall through.
2. Scan payload for SChunkHeader (works for any hdr_size).
3. If SChunkHeader not found: try TBitmapData as final fallback.
The `hdr_size` alone does not reliably distinguish the two formats.

### Discovery 17: n_chunks=1 Has No Offset Table Entry
When `nc == 1` and `nr == 1` (single-chunk sprite), the SChunkHeader is NOT followed
by an offset table. Chunk data starts DIRECTLY at `SChunkHeader + 16` (immediately
after the 4-field header). The bytes at `offsets_start` are chunk data (4-byte cache ID),
NOT an offset pointer. Treating them as offsets caused single-chunk sprites to produce
black output. Fixed by special-casing `n_chunks == 1` in both `_find_chunk_table` and
the main decode loop.

### Discovery 18: SChunkHeader n_cols/n_rows May Differ from ceil(dim/64) by Up to ±2
Many `.i2d` files store `n_cols`/`n_rows` values that disagree with `ceil(width/64)`:
- Some pad to the next even number (e.g., width=96 → n_cols=2 expected, file stores 2 ✓)
- Some pad to the next power of 2 (e.g., width=96 → n_cols=2 expected, file stores 2 ✓)
- Some store FEWER rows than needed, so bottom pixels are transparent (clipped)
- Some store MORE rows (extra transparent rows appended)
The scanner now accepts `nc >= max(1, n_cols_min - 2)` and `nr >= max(1, n_rows_min - 2)`
instead of requiring exact matches. Always use the stored values for canvas allocation.

### Discovery 19: TBitmapData Format Appears in Files of ANY hdr_size
TBitmapData was not exclusive to `hdr_size == 84` files. Files with larger headers
(e.g., 96, 100, 108+) also embed TBitmapData structs in their payload. When the
SChunkHeader scan returns None, the TBitmapData scanner is now tried as a final fallback
for all file sizes. This salvaged hundreds of sprites from the Misc, TownInt, KeepInt
categories that were failing.

### Discovery 20: 16-bit BGR555 Direct Pixels (palsize=0)
A subset of `.i2d` files (shadow overlays, stain textures, window/glass textures) use
16-bit BGR555 direct colour instead of 8-bit indexed:
- TBitmapData `palsize` field = 0 (no embedded palette)
- TBitmapData `datasize` field = `w × h × 2` (two bytes per pixel)
- Pixel format: uint16 LE BGR555 → same conversion as palette entries
- Transparency: word == 0 → alpha = 0; else alpha = 255
These files have no `.tn` companion and would have returned None with the palette-only path.

### Discovery 21: TBitmapData Dimension Tolerance of ±4 Pixels
Some TBitmapData structs store dimensions 1–4 pixels smaller than the CGSR header width/height:
- `kinpicturen2.i2d`: CGSR says 32×32, TBitmapData stores 28×28 (−4 px each)
- `tinbeermug02.i2d`: CGSR says 20×24, TBitmapData stores 20×19 (−1 row)
- `tinplaque01.i2d`:  CGSR says 26×26, TBitmapData stores 24×24 (−2 px each)
Cause: the sprite was cropped or padded at runtime. Fixed by first scanning with tolerance=0,
then retrying with tolerance=4 (`abs(w2-width) <= 4`). The decoded image is cropped back to
the CGSR header dimensions so the final output is always the correct size.

### Discovery 22: chunk_end IndexError from Unclamped Payload Slice
When multi-chunk offsets are resolved, `chunk_end` can exceed `len(payload)` because:
- The offset table may store `len(payload) - ct_base` exactly (valid last chunk)
- But computed `ct_base + chunk_end` can round up beyond the file length
Fix: `chunk_end = min(chunk_end, len(payload))` at the top of `_decode_chunk`.
Without this clamp, IndexError was triggered on ≈600 sprites, silently returning None.

### Discovery 23: Palette Format is X1R5G5B5 (R=high), NOT BGR555 (R=low)
**Critical correction:** Early code read the palette as `R=(word & 0x1F)<<3` (R in low bits),
which is true DirectDraw BGR555 but produces completely wrong sprite colours.

Empirically confirmed by comparison-rendering `forbirch001.i2d` with 4 interpretations:
- **RGB888 (768 bytes raw):** garbled random bright colours — WRONG
- **BGR888 (byte-swapped):** also garbled — WRONG
- **X1R5G5B5 `R=((word>>10)&0x1F)<<3, B=(word&0x1F)<<3`:** dark olive/green birch tree — CORRECT ✅
- **BGR555 `R=(word&0x1F)<<3, B=((word>>10)&0x1F)<<3`:** R/B swapped vs correct — slightly off

The SPalette struct comment in the original source says "BGR555" but the *actual* bit layout
used by the game's DirectDraw surface is **X1R5G5B5** (same as D3DFMT_X1R5G5B5 / DDPF_RGB
with `dwRBitMask=0x7C00`). R occupies the high 5 bits, B the low 5 bits.

Fix applied in commit a65f858:
- `_bgr555_to_rgb888`: corrected to R=bits14-10, G=bits9-5, B=bits4-0
- `_load_palette`: now reads 512 bytes (X1R5G5B5) instead of 768 bytes (RGB888)
- `_decode_comp0`: same fix for TBitmapData palette path and 16-bit direct-pixel path
- `.tn` files: only first 512 bytes read for palette (bytes 512-767 are ARGB/thumbnail data)

---

## Implementation Progress

### Commit 1 — 2026-03-08 00:47 — Initial RevEngine (11 files, 2,948 lines)

Full working toolkit created from scratch:

- **`setup.py`** — one-shot installer: installs deps, extracts all ZIP archives
- **`archive_extractor.py`** — batch ZIP extractor with progress reporting
- **`cgsr_decoder.py`** — first working CGSR parser (prototype, superseded)
- **`map_parser.py`** — MAP chunk parser: 9,722 chunks, world 67×32
- **`decoders/cgsr.py`** — refined CGSR parser with verified field offsets
- **`asset_studio.py` v1** — 1,655-line GUI with 6 tabs:
  - World Map, Characters, Equipment, Spells, Scripts, 3D Models
- **`texture_extractor_guide.md`** — dgVoodoo2 + RenderDoc pipeline
- **`requirements.txt`** — Pillow + numpy

At this point: i2d decoding was **not yet working** (chunk table scanner not yet written; `decoders/i2d.py` did not exist).

### Commit 2 — 2026-03-08 02:46 — Sprite Decoder + SpritesTab (666 lines added)

Major breakthrough: full i2d sprite decoding + browser tab:

- **`decoders/i2d.py`** (352 lines, written from scratch):
  - Full chunk table scanner with validation (eliminates 130 false positives)
  - Full RLE decompressor (DL escape, DL+0xC0 next-row, count+color runs)
  - LZ back-reference placeholder (DH escape → skip 2 bytes)
  - Palette system (.tn → BMP → VGA fallback, cached per folder)
  - `decode_i2d(path)` → PIL RGBA image
  - `decode_i2d_info(path)` → header dict (no pixel decode)

- **`asset_studio.py`** (325 lines added → 1,980 total):
  - Fixed `stitch_zone_map()`: `.isdigit()` → `int()/except` for signed Y coords
    → Zone 0 now correctly renders as 1600×3840 px (750 tiles, 25×60 grid)
  - Fixed `get_available_zones()`: same int/except fix
  - Added **SpritesTab**: 7th tab
    - Browse all 5,500+ sprites organized by category (Forest, Town, Dungeon, etc.)
    - Grid of 48×48 thumbnails loaded from .tn files (8 per row)
    - Click any thumbnail → background thread decodes full `.i2d` → shown in detail panel
    - Fallback: scale up .tn thumbnail if no .i2d available
    - "Save PNG" button → saves decoded sprite to `test_renders/`
    - Category combobox (Forest, Town, Dungeon, Cave, Keep, KeepInt, Ruin, Labyrnth, TownInt, Misc)

### Commit 4 — 2026-03-08 (current session) — Asset Studio completion

- **`decoders/i3d.py`** (new, ~150 lines):
  - Heuristic geometry decoder: stride detection via h2 interpretation
  - Parses vertices (float32 x,y,z) at detected stride
  - Parses face indices (uint16 triplets)
  - Sanity checks on all float values and indices
  - OBJ exporter: `export_obj(geom, out_path)` → Wavefront OBJ file

- **`decoders/i2d.py`** (LZ fix):
  - `_decode_chunk` refactored to use chunk-local `bytearray(CHUNK_PX × CHUNK_PX)`
  - LZ back-reference implemented: `distance = byte1`, `length = byte2 + 1`
  - Back-reference copies from chunk-local buffer at `cur_pos - distance`
  - Non-zero pixels copied to canvas pixels after chunk decode (transparency preserved)

- **`asset_studio.py`** (additions):
  - `_get_sprite_categories()` — discovers categories from `Thumbnails/` filesystem
  - `SpritesTab`: dynamic category combobox (includes Chars, Equip, all categories)
  - `SpritesTab`: "Export All" button — batch PNG export of entire category
    with progress updates and Stop button; saves to `test_renders/<Category>/`
  - `ModelViewer3D` widget — orthographic wireframe renderer:
    - Drag to rotate (azimuth + elevation), scroll to zoom
    - Wireframe rendering with painter's algorithm depth sort
    - Point cloud fallback when no faces decoded
    - Fits geometry to canvas automatically
  - `ModelsTab`: detail panel split vertically (metadata top + 3D viewer bottom)
  - `ModelsTab`: "Export OBJ" button → filedialog save → writes Wavefront OBJ

### Commit 3 — 2026-03-08 02:52 — Bug fixes (16 insertions, 16 deletions)

Performance + correctness fixes for SpritesTab:

- **`_load_category()`**: replaced `glob("*.tn") + glob("*.TN")` with `iterdir()` +
  `seen: set` to avoid Windows duplicate file issue
- **i2d lookup**: replaced per-sprite `iterdir()` scan with pre-built
  `stem.lower() → path` dict (O(n²) → O(n))

### Commit 5 — 2026-03-08 (a615619) — i2d decoder: massively improved coverage

Pushed `.i2d` sprite decode success rate from ~155 to **2650/2654 (99.8%)**.

- **`decoders/i2d.py`** (major rewrite, Discoveries 16–22):
  - `_find_chunk_table()` return type changed from `Optional[int]` to `Optional[tuple]`
    of `(ct_type_off, nc, nr)` — callers now use the stored grid dims, not computed
  - **n_chunks=1 special case**: single-chunk files skip offset table entirely
  - **Relaxed nc/nr matching**: accept ±2 from expected `ceil(dim/64)` value
  - **Dual decode path for hdr_size=84**: try TBitmapData first, fall through to SChunkHeader
  - **TBitmapData fallback for all hdr_sizes**: final fallback when SChunkHeader not found
  - **16-bit BGR555 pixel path**: `palsize==0, datasize==w*h*2` → direct colour decode
  - **±4px TBitmapData tolerance**: scan with tol=0 first, retry with tol=4
  - **chunk_end clamp**: `min(chunk_end, len(payload))` prevents IndexError on last chunk
  - LZ implementation confirmed from ChunkDecompress ASM: 4-byte token (count + uint16 dist)

Coverage breakdown by category (final state):
```
Cave     : 289 OK,  18 fail   KeepInt  :  92 OK,   7 fail
Dungeon  : 354 OK,  10 fail   Labyrnth :  73 OK,   1 fail
Equip    :  51 OK,   1 fail   Misc     :  82 OK,  60 fail *
Forest   : 624 OK,  11 fail   Ruin     : 168 OK,   1 fail
Keep     : 128 OK,   0 fail   Town     : 489 OK,   9 fail
                              TownInt  : 152 OK,   7 fail
TOTAL: 2529 OK / 125 fail  →  after all fixes: 2650 OK / 4 fail
```
*Misc failures are `automap.i2d` (hdr_size=8, map format), `blood.i2d` (w=h=0),
 and `dunwwwf.i2d` (wildly mismatched nc/nr) — legitimately different formats.

### Commit 6 — 2026-03-09 (a65f858) — Palette format correction (X1R5G5B5)

Critical fix: all sprites were rendering with completely wrong colours since the
palette format was misidentified as raw RGB888 (768 bytes). Actual format is
**X1R5G5B5** (256 × uint16 LE, 512 bytes).

- **`decoders/i2d.py`**:
  - `_bgr555_to_rgb888`: corrected bit-field order — R=bits14-10 (high), B=bits4-0 (low)
  - `_load_palette`: reads 512 bytes (X1R5G5B5) instead of 768 bytes (raw RGB888)
    for both embedded SPalette and `.tn` file sources
  - `_decode_comp0`: same 512-byte fix for TBitmapData palette path
  - Direct 16-bit pixel path: corrected channel order to match (was also swapped)
- Documentation (`REVENANT_REVERSE_ENGINEERING.md`): corrected palette format
  throughout, added Discovery 23, updated `.tn` file format section

Coverage unchanged: **2650/2654 (99.8%)** — same 4 legitimately-different files fail.

---

## Algorithms

### Algorithm 1: CGSR Header Parse

```python
import struct
HEADER_SIZE = 0x54  # 84 bytes

raw = path.read_bytes()
if len(raw) < 88 or raw[:4] != b'CGSR':
    return None

type_byte   = raw[4]          # 0x01=2D, 0x00=3D
version     = raw[7]
data_size   = struct.unpack_from('<I', raw, 0x08)[0]
state_count = struct.unpack_from('<I', raw, 0x18)[0]
state_name  = raw[0x1C:0x40].split(b'\x00')[0].decode('ascii', 'replace')
hdr_size    = struct.unpack_from('<H', raw, 0x10)[0]   # always 84
width, height = struct.unpack_from('<HH', raw, 0x48)
x_off, y_off  = struct.unpack_from('<HH', raw, 0x4C)
pixel_flags   = struct.unpack_from('<I',  raw, 0x50)[0]  # NOT a file offset!

payload = raw[hdr_size:]
```

### Algorithm 2: i3d Animation State Table Parse

```python
ENTRY_SIZE  = 76
NAME_OFFSET = 20

for i in range(state_count):
    entry      = payload[i * ENTRY_SIZE : (i+1) * ENTRY_SIZE]
    flags_data = entry[:NAME_OFFSET]
    name       = entry[NAME_OFFSET:].split(b'\x00')[0].decode('ascii', 'replace').strip()
    # name = e.g. "still", "walk", "attack", "die"

geom_file_offset = HEADER_SIZE + state_count * ENTRY_SIZE
```

### Algorithm 3: .tn Palette Load

```python
def load_tn_palette(tn_path: Path) -> list:
    """Returns list of 256 (R,G,B,A) tuples. Index 0 = transparent."""
    raw = tn_path.read_bytes()   # exactly 768 bytes
    return [
        (raw[i*3], raw[i*3+1], raw[i*3+2], 0 if i == 0 else 255)
        for i in range(256)
    ]
```

### Algorithm 4: Chunk Table Scanner (with validation, relaxed dims)

```python
CHUNK_TYPE = 5
CHUNK_PX   = 64

def find_chunk_table(payload: bytes,
                     n_cols_min: int,
                     n_rows_min: int) -> Optional[tuple]:
    """
    Returns (ct_type_off, nc, nr) — offset of type=5 field + ACTUAL stored grid dims.
    Accepts nc/nr within ±2 of expected ceil(dim/64).
    Single-chunk sprites (nc*nr==1) have no offset table; validated by payload length.
    """
    limit = len(payload) - 20
    for i in range(32, limit, 4):
        if struct.unpack_from('<I', payload, i)[0] != CHUNK_TYPE:
            continue
        nc = struct.unpack_from('<I', payload, i + 4)[0]
        nr = struct.unpack_from('<I', payload, i + 8)[0]
        if not (1 <= nc <= 32 and 1 <= nr <= 32):
            continue
        # Accept ±2 from expected dims (some files pad to even/power-of-2)
        if nc < max(1, n_cols_min - 2) or nr < max(1, n_rows_min - 2):
            continue
        n_chunks = nc * nr
        if n_chunks == 1:
            # No offset table — data starts at SChunkHeader+16 directly
            if i + 22 <= len(payload):
                return (i, nc, nr)
        else:
            offsets_start = i + 16
            if offsets_start + n_chunks * 4 > len(payload):
                continue
            ct_base   = i - 32
            max_valid = len(payload) - ct_base
            for k in range(n_chunks):
                off = struct.unpack_from('<I', payload, offsets_start + k * 4)[0]
                if 0 < off < max_valid:
                    return (i, nc, nr)   # confirmed valid offset table
    return None

# Usage:
result = find_chunk_table(payload, n_cols_min, n_rows_min)
if result:
    ct_type_off, nc, nr = result   # use nc/nr for canvas size, NOT ceil(dim/64)
```

### Algorithm 5: Chunk Offset Resolution

```python
ct_type_off   = find_chunk_table(payload, n_cols, n_rows)
ct_base       = ct_type_off - 32
offsets_start = ct_type_off + 16   # skip type(4) + n_cols(4) + n_rows(4) + table_sz(4)

offsets = [
    struct.unpack_from('<I', payload, offsets_start + k * 4)[0]
    for k in range(n_chunks)
]

for idx, off in enumerate(offsets):
    if off == 0:
        continue  # empty/transparent chunk
    abs_off = ct_base + off  # absolute position in payload

    # Chunk size: distance to next non-zero offset
    chunk_end = len(payload) - ct_base
    for nxt in offsets[idx + 1:]:
        if 0 < nxt <= len(payload):
            chunk_end = nxt
            break
    chunk_data = payload[abs_off : ct_base + chunk_end]

    col = idx % n_cols
    row = idx // n_cols
    # decode chunk at canvas position (col*64, row*64)
```

### Algorithm 6: Chunk RLE Decoder (current — with LZ and chunk-local buffer)

```python
def decode_chunk(payload: bytes, chunk_abs: int, chunk_end: int,
                 pixels: bytearray, stride: int,
                 x0: int, y0: int, img_w: int, img_h: int):
    """
    payload   : full .i2d payload (LZ back-refs span entire payload)
    chunk_abs : absolute start of chunk block (incl. 4-byte cache ID)
    chunk_end : exclusive end of chunk in payload (clamped to len(payload))
    """
    if chunk_abs + 6 > len(payload):
        return
    chunk_end = min(chunk_end, len(payload))   # CRITICAL: clamp to avoid IndexError
    dl = payload[chunk_abs + 4]   # RLE escape byte
    dh = payload[chunk_abs + 5]   # LZ  escape byte
    i  = chunk_abs + 6

    # Chunk-local 64×64 buffer (index 0 = transparent)
    chunk_buf = bytearray(CHUNK_PX * CHUNK_PX)
    x, y = 0, 0

    while i < chunk_end and y < CHUNK_PX:
        b = payload[i]; i += 1

        if b == dl:
            # ── RLE escape ──────────────────────────────────
            cmd = payload[i]; i += 1
            if cmd == 0:
                y += 1; x = 0                    # EOL — end of row
            elif cmd & 0x80:
                n = cmd & 0x7F                   # transparent skip
                x += n
                while x >= CHUNK_PX: x -= CHUNK_PX; y += 1
            else:
                color = payload[i]; i += 1       # RLE run: cmd copies of color
                for _ in range(cmd):
                    if 0 <= x < CHUNK_PX and y < CHUNK_PX:
                        chunk_buf[y * CHUNK_PX + x] = color
                    x += 1
                    if x >= CHUNK_PX: x = 0; y += 1

        elif b == dh:
            # ── LZ back-reference (4-byte token: DH + count + dist_lo + dist_hi)
            p_dh  = i - 1                        # absolute position of DH byte
            count = payload[i]; i += 1
            dist  = payload[i] | (payload[i+1] << 8); i += 2
            src   = p_dh - dist
            for k in range(count):
                pix = payload[src + k] if src + k >= 0 else 0
                if 0 <= x < CHUNK_PX and y < CHUNK_PX:
                    chunk_buf[y * CHUNK_PX + x] = pix
                x += 1
                if x >= CHUNK_PX: x = 0; y += 1

        else:
            # ── Literal pixel ────────────────────────────────
            if 0 <= x < CHUNK_PX and y < CHUNK_PX:
                chunk_buf[y * CHUNK_PX + x] = b
            x += 1
            if x >= CHUNK_PX: x = 0; y += 1

    # Copy non-zero chunk_buf pixels → canvas (preserves transparency)
    for cy in range(CHUNK_PX):
        py = y0 + cy
        if py >= img_h: break
        for cx in range(CHUNK_PX):
            px = x0 + cx
            if px >= img_w: break
            v = chunk_buf[cy * CHUNK_PX + cx]
            if v: pixels[py * stride + px] = v
```

### Algorithm 7: Automap Tile Stitching (signed Y fix)

```python
# Tile filenames: Zone_Y_X.bmp  —  Y and X may be NEGATIVE
tiles = [f for f in automap_dir.iterdir()
         if f.suffix.lower() == '.bmp' and f.name.startswith(f"{zone}_")]

coords = []
for t in tiles:
    parts = t.stem.split('_')  # e.g. ['0', '-10', '25']
    try:
        y_val = int(parts[1])  # use int(), NOT isdigit() — negatives!
        x_val = int(parts[2])
        coords.append((y_val, x_val, t))
    except (ValueError, IndexError):
        continue

if not coords:
    return None

min_y = min(y for y,x,_ in coords)
min_x = min(x for y,x,_ in coords)
n_cols = max(x for y,x,_ in coords) - min_x + 1
n_rows = max(y for y,x,_ in coords) - min_y + 1

canvas = Image.new('RGB', (n_cols * tile_size, n_rows * tile_size), (20,20,30))
for y_val, x_val, path in coords:
    col = x_val - min_x
    row = y_val - min_y
    tile = Image.open(path).convert('RGB').resize((tile_size, tile_size), Image.NEAREST)
    canvas.paste(tile, (col * tile_size, row * tile_size))
```

### Algorithm 8: .tn File Deduplication (Windows fix)

```python
# WRONG — on Windows, glob("*.tn") already matches .TN; both globs give duplicates:
# tn_files = list(dir.glob("*.tn")) + list(dir.glob("*.TN"))

# CORRECT — use iterdir() with seen-set on lowercased stem:
seen: set[str] = set()
tn_files: list[Path] = []
for f in sorted(tn_dir.iterdir()):
    if f.suffix.lower() == ".tn" and f.stem.lower() not in seen:
        seen.add(f.stem.lower())
        tn_files.append(f)
```

### Algorithm 9: Fast i2d Lookup (O(n) not O(n²))

```python
# WRONG — O(n²): calls iterdir() for every sprite
for tn in tn_files:
    for f in img_dir.iterdir():
        if f.stem.lower() == tn.stem.lower() and f.suffix.lower() == '.i2d':
            ...

# CORRECT — build index once (O(n)), then do O(1) lookups
i2d_index: dict[str, Path] = {}
if img_dir.exists():
    for f in img_dir.iterdir():
        if f.suffix.lower() == ".i2d":
            i2d_index[f.stem.lower()] = f

for tn in tn_files:
    i2d = i2d_index.get(tn.stem.lower(), Path(""))
```

---

## Tools & Scripts

### `setup.py`
**Purpose:** One-shot first-run script — installs deps and extracts all archives.
**Usage:** `py RevEngine/setup.py`
**What it does:** `pip install -r requirements.txt`, then calls `extract_all_archives()`

---

### `archive_extractor.py`
**Purpose:** Batch extract all Revenant archives to `_extracted/`
**Usage:**
```
python archive_extractor.py                    # interactive, extract all
python archive_extractor.py --list             # list extracted asset summary
python archive_extractor.py --overwrite        # force re-extract
python archive_extractor.py --game-dir PATH
python archive_extractor.py --output PATH
```
**Constants:** `GAME_DIR = Path("C:/GOG Games/Revenant")`, `EXTRACT_DIR = GAME_DIR / "_extracted"`

---

### `cgsr_decoder.py`
**Status:** Legacy prototype. Superseded by `decoders/cgsr.py` + `decoders/i2d.py`.
Kept for reference only.

---

### `decoders/cgsr.py`
**Purpose:** Refined CGSR header parser + i3d animation state reader.
```python
from decoders.cgsr import parse, describe, thumbnail_to_image, thumbnail_to_tk

f = parse(Path("character.i3d"))
print(describe(f))                    # formatted summary
for state in f.anim_states:
    print(state.index, state.name)    # all animation state names
print(f.geometry.estimated_verts)     # approximate vertex count
img = thumbnail_to_image(f.thumbnail, scale=8)  # 128×128 preview
```

---

### `decoders/i2d.py`
**Purpose:** Full i2d sprite decoder — the primary decoder for 2D assets.
**Status:** 2650/2654 sprites decode successfully (99.8%). The 4 remaining failures are
files with legitimately different formats (map data, zero-size, extreme dimension mismatch).
```python
from decoders.i2d import decode_i2d, decode_i2d_info

img = decode_i2d(Path("forbirch001.i2d"))   # → PIL RGBA image or None
if img:
    img.save("output.png")

info = decode_i2d_info(Path("forbirch001.i2d"))
# Returns dict: width, height, x_offset, y_offset, n_chunks, ct_found, file_size
```
**Two decoder paths:**
1. `_decode_comp0()` — TBitmapData image-list (8-bit indexed or 16-bit BGR555)
2. `_find_chunk_table()` + `_decode_chunk()` — SChunkHeader RLE+LZ compressed tiles

**Key constants:**
```python
CHUNK_PX   = 64   # pixels per chunk tile
CHUNK_TYPE = 5    # chunk table type marker
```

---

### `map_parser.py`
**Purpose:** Parse Revenant MAP chunk files (9,722 chunks total).
```
python map_parser.py --analyze            # print world bounds
python map_parser.py --manifest OUT.json  # export chunk manifest
python map_parser.py --visualize 0        # ASCII + PNG of Z-layer 0
python map_parser.py --map-dir PATH
```
Default map dir: `C:/GOG Games/Revenant/_extracted/ahkuilon/Map`

---

### `asset_studio.py`
**Purpose:** Full GUI asset viewer / game encyclopedia.
**Usage:** `python asset_studio.py`
**Requirements:** Python 3.10+, Pillow, tkinter (built-in)
**Window size:** 1400×880 px, resizable

**7 tabs:**
| Tab | Content | Key feature |
|-----|---------|-------------|
| World Map | Automap tile stitcher | Zone selector, zoom 25/50/100%, pan (middle mouse) |
| Characters | Gallery from char.def (60 chars) | Portrait + stats + i3d anim count, live filter |
| Equipment | Weapons (60) + Armour (207) | Sortable Treeview, .tn thumbnail on select |
| **Sprites** | 5,500+ sprites by category | 48px thumbnail grid, click → full decode |
| Spells | 74 spells from spell.def | Filtered list + detail pane |
| Scripts | All .def files | Syntax-highlighted viewer + full-text search |
| 3D Models | 612 i3d files | Name, folder, size, anim count, est. verts, state list |

**Sprite categories:** Discovered dynamically from `Thumbnails/` subdirectories at runtime.
Includes: Forest, Town, Dungeon, Cave, Keep, KeepInt, Ruin, Labyrnth, TownInt, Misc, Chars, Equip (and any future additions).

**Pre-rendered cache:** `test_renders/world_map_zone0.png` — if present, World Map loads instantly.

**Save PNG:** SpritesTab has a "Save PNG" button → saves current decoded sprite to `test_renders/`.

**Header counts bar** (updates 2s after launch): shows live i3d/bmp/def/mp3 totals.

---

### `test_tn.py`
**Purpose:** Diagnostic — verified .tn file format.
Reads Forest + Equip .tn files; prints size, palette entries, non-zero count.
Confirmed: 768 bytes; first 512 = X1R5G5B5 palette (256 × uint16 LE), bytes 512-767 = ARGB/thumbnail data.
Index 0 is transparent (decoder forces alpha=0 regardless of stored colour).

---

### `texture_extractor_guide.md`
**Purpose:** Alternative texture capture via dgVoodoo2 + RenderDoc.
Rationale: CGSR files embed DirectDraw 7 surface descriptors (e.g. 0x2088) that are
runtime values, not static parse targets. Runtime capture bypasses all format complexity.
Pipeline: install dgVoodoo2 DLLs → launch game under RenderDoc → F12 capture → export textures.

---

## Current Progress State

### What Works (as of latest commit, 2026-03-08 a615619)

| Feature | Status | Notes |
|---------|--------|-------|
| Archive extraction (.rvr/.rvi/.rvm) | ✅ Complete | Plain ZIP |
| CGSR header parsing | ✅ Complete | All fields verified |
| .tn palette loading | ✅ Complete | Dual use: palette + 16×16 preview |
| .i2d sprite decoding (RLE + LZ) | ✅ 99.8% | 2650/2654 files; 4 unfixable outliers |
| .i2d TBitmapData (uncompressed) | ✅ Complete | 8-bit indexed + 16-bit BGR555 paths |
| .bmp loading (portraits, tiles) | ✅ Complete | Standard PIL |
| Automap tile stitching | ✅ Complete | 1600×3840 Zone 0 |
| char.def / weapon.def / armor.def / spell.def parsing | ✅ Complete | Regex block parser |
| MAP chunk header + coordinate parsing | ✅ Complete | 9,722 chunks |
| World Map GUI tab | ✅ Complete | Zoom, pan, zone select |
| Characters GUI tab | ✅ Complete | Gallery + detail + filter |
| Equipment GUI tab | ✅ Complete | Dual Treeview + .tn preview |
| **Sprites GUI tab** | ✅ Complete | Dynamic categories, thumbnail grid, batch export |
| Spells GUI tab | ✅ Complete | Table + detail |
| Scripts GUI tab | ✅ Complete | Viewer + full-text search |
| 3D Models GUI tab | ✅ Complete | Wireframe viewer, OBJ export, 612 models |
| Asset Studio launch (7 tabs) | ✅ Complete | ~2,000 lines |

### What Is Unfinished / Known Gaps

| Feature | Status | Notes |
|---------|--------|-------|
| LZ back-reference decode (DH escape in .i2d) | ⚠️ Best-effort | Assumed: (distance, length+1); format not confirmed from source |
| .i3d geometry decode (vertices, faces) | ⚠️ Heuristic | Stride detection; many models show wireframe; some fall back to point cloud |
| UV / normal decode for i3d | ❌ Not implemented | Only x,y,z taken from each vertex; rest of stride ignored |
| i3d → OBJ export | ✅ Complete | "Export OBJ" button in Models tab; Blender-compatible |
| 3D wireframe viewer | ✅ Complete | ModelViewer3D in Models tab; drag/scroll rotation |
| Animation playback | ❌ Not implemented | State names decoded; frame data format unknown |
| Full MAP chunk payload decode | ❌ Not implemented | Post-header tile data format unknown |

---

## Next Steps

### Priority 1: Confirm LZ Back-Reference Encoding
`decoders/i2d.py` now implements an assumed LZ format (`distance, length+1`). Need to verify:
- Compare decoded sprites against runtime RenderDoc captures for accuracy
- If pixels are wrong in LZ regions, try alternate encodings (e.g., packed offset+length nibbles)
- Check whether `DH == 0` is a special end-of-chunk signal

### Priority 2: Confirm i3d Stride / Vertex Layout
`decoders/i3d.py` uses heuristic stride detection. Next steps:
- Load a known character model in Blender via OBJ export; verify mesh looks correct
- If deformed: try reading normals (float32 × 3 after xyz) and UV coords to confirm stride
- Check if `h0` flags indicate different vertex formats per file

### Priority 3: UV / Normal Decode for i3d
Once stride is confirmed:
- Decode float32 normals (stride ≥ 24: bytes 12–23)
- Decode float32 UV coords (stride ≥ 32: bytes 24–31)
- Extend `export_obj()` to write `vt` / `vn` lines and MTL file for textured export

### Priority 4: Animation Frame Data
The CGSR header contains a state_count and state table (76 bytes/entry). Each entry
likely contains: frame offsets, bounding box, pivot point. Goals:
- Map state names (from `.i3d` adjacent `.dat` or string table) to frame indices
- Export per-frame OBJ or animate in the tkinter viewer

### Priority 5: MAP Chunk Payload
- Hexdump first few `.DAT` map files and look for repeating patterns (tile IDs)
- Identify tile size (likely 8×8 or 16×16 tile grid within each chunk)
- Map tile IDs to texture assets from the imagery archives
- Goal: render a textured top-down map view

---

## Environment & Dependencies

```
Python: 3.10+
Pillow: >= 10.0.0   (pip install Pillow)
numpy:  >= 1.24.0   (pip install numpy)
tkinter: built-in   (no install needed on Windows)
```

**First-time setup:**
```
cd "C:/GOG Games/Revenant/RevEngine"
py setup.py
```

**Run Asset Studio:**
```
cd "C:/GOG Games/Revenant/RevEngine"
python asset_studio.py
```

**Git history:**
```
a615619  feat(i2d): massively improve sprite decoder coverage (155→2650 OK)
46f9fe7  feat: dynamic categories, batch export, ModelViewer3D, i3d decoder, LZ fix
50bfc2e  Fix SpritesTab duplicate .tn loading and speed up i2d lookup
9750aaf  Fix map stitching, add Sprites browser, improve i2d decoder
6c00108  Initial RevEngine asset pipeline for Revenant (1999)
```

---

*Last updated: 2026-03-09 — Corrected palette format to X1R5G5B5 (512 bytes, R=high bits); fixed _bgr555_to_rgb888 channel order; all sprites now render with correct colours. i2d coverage 99.8% (2650/2654).*
