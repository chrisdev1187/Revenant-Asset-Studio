import struct
from pathlib import Path

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
