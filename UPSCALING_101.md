# Upscaling 101 — RevEngine Research & Pipeline Doc

> **Purpose**: Capture all findings, decisions, and gaps from the Old-to-Modern 3D model
> modernization project. Use this as the source of truth before opening any code.

---

## 1. The Problem: 1999-Era Asset Limitations

Revenant (1999) ships with assets designed for late-90s hardware:

| Asset | 1999 Spec | Modern Expectation |
|---|---|---|
| Geometry | 400–600 vertices, irregular triangulation | 5,000–10,000 verts, smooth topology |
| Textures | 128×128 px, 16-bit RGB565, no mipmaps | 512×512+ px, RGBA PNG, PBR maps |
| Rigging | Rigid: one bone per vertex (no blend weights) | Smooth: weighted multi-bone blending |
| Animations | 40+ states, SAniKey32 delta-compressed keyframes | Same (preserved as-is) |
| Surface info | Everything baked into one flat diffuse | Separate albedo / normal / roughness / metallic / AO |
| Normals | Flat-shaded per triangle | Smooth interpolated per vertex |

No PBR maps exist — they must be generated or baked.

---

## 2. Geometry Modernization — Findings

### 2.1 Subdivision Approach

| Approach | Result | Verdict |
|---|---|---|
| Catmull-Clark (no pre-processing) | Character collapses into a blob | ✗ Broken |
| SIMPLE subdivision | Shape preserved, no smoothing | ~ Usable but dull |
| CC + merge-by-distance first | Smooth geometry, shape intact | ✓ Correct |

**Root cause of the blob**: Revenant meshes use split vertices at UV seams — same XYZ
position, different UV coordinates, topologically disconnected. Catmull-Clark averages
all disconnected vertices toward the centroid = sphere/blob.

**Fix**: `bpy.ops.mesh.remove_doubles(threshold=1e-5)` in Edit Mode before applying CC.
- acolyte.i3d: 108 coincident vertices welded
- Result: 401 verts → 5,835 verts (14.5× at levels=2)

### 2.2 Bone Transform Bug (Fixed)

**Symptom**: After Blender roundtrip, character had detached limbs and distorted mesh.

**Root cause** (found in `decoders/gltf_export.py`):
- Bone nodes in the glTF hierarchy were storing **world-space** transforms
- glTF spec requires **local-space** transforms; readers compound the hierarchy
- Result: every non-root bone was at `parent_world × child_world` instead of `child_world`

**Fix** (applied to `gltf_export.py`):
```python
# Before (wrong): stored world matrix on every node
node["translation"] = _mat_translation(world_mat)

# After (correct): compute local = world × parent_world_inv
local_mat = _mat_mul(world_mat, _mat_inv4(parent_world_mat))
node["translation"] = _mat_translation(local_mat)
```
Same fix applied to animation channels (all 40+ states × all bones × all frames).

### 2.3 Matrix Convention Note

Revenant uses **row-vector / Direct3D convention**: `v_out = v_in @ M`.

glTF uses **column-vector / OpenGL convention**: stored as column-major MAT4.

The inverse bind matrices (IBM) were already correctly transposed in the exporter
(comment existed). The node TRS was not — now fixed.

---

## 3. Texture Upscaling Research

### 3.1 Tools Evaluated

| Tool | Speed | Quality | Automated | Notes |
|---|---|---|---|---|
| Python Real-ESRGAN (CPU) | 20+ min | Excellent | Yes | Wrong path — used CPU |
| **realesrgan-ncnn-vulkan** | **~2–5 sec GPU** | **Excellent** | **Yes** | **Already in RevEngine UpscaleTab — USE THIS** |
| PIL LANCZOS | Instant | Acceptable | Yes | Fallback only |
| Materialize (GUI) | Manual | Best (PBR) | No | Use for manual polish after pipeline |
| SD ControlNet | Slow | Creative | Partial | Requires server setup |

**Key finding**: RevEngine's `UpscaleTab` already ships `realesrgan-ncnn-vulkan.exe`
(Vulkan binary, works on any GPU via Vulkan API — not CUDA-specific).
The 20-minute run was a mistake — we invoked the Python CPU version instead.

### 3.2 ESRGAN Model Selection

