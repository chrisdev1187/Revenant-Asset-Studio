# Revenant Asset Studio

A reverse-engineered asset browser, viewer, and exporter for **Revenant (1999)** by Monolith Productions.

Built on research from nuxdie, MathJazz, and benjcooley.

---

## Feature Status

| Feature | Status | Notes |
|---|---|---|
| World maps & zones | ✅ Full | All automaps stitched, PNG export via file dialog |
| Sprite decode (.i2d) | ✅ 99.8% | Thumbnail browser, category filter, full decode; LZ cross-chunk history resolved |
| Character sheets | ✅ Full | Portraits, parsed stats from char.def, batch PNG export |
| Equipment (Weapons/Armor) | ✅ Full | Icons, stats; correct palette transparency + exact name matching |
| Spells | ✅ Full | Icon, talisman combos, variants, mana, damage type, animation link |
| Sounds | ✅ Full | 1,057 WAV effects + 6 MP3 speech + OGG music; 90+ category groups, filter + playback |
| Cinematix | ✅ Full | SMK FMV videos, playback via system player |
| 3D Models — geometry | ✅ Full | All 113 characters, skeletal assembly |
| 3D Models — animation | ✅ Full | All states/frames, scrubber + playback |
| 3D Models — textures | ✅ Full | Multi-texture, tiling UV, backface cull |
| 3D Models — glTF export | ✅ Full | Single mesh, scene-level rig, all animation clips |
| OBJ export | ✅ Full | Batch OBJ, static pose, normals, UVs, texture PNG |
| Scripts | ✅ Full | All .def files, cross-reference search, batch export |
| **UI Resources** | ✅ Full | All 60+ .dat UI files decoded; background preview + element tile grid; font glyph map; animation; batch export |
| **Ahkuilon / Zone Scripts** | ✅ Full | 9 zone scripts (.s) + definition files; syntax highlight; live 2D CUBE object map; batch export |
| **Menu bar** | ✅ Full | File / View / Export / Help; Settings dialog; keyboard shortcuts |
| **Unified export** | ✅ Full | Export Current Tab (Ctrl+E), per-type menu entries, Export All Assets |
| **Asset Upscaler** | ✅ Full | NVIDIA NIM FLUX.1-kontext-dev img2img batch upscale; prompt + strength controls; before/after review; flag/redo; Cinematix SMK→MP4 pipeline |
| **Modernize 3D** | ✅ Full | One-click pipeline: decode i3d → GPU upscale → Sobel normal/roughness → Blender CC subdivision + AO bake → PBR GLB with full rig + animations |
| Deathmatch zones (DM1–DM6) | ⏳ Planned | 6 MP maps with .chr character saves, scripts, automaps |
| Map chunk tiles | ⏳ Planned | 4,896 .DAT world geometry tiles (format TBD) |
| Playable character textures | ⏳ Deferred | Known broken; requires separate investigation |

---

## Changelog

### 2026-05-12 — Tab fixes, sound categorisation, texture export

**Bug fixes — tab rendering**
- **Sprites tab:** `_load_tn_image`, `GRID_COLS`, `THUMB_SIZE`, `CELL_W`, `CELL_H` were imported inside `__init__` (function-local scope), making them invisible to all other methods. Moved to module-level import — thumbnails and decoded i2d sprites now display correctly.
- **UI Resources tab:** `_decode_dat_frame` typo fixed → `decode_dat_frame`; frames now decode and preview correctly.
- **3D Models tab:** `log` was never imported into `models.py`; the background worker thread called `log.info(...)` before any try/except, silently killing the thread before `_update` could run. Fixed: `import logging` + `log = logging.getLogger("RevEngine.Models")` added. Models now load and render.
- **Cinematix tab:** `Path("Disk2")` was a relative path resolved from CWD, not the game directory. Replaced with `game_dir / "Disk2"` plus additional search paths (`Movies`, `Cinematix`, `Video`).
- **World Map tab:** `_all_automap_dirs` / `_get_unextracted_modules` don't exist in `parsers.py` (no underscore prefix). Fixed to aliased imports.

**Sounds tab — complete rewrite**
- **Root cause:** `_load_all` called `snd_dir.iterdir()` which yields the `effects/` directory object itself — all 1,057 WAV files inside it were silently skipped.
- **Fix:** explicit `eff_dir.glob("*.wav")` after resolving `Sound/effects/`.
- **Categorisation:** 90+ prefix → category mappings covering Player (Locke), named NPCs (Bayne, Morganna, …), human enemies, undead, beasts, bosses, magic/spells, combat SFX, environment, doors/containers, items, and UI. Longest-prefix-first matching ensures specificity.
- **UI:** Category combobox dropdown filter; text filter box; sounds sorted by (category, filename); status bar shows file count and category count.

