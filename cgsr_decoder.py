"""
RevEngine - CGSR Format Decoder
================================
Decodes Revenant (1999) proprietary CGSR image format:
  .i2d  ->  2D sprites/textures  ->  PNG
  .i3d  ->  3D model data        ->  OBJ + MTL

CGSR Header Structure (84 bytes):
  0x00 - 0x03  : Magic "CGSR" (0x43475352)
  0x04 - 0x07  : Type flags [type_byte, 0x00, 0x00, version]
  0x08 - 0x0B  : Data size (uint32 LE)
  0x0C - 0x0F  : Uncompressed size (uint32 LE)
  0x10 - 0x11  : Header size = 0x54 = 84 bytes (uint16 LE)
  0x12 - 0x13  : Flags (uint16 LE)
  0x14 - 0x17  : Sub-type / render flags (uint32 LE)
  0x18 - 0x1B  : Frame count (uint32 LE)
  0x1C - 0x3F  : Frame name (null-terminated string, padded to 36 bytes)
  0x40 - 0x53  : Sprite/bounds info block (varies by type)
  0x54+        : Actual data payload
"""

import struct
import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Tuple
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger('RevEngine')

CGSR_MAGIC = b'CGSR'
HEADER_SIZE = 0x54  # 84 bytes

# Known type byte values from .i2d vs .i3d
TYPE_2D = 0x01  # .i2d - sprite/texture
TYPE_3D = 0x00  # .i3d - 3D model


@dataclass
class CGSRHeader:
    magic: bytes          # 'CGSR'
    type_byte: int        # 0x01=2D, 0x00=3D
    version: int          # usually 0x01
    data_size: int        # size of data after header
    uncompressed_size: int
    header_size: int      # should be 0x54
    flags: int
    sub_type: int
    frame_count: int
    frame_name: str       # animation/frame name (e.g. "still", "start")
    # Sprite bounds (i2d specific)
    width: int = 0
    height: int = 0
    x_offset: int = 0
    y_offset: int = 0
    data_offset: int = 0  # offset within file to pixel data


@dataclass
class CGSRFile:
    filepath: Path
    header: CGSRHeader
    raw_data: bytes
    frames: List[bytes] = field(default_factory=list)


def parse_header(data: bytes) -> Optional[CGSRHeader]:
    """Parse the 84-byte CGSR header."""
    if len(data) < HEADER_SIZE:
        log.error("File too small for CGSR header")
        return None

    magic = data[0:4]
    if magic != CGSR_MAGIC:
        log.error(f"Not a CGSR file (magic: {magic!r})")
        return None

    type_byte = data[4]
    version   = data[7]
    data_size, uncompressed_size = struct.unpack_from('<II', data, 8)
    header_size, flags           = struct.unpack_from('<HH', data, 16)
    sub_type, frame_count        = struct.unpack_from('<II', data, 20)

    # Frame name: null-terminated string at 0x1C, padded to 36 bytes
    name_raw = data[0x1C:0x40]
    frame_name = name_raw.split(b'\x00')[0].decode('ascii', errors='replace')

    # Bounds block at 0x40 (sprite dimensions for i2d)
    # Based on header analysis:
    # +0x04: width  (uint16)
    # +0x06: height (uint16)
    # +0x08: x_offset (uint16)
    # +0x0A: y_offset (uint16)
    # +0x0C: data_offset (uint32)
    bounds_base = 0x40
    width, height, x_off, y_off = struct.unpack_from('<HHHH', data, bounds_base + 4)
    data_off = struct.unpack_from('<I', data, bounds_base + 12)[0]

    return CGSRHeader(
        magic=magic,
        type_byte=type_byte,
        version=version,
        data_size=data_size,
        uncompressed_size=uncompressed_size,
        header_size=header_size,
        flags=flags,
        sub_type=sub_type,
        frame_count=frame_count,
        frame_name=frame_name,
        width=width,
        height=height,
        x_offset=x_off,
        y_offset=y_off,
        data_offset=data_off,
    )