| Model | Best for |
|---|---|
| `realesrgan-x4plus-anime` | Hand-painted textures (characters, props) ← **default for Revenant** |
| `realesrgan-x4plus` | Photo-realistic / detailed textures |
| `realesrnet-x4plus` | Faster, slightly lower quality |

### 3.3 ncnn-vulkan Binary Location

```
ENGINE_DIR / "tools" / "realesrgan-ncnn" / "realesrgan-ncnn-vulkan.exe"
```
Install via RevEngine Upscale tab → "Install to project" button (downloads ~30 MB zip).
Fallback: `shutil.which("realesrgan-ncnn-vulkan")` for system-wide installs.

---

## 4. Normal Map Generation Research

### 4.1 Options

| Method | Quality | Speed | Automated | Dependencies |
|---|---|---|---|---|
| **Python Sobel (ours)** | Good | Instant | Yes | Pillow + numpy |
| Materialize | Excellent | Manual | No (GUI) | Windows app |
| xNormal (from geometry) | Best | ~5 min | Partial | GUI + high-poly mesh |
| SD ControlNet | Creative | ~30 sec | Partial | ComfyUI server |
| NormalMap-Online | Good | Browser | No | Manual upload |

### 4.2 Sobel Algorithm (Implemented in `decoders/pbr_maps.py`)

```
diffuse → greyscale → Gaussian blur (r=1) → central-difference Sobel:
  dX[:, 1:-1] = (H[:, 2:] - H[:, :-2]) * 0.5
  dY[1:-1, :] = (H[2:, :] - H[:-2, :]) * 0.5
→ normalize([-dX*strength, -dY*strength, 1.0])
→ encode: R=(Nx+1)/2, G=(Ny+1)/2, B=Nz  (DirectX tangent-space)
```

Recommended `strength`: 1.5–2.5 for character armor/cloth.

### 4.3 Materialize Workflow (Manual Polish Path)

