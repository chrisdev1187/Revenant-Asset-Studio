"""
RevEngine Setup Script
=======================
Installs dependencies and runs initial extraction pipeline.
Run this first before any other RevEngine tools.

Usage:
    py setup.py
"""

import subprocess
import sys
import os
from pathlib import Path

GAME_DIR    = Path("C:/GOG Games/Revenant")
EXTRACT_DIR = GAME_DIR / "_extracted"
ENGINE_DIR  = GAME_DIR / "RevEngine"

REQUIRED_PACKAGES = [
    "Pillow>=10.0.0",
    "numpy>=1.24.0",
]

def install_deps():
    print("[1/4] Installing Python dependencies...")
    subprocess.check_call([
        sys.executable, "-m", "pip", "install", "--quiet"
    ] + REQUIRED_PACKAGES)
    print("      Done.\n")

def extract_archives():
    print("[2/4] Extracting game archives...")

    archives = [
        ("resources.rvr", "resources"),
        ("imagery.rvi",   "imagery"),
    ]

    import zipfile
    for archive_name, out_name in archives:
        archive_path = GAME_DIR / archive_name
        out_dir      = EXTRACT_DIR / out_name

        if not archive_path.exists():
            print(f"      WARNING: {archive_name} not found")
            continue

        if out_dir.exists() and any(out_dir.iterdir()):
            print(f"      {archive_name}: already extracted, skipping")
            continue

        print(f"      Extracting {archive_name}...")
        out_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path, 'r') as zf:
            zf.extractall(out_dir)
        print(f"      Done: {len(list(out_dir.rglob('*')))} files")

    # Also extract map modules
    modules_dir = GAME_DIR / "Modules"
    for rvm in modules_dir.glob("*.rvm"):
        out_dir = EXTRACT_DIR / rvm.stem
        if out_dir.exists() and any(out_dir.iterdir()):
            continue
        print(f"      Extracting {rvm.name}...")
        out_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(rvm, 'r') as zf:
            zf.extractall(out_dir)

    print("      All archives extracted.\n")

def analyze_assets():
    print("[3/4] Analyzing extracted assets...")

    if not EXTRACT_DIR.exists():
        print("      No extracted files found - run extraction first")
        return

    all_files = list(EXTRACT_DIR.rglob('*'))
    file_files = [f for f in all_files if f.is_file()]

    ext_counts = {}
    for f in file_files:
        ext = f.suffix.lower()
        ext_counts[ext] = ext_counts.get(ext, 0) + 1

    print(f"\n      Asset inventory:")
    print(f"      {'Extension':<12} {'Count':>8}")
    print("      " + "-"*22)
    for ext, count in sorted(ext_counts.items(), key=lambda x: -x[1])[:15]:
        ready = "[ready]" if ext in ['.bmp','.mp3','.wav','.def','.s'] else "[needs decode]"
        print(f"      {ext or '(none)':<12} {count:>8}  {ready}")

    print(f"\n      Total: {len(file_files)} files")
    print()

def print_next_steps():
    print("[4/4] Next Steps:")
    print()
    print("  TEXTURES (.i2d/.i3d):")
    print("    Method: dgVoodoo2 + RenderDoc runtime capture")
    print("    Guide:  RevEngine/texture_extractor_guide.md")
    print()
    print("  AUDIO (.mp3/.wav):")
    print("    Status: READY - standard formats")
    print("    Location: _extracted/resources/Sound/")
    print()
    print("  MAP DATA (.DAT):")
    print("    Tool:   py RevEngine/map_parser.py --analyze")
    print("    World:  67x32 chunks, 32 vertical layers")
    print()
    print("  GAME SCRIPTS (.def):")
    print("    Status: READY - plain text format")
    print("    Contains: weapons, armor, spells, characters, items")
    print()
    print("  AI UPSCALING (after texture extraction):")
    print("    Tool:   RevEngine/upscale_pipeline.py (coming next)")
    print("    Method: Real-ESRGAN 4x via ComfyUI or standalone")
    print()
    print("  ENGINE PORT:")
    print("    Target: Unreal Engine 5 or Unity HDRP")
    print("    Map:    9722 chunks -> UE5 World Partition landscape")
    print()

if __name__ == '__main__':
    print("\n" + "="*60)
    print("  RevEngine - Revenant (1999) Asset Pipeline")
    print("  Game found at:", GAME_DIR)
    print("="*60 + "\n")

    install_deps()
    extract_archives()
    analyze_assets()
    print_next_steps()

    print("="*60)
    print("  Setup complete!")
    print("="*60 + "\n")