def load_cgsr(filepath: Path) -> Optional[CGSRFile]:
    """Load and parse a CGSR file (.i2d or .i3d)."""
    try:
        raw = filepath.read_bytes()
    except IOError as e:
        log.error(f"Cannot read {filepath}: {e}")
        return None

    header = parse_header(raw)
    if not header:
        return None

    payload = raw[HEADER_SIZE:]
    return CGSRFile(filepath=filepath, header=header, raw_data=payload)


def decode_i2d_to_png(cgsr: CGSRFile, output_path: Path) -> bool:
    """
    Attempt to decode a .i2d CGSR sprite to PNG.

    Pixel format: The game used 16-bit color (RGB565 or ARGB1555)
    based on late-90s Direct3D conventions.

    We'll try multiple interpretations and pick the one that
    produces valid-looking output.
    """
    try:
        from PIL import Image
    except ImportError:
        log.error("Pillow not installed. Run: pip install Pillow")
        return False

    h = cgsr.header

    if h.width == 0 or h.height == 0:
        log.warning(f"Zero dimensions in {cgsr.filepath.name}, skipping")
        return False

    # The pixel data starts after the header and any per-frame offset table
    # data_offset is the offset from the start of the payload (post-header)
    payload = cgsr.raw_data

    # Try to find pixel data using the data_offset field
    pixel_start = h.data_offset if h.data_offset > 0 else 0

    # Calculate expected sizes for different pixel formats
    num_pixels = h.width * h.height
    size_16bit = num_pixels * 2
    size_32bit = num_pixels * 4
    size_8bit  = num_pixels

    available = len(payload) - pixel_start

    log.debug(f"  {cgsr.filepath.name}: {h.width}x{h.height}, "
              f"payload={len(payload)}, pixel_start={pixel_start}, "
              f"available={available}, need_16bit={size_16bit}")

    # Try RGB565 (most common for late-90s D3D)
    if available >= size_16bit:
        pixels_raw = payload[pixel_start:pixel_start + size_16bit]
        img = rgb565_to_image(pixels_raw, h.width, h.height)
        if img:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(output_path)
            log.info(f"  Saved: {output_path.name} ({h.width}x{h.height} RGB565)")
            return True

    # Try ARGB1555
    if available >= size_16bit:
        pixels_raw = payload[pixel_start:pixel_start + size_16bit]
        img = argb1555_to_image(pixels_raw, h.width, h.height)
        if img:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(output_path)
            log.info(f"  Saved: {output_path.name} ({h.width}x{h.height} ARGB1555)")
            return True

    log.warning(f"  Could not decode {cgsr.filepath.name} "
                f"(available={available}, need={size_16bit})")
    return False


def rgb565_to_image(data: bytes, width: int, height: int):
    """Convert raw RGB565 bytes to PIL Image."""
    from PIL import Image
    pixels = []
    for i in range(0, len(data) - 1, 2):
        word = struct.unpack_from('<H', data, i)[0]
        r = ((word >> 11) & 0x1F) << 3
        g = ((word >> 5)  & 0x3F) << 2
        b = (word         & 0x1F) << 3
        pixels.append((r, g, b))

    if len(pixels) < width * height:
        return None

    img = Image.new('RGB', (width, height))
    img.putdata(pixels[:width * height])
    return img


def argb1555_to_image(data: bytes, width: int, height: int):
    """Convert raw ARGB1555 bytes to PIL Image with transparency."""
    from PIL import Image
    pixels = []
    for i in range(0, len(data) - 1, 2):
        word = struct.unpack_from('<H', data, i)[0]
        a = 255 if (word >> 15) else 0
        r = ((word >> 10) & 0x1F) << 3
        g = ((word >> 5)  & 0x1F) << 3
        b = (word         & 0x1F) << 3
        pixels.append((r, g, b, a))

    if len(pixels) < width * height:
        return None

    img = Image.new('RGBA', (width, height))
    img.putdata(pixels[:width * height])
    return img