**Blender detection**
- `_detect_blender()` now scans `C:\Program Files\Blender Foundation\Blender*\blender.exe` when `blender` is not on `PATH` (the Windows installer does not add it). Picks highest-version install. Confirmed working with Blender 5.1.

**glTF / GLB texture export — three-path fix**
- **Godot exporter** (`core/godot_exporter.py`): was passing `[]` as the textures argument to `export_gltf`. Now calls `decode_i3d_textures(i3d_path)` and passes the result.
- **Models tab Export glTF** (`ui/tabs/models.py`): was reading `_viewer._textures` which could be stale if texture load failed at model-select time. Now decodes textures fresh from `geom.path` at export time. Also saves a `_diffuse.png` sidecar alongside every `.gltf` for manual use in Blender.
- **Modernize pipeline** (`asset_studio_modernize.py` + `tools/modernize_pipeline.py`): Blender headless cannot reliably unpack data-URI textures from an imported glTF during GLB re-export. Fix: always extract the decoded texture to a real PNG file (`_diffuse_raw.png`) and pass it to Blender via `--upscaled-tex`. `_swap_texture` in the Blender script now also builds a full Principled BSDF node tree from scratch if the glTF import created no Image Texture node.

### 2026-05-09 — Bug fixes

- **Models tab — textured mode default:** 3D viewer now opens in Textured mode by default (was Shaded). All embedded DirectDraw textures display immediately on model selection without requiring a mode switch.
- **ncnn upscaler — model file layout fix:** `realesrgan-ncnn-vulkan` expects model weights at `models/<name>.param` relative to the exe. Zip extraction and/or OneDrive sync were stripping the `models/` subdirectory and truncating filenames. Fixed: correct directory structure documented and restored; `_detect_ncnn()` now falls back to a glob pattern (`*ncnn-vulkan*.exe`) to survive future naming drift.
- **Zip extraction robustness:** `_install_ncnn_worker` now validates whether the zip has a top-level directory before stripping it, preventing filename corruption on flat-structured archives.

### 2026-05-09 — Modernize 3D pipeline

- **New "Modernize 3D" tab:** One-click pipeline converts any Revenant `.i3d` file into a modern, PBR-textured, rigged, animated `.glb` — no manual Blender work required.
- **6-step fully automated pipeline:**
  1. **Decode** — reads `.i3d` geometry + embedded texture via existing decoders
  2. **Export base glTF** — writes correct local-space bone transforms (world-space bug fixed in `gltf_export.py`)
  3. **GPU texture upscale** — `realesrgan-ncnn-vulkan` (Vulkan binary, works on Nvidia/AMD/Intel via Vulkan API, ~2–5 s on GPU). Falls back to PIL LANCZOS if binary not installed.
  4. **Normal map** — Sobel gradient from upscaled diffuse → tangent-space normal PNG (`decoders/pbr_maps.py`)
  5. **Roughness map** — inverted luminance, clamped to [0.50–1.00] (`decoders/pbr_maps.py`)
  6. **Blender headless** — merge-by-distance (fixes UV-split blob bug) → Catmull-Clark subdivision (401→5,835 verts for acolyte at levels=2) → shade smooth → AO bake (Cycles 64 spp) → wire normal + roughness into BSDF → export GLB with full rig + all 40+ animation clips
- **GPU selector:** WMI-detected adapter list (Nvidia/AMD/Intel) + CPU-only fallback. Combobox with refresh button; CPU mode uses 600 s timeout.
- **Real-time progress bar + timestamped log:** Each pipeline step streams Blender stdout line-by-line into the log. Stop button terminates the Blender subprocess cleanly.
- **Browse opens in Chars folder:** File dialog starts at `extracted/imagery/Imagery/Chars/` (622 `.i3d` files available).
- **Key bug fix — bone transforms:** `gltf_export.py` was writing world-space transforms on all hierarchy nodes; glTF requires local-space. Fixed: `local = world_mat × parent_world_inv`. Applied to both bind pose and all animation channels.
- **Key bug fix — CC subdivision:** UV-seam split vertices (same XYZ, different UV, topologically disconnected) were averaging to centroid → blob. Fixed with `mesh.remove_doubles(threshold=1e-5)` before applying Catmull-Clark.
- **New files:** `asset_studio_modernize.py`, `decoders/pbr_maps.py`, `tools/modernize_pipeline.py`, `UPSCALING_101.md`

