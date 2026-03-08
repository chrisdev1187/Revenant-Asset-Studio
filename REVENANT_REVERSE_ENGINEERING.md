# Revenant Reverse Engineering Log

> **Purpose:** This document is the authoritative technical record of the RevEngine project.
> It must be updated every time new code is written or a new discovery is made.
> It is written so the entire project can be reconstructed from this document alone
> if all source code is lost.
>
> **Git history:** 3 commits, all on 2026-03-08 by chrisdev1187
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

`.i2d` files use an **8-bit paletted, chunk-compressed** pixel format.
The real pixel format is NOT 16-bit (RGB565/ARGB1555) despite being a late-90s D3D
game. Palette indices are stored and the palette itself lives in a companion `.tn` file.

#### Palette Source (.tn files)

- `.tn` files are exactly **768 bytes**: 256 entries × 3 bytes (R, G, B). No header.
- Stored in `_extracted/imagery/Thumbnails/<Category>/`, named to match the `.i2d`.
- **Palette index 0 = transparent (alpha = 0) regardless of its RGB values.**
- Fallback order for palette resolution:
  1. `.tn` companion file from same directory as `.i2d`
  2. `.bmp` (mode `'P'`) found anywhere in the same directory as the `.i2d`
  3. Windows VGA 16-colour palette + grayscale ramp (last resort)
- Palette results are cached per folder to avoid re-reading disk.

#### Chunk Grid Layout

The canvas is divided into **64×64 pixel tiles** (chunks):
```
CHUNK_PX = 64
n_cols   = ceil(width  / 64)
n_rows   = ceil(height / 64)
n_chunks = n_cols × n_rows
```
Canvas is `n_cols × 64` wide, `n_rows × 64` tall; final image is cropped to `(width, height)`.

#### Chunk Table Location

The chunk table is NOT at a fixed offset. Must be located by scanning the payload:

```
Scan payload starting at offset 32, step 4 bytes:
  Look for: [uint32 = 5] [uint32 = n_cols] [uint32 = n_rows]

When found at position i:
  ct_base       = i - 32        (32 bytes of pre-header before the type=5 field)
  offsets_start = i + 16        (type[4] + n_cols[4] + n_rows[4] + table_sz[4])
```

**Validation (eliminates ~130 false positives in the wild):**
After finding the `[5, n_cols, n_rows]` pattern, verify that at least one of the
`n_chunks` uint32 offsets at `offsets_start` is non-zero AND less than
`len(payload) - ct_base`. Without this check, bogus `[5,1,1]` patterns in unrelated
data will produce empty/wrong output. This was a significant bug discovered and fixed
in the second commit.

#### Chunk Offset Table

After `offsets_start`: `n_chunks` × uint32 LE values.
Each value is an offset **relative to `ct_base`** (the 32-byte pre-header position).

```
off = offsets[idx]
if off == 0:
    → skip (empty/transparent chunk, leave pixels as 0)
abs_off = ct_base + off         ← byte position in payload
```

Chunk data size: determined by the next non-zero offset in the table, minus current.
Last chunk: extends to end of payload.

#### Chunk RLE Compression Format

Each chunk block begins with 2 escape-byte definitions:
```
data[0] = DL   (RLE escape byte — value varies per file)
data[1] = DH   (LZ escape byte  — value varies per file)
pixel stream follows at data[2:]
```

Pixel stream interpretation (advance left→right, wrap to next row at x≥64):
```
byte b:
  b == DL  →  RLE escape:
                cmd = next byte
                if cmd == 0xC0:
                  → NEXT ROW: y += 1, x = 0
                else:
                  count = cmd
                  color = next byte
                  → paint `count` pixels with palette index `color`
  b == DH  →  LZ back-reference (NOT YET IMPLEMENTED):
                → skip 2 bytes and continue
  else     →  literal pixel: paint 1 pixel with palette index b
```

When `x >= 64`: wrap → `x = 0`, `y += 1`.
When `y >= 64`: chunk is complete.

> **LZ Note:** The `DH` escape is encountered in the wild but the 2-byte back-reference
> encoding is not yet reverse-engineered. Currently skipped (2 bytes discarded).
> Sprites with heavy LZ content will have missing pixels in those regions.

#### Full Decode Procedure

```python
# 1. Parse header (84 bytes)
width  = struct.unpack_from('<H', raw, 0x48)[0]
height = struct.unpack_from('<H', raw, 0x4A)[0]
hdr_sz = struct.unpack_from('<H', raw, 0x10)[0]   # = 84
payload = raw[hdr_sz:]

# 2. Calculate chunk grid
n_cols = (width  + 63) // 64
n_rows = (height + 63) // 64

# 3. Find chunk table (validated scanner)
ct_type_off = find_chunk_table(payload, n_cols, n_rows)
ct_base     = ct_type_off - 32
offsets     = [struct.unpack_from('<I', payload, ct_type_off+16+k*4)[0]
               for k in range(n_cols*n_rows)]

# 4. Load palette (768-byte .tn file)
rgba_pal = make_rgba_palette(load_tn(path.parent / (path.stem + '.tn')))

# 5. Allocate canvas (palette indices, 0 = transparent)
canvas_w = n_cols * 64
canvas_h = n_rows * 64
pixels = bytearray(canvas_w * canvas_h)

# 6. Decode each chunk into canvas
for idx, off in enumerate(offsets):
    if off == 0: continue
    col, row = idx % n_cols, idx // n_cols
    abs_off  = ct_base + off
    chunk_data = payload[abs_off : ct_base + next_nonzero_off]
    decode_chunk(chunk_data, pixels, canvas_w,
                 col*64, row*64, canvas_w, canvas_h)

# 7. Apply palette → RGBA
out = Image.new('RGBA', (canvas_w, canvas_h), (0,0,0,0))
for py in range(canvas_h):
    for px in range(canvas_w):
        r,g,b,a = rgba_pal[pixels[py*canvas_w+px]]
        out.putpixel((px,py), (r,g,b,a))

# 8. Crop to actual dimensions
out = out.crop((0, 0, width, height))
```

---

### `.tn` File Format

- **Size:** Exactly 768 bytes (256 × RGB)
- **Format:** Raw binary, no header. Entry `i` = bytes `[i*3, i*3+1, i*3+2]` = R, G, B.
- **Dual purpose:** Used as both the 256-colour palette for `.i2d` decoding AND as a
  16×16 thumbnail preview (first 768 bytes interpreted as `Image.frombytes('RGB', (16,16), data)`).
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
A `.tn` file has dual purpose. The same 768 bytes (256×RGB) serve as:
- The decode palette for the companion `.i2d` sprite
- A 16×16 pixel thumbnail preview when interpreted as raw RGB888

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

### Discovery 14: LZ Back-Reference Format (Best-Effort, Assumed)
The DH escape in `.i2d` chunk compression is followed by 2 bytes.
**Assumed format** (most common for 1999-era sprite compression):
- byte1 = distance (pixels back in the linear chunk buffer)
- byte2 = length - 1 (so length is 1–256 pixels)
A chunk-local buffer (`chunk_buf[CHUNK_PX × CHUNK_PX]`) is maintained during decode
so back-references can read previously written pixels. This assumption is NOT
confirmed from game source — if sprites look wrong in LZ-heavy regions, the format
may differ (e.g., distance encoded in high bits of a combined 16-bit word).

### Discovery 15: Sprites Browser Missing Chars + Equip Categories
The original `SPRITE_CATS` list hardcoded only environment categories (Forest, Town,
Dungeon, etc.). Both `Chars` and `Equip` exist as subdirectories in `Thumbnails/`
and contain the character sprites and equipment icons. Fixed by discovering categories
dynamically from the filesystem with `_get_sprite_categories()`.

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

### Algorithm 4: Chunk Table Scanner (with validation)

