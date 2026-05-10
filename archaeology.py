"""
RevEngine - Phase 0 Archaeology Script
=======================================
Run this from CMD inside C:\\GOG Games\\Revenant\\RevEngine

    python archaeology.py

It reads your actual game files and answers the 4 unknowns needed
before any live-scene code can be written. Paste the full output
back to Claude.

No files are modified. Read-only analysis only.
"""

import struct
import os
import sys
from pathlib import Path

# ── Locate game files ─────────────────────────────────────────────────────────

_HERE = Path(__file__).resolve().parent
GAME_DIR     = _HERE / "game"
EXTRACT_DIR  = _HERE / "extracted"
IMAGERY_DIR  = EXTRACT_DIR / "imagery" / "Imagery"
SOURCE_DIR   = GAME_DIR / "Revenant-master"

SEP  = "=" * 70
SEP2 = "-" * 70

def banner(title):
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)

def ok(msg):   print(f"  [OK]  {msg}")
def warn(msg): print(f"  [??]  {msg}")
def err(msg):  print(f"  [!!]  {msg}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def read_i3d_states(path):
    """Return list of (name, prefix_hex, prefix_bytes) for every state in an i3d file."""
    raw = path.read_bytes()
    if raw[:4] != b'CGSR':
        return None, None
    state_count = struct.unpack_from('<I', raw, 0x18)[0]
    states = []
    for i in range(min(state_count, 64)):
        off    = 84 + i * 76
        if off + 76 > len(raw):
            break
        prefix = raw[off : off + 20]
        name   = raw[off+20 : off+76].split(b'\x00')[0].decode('ascii', 'replace').strip()
        states.append((name, prefix.hex(), prefix))
    return state_count, states


def count_geometry_sections(path, state_count):
    """
    Count how many distinct vertex+face blocks exist in the file.
    Uses the same scanner logic as the working decoder.
    """
    raw = path.read_bytes()
    content_size  = struct.unpack_from('<I', raw, 8)[0]
    payload_start = len(raw) - content_size
    if payload_start < 0 or payload_start + 24 > len(raw):
        return 0

    vc = struct.unpack_from('<I', raw, payload_start + 12)[0]
    fc = struct.unpack_from('<I', raw, payload_start + 20)[0]
    if vc == 0 or vc > 300_000 or fc == 0:
        return 0

    # Count how many non-overlapping face blocks exist
    VALID_STRIDES = (32, 28, 40, 36, 44, 24, 48, 20, 16)
    found_positions = []
    n_face_bytes = fc * 6
    scan_end = len(raw) - n_face_bytes
    last_found = -1

    for fstart in range(payload_start + 48, scan_end, 2):
        if fstart <= last_found:
            continue
        n_ok = 0; off = fstart; max_idx = 0
        while n_ok < fc and off + 6 <= len(raw):
            a, b, c = struct.unpack_from('<HHH', raw, off)
            if a < vc and b < vc and c < vc:
                n_ok += 1; off += 6
                max_idx = max(max_idx, a, b, c)
            else:
                break
        if n_ok < fc or max_idx <= 1:
            continue
        for stride in VALID_STRIDES:
            vstart = fstart - vc * stride
            if vstart < payload_start:
                continue
            ok_v = True
            for i in range(min(vc, 8)):
                voff = vstart + i * stride
                if voff + 12 > len(raw):
                    ok_v = False; break
                x, y, z = struct.unpack_from('<fff', raw, voff)
                import math
                if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z) and
                        abs(x) < 50000 and abs(y) < 50000 and abs(z) < 50000):
                    ok_v = False; break
            if ok_v:
                found_positions.append(fstart)
                last_found = fstart + n_face_bytes
                break

    return len(found_positions)


def find_i3d(name_hint):
    """Find an i3d file by partial name anywhere under IMAGERY_DIR."""
    if not IMAGERY_DIR.exists():
        return None
    for p in IMAGERY_DIR.rglob("*.i3d"):
        if name_hint.lower() in p.stem.lower():
            return p
    for p in IMAGERY_DIR.rglob("*.I3D"):
        if name_hint.lower() in p.stem.lower():
            return p
    return None


def list_char_files(char_hint):
    """List all files for a character folder."""
    chars_dir = IMAGERY_DIR / "Chars"
    if not chars_dir.exists():
        return []
    results = []
    for entry in chars_dir.iterdir():
        if char_hint.lower() in entry.name.lower():
            if entry.is_dir():
                results += list(entry.iterdir())
            else:
                results.append(entry)
    return results


