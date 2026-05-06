# Revenant Asset Studio

A reverse-engineered asset browser, viewer, and exporter for **Revenant (1999)** by Monolith Productions.

Built on research from nuxdie, MathJazz, and benjcooley.

---

## Feature Status

| Feature | Status | Notes |
|---|---|---|
| World maps & zones | ✅ 100% | All automaps stitched, PNG export |
| Sprite decode (.i2d) | ✅ 90% | Thumbnail browser, category filter |
| Character sheets | 🔄 50% | Parsed from char.def |
| 3D Models — geometry | ✅ Full | All 113 characters, skeletal assembly |
| 3D Models — animation | ✅ Full | All states/frames, scrubber + playback |
| 3D Models — textures | ✅ Full | Multi-texture, tiling UV, backface cull |
| 3D Models — glTF export | ✅ Full | Rigged mesh + all animation clips |
| OBJ export | ✅ | Static pose, normals, UVs, texture PNG |
| Equipment | 🔄 WIP | |
| Spells | 🔄 WIP | |
| Scripts | 🔄 50% | .def cross-reference search |

---

<img width="1391" height="906" alt="Screenshot 2026-03-13 012323" src="https://github.com/user-attachments/assets/5bb20886-8bc4-4798-9142-64883903bbfc" />
<img width="1397" height="905" alt="Screenshot 2026-03-13 01223811" src="https://github.com/user-attachments/assets/dd3fae42-b7fe-40d8-9cae-486ab87f8f54" />
<img width="1388" height="907" alt="Screenshot 2026-03-13 012208" src="https://github.com/user-attachments/assets/81eda89f-5208-4e03-8ed0-964a203d654f" />

---

## Setup

Requires **Python 3.10+** and **Pillow**.

```bash
pip install pillow
```

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

**Export times** (approximate, i7-class CPU):

| Model | States | Time |
|---|---|---|
| acolyte.i3d | 41 | ~1 s |
| darkrevenant.i3d | 43 | ~1 s |
| locke.i3d | 352 | ~15 s |

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
├── asset_studio.py          Main GUI application (Tkinter)
├── archive_extractor.py     Batch ZIP extractor for .rvr/.rvi/.rvm
├── map_parser.py            Zone/tile map parser
├── export_zone_maps.py      CLI: batch-export automap zones to PNG
├── diagnose_automaps.py     Automap tile diagnostic tool
├── archaeology.py           Low-level format archaeology helpers
│
└── decoders/
    ├── i3d.py               .i3d skeletal model decoder (geometry + animation)
    │                          decode_i3d_geometry()   — full mesh + rig
    │                          decode_i3d_textures()   — all embedded textures
    │                          load_state()            — animate in-place
    │                          list_anim_states()      — state names only
    │                          export_obj()            — Wavefront OBJ writer
    ├── gltf_export.py       glTF 2.0 exporter (skinned mesh + animation clips)
    │                          export_gltf()
    ├── i2d.py               .i2d sprite decoder
    └── cgsr.py              CGSR header parser (shared)
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
- `RevEngine.i3d` — decoders/i3d.py
- `RevEngine.glTF` — decoders/gltf_export.py
- `RevEngine.Extractor` — archive_extractor.py

---

## HD Remake Pipeline

The glTF export is designed as the first stage of a full HD remake pipeline:

```
Revengine  →  glTF 2.0  →  Blender  →  HD mesh/rig  →  Godot 4 / Unreal
```

1. Export any character from the Models tab → `.gltf`
2. Import into Blender 3.x+ (File → Import → glTF 2.0)
3. The full skeleton and all animation clips are available in the NLA Editor
4. Retopologise, re-skin, and enhance textures against the original rig
5. Export from Blender to the target engine

The bone hierarchy, parent indices, inverse bind matrices, and per-frame TRS keyframes are all faithfully reproduced from the original SAniKey32 streams.

---

## Acknowledgements

- [benjcooley/Revenant](https://github.com/benjcooley/Revenant) — C++ source reference
- [IgorZyktin/Revenant](https://github.com/IgorZyktin/Revenant)
- [depy/RevenantRE](https://github.com/depy/RevenantRE)
- nuxdie, MathJazz — original format research

![CodeRabbit Pull Request Reviews](https://img.shields.io/coderabbit/prs/github/chrisdev1187/Revenant-Asset-Studio?utm_source=oss&utm_medium=github&utm_campaign=chrisdev1187%2FRevenant-Asset-Studio&labelColor=171717&color=FF570A&link=https%3A%2F%2Fcoderabbit.ai&label=CodeRabbit+Reviews)