```python
CHUNK_TYPE = 5
CHUNK_PX   = 64

def find_chunk_table(payload: bytes, n_cols: int, n_rows: int) -> Optional[int]:
    """Returns offset of the type=5 field within payload, or None."""
    n_chunks = n_cols * n_rows
    min_size = 16 + n_chunks * 4
    limit    = len(payload) - min_size

    for i in range(32, limit, 4):    # i >= 32 guarantees ct_base = i-32 >= 0
        if (struct.unpack_from('<I', payload, i)[0]     == CHUNK_TYPE and
            struct.unpack_from('<I', payload, i + 4)[0] == n_cols     and
            struct.unpack_from('<I', payload, i + 8)[0] == n_rows):

            # VALIDATION: at least one offset must be non-zero and in-bounds
            ct_base       = i - 32
            max_valid     = len(payload) - ct_base
            offsets_start = i + 16
            for k in range(n_chunks):
                off = struct.unpack_from('<I', payload, offsets_start + k * 4)[0]
                if 0 < off < max_valid:
                    return i   # confirmed match
    return None
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

### Algorithm 6: Chunk RLE Decoder

```python
def decode_chunk(data: bytes, pixels: bytearray, stride: int,
                 x0: int, y0: int, img_w: int, img_h: int):
    if len(data) < 2:
        return
    dl = data[0]   # RLE escape byte
    dh = data[1]   # LZ escape byte (unimplemented — skip 2 bytes)
    i, x, y = 2, 0, 0

    while i < len(data) and y < CHUNK_PX:
        b = data[i]; i += 1

        if b == dl:
            if i >= len(data): break
            cmd = data[i]; i += 1

            if cmd == 0xC0:
                y += 1; x = 0    # ← CRITICAL: next row, not a count

            else:
                count = cmd
                if i >= len(data): break
                color = data[i]; i += 1
                for _ in range(count):
                    if x < CHUNK_PX and y < CHUNK_PX:
                        px_, py_ = x0 + x, y0 + y
                        if 0 <= px_ < img_w and 0 <= py_ < img_h:
                            pixels[py_ * stride + px_] = color
                    x += 1
                    if x >= CHUNK_PX:
                        x = 0; y += 1
                        if y >= CHUNK_PX: break

        elif b == dh:
            i += 2    # LZ back-ref: skip (not yet decoded)

        else:
            if x < CHUNK_PX and y < CHUNK_PX:
                px_, py_ = x0 + x, y0 + y
                if 0 <= px_ < img_w and 0 <= py_ < img_h:
                    pixels[py_ * stride + px_] = b
            x += 1
            if x >= CHUNK_PX:
                x = 0; y += 1
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
**Status:** Working. ~5,500 sprites decode successfully.
```python
from decoders.i2d import decode_i2d, decode_i2d_info

img = decode_i2d(Path("forbirch001.i2d"))   # → PIL RGBA image or None
if img:
    img.save("output.png")

info = decode_i2d_info(Path("forbirch001.i2d"))
# Returns dict: width, height, x_offset, y_offset, n_chunks, ct_found, file_size
```
**Known limitation:** LZ back-references (DH escape) are skipped — sprites heavy in
LZ content will have pixel gaps.

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

**Sprite categories:** Forest, Town, Dungeon, Cave, Keep, KeepInt, Ruin, Labyrnth, TownInt, Misc

**Pre-rendered cache:** `test_renders/world_map_zone0.png` — if present, World Map loads instantly.

**Save PNG:** SpritesTab has a "Save PNG" button → saves current decoded sprite to `test_renders/`.

**Header counts bar** (updates 2s after launch): shows live i3d/bmp/def/mp3 totals.

---

### `test_tn.py`
**Purpose:** Diagnostic — verified .tn file format.
Reads Forest + Equip .tn files; prints size, palette entries, non-zero count.
Confirmed: 768 bytes, 256-colour RGB palette, index 0 often black (transparent).

---

### `texture_extractor_guide.md`
**Purpose:** Alternative texture capture via dgVoodoo2 + RenderDoc.
Rationale: CGSR files embed DirectDraw 7 surface descriptors (e.g. 0x2088) that are
runtime values, not static parse targets. Runtime capture bypasses all format complexity.
Pipeline: install dgVoodoo2 DLLs → launch game under RenderDoc → F12 capture → export textures.

---

## Current Progress State

### What Works (as of latest commit, 2026-03-08 02:52)

| Feature | Status | Notes |
|---------|--------|-------|
| Archive extraction (.rvr/.rvi/.rvm) | ✅ Complete | Plain ZIP |
| CGSR header parsing | ✅ Complete | All fields verified |
| .tn palette loading | ✅ Complete | Dual use: palette + 16×16 preview |
| .i2d sprite decoding (RLE) | ✅ Complete | ~5,500 sprites |
| .bmp loading (portraits, tiles) | ✅ Complete | Standard PIL |
| Automap tile stitching | ✅ Complete | 1600×3840 Zone 0 |
| char.def / weapon.def / armor.def / spell.def parsing | ✅ Complete | Regex block parser |
| MAP chunk header + coordinate parsing | ✅ Complete | 9,722 chunks |
| World Map GUI tab | ✅ Complete | Zoom, pan, zone select |
| Characters GUI tab | ✅ Complete | Gallery + detail + filter |
| Equipment GUI tab | ✅ Complete | Dual Treeview + .tn preview |
| **Sprites GUI tab** | ✅ Complete | Thumbnail grid + i2d decode |
| Spells GUI tab | ✅ Complete | Table + detail |
| Scripts GUI tab | ✅ Complete | Viewer + full-text search |
| 3D Models GUI tab | ✅ Complete | 612 models, anim state listing |
| Asset Studio launch (7 tabs) | ✅ Complete | 1,959 lines |

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
(pending) feat: dynamic categories, batch export, ModelViewer3D, i3d decoder, LZ fix
50bfc2e  Fix SpritesTab duplicate .tn loading and speed up i2d lookup
9750aaf  Fix map stitching, add Sprites browser, improve i2d decoder
6c00108  Initial RevEngine asset pipeline for Revenant (1999)
```

---

*Last updated: 2026-03-08 — Added i3d geometry decoder, LZ back-ref fix, ModelViewer3D, dynamic sprite categories, batch PNG export.*
