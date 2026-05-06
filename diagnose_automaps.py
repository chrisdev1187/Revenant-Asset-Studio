#!/usr/bin/env python3
"""
diagnose_automaps.py — Report everything found in the Automaps directory.
Run this to diagnose missing zones in the world map viewer.

Usage:
    python diagnose_automaps.py
    python diagnose_automaps.py --game-dir "D:/Games/Revenant"
"""
import sys, argparse
from pathlib import Path
from collections import defaultdict

parser = argparse.ArgumentParser()
parser.add_argument("--game-dir", default="C:/GOG Games/Revenant")
parser.add_argument("--extract-dir", default="C:/Users/chris/OneDrive/Desktop/Revengine/extracted")
args = parser.parse_args()

game_dir    = Path(args.game_dir)
extract_dir = Path(args.extract_dir)
automap_dir = extract_dir / "Ahkuilon" / "Automaps"

print(f"Game dir:    {game_dir}")
print(f"Extract dir: {extract_dir}")
print(f"Automap dir: {automap_dir}")
print(f"Exists:      {automap_dir.exists()}")
print()

if not automap_dir.exists():
    print("ERROR: Automaps directory not found!")
    sys.exit(1)

# --- Subdirectory structure ---
print("=== SUBDIRECTORY STRUCTURE ===")
subdirs = [d for d in automap_dir.iterdir() if d.is_dir()]
flat_bmps = [f for f in automap_dir.iterdir() if f.is_file() and f.suffix.lower() == '.bmp']
print(f"Subdirectories ({len(subdirs)}): {[d.name for d in sorted(subdirs)]}")
print(f"BMP files in root ({len(flat_bmps)}): {[f.name for f in sorted(flat_bmps)[:10]]}")
print()

# --- Scan ALL bmp files recursively ---
print("=== ALL BMP FILES (recursive) ===")
all_bmps = list(automap_dir.rglob("*.bmp")) + list(automap_dir.rglob("*.BMP"))
print(f"Total BMP files found: {len(all_bmps)}")
print()

# Group by parent directory
by_dir = defaultdict(list)
for f in sorted(all_bmps):
    rel = f.relative_to(automap_dir)
    by_dir[str(f.parent.relative_to(automap_dir))].append(f.name)

for d, files in sorted(by_dir.items()):
    print(f"  [{d}] ({len(files)} files)")
    for fn in sorted(files)[:5]:
        print(f"    {fn}")
    if len(files) > 5:
        print(f"    ... and {len(files)-5} more")
print()

# --- Parse all filenames ---
print("=== FILENAME PARSING ANALYSIS ===")
parsed_ok   = []
parsed_fail = []

for f in sorted(all_bmps):
    stem  = f.stem
    parts = stem.split('_')
    rel   = str(f.relative_to(automap_dir))

    if len(parts) == 3:
        try:
            zone = int(parts[0])
            x    = int(parts[1])
            y    = int(parts[2])
            parsed_ok.append((zone, x, y, rel))
        except ValueError:
            parsed_fail.append((rel, f"parts={parts} — not all integers"))
    elif len(parts) == 2:
        try:
            x = int(parts[0])
            y = int(parts[1])
            parsed_fail.append((rel, f"ONLY 2 PARTS (x={x}, y={y}) — missing zone prefix?"))
        except ValueError:
            parsed_fail.append((rel, f"parts={parts} — 2 parts, not integers"))
    else:
        parsed_fail.append((rel, f"parts={parts} — unexpected count {len(parts)}"))

print(f"Parsed OK (zone_x_y format): {len(parsed_ok)}")
zones_found = sorted(set(z for z,x,y,_ in parsed_ok))
print(f"Zone numbers found: {zones_found}")
print()

print(f"Could NOT parse: {len(parsed_fail)}")
for rel, reason in parsed_fail[:20]:
    print(f"  {rel}: {reason}")
if len(parsed_fail) > 20:
    print(f"  ... and {len(parsed_fail)-20} more")
print()

# --- Per-zone tile counts ---
print("=== TILES PER ZONE ===")
zone_counts = defaultdict(int)
for z,x,y,_ in parsed_ok:
    zone_counts[z] += 1
for z in sorted(zone_counts):
    print(f"  Zone {z:3d}: {zone_counts[z]:4d} tiles")
