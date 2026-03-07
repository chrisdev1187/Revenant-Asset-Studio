# Revenant Texture Extraction Guide
## dgVoodoo2 + RenderDoc Pipeline

### Why This Approach
The CGSR (.i2d/.i3d) format stores runtime DirectDraw 7 surface
descriptors DIRECTLY in the file. Values like 0x2088 and 0x1400
are embedded D3D flags/addresses — not parseable static offsets.

**The solution: capture textures AT RUNTIME as the engine loads them.**

---

## Step 1 — Setup dgVoodoo2

1. Download dgVoodoo2 from: https://github.com/dege-diosg/dgVoodoo2/releases
2. Copy these DLLs into `C:/GOG Games/Revenant/`:
   - DDraw.dll
   - D3DImm.dll
   - D3D8.dll (may not be needed)
3. Run dgVoodooCpl.exe, configure:
   - Resolution: 1920x1080 or higher
   - Windowed mode: YES (required for RenderDoc)
   - VRAM: 512 MB
   - DirectX feature level: 11 or 12

---

## Step 2 — Attach RenderDoc

1. Download RenderDoc: https://renderdoc.org/
2. Launch RenderDoc
3. Go to: File > Launch Application
4. Set executable: `C:/GOG Games/Revenant/Revenant.exe`
5. Working directory: `C:/GOG Games/Revenant/`
6. Capture settings:
   - API: D3D11 (dgVoodoo2 wraps to D3D11/12)
   - Auto capture: ON

---

## Step 3 — Capture and Export

1. Launch game through RenderDoc
2. Load into the game world (all zones you want textures from)
3. Press F12 (or configured key) to capture a frame
4. In RenderDoc: Texture Viewer
   - All loaded textures appear in the Resources panel
   - Filter by type: Texture2D
5. Export all: File > Export All > PNG/DDS

---

## What You'll Get
- All environment textures (cave, dungeon, town, forest...)
- All character textures
- All equipment/item sprites
- UI textures
- Already in correct RGB format, no decoding needed

---

## Alternative: Python D3D Hook (Advanced)

For automated extraction without manual RenderDoc steps:

```python
# Conceptual - requires C++ implementation
# Write a D3D7 wrapper DLL that:
# 1. Implements IDirectDraw7 interface
# 2. Intercepts CreateSurface() calls
# 3. When surface is Unlock()ed, save pixel data to file
# 4. Inject as DDraw.dll replacement
```

Tools for this:
- Microsoft Detours library (hook D3D7 calls)
- Or: use dgVoodoo2 with D3D11 and write a D3D11 texture capture shader

---

## What We Already Know About the Format

| Finding | Value |
|---------|-------|
| Archive format | ZIP (renamed .rvr/.rvi/.rvm) |
| CGSR magic | 0x43475352 "CGSR" |
| Header size | 84 bytes (0x54) |
| Texture format | 16-bit (ARGB1555 or RGB565) |
| Runtime flags at 0x68 | 0x2088 = D3D/DD surface capability flags |
| Frame name offset | 0x1C (null-terminated string) |
| Sprite dimensions | width @ 0x48, height @ 0x4A |
| Sprite world offset | x @ 0x4C, y @ 0x4E |
| Lighting tables | Stored in lower portion of file (color ramps) |
| BMP files | Standard Windows BMP, directly readable |
| Audio | Standard MP3/WAV, directly usable |
| Script files | Plain text .def and .s files |
| Map chunks | MAP magic at 0x00, coord in filename (X_Y_Z.DAT) |