def dump_i3d_info(cgsr: CGSRFile) -> dict:
    """
    Parse .i3d 3D model data and return structure info.
    The i3d format stores named sub-objects (parts) with geometry.
    """
    h = cgsr.header
    payload = cgsr.raw_data

    info = {
        'name': cgsr.filepath.stem,
        'frame_name': h.frame_name,
        'frame_count': h.frame_count,
        'data_size': h.data_size,
        'sub_objects': []
    }

    # Scan for named sub-object markers in the payload
    # The header shows object names like "#fire", "fgey" at specific offsets
    # These appear to be at fixed offsets described in an offset table
    offset = 0
    while offset < len(payload) - 4:
        # Look for sub-object name markers (# prefix or named chunks)
        if payload[offset:offset+1] == b'#':
            name_end = payload.index(b'\x00', offset)
            obj_name = payload[offset:name_end].decode('ascii', errors='replace')
            info['sub_objects'].append({'name': obj_name, 'offset': offset})
        offset += 1

    return info


def batch_extract_i2d(input_dir: Path, output_dir: Path) -> Tuple[int, int]:
    """Extract all .i2d files from input_dir to output_dir as PNGs."""
    success = 0
    failed = 0

    i2d_files = list(input_dir.rglob('*.i2d')) + list(input_dir.rglob('*.I2D'))
    log.info(f"Found {len(i2d_files)} .i2d files to process")

    for i2d_path in i2d_files:
        rel = i2d_path.relative_to(input_dir)
        out_path = output_dir / rel.with_suffix('.png')

        cgsr = load_cgsr(i2d_path)
        if cgsr and decode_i2d_to_png(cgsr, out_path):
            success += 1
        else:
            failed += 1

    return success, failed


def print_cgsr_info(filepath: Path):
    """Print detailed CGSR header info for debugging."""
    cgsr = load_cgsr(filepath)
    if not cgsr:
        return

    h = cgsr.header
    print(f"\n{'='*60}")
    print(f"File:     {filepath.name}")
    print(f"Type:     {'2D Sprite' if h.type_byte == TYPE_2D else '3D Model'}")
    print(f"Version:  {h.version}")
    print(f"Frame:    '{h.frame_name}' (count: {h.frame_count})")
    print(f"Size:     {h.data_size} bytes (uncompressed: {h.uncompressed_size})")
    print(f"Flags:    0x{h.flags:04X}  SubType: 0x{h.sub_type:08X}")
    if h.type_byte == TYPE_2D:
        print(f"Dims:     {h.width} x {h.height} pixels")
        print(f"Offset:   ({h.x_offset}, {h.y_offset})")
        print(f"DataOff:  0x{h.data_offset:04X} ({h.data_offset})")
    print(f"Payload:  {len(cgsr.raw_data)} bytes")


# ─── CLI Entry Point ────────────────────────────────────────────────────────

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='RevEngine CGSR Decoder - Revenant 1999 asset extractor'
    )
    subparsers = parser.add_subparsers(dest='command')

    # info command
    info_p = subparsers.add_parser('info', help='Print CGSR header info')
    info_p.add_argument('file', help='Path to .i2d or .i3d file')

    # extract command
    ext_p = subparsers.add_parser('extract', help='Extract i2d textures to PNG')
    ext_p.add_argument('input',  help='Input directory (extracted imagery)')
    ext_p.add_argument('output', help='Output directory for PNGs')
    ext_p.add_argument('-v', '--verbose', action='store_true')

    args = parser.parse_args()

    if args.command == 'info':
        print_cgsr_info(Path(args.file))

    elif args.command == 'extract':
        if args.verbose:
            log.setLevel(logging.DEBUG)
        ok, fail = batch_extract_i2d(Path(args.input), Path(args.output))
        print(f"\nDone: {ok} extracted, {fail} failed")

    else:
        parser.print_help()
