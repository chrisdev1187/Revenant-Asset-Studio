"""
RevEngine - Map/Level Parser
=============================
Parses Revenant (1999) map chunk files:
  .DAT  ->  Map tile/chunk data  ->  JSON + visualization

MAP Header Structure:
  0x00 - 0x03  : Magic "MAP " (0x4D415020)
  0x04 - 0x07  : Chunk format version (uint32 LE)
  0x08 - 0x09  : Unknown flags (uint16 LE)
  0x0A - 0x0B  : Tile count or flags (uint16 LE)
  0x0C+        : Chunk data blocks

Chunk naming convention: X_Y_Z.DAT
  X, Y = world grid coordinates
  Z    = vertical layer (altitude)
"""

import struct
import json
import os
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger('RevEngine.Map')

MAP_MAGIC = b'MAP '


@dataclass
class MapChunkCoord:
    x: int
    y: int
    z: int


@dataclass
class MapChunk:
    filepath: Path
    coord: MapChunkCoord
    version: int
    raw_size: int
    payload: bytes

    def to_dict(self):
        return {
            'file': self.filepath.name,
            'coord': asdict(self.coord),
            'version': self.version,
            'raw_size': self.raw_size,
        }


def parse_chunk_coord(filename: str) -> Optional[MapChunkCoord]:
    """Parse X_Y_Z.DAT filename into coordinates."""
    stem = Path(filename).stem
    parts = stem.split('_')
    if len(parts) == 3:
        try:
            return MapChunkCoord(
                x=int(parts[0]),
                y=int(parts[1]),
                z=int(parts[2])
            )
        except ValueError:
            pass
    return None


def parse_map_chunk(filepath: Path) -> Optional[MapChunk]:
    """Parse a single .DAT map chunk file."""
    try:
        data = filepath.read_bytes()
    except IOError as e:
        log.error(f"Cannot read {filepath}: {e}")
        return None

    if len(data) < 16:
        return None

    magic = data[0:4]
    if magic != MAP_MAGIC:
        log.warning(f"{filepath.name}: Not a MAP chunk (magic: {magic!r})")
        return None

    version = struct.unpack_from('<I', data, 4)[0]
    coord = parse_chunk_coord(filepath.name)
    if not coord:
        coord = MapChunkCoord(0, 0, 0)

    return MapChunk(
        filepath=filepath,
        coord=coord,
        version=version,
        raw_size=len(data),
        payload=data[16:],
    )


def load_all_chunks(map_dir: Path) -> List[MapChunk]:
    """Load all .DAT map chunks from a directory."""
    chunks = []
    dat_files = list(map_dir.rglob('*.DAT')) + list(map_dir.rglob('*.dat'))
    log.info(f"Found {len(dat_files)} map chunk files")

    for f in dat_files:
        chunk = parse_map_chunk(f)
        if chunk:
            chunks.append(chunk)

    return chunks


def analyze_map(map_dir: Path) -> Dict:
    """Analyze the full map and return bounds + statistics."""
    chunks = load_all_chunks(map_dir)

    if not chunks:
        return {}

    xs = [c.coord.x for c in chunks]
    ys = [c.coord.y for c in chunks]
    zs = [c.coord.z for c in chunks]

    analysis = {
        'total_chunks': len(chunks),
        'bounds': {
            'x': {'min': min(xs), 'max': max(xs)},
            'y': {'min': min(ys), 'max': max(ys)},
            'z': {'min': min(zs), 'max': max(zs)},
        },
        'layers': sorted(set(zs)),
        'world_size': {
            'width':  max(xs) - min(xs) + 1,
            'height': max(ys) - min(ys) + 1,
            'depth':  max(zs) - min(zs) + 1,
        },
        'versions': sorted(set(c.version for c in chunks)),
    }

    return analysis


def export_chunk_manifest(map_dir: Path, output_json: Path):
    """Export a JSON manifest of all map chunks for engine import."""
    chunks = load_all_chunks(map_dir)
    manifest = {
        'game': 'Revenant',
        'year': 1999,
        'format': 'MAP_DAT',
        'total_chunks': len(chunks),
        'chunks': [c.to_dict() for c in chunks],
    }

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(manifest, indent=2))
    log.info(f"Manifest written: {output_json} ({len(chunks)} chunks)")
    return manifest


def visualize_map_layer(chunks: List[MapChunk], z_layer: int,
                        output_path: Optional[Path] = None):
    """
    Generate a simple ASCII or image visualization of a map layer.
    Each chunk = one cell in the grid.
    """
    layer_chunks = [c for c in chunks if c.coord.z == z_layer]
    if not layer_chunks:
        print(f"No chunks found for Z layer {z_layer}")
        return

    xs = [c.coord.x for c in layer_chunks]
    ys = [c.coord.y for c in layer_chunks]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    coord_set = {(c.coord.x, c.coord.y) for c in layer_chunks}
    width  = max_x - min_x + 1
    height = max_y - min_y + 1

    print(f"\nMap Layer Z={z_layer}  ({width}x{height} chunks, "
          f"{len(layer_chunks)} populated)\n")

    # ASCII art map
    for y in range(min_y, max_y + 1):
        row = ""
        for x in range(min_x, max_x + 1):
            row += "█" if (x, y) in coord_set else "·"
        print(f"  {row}")

    print()

    # Try to generate a proper image if Pillow is available
    if output_path:
        try:
            from PIL import Image, ImageDraw
            CELL = 4
            img = Image.new('RGB', (width * CELL, height * CELL), (30, 30, 30))
            draw = ImageDraw.Draw(img)
            for c in layer_chunks:
                px = (c.coord.x - min_x) * CELL
                py = (c.coord.y - min_y) * CELL
                draw.rectangle([px, py, px+CELL-1, py+CELL-1], fill=(100, 200, 100))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(output_path)
            log.info(f"Map image saved: {output_path}")
        except ImportError:
            pass


if __name__ == '__main__':
    import argparse

    MAP_DIR = Path("C:/Users/chris/OneDrive/Desktop/Revengine/extracted/Ahkuilon/Map")

    parser = argparse.ArgumentParser(
        description='RevEngine Map Parser - Revenant 1999'
    )
    parser.add_argument('--map-dir', default=str(MAP_DIR))
    parser.add_argument('--analyze', action='store_true',
                        help='Print map analysis')
    parser.add_argument('--manifest', metavar='OUTPUT.json',
                        help='Export chunk manifest JSON')
    parser.add_argument('--visualize', metavar='Z_LAYER', type=int,
                        help='Visualize a specific Z layer')

    args = parser.parse_args()
    map_dir = Path(args.map_dir)

    if args.analyze:
        analysis = analyze_map(map_dir)
        import pprint
        pprint.pprint(analysis)

    if args.manifest:
        export_chunk_manifest(map_dir, Path(args.manifest))

    if args.visualize is not None:
        chunks = load_all_chunks(map_dir)
        visualize_map_layer(chunks, args.visualize,
                            output_path=Path(f"map_layer_z{args.visualize}.png"))