1. Open Materialize (download: https://boundingboxsoftware.com/materialize/)
2. File → Open Diffuse → load upscaled PNG
3. Create Height Map: Pre-Contrast "Mids", Frequency medium, Shape Recognition on
4. Create Normal Map: Source = Height + Diffuse, Strength ~1.5
5. Export all maps as PNG
6. Drop into model's output folder → pipeline picks them up on re-run

---

## 5. PBR Map Strategy

| Map | Source | Method | File |
|---|---|---|---|
| Albedo / Diffuse | i3d embedded texture | 4× ncnn-vulkan upscale | `{model}_diffuse.png` |
| Normal | Generated | Sobel from upscaled diffuse | `{model}_normal.png` |
| Roughness | Generated | Inverted luminance (0.4–1.0) | `{model}_roughness.png` |
| Metallic | Constant | 0.0 (fantasy = non-metal) | (embedded in material) |
| AO | Baked | Blender Cycles headless, 512px, 64spp | `{model}_ao.png` |

All maps are wired into the Blender BSDF material before GLB export:
- Normal → `ShaderNodeNormalMap` → BSDF Normal
- Roughness → BSDF Roughness
- AO → multiplied over Base Color (optional, handled by viewer)

---

## 6. Full Automated Pipeline

```
.i3d file
  │
  ▼  Step 1 (~0.1s)
decode_i3d_geometry() + decode_i3d_textures()
  → I3DGeometry (401 verts, 22 bones, 41 anims)
  → PIL Image 128×128 diffuse
  │
  ▼  Step 2 (~0.5s)
export_gltf()  [decoders/gltf_export.py]
  → base .gltf with correct LOCAL bone transforms
  │
  ▼  Step 3 (~2–5s on GPU)
realesrgan-ncnn-vulkan  -n realesrgan-x4plus-anime  -s 4
  → upscaled_diffuse.png  512×512
  │
  ▼  Step 4 (~0.2s)
generate_normal_map(upscaled_diffuse, strength=2.0)  [decoders/pbr_maps.py]
  → normal.png  512×512
  │
  ▼  Step 5 (~0.1s)
generate_roughness_map(upscaled_diffuse)  [decoders/pbr_maps.py]
  → roughness.png  512×512
  │
  ▼  Step 6 (~30s)
Blender 5.1 headless  [tools/modernize_pipeline.py]
  ├── Import .gltf
  ├── merge-by-distance (weld 108 coincident verts)
  ├── Catmull-Clark subdivision levels=2  (401 → 5,835 verts)
  ├── Shade smooth
  ├── Swap in upscaled diffuse texture
  ├── Wire normal + roughness into BSDF material
  ├── AO bake (Cycles, 512×512, 64spp)
  └── Export .glb (mesh + skin + 41 animations + all maps)
  │
  ▼
{model}_modern.glb  ✓ rigged  ✓ animated  ✓ PBR textured

Sidecar files:
  {model}_diffuse.png   (upscaled 512×512)
  {model}_normal.png    (Sobel generated)
  {model}_roughness.png (luminance inverted)
  {model}_ao.png        (Blender baked)
```

**Total time**: ~35–45 seconds per model on Nvidia GPU.

---

## 7. RevEngine Integration

### ModernizeTab UI

New tab `"  Modernize 3D  "` in the main notebook:

```
┌──────────────────────────────────────────────────────────────┐
│ World Map │ Characters │ 3D Models │ ... │ Modernize 3D       │
├──────────────────────────────────────────────────────────────┤
│ LEFT (240px)                    │ RIGHT (expands)            │
│                                 │                            │
│ Model: [____________] [Browse]  │ Step 3/6 — Upscaling...   │
│ Output:[____________] [Browse]  │ ████████░░░░░░░  50%       │
│ ─────────────────────────────  │                            │
│ [✓] Subdivide    levels: [2]   │ 20:31:02 [OK] Decoded      │
│ [✓] Upscale      scale:  [4x]  │           acolyte.i3d      │
│ [✓] Normal map   str:  [2.0]   │           401v 22b 41a     │
│ [✓] Bake AO      res: [512]    │ 20:31:03 [OK] Exported     │
│ ─────────────────────────────  │           base gltf 187KB  │
│ [▶ Run]  [⏹ Stop]  [📁 Open]   │ 20:31:04 [..] Upscaling    │
│                                 │           128×128→512×512  │
└──────────────────────────────────────────────────────────────┘
```

### Files

| File | Role |
|---|---|
| `decoders/pbr_maps.py` | Sobel normal + roughness generation |
| `decoders/glb_patch.py` | Binary GLB PBR map injection (fallback) |
| `tools/modernize_pipeline.py` | Blender headless script (updated with PBR wiring) |
| `asset_studio_modernize.py` | `ModernizeTab` class |
| `asset_studio.py` | +2 lines to register the new tab |

---

## 8. Gaps — Future Research Needed

| Gap | Priority | Notes |
|---|---|---|
| Materialize CLI / watch-folder | High | Best normal quality; could poll output folder |
| xNormal high-to-low bake | Medium | Better normals from subdivided geometry |
| UV repacking (xAtlas) | Medium | Double effective texture res before upscaling |
| Per-bone blend weights | Medium | True smooth skinning; requires mesh rebind |
| Displacement maps | Low | Geometry nodes in Blender; complex |
| SD ControlNet texture gen | Low | Requires ComfyUI server |
| LOD generation | Low | Decimate modifier for game engine export |
| Batch pipeline (all characters) | High | Loop over extracted/imagery/Imagery/Chars/*.i3d |

---

## 9. Quick Reference — Commands

```powershell
# Regenerate a single model gltf (Python, in-repo)
cd C:\Users\chris\OneDrive\Desktop\Revengine
python -c "
from decoders.i3d import decode_i3d_geometry, decode_i3d_textures
from decoders.gltf_export import export_gltf
from pathlib import Path
i3d = Path('extracted/imagery/Imagery/Chars/acolyte.i3d')
export_gltf(decode_i3d_geometry(i3d), decode_i3d_textures(i3d), Path('test_renders/acolyte_full.gltf'))
"

# Run full modernize pipeline (Blender headless)
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" `
  --background --python tools/modernize_pipeline.py -- `
  --input  test_renders/acolyte_full.gltf `
  --output test_renders_hd/acolyte_modern.glb `
  --levels 2 --ao-size 512

# Launch RevEngine UI
python asset_studio.py
```