### 2026-05-08 — FLUX NIM upscaler
- **Replaced Real-ESRGAN with NVIDIA NIM FLUX.1-kontext-dev:** The Asset Upscaler tab now calls the NVIDIA NIM cloud API (`black-forest-labs/flux.1-kontext-dev`) for all static asset enhancement. FLUX.1-kontext-dev preserves structural identity while adding epic lighting, colour depth, and cinematic detail — ideal for retro game assets.
- **Configurable prompt + negative prompt:** Free-text fields in the left panel default to a retro-fantasy prompt. Both fields accept any text and are used for batch runs and individual redos.
- **Strength / creativity slider:** 0.45 → 0.85. Maps to FLUX guidance scale (1.5–5.0) and inference steps (20–40). Low strength = faithful; high strength = creative.
- **`.env` support:** API key is loaded from `.env` at launch via `python-dotenv`. A key status badge (✓/✗) in the left panel reflects availability without requiring a restart.
- **Cinematix SMK→MP4 pipeline:** Video frames use PIL LANCZOS fast-resize (FLUX skipped — per-frame API calls would be prohibitively slow). Output: `renders/upscaled/cinematix/<stem>_{scale}x.mp4`.
- **Tiny-sprite bypass:** Assets ≤32 px use `PIL.NEAREST` (FLUX over-smooths at tiny resolutions).

### 2026-05-07 — Asset Upscaler
- **Asset Upscaler tab:** New tab batch-upscales all game asset categories. Categories: UI Panels (`.dat` frames), Equipment Icons, Talisman Icons, Model Textures (`.i3d` embedded), Sprites (`.i2d` clean), and Cinematix FMV. Assets ≤32 px are upscaled with `PIL.NEAREST ×4`. Output written to `renders/upscaled/<category>/`.
- **Results review window:** Vertical scrollable card list shows every processed asset with before/after thumbnails, filename, resolution delta, and status badge (ok / flagged / failed). Selecting a card opens a side-by-side compare view. Individual assets can be re-queued via **Redo**; **Redo Flagged** batch-reruns all flagged items.
- **Cinematix SMK→MP4 pipeline:** FFmpeg extracts frames at 15 fps → upscale → FFmpeg re-encodes to H.264 CRF 18. Searches `GOG Games/Revenant/Disk2` and `GAME_DIR` automatically.
- **FFmpeg auto-installer:** Detects FFmpeg in `tools/ffmpeg.exe`, `PATH`, and common install locations. Downloads the BtbN win64-lgpl build (~25 MB) if missing.

### 2026-05-07
- **Menu bar + Settings dialog:** Added File / View / Export / Help menu bar. Settings dialog (Ctrl+,) allows changing Game Dir, Extract Dir, and Renders Dir with JSON persistence (`revengine.json`). Keyboard shortcuts: Ctrl+Q quit, Ctrl+E export current tab, F1 about.
- **Unified export menu:** Export → Export Current Tab (Ctrl+E) dispatches to whichever tab is active. Per-type entries for Characters, Equipment, Sprites, Spells, Scripts, Models, UI Resources, Ahkuilon. Export All Assets runs every exporter in sequence.
- **UI Resources tab:** New tab browsing all 60+ CGSR `.dat` UI files from `extracted/resources/`. Decoded using a fixed `_decode_dat_frame` scan (was capped at 16 bytes — broke `credits.dat` / `splash.dat` whose TBitmapData sits at offset 2064). Layout: resizable PanedWindow with background preview (top, max 2× upscale) + element tile grid (bottom, 80 px cells). Background frame auto-detected as largest by area. Font files (≥20 glyphs all ≤24×32 px) render as a 16-column glyph map. Optional frame animation. Batch PNG export.
- **`_bgr555_fast`:** New module-level helper decodes BGR555 16-bit pixel data via numpy vectorised bit-ops (near-instant for 640×480 frames); falls back to pure Python when numpy is absent.
- **Ahkuilon tab:** New tab for the 9 zone script directories. Script viewer with syntax highlight (block, trigger, action, command, property, number, string, comment). Live 2D canvas map — parses all `CUBE` trigger volumes from each `.s` file and plots centroid dots with hover labels. Batch export of scripts and map images.
- **`.dat` decoder scan-range fix:** `_decode_dat_frame` now scans the entire frame payload instead of only the first 16 bytes; added bounds guard before pixel extraction. Fixes `credits.dat`, `splash.dat`, and any other single-outer-frame files.

