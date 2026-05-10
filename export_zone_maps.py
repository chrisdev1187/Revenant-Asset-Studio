#!/usr/bin/env python3
"""
export_zone_maps.py — Batch export all Revenant automap zones to PNG.

Usage:
    python export_zone_maps.py
    python export_zone_maps.py --game-dir "D:/Games/Revenant"
    python export_zone_maps.py --game-dir "D:/Games/Revenant" --out my_maps/
    python export_zone_maps.py --zone 0          # export one zone only
    python export_zone_maps.py --list            # list available zones

Output PNGs are written to:
    <game_dir>/RevEngine/test_renders/world_map_zone<N>.png
(or --out directory if specified)
"""

import sys
import argparse
from pathlib import Path

# Allow running from the repo root without installing
sys.path.insert(0, str(Path(__file__).parent))

from core.config import Config
from core.parsers import stitch_zone_map, get_all_zone_keys, get_automap_tiles


def main():
    config = Config(Path(__file__).resolve().parent)
    parser = argparse.ArgumentParser(
        description="Batch-export Revenant automap zones to PNG."
    )
    parser.add_argument(
        "--game-dir", metavar="PATH",
        help="Path to Revenant install (default: C:/GOG Games/Revenant)"
    )
    parser.add_argument(
        "--out", metavar="DIR",
        help="Output directory (default: <game>/RevEngine/test_renders/)"
    )
    parser.add_argument(
        "--zone", metavar="N", type=int, default=None,
        help="Export a single zone number instead of all zones"
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List available zones and exit"
    )
    args = parser.parse_args()

    if args.game_dir:
        config.game_dir = Path(args.game_dir)

    stitch_fn   = lambda z: stitch_zone_map(config, z)
    zones_fn    = lambda: [z for m, z in get_all_zone_keys(config)]
    tiles_fn    = lambda z: get_automap_tiles(config, z)
    renders_dir = config.renders_dir

    out_dir = Path(args.out) if args.out else renders_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    zones = zones_fn()
    if not zones:
        print("ERROR: No automap tiles found.")
        sys.exit(1)

    if args.list:
        print(f"Available zones ({len(zones)}):")
        for z in zones:
            tiles = tiles_fn(z)
            print(f"  Zone {z:3d} — {len(tiles):4d} tiles")
        sys.exit(0)

    targets = [args.zone] if args.zone is not None else zones

    print(f"Output directory: {out_dir}")
    print(f"Exporting {len(targets)} zone(s)…\n")

    ok = skipped = 0
    for z in targets:
        tiles = tiles_fn(z)
        print(f"  Zone {z:3d} — {len(tiles):4d} tiles … ", end="", flush=True)
        img = stitch_fn(z)
        if img is None:
            print("SKIP (no tiles or PIL missing)")
            skipped += 1
            continue
        out = out_dir / f"world_map_zone{z}.png"
        img.save(out)
        print(f"saved  {img.width}x{img.height}px → {out.name}")
        ok += 1

    print(f"\nDone: {ok} exported, {skipped} skipped.")
    print(f"Files in: {out_dir}")


if __name__ == "__main__":
    main()
