# Revenant Asset Studio

A reverse-engineered asset browser and viewer for **Revenant (1999)** by Monolith Productions.

Built on research from nuxdie, MathJazz, and benjcooley.

---

## Current State

| Feature | Status |
|---|---|
| World maps & zones | ✅ 100% |
| Sprite decode (.i2d) | ✅ 90% |
| Character sheets | 🔄 50% |
| 3D Models (.i3d) — geometry | ✅ Full skeletal assembly (sessions 1–10b) |
| 3D Models (.i3d) — textures | ✅ Sidecar .bmp UV-textured rendering (session 11) |
| Equipment | 🔄 WIP |
| Spells | 🔄 WIP |
| Scripts | 🔄 50% |

---

## Setup

Requires Python 3.10+ and Pillow.

```bash
pip install pillow
```

Place the tool in your Revenant install directory, e.g.:

```
C:\GOG Games\Revenant\RevEngine\
```

Run:

```bash
python asset_studio.py
```

---

## 3D Model Viewer

The Models tab renders Revenant's `.i3d` skeletal character models with:

- **17-bone skeletal assembly** — all body parts (head, torso, limbs, feet)
- **1100+ faces** per character (Rubold: 476 verts / 1135 faces)
- **Upright orientation** — characters stand upright (X-axis = body length)
- **Two render modes:**
  - **Shaded** — two-pass Phong-lit flat shading with depth sort
  - **Textured** — UV-mapped texture from sidecar `.bmp` (auto-detected)
- **Animation states** — 23–352 named states per character
- Drag to rotate · Scroll to zoom

### Decoded models

| Model | Verts | Faces | States |
|---|---|---|---|
| Rubold.i3d | 476 | 1135 | 23 |
| Skeleton.i3d | 344 | 1163 | 25 |
| Druhg.i3d | 334 | 1209 | 33 |
| Jhaga.i3d | 349 | 1188 | 16 |
| Hopper.i3d | 289 | 708 | 16 |
| Kantha.i3d | 503 | 1497 | 29 |

---

## File Format Notes

See `REVENANT_REVERSE_ENGINEERING.md` for full binary format documentation including:

- CGSR file header layout
- 8-section object table
- 17-bone skeleton structure
- Vertex buffer format (stride 32: XYZ + Normal + UV)
- Face pool with `field_A` pointer for per-bone face tables
- Animation state header (76-byte records)

---

## Thanks

- [benjcooley/Revenant](https://github.com/benjcooley/Revenant) — C++ source reference
- [IgorZyktin/Revenant](https://github.com/IgorZyktin/Revenant)
- [depy/RevenantRE](https://github.com/depy/RevenantRE)