### 2026-05-06 — LZ cross-chunk history fix
- **i2d.py — major sprite fix:** Resolved the long-standing LZ back-reference limitation.
  1,859 of 2,224 compressed sprites had pixel regions that decoded as transparent because
  LZ `dist` values caused the source address `di − dist − 4` to go negative (before the
  start of the current chunk's buffer).

  **Root cause (confirmed from `chunkcache.cpp` source):** `chunkbuffer[]` is a flat
  `malloc(N × 4096)` C array. When the ASM's `sub edi, dist; sub edi, 4` produces a
  negative offset, it reads from the previous slot — which holds the same sprite's
  prior chunk (slots are allocated sequentially per sprite). The decoder had no
  equivalent of this "previous slot."

  **Fix:** `_decode_chunk` now accepts a `history` bytearray (concatenated decoded
  chunk outputs for the current sprite). Negative LZ positions resolve into history
  instead of returning 0. Empty chunks contribute 4096 zero bytes to preserve slot
  alignment. Result: **2,623 / 2,627 sprites decode correctly (99.8%), zero regressions.**
  Previously-transparent holes in LZ-referenced regions now render with correct colours.

### 2026-05-06
- **World Map:** Save PNG now opens a file dialog instead of saving to a hardcoded path. Removed broken "Export All Zones" and "Diagnose" buttons.
- **Equipment icons:** Fixed purple/magenta backgrounds — palette index 0 is now treated as transparent (RGBA). Fixed wrong icons caused by over-permissive name matching; now uses exact-first then shortest-prefix.
- **Spells tab:** Complete rework — shows spell icon, description, mana, damage type, and full variant list with talisman icon chains per variant.
- **Sounds tab:** New tab listing all 1,743 SFX/voice MP3s and OGG music tracks with name filter and one-click playback.
- **Cinematix tab:** New tab listing all 4 SMK FMV files with file size and playback via system handler.
- **Models — animation state:** Fixed texture reset when switching animation states; stored textures and face_tex_indices are now preserved across `viewer.load()` calls.
- **glTF export:** Fixed fragmentation — was exporting one mesh primitive per texture group (100+ objects in Blender); now exports a single primitive with a single material.
- **glTF export:** Fixed missing rig — bones were children of the mesh node causing Blender to nest armature inside mesh; bones are now scene-level siblings of the mesh node.
- **i2d.py:** Fixed LZ back-reference implementation — code was copying from the compressed payload stream; corrected to copy from the decompressed `chunk_buf` as the format spec requires.

---

<img width="1391" height="906" alt="Screenshot 2026-03-13 012323" src="https://github.com/user-attachments/assets/5bb20886-8bc4-4798-9142-64883903bbfc" />
<img width="1397" height="905" alt="Screenshot 2026-03-13 01223811" src="https://github.com/user-attachments/assets/dd3fae42-b7fe-40d8-9cae-486ab87f8f54" />
<img width="1388" height="907" alt="Screenshot 2026-03-13 012208" src="https://github.com/user-attachments/assets/81eda89f-5208-4e03-8ed0-964a203d654f" />

---

## Setup

Requires **Python 3.10+**.

```bash
pip install -r requirements.txt
```

This installs: `Pillow`, `numpy`, `openai` (NIM client), `python-dotenv`.

### NVIDIA NIM API key (required for the Upscaler tab)

1. Get a free key at **https://build.nvidia.com** (free tier includes 1,000 credits)
2. Create `.env` in the project root:

```
NVIDIA_API_KEY=nvapi-...
```

The key status badge in the Upscaler left panel turns green when the key is detected.

Clone into any directory — **not** inside the game folder:

```
C:\<anywhere>\Revengine\
```

### 1 — Extract game archives

```bash
python archive_extractor.py
# Default game dir: C:\GOG Games\Revenant
# Output:           Revengine\extracted\
```

Extracts `.rvr` / `.rvi` / `.rvm` archives (all standard ZIP with renamed extensions).
Run once; subsequent launches skip already-extracted files.

### 2 — Launch the studio

```bash
python asset_studio.py
```

Override the game directory at launch:

```bash
python asset_studio.py --game-dir "D:\Games\Revenant"
```

---

## 3D Model Viewer

The **Models** tab renders Revenant's `.i3d` skeletal character models (113 total).

### Render modes

| Mode | Description |
|---|---|
| **Shaded** | Two-pass Phong-lit flat shading with depth sort |
| **Textured** | Per-triangle affine UV mapping from embedded DirectDraw atlas (RGB565); tiling UVs supported |

- Drag to rotate · Scroll to zoom
- Backface culling enabled in textured mode

### Animation controls

- **State combobox** — lists all named animation states with frame count, e.g. `leftwalk ×24f`
- **Frame scrubber** — active for multi-frame states
- **Play / Stop** — loops at configurable FPS
- **Bind pose** entry always restores the reference skeleton

### Multi-texture models

Characters such as `locke`, `morganna`, `navarro`, `bayne`, and `darkrevenant` carry 2–5 separate DirectDraw textures (body, face, armour plates, accessories). The renderer assigns each face group to its correct texture slot automatically.

### Example models

| Model | Verts | Faces | States | Textures | Bones |
|---|---|---|---|---|---|
| acolyte.i3d | 401 | 486 | 41 | 1 | 22 |
| locke.i3d | 477 | 593 | 352 | 5 | 21 |
| morganna.i3d | 349 | 501 | 327 | 5 | 21 |
| navarro.i3d | 442 | 487 | 307 | 5 | 21 |
| darkrevenant.i3d | 528 | 649 | 43 | 5 | 21 |
| kantha.i3d | 503 | 632 | 29 | 1 | 27 |
| skeleton.i3d | 344 | 573 | 25 | 1 | 22 |
| arakna.i3d | 337 | 342 | 44 | 1 | 46 |
| bluedragon.i3d | 681 | 753 | 30 | 1 | 27 |

---

## Export

### OBJ Export

Exports the current animation pose as Wavefront OBJ with normals, UVs, and an MTL + PNG sidecar when texture data is available. Loads directly into Blender, MeshLab, etc.

### glTF 2.0 Export (Rigged + Animated)

Click **Export glTF** in the Models tab to export a fully rigged, animated `.gltf` file. The export runs in a background thread and shows live progress in the status bar.

The output file is **self-contained** (all geometry, textures, and animation data embedded as base64 data URIs).

**What's included:**

| Component | Detail |
|---|---|
| Skinned mesh | POSITION, NORMAL, TEXCOORD_0, JOINTS_0, WEIGHTS_0 |
| Skeleton | Full bone hierarchy as glTF nodes (inverse bind matrices included) |
| Bone assignment | Hard single-bone per vertex (weight = 1.0) — matches Revenant's engine |
| Animation clips | Every animation state exported as a named glTF animation |
| Keyframe data | Per-bone TRS (translation, rotation as quaternion, scale) per frame |
| Textures | All embedded textures encoded as PNG data URIs inside the .gltf |
| Materials | One PbrMetallicRoughness material per texture slot |

**Import into Blender 3.x+:**

1. File → Import → glTF 2.0
2. Select the exported `.gltf`
3. All animation states appear in the Action Editor / NLA Editor
4. Press **Z → Material Preview** (or the sphere icon top-right of the 3D viewport) to see the texture — Blender's default Solid mode hides materials

A `_diffuse.png` sidecar is saved alongside every `.gltf` export in case you need to manually assign the texture in the Shader Editor.

**Export times** (approximate, i7-class CPU):

| Model | States | Time |
|---|---|---|
| acolyte.i3d | 41 | ~1 s |
| darkrevenant.i3d | 43 | ~1 s |
| locke.i3d | 352 | ~15 s |

---

## Asset Upscaler

The **Upscale** tab provides a fully automated AI enhancement pipeline for every asset category in the game, powered by **NVIDIA NIM FLUX.1-kontext-dev**.

### How it works

Each asset is:
1. Decoded to a PIL Image (existing decoders — unchanged)
2. Pre-scaled to the target resolution (2× or 4× of original, clamped to 2048 px, aligned to 64-px grid)
3. Encoded as a PNG data URI and submitted to the NIM endpoint
4. The response image (b64_json) is decoded back to RGBA PNG and saved

FLUX.1-kontext-dev is an image-editing model that preserves structural identity while enriching lighting, colour, and surface detail — producing "alive" results that respect the original retro design.

### Asset categories

| Category | Source files | Method | Output |
|---|---|---|---|
| UI Panels | `extracted/resources/*.dat` | FLUX ×2/×4 | PNG per frame |
| Equipment Icons | `Thumbnails/Equip/*.tn` | FLUX ×2/×4 | PNG 64+ px |
| Talisman Icons | `Thumbnails/Magic/*.tn` | FLUX ×2/×4 | PNG 64+ px |
| Model Textures | `Imagery/Chars/**/*.i3d` | FLUX ×2/×4 | PNG per slot |
| Sprites | `Imagery/**/*.i2d` (LZ-clean) | FLUX ×2/×4 | PNG |
| Cinematix FMV | `Disk2/*.smk` | FFmpeg + PIL LANCZOS + FFmpeg | H.264 MP4 |

Assets ≤32 px bypass FLUX and receive `PIL.NEAREST` resize (FLUX over-smooths tiny pixel art). Video frames use PIL LANCZOS — running a cloud API call per frame is impractical.

### Controls

| Control | Values | Effect |
|---|---|---|
| **Scale** | 2×, 4× | Target resolution multiplier |
| **Strength** | 0.45 – 0.85 | Maps to FLUX guidance (1.5–5.0) and steps (20–40). Low = faithful; high = creative |
| **FLUX Prompt** | free text | Describes the desired enhancement style |
| **Negative prompt** | free text | Suppresses unwanted artefacts |

### Output layout

```
renders/upscaled/
├── ui_panels/          <stem>_f<n>.png  per dat frame
├── equip_icons/        <stem>.png
├── talisman_icons/     <stem>.png
├── model_textures/     <stem>_t<n>.png  per texture slot
├── sprites/            <stem>.png
└── cinematix/          <stem>_{scale}x.mp4
```

### Before/after review

Every processed asset appears in the scrollable results list with status badge:

| Badge | Meaning |
|---|---|
| **ok** | Accepted |
| **flagged** | Marked for redo |
| **failed** | Decode or API error |

Click any card to open the side-by-side compare view. Use **Flag** → **Redo** to reprocess a single item, or **Redo Flagged** to batch-redo all flagged items with a different strength or prompt.

### Dependencies

- **openai** Python package (`pip install openai`) — NIM API client
- **python-dotenv** — auto-loads `NVIDIA_API_KEY` from `.env`
- **NVIDIA NIM API key** — free tier at https://build.nvidia.com
- **FFmpeg** — auto-installed to `tools/ffmpeg.exe` via in-app downloader (Cinematix only)

---

## File Format Reference

### Archive formats

| Extension | Type | Notes |
|---|---|---|
| `.rvr` | Resources | Characters, spells, scripts |
| `.rvi` | Imagery | Sprites, models, thumbnails |
| `.rvm` | Map/module | Zone data, automaps |

All three are standard ZIP files with renamed extensions.

### CGSR file header

```
FileResHdr (20 bytes):
  [0:4]   'CGSR' magic
  [4:6]   topbm     (uint16)
  [6]     comptype  (0 = uncompressed)
  [7]     version   (1)
  [8:12]  datasize
  [12:16] objsize
  [16:20] hdrsize   — size of SImageryHeader (excludes FileResHdr itself)

SImageryHeader at offset 20:
  [0:4]   imageryid  (int32)
  [4:8]   numstates  (int32)
  [8 + i*76]  SImageryStateHeader[i]:
    [0:32]  animname[32]
    [32:36] OFFSET walkmap
    [36:40] DWORD flags
    [40:42] short aniflags
    [42:44] short frames   ← animation frame count

Body base = 20 + hdrsize
```

### S3DImageryBody (new format, flag 0x10)

```
[0]   DWORD flags
[4]   DWORD version
[8]   OS3DImageryState   statedata    (TOffset)
[12]  int   numverts
[16]  OOOD3DVERTEX verts              (3-level TOffset chain)
[20]  int   numfaces
[24]  OS3DFace faces                  (1-level TOffset)
[28]  int   nummaterials
[32]  OD3DMATERIAL materials          (TOffset)
[36]  int   numtextures
[40]  OS3DImageryTexture textures     (TOffset)
[44]  int   numobjects
[48]  OS3DImageryObject objects       (TOffset)
[52]  int   numtags
[56]  OS3DImageryTag tags             (TOffset)
```

**D3DVERTEX (32 bytes):** `x,y,z` (12) + `nx,ny,nz` (12) + `tu,tv` (8)

**S3DFace (6 bytes):** `WORD v1, v2, v3` — **local** indices per object. Global index = local + `object.vertpos`.

### S3DImageryObject (48 bytes)

```
[0:32]  char name[32]
[32:34] WORD material
[34:36] WORD vertpos    — first vertex in global buffer
[36:38] WORD vertnum    — vertex count for this object (bone)
[38:40] WORD pad
[40:44] OS3DImageryObjectTexture textures  (TOffset → face group array)
[44:48] OS3DImageryObjectState   states    (TOffset → animation state array)
```

### S3DImageryObjectTexture (4 bytes)

```
WORD facepos, WORD facenum
textures[0]   = no-texture face group
textures[1..N] = face groups for embedded textures 0..N-1
```

### S3DImageryObjectState (12 bytes)

```
[0:4]  int  parent        — parent object index (−1 = root)
[4:8]  int  numanikeys
[8:12] OSAniKey32 anikeys — TOffset to SAniKey32 stream
```

### SAniKey32 animation format

Revenant uses **skeletal animation**: vertices are stored once in bone-local space; each state+frame supplies per-bone TRS keys.

```
Frame 0:  CODE keys (t=0, codes 2–10)
  POSX/POSY/POSZ: 24-bit signed integer ÷ 256  → float position
  ROTX/ROTY/ROTZ: 24-bit signed integer ÷ 256  → float radians
  SCLX/SCLY/SCLZ: 24-bit signed integer ÷ 256  → float scale

Frames 1–N: packed 10-bit keys, grouped by channel
  bits  0– 1: type  (1=POS, 2=ROT, 3=SCL)
  bits  2–11: x  (10-bit signed)
  bits 12–21: y  (10-bit signed)
  bits 22–31: z  (10-bit signed)

Scales: POS ÷ 4,  ROT ÷ (512/π),  SCL ÷ 64

No NEXTFRAME markers — packed keys are stored consecutively per channel.
rot_packed[k] → frame k+1.
```

Bone hierarchy resolved depth-first; `world_matrix = local_matrix × parent_world_matrix`.

### S3DImageryTexture (120 bytes)

```
[0:108]  DDSURFACEDESC desc
   +8    dwHeight, +12 dwWidth
   +76   DDPIXELFORMAT:
     +76 dwFlags      (DDPF_RGB=0x40, DDPF_PALETTEINDEXED8=0x20)
     +84 dwRGBBitCount
     +88/92/96  R/G/B masks
[108:112] OFFSET bits  → TOffset to frame OFFSET array → pixel data
[112:116] OFFSET pals  → X1R5G5B5 palette (palettized only)
[116:120] int frames
```

Character models use **RGB565** (16-bit, R=0xF800, G=0x07E0, B=0x001F).

### TOffset (self-relative int32)

```
_deref(raw, field_pos) = field_pos + int32_at(field_pos)
```

A stored value of 0 is a null pointer (do not dereference).

---

## Module Overview

```
Revengine/
├── asset_studio.py              Entry point for the Studio application
├── asset_studio_modernize.py    "Modernize 3D" tab logic
├── archive_extractor.py         Batch ZIP extractor for .rvr/.rvi/.rvm
├── map_parser.py                Zone/tile map parser
├── archaeology.py               Low-level format archaeology helpers
│
├── core/                        Business logic & centralized state
│   ├── config.py                Centralized configuration (paths, settings)
│   ├── constants.py             UI theme, data mappings, and PIL status
│   ├── parsers.py               Revenant-specific data and asset location logic
│   └── godot_exporter.py        Godot systematic porting pipeline
│
├── ui/                          Tkinter graphical user interface
│   ├── app.py                   Main window and notebook orchestration
│   ├── widgets.py               Shared UI components (StatusBar, ScrollFrame)
│   └── tabs/                    Module-per-tab logic
│       ├── godot_export.py      Systematic porting & modernization management
│       └── ...                  (World Map, Characters, Models, etc.)
│
├── decoders/                    Low-level format decoders
│   ├── i3d.py                   .i3d skeletal model decoder
│   ├── i2d.py                   .i2d sprite decoder
│   ├── gltf_export.py           glTF 2.0 conversion
│   └── pbr_maps.py              Sobel-based PBR map generation
│
├── tools/                       Automation & external scripts
│   └── modernize_pipeline.py    Blender headless modernization script
│
├── UPSCALING_101.md             Research doc: pipeline design and findings
└── REVENANT_REVERSE_ENGINEERING.md Authorities technical record
```

---

## Logging

All modules emit structured log output via Python's `logging` module at these levels:

| Level | When |
|---|---|
| `DEBUG` | Per-file format decisions (new vs old body, state/frame) |
| `INFO` | Model loaded (vert/face/state/bone counts), glTF milestones |
| `WARNING` | Decode returned None, unexpected format variants |
| `ERROR` | File read failures, unrecoverable parse errors |

Default level is `INFO`. To see debug output:

```python
import logging
logging.getLogger("RevEngine").setLevel(logging.DEBUG)
```

Or from the command line:

```bash
python -c "import logging; logging.basicConfig(level=logging.DEBUG)" asset_studio.py
```

Logger hierarchy:
- `RevEngine.Studio` — asset_studio.py
- `RevEngine.Modernize` — asset_studio_modernize.py
- `RevEngine.i3d` — decoders/i3d.py
- `RevEngine.glTF` — decoders/gltf_export.py
- `RevEngine.Extractor` — archive_extractor.py

---

## Modernize 3D

The **Modernize 3D** tab is a fully automated old-to-modern pipeline that takes any Revenant `.i3d` file and outputs a production-ready `.glb` with smooth geometry, PBR textures, and all animations intact.

### What it produces

| Asset | 1999 Original | Modernized Output |
|---|---|---|
| Geometry | ~400–600 verts, hard edges | ~5,000–8,000 verts, smooth CC mesh |
| Texture | 128×128 RGB565 | 512×512+ PNG (4× GPU upscaled) |
| Surface maps | None (flat diffuse only) | Normal map + Roughness map + AO map |
| Rig | Rigid single-bone-per-vertex | Same skeleton, preserved |
| Animations | 40+ SAniKey32 states | All states exported to GLB |

### Pipeline steps

```
.i3d file
  │
  ▼  ~0.1s
decode_i3d_geometry() + decode_i3d_textures()
  → geometry (verts, faces, bones, animations)
  → PIL Image 128×128 diffuse
  │
  ▼  ~0.5s
export_gltf()  — local-space bone transforms (glTF-correct)
  → base .gltf
  │
  ▼  ~2–5s  (GPU)
realesrgan-ncnn-vulkan  -n realesrgan-x4plus-anime  -s 4
  → upscaled_diffuse.png  512×512
  │
  ▼  ~0.2s
generate_normal_map(strength=2.0)   [decoders/pbr_maps.py]
generate_roughness_map()            [decoders/pbr_maps.py]
  → normal.png + roughness.png
  │
  ▼  ~30s
Blender 5.x headless               [tools/modernize_pipeline.py]
  ├── merge-by-distance (weld UV-split verts)
  ├── Catmull-Clark subdivision levels=2
  ├── Shade smooth
  ├── Swap in upscaled diffuse
  ├── Wire normal + roughness → BSDF material nodes
  ├── AO bake (Cycles, 512×512, 64 spp)
  └── Export GLB (mesh + skin + all animations + all maps)
  │
  ▼
{model}_modern.glb   ✓ rigged  ✓ animated  ✓ PBR textured

Sidecar files:
  {model}_diffuse.png     upscaled 512×512
  {model}_normal.png      Sobel-generated
  {model}_roughness.png   luminance-inverted
  {model}_ao.png          Cycles-baked
```

**Total time: ~35–45 seconds per model on any Vulkan-capable GPU.**

### GPU support

The upscaler binary (`realesrgan-ncnn-vulkan`) runs on Nvidia, AMD, and Intel GPUs via the Vulkan API — no CUDA required. A CPU-only fallback is also available (significantly slower — ~5–10 minutes per texture).

Install the binary via the Upscale tab → "Install to project" button, or place `realesrgan-ncnn-vulkan.exe` in `tools/realesrgan-ncnn/`.

### Options

| Option | Default | Notes |
|---|---|---|
| Subdivide levels | 2 | 1 = subtle, 3–4 = very heavy (slow Blender bake) |
| Upscale | 4× | Uses anime model — best for hand-painted game textures |
| Normal map strength | 2.0 | 1.0–4.0; higher = more pronounced surface detail |
| AO resolution | 512 | 256 for speed, 1024 for quality |
| GPU | Auto | WMI-detected; includes per-adapter index + CPU fallback |

See `UPSCALING_101.md` for full research findings, tool comparisons, and known gaps.

---

## HD Remake Pipeline

The glTF export (Models tab) or the full modernized GLB (Modernize 3D tab) feed directly into a standard HD remake workflow:

```
Revengine  →  Modernize 3D  →  .glb  →  Blender / Godot 4 / Unreal
```

**Quick path (Modernize 3D tab):**
1. Select any `.i3d` from `extracted/imagery/Imagery/Chars/`
2. Click **Run** — ~40 seconds
3. Open output `.glb` in Blender, Godot 4, or any glTF-capable engine
4. Full skeleton + all animations available in the NLA Editor / AnimationPlayer

**Manual path (glTF export from Models tab):**
1. Export any character → `.gltf`
2. Import into Blender (File → Import → glTF 2.0)
3. Retopologise, re-skin, enhance textures against the original rig
4. Export to target engine

The bone hierarchy, parent indices, inverse bind matrices, and per-frame TRS keyframes are all faithfully reproduced from the original SAniKey32 streams.

---

## Acknowledgements

- [benjcooley/Revenant](https://github.com/benjcooley/Revenant) — C++ source reference
- [IgorZyktin/Revenant](https://github.com/IgorZyktin/Revenant)
- [depy/RevenantRE](https://github.com/depy/RevenantRE)
- nuxdie, MathJazz — original format research

![CodeRabbit Pull Request Reviews](https://img.shields.io/coderabbit/prs/github/chrisdev1187/Revenant-Asset-Studio?utm_source=oss&utm_medium=github&utm_campaign=chrisdev1187%2FRevenant-Asset-Studio&labelColor=171717&color=FF570A&link=https%3A%2F%2Fcoderabbit.ai&label=CodeRabbit+Reviews)
