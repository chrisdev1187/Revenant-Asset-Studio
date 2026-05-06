"""
RevEngine - Archive Extractor
==============================
Extracts Revenant (1999) proprietary archive formats:
  .rvr  ->  Main resource archive  (ZIP)
  .rvi  ->  Imagery archive        (ZIP)
  .rvm  ->  Map/module archive     (ZIP)

All three formats are standard ZIP files with renamed extensions.
This tool handles batch extraction with progress reporting.
"""

import zipfile
import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger('RevEngine.Extractor')


REVENANT_ARCHIVES = {
    '.rvr': 'Resources archive',
    '.rvi': 'Imagery archive',
    '.rvm': 'Map/module archive',
}

GAME_DIR = Path("C:/GOG Games/Revenant")
EXTRACT_DIR = Path("C:/Users/chris/OneDrive/Desktop/Revengine/extracted")


@dataclass
class ArchiveInfo:
    path: Path
    file_count: int
    total_size: int
    extensions: dict  # extension -> count


def inspect_archive(archive_path: Path) -> Optional[ArchiveInfo]:
    """Inspect a ZIP-based Revenant archive without extracting."""
    try:
        with zipfile.ZipFile(archive_path, 'r') as zf:
            names = zf.namelist()
            total_size = sum(info.file_size for info in zf.infolist())

            ext_counts = {}
            for name in names:
                ext = Path(name).suffix.lower()
                ext_counts[ext] = ext_counts.get(ext, 0) + 1

            return ArchiveInfo(
                path=archive_path,
                file_count=len(names),
                total_size=total_size,
                extensions=ext_counts,
            )
    except zipfile.BadZipFile as e:
        log.error(f"Not a valid ZIP: {archive_path.name} ({e})")
        return None


def _safe_makedirs(path: Path) -> None:
    """mkdir -p, renaming any file that blocks a path component."""
    parts = path.parts
    current = Path(parts[0])
    for part in parts[1:]:
        current = current / part
        if current.exists() and not current.is_dir():
            renamed = current.parent / (current.name + '.bin')
            log.warning(f"Renaming file blocking directory slot: {current} -> {renamed}")
            current.rename(renamed)
        if not current.exists():
            current.mkdir(exist_ok=True)


def extract_archive(archive_path: Path, output_dir: Path,
                    overwrite: bool = False) -> tuple[int, int]:
    """
    Extract a Revenant archive to output_dir.
    Returns (files_extracted, files_skipped).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted = 0
    skipped = 0

    try:
        with zipfile.ZipFile(archive_path, 'r') as zf:
            entries = zf.infolist()
            total = len(entries)

            for i, entry in enumerate(entries, 1):
                if entry.is_dir():
                    continue

                out_path = output_dir / entry.filename

                if out_path.exists() and not overwrite:
                    skipped += 1
                    continue

                # Progress every 100 files
                if i % 100 == 0 or i == total:
                    pct = int(i / total * 100)
                    log.info(f"  [{pct:3d}%] {i}/{total} files...")

                _safe_makedirs(out_path.parent)
                with zf.open(entry) as src, open(out_path, 'wb') as dst:
                    dst.write(src.read())
                extracted += 1

    except zipfile.BadZipFile as e:
        log.error(f"Extraction failed: {e}")

    return extracted, skipped


def extract_all_archives(game_dir: Path = GAME_DIR,
                         extract_dir: Path = EXTRACT_DIR,
                         overwrite: bool = False):
    """Extract all known Revenant archives from the game directory."""
    print("\n" + "="*60)
    print("  RevEngine Archive Extractor")
    print("  Game dir:", game_dir)
    print("  Output:  ", extract_dir)
    print("="*60 + "\n")

    archives_found = []

    # Root-level archives
    for ext, desc in REVENANT_ARCHIVES.items():
        for f in game_dir.glob(f'*{ext}'):
            archives_found.append((f, desc))

    # Module subdirectory
    modules_dir = game_dir / 'Modules'
    if modules_dir.exists():
        for f in modules_dir.glob('*.rvm'):
            archives_found.append((f, 'Map/module archive'))

    if not archives_found:
        log.error("No Revenant archives found in " + str(game_dir))
        return

    print(f"Found {len(archives_found)} archives to extract:\n")

    for archive_path, desc in archives_found:
        info = inspect_archive(archive_path)
        if not info:
            continue

        out_dir = extract_dir / archive_path.stem
        print(f"  {archive_path.name}")
        print(f"    Type:   {desc}")
        print(f"    Files:  {info.file_count}")
        print(f"    Size:   {info.total_size / 1024 / 1024:.1f} MB")
        print(f"    Types:  {dict(sorted(info.extensions.items(), key=lambda x: -x[1])[:5])}")
        print(f"    -> {out_dir}")

    print()
    confirm = input("Proceed with extraction? [Y/n]: ").strip().lower()
    if confirm == 'n':
        print("Aborted.")
        return

    print()
    total_extracted = 0
    total_skipped = 0

    for archive_path, desc in archives_found:
        out_dir = extract_dir / archive_path.stem
        log.info(f"Extracting {archive_path.name}...")
        ex, sk = extract_archive(archive_path, out_dir, overwrite=overwrite)
        log.info(f"  Done: {ex} extracted, {sk} skipped")
        total_extracted += ex
        total_skipped += sk

    print(f"\n{'='*60}")
    print(f"  COMPLETE: {total_extracted} files extracted, {total_skipped} skipped")
    print(f"  Output: {extract_dir}")
    print(f"{'='*60}\n")


def list_extracted_assets(extract_dir: Path = EXTRACT_DIR):
    """Print a summary of all extracted assets."""
    if not extract_dir.exists():
        print("No extracted files found. Run extract first.")
        return

    print(f"\n{'='*60}")
    print("  Extracted Asset Summary")
    print(f"{'='*60}")

    all_files = list(extract_dir.rglob('*'))
    file_files = [f for f in all_files if f.is_file()]

    ext_counts = {}
    ext_sizes = {}
    for f in file_files:
        ext = f.suffix.lower()
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
        ext_sizes[ext] = ext_sizes.get(ext, 0) + f.stat().st_size

    print(f"\n{'Extension':<12} {'Count':>8} {'Total Size':>12}")
    print("-" * 36)
    for ext, count in sorted(ext_counts.items(), key=lambda x: -x[1]):
        size_mb = ext_sizes[ext] / 1024 / 1024
        print(f"{ext or '(none)':<12} {count:>8} {size_mb:>10.1f} MB")

    total_size = sum(f.stat().st_size for f in file_files) / 1024 / 1024
    print("-" * 36)
    print(f"{'TOTAL':<12} {len(file_files):>8} {total_size:>10.1f} MB\n")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='RevEngine Archive Extractor - Revenant 1999'
    )
    parser.add_argument('--game-dir', default=str(GAME_DIR),
                        help='Path to Revenant game folder')
    parser.add_argument('--output', default=str(EXTRACT_DIR),
                        help='Output directory for extracted files')
    parser.add_argument('--overwrite', action='store_true',
                        help='Overwrite existing files')
    parser.add_argument('--list', action='store_true',
                        help='List already-extracted assets')

    args = parser.parse_args()

    if args.list:
        list_extracted_assets(Path(args.output))
    else:
        extract_all_archives(
            game_dir=Path(args.game_dir),
            extract_dir=Path(args.output),
            overwrite=args.overwrite,
        )