def search_source(filename, keywords):
    """Search Revenant-master source for keywords in a file."""
    src = SOURCE_DIR / filename
    if not src.exists():
        return None, False
    text = src.read_text(encoding='utf-8', errors='replace')
    hits = {}
    for kw in keywords:
        count = text.lower().count(kw.lower())
        if count:
            hits[kw] = count
            # grab surrounding context for first hit
            idx = text.lower().find(kw.lower())
            hits[kw + '_ctx'] = text[max(0,idx-60):idx+120].replace('\n', ' | ')
    return hits, src.exists()


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'#'*70}")
    print("  RevEngine Phase 0 — Archaeology Report")
    print(f"  Game dir : {GAME_DIR}")
    print(f"  Extract  : {EXTRACT_DIR}")
    print(f"{'#'*70}")

    # ── Environment check ─────────────────────────────────────────────────────
    banner("ENV CHECK")
    for label, path in [
        ("Game dir",      GAME_DIR),
        ("Extracted",     EXTRACT_DIR),
        ("Imagery dir",   IMAGERY_DIR),
        ("Source dir",    SOURCE_DIR),
    ]:
        exists = path.exists()
        (ok if exists else warn)(f"{label}: {path}  {'EXISTS' if exists else 'NOT FOUND'}")

    if not IMAGERY_DIR.exists():
        err("Imagery directory not found. Run setup.py first to extract game archives.")
        sys.exit(1)

    # ── Count i3d files ───────────────────────────────────────────────────────
    all_i3d = list(IMAGERY_DIR.rglob("*.i3d")) + list(IMAGERY_DIR.rglob("*.I3D"))
    ok(f"Total i3d files found: {len(all_i3d)}")

    # ── UNKNOWN 1 + 2: State table prefix bytes ───────────────────────────────
    banner("UNKNOWN 1+2 — State Table Prefix Bytes")
    print("  Dumping state table for 6 representative files.")
    print()

    probe_hints = ["acolyte", "deaddruhg", "locke", "arrow", "sword", "goblin"]
    probed = []
    for hint in probe_hints:
        f = find_i3d(hint)
        if f:
            probed.append(f)
    # pad with random i3d if we didn't find enough
    if len(probed) < 4:
        for p in all_i3d[:10]:
            if p not in probed:
                probed.append(p)
            if len(probed) >= 6:
                break

    for path in probed[:6]:
        state_count, states = read_i3d_states(path)
        if states is None:
            warn(f"{path.name}: not a valid CGSR file")
            continue
        print(f"  FILE: {path.name}  (in {path.parent.name})  states={state_count}")
        for name, hexstr, raw_bytes in states:
            # Try to interpret prefix as uint32 sequence
            if len(raw_bytes) >= 20:
                u0,u1,u2,u3,u4 = struct.unpack_from('<IIIII', raw_bytes, 0)
                print(f"    state '{name:<20}'  "
                      f"hex={hexstr[:40]}  "
                      f"uint32s=[ {u0}, {u1}, {u2}, {u3}, {u4} ]")
            else:
                print(f"    state '{name:<20}'  hex={hexstr}")
        print()

    # ── UNKNOWN 1: Count geometry sections ────────────────────────────────────
    banner("UNKNOWN 1 — Geometry Section Count (morph vs skeletal)")
    print("  For each file: does it have 1 geometry section, or one per state?")
    print()

    for path in probed[:6]:
        state_count, states = read_i3d_states(path)
        if states is None:
            continue
        n_geom = count_geometry_sections(path, state_count)
        verdict = ""
        if n_geom == 1:
            verdict = "→ ONE SHARED MESH (T-pose only, or skeletal)"
        elif state_count and n_geom == state_count:
            verdict = f"→ MORPH TARGETS ({n_geom} vertex buffers = {state_count} states)"
        elif n_geom > 1:
            verdict = f"→ MULTIPLE SECTIONS ({n_geom}) — sub-objects or LODs?"
        else:
            verdict = "→ could not detect geometry"
        print(f"  {path.name:<35}  states={state_count}  geom_sections={n_geom}  {verdict}")

    # ── UNKNOWN 3: Character folder structure ─────────────────────────────────
    banner("UNKNOWN 3 — Character Folder Structure (single vs multi-file)")
    chars_dir = IMAGERY_DIR / "Chars"
    if chars_dir.exists():
        print(f"  Chars dir: {chars_dir}")
        entries = sorted(chars_dir.iterdir())
        print(f"  Total entries: {len(entries)}")
        print()
        # Print first 12 entries with their contents
        for entry in entries[:12]:
            if entry.is_dir():
                children = sorted(entry.iterdir())
                child_names = [c.name for c in children[:8]]
                print(f"  DIR  {entry.name}/")
                for c in child_names:
                    print(f"         {c}")
                if len(children) > 8:
                    print(f"         ... ({len(children)-8} more)")
            else:
                print(f"  FILE {entry.name}")
        if len(entries) > 12:
            print(f"  ... ({len(entries)-12} more entries)")
        print()

        # Try to find a known character and list ALL its files
        for hint in ["locke", "acolyte", "player"]:
            files = list_char_files(hint)
            if files:
                print(f"  Files for '{hint}':")
                for f in sorted(files):
                    size = f.stat().st_size if f.is_file() else 0
                    print(f"    {f.name:<40} {size:>8} bytes  ({f.suffix.lower()})")
                break
    else:
        warn(f"Chars dir not found: {chars_dir}")

    # ── UNKNOWN 4: Source code — tag / attachment system ──────────────────────
    banner("UNKNOWN 4 — Tag / Attachment System (source code)")

    tag_keywords = ["FindTag", "GetTag", "AttachPoint", "attach", "RHAND", "LHAND",
                    "HEAD_ATTACH", "tag_name", "imagery->tag", "tagpos", "tagrot"]
    anim_keywords = ["frame_count", "frame_data", "morph", "CalcMatrix",
                     "bone", "pivot", "S3DObject", "S3DImagery", "T3DImagery",
                     "state_count", "anim_state", "STIL"]

    source_files = [
        "imagery.cpp", "imagery.h", "3dimage.h", "3dcont.cpp",
        "3drender.cpp", "object.cpp", "object.h", "3dobject.cpp"
    ]

    found_any_source = False
    for fname in source_files:
        src_path = SOURCE_DIR / fname
        if not src_path.exists():
            continue
        found_any_source = True
        text = src_path.read_text(encoding='utf-8', errors='replace')
        size = len(text.splitlines())
        print(f"\n  SOURCE: {fname}  ({size} lines)")

        # Search for tag keywords
        tag_hits = [(kw, text.lower().count(kw.lower())) for kw in tag_keywords if kw.lower() in text.lower()]
        anim_hits = [(kw, text.lower().count(kw.lower())) for kw in anim_keywords if kw.lower() in text.lower()]

        if tag_hits:
            print(f"    TAG keywords found: {', '.join(f'{k}({n})' for k,n in tag_hits)}")
            # Print context for first 3 tag hits
            for kw, _ in tag_hits[:3]:
                idx = text.lower().find(kw.lower())
                ctx = text[max(0,idx-40):idx+100].replace('\n', ' | ').strip()
                print(f"      '{kw}' context: {ctx[:140]}")

        if anim_hits:
            print(f"    ANIM keywords found: {', '.join(f'{k}({n})' for k,n in anim_hits)}")
            for kw, _ in anim_hits[:3]:
                idx = text.lower().find(kw.lower())
                ctx = text[max(0,idx-40):idx+100].replace('\n', ' | ').strip()
                print(f"      '{kw}' context: {ctx[:140]}")

        if not tag_hits and not anim_hits:
            print(f"    (no relevant keywords found)")

    if not found_any_source:
        warn(f"No source files found in {SOURCE_DIR}")
        warn("If source is in a different location, edit SOURCE_DIR at top of this script.")

    # ── Bonus: dump raw bytes at state table for one file ─────────────────────
    banner("BONUS — Full Raw State Table Hexdump (first file with >2 states)")
    for path in probed:
        state_count, states = read_i3d_states(path)
        if states and len(states) > 2:
            print(f"  File: {path.name}")
            raw = path.read_bytes()
            print(f"  First {min(state_count,8)} state entries (76 bytes each), offset 84:")
            for i, (name, hexstr, _) in enumerate(states[:8]):
                off = 84 + i * 76
                entry = raw[off:off+76]
                print(f"\n  [{i}] state='{name}'  offset={off}")
                for row in range(0, 76, 16):
                    chunk = entry[row:row+16]
                    hex_part = ' '.join(f'{b:02x}' for b in chunk)
                    asc_part = ''.join(chr(b) if 32<=b<127 else '.' for b in chunk)
                    print(f"    {row:02x}: {hex_part:<48}  {asc_part}")
            break

    # ── Summary ───────────────────────────────────────────────────────────────
    banner("SUMMARY — Paste Everything Above Back to Claude")
    print("  All output above answers the 4 unknowns needed for Phase 1.")
    print("  Copy from the top of this output and paste it in the chat.")
    print()

if __name__ == "__main__":
    main()
