# Test 1: Read a .TN file from Forest category
forest_dir = Path(r"C:\GOG Games\Revenant\_extracted\imagery\Imagery\Forest")
equip_dir = Path(r"C:\GOG Games\Revenant\_extracted\imagery\Imagery\Equip")
tn_forest = Path(r"C:\GOG Games\Revenant\_extracted\imagery\Thumbnails\Forest")
tn_equip = Path(r"C:\GOG Games\Revenant\_extracted\imagery\Thumbnails\Equip")

# Check sizes of first 10 .tn files in Forest and Equip thumbnails
print("=== Forest .TN sizes ===")
for f in sorted(tn_forest.iterdir())[:10]:
    if f.suffix.lower() == '.tn':
        data = f.read_bytes()
        print(f"  {f.name}: {len(data)} bytes")
        if len(data) == 768:
            print(f"    First 5 palette entries (RGB):")
            for i in range(5):
                r, g, b = data[i*3], data[i*3+1], data[i*3+2]
                print(f"      [{i}]: R={r}, G={g}, B={b}")
            # Count non-zero entries
            nonzero = sum(1 for i in range(256) if any(data[i*3:i*3+3]))
            print(f"    Non-zero entries: {nonzero}/256")

print()
print("=== Equip .TN sizes ===")
for f in sorted(tn_equip.iterdir())[:10]:
    if f.suffix.lower() == '.tn':
        data = f.read_bytes()
        print(f"  {f.name}: {len(data)} bytes")
        if len(data) == 768:
            nonzero = sum(1 for i in range(256) if any(data[i*3:i*3+3]))
            print(f"    Non-zero entries: {nonzero}/256")

# Test 2: Try decoding forbirch001.i2d with its .TN palette
print()
print("=== Decoding forbirch001 with .TN palette ===")
i2d_path = forest_dir / "forbirch001.i2d"
tn_path = tn_forest / "forbirch001.tn"
if not tn_path.exists():
    # Try case-insensitive search
    for f in tn_forest.iterdir():
        if f.stem.lower() == "forbirch001" and f.suffix.lower() == ".tn":
            tn_path = f
            break

print(f"i2d exists: {i2d_path.exists()}")
print(f"tn exists: {tn_path.exists()}")

if tn_path.exists():
    pal_data = tn_path.read_bytes()
    print(f"TN size: {len(pal_data)} bytes")
    print(f"First 5 palette entries:")
    for i in range(5):
        r, g, b = pal_data[i*3], pal_data[i*3+1], pal_data[i*3+2]
        print(f"  [{i:3d}]: #{r:02x}{g:02x}{b:02x} = ({r}, {g}, {b})")
    nonzero = sum(1 for i in range(256) if any(pal_data[i*3:i*3+3]))
    print(f"Non-zero palette entries: {nonzero}/256")
    
    # Print some non-zero entries to see if these look like green/brown (forest colors)
    print(f"All non-zero entries (first 20):")
    count = 0
    for i in range(256):
        r, g, b = pal_data[i*3], pal_data[i*3+1], pal_data[i*3+2]
        if r or g or b:
            print(f"  [{i:3d}]: #{r:02x}{g:02x}{b:02x} = ({r}, {g}, {b})")
            count += 1
            if count >= 20:
                break

# Test 3: Check alphagem TN 
print()
print("=== alphagem TN palette ===")
alphagem_tn = tn_equip / "alphagem.tn"
if not alphagem_tn.exists():
    for f in tn_equip.iterdir():
        if f.stem.lower() == "alphagem":
            alphagem_tn = f
            break

if alphagem_tn.exists():
    pal_data = alphagem_tn.read_bytes()
    print(f"TN size: {len(pal_data)} bytes")
    nonzero = sum(1 for i in range(256) if any(pal_data[i*3:i*3+3]))
    print(f"Non-zero palette entries: {nonzero}/256")
    print(f"First 20 non-zero entries:")
    count = 0
    for i in range(256):
        r, g, b = pal_data[i*3], pal_data[i*3+1], pal_data[i*3+2]
        if r or g or b:
            print(f"  [{i:3d}]: #{r:02x}{g:02x}{b:02x} = ({r}, {g}, {b})")
            count += 1
            if count >= 20:
                break
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

�
