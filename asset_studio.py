"""
RevEngine Asset Studio v2
==========================
Assembled game encyclopedia for Revenant (1999) by Cinematix Studios.

Opens directly to assembled, stitched views:
  - World Map   : fully assembled automap tiles per zone
  - Characters  : gallery of all characters + stats from char.def
  - Equipment   : weapons & armour catalogue from weapon.def / armor.def
  - Spells      : spell catalogue from spell.def
  - Scripts     : all .def files with cross-reference search

Usage:
    py asset_studio.py
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import struct
import re
import threading
import hashlib
import math
import logging
import json
import os
from pathlib import Path
from typing import Optional, List, Dict, Tuple

# Load .env from the project root (NVIDIA_API_KEY etc.) before anything else reads env vars.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env", override=False)
except ImportError:
    pass  # python-dotenv optional; set NVIDIA_API_KEY in your shell if not installed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("RevEngine.Studio")

# ─── Paths ───────────────────────────────────────────────────────────────────
# Default: GOG install location. Override via --game-dir on the command line.
_DEFAULT_GAME_DIR = Path("C:/GOG Games/Revenant")

def _resolve_game_dir() -> Path:
    import sys
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg in ("--game-dir", "--game_dir") and i < len(sys.argv):
            return Path(sys.argv[i + 1])
        if arg.startswith("--game-dir="):
            return Path(arg.split("=", 1)[1])
        if arg.startswith("--game_dir="):
            return Path(arg.split("=", 1)[1])
    return _DEFAULT_GAME_DIR

GAME_DIR    = _resolve_game_dir()
EXTRACT_DIR = Path("C:/Users/chris/OneDrive/Desktop/Revengine/extracted")
ENGINE_DIR  = Path("C:/Users/chris/OneDrive/Desktop/Revengine")
IMAGERY     = EXTRACT_DIR / "imagery"
RESOURCES   = EXTRACT_DIR / "resources"
AHKUILON    = EXTRACT_DIR / "Ahkuilon"
RENDERS_DIR = ENGINE_DIR / "test_renders"

_CONFIG_PATH = ENGINE_DIR / "revengine.json"

def _load_config():
    global GAME_DIR, EXTRACT_DIR, RENDERS_DIR, IMAGERY, RESOURCES, AHKUILON
    global IMAGERY_ASSETS, THUMBNAILS, CHAR_DEF, WEAPON_DEF, ARMOR_DEF, SPELL_DEF
    if not _CONFIG_PATH.exists():
        return
    try:
        cfg = json.loads(_CONFIG_PATH.read_text())
        if "game_dir"    in cfg: GAME_DIR    = Path(cfg["game_dir"])
        if "extract_dir" in cfg:
            EXTRACT_DIR   = Path(cfg["extract_dir"])
            IMAGERY       = EXTRACT_DIR / "imagery"
            RESOURCES     = EXTRACT_DIR / "resources"
            AHKUILON      = EXTRACT_DIR / "Ahkuilon"
            IMAGERY_ASSETS = IMAGERY / "Imagery"
            THUMBNAILS    = IMAGERY / "Thumbnails"
            CHAR_DEF      = IMAGERY  / "char.def"
            WEAPON_DEF    = IMAGERY  / "weapon.def"
            ARMOR_DEF     = IMAGERY  / "armor.def"
            SPELL_DEF     = RESOURCES / "spell.def"
        if "renders_dir" in cfg: RENDERS_DIR = Path(cfg["renders_dir"])
    except Exception:
        pass

def _save_config():
    try:
        _CONFIG_PATH.write_text(json.dumps({
            "game_dir":    str(GAME_DIR),
            "extract_dir": str(EXTRACT_DIR),
            "renders_dir": str(RENDERS_DIR),
        }, indent=2))
    except Exception:
        pass

IMAGERY_ASSETS = IMAGERY / "Imagery"     # .i2d / .i3d / .bmp
THUMBNAILS     = IMAGERY / "Thumbnails"  # .tn files

CHAR_DEF    = IMAGERY    / "char.def"
WEAPON_DEF  = IMAGERY    / "weapon.def"
ARMOR_DEF   = IMAGERY    / "armor.def"
SPELL_DEF   = RESOURCES  / "spell.def"

# ─── PIL ─────────────────────────────────────────────────────────────────────
try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ─── Colour Theme ─────────────────────────────────────────────────────────────
BG_DARK   = "#0f0f1a"
BG_MID    = "#1a1a2e"
BG_PANEL  = "#16213e"
BG_CARD   = "#1e2a45"
FG_TEXT   = "#e0e6f8"
FG_DIM    = "#8090b0"
FG_MUTED  = "#506080"
ACCENT    = "#c084fc"       # purple
ACCENT2   = "#60a5fa"       # blue
ACCENT3   = "#34d399"       # green
GOLD      = "#fbbf24"       # gold
RED       = "#f87171"       # red
BORDER    = "#2a3a5a"
SEP       = "#1e2d48"

WEAPON_TYPE = {0:"Hand/Claw", 1:"Knife/Dagger", 2:"Sword",
               3:"Bludgeon", 4:"Axe", 5:"Staff/Polearm",
               6:"Bow", 7:"Crossbow"}

ARMOR_SLOT = {2:"Chest", 3:"Head", 4:"Weapon", 5:"Shield",
              6:"Gauntlet", 7:"Ring1", 8:"Ring2",
              9:"Legs", 10:"Boots", 11:"Amulet"}

TALISMAN_MAP = {
    'A': 'Sun',   'B': 'Life',  'C': 'Ocean', 'D': 'Law',   'E': 'Soul',
    'F': 'Stars', 'G': 'Death', 'H': 'Chaos', 'I': 'Sky',   'J': 'Earth',
    'K': 'Ward',  'L': 'Moon',  'M': 'Rubert','N': 'Gilmor','O': 'Barry',
}

DAMAGE_TYPE_NAMES = {
    'DT_NONE': 'None', 'DT_MISC': 'Misc', 'DT_HAND': 'Hand',
    'DT_PUNCTURE': 'Puncture', 'DT_CUT': 'Cut', 'DT_CHOP': 'Chop',
    'DT_BLUDGEON': 'Bludgeon', 'DT_MAGICAL': 'Magical',
    'DT_BURN': 'Burn', 'DT_FREEZE': 'Freeze', 'DT_POISON': 'Poison',
}


# ═══════════════════════════════════════════════════════════════════════════════
#  DATA PARSERS
# ═══════════════════════════════════════════════════════════════════════════════

def _read_def(path: Path) -> str:
    """Read a .def file, tolerating latin-1 encoding."""
    try:
        return path.read_text(encoding='latin-1')
    except Exception:
        return ""


def parse_char_def() -> List[Dict]:
    """Parse char.def into a list of character dicts."""
    text = _read_def(CHAR_DEF)
    chars = []

    pattern = re.compile(
        r'CHARACTER\s+"([^"]+)"[^\n]*\nBEGIN(.*?)END',
        re.DOTALL
    )
    for m in pattern.finditer(text):
        name  = m.group(1).strip()
        body  = m.group(2)
        entry = {"name": name, "_raw": body.strip()}

        def _get(tag, default=""):
            rx = re.search(rf'\b{tag}\s+"?([^"\n]+)"?', body)
            return rx.group(1).strip() if rx else default

        def _get_nums(tag):
            rx = re.search(rf'\b{tag}\b\s+([\d,\s\-]+)', body)
            if rx:
                return [int(x.strip()) for x in rx.group(1).split(',')
                        if x.strip().lstrip('-').isdigit()]
            return []

        entry["class"]      = _get("CLASS")
        entry["groups"]     = _get("GROUPS")
        entry["enemies"]    = _get("ENEMIES")
        entry["script"]     = _get("SCRIPT")
        entry["sound"]      = _get("SOUND")

        sight = _get_nums("SIGHT")
        entry["sight"] = sight[2] if len(sight) >= 3 else (sight[0] if sight else 0)

        block = _get_nums("BLOCK")
        entry["block_pct"] = block[0] if block else 0

        entry["weapon_dmg"]  = _get_nums("WEAPONDAMAGE")[0] if _get_nums("WEAPONDAMAGE") else 0

        health = _get_nums("HEALTH")
        entry["health"]      = health[0] if health else 0

        speed = _get_nums("SPEED")
        entry["speed"]       = speed[0] if speed else 0

        # Parse individual ATTACK blocks: ATTACK "name" BEGIN ... END
        attack_blocks = re.findall(
            r'ATTACK\s+"?([^"\n]+)"?\s+BEGIN(.*?)END', body, re.DOTALL)
        entry["attacks"] = []
        for aname, abody in attack_blocks:
            atk = {"name": aname.strip()}
            dmg = re.search(r'\bDAMAGE\b\s+([\d\s,]+)', abody)
            atk["damage"] = dmg.group(1).strip() if dmg else ""
            anim = re.search(r'\bANIMATION\s+"?([^"\n]+)"?', abody)
            atk["anim"] = anim.group(1).strip() if anim else ""
            entry["attacks"].append(atk)
        # Fallback: bare ATTACK count
        if not entry["attacks"]:
            entry["attack_count"] = len(re.findall(r'\bATTACK\b', body))
        else:
            entry["attack_count"] = len(entry["attacks"])

        # Parse IMPACT blocks similarly
        impact_blocks = re.findall(
            r'IMPACT\s+"?([^"\n]+)"?\s+BEGIN(.*?)END', body, re.DOTALL)
        entry["impacts"] = []
        for iname, ibody in impact_blocks:
            entry["impacts"].append({"name": iname.strip()})
        if not entry["impacts"]:
            entry["impact_count"] = len(re.findall(r'\bIMPACT\b', body))
        else:
            entry["impact_count"] = len(entry["impacts"])

        # Spells the character can cast
        spells = re.findall(r'\bSPELL\s+"?([^"\n]+)"?', body)
        entry["spells"] = [s.strip() for s in spells]

        # Animation state names referenced in char body
        anims = re.findall(r'\bANIMATION\s+"?([^"\n]+)"?', body)
        entry["anim_refs"] = sorted(set(a.strip() for a in anims))

        chars.append(entry)

    return chars


def parse_weapon_def() -> List[Dict]:
    """Parse weapon.def into a list of weapon dicts."""
    text = _read_def(WEAPON_DEF)
    weapons = []
    pattern = re.compile(r'WEAPON\s+"([^"]+)"\s*\nBEGIN(.*?)END', re.DOTALL)
    for m in pattern.finditer(text):
        name = m.group(1).strip()
        body = m.group(2)
        nums_m = re.search(r'BASICMODS\s+([\d,\s\-]+)', body)
        nums = [int(x.strip()) for x in nums_m.group(1).split(',')
                if x.strip().lstrip('-').isdigit()] if nums_m else []
        # eqslot, type, damage, combining, poison, value, damagemod, minstrength
        w = {
            "name":       name,
            "eq_slot":    nums[0] if len(nums)>0 else 0,
            "type":       nums[1] if len(nums)>1 else 0,
            "damage":     nums[2] if len(nums)>2 else 0,
            "combining":  nums[3] if len(nums)>3 else 0,
            "poison":     nums[4] if len(nums)>4 else 0,
            "value":      nums[5] if len(nums)>5 else 0,
            "damage_mod": nums[6] if len(nums)>6 else 0,
            "min_str":    nums[7] if len(nums)>7 else 0,
            "type_name":  WEAPON_TYPE.get(nums[1] if len(nums)>1 else 0, "?"),
        }
        weapons.append(w)
    return weapons


def parse_armor_def() -> List[Dict]:
    """Parse armor.def into a list of armour dicts."""
    text = _read_def(ARMOR_DEF)
    armors = []
    pattern = re.compile(r'ARMOR\s+"([^"]+)"\s*\nBEGIN(.*?)END', re.DOTALL)
    for m in pattern.finditer(text):
        name = m.group(1).strip()
        body = m.group(2)
        nums_m = re.search(r'BASICMODS\s+([\d,\s\-]+)', body)
        nums = [int(x.strip()) for x in nums_m.group(1).split(',')
                if x.strip().lstrip('-').isdigit()] if nums_m else []
        # eqslot, protection, combining, resistpoison, stealth, value, minstrength, minconstitution
        a = {
            "name":       name,
            "eq_slot":    nums[0] if len(nums)>0 else 0,
            "slot_name":  ARMOR_SLOT.get(nums[0] if len(nums)>0 else 0, "?"),
            "protection": nums[1] if len(nums)>1 else 0,
            "combining":  nums[2] if len(nums)>2 else 0,
            "resist_psn": nums[3] if len(nums)>3 else 0,
            "stealth":    nums[4] if len(nums)>4 else 0,
            "value":      nums[5] if len(nums)>5 else 0,
            "min_str":    nums[6] if len(nums)>6 else 0,
            "min_con":    nums[7] if len(nums)>7 else 0,
        }
        armors.append(a)
    return armors


def parse_spell_def() -> List[Dict]:
    """Parse spell.def into a list of spell dicts with full VARIANT/talisman data."""
    text = _read_def(SPELL_DEF)
    spells = []
    pattern = re.compile(r'SPELL\s+"([^"]+)"\s*\nBEGIN(.*?)END', re.DOTALL)
    # VARIANT "name", type, "talismans", "effect", mana, wait, min_d, max_d, ...
    variant_re = re.compile(
        r'VARIANT\s+"([^"]+)"\s*,\s*\w+\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*(\d+)'
        r'(?:\s*,\s*(\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+))?',
        re.DOTALL
    )
    for m in pattern.finditer(text):
        name = m.group(1).strip()
        body = m.group(2)

        def _tag(t, b=body):
            rx = re.search(rf'\b{t}\b\s+(-?[\w\.]+)', b)
            return rx.group(1) if rx else ""

        desc_m = re.search(r'\bDESCRIPTION\s+"([^"]+)"', body)
        description = desc_m.group(1).strip() if desc_m else ""

        icon_m = re.search(r'\bICONNAME\s+"([^"]+)"', body)
        icon_name = icon_m.group(1).strip() if icon_m else name

        anim_m = re.search(r'\bANIMATION\s+"?([^"\n]+)"?', body)
        animation = anim_m.group(1).strip() if anim_m else ""

        dt_m = re.search(r'\bDAMAGETYPE\s+(\w+)', body)
        damage_type = dt_m.group(1) if dt_m else ""

        variants = []
        for vm in variant_re.finditer(body):
            talis_str  = vm.group(2).strip()
            talis_names = [TALISMAN_MAP.get(c.upper(), c) for c in talis_str]
            min_d = vm.group(6) or "—"
            max_d = vm.group(7) or "—"
            variants.append({
                'name':        vm.group(1).strip(),
                'talismans':   talis_str,
                'talis_names': talis_names,
                'effect':      vm.group(3).strip(),
                'mana':        int(vm.group(4)),
                'min_d':       min_d,
                'max_d':       max_d,
            })

        mana = str(variants[0]['mana']) if variants else _tag("MANA") or "—"

        s = {
            "name":        name,
            "icon_name":   icon_name,
            "mana":        mana,
            "damage":      _tag("DAMAGE"),
            "duration":    _tag("DURATION"),
            "description": description,
            "animation":   animation,
            "damage_type": damage_type,
            "variants":    variants,
        }
        spells.append(s)
    return spells


def find_char_i3d(char_name: str) -> Optional[Path]:
    """Try to find the i3d file matching a character name."""
    chars_dir = IMAGERY_ASSETS / "Chars"
    if not chars_dir.exists():
        return None
    norm = re.sub(r'[^a-z0-9]', '', char_name.lower())
    for f in chars_dir.iterdir():
        if f.suffix.lower() == '.i3d':
            stem_norm = re.sub(r'[^a-z0-9]', '', f.stem.lower())
            if stem_norm == norm or norm.startswith(stem_norm) or stem_norm.startswith(norm[:4]):
                return f
    return None


def find_portrait(char_name: str) -> Optional[Path]:
    """Find portrait BMP for a character."""
    chars_dir = IMAGERY_ASSETS / "Chars"
    if not chars_dir.exists():
        return None
    norm = char_name.lower().split()[0]  # first word
    for f in chars_dir.iterdir():
        if f.suffix.lower() == '.bmp' and f.stem.lower() == norm:
            return f
    return None


def parse_i3d_anim_count(path: Path) -> int:
    """Return animation state count from an i3d file header."""
    return len(parse_i3d_anim_states(path))


def parse_i3d_anim_states(path: Path) -> List[Dict]:
    """Return list of animation states: [{name, frames}, ...].

    CGSR header (84 bytes):
      0x00 magic='CGSR', 0x06 topbm(2), 0x10 hdrsize(4)
    Per-state header (32 bytes each), starting at byte 52:
      +0  pad(4), +4 frame_count(4), +8 name(8 bytes, C string),
      +24 width(2), +26 height(2), +28 regx(2), +30 regy(2)
    """
    states = []
    try:
        raw = path.read_bytes()
        if len(raw) < 84 or raw[:4] != b'CGSR':
            return states
        topbm    = struct.unpack_from('<H', raw, 0x06)[0]
        hdrsize  = struct.unpack_from('<I', raw, 0x10)[0]
        n_states = topbm + 1
        state_base = 52  # per-state headers start at byte 52
        for i in range(n_states):
            off = state_base + i * 32
            if off + 32 > hdrsize:
                break
            frames = struct.unpack_from('<I', raw, off + 4)[0]
            name_bytes = raw[off + 8: off + 16]
            name = name_bytes.split(b'\x00')[0].decode('ascii', errors='replace')
            w = struct.unpack_from('<H', raw, off + 24)[0] if off + 26 <= hdrsize else 0
            h = struct.unpack_from('<H', raw, off + 26)[0] if off + 28 <= hdrsize else 0
            states.append({"name": name or f"state{i}", "frames": frames,
                           "width": w, "height": h})
    except Exception:
        pass
    return states


def _all_automap_dirs() -> List[Path]:
    """Return every Automaps/ directory found under _extracted/.

    Revenant stores each game module (Ahkuilon, town interiors, dungeons, etc.)
    as a separate subdirectory of _extracted/.  Each module that has been
    extracted will contain an Automaps/ folder with its zone tiles.

    Example layout:
        _extracted/Ahkuilon/Automaps/      ← main outdoor world
        _extracted/Arindale/Automaps/      ← town of Arindale
        _extracted/OrcCamp/Automaps/       ← orc stronghold
        _extracted/SomeDungeon/Automaps/   ← etc.
    """
    dirs = []
    if not EXTRACT_DIR.exists():
        return dirs
    for child in sorted(EXTRACT_DIR.iterdir()):
        if child.is_dir():
            candidate = child / "Automaps"
            if candidate.is_dir():
                dirs.append(candidate)
    return dirs


# ZoneKey = (module_name, zone_number)  — uniquely identifies one map
ZoneKey = Tuple[str, int]


def get_all_zone_keys() -> List[ZoneKey]:
    """Scan every module's Automaps/ and return (module, zone) pairs, sorted."""
    seen: set = set()
    for adir in _all_automap_dirs():
        module = adir.parent.name          # e.g. "Ahkuilon", "Arindale"
        for f in adir.rglob("*.bmp"):
            parts = f.stem.split('_')
            if len(parts) >= 3:
                try:
                    z = int(parts[0])
                    seen.add((module, z))
                except ValueError:
                    pass
    # Sort: Ahkuilon first (zone 0), then alphabetically by module, then by zone
    return sorted(seen, key=lambda mk: (mk[0].lower() != "ahkuilon", mk[0].lower(), mk[1]))


def get_automap_tiles(zone: int, module: str = "Ahkuilon") -> List[Path]:
    """Get all automap BMP tiles for a (module, zone) pair."""
    tiles = []
    adir = EXTRACT_DIR / module / "Automaps"
    if not adir.exists():
        # Fall back: search all modules
        for d in _all_automap_dirs():
            for f in d.rglob("*.bmp"):
                parts = f.stem.split('_')
                if len(parts) >= 3:
                    try:
                        if int(parts[0]) == zone:
                            tiles.append(f)
                    except ValueError:
                        pass
        return tiles
    for f in adir.rglob("*.bmp"):
        parts = f.stem.split('_')
        if len(parts) >= 3:
            try:
                if int(parts[0]) == zone:
                    tiles.append(f)
            except ValueError:
                pass
    return tiles


def get_available_zones() -> List[int]:
    """Return sorted list of unique zone numbers across ALL modules (legacy helper)."""
    return sorted(set(z for _, z in get_all_zone_keys()))


def stitch_zone_map(zone: int, module: str = "Ahkuilon",
                    tile_size: int = 64) -> Optional["Image.Image"]:
    """Stitch all automap tiles for a (module, zone) into a single PIL Image.

    Tile filenames: <zone>_<X>_<Y>.bmp   X and Y may be negative.
    """
    if not HAS_PIL:
        return None
    tiles = get_automap_tiles(zone, module)
    if not tiles:
        return None

    coords = []
    for t in tiles:
        parts = t.stem.split('_')
        if len(parts) < 3:
            continue
        try:
            coords.append((int(parts[1]), int(parts[2]), t))
        except ValueError:
            pass

    if not coords:
        return None

    min_x = min(x for x, y, _ in coords)
    max_x = max(x for x, y, _ in coords)
    min_y = min(y for x, y, _ in coords)
    max_y = max(y for x, y, _ in coords)

    canvas = Image.new('RGB',
                       (tile_size * (max_x - min_x + 1),
                        tile_size * (max_y - min_y + 1)),
                       (20, 20, 30))

    for x_val, y_val, path in coords:
        paste_x = tile_size * (x_val - min_x)
        paste_y = tile_size * (y_val - min_y)
        try:
            tile = Image.open(path).convert('RGB').resize(
                (tile_size, tile_size), Image.NEAREST)
            canvas.paste(tile, (paste_x, paste_y))
        except Exception:
            pass

    return canvas


def _char_color(name: str) -> Tuple[int, int, int]:
    """Generate a deterministic dark colour for a character card from its name."""
    h = hashlib.md5(name.encode()).digest()
    r = 40  + (h[0] % 100)
    g = 40  + (h[1] % 100)
    b = 80  + (h[2] % 100)
    return (r, g, b)


def make_placeholder_portrait(name: str, size: int = 96) -> Optional["Image.Image"]:
    """Create a coloured placeholder portrait with initials."""
    if not HAS_PIL:
        return None
    color = _char_color(name)
    img   = Image.new('RGB', (size, size), color)
    draw  = ImageDraw.Draw(img)
    # Dark gradient border
    for i in range(4):
        c = tuple(max(0, x - i * 20) for x in color)
        draw.rectangle([i, i, size - 1 - i, size - 1 - i], outline=c)
    # Initials
    initials = ''.join(w[0].upper() for w in name.split()[:2])
    font_size = size // 3
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), initials, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) // 2, (size - th) // 2), initials,
              fill=(220, 230, 255), font=font)
    return img


# ═══════════════════════════════════════════════════════════════════════════════
#  REUSABLE WIDGETS
# ═══════════════════════════════════════════════════════════════════════════════

class ScrollFrame(tk.Frame):
    """A frame with a vertical scrollbar."""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=kwargs.pop('bg', BG_MID), **kwargs)
        self.canvas = tk.Canvas(self, bg=BG_MID, highlightthickness=0)
        self.vsb    = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner  = tk.Frame(self.canvas, bg=BG_MID)
        self._win   = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<MouseWheel>",  self._on_mousewheel)
        self.inner.bind("<MouseWheel>",   self._on_mousewheel)

    def _on_inner_configure(self, _):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        self.canvas.itemconfig(self._win, width=e.width)

    def _on_mousewheel(self, e):
        self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")


class StatusBar(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG_DARK, pady=2)
        self._var = tk.StringVar(value="Ready")
        tk.Label(self, textvariable=self._var, bg=BG_DARK, fg=FG_DIM,
                 font=("Consolas", 9), anchor="w").pack(side="left", padx=8)

    def set(self, msg: str):
        self._var.set(msg)
        self.update_idletasks()


# ═══════════════════════════════════════════════════════════════════════════════
#  WORLD MAP TAB
# ═══════════════════════════════════════════════════════════════════════════════

# Zone → name mapping based on diagnostic scan of actual tile data.
# Zones confirmed present: 0,2-5,30-32,36-37,39,41,44-46,48-49,51-58,73,83,100-102,205
# Zones 6-29 (except present ones) and gaps are simply absent from game data.
# Town/OrcCamp interiors have NO automap tiles (too small; developers didn't generate them).
ZONE_NAMES = {
    # ── Ahkuilon outdoor world ────────────────────────────────────────────────
    0:   "Main World (Ahkuilon)",
    # ── Interior zones (confirmed tile data) ─────────────────────────────────
    2:   "Zone 2",
    3:   "Zone 3",
    4:   "Zone 4",
    5:   "Zone 5",
    # ── Dungeon / Keep zones (30-58 range) ───────────────────────────────────
    30:  "Zone 30",
    31:  "Zone 31",
    32:  "Zone 32",
    36:  "Zone 36",
    37:  "Zone 37",
    39:  "Zone 39",
    41:  "Zone 41",
    44:  "Zone 44",
    45:  "Zone 45",
    46:  "Zone 46",
    48:  "Zone 48",
    49:  "Zone 49",
    51:  "Zone 51",
    52:  "Zone 52",
    53:  "Zone 53",
    54:  "Zone 54",
    55:  "Zone 55",
    56:  "Zone 56",
    57:  "Zone 57",
    58:  "Zone 58",
    # ── Large zones ───────────────────────────────────────────────────────────
    73:  "Zone 73",
    83:  "Zone 83",
    100: "Zone 100",
    101: "Zone 101",
    102: "Zone 102",
    205: "Zone 205",
}


def _get_unextracted_modules() -> List[str]:
    """Return stems of .rvm module files that exist but haven't been extracted yet."""
    unextracted = []
    modules_dir = GAME_DIR / "Modules"
    if not modules_dir.exists():
        candidates = list(GAME_DIR.glob("*.rvm"))
    else:
        candidates = list(modules_dir.glob("*.rvm")) + list(GAME_DIR.glob("*.rvm"))
    for rvm in candidates:
        stem = rvm.stem
        out_dir = EXTRACT_DIR / stem
        if not out_dir.exists() or not any(out_dir.rglob("*")):
            unextracted.append(stem)
    return sorted(unextracted)


# ═══════════════════════════════════════════════════════════════════════════════
#  WORLD MAP TAB
# ═══════════════════════════════════════════════════════════════════════════════

class WorldMapTab(tk.Frame):
    def __init__(self, parent, status: StatusBar):
        super().__init__(parent, bg=BG_MID)
        self._status  = status
        self._photo   = None
        self._img     = None
        self._zoom    = 1.0
        self._zones   = []
        self._cur_zone = tk.StringVar(value="")
        self._cache    = {}      # zone -> PIL Image
        self._build_ui()
        self.after(100, self._init_load)

    def _build_ui(self):
        # ── Toolbar ──────────────────────────────────────────────────────────
        bar = tk.Frame(self, bg=BG_DARK, pady=4)
        bar.pack(fill="x")

        tk.Label(bar, text="Zone:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 10)).pack(side="left", padx=(10, 4))

        self._zone_combo = ttk.Combobox(bar, textvariable=self._cur_zone,
                                         state="readonly", width=32,
                                         font=("Segoe UI", 10))
        self._zone_combo.pack(side="left", padx=4)
        self._zone_combo.bind("<<ComboboxSelected>>", self._on_zone_change)

        tk.Button(bar, text="Stitch Zone", command=self._stitch_current,
                  bg=ACCENT, fg="white", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10
                  ).pack(side="left", padx=8)

        tk.Button(bar, text="Save PNG", command=self._save_current,
                  bg=ACCENT2, fg="white", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10
                  ).pack(side="left", padx=4)

        self._extract_btn = tk.Button(
                  bar, text="⬇ Extract Modules", command=self._extract_missing_modules,
                  bg="#5a3070", fg="white", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10)
        self._extract_btn.pack(side="left", padx=4)

        # Zoom controls
        tk.Label(bar, text="Zoom:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 10)).pack(side="left", padx=(20, 4))
        for label, val in [("25%", 0.25), ("50%", 0.5), ("100%", 1.0)]:
            tk.Button(bar, text=label, bg=BG_PANEL, fg=FG_TEXT, relief="flat",
                      font=("Segoe UI", 9), padx=6,
                      command=lambda v=val: self._set_zoom(v)
                      ).pack(side="left", padx=2)

        self._tile_lbl = tk.Label(bar, text="", bg=BG_DARK, fg=FG_DIM,
                                   font=("Segoe UI", 9))
        self._tile_lbl.pack(side="right", padx=12)

        # ── Scrollable canvas ─────────────────────────────────────────────────
        frame = tk.Frame(self, bg=BG_MID)
        frame.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(frame, bg="#0a0a14", cursor="crosshair",
                                  highlightthickness=0)
        h_sb = ttk.Scrollbar(frame, orient="horizontal",
                               command=self._canvas.xview)
        v_sb = ttk.Scrollbar(frame, orient="vertical",
                               command=self._canvas.yview)
        self._canvas.configure(xscrollcommand=h_sb.set,
                                yscrollcommand=v_sb.set)
        h_sb.pack(side="bottom", fill="x")
        v_sb.pack(side="right",  fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._canvas.bind("<MouseWheel>", self._on_wheel)
        self._canvas.bind("<ButtonPress-2>",   self._pan_start)
        self._canvas.bind("<B2-Motion>",        self._pan_move)

        self._map_item  = None
        self._pan_start_x = 0
        self._pan_start_y = 0

    def _pan_start(self, e):
        self._canvas.scan_mark(e.x, e.y)

    def _pan_move(self, e):
        self._canvas.scan_dragto(e.x, e.y, gain=1)

    def _on_wheel(self, e):
        factor = 1.1 if e.delta > 0 else 0.9
        self._zoom = max(0.1, min(4.0, self._zoom * factor))
        self._refresh_display()

    def _init_load(self):
        # _zones now stores ZoneKey = (module_name, zone_number) tuples
        self._zones = get_all_zone_keys()

        # Count unextracted modules so we can prompt the user
        unextracted = _get_unextracted_modules()
        if unextracted:
            hint = f"  ({len(unextracted)} unextracted module(s): {', '.join(unextracted[:4])}{'…' if len(unextracted)>4 else ''}  — click ⬇ Extract Modules)"
        else:
            hint = ""

        if not self._zones:
            self._status.set(
                "No automap tiles found. Run archive_extractor.py first, then restart." + hint)
            return

        def _label(mk: ZoneKey) -> str:
            module, z = mk
            name = ZONE_NAMES.get(z, f"Zone {z}")
            if module.lower() == "ahkuilon":
                return f"Zone {z}  —  {name}"
            return f"Zone {z}  —  {module}  ({name})"

        labels = [_label(mk) for mk in self._zones]
        self._zone_combo['values'] = labels
        self._zone_combo.current(0)

        modules_found = len(set(m for m, _ in self._zones))
        status_extra = f"  |  {hint.strip()}" if hint else ""
        self._status.set(
            f"{len(self._zones)} zone(s) across {modules_found} module(s) found{status_extra}")

        # Check for pre-rendered zone 0 (main world module)
        main_module = next((m for m, z in self._zones if m.lower() == "ahkuilon" and z == 0),
                           self._zones[0][0] if self._zones else "ahkuilon")
        cached_path = RENDERS_DIR / f"world_map_{main_module}_zone0.png"
        if not cached_path.exists():
            cached_path = RENDERS_DIR / "world_map_zone0.png"   # legacy name
        if cached_path.exists() and HAS_PIL:
            img = Image.open(cached_path)
            self._cache[(main_module, 0)] = img
            self._img = img
            self._zoom = 0.25
            self._refresh_display()
            tiles = get_automap_tiles(0, main_module)
            self._tile_lbl.config(
                text=f"{main_module} Zone 0: {len(tiles)} tiles  |  {img.width}x{img.height}px")
        else:
            self._stitch_current()

    def _extract_missing_modules(self):
        """Extract any .rvm module files that haven't been extracted yet."""
        unextracted = _get_unextracted_modules()
        if not unextracted:
            self._status.set("All modules already extracted.")
            return

        self._extract_btn.config(state="disabled", text="Extracting…")
        self._status.set(f"Extracting {len(unextracted)} module(s): {', '.join(unextracted)}…")

        def _worker():
            import zipfile as _zf
            done = []
            failed = []
            for stem in unextracted:
                # Try both Modules/ subdir and game root
                candidates = [
                    GAME_DIR / "Modules" / f"{stem}.rvm",
                    GAME_DIR / f"{stem}.rvm",
                ]
                src = next((p for p in candidates if p.exists()), None)
                if src is None:
                    failed.append(stem)
                    continue
                out_dir = EXTRACT_DIR / stem
                try:
                    out_dir.mkdir(parents=True, exist_ok=True)
                    with _zf.ZipFile(src) as zf:
                        zf.extractall(out_dir)
                    done.append(stem)
                except Exception as e:
                    failed.append(f"{stem}({e})")
            self.after(0, self._on_extract_done, done, failed)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_extract_done(self, done, failed):
        self._extract_btn.config(state="normal", text="⬇ Extract Modules")
        if done:
            self._status.set(
                f"Extracted: {', '.join(done)}. Reloading zones…")
            # Reload the zone list now that new modules are available
            self._zones = get_all_zone_keys()

            def _label(mk: ZoneKey) -> str:
                module, z = mk
                name = ZONE_NAMES.get(z, f"Zone {z}")
                if module.lower() == "ahkuilon":
                    return f"Zone {z}  —  {name}"
                return f"Zone {z}  —  {module}  ({name})"

            self._zone_combo['values'] = [_label(mk) for mk in self._zones]
            if self._zones:
                self._zone_combo.current(0)
            msg = f"Extracted {len(done)} module(s). {len(self._zones)} zones now available."
            if failed:
                msg += f"  Failed: {', '.join(failed)}"
            self._status.set(msg)
        else:
            self._status.set(
                f"Extraction failed — .rvm files not found in {GAME_DIR}/Modules/. "
                f"Failed: {', '.join(failed)}")


    def _current_zone_key(self) -> ZoneKey:
        """Return the (module, zone) key for the currently selected combobox entry."""
        idx = self._zone_combo.current()
        if 0 <= idx < len(self._zones):
            return self._zones[idx]
        return self._zones[0] if self._zones else ("ahkuilon", 0)

    def _on_zone_change(self, _=None):
        mk = self._current_zone_key()
        if mk in self._cache:
            self._img  = self._cache[mk]
            self._zoom = 0.25
            self._refresh_display()
            module, z = mk
            self._tile_lbl.config(
                text=f"{module} Zone {z}: {self._img.width}x{self._img.height}px (cached)")
        else:
            self._stitch_current()

    def _stitch_current(self):
        mk = self._current_zone_key()
        module, zone = mk
        self._status.set(f"Stitching {module} zone {zone}...")

        def _worker():
            img = stitch_zone_map(zone, module)
            self.after(0, lambda: self._on_stitch_done(mk, img))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_stitch_done(self, mk: ZoneKey, img):
        module, zone = mk
        if img is None:
            self._status.set(f"No tiles found for {module} zone {zone}  (check Diagnose for tile counts)")
            return
        self._cache[mk] = img
        self._img   = img
        self._zoom  = 0.25
        self._refresh_display()
        tiles = get_automap_tiles(zone, module)
        self._tile_lbl.config(
            text=f"{module} Zone {zone}: {len(tiles)} tiles  |  {img.width}x{img.height}px")
        self._status.set(
            f"{module} zone {zone} stitched — {len(tiles)} tiles, {img.width}x{img.height}px")

    def _save_current(self):
        """Save the full-resolution stitched zone map as PNG (file dialog)."""
        if self._img is None:
            self._status.set("Nothing to save — stitch a zone first.")
            return
        module, zone = self._current_zone_key()
        RENDERS_DIR.mkdir(parents=True, exist_ok=True)
        default_name = f"world_map_{module}_zone{zone}.png"
        out = filedialog.asksaveasfilename(
            title="Save Zone Map as PNG",
            initialdir=str(RENDERS_DIR),
            initialfile=default_name,
            defaultextension=".png",
            filetypes=[("PNG Image", "*.png"), ("All files", "*.*")],
        )
        if not out:
            return
        self._img.save(out)
        self._status.set(
            f"Saved: {Path(out).name}  ({self._img.width}×{self._img.height}px)"
        )

    def _export_all_zones(self):
        """Stitch and save every available zone to PNG in the renders folder."""
        if not self._zones:
            self._status.set("No zones found.")
            return
        self._export_all_btn.config(state="disabled", text="Exporting…")
        total = len(self._zones)
        self._status.set(f"Exporting {total} zones…")

        def _worker():
            RENDERS_DIR.mkdir(parents=True, exist_ok=True)
            for done, mk in enumerate(self._zones):
                module, z = mk
                self.after(0, lambda m=module, z=z, d=done: self._status.set(
                    f"Stitching {m} zone {z}… ({d}/{total})"))
                img = stitch_zone_map(z, module)
                if img:
                    out = RENDERS_DIR / f"world_map_{module}_zone{z}.png"
                    img.save(out)
                    self._cache[mk] = img
            self.after(0, self._on_export_all_done, total)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_export_all_done(self, count: int):
        self._export_all_btn.config(state="normal", text="Export All Zones")
        self._status.set(
            f"Export complete — {count} zone maps saved to {RENDERS_DIR}")

    def _show_diagnose(self):
        """Show a popup with full Automaps directory diagnostic info."""
        win = tk.Toplevel(self)
        win.title("Automap Diagnostic")
        win.configure(bg=BG_DARK)
        win.geometry("700x540")

        tk.Label(win, text="AUTOMAP DIAGNOSTIC", bg=BG_DARK, fg=ACCENT,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=14, pady=(12, 4))

        txt = tk.Text(win, bg="#0c0c14", fg=FG_TEXT, font=("Consolas", 9),
                      relief="flat", wrap="none")
        sb_y = ttk.Scrollbar(win, orient="vertical",   command=txt.yview)
        sb_x = ttk.Scrollbar(win, orient="horizontal", command=txt.xview)
        txt.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        sb_x.pack(side="bottom", fill="x")
        sb_y.pack(side="right",  fill="y")
        txt.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        txt.tag_configure("h",    foreground=ACCENT,  font=("Segoe UI", 9, "bold"))
        txt.tag_configure("ok",   foreground="#80e080")
        txt.tag_configure("warn", foreground="#e0c060")
        txt.tag_configure("dim",  foreground=FG_DIM)

        def w(line, tag=""):
            txt.insert("end", line + "\n", tag)

        w(f"EXTRACT_DIR : {EXTRACT_DIR}", "dim")
        w(f"GAME_DIR    : {GAME_DIR}", "dim")
        w("")

        # --- Module directories ---
        w("MODULE DIRS WITH Automaps/", "h")
        amap_dirs = _all_automap_dirs()
        if amap_dirs:
            for d in amap_dirs:
                bmps = list(d.rglob("*.bmp"))
                w(f"  ✓ {d}  ({len(bmps)} bmp files)", "ok")
        else:
            w("  NONE FOUND", "warn")
        w("")

        # --- Unextracted modules ---
        unext = _get_unextracted_modules()
        w("UNEXTRACTED .rvm MODULES", "h")
        if unext:
            for m in unext:
                w(f"  ! {m}  ← click '⬇ Extract Modules' to extract", "warn")
        else:
            w("  All found modules are extracted", "ok")
        w("")

        # --- All bmp files found ---
        w("ALL BMP FILES FOUND (rglob)", "h")
        all_bmps: List[Path] = []
        for d in amap_dirs:
            all_bmps.extend(d.rglob("*.bmp"))
        all_bmps.sort()
        w(f"  Total: {len(all_bmps)}")

        zone_counts: dict = {}
        bad: List[str] = []
        for f in all_bmps:
            parts = f.stem.split('_')
            if len(parts) == 3:
                try:
                    z = int(parts[0])
                    zone_counts[z] = zone_counts.get(z, 0) + 1
                    continue
                except ValueError:
                    pass
            bad.append(f.name)

        w("")
        w("ZONE TILE COUNTS", "h")
        for z in sorted(zone_counts):
            w(f"  Zone {z:4d} : {zone_counts[z]:5d} tiles", "ok")

        if bad:
            w("")
            w(f"UNPARSEABLE FILENAMES ({len(bad)})", "h")
            for b in bad[:20]:
                w(f"  {b}", "warn")
            if len(bad) > 20:
                w(f"  … and {len(bad)-20} more", "dim")

        # --- Modules folder contents ---
        w("")
        w("MODULES FOLDER CONTENTS", "h")
        mdir = GAME_DIR / "Modules"
        if mdir.exists():
            for f in sorted(mdir.iterdir()):
                w(f"  {f.name}  ({f.stat().st_size // 1024} KB)", "ok")
        else:
            w(f"  {mdir}  — NOT FOUND", "warn")
            w("  (town/orc-camp automaps live in Modules/*.rvm)", "dim")

        txt.configure(state="disabled")

    def _refresh_display(self):
        if self._img is None or not HAS_PIL:
            return
        w = max(1, int(self._img.width  * self._zoom))
        h = max(1, int(self._img.height * self._zoom))
        scaled = self._img.resize((w, h), Image.NEAREST)
        self._photo = ImageTk.PhotoImage(scaled)
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor="nw", image=self._photo)
        self._canvas.configure(scrollregion=(0, 0, w, h))


# ═══════════════════════════════════════════════════════════════════════════════
#  CHARACTER GALLERY TAB
# ═══════════════════════════════════════════════════════════════════════════════

class CharCard(tk.Frame):
    """A single character card widget."""
    def __init__(self, parent, char: Dict, photo=None, on_click=None, **kwargs):
        super().__init__(parent, bg=BG_CARD, bd=0, highlightthickness=1,
                         highlightbackground=BORDER, **kwargs)
        self._on_click = on_click
        self._char     = char

        # Portrait
        img_frame = tk.Frame(self, bg=BG_CARD, padx=4, pady=4)
        img_frame.pack(fill="x")
        if photo:
            lbl = tk.Label(img_frame, image=photo, bg=BG_CARD)
            lbl.pack()
        else:
            tk.Label(img_frame, text="?", bg=BG_MID, fg=FG_DIM,
                     width=8, height=4, font=("Segoe UI", 18)).pack()

        # Name
        tk.Label(self, text=char["name"], bg=BG_CARD, fg=FG_TEXT,
                 font=("Segoe UI", 9, "bold"), wraplength=110,
                 justify="center").pack(pady=(0, 2))

        # Quick stats
        cls  = char.get("class", "") or "—"
        atks = char.get("attack_count", 0)
        grp  = (char.get("groups", "") or "—").split(",")[0]
        tk.Label(self, text=f"Class: {cls}", bg=BG_CARD, fg=ACCENT2,
                 font=("Segoe UI", 8)).pack()
        tk.Label(self, text=f"Group: {grp}", bg=BG_CARD, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack()
        tk.Label(self, text=f"Attacks: {atks}", bg=BG_CARD, fg=ACCENT3,
                 font=("Segoe UI", 8)).pack(pady=(0, 4))

        # Click binding
        for w in self.winfo_children() + [self]:
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>",    lambda e: self.config(highlightbackground=ACCENT))
            w.bind("<Leave>",    lambda e: self.config(highlightbackground=BORDER))

    def _click(self, _=None):
        if self._on_click:
            self._on_click(self._char)


class CharacterGalleryTab(tk.Frame):
    def __init__(self, parent, status: StatusBar):
        super().__init__(parent, bg=BG_MID)
        self._status  = status
        self._photos  = {}
        self._chars   = []
        self._filter  = tk.StringVar()
        self._filter.trace_add("write", self._apply_filter)
        self._build_ui()
        self.after(200, self._load_all)

    def _build_ui(self):
        # ── Toolbar ──────────────────────────────────────────────────────────
        bar = tk.Frame(self, bg=BG_DARK, pady=6)
        bar.pack(fill="x")

        tk.Label(bar, text="Filter:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 10)).pack(side="left", padx=(10, 4))
        self._search = tk.Entry(bar, textvariable=self._filter,
                                 bg=BG_PANEL, fg=FG_TEXT,
                                 insertbackground=FG_TEXT,
                                 font=("Segoe UI", 10), relief="flat",
                                 width=24)
        self._search.pack(side="left", padx=4)

        tk.Button(bar, text="Export All Portraits", bg=ACCENT2, fg="#000",
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=8,
                  command=self._export_all).pack(side="right", padx=4)
        self._count_lbl = tk.Label(bar, text="", bg=BG_DARK, fg=FG_DIM,
                                    font=("Segoe UI", 9))
        self._count_lbl.pack(side="right", padx=12)

        # ── Panes ─────────────────────────────────────────────────────────────
        pane = tk.PanedWindow(self, orient="horizontal", bg=BG_DARK,
                               sashrelief="flat", sashwidth=6)
        pane.pack(fill="both", expand=True)

        # Left: gallery grid
        left = tk.Frame(pane, bg=BG_MID)
        pane.add(left, minsize=400)
        self._scroll = ScrollFrame(left, bg=BG_MID)
        self._scroll.pack(fill="both", expand=True)
        self._grid = self._scroll.inner

        # Right: detail panel
        right = tk.Frame(pane, bg=BG_PANEL, padx=12, pady=12)
        pane.add(right, minsize=260)
        tk.Label(right, text="CHARACTER DETAILS", bg=BG_PANEL, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Separator(right).pack(fill="x", pady=6)

        self._detail_name = tk.Label(right, text="Select a character",
                                      bg=BG_PANEL, fg=FG_TEXT,
                                      font=("Segoe UI", 14, "bold"),
                                      wraplength=240, justify="left")
        self._detail_name.pack(anchor="w", pady=(0, 4))

        self._detail_portrait = tk.Label(right, bg=BG_PANEL)
        self._detail_portrait.pack(anchor="w", pady=4)

        self._detail_text = tk.Text(right, bg=BG_PANEL, fg=FG_TEXT,
                                     font=("Consolas", 9),
                                     relief="flat", wrap="word",
                                     state="disabled", height=32,
                                     cursor="arrow")
        sb = ttk.Scrollbar(right, orient="vertical",
                            command=self._detail_text.yview)
        self._detail_text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", pady=(8, 0))
        self._detail_text.pack(fill="both", expand=True, pady=(8, 0))

        # Text tags
        self._detail_text.tag_configure("h",    foreground=ACCENT,
                                                 font=("Segoe UI", 9, "bold"))
        self._detail_text.tag_configure("v",    foreground=FG_TEXT,
                                                 font=("Consolas", 9))
        self._detail_text.tag_configure("kv",   foreground=ACCENT2,
                                                 font=("Segoe UI", 9))
        self._detail_text.tag_configure("dim",  foreground=FG_DIM,
                                                 font=("Segoe UI", 8))
        self._detail_text.tag_configure("link", foreground="#6ab0f5",
                                                 font=("Segoe UI", 8),
                                                 underline=True)
        self._detail_text.tag_configure("good", foreground="#80e080",
                                                 font=("Consolas", 9))
        self._detail_text.tag_configure("warn", foreground="#e0c060",
                                                 font=("Consolas", 9))
        self._detail_text.tag_configure("anim", foreground="#c080ff",
                                                 font=("Consolas", 9))
        self._detail_text.tag_configure("raw",  foreground="#607060",
                                                 font=("Consolas", 8))

    def _load_all(self):
        self._status.set("Parsing char.def...")
        self._chars = parse_char_def()
        self._status.set(f"Loading portraits for {len(self._chars)} characters...")
        self._load_portraits()
        self._render_gallery(self._chars)
        self._count_lbl.config(text=f"{len(self._chars)} characters")
        self._status.set(f"Character gallery: {len(self._chars)} characters loaded")

    def _load_portraits(self):
        """Load portrait images (PIL) for all characters."""
        if not HAS_PIL:
            return
        for ch in self._chars:
            name = ch["name"]
            portrait_path = find_portrait(name)
            if portrait_path:
                try:
                    img = Image.open(portrait_path).convert("RGB")
                    img = img.resize((96, 96), Image.LANCZOS)
                    self._photos[name] = ImageTk.PhotoImage(img)
                    continue
                except Exception:
                    pass
            # Placeholder
            img = make_placeholder_portrait(name, 96)
            if img:
                self._photos[name] = ImageTk.PhotoImage(img)

    def _render_gallery(self, chars: List[Dict]):
        for w in self._grid.winfo_children():
            w.destroy()

        cols = 5
        for i, ch in enumerate(chars):
            photo = self._photos.get(ch["name"])
            card  = CharCard(self._grid, ch, photo=photo,
                              on_click=self._show_detail)
            card.grid(row=i // cols, column=i % cols,
                      padx=6, pady=6, sticky="nw")

    def _apply_filter(self, *_):
        flt = self._filter.get().strip().lower()
        if not flt:
            filtered = self._chars
        else:
            filtered = [c for c in self._chars
                        if flt in c["name"].lower()
                        or flt in c.get("class", "").lower()
                        or flt in c.get("groups", "").lower()
                        or flt in c.get("script", "").lower()]
        self._render_gallery(filtered)
        self._count_lbl.config(text=f"{len(filtered)} / {len(self._chars)}")

    def _show_detail(self, char: Dict):
        name = char["name"]
        self._detail_name.config(text=name)

        # Portrait (larger in detail pane)
        portrait_path = find_portrait(name)
        if portrait_path and HAS_PIL:
            try:
                img = Image.open(portrait_path).convert("RGB").resize(
                    (128, 128), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self._detail_portrait.config(image=photo, text="")
                self._detail_portrait._photo = photo
            except Exception:
                self._detail_portrait.config(image="", text="")
        else:
            photo = self._photos.get(name)
            if photo:
                self._detail_portrait.config(image=photo, text="")
                self._detail_portrait._photo = photo
            else:
                self._detail_portrait.config(image="", text="")

        # i3d / animation info
        i3d_path    = find_char_i3d(name)
        anim_states = parse_i3d_anim_states(i3d_path) if i3d_path else []

        txt = self._detail_text
        txt.configure(state="normal")
        txt.delete("1.0", "end")

        # Bind tag so clicking a "link" opens Explorer/Finder
        txt.tag_unbind("link", "<Button-1>")

        def row(label, value, vtag="v"):
            txt.insert("end", f"  {label:<16}", "kv")
            txt.insert("end", f"{value or '—'}\n", vtag)

        def file_row(label, path: Optional[Path]):
            txt.insert("end", f"  {label:<16}", "kv")
            if path and path.exists():
                display = path.name
                start   = txt.index("end-1c")
                txt.insert("end", display, "link")
                end = txt.index("end-1c")
                tag = f"link_{path}"
                txt.tag_add(tag, start, end)
                txt.tag_configure(tag, foreground="#6ab0f5", underline=True)
                txt.tag_bind(tag, "<Button-1>",
                             lambda e, p=path: self._open_path(p))
                txt.tag_bind(tag, "<Enter>",
                             lambda e: txt.config(cursor="hand2"))
                txt.tag_bind(tag, "<Leave>",
                             lambda e: txt.config(cursor="arrow"))
                txt.insert("end", "\n")
            else:
                txt.insert("end", "not found\n", "dim")

        # ── IDENTITY ─────────────────────────────────────────────────────────
        txt.insert("end", "IDENTITY\n", "h")
        row("Name",    name)
        row("Class",   char.get("class"))
        row("Groups",  char.get("groups"))
        row("Enemies", char.get("enemies"))
        if char.get("script"):
            row("Script",  char.get("script"))

        # ── FILES ────────────────────────────────────────────────────────────
        txt.insert("end", "\nFILES\n", "h")
        file_row("Portrait",   portrait_path)
        file_row("3D Model",   i3d_path)
        if CHAR_DEF.exists():
            file_row("char.def",   CHAR_DEF)

        # ── COMBAT ───────────────────────────────────────────────────────────
        txt.insert("end", "\nCOMBAT\n", "h")
        row("Health",     str(char.get("health", 0)) if char.get("health") else "—")
        row("Speed",      str(char.get("speed",  0)) if char.get("speed")  else "—")
        row("Block %",    f"{char.get('block_pct', 0)}%")
        row("Weapon DMG", str(char.get("weapon_dmg", 0)))
        row("Sight",      str(char.get("sight", 0)))

        # Attacks
        attacks = char.get("attacks", [])
        if attacks:
            txt.insert("end", f"\nATTACKS  ({len(attacks)})\n", "h")
            for atk in attacks:
                aname = atk.get("name", "?")
                dmg   = atk.get("damage", "")
                anim  = atk.get("anim", "")
                txt.insert("end", f"  • {aname}", "v")
                if dmg:
                    txt.insert("end", f"  dmg:{dmg}", "warn")
                if anim:
                    txt.insert("end", f"  [{anim}]", "anim")
                txt.insert("end", "\n")
        elif char.get("attack_count", 0):
            row("Attacks", str(char["attack_count"]))

        # Impacts
        impacts = char.get("impacts", [])
        if impacts:
            txt.insert("end", f"\nIMPACTS  ({len(impacts)})\n", "h")
            for imp in impacts:
                txt.insert("end", f"  • {imp.get('name','?')}\n", "v")
        elif char.get("impact_count", 0):
            row("Impacts", str(char["impact_count"]))

        # Spells
        spells = char.get("spells", [])
        if spells:
            txt.insert("end", f"\nSPELLS  ({len(spells)})\n", "h")
            for sp in spells:
                txt.insert("end", f"  • {sp}\n", "good")

        # ── 3D MODEL / ANIMATIONS ────────────────────────────────────────────
        txt.insert("end", "\n3D MODEL\n", "h")
        if i3d_path:
            row("File",   i3d_path.name)
            row("Size",   f"{i3d_path.stat().st_size // 1024} KB")
            if anim_states:
                txt.insert("end", f"\nANIMATION STATES  ({len(anim_states)})\n", "h")
                for st in anim_states:
                    sname  = st["name"]
                    frames = st["frames"]
                    w, h   = st.get("width", 0), st.get("height", 0)
                    txt.insert("end", f"  {sname:<14}", "anim")
                    txt.insert("end", f"  {frames} frame{'s' if frames!=1 else ''}", "v")
                    if w and h:
                        txt.insert("end", f"  ({w}×{h})", "dim")
                    txt.insert("end", "\n")

                # Show which states char.def references
                anim_refs = char.get("anim_refs", [])
                if anim_refs:
                    known   = {st["name"] for st in anim_states}
                    txt.insert("end", f"\nANIM REFS IN char.def\n", "h")
                    for ref in anim_refs:
                        found = ref in known
                        txt.insert("end", f"  {'✓' if found else '?'} {ref}\n",
                                   "good" if found else "warn")
            else:
                row("Anim states", "0 (header unreadable)")
        else:
            txt.insert("end", "  No .i3d file found for this character.\n", "dim")
            txt.insert("end", "  Expected in:\n", "dim")
            txt.insert("end", f"  {IMAGERY_ASSETS / 'Chars'}\n", "dim")

        # ── RAW char.def BLOCK ───────────────────────────────────────────────
        raw_body = char.get("_raw", "")
        if raw_body:
            txt.insert("end", "\n▼ RAW char.def  (click to expand)\n", "h")
            # Collapsed by default — show first 3 lines
            lines = raw_body.splitlines()
            preview = "\n".join(f"  {l}" for l in lines[:3])
            if len(lines) > 3:
                preview += f"\n  … ({len(lines)-3} more lines)"
            txt.insert("end", preview + "\n", "raw")

            # Tag to expand/collapse
            raw_start = txt.index("end-1c linestart")
            full_raw  = "\n".join(f"  {l}" for l in lines) + "\n"
            self._raw_expanded = getattr(self, "_raw_expanded", {})
            self._raw_expanded[name] = False

            def _toggle_raw(e, n=name, full=full_raw, preview_text=preview+"\n"):
                expanded = self._raw_expanded.get(n, False)
                txt.configure(state="normal")
                # Find the raw block
                idx = txt.search("▼ RAW char.def", "1.0")
                if not idx:
                    txt.configure(state="disabled")
                    return
                block_start = txt.index(f"{idx} +1 line")
                block_end   = txt.index(f"{block_start} lineend +1c")
                # Count lines in current raw section
                cur = txt.get(block_start, "end")
                if not expanded:
                    # Expand: replace preview with full
                    txt.delete(block_start, "end")
                    txt.insert(block_start, full, "raw")
                    self._raw_expanded[n] = True
                else:
                    txt.delete(block_start, "end")
                    txt.insert(block_start, preview_text, "raw")
                    self._raw_expanded[n] = False
                txt.configure(state="disabled")

            # Bind the header line
            h_start = txt.search("▼ RAW char.def", "1.0")
            if h_start:
                h_end = f"{h_start} lineend"
                txt.tag_add("raw_toggle", h_start, h_end)
                txt.tag_configure("raw_toggle", foreground=ACCENT,
                                   font=("Segoe UI", 9, "bold"), underline=True)
                txt.tag_bind("raw_toggle", "<Button-1>", _toggle_raw)
                txt.tag_bind("raw_toggle", "<Enter>",
                             lambda e: txt.config(cursor="hand2"))
                txt.tag_bind("raw_toggle", "<Leave>",
                             lambda e: txt.config(cursor="arrow"))

        txt.configure(state="disabled")

    def _open_path(self, path: Path):
        """Open a file or its parent folder in the OS file manager."""
        import subprocess, sys
        try:
            target = path if path.is_dir() else path.parent
            if sys.platform == "win32":
                subprocess.Popen(["explorer", str(target)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
        except Exception:
            pass

    def _export_all(self):
        if not HAS_PIL:
            self._status.set("PIL not available")
            return
        if not self._chars:
            self._status.set("No characters loaded")
            return
        dest = RENDERS_DIR / "Characters"
        dest.mkdir(parents=True, exist_ok=True)
        ok = skip = 0
        for ch in self._chars:
            name = ch["name"]
            portrait_path = find_portrait(name)
            try:
                if portrait_path:
                    img = Image.open(portrait_path).convert("RGB")
                else:
                    img = make_placeholder_portrait(name, 128)
                if img:
                    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)
                    img.save(str(dest / f"{safe}.png"))
                    ok += 1
                else:
                    skip += 1
            except Exception:
                skip += 1
        self._status.set(f"Characters exported: {ok} portraits → {dest}")


# ═══════════════════════════════════════════════════════════════════════════════
#  EQUIPMENT TAB
# ═══════════════════════════════════════════════════════════════════════════════

class EquipmentTab(tk.Frame):
    def __init__(self, parent, status: StatusBar):
        super().__init__(parent, bg=BG_MID)
        self._status  = status
        self._weapons = []
        self._armors  = []
        self._build_ui()
        self.after(300, self._load_all)

    def _build_ui(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=4, pady=4)

        self._wpn_frame = tk.Frame(nb, bg=BG_MID)
        self._arm_frame = tk.Frame(nb, bg=BG_MID)
        nb.add(self._wpn_frame, text=f"  Weapons  ")
        nb.add(self._arm_frame, text=f"  Armour   ")

        self._build_weapon_panel(self._wpn_frame)
        self._build_armor_panel (self._arm_frame)

    def _build_weapon_panel(self, parent):
        # Toolbar
        bar = tk.Frame(parent, bg=BG_DARK, pady=4)
        bar.pack(fill="x")
        self._wpn_filter_var = tk.StringVar()
        tk.Label(bar, text="Filter:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 10)).pack(side="left", padx=(10,4))
        tk.Entry(bar, textvariable=self._wpn_filter_var,
                  bg=BG_PANEL, fg=FG_TEXT, insertbackground=FG_TEXT,
                  font=("Segoe UI", 10), relief="flat", width=20
                  ).pack(side="left", padx=4)
        self._wpn_filter_var.trace_add("write", self._filter_weapons)
        tk.Button(bar, text="Export All Icons", bg=ACCENT2, fg="#000",
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=8,
                  command=self._export_all_weapons).pack(side="right", padx=4)
        self._wpn_count = tk.Label(bar, text="", bg=BG_DARK, fg=FG_DIM,
                                    font=("Segoe UI", 9))
        self._wpn_count.pack(side="right", padx=12)

        # Table + detail pane
        pane = tk.PanedWindow(parent, orient="horizontal", bg=BG_DARK,
                               sashwidth=6, sashrelief="flat")
        pane.pack(fill="both", expand=True)

        # Treeview
        tv_frame = tk.Frame(pane, bg=BG_MID)
        pane.add(tv_frame, minsize=400)

        cols = ("name","type","dmg","value","min_str")
        self._wpn_tv = ttk.Treeview(tv_frame, columns=cols, show="headings",
                                      selectmode="browse")
        self._wpn_tv.heading("name",    text="Weapon",         anchor="w")
        self._wpn_tv.heading("type",    text="Type",           anchor="w")
        self._wpn_tv.heading("dmg",     text="Damage",         anchor="center")
        self._wpn_tv.heading("value",   text="Value",          anchor="center")
        self._wpn_tv.heading("min_str", text="Min STR",        anchor="center")
        self._wpn_tv.column("name",    width=200, stretch=True)
        self._wpn_tv.column("type",    width=110, stretch=False)
        self._wpn_tv.column("dmg",     width=60,  stretch=False, anchor="center")
        self._wpn_tv.column("value",   width=70,  stretch=False, anchor="center")
        self._wpn_tv.column("min_str", width=65,  stretch=False, anchor="center")

        sb = ttk.Scrollbar(tv_frame, orient="vertical",
                            command=self._wpn_tv.yview)
        self._wpn_tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._wpn_tv.pack(fill="both", expand=True)
        self._wpn_tv.bind("<<TreeviewSelect>>", self._on_weapon_select)

        # Detail
        det = tk.Frame(pane, bg=BG_PANEL, padx=12, pady=12)
        pane.add(det, minsize=220)
        tk.Label(det, text="WEAPON DETAILS", bg=BG_PANEL, fg=GOLD,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Separator(det).pack(fill="x", pady=6)
        self._wpn_detail = tk.Text(det, bg=BG_PANEL, fg=FG_TEXT,
                                    font=("Consolas", 9), relief="flat",
                                    state="disabled", wrap="word", height=20)
        self._wpn_detail.pack(fill="both", expand=True)
        self._wpn_detail.tag_configure("h",  foreground=GOLD, font=("Segoe UI",10,"bold"))
        self._wpn_detail.tag_configure("kv", foreground=ACCENT2, font=("Segoe UI",9))

        # tn thumbnail display
        self._wpn_img_lbl = tk.Label(det, bg=BG_PANEL)
        self._wpn_img_lbl.pack(pady=4)

    def _build_armor_panel(self, parent):
        bar = tk.Frame(parent, bg=BG_DARK, pady=4)
        bar.pack(fill="x")
        self._arm_filter_var = tk.StringVar()
        tk.Label(bar, text="Filter:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 10)).pack(side="left", padx=(10,4))
        tk.Entry(bar, textvariable=self._arm_filter_var,
                  bg=BG_PANEL, fg=FG_TEXT, insertbackground=FG_TEXT,
                  font=("Segoe UI", 10), relief="flat", width=20
                  ).pack(side="left", padx=4)
        self._arm_filter_var.trace_add("write", self._filter_armors)
        tk.Button(bar, text="Export All Icons", bg=ACCENT2, fg="#000",
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=8,
                  command=self._export_all_armors).pack(side="right", padx=4)
        self._arm_count = tk.Label(bar, text="", bg=BG_DARK, fg=FG_DIM,
                                    font=("Segoe UI", 9))
        self._arm_count.pack(side="right", padx=12)

        pane = tk.PanedWindow(parent, orient="horizontal", bg=BG_DARK,
                               sashwidth=6, sashrelief="flat")
        pane.pack(fill="both", expand=True)

        tv_frame = tk.Frame(pane, bg=BG_MID)
        pane.add(tv_frame, minsize=400)

        cols = ("name","slot","prot","value","min_str")
        self._arm_tv = ttk.Treeview(tv_frame, columns=cols, show="headings",
                                      selectmode="browse")
        self._arm_tv.heading("name",  text="Armour",    anchor="w")
        self._arm_tv.heading("slot",  text="Slot",      anchor="w")
        self._arm_tv.heading("prot",  text="Protection",anchor="center")
        self._arm_tv.heading("value", text="Value",     anchor="center")
        self._arm_tv.heading("min_str",text="Min STR",  anchor="center")
        self._arm_tv.column("name",   width=220, stretch=True)
        self._arm_tv.column("slot",   width=90,  stretch=False)
        self._arm_tv.column("prot",   width=80,  stretch=False, anchor="center")
        self._arm_tv.column("value",  width=70,  stretch=False, anchor="center")
        self._arm_tv.column("min_str",width=65,  stretch=False, anchor="center")

        sb2 = ttk.Scrollbar(tv_frame, orient="vertical",
                             command=self._arm_tv.yview)
        self._arm_tv.configure(yscrollcommand=sb2.set)
        sb2.pack(side="right", fill="y")
        self._arm_tv.pack(fill="both", expand=True)
        self._arm_tv.bind("<<TreeviewSelect>>", self._on_armor_select)

        det2 = tk.Frame(pane, bg=BG_PANEL, padx=12, pady=12)
        pane.add(det2, minsize=220)
        tk.Label(det2, text="ARMOUR DETAILS", bg=BG_PANEL, fg=ACCENT3,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Separator(det2).pack(fill="x", pady=6)
        self._arm_detail = tk.Text(det2, bg=BG_PANEL, fg=FG_TEXT,
                                    font=("Consolas", 9), relief="flat",
                                    state="disabled", wrap="word", height=20)
        self._arm_detail.pack(fill="both", expand=True)
        self._arm_detail.tag_configure("h",  foreground=ACCENT3, font=("Segoe UI",10,"bold"))
        self._arm_detail.tag_configure("kv", foreground=ACCENT2, font=("Segoe UI",9))

        # tn thumbnail display
        self._arm_img_lbl = tk.Label(det2, bg=BG_PANEL)
        self._arm_img_lbl.pack(pady=4)

    def _load_all(self):
        self._status.set("Parsing weapon.def...")
        self._weapons = parse_weapon_def()
        self._status.set("Parsing armor.def...")
        self._armors  = parse_armor_def()
        self._populate_weapons(self._weapons)
        self._populate_armors (self._armors)
        self._wpn_count.config(text=f"{len(self._weapons)} weapons")
        self._arm_count.config(text=f"{len(self._armors)} armour pieces")
        self._status.set(
            f"Equipment loaded: {len(self._weapons)} weapons, {len(self._armors)} armour pieces")

    def _populate_weapons(self, data: List[Dict]):
        self._wpn_tv.delete(*self._wpn_tv.get_children())
        for w in sorted(data, key=lambda x: -x["damage"]):
            self._wpn_tv.insert("", "end",
                values=(w["name"], w["type_name"],
                        w["damage"], w["value"], w["min_str"]),
                tags=(w["name"],))

    def _populate_armors(self, data: List[Dict]):
        self._arm_tv.delete(*self._arm_tv.get_children())
        for a in sorted(data, key=lambda x: -x["protection"]):
            self._arm_tv.insert("", "end",
                values=(a["name"], a["slot_name"],
                        a["protection"], a["value"], a["min_str"]),
                tags=(a["name"],))

    def _filter_weapons(self, *_):
        flt = self._wpn_filter_var.get().strip().lower()
        filtered = [w for w in self._weapons
                    if flt in w["name"].lower() or flt in w["type_name"].lower()
                    ] if flt else self._weapons
        self._populate_weapons(filtered)
        self._wpn_count.config(text=f"{len(filtered)} / {len(self._weapons)}")

    def _filter_armors(self, *_):
        flt = self._arm_filter_var.get().strip().lower()
        filtered = [a for a in self._armors
                    if flt in a["name"].lower() or flt in a["slot_name"].lower()
                    ] if flt else self._armors
        self._populate_armors(filtered)
        self._arm_count.config(text=f"{len(filtered)} / {len(self._armors)}")

    def _on_weapon_select(self, _):
        sel = self._wpn_tv.selection()
        if not sel:
            return
        vals = self._wpn_tv.item(sel[0], "values")
        name = vals[0]
        w = next((x for x in self._weapons if x["name"] == name), None)
        if not w:
            return
        txt = self._wpn_detail
        txt.configure(state="normal")
        txt.delete("1.0", "end")
        txt.insert("end", f"{w['name']}\n", "h")

        def row(k, v):
            txt.insert("end", f"  {k:<18}", "kv")
            txt.insert("end", f"{v}\n")

        row("Type",         w["type_name"])
        row("Damage",       str(w["damage"]))
        row("Damage Mod",   str(w["damage_mod"]))
        row("Value (gold)", str(w["value"]))
        row("Min Strength", str(w["min_str"]))
        row("Poison",       str(w["poison"]))
        row("Combining",    str(w["combining"]))
        txt.configure(state="disabled")

        # Try to load .tn thumbnail
        self._load_equip_tn(name.lower(), self._wpn_img_lbl)

    def _on_armor_select(self, _):
        sel = self._arm_tv.selection()
        if not sel:
            return
        vals = self._arm_tv.item(sel[0], "values")
        name = vals[0]
        a = next((x for x in self._armors if x["name"] == name), None)
        if not a:
            return
        txt = self._arm_detail
        txt.configure(state="normal")
        txt.delete("1.0", "end")
        txt.insert("end", f"{a['name']}\n", "h")

        def row(k, v):
            txt.insert("end", f"  {k:<18}", "kv")
            txt.insert("end", f"{v}\n")

        row("Slot",         a["slot_name"])
        row("Protection",   str(a["protection"]))
        row("Value (gold)", str(a["value"]))
        row("Min Strength", str(a["min_str"]))
        row("Min Constit.", str(a["min_con"]))
        row("Stealth",      str(a["stealth"]))
        row("Resist Poison",str(a["resist_psn"]))
        row("Combining",    str(a["combining"]))
        txt.configure(state="disabled")

        # Try to load .tn thumbnail
        self._load_equip_tn(name.lower(), self._arm_img_lbl)

    def _load_equip_tn(self, name: str, lbl: tk.Label):
        """Load .tn thumbnail for equipment: exact match first, then prefix."""
        if not HAS_PIL:
            return
        equip_dir = THUMBNAILS / "Equip"
        if not equip_dir.exists():
            lbl.config(image="")
            return
        norm = name.lower().replace(" ", "").replace("-", "").replace("'", "")
        best: Optional[Path] = None
        best_score = 999
        for f in equip_dir.iterdir():
            if f.suffix.lower() != '.tn':
                continue
            fn = f.stem.lower().replace(" ", "").replace("-", "").replace("'", "")
            if fn == norm:
                best = f
                break
            # prefix match — prefer shorter distance
            if fn.startswith(norm) or norm.startswith(fn):
                score = abs(len(fn) - len(norm))
                if score < best_score:
                    best = f
                    best_score = score
        if best is None:
            lbl.config(image="")
            return
        try:
            raw = best.read_bytes()
            px  = _decode_tn_pixels(raw)
            if px is not None:
                rgba = Image.frombytes('RGBA', (16, 16), px)
                bg   = Image.new('RGB', (16, 16), (30, 42, 69))
                bg.paste(rgba, mask=rgba.split()[3])
                img  = bg.resize((64, 64), Image.NEAREST)
                ph   = ImageTk.PhotoImage(img)
                lbl.config(image=ph)
                lbl._photo = ph
                return
        except Exception:
            pass
        lbl.config(image="")

    def _export_all_weapons(self):
        self._export_equip_icons(self._weapons, "Weapons")

    def _export_all_armors(self):
        self._export_equip_icons(self._armors, "Armors")

    def _export_equip_icons(self, items: list, folder: str):
        if not HAS_PIL or not items:
            self._status.set(f"No {folder.lower()} loaded")
            return
        equip_dir = THUMBNAILS / "Equip"
        dest = RENDERS_DIR / folder
        dest.mkdir(parents=True, exist_ok=True)
        ok = skip = 0
        for item in items:
            name = item["name"]
            norm = name.lower().replace(" ", "").replace("-", "").replace("'", "")
            best = None; best_score = 999
            for f in equip_dir.iterdir():
                if f.suffix.lower() != '.tn':
                    continue
                fn = f.stem.lower().replace(" ", "").replace("-", "").replace("'", "")
                if fn == norm:
                    best = f; break
                if fn.startswith(norm) or norm.startswith(fn):
                    score = abs(len(fn) - len(norm))
                    if score < best_score:
                        best = f; best_score = score
            if best:
                img = _load_tn_image(best, 64)
                if img:
                    safe = "".join(c if c.isalnum() or c in " _-" else "_" for c in name)
                    try:
                        img.save(str(dest / f"{safe}.png")); ok += 1
                    except Exception:
                        skip += 1
                    continue
            skip += 1
        self._status.set(f"{folder} icons exported: {ok} saved, {skip} skipped → {dest}")


# ═══════════════════════════════════════════════════════════════════════════════
#  SPELLS TAB  (reworked: icons + talisman combos + variants)
# ═══════════════════════════════════════════════════════════════════════════════

def _load_spell_icon(icon_name: str, size: int = 48) -> Optional["Image.Image"]:
    """Load spell icon from Magic/ thumbnails directory."""
    magic_dir = THUMBNAILS / "Magic"
    if not magic_dir.exists():
        return None
    norm = icon_name.lower().replace(" ", "").replace("-", "")
    for f in magic_dir.iterdir():
        if f.suffix.lower() == '.tn':
            fn = f.stem.lower().replace(" ", "").replace("-", "")
            if fn == norm:
                return _load_tn_image(f, size)
    return None


def _load_talisman_icons(size: int = 24) -> Dict[str, Optional["ImageTk.PhotoImage"]]:
    """Load all talisman icons from Magic/ thumbnails, keyed by talisman name."""
    result: Dict[str, Optional["ImageTk.PhotoImage"]] = {}
    if not HAS_PIL:
        return result
    magic_dir = THUMBNAILS / "Magic"
    if not magic_dir.exists():
        return result
    for name in TALISMAN_MAP.values():
        fn = magic_dir / f"{name.lower()}.tn"
        if fn.exists():
            img = _load_tn_image(fn, size)
            if img:
                result[name] = ImageTk.PhotoImage(img)
    return result


def _bgr555_fast(px: bytes, w: int, h: int) -> "Image.Image":
    """BGR555 → RGBA; uses numpy if available for large images."""
    try:
        import numpy as np
        arr  = np.frombuffer(px, dtype='<u2').reshape(h, w)
        r    = ((arr >> 10) & 0x1F).astype(np.uint8) << 3
        g    = ((arr >>  5) & 0x1F).astype(np.uint8) << 3
        b    = (arr         & 0x1F).astype(np.uint8) << 3
        a    = np.where(arr == 0, np.uint8(0), np.uint8(255))
        rgba = np.stack([r, g, b, a], axis=-1)
        return Image.fromarray(rgba, 'RGBA')
    except ImportError:
        pass
    img = Image.new('RGBA', (w, h))
    pix = img.load()
    for idx in range(w * h):
        word = struct.unpack_from('<H', px, idx * 2)[0]
        r = ((word >> 10) & 0x1F) << 3
        g = ((word >>  5) & 0x1F) << 3
        b = ( word        & 0x1F) << 3
        pix[idx % w, idx // w] = (r, g, b, 0 if word == 0 else 255)
    return img


def _decode_dat_frame(dat_path: Path, frame_idx: int,
                      size: Optional[int] = None) -> Optional["Image.Image"]:
    """Decode frame_idx from a multi-frame CGSR .dat file (RGB555 direct pixels).

    Format: [CGSR magic][count:1][flags:3][total:4][total:4]
            [count×4 LE offsets starting at byte 16][data section]
    Each frame starts with a 4-byte size prefix then TBitmapData at offset +4.
    TBitmapData: width(4)+height(4)+...+datasize(4 at +68) + pixels at +72.
    Pixels are BGR555 16-bit when palsize==0 and datasize==w*h*2.
    """
    if not HAS_PIL:
        return None
    try:
        from PIL import Image as _Image
        raw = dat_path.read_bytes()
        if len(raw) < 20 or raw[:4] != b'CGSR':
            return None
        n = raw[4]
        if frame_idx < 0 or frame_idx >= n:
            return None
        offsets = [struct.unpack_from('<I', raw, 16 + i * 4)[0] for i in range(n)]
        data_start = 16 + n * 4
        abs_off = data_start + offsets[frame_idx]
        next_off = (data_start + offsets[frame_idx + 1]
                    if frame_idx + 1 < n else len(raw))
        fd = raw[abs_off:next_off]
        # Scan entire frame for TBitmapData (n=1 files pack data at large offsets)
        for i in range(0, max(0, len(fd) - 76), 4):
            w = struct.unpack_from('<i', fd, i)[0]
            h = struct.unpack_from('<i', fd, i + 4)[0]
            if not (1 <= w <= 2048 and 1 <= h <= 2048):
                continue
            palsize  = struct.unpack_from('<I', fd, i + 60)[0]
            datasize = struct.unpack_from('<I', fd, i + 68)[0]
            if palsize == 0 and datasize == w * h * 2:
                if i + 72 + datasize > len(fd):
                    continue
                px  = fd[i + 72: i + 72 + datasize]
                img = _bgr555_fast(px, w, h)
                if size and (w, h) != (size, size):
                    img = img.resize((size, size), _Image.LANCZOS)
                return img
    except Exception:
        pass
    return None


class SpellsTab(tk.Frame):
    def __init__(self, parent, status: StatusBar):
        super().__init__(parent, bg=BG_MID)
        self._status   = status
        self._spells   = []
        self._talis_ph : Dict[str, "ImageTk.PhotoImage"] = {}
        self._spell_ph : Dict[str, "ImageTk.PhotoImage"] = {}
        self._slot_ph  : Optional["ImageTk.PhotoImage"] = None   # spell slot badge
        self._variant_talis_widgets: list = []   # kept alive
        self._export_stop = False
        self._build_ui()
        self.after(400, self._load_all)

    def _build_ui(self):
        bar = tk.Frame(self, bg=BG_DARK, pady=4)
        bar.pack(fill="x")
        self._flt_var = tk.StringVar()
        tk.Label(bar, text="Filter:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 10)).pack(side="left", padx=(10, 4))
        tk.Entry(bar, textvariable=self._flt_var,
                 bg=BG_PANEL, fg=FG_TEXT, insertbackground=FG_TEXT,
                 font=("Segoe UI", 10), relief="flat", width=20
                 ).pack(side="left", padx=4)
        self._flt_var.trace_add("write", self._filter)
        self._export_btn = tk.Button(bar, text="Export All Icons", bg=ACCENT2,
                                     fg="#000", relief="flat",
                                     font=("Segoe UI", 9, "bold"), padx=8,
                                     command=self._export_all)
        self._export_btn.pack(side="right", padx=4)
        self._count_lbl = tk.Label(bar, text="", bg=BG_DARK, fg=FG_DIM,
                                   font=("Segoe UI", 9))
        self._count_lbl.pack(side="right", padx=12)

        pane = tk.PanedWindow(self, orient="horizontal", bg=BG_DARK,
                              sashwidth=6, sashrelief="flat")
        pane.pack(fill="both", expand=True)

        # ── Left: compact spell list ──────────────────────────────────────────
        lf = tk.Frame(pane, bg=BG_MID)
        pane.add(lf, minsize=240)
        cols = ("name", "mana", "type")
        self._tv = ttk.Treeview(lf, columns=cols, show="headings",
                                selectmode="browse")
        self._tv.heading("name", text="Spell",  anchor="w")
        self._tv.heading("mana", text="Mana",   anchor="center")
        self._tv.heading("type", text="Dmg Type", anchor="w")
        self._tv.column("name", width=180, stretch=True)
        self._tv.column("mana", width=50,  stretch=False, anchor="center")
        self._tv.column("type", width=80,  stretch=False)
        sb = ttk.Scrollbar(lf, orient="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._tv.pack(fill="both", expand=True)
        self._tv.bind("<<TreeviewSelect>>", self._on_select)

        # ── Right: rich detail card ───────────────────────────────────────────
        right = tk.Frame(pane, bg=BG_PANEL)
        pane.add(right, minsize=380)

        # Header row: icon + slot badge + name
        hdr = tk.Frame(right, bg=BG_PANEL, padx=10, pady=8)
        hdr.pack(fill="x")
        self._icon_lbl = tk.Label(hdr, bg=BG_PANEL)
        self._icon_lbl.pack(side="left", padx=(0, 4))
        self._slot_badge_lbl = tk.Label(hdr, bg=BG_PANEL)
        self._slot_badge_lbl.pack(side="left", padx=(0, 10))
        name_frame = tk.Frame(hdr, bg=BG_PANEL)
        name_frame.pack(side="left", fill="x", expand=True)
        self._spell_name_lbl = tk.Label(name_frame, text="Select a spell",
                                        bg=BG_PANEL, fg=FG_TEXT,
                                        font=("Segoe UI", 14, "bold"),
                                        anchor="w", wraplength=280)
        self._spell_name_lbl.pack(anchor="w")
        self._spell_desc_lbl = tk.Label(name_frame, text="",
                                        bg=BG_PANEL, fg=FG_DIM,
                                        font=("Segoe UI", 9), wraplength=280,
                                        justify="left", anchor="w")
        self._spell_desc_lbl.pack(anchor="w", pady=(2, 0))

        ttk.Separator(right).pack(fill="x")

        # Scrollable detail body
        scroll_frame = ScrollFrame(right, bg=BG_PANEL)
        scroll_frame.pack(fill="both", expand=True)
        self._body = scroll_frame.inner
        self._body.configure(bg=BG_PANEL)

    def _load_all(self):
        self._status.set("Parsing spell.def…")
        self._spells = parse_spell_def()
        if HAS_PIL:
            self._talis_ph = _load_talisman_icons(size=28)
            # Load spell-slot badge from bottombar.dat frame 2 (42×42)
            slot_img = _decode_dat_frame(RESOURCES / "bottombar.dat", 2, size=32)
            if slot_img:
                self._slot_ph = ImageTk.PhotoImage(slot_img)
        self._populate(self._spells)
        self._count_lbl.config(text=f"{len(self._spells)} spells")
        self._status.set(f"Spells loaded: {len(self._spells)}")

    def _populate(self, data: List[Dict]):
        self._tv.delete(*self._tv.get_children())
        for s in data:
            dt = DAMAGE_TYPE_NAMES.get(s.get("damage_type", ""), s.get("damage_type", "—"))
            self._tv.insert("", "end",
                values=(s["name"], s.get("mana", "—"), dt or "—"))

    def _filter(self, *_):
        flt = self._flt_var.get().strip().lower()
        filtered = ([s for s in self._spells if flt in s["name"].lower()]
                    if flt else self._spells)
        self._populate(filtered)
        self._count_lbl.config(text=f"{len(filtered)} / {len(self._spells)}")

    def _on_select(self, _):
        sel = self._tv.selection()
        if not sel:
            return
        name = self._tv.item(sel[0], "values")[0]
        s = next((x for x in self._spells if x["name"] == name), None)
        if s:
            self._show_detail(s)

    def _show_detail(self, s: Dict):
        # ── Header ───────────────────────────────────────────────────────────
        self._spell_name_lbl.config(text=s["name"])
        self._spell_desc_lbl.config(text=s.get("description", ""))

        # Icon + slot badge
        if HAS_PIL:
            icon_name = s.get("icon_name", s["name"])
            if icon_name not in self._spell_ph:
                img = _load_spell_icon(icon_name, size=56)
                if img:
                    self._spell_ph[icon_name] = ImageTk.PhotoImage(img)
                else:
                    self._spell_ph[icon_name] = None
            ph = self._spell_ph.get(icon_name)
            if ph:
                self._icon_lbl.config(image=ph, width=0)
                self._icon_lbl._ph = ph
            else:
                self._icon_lbl.config(image="", text="?", fg=FG_MUTED,
                                      font=("Segoe UI", 22), width=3)
            # Slot badge: show bottombar slot frame if available
            if self._slot_ph:
                self._slot_badge_lbl.config(image=self._slot_ph)
                self._slot_badge_lbl._ph = self._slot_ph
            else:
                self._slot_badge_lbl.config(image="")

        # ── Body: clear and rebuild ───────────────────────────────────────────
        for w in self._body.winfo_children():
            w.destroy()
        self._variant_talis_widgets.clear()

        def _sect(txt):
            tk.Label(self._body, text=txt, bg=BG_PANEL, fg=ACCENT,
                     font=("Segoe UI", 9, "bold"), anchor="w"
                     ).pack(fill="x", padx=10, pady=(8, 2))

        def _row(k, v):
            f = tk.Frame(self._body, bg=BG_PANEL)
            f.pack(fill="x", padx=10, pady=1)
            tk.Label(f, text=f"{k}:", bg=BG_PANEL, fg=ACCENT2,
                     font=("Segoe UI", 9), width=16, anchor="w").pack(side="left")
            tk.Label(f, text=str(v), bg=BG_PANEL, fg=FG_TEXT,
                     font=("Consolas", 9), anchor="w").pack(side="left")

        # ── Stats ─────────────────────────────────────────────────────────────
        _sect("STATS")
        dt = DAMAGE_TYPE_NAMES.get(s.get("damage_type", ""), s.get("damage_type", ""))
        _row("Damage type", dt or "—")

        # Animation row with linked .i3d file
        anim = s.get("animation", "")
        if anim:
            model_file = _spell_anim_model(anim)
            af = tk.Frame(self._body, bg=BG_PANEL)
            af.pack(fill="x", padx=10, pady=1)
            tk.Label(af, text="Animation:", bg=BG_PANEL, fg=ACCENT2,
                     font=("Segoe UI", 9), width=16, anchor="w").pack(side="left")
            tk.Label(af, text=anim, bg=BG_PANEL, fg=FG_TEXT,
                     font=("Consolas", 9), anchor="w").pack(side="left")
            if model_file and model_file.exists():
                def _open_model(p=model_file):
                    import subprocess, os
                    subprocess.Popen(["explorer", "/select,", str(p)])
                tk.Button(af, text=f"  {model_file.name}  ", bg=BG_CARD,
                          fg=ACCENT2, relief="flat", cursor="hand2",
                          font=("Segoe UI", 8), command=_open_model
                          ).pack(side="left", padx=6)
        else:
            _row("Animation", "—")

        if s.get("damage"):
            _row("Damage",  s["damage"])
        if s.get("duration"):
            _row("Duration", s["duration"])

        # ── Variants / Talisman combos ────────────────────────────────────────
        variants = s.get("variants", [])
        if variants:
            _sect(f"VARIANTS  ({len(variants)})")
            for v in variants:
                vf = tk.Frame(self._body, bg=BG_CARD,
                              highlightthickness=1, highlightbackground=BORDER)
                vf.pack(fill="x", padx=10, pady=3)

                # Variant name + mana
                hf = tk.Frame(vf, bg=BG_CARD)
                hf.pack(fill="x", padx=6, pady=(4, 2))
                tk.Label(hf, text=v["name"], bg=BG_CARD, fg=FG_TEXT,
                         font=("Segoe UI", 9, "bold")).pack(side="left")
                if v.get("mana"):
                    tk.Label(hf, text=f"  {v['mana']} mana",
                             bg=BG_CARD, fg=ACCENT2,
                             font=("Segoe UI", 8)).pack(side="left")
                if v.get("min_d") not in (None, "—") and v.get("max_d") not in (None, "—"):
                    tk.Label(hf, text=f"  dmg {v['min_d']}–{v['max_d']}",
                             bg=BG_CARD, fg=GOLD,
                             font=("Segoe UI", 8)).pack(side="left")

                # Talisman icon chain
                talis_str  = v.get("talismans", "")
                talis_names = v.get("talis_names", [])
                tf = tk.Frame(vf, bg=BG_CARD)
                tf.pack(fill="x", padx=6, pady=(0, 4))
                for letter, tname in zip(talis_str, talis_names):
                    ph = self._talis_ph.get(tname)
                    cell = tk.Frame(tf, bg=BG_CARD)
                    cell.pack(side="left", padx=3)
                    if ph:
                        lbl_i = tk.Label(cell, image=ph, bg=BG_CARD)
                        lbl_i.pack()
                        lbl_i._ph = ph
                        self._variant_talis_widgets.append(lbl_i)
                    tk.Label(cell, text=tname, bg=BG_CARD, fg=FG_DIM,
                             font=("Segoe UI", 7)).pack()

                if v.get("effect"):
                    ef = tk.Frame(vf, bg=BG_CARD)
                    ef.pack(fill="x", padx=6, pady=(0, 4))
                    tk.Label(ef, text="Effect:", bg=BG_CARD, fg=FG_MUTED,
                             font=("Segoe UI", 8)).pack(side="left")
                    tk.Label(ef, text=v["effect"], bg=BG_CARD, fg=ACCENT3,
                             font=("Consolas", 8)).pack(side="left", padx=4)

    # ── Batch export ──────────────────────────────────────────────────────────
    def _export_all(self):
        if not HAS_PIL:
            self._status.set("PIL not available")
            return
        if not self._spells:
            self._status.set("No spells loaded")
            return
        dest = RENDERS_DIR / "SpellIcons"
        dest.mkdir(parents=True, exist_ok=True)
        total = len(self._spells)
        self._export_stop = False
        self._export_btn.config(text="Stop", bg=RED,
                                command=lambda: setattr(self, '_export_stop', True))

        def _worker():
            ok = skip = 0
            for i, s in enumerate(self._spells, 1):
                if self._export_stop:
                    break
                icon_name = s.get("icon_name", s["name"])
                img = _load_spell_icon(icon_name, size=64)
                if img:
                    out = dest / f"{icon_name}.png"
                    try:
                        img.save(str(out)); ok += 1
                    except Exception:
                        skip += 1
                else:
                    skip += 1
                if i % 10 == 0 or i == total:
                    self.after(0, lambda n=i: self._status.set(
                        f"Exporting spell icons: {n}/{total}…"))
            self.after(0, self._on_export_done, ok, skip, dest)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_export_done(self, ok: int, skip: int, dest: Path):
        self._export_btn.config(text="Export All Icons", bg=ACCENT2,
                                command=self._export_all)
        self._status.set(f"Spell icons: {ok} saved, {skip} skipped → {dest}")


def _spell_anim_model(anim_name: str) -> Optional[Path]:
    """Return the most relevant .i3d model file for a spell animation name."""
    chars_dir = IMAGERY_ASSETS / "Chars"
    candidates = {
        "invoke1": "invoker.i3d", "invoke2": "invoker.i3d",
        "invoke3": "invoker.i3d", "invoke4": "invoker.i3d",
        "invoke5": "invoker.i3d", "cinv1":   "invoker.i3d",
        "Vomit":   "zombie.i3d",
    }
    fname = candidates.get(anim_name)
    if fname:
        p = chars_dir / fname
        if p.exists():
            return p
    # Generic fallback: search for model whose name contains the anim name
    anim_lower = anim_name.lower()
    for f in chars_dir.glob("*.i3d"):
        if anim_lower in f.stem.lower():
            return f
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  SCRIPTS TAB
# ═══════════════════════════════════════════════════════════════════════════════

class ScriptsTab(tk.Frame):
    def __init__(self, parent, status: StatusBar):
        super().__init__(parent, bg=BG_MID)
        self._status  = status
        self._def_files: List[Path] = []
        self._build_ui()
        self.after(500, self._load_all)

    def _build_ui(self):
        bar = tk.Frame(self, bg=BG_DARK, pady=4)
        bar.pack(fill="x")
        self._search_var = tk.StringVar()
        tk.Label(bar, text="Search in files:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 10)).pack(side="left", padx=(10,4))
        tk.Entry(bar, textvariable=self._search_var,
                  bg=BG_PANEL, fg=FG_TEXT, insertbackground=FG_TEXT,
                  font=("Segoe UI", 10), relief="flat", width=30
                  ).pack(side="left", padx=4)
        tk.Button(bar, text="Search", command=self._do_search,
                  bg=ACCENT2, fg="white", relief="flat",
                  font=("Segoe UI", 9, "bold"), padx=8
                  ).pack(side="left", padx=4)
        tk.Button(bar, text="Export All .def", command=self._export_all,
                  bg=ACCENT3, fg="#000", relief="flat",
                  font=("Segoe UI", 9, "bold"), padx=8
                  ).pack(side="left", padx=4)
        self._count_lbl = tk.Label(bar, text="", bg=BG_DARK, fg=FG_DIM,
                                    font=("Segoe UI", 9))
        self._count_lbl.pack(side="right", padx=12)

        pane = tk.PanedWindow(self, orient="horizontal", bg=BG_DARK,
                               sashwidth=6, sashrelief="flat")
        pane.pack(fill="both", expand=True)

        # File tree
        lf = tk.Frame(pane, bg=BG_MID)
        pane.add(lf, minsize=220)
        tk.Label(lf, text=".DEF FILES", bg=BG_MID, fg=ACCENT,
                 font=("Segoe UI", 9, "bold"), pady=4).pack(anchor="w", padx=8)
        self._file_lb = tk.Listbox(lf, bg=BG_PANEL, fg=FG_TEXT,
                                    font=("Consolas", 9), selectmode="single",
                                    relief="flat", activestyle="dotbox",
                                    selectbackground=BG_CARD,
                                    selectforeground=ACCENT)
        sb_f = ttk.Scrollbar(lf, orient="vertical", command=self._file_lb.yview)
        self._file_lb.configure(yscrollcommand=sb_f.set)
        sb_f.pack(side="right", fill="y")
        self._file_lb.pack(fill="both", expand=True, padx=(4,0), pady=4)
        self._file_lb.bind("<<ListboxSelect>>", self._on_file_select)

        # Content + search results
        right = tk.Frame(pane, bg=BG_PANEL)
        pane.add(right)

        # Search results
        self._results_frame = tk.Frame(right, bg=BG_DARK)
        self._results_tv = ttk.Treeview(self._results_frame,
                                         columns=("file","line","text"),
                                         show="headings", height=8)
        self._results_tv.heading("file", text="File", anchor="w")
        self._results_tv.heading("line", text="Line", anchor="center")
        self._results_tv.heading("text", text="Match", anchor="w")
        self._results_tv.column("file", width=140, stretch=False)
        self._results_tv.column("line", width=50,  stretch=False, anchor="center")
        self._results_tv.column("text", width=400, stretch=True)
        sb_r = ttk.Scrollbar(self._results_frame, orient="vertical",
                              command=self._results_tv.yview)
        self._results_tv.configure(yscrollcommand=sb_r.set)
        sb_r.pack(side="right", fill="y")
        self._results_tv.pack(fill="both", expand=True)
        self._results_tv.bind("<<TreeviewSelect>>", self._on_result_select)
        # Hidden by default

        # File content viewer
        self._content_frame = tk.Frame(right, bg=BG_PANEL)
        self._content_frame.pack(fill="both", expand=True)

        hdr = tk.Frame(self._content_frame, bg=BG_DARK, pady=2)
        hdr.pack(fill="x")
        self._file_lbl = tk.Label(hdr, text="Select a file", bg=BG_DARK,
                                   fg=ACCENT2, font=("Segoe UI", 9, "bold"))
        self._file_lbl.pack(side="left", padx=8)

        self._content_text = tk.Text(self._content_frame, bg=BG_PANEL,
                                      fg=FG_TEXT, font=("Consolas", 9),
                                      relief="flat", state="disabled",
                                      wrap="none")
        sb_h = ttk.Scrollbar(self._content_frame, orient="horizontal",
                              command=self._content_text.xview)
        sb_v = ttk.Scrollbar(self._content_frame, orient="vertical",
                              command=self._content_text.yview)
        self._content_text.configure(xscrollcommand=sb_h.set,
                                      yscrollcommand=sb_v.set)
        sb_h.pack(side="bottom", fill="x")
        sb_v.pack(side="right",  fill="y")
        self._content_text.pack(fill="both", expand=True)

        # Syntax colours
        self._content_text.tag_configure("comment", foreground=FG_MUTED)
        self._content_text.tag_configure("keyword", foreground=ACCENT,
                                          font=("Consolas", 9, "bold"))
        self._content_text.tag_configure("string",  foreground=ACCENT3)
        self._content_text.tag_configure("define",  foreground=GOLD)
        self._content_text.tag_configure("number",  foreground=ACCENT2)
        self._content_text.tag_configure("highlight",background=GOLD,
                                          foreground="#000000")

    def _load_all(self):
        defs = sorted(EXTRACT_DIR.rglob("*.def"))
        self._def_files = defs
        self._file_lb.delete(0, "end")
        for d in defs:
            rel = str(d.relative_to(EXTRACT_DIR))
            self._file_lb.insert("end", rel)
        self._count_lbl.config(text=f"{len(defs)} .def files")
        self._status.set(f"Scripts: {len(defs)} .def files indexed")

    def _on_file_select(self, _):
        sel = self._file_lb.curselection()
        if not sel:
            return
        path = self._def_files[sel[0]]
        self._file_lbl.config(text=str(path.relative_to(EXTRACT_DIR)))
        content = _read_def(path)
        self._render_content(content)

    def _render_content(self, content: str, highlight: str = ""):
        txt = self._content_text
        txt.configure(state="normal")
        txt.delete("1.0", "end")

        for lineno, line in enumerate(content.splitlines(), 1):
            start = txt.index("end")
            txt.insert("end", line + "\n")
            end = txt.index("end")

            # Syntax highlighting
            if line.strip().startswith("//"):
                txt.tag_add("comment", start, end)
            elif line.strip().startswith("#define"):
                txt.tag_add("define", start, end)
            elif re.search(r'\b(CHARACTER|WEAPON|ARMOR|SPELL|CLASS|BEGIN|END)\b', line):
                for m in re.finditer(r'\b(CHARACTER|WEAPON|ARMOR|SPELL|CLASS|BEGIN|END)\b', line):
                    s = f"{start}+{m.start()}c"
                    e = f"{start}+{m.end()}c"
                    txt.tag_add("keyword", s, e)
            # Strings
            for m in re.finditer(r'"[^"]*"', line):
                s = f"{start}+{m.start()}c"
                e = f"{start}+{m.end()}c"
                txt.tag_add("string", s, e)

        # Highlight search term
        if highlight:
            idx = "1.0"
            while True:
                idx = txt.search(highlight, idx, nocase=True, stopindex="end")
                if not idx:
                    break
                end = f"{idx}+{len(highlight)}c"
                txt.tag_add("highlight", idx, end)
                idx = end

        txt.configure(state="disabled")

    def _do_search(self):
        term = self._search_var.get().strip()
        if not term:
            self._results_frame.pack_forget()
            return

        matches = []
        for path in self._def_files:
            content = _read_def(path)
            for lineno, line in enumerate(content.splitlines(), 1):
                if term.lower() in line.lower():
                    matches.append((path, lineno, line.strip()))

        self._results_tv.delete(*self._results_tv.get_children())
        for path, lineno, text in matches[:500]:
            rel = str(path.relative_to(EXTRACT_DIR))
            self._results_tv.insert("", "end", values=(rel, lineno, text),
                                     tags=(str(path),))

        self._results_frame.pack(fill="x", padx=4, pady=4)
        self._count_lbl.config(text=f"{len(matches)} matches for '{term}'")
        self._status.set(f"Found {len(matches)} matches for '{term}' across {len(self._def_files)} files")

    def _on_result_select(self, _):
        sel = self._results_tv.selection()
        if not sel:
            return
        vals = self._results_tv.item(sel[0], "values")
        rel_path_str = vals[0]
        lineno       = int(vals[1])
        term         = self._search_var.get().strip()

        path = EXTRACT_DIR / rel_path_str
        if path.exists():
            # Find it in list
            for i, d in enumerate(self._def_files):
                if d == path:
                    self._file_lb.selection_clear(0, "end")
                    self._file_lb.selection_set(i)
                    self._file_lb.see(i)
                    break
            self._file_lbl.config(text=rel_path_str)
            content = _read_def(path)
            self._render_content(content, highlight=term)
            # Scroll to line
            self._content_text.configure(state="normal")
            self._content_text.see(f"{lineno}.0")
            self._content_text.configure(state="disabled")

    def _export_all(self):
        if not self._def_files:
            self._status.set("No .def files loaded")
            return
        dest = RENDERS_DIR / "Scripts"
        dest.mkdir(parents=True, exist_ok=True)
        ok = skip = 0
        for path in self._def_files:
            try:
                import shutil
                shutil.copy2(str(path), str(dest / path.name))
                ok += 1
            except Exception:
                skip += 1
        self._status.set(f"Scripts exported: {ok} files → {dest}")


# ═══════════════════════════════════════════════════════════════════════════════
#  3D WIREFRAME VIEWER WIDGET
# ═══════════════════════════════════════════════════════════════════════════════

class ModelViewer3D(tk.Frame):
    """
    Orthographic 3D viewer for i3d geometry.
    Supports flat-shaded and UV-textured rendering modes.
    Drag to rotate, scroll wheel to zoom.
    Falls back to a point cloud when no face data is available.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_DARK, **kwargs)
        self._verts            : List[tuple] = []
        self._faces            : List[tuple] = []
        self._normals          : List[tuple] = []
        self._uvs              : List[tuple] = []
        self._texture           = None   # first PIL.Image (kept for export compat)
        self._textures         : list  = []   # all PIL.Images, indexed by face_tex_indices
        self._face_tex_indices : List[int] = []
        self._photo_ref = None         # keep ImageTk.PhotoImage alive
        self._az     = 0.5
        self._el     = 0.1
        self._zoom   = 1.0
        self._drag   = None
        self._mode_var = tk.StringVar(value="textured")
        self._build()

    def _build(self):
        # ── Top toolbar ───────────────────────────────────────────────────────
        toolbar = tk.Frame(self, bg=BG_DARK)
        toolbar.pack(fill="x", side="top")

        tk.Label(toolbar, text="Render:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(side="left", padx=(6, 2))
        for label, val in [("Shaded", "shaded"), ("Textured", "textured")]:
            tk.Radiobutton(toolbar, text=label, variable=self._mode_var, value=val,
                           bg=BG_DARK, fg=FG_TEXT, selectcolor=BG_PANEL,
                           activebackground=BG_DARK, font=("Segoe UI", 8),
                           command=self._redraw).pack(side="left", padx=2)

        self._canvas = tk.Canvas(self, bg="#07070f", highlightthickness=0,
                                 cursor="fleur")
        self._canvas.pack(fill="both", expand=True)
        self._info_lbl = tk.Label(self, text="Select a model to view",
                                  bg=BG_DARK, fg=FG_MUTED,
                                  font=("Segoe UI", 8))
        self._info_lbl.pack(pady=(2, 4))

        self._canvas.bind("<ButtonPress-1>",  self._drag_start)
        self._canvas.bind("<B1-Motion>",       self._drag_move)
        self._canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, '_drag', None))
        self._canvas.bind("<MouseWheel>",      self._on_wheel)
        self._canvas.bind("<Configure>",       lambda e: self._redraw())

    def load(self, verts: list, faces: list, info: str = "",
             normals: list = None, uvs: list = None, texture=None,
             textures: list = None, face_tex_indices: list = None):
        self._verts   = verts
        self._faces   = faces
        self._normals = normals or []
        self._uvs     = uvs or []
        if textures is not None:
            self._textures = textures
            self._texture  = textures[0] if textures else None
        elif texture is not None:
            self._texture  = texture
            self._textures = [texture]
        self._face_tex_indices = face_tex_indices or []
        self._photo_ref = None
        self._az     = 0.5
        self._el     = 0.1
        self._zoom   = 1.0
        self._info_lbl.config(text=info or ("No geometry" if not verts else ""))
        self._redraw()

    def reload(self, verts: list, faces: list, info: str = "",
               normals: list = None, uvs: list = None):
        """Like load() but preserves current rotation/zoom and texture."""
        self._verts   = verts
        self._faces   = faces
        self._normals = normals or []
        self._uvs     = uvs or []
        self._photo_ref = None
        self._info_lbl.config(text=info or ("No geometry" if not verts else ""))
        self._redraw()

    @staticmethod
    def load_textures_for(i3d_path) -> list:
        """
        Load all textures for an .i3d file.
        Priority:
          1. Sidecar file (.bmp/.png/.tga) — returned as a single-element list
          2. All embedded DirectDraw textures from the .i3d itself
        Returns a list of PIL RGBA Images (may be empty).
        """
        try:
            from PIL import Image as _Image
            p = Path(i3d_path)
            for ext in (".bmp", ".BMP", ".png", ".PNG", ".tga", ".TGA"):
                candidate = p.with_suffix(ext)
                if candidate.exists():
                    return [_Image.open(candidate).convert("RGBA")]
        except Exception:
            pass
        try:
            from decoders.i3d import decode_i3d_textures
            return decode_i3d_textures(Path(i3d_path))
        except Exception:
            pass
        return []

    @staticmethod
    def load_texture_for(i3d_path) -> "Optional[object]":
        """Single-texture backward-compat wrapper around load_textures_for."""
        textures = ModelViewer3D.load_textures_for(i3d_path)
        return textures[0] if textures else None

    def _drag_start(self, e):
        self._drag = (e.x, e.y, self._az, self._el)

    def _drag_move(self, e):
        if not self._drag:
            return
        x0, y0, az0, el0 = self._drag
        self._az = az0 + (e.x - x0) * 0.008
        self._el = max(-1.5, min(1.5, el0 - (e.y - y0) * 0.008))
        self._redraw()

    def _on_wheel(self, e):
        self._zoom = max(0.05, min(20.0, self._zoom * (1.1 if e.delta > 0 else 0.9)))
        self._redraw()

    def _redraw(self):
        mode = self._mode_var.get()
        if mode == "textured" and self._textures and self._uvs:
            self._redraw_textured()
        else:
            self._redraw_shaded()

    def _redraw_shaded(self):
        c  = self._canvas
        cw = c.winfo_width()  or 300
        ch = c.winfo_height() or 240
        c.delete("all")

        if not self._verts:
            c.create_text(cw // 2, ch // 2, text="No geometry decoded",
                          fill=FG_MUTED, font=("Segoe UI", 10))
            return

        # ── Centre mesh on bounding-box centroid ───────────────────────────
        xs_r = [v[0] for v in self._verts]
        ys_r = [v[1] for v in self._verts]
        zs_r = [v[2] for v in self._verts]
        cx_r = (max(xs_r) + min(xs_r)) / 2
        cy_r = (max(ys_r) + min(ys_r)) / 2
        cz_r = (max(zs_r) + min(zs_r)) / 2

        # After bind-pose bone transforms, Z is world-up (feet≈z0, head≈z60).
        # Map Z→up (Y screen), X→horizontal, Y→depth so character stands upright.
        verts_c = [(x - cx_r, z - cz_r, y - cy_r) for x, y, z in self._verts]

        # ── Stable scale (rotation-invariant, from raw extents) ────────────
        mesh_span = max(max(xs_r)-min(xs_r), max(ys_r)-min(ys_r),
                        max(zs_r)-min(zs_r), 1e-6)
        scale = self._zoom * min(cw, ch) * 0.42 / mesh_span

        # ── Rotate ─────────────────────────────────────────────────────────
        az, el = self._az, self._el
        caz, saz = math.cos(az), math.sin(az)
        cel, sel = math.cos(el), math.sin(el)

        rot = []
        for x, y, z in verts_c:
            rx =  x * caz + z * saz
            ry =  y
            rz = -x * saz + z * caz
            rot.append((rx, ry * cel - rz * sel, ry * sel + rz * cel))

        # ── Rotate stored vertex normals (same transform, Z-up swap) ───────
        has_normals = len(self._normals) == len(self._verts)
        rot_nrm = []
        if has_normals:
            for nx, ny, nz in self._normals:
                # Match vertex swap: world (nx,ny,nz) → display (nx, nz, ny)
                nx2, ny2, nz2 = nx, nz, ny
                rnx =  nx2 * caz + nz2 * saz
                rny =  ny2
                rnz = -nx2 * saz + nz2 * caz
                rot_nrm.append((rnx, rny * cel - rnz * sel, rny * sel + rnz * cel))

        # ── Screen projection ──────────────────────────────────────────────
        cx2 = cw // 2;  cy2 = ch // 2
        pts = [(cx2 + v[0] * scale, cy2 - v[1] * scale, v[2]) for v in rot]

        # ── Light ──────────────────────────────────────────────────────────
        lx, ly, lz = 0.57, 0.74, 0.37   # pre-normalised

        # ── Build face list ────────────────────────────────────────────────
        if self._faces:
            face_data = []
            for face in self._faces:
                a, b, fi = face
                if a >= len(pts) or b >= len(pts) or fi >= len(pts):
                    continue
                ax, ay, az_ = pts[a]
                bx, by, bz_ = pts[b]
                fx, fy, fz_ = pts[fi]

                # Normal: use stored vertex normals (average of 3) when available
                # — these are always correct regardless of face winding order.
                # Fall back to computed face normal only if no normals stored.
                if has_normals:
                    na = rot_nrm[a]; nb = rot_nrm[b]; nc = rot_nrm[fi]
                    fnx = (na[0]+nb[0]+nc[0]) / 3
                    fny = (na[1]+nb[1]+nc[1]) / 3
                    fnz = (na[2]+nb[2]+nc[2]) / 3
                    nlen = math.sqrt(fnx*fnx + fny*fny + fnz*fnz) or 1.0
                    fnx /= nlen; fny /= nlen; fnz /= nlen
                else:
                    ra = rot[a]; rb = rot[b]; rc = rot[fi]
                    e1 = (rb[0]-ra[0], rb[1]-ra[1], rb[2]-ra[2])
                    e2 = (rc[0]-ra[0], rc[1]-ra[1], rc[2]-ra[2])
                    fnx = e1[1]*e2[2] - e1[2]*e2[1]
                    fny = e1[2]*e2[0] - e1[0]*e2[2]
                    fnz = e1[0]*e2[1] - e1[1]*e2[0]
                    nlen = math.sqrt(fnx*fnx + fny*fny + fnz*fnz) or 1.0
                    fnx /= nlen; fny /= nlen; fnz /= nlen

                # fnz > 0 means normal faces toward viewer = front face
                front = fnz > 0.0

                # Lighting: use abs dot so back faces still shade (not solid black)
                diff = abs(fnx*lx + fny*ly + fnz*lz)
                if front:
                    light = 0.22 + 0.73 * diff
                else:
                    light = 0.05 + 0.18 * diff   # back faces much darker

                r_c = int(min(255, 40  + light * 145))
                g_c = int(min(255, 75  + light * 135))
                b_c = int(min(255, 130 + light * 105))

                depth = (az_ + bz_ + fz_) / 3
                face_data.append((front, depth, ax, ay, bx, by, fx, fy,
                                   f"#{r_c:02x}{g_c:02x}{b_c:02x}"))

            # Two-pass draw: back faces first (no outline), front faces on top
            # This guarantees front faces are never buried by back faces,
            # fixing the "crystal / inside-out" artefact caused by mixed winding.
            back  = sorted((f for f in face_data if not f[0]), key=lambda f:  f[1])
            front = sorted((f for f in face_data if     f[0]), key=lambda f:  f[1])

            for _, _d, ax, ay, bx, by, fx, fy, fill in back:
                c.create_polygon(ax, ay, bx, by, fx, fy,
                                 fill=fill, outline="", width=0)
            for _, _d, ax, ay, bx, by, fx, fy, fill in front:
                c.create_polygon(ax, ay, bx, by, fx, fy,
                                 fill=fill, outline="#1a2a3a", width=1)
        else:
            r = max(1, int(scale * 0.05))
            for px, py, _ in pts:
                c.create_oval(px-r, py-r, px+r, py+r, fill="#5080d0", outline="")

        c.create_text(6, 6, text="Drag to rotate  ·  Scroll to zoom",
                      anchor="nw", fill=FG_MUTED, font=("Segoe UI", 8))

    # ─── Textured render (PIL affine-UV software rasterizer) ─────────────────

    def _redraw_textured(self):
        """
        Render with proper per-triangle affine UV mapping using PIL.Image.transform.
        Each triangle gets its own texture patch via the inverse-affine mapping,
        then is composited onto the framebuffer with a triangular alpha mask.
        """
        c  = self._canvas
        cw = c.winfo_width()  or 300
        ch = c.winfo_height() or 240

        try:
            from PIL import Image as PILImage, ImageDraw as PILDraw, ImageEnhance
        except ImportError:
            self._redraw_shaded()
            return

        if not self._verts or not self._faces or not self._textures or not self._uvs:
            self._redraw_shaded()
            return

        # Pre-tile each texture 3×3 so UV coordinates in [-1, 2] map cleanly.
        # Many playable characters use tiling UVs (e.g. u=-1 to 1.25) for
        # repeating armour/cloth patterns.  Hard clamping destroys those.
        # With 3 tiles: _uvt(x) = (x + 1) / 3 maps [-1, 2] → [0, 1] inside
        # the tiled texture, which covers the full observed UV range.
        NTILES = 3
        textures_tiled = []
        for t in self._textures:
            t_rgb = t.convert("RGB")
            tw_b, th_b = t_rgb.size
            tiled = PILImage.new("RGB", (tw_b * NTILES, th_b * NTILES))
            for ty in range(NTILES):
                for tx in range(NTILES):
                    tiled.paste(t_rgb, (tx * tw_b, ty * th_b))
            textures_tiled.append(tiled)

        uvs = self._uvs
        face_tex = self._face_tex_indices

        # ── Same Z-up rotation pipeline as shaded ─────────────────────────────
        xs_r = [v[0] for v in self._verts]
        ys_r = [v[1] for v in self._verts]
        zs_r = [v[2] for v in self._verts]
        cx_r = (max(xs_r) + min(xs_r)) / 2
        cy_r = (max(ys_r) + min(ys_r)) / 2
        cz_r = (max(zs_r) + min(zs_r)) / 2
        mesh_span = max(max(xs_r)-min(xs_r), max(ys_r)-min(ys_r),
                        max(zs_r)-min(zs_r), 1e-6)
        scale = self._zoom * min(cw, ch) * 0.42 / mesh_span

        az, el = self._az, self._el
        caz, saz = math.cos(az), math.sin(az)
        cel, sel = math.cos(el), math.sin(el)

        rot = []
        for x, y, z in self._verts:
            x2, y2, z2 = x - cx_r, z - cz_r, y - cy_r   # Z-up mapping
            rx =  x2 * caz + z2 * saz
            ry =  y2
            rz = -x2 * saz + z2 * caz
            rot.append((rx, ry * cel - rz * sel, ry * sel + rz * cel))

        has_normals = len(self._normals) == len(self._verts)
        rot_nrm = []
        if has_normals:
            for nx, ny, nz in self._normals:
                nx2, ny2, nz2 = nx, nz, ny
                rnx =  nx2 * caz + nz2 * saz
                rny =  ny2
                rnz = -nx2 * saz + nz2 * caz
                rot_nrm.append((rnx, rny * cel - rnz * sel, rny * sel + rnz * cel))

        cx2 = cw // 2;  cy2 = ch // 2
        pts = [(cx2 + v[0] * scale, cy2 - v[1] * scale, v[2]) for v in rot]

        lx, ly, lz = 0.57, 0.74, 0.37

        # ── Collect and depth-sort visible (front-facing) faces ───────────────
        # _uvt maps raw UV x (range [-1, 2]) to [0, 1] inside the 3×3 tiled
        # texture.  Clamp with tiny margin to handle IEEE rounding at borders.
        def _uvt(x): return max(0.0, min(1.0, (x + 1.0) / NTILES))

        face_list = []
        for face_idx, (a, b, fi) in enumerate(self._faces):
            if a >= len(pts) or b >= len(pts) or fi >= len(pts):
                continue
            ax, ay, az_ = pts[a];  bx, by, bz_ = pts[b];  fx, fy, fz_ = pts[fi]

            if has_normals and a < len(rot_nrm):
                na = rot_nrm[a]; nb = rot_nrm[b]; nc = rot_nrm[fi]
                fnx = (na[0]+nb[0]+nc[0])/3; fny = (na[1]+nb[1]+nc[1])/3; fnz = (na[2]+nb[2]+nc[2])/3
            else:
                ra = rot[a]; rb = rot[b]; rc = rot[fi]
                e1 = (rb[0]-ra[0], rb[1]-ra[1], rb[2]-ra[2])
                e2 = (rc[0]-ra[0], rc[1]-ra[1], rc[2]-ra[2])
                fnx = e1[1]*e2[2]-e1[2]*e2[1]; fny = e1[2]*e2[0]-e1[0]*e2[2]; fnz = e1[0]*e2[1]-e1[1]*e2[0]

            nlen = math.sqrt(fnx*fnx+fny*fny+fnz*fnz) or 1.0
            fnx /= nlen; fny /= nlen; fnz /= nlen

            if fnz <= 0.0:   # backface cull
                continue

            diff  = fnx*lx + fny*ly + fnz*lz
            light = 0.25 + 0.75 * max(0.0, diff)
            depth = (az_ + bz_ + fz_) / 3

            ua = _uvt(uvs[a][0])  if a  < len(uvs) else 1/3.; va = _uvt(uvs[a][1])  if a  < len(uvs) else 1/3.
            ub = _uvt(uvs[b][0])  if b  < len(uvs) else 1/3.; vb = _uvt(uvs[b][1])  if b  < len(uvs) else 1/3.
            uf = _uvt(uvs[fi][0]) if fi < len(uvs) else 1/3.; vf = _uvt(uvs[fi][1]) if fi < len(uvs) else 1/3.

            t_idx = face_tex[face_idx] if face_idx < len(face_tex) else 0
            face_list.append((depth, ax, ay, bx, by, fx, fy,
                               ua, va, ub, vb, uf, vf, light, t_idx))

        face_list.sort(key=lambda f: f[0])   # back→front (depth only, all front-facing)

        # ── Rasterize to PIL image with per-triangle affine UV mapping ────────
        img = PILImage.new("RGB", (cw, ch), "#07070f")

        for (depth, ax, ay, bx, by, fx, fy,
             ua, va, ub, vb, uf, vf, light, t_idx) in face_list:

            # Select tiled texture for this face group
            if t_idx < 0 or t_idx >= len(textures_tiled):
                continue   # no-texture group — skip
            tex = textures_tiled[t_idx]
            tw, th = tex.size

            # Bounding box (clamped to canvas)
            xlo = max(0, int(min(ax, bx, fx)))
            xhi = min(cw, int(max(ax, bx, fx)) + 2)
            ylo = max(0, int(min(ay, by, fy)))
            yhi = min(ch, int(max(ay, by, fy)) + 2)
            bbw = xhi - xlo;  bbh = yhi - ylo
            if bbw <= 0 or bbh <= 0:
                continue

            # Inverse affine: dest (x_bb, y_bb) → source (tu, tv)
            det = ax*(by - fy) + bx*(fy - ay) + fx*(ay - by)
            if abs(det) < 0.5:
                continue

            A = (ua*(by-fy) + ub*(fy-ay) + uf*(ay-by)) * tw / det
            B = (ua*(fx-bx) + ub*(ax-fx) + uf*(bx-ax)) * tw / det
            C = (ua*(bx*fy-fx*by) + ub*(fx*ay-ax*fy) + uf*(ax*by-bx*ay)) * tw / det
            D = (va*(by-fy) + vb*(fy-ay) + vf*(ay-by)) * th / det
            E = (va*(fx-bx) + vb*(ax-fx) + vf*(bx-ax)) * th / det
            F = (va*(bx*fy-fx*by) + vb*(fx*ay-ax*fy) + vf*(ax*by-bx*ay)) * th / det

            C2 = A * xlo + B * ylo + C
            F2 = D * xlo + E * ylo + F

            try:
                patch = tex.transform((bbw, bbh), PILImage.AFFINE,
                                      data=(A, B, C2, D, E, F2),
                                      resample=PILImage.BILINEAR)
            except Exception:
                continue

            if light != 1.0:
                patch = ImageEnhance.Brightness(patch).enhance(light)

            mask = PILImage.new("L", (bbw, bbh), 0)
            PILDraw.Draw(mask).polygon(
                [(ax-xlo, ay-ylo), (bx-xlo, by-ylo), (fx-xlo, fy-ylo)], fill=255)

            img.paste(patch, (xlo, ylo), mask)

        PILDraw.Draw(img).text((6, 6),
            "Drag to rotate  ·  Scroll to zoom  ·  [Textured]",
            fill=(80, 100, 130))

        # ── Display ───────────────────────────────────────────────────────────
        from PIL import ImageTk
        photo = ImageTk.PhotoImage(img)
        self._photo_ref = photo
        c.delete("all")
        c.create_image(0, 0, anchor="nw", image=photo)


# ═══════════════════════════════════════════════════════════════════════════════
#  3D MODELS TAB
# ═══════════════════════════════════════════════════════════════════════════════

class ModelsTab(tk.Frame):
    def __init__(self, parent, status: StatusBar):
        super().__init__(parent, bg=BG_MID)
        self._status = status
        self._models  : List[Dict] = []
        self._build_ui()
        self.after(600, self._load_all)

    def _build_ui(self):
        bar = tk.Frame(self, bg=BG_DARK, pady=4)
        bar.pack(fill="x")
        self._flt_var = tk.StringVar()
        tk.Label(bar, text="Filter:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 10)).pack(side="left", padx=(10,4))
        tk.Entry(bar, textvariable=self._flt_var,
                  bg=BG_PANEL, fg=FG_TEXT, insertbackground=FG_TEXT,
                  font=("Segoe UI", 10), relief="flat", width=24
                  ).pack(side="left", padx=4)
        self._flt_var.trace_add("write", self._filter)
        self._batch_btn = tk.Button(bar, text="Batch Export OBJ", bg=ACCENT3,
                                     fg="#000", relief="flat",
                                     font=("Segoe UI", 9, "bold"), padx=8,
                                     command=self._batch_export_obj)
        self._batch_btn.pack(side="right", padx=4)
        self._count_lbl = tk.Label(bar, text="", bg=BG_DARK, fg=FG_DIM,
                                    font=("Segoe UI", 9))
        self._count_lbl.pack(side="right", padx=12)

        pane = tk.PanedWindow(self, orient="horizontal", bg=BG_DARK,
                               sashwidth=6, sashrelief="flat")
        pane.pack(fill="both", expand=True)

        tv_f = tk.Frame(pane, bg=BG_MID)
        pane.add(tv_f, minsize=460)

        cols = ("name","folder","size","anims","verts")
        self._tv = ttk.Treeview(tv_f, columns=cols, show="headings",
                                  selectmode="browse")
        self._tv.heading("name",   text="Model File",   anchor="w")
        self._tv.heading("folder", text="Folder",       anchor="w")
        self._tv.heading("size",   text="Size (KB)",    anchor="center")
        self._tv.heading("anims",  text="Anim States",  anchor="center")
        self._tv.heading("verts",  text="Est. Verts",   anchor="center")
        self._tv.column("name",   width=200, stretch=True)
        self._tv.column("folder", width=100, stretch=False)
        self._tv.column("size",   width=70,  stretch=False, anchor="center")
        self._tv.column("anims",  width=80,  stretch=False, anchor="center")
        self._tv.column("verts",  width=80,  stretch=False, anchor="center")
        sb = ttk.Scrollbar(tv_f, orient="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._tv.pack(fill="both", expand=True)
        self._tv.bind("<<TreeviewSelect>>", self._on_select)

        # Detail panel (right): metadata top + 3D viewer bottom + OBJ export
        det = tk.Frame(pane, bg=BG_PANEL)
        pane.add(det, minsize=300)

        # Header row
        hdr = tk.Frame(det, bg=BG_PANEL, padx=10, pady=6)
        hdr.pack(fill="x")
        tk.Label(hdr, text="MODEL DETAILS", bg=BG_PANEL, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Button(hdr, text="Export glTF", bg=ACCENT2, fg="#000000",
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=8,
                  command=self._export_gltf).pack(side="right", padx=(0, 4))
        tk.Button(hdr, text="Export OBJ", bg=ACCENT3, fg="#000000",
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=8,
                  command=self._export_obj).pack(side="right")

        ttk.Separator(det).pack(fill="x")

        # ── Animation controls bar ────────────────────────────────────────
        anim_bar = tk.Frame(det, bg=BG_DARK, padx=8, pady=4)
        anim_bar.pack(fill="x")

        tk.Label(anim_bar, text="State:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 9)).pack(side="left")

        self._state_var = tk.StringVar(value="[0] Bind pose")
        self._state_cb  = ttk.Combobox(anim_bar, textvariable=self._state_var,
                                        state="readonly", width=22,
                                        font=("Segoe UI", 9))
        self._state_cb.pack(side="left", padx=(4, 8))
        self._state_cb.bind("<<ComboboxSelected>>", self._on_state_select)

        # Frame scrubber (shown only for multi-frame states)
        self._frame_var = tk.IntVar(value=0)
        self._frame_lbl = tk.Label(anim_bar, text="Frame:", bg=BG_DARK, fg=FG_DIM,
                                    font=("Segoe UI", 9))
        self._frame_scale = tk.Scale(anim_bar, variable=self._frame_var,
                                      from_=0, to=0, orient="horizontal",
                                      bg=BG_DARK, fg=FG_TEXT, highlightthickness=0,
                                      troughcolor=BG_PANEL, activebackground=ACCENT,
                                      length=80, showvalue=True,
                                      command=self._on_frame_change)

        # Play / Stop buttons
        self._play_btn = tk.Button(anim_bar, text="▶ Play", bg=BG_MID, fg=FG_TEXT,
                                    relief="flat", font=("Segoe UI", 9), padx=6,
                                    command=self._anim_play)
        self._stop_btn = tk.Button(anim_bar, text="■ Stop", bg=BG_MID, fg=FG_TEXT,
                                    relief="flat", font=("Segoe UI", 9), padx=6,
                                    command=self._anim_stop)
        self._play_btn.pack(side="left", padx=(0, 2))
        self._stop_btn.pack(side="left", padx=(0, 8))

        self._fps_var = tk.IntVar(value=8)
        tk.Label(anim_bar, text="FPS:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Spinbox(anim_bar, textvariable=self._fps_var, from_=1, to=30,
                   width=3, bg=BG_PANEL, fg=FG_TEXT, relief="flat",
                   font=("Segoe UI", 9)).pack(side="left", padx=(2, 0))

        self._anim_job  = None   # after() job id
        self._anim_frame = 0     # current playback frame

        ttk.Separator(det).pack(fill="x")

        # Vertical split: metadata text (top) + 3D viewer (bottom)
        vpane = tk.PanedWindow(det, orient="vertical", bg=BG_DARK,
                               sashwidth=5, sashrelief="flat")
        vpane.pack(fill="both", expand=True)

        meta_frame = tk.Frame(vpane, bg=BG_PANEL, padx=8, pady=4)
        vpane.add(meta_frame, minsize=100)
        self._det_text = tk.Text(meta_frame, bg=BG_PANEL, fg=FG_TEXT,
                                  font=("Consolas", 9), relief="flat",
                                  state="disabled", wrap="word", height=7)
        self._det_text.pack(fill="both", expand=True)
        self._det_text.tag_configure("h",   foreground=ACCENT,  font=("Segoe UI", 10, "bold"))
        self._det_text.tag_configure("kv",  foreground=ACCENT2, font=("Segoe UI", 9))
        self._det_text.tag_configure("list",foreground=ACCENT3, font=("Consolas", 8))

        self._viewer = ModelViewer3D(vpane)
        vpane.add(self._viewer, minsize=200)

        self._current_geom    = None   # holds last decoded I3DGeometry
        self._current_texture = None   # holds last loaded PIL texture (for export)
        self._current_path    = None   # path of currently selected model

    def _load_all(self):
        self._status.set("Scanning i3d model files...")
        models = []
        seen   = set()
        for f in IMAGERY_ASSETS.rglob("*.i3d"):
            key = f.name.lower()
            if key in seen:
                continue
            seen.add(key)
            anim_count = parse_i3d_anim_count(f)
            # Quick vertex count: Layout A = sec[1].count, Layout B = sec[1].rel
            verts = 0
            try:
                raw = f.read_bytes()
                if len(raw) >= 28 and raw[:4] == b'CGSR':
                    hdrsize    = struct.unpack_from('<I', raw, 16)[0]
                    geom_start = 20 + hdrsize
                    if geom_start + 24 <= len(raw):
                        sec1_rel = struct.unpack_from('<I', raw, geom_start + 8)[0]     # Layout B vc
                        sec1_cnt = struct.unpack_from('<I', raw, geom_start + 8 + 4)[0] # Layout A vc
                        sec2_cnt = struct.unpack_from('<I', raw, geom_start + 16 + 4)[0]
                        verts = sec1_cnt if sec2_cnt > 0 else sec1_rel
            except Exception:
                pass
            models.append({
                "name":   f.name,
                "folder": f.parent.name,
                "path":   f,
                "size_kb": f.stat().st_size // 1024,
                "anims":  anim_count,
                "verts":  verts,
            })

        self._models = sorted(models, key=lambda x: x["anims"], reverse=True)
        self._populate(self._models)
        self._count_lbl.config(text=f"{len(self._models)} models")
        self._status.set(f"3D Models: {len(self._models)} i3d files indexed")

    def _populate(self, data: List[Dict]):
        self._tv.delete(*self._tv.get_children())
        for m in data:
            self._tv.insert("", "end",
                values=(m["name"], m["folder"],
                        m["size_kb"], m["anims"],
                        m["verts"] if m["verts"] else "?"))

    def _filter(self, *_):
        flt = self._flt_var.get().strip().lower()
        filtered = [m for m in self._models
                    if flt in m["name"].lower() or flt in m["folder"].lower()
                    ] if flt else self._models
        self._populate(filtered)
        self._count_lbl.config(text=f"{len(filtered)} / {len(self._models)}")

    def _on_select(self, _):
        sel = self._tv.selection()
        if not sel:
            return
        name = self._tv.item(sel[0], "values")[0]
        m = next((x for x in self._models if x["name"] == name), None)
        if not m:
            return

        self._anim_stop()
        self._current_path = m["path"]

        # Load animation state list via fast decoder
        from decoders.i3d import list_anim_states
        anim_states = list_anim_states(m["path"])

        # Populate state combobox
        state_entries = ["[0] Bind pose (T-pose)"]
        for s in anim_states:
            tag = "cycle" if s.anim_type == 0 else "pose"
            nf  = f" ×{s.nframes}f" if s.anim_type == 0 and s.nframes > 0 else ""
            state_entries.append(f"[{s.index + 1}] {s.name}  ({tag}{nf})")
        self._state_cb["values"] = state_entries
        self._state_cb.current(0)
        self._frame_var.set(0)
        self._frame_scale.config(to=0)
        self._frame_lbl.pack_forget()
        self._frame_scale.pack_forget()

        # Fill metadata panel
        txt = self._det_text
        txt.configure(state="normal")
        txt.delete("1.0", "end")
        txt.insert("end", f"{m['name']}\n", "h")

        def row(k, v):
            txt.insert("end", f"  {k:<20}", "kv")
            txt.insert("end", f"{v}\n")

        row("Folder",      m["folder"])
        row("File size",   f"{m['size_kb']:,} KB  ({m['path'].stat().st_size:,} bytes)")
        row("Anim states", str(len(anim_states)) if anim_states else "0")

        if anim_states:
            txt.insert("end", f"\nAnimation States ({len(anim_states)}):\n", "kv")
            for s in anim_states:
                tag = "cycle" if s.anim_type == 0 else "pose"
                nf  = f" ×{s.nframes}f" if s.anim_type == 0 and s.nframes > 0 else ""
                txt.insert("end", f"  [{s.index:>2}] {s.name}  ({tag}{nf})\n", "list")

        txt.configure(state="disabled")

        # Async geometry decode → 3D viewer
        self._decode_model(m["path"])

    def _on_state_select(self, _=None):
        """User selected a new animation state from the combobox."""
        if self._current_geom is None:
            return
        self._anim_stop()
        idx = self._state_cb.current()   # 0 = bind pose, 1..N = state 0..N-1
        self._apply_state(idx)

    def _apply_state(self, combo_idx: int, frame: int = 0):
        """Apply combo_idx (0=bind-pose, 1..N = anim state 0..N-1) at given frame."""
        geom = self._current_geom
        if geom is None:
            return
        from decoders.i3d import load_state
        if combo_idx == 0:
            ok = load_state(geom, 0, 0)   # bind pose
        else:
            state_idx = combo_idx - 1     # index into anim_states list
            ok = load_state(geom, state_idx, frame)

        if ok:
            # Update frame scrubber visibility
            if combo_idx > 0:
                st = geom.anim_states[combo_idx - 1]
                max_f = max(0, (st.nframes or 1) - 1)
            else:
                max_f = 0

            if max_f > 0:
                self._frame_lbl.pack(side="left", padx=(8, 2))
                self._frame_scale.config(to=max_f)
                self._frame_scale.pack(side="left")
            else:
                self._frame_lbl.pack_forget()
                self._frame_scale.pack_forget()

            has_uvs = len(geom.uvs) == len(geom.vertices)
            has_nrm = len(geom.normals) == len(geom.vertices)
            extras  = (["+normals"] if has_nrm else []) + (["+UVs"] if has_uvs else [])
            state_label = "bind" if combo_idx == 0 else geom.anim_states[combo_idx - 1].name
            info = (f"{len(geom.vertices):,} verts  ·  {len(geom.faces):,} faces"
                    f"  ·  state: {state_label}"
                    + (f"  ·  frame {frame}" if max_f > 0 else "")
                    + ("  ·  " + " ".join(extras) if extras else ""))
            # Preserve textures and face_tex_indices across state changes
            stored_tex = self._viewer._textures if self._viewer._textures else None
            stored_fti = (geom.face_tex_indices
                          if geom.face_tex_indices else None)
            self._viewer.load(geom.vertices, geom.faces, info,
                              normals=geom.normals if has_nrm else None,
                              uvs=geom.uvs if has_uvs else None,
                              textures=stored_tex,
                              face_tex_indices=stored_fti)

    def _on_frame_change(self, val=None):
        """Frame scrubber moved."""
        self._anim_stop()
        frame = self._frame_var.get()
        combo_idx = self._state_cb.current()
        self._apply_state(combo_idx, frame)

    def _anim_play(self):
        """Start animation playback for multi-frame states."""
        if self._current_geom is None:
            return
        combo_idx = self._state_cb.current()
        if combo_idx == 0:
            return
        geom = self._current_geom
        st = geom.anim_states[combo_idx - 1]
        nf = max(1, st.nframes or 1)
        if nf <= 1:
            return
        self._anim_stop()
        self._anim_frame = self._frame_var.get()
        self._play_btn.config(relief="sunken")
        self._anim_tick(combo_idx, nf)

    def _anim_tick(self, combo_idx: int, nf: int):
        fps = max(1, self._fps_var.get())
        self._apply_state(combo_idx, self._anim_frame)
        self._frame_var.set(self._anim_frame)
        self._anim_frame = (self._anim_frame + 1) % nf
        self._anim_job = self.after(int(1000 / fps), self._anim_tick, combo_idx, nf)

    def _anim_stop(self):
        if self._anim_job is not None:
            self.after_cancel(self._anim_job)
            self._anim_job = None
        self._play_btn.config(relief="flat")



    def _decode_model(self, path: Path):
        """Decode geometry + texture for the given .i3d file and update viewer."""
        self._current_geom    = None
        self._current_texture = None
        self._viewer.load([], [], "Decoding…")

        def _worker(p=path):
            log.info("Loading model: %s", p.name)
            try:
                from decoders.i3d import decode_i3d_geometry
                geom = decode_i3d_geometry(p)
            except Exception as exc:
                log.error("Geometry decode failed for %s: %s", p.name, exc)
                geom = None

            # Load all embedded textures (or sidecar)
            textures = ModelViewer3D.load_textures_for(p)
            tex = textures[0] if textures else None

            self._current_geom    = geom
            self._current_texture = tex
            if geom:
                log.info("  %s: %d verts, %d faces, %d states, %d tex, rig=%s",
                         p.name, len(geom.vertices), len(geom.faces),
                         len(geom.anim_states), len(textures),
                         f"{geom.rig.num_bones} bones" if geom.rig else "none")
                has_uvs = len(geom.uvs) == len(geom.vertices)
                has_nrm = len(geom.normals) == len(geom.vertices)
                ntex = len(textures)
                tex_tag = f"  ·  +{ntex} tex" if ntex else ""
                extras  = (["+normals"] if has_nrm else []) + (["+UVs"] if has_uvs else [])
                extras_str = ("  ·  " + " ".join(extras)) if extras else ""
                n_states = len(geom.anim_states)
                info = (f"{len(geom.vertices):,} verts  ·  "
                        f"{len(geom.faces):,} faces  ·  "
                        f"{n_states} anim states{extras_str}{tex_tag}")
            else:
                info = "Geometry format not detected"

            def _update():
                self._viewer.load(
                    geom.vertices if geom else [],
                    geom.faces    if geom else [],
                    info,
                    normals          = geom.normals          if (geom and len(geom.normals)==len(geom.vertices)) else None,
                    uvs              = geom.uvs              if (geom and len(geom.uvs)    ==len(geom.vertices)) else None,
                    textures         = textures              if textures else None,
                    face_tex_indices = geom.face_tex_indices if geom else None,
                )
                if self._state_cb.current() != 0:
                    self._state_cb.current(0)
            self.after(0, _update)

        threading.Thread(target=_worker, daemon=True).start()



    def _export_obj(self):
        """Save current model as Wavefront OBJ (+ .mtl and texture .png if available)."""
        if self._current_geom is None:
            self._status.set("No geometry — select a model and wait for decode first")
            return
        geom = self._current_geom
        tex  = self._current_texture
        default_name = geom.path.stem + ".obj"
        out = filedialog.asksaveasfilename(
            title="Export OBJ",
            initialdir=str(Path.home() / "Desktop"),
            initialfile=default_name,
            defaultextension=".obj",
            filetypes=[("Wavefront OBJ", "*.obj"), ("All files", "*.*")],
        )
        if not out:
            return
        from decoders.i3d import export_obj
        if export_obj(geom, Path(out), texture=tex):
            tex_note = " + texture" if tex else ""
            self._status.set(f"OBJ saved: {Path(out).name}  "
                             f"({len(geom.vertices):,} verts, {len(geom.faces):,} faces{tex_note})")
        else:
            self._status.set("OBJ export failed")

    def _export_gltf(self):
        """Export current model as glTF 2.0 — skeleton + all animation clips + textures."""
        if self._current_geom is None:
            self._status.set("No geometry — select a model and wait for decode first")
            return
        geom = self._current_geom
        if geom.rig is None:
            self._status.set("No rig data — old-format model cannot be exported as glTF")
            return

        default_name = geom.path.stem + ".gltf"
        out = filedialog.asksaveasfilename(
            title="Export glTF 2.0 (rigged + animated)",
            initialdir=str(Path.home() / "Desktop"),
            initialfile=default_name,
            defaultextension=".gltf",
            filetypes=[("glTF 2.0", "*.gltf"), ("All files", "*.*")],
        )
        if not out:
            return

        textures = getattr(self._viewer, '_textures', [])
        out_path  = Path(out)
        self._status.set(f"Exporting {geom.path.stem}… (baking animations, may take a moment)")

        def _worker():
            log.info("glTF export start: %s -> %s", geom.path.name, out_path)
            try:
                from decoders.gltf_export import export_gltf
                ok = export_gltf(
                    geom, textures, out_path,
                    status_cb=lambda msg: (
                        log.info("  %s", msg),
                        self.after(0, lambda m=msg: self._status.set(m)),
                    ),
                )
                n_anim = len(geom.anim_states)
                nb     = geom.rig.num_bones
                if ok:
                    sz_kb = out_path.stat().st_size // 1024
                    log.info("glTF export done: %s (%d KB)", out_path.name, sz_kb)
                    msg = (f"glTF saved: {out_path.name}  "
                           f"({len(geom.vertices):,} verts · {nb} bones · {n_anim} anim states)")
                else:
                    log.warning("glTF export returned False")
                    msg = "glTF export failed"
            except Exception as e:
                log.exception("glTF export error for %s", geom.path.name)
                msg = f"glTF export error: {e}"
            self.after(0, lambda m=msg: self._status.set(m))

        threading.Thread(target=_worker, daemon=True).start()

    def _batch_export_obj(self):
        """Export all currently listed models as OBJ files."""
        models = self._models if self._models else []
        if not models:
            self._status.set("No models loaded")
            return
        dest = RENDERS_DIR / "Models_OBJ"
        dest.mkdir(parents=True, exist_ok=True)
        total = len(models)
        self._batch_btn.config(text="Stop batch…", bg=RED,
                               command=lambda: setattr(self, '_batch_stop', True))
        self._batch_stop = False

        def _worker():
            ok = skip = 0
            for i, m in enumerate(models, 1):
                if getattr(self, '_batch_stop', False):
                    break
                path = m.get("path")
                if not path or not path.is_file():
                    skip += 1; continue
                out = dest / f"{path.stem}.obj"
                try:
                    from decoders.i3d import decode_i3d_geometry, export_obj
                    geom = decode_i3d_geometry(path)
                    if geom and export_obj(geom, out):
                        ok += 1
                    else:
                        skip += 1
                except Exception:
                    skip += 1
                if i % 10 == 0 or i == total:
                    self.after(0, lambda n=i: self._status.set(
                        f"Batch OBJ: {n}/{total}…"))
            self.after(0, self._on_batch_done, ok, skip, dest)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_batch_done(self, ok: int, skip: int, dest: Path):
        self._batch_btn.config(text="Batch Export OBJ", bg=ACCENT3,
                               command=self._batch_export_obj)
        self._status.set(f"Batch OBJ: {ok} exported, {skip} skipped → {dest}")


# ═══════════════════════════════════════════════════════════════════════════════
#  SPRITES BROWSER TAB
# ═══════════════════════════════════════════════════════════════════════════════

# Categories discovered dynamically from Thumbnails/ subdirectories.
# Preferred order for display; any extra dirs found on disk are appended.
_CAT_ORDER = [
    "Chars", "Equip", "Forest", "Town", "Dungeon", "Cave",
    "Keep", "KeepInt", "Ruin", "Labyrnth", "TownInt", "Misc",
]

def _get_sprite_categories() -> List[str]:
    """Scan Thumbnails/ and return sorted category names."""
    if not THUMBNAILS.exists():
        return _CAT_ORDER[:]
    found = sorted(d.name for d in THUMBNAILS.iterdir() if d.is_dir())
    # Preferred order first, then anything else alphabetically
    ordered = [c for c in _CAT_ORDER if c in found]
    ordered += [c for c in found if c not in _CAT_ORDER]
    return ordered if ordered else found

THUMB_SIZE  = 48   # displayed thumbnail px
CELL_W      = 72   # grid cell width
CELL_H      = 66   # grid cell height (image + name)
GRID_COLS   = 8    # thumbnails per row


def _decode_tn_pixels(raw: bytes) -> Optional[bytes]:
    """
    Decode a 768-byte .tn file to 1024 bytes of flat RGBA8888 (16×16 image).
    Palette index 0 is transparent (alpha=0); all others opaque.

    .tn format:
      [0:512]   256 × uint16 LE X1R5G5B5 palette  (R=bits14-10, G=9-5, B=4-0)
      [512:768] 256 bytes = 16×16 pixels as 8-bit palette indices
    """
    if len(raw) < 768:
        return None
    pal = []
    for i in range(256):
        word = struct.unpack_from('<H', raw, i * 2)[0]
        r = ((word >> 10) & 0x1F) << 3
        g = ((word >>  5) & 0x1F) << 3
        b = ( word        & 0x1F) << 3
        pal.append((r, g, b))
    indices = raw[512:768]
    pixels  = bytearray(256 * 4)  # RGBA
    for j in range(256):
        idx = indices[j]
        r, g, b = pal[idx]
        a = 0 if idx == 0 else 255
        pixels[j * 4]     = r
        pixels[j * 4 + 1] = g
        pixels[j * 4 + 2] = b
        pixels[j * 4 + 3] = a
    return bytes(pixels)


def _load_tn_image(tn_path: Path, size: int = THUMB_SIZE,
                   bg: tuple = (30, 42, 69)) -> Optional["Image.Image"]:
    """Load a 16×16 .tn thumbnail, composited over dark bg (index 0 = transparent)."""
    if not HAS_PIL:
        return None
    try:
        raw = tn_path.read_bytes()
        px  = _decode_tn_pixels(raw)
        if px is None:
            return None
        rgba = Image.frombytes('RGBA', (16, 16), px)
        canvas = Image.new('RGB', (16, 16), bg)
        canvas.paste(rgba, mask=rgba.split()[3])
        return canvas.resize((size, size), Image.NEAREST)
    except Exception:
        return None


class SpritesTab(tk.Frame):
    """Browse all sprite thumbnails by category; click to decode full i2d."""

    def __init__(self, parent, status: StatusBar):
        super().__init__(parent, bg=BG_MID)
        self._status      = status
        self._cats        = _get_sprite_categories()
        self._cat         = tk.StringVar(value=self._cats[0] if self._cats else "")
        self._ph_cache: dict[str, "ImageTk.PhotoImage"] = {}
        self._full_img    = None      # current detail PIL image
        self._full_ph     = None
        self._tn_items: list[tuple[Path, Path]] = []   # (tn_path, i2d_path)
        self._sel_name    = tk.StringVar(value="")
        self._export_stop = False     # flag to cancel running export
        self._build_ui()
        if self._cats:
            self.after(200, lambda: self._load_category(self._cats[0]))

    # ── UI construction ──────────────────────────────────────────────────────
    def _build_ui(self):
        # Top toolbar
        bar = tk.Frame(self, bg=BG_DARK, pady=4)
        bar.pack(fill="x")
        tk.Label(bar, text="Category:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 10)).pack(side="left", padx=(12, 4))
        self._cat_cb = ttk.Combobox(bar, textvariable=self._cat,
                                    values=self._cats, state="readonly", width=14)
        self._cat_cb.pack(side="left", padx=(0, 10))
        self._cat_cb.bind("<<ComboboxSelected>>", self._on_cat_change)

        self._count_lbl = tk.Label(bar, text="", bg=BG_DARK, fg=FG_DIM,
                                    font=("Segoe UI", 9))
        self._count_lbl.pack(side="left", padx=10)

        # Right-side buttons
        tk.Button(bar, text="Save PNG", bg=BG_PANEL, fg=FG_TEXT,
                  relief="flat", padx=8,
                  command=self._save_full_png).pack(side="right", padx=4)
        self._export_btn = tk.Button(bar, text="Export All", bg=ACCENT2,
                                     fg="white", relief="flat", padx=8,
                                     command=self._export_all)
        self._export_btn.pack(side="right", padx=4)

        # Main split: grid left | detail right
        paned = tk.PanedWindow(self, orient="horizontal", bg=BG_DARK,
                               sashwidth=4, sashrelief="flat")
        paned.pack(fill="both", expand=True)

        # ── Left: scrollable thumbnail grid ──────────────────────────────────
        left = tk.Frame(paned, bg=BG_MID)
        paned.add(left, minsize=200)

        self._canvas = tk.Canvas(left, bg=BG_MID, highlightthickness=0)
        vsb = ttk.Scrollbar(left, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        self._canvas.bind("<Configure>", self._on_resize)
        self._canvas.bind("<MouseWheel>", lambda e: self._canvas.yview_scroll(
            -1 if e.delta > 0 else 1, "units"))

        # inner frame inside canvas for the grid
        self._inner = tk.Frame(self._canvas, bg=BG_MID)
        self._win_id = self._canvas.create_window((0, 0), window=self._inner,
                                                   anchor="nw")
        self._inner.bind("<Configure>",
                         lambda e: self._canvas.configure(
                             scrollregion=self._canvas.bbox("all")))

        # ── Right: detail panel ───────────────────────────────────────────────
        right = tk.Frame(paned, bg=BG_PANEL, width=340)
        paned.add(right, minsize=240)

        tk.Label(right, textvariable=self._sel_name, bg=BG_PANEL, fg=ACCENT2,
                 font=("Segoe UI", 11, "bold"), anchor="center").pack(
                     fill="x", pady=(10, 4))

        self._dim_lbl = tk.Label(right, text="", bg=BG_PANEL, fg=FG_DIM,
                                  font=("Segoe UI", 9))
        self._dim_lbl.pack(fill="x", padx=10)

        # Image canvas for the decoded sprite
        self._detail_canvas = tk.Canvas(right, bg=BG_MID, highlightthickness=1,
                                         highlightbackground=BG_DARK)
        self._detail_canvas.pack(fill="both", expand=True, padx=10, pady=10)

        self._decode_lbl = tk.Label(right, text="", bg=BG_PANEL, fg=FG_DIM,
                                     font=("Segoe UI", 8))
        self._decode_lbl.pack(pady=(0, 6))

    # ── Category loading ─────────────────────────────────────────────────────
    def _on_cat_change(self, _=None):
        self._load_category(self._cat.get())

    def _load_category(self, cat: str):
        tn_dir  = THUMBNAILS / cat
        img_dir = IMAGERY_ASSETS / cat
        if not tn_dir.exists():
            self._status.set(f"No thumbnails for {cat}")
            return

        self._status.set(f"Loading {cat} thumbnails…")
        self._ph_cache.clear()

        # Collect (tn_path, i2d_path) pairs
        # On Windows glob("*.tn") already matches .TN (case-insensitive FS),
        # so combining both patterns produces duplicates — deduplicate by stem.
        _seen: set[str] = set()
        tn_files: list[Path] = []
        for f in sorted(tn_dir.iterdir()):
            if f.suffix.lower() == ".tn" and f.stem.lower() not in _seen:
                _seen.add(f.stem.lower())
                tn_files.append(f)
        # Build a lowercase stem→path index for i2d files in img_dir (fast lookup)
        i2d_index: dict[str, Path] = {}
        if img_dir.exists():
            for f in img_dir.iterdir():
                if f.suffix.lower() == ".i2d":
                    i2d_index[f.stem.lower()] = f

        pairs: list[tuple[Path, Path]] = []
        for tn in tn_files:
            i2d = i2d_index.get(tn.stem.lower(), Path(""))
            pairs.append((tn, i2d))
        self._tn_items = pairs

        self._count_lbl.config(text=f"{len(pairs)} sprites")
        self._rebuild_grid()
        self._status.set(f"{cat}: {len(pairs)} sprites")

    def _rebuild_grid(self):
        # Clear old widgets
        for w in self._inner.winfo_children():
            w.destroy()
        self._ph_cache.clear()

        ncols = max(1, GRID_COLS)
        for idx, (tn_path, i2d_path) in enumerate(self._tn_items):
            row = idx // ncols
            col = idx % ncols
            cell = tk.Frame(self._inner, bg=BG_MID,
                            width=CELL_W, height=CELL_H)
            cell.grid_propagate(False)
            cell.grid(row=row, column=col, padx=2, pady=2)

            # Thumbnail image
            img = _load_tn_image(tn_path, THUMB_SIZE)
            if img and HAS_PIL:
                ph = ImageTk.PhotoImage(img)
                self._ph_cache[str(tn_path)] = ph
                lbl = tk.Label(cell, image=ph, bg=BG_MID, cursor="hand2")
                lbl._photo = ph
                lbl.pack(pady=(3, 0))
            else:
                ph = None
                lbl = tk.Label(cell, text="?", bg=BG_MID, fg=FG_DIM,
                               width=4, height=3)
                lbl.pack(pady=(3, 0))

            # Name label (truncated)
            name = tn_path.stem[:11]
            tk.Label(cell, text=name, bg=BG_MID, fg=FG_TEXT,
                     font=("Segoe UI", 7), anchor="center").pack()

            # Bind click
            for w in (cell, lbl):
                w.bind("<Button-1>",
                       lambda e, tp=tn_path, ip=i2d_path: self._on_click(tp, ip))

        # Update scroll region
        self._inner.update_idletasks()
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    # ── Sprite click → decode ────────────────────────────────────────────────
    def _on_click(self, tn_path: Path, i2d_path: Path):
        name = tn_path.stem
        self._sel_name.set(name)
        self._decode_lbl.config(text="Decoding…")
        self._status.set(f"Decoding {name}…")

        def _worker():
            # Try full i2d decode first
            img = None
            if i2d_path.is_file():
                try:
                    from decoders.i2d import decode_i2d
                    img = decode_i2d(i2d_path)
                except Exception:
                    pass
            # Fallback: scale up the .tn thumbnail
            if img is None:
                img = _load_tn_image(tn_path, 128)
                label_txt = f"Preview: {tn_path.name}  (no i2d decode)"
            else:
                label_txt = f"{img.width}×{img.height}px  |  {i2d_path.name}"
            self.after(0, lambda: self._show_detail(img, label_txt))

        import threading
        threading.Thread(target=_worker, daemon=True).start()

    def _show_detail(self, img, label_txt: str):
        if img is None:
            self._decode_lbl.config(text="Decode failed")
            return
        self._full_img = img
        # Fit into the detail canvas
        cw = self._detail_canvas.winfo_width()  or 300
        ch = self._detail_canvas.winfo_height() or 300
        scale = min(cw / max(img.width, 1), ch / max(img.height, 1), 4.0)
        dw = max(1, int(img.width  * scale))
        dh = max(1, int(img.height * scale))

        disp = img.resize((dw, dh), Image.NEAREST)
        # Composite onto dark background
        bg = Image.new("RGBA", (dw, dh), (20, 20, 30, 255))
        if disp.mode == "RGBA":
            bg.paste(disp, (0, 0), disp)
        else:
            bg.paste(disp.convert("RGBA"), (0, 0))
        ph = ImageTk.PhotoImage(bg)
        self._full_ph = ph

        self._detail_canvas.delete("all")
        self._detail_canvas.create_image(cw // 2, ch // 2,
                                          anchor="center", image=ph)
        self._detail_canvas.configure(scrollregion=self._detail_canvas.bbox("all"))
        self._dim_lbl.config(text=f"{img.width}×{img.height} px")
        self._decode_lbl.config(text=label_txt)
        self._status.set(label_txt)

    def _on_resize(self, _=None):
        w = self._canvas.winfo_width()
        self._canvas.itemconfig(self._win_id, width=w)

    def _export_all(self):
        """Batch-decode and save all sprites in the current category as PNGs."""
        if not self._tn_items:
            self._status.set("No sprites loaded — select a category first")
            return
        cat  = self._cat.get()
        dest = RENDERS_DIR / cat
        dest.mkdir(parents=True, exist_ok=True)

        total = len(self._tn_items)
        self._export_stop = False
        self._export_btn.config(text="Stop", command=self._stop_export,
                                bg=RED)

        def _worker():
            ok = skip = 0
            for n, (tn_path, i2d_path) in enumerate(self._tn_items, 1):
                if self._export_stop:
                    break
                out = dest / f"{tn_path.stem}.png"
                img = None
                # Try full i2d decode first
                if i2d_path.is_file():
                    try:
                        from decoders.i2d import decode_i2d
                        img = decode_i2d(i2d_path)
                    except Exception:
                        pass
                # Fallback: scale up the .tn thumbnail (48×48)
                if img is None:
                    img = _load_tn_image(tn_path, 64)
                if img:
                    try:
                        img.save(str(out))
                        ok += 1
                    except Exception:
                        skip += 1
                else:
                    skip += 1
                if n % 20 == 0 or n == total:
                    self.after(0, lambda n=n: self._status.set(
                        f"Exporting {cat}: {n}/{total}…"))
            self.after(0, self._on_export_done, ok, skip, dest)

        threading.Thread(target=_worker, daemon=True).start()

    def _stop_export(self):
        self._export_stop = True

    def _on_export_done(self, ok: int, skip: int, dest: Path):
        self._export_btn.config(text="Export All", command=self._export_all,
                                bg=ACCENT2)
        self._status.set(
            f"Export done: {ok} saved, {skip} skipped → {dest}")

    def _save_full_png(self):
        if self._full_img is None:
            self._status.set("Nothing to save — click a sprite first")
            return
        RENDERS_DIR.mkdir(exist_ok=True)
        name = self._sel_name.get() or "sprite"
        out = RENDERS_DIR / f"{name}.png"
        try:
            self._full_img.save(str(out))
            self._status.set(f"Saved: {out.name}")
        except Exception as e:
            self._status.set(f"Save failed: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  SOUNDS TAB
# ═══════════════════════════════════════════════════════════════════════════════

class SoundsTab(tk.Frame):
    """Browse and play all game audio: music tracks + voice/SFX MP3s."""

    def __init__(self, parent, status: StatusBar):
        super().__init__(parent, bg=BG_MID)
        self._status       = status
        self._sounds: List[Dict] = []
        self._current_proc = None
        self._build_ui()
        self.after(600, self._load_all)

    def _build_ui(self):
        bar = tk.Frame(self, bg=BG_DARK, pady=4)
        bar.pack(fill="x")

        tk.Label(bar, text="Filter:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 10)).pack(side="left", padx=(10, 4))
        self._flt_var = tk.StringVar()
        tk.Entry(bar, textvariable=self._flt_var,
                 bg=BG_PANEL, fg=FG_TEXT, insertbackground=FG_TEXT,
                 font=("Segoe UI", 10), relief="flat", width=28
                 ).pack(side="left", padx=4)
        self._flt_var.trace_add("write", self._filter)

        tk.Button(bar, text="▶ Play", bg=ACCENT3, fg="#000", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10,
                  command=self._play_selected).pack(side="left", padx=8)
        tk.Button(bar, text="■ Stop", bg=RED, fg="white", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10,
                  command=self._stop).pack(side="left", padx=2)

        self._count_lbl = tk.Label(bar, text="", bg=BG_DARK, fg=FG_DIM,
                                   font=("Segoe UI", 9))
        self._count_lbl.pack(side="right", padx=12)

        pane = tk.PanedWindow(self, orient="horizontal", bg=BG_DARK,
                              sashwidth=6, sashrelief="flat")
        pane.pack(fill="both", expand=True)

        tv_f = tk.Frame(pane, bg=BG_MID)
        pane.add(tv_f, minsize=560)
        cols = ("name", "cat", "size")
        self._tv = ttk.Treeview(tv_f, columns=cols, show="headings",
                                selectmode="browse")
        self._tv.heading("name", text="File",     anchor="w")
        self._tv.heading("cat",  text="Category", anchor="w")
        self._tv.heading("size", text="KB",        anchor="center")
        self._tv.column("name", width=320, stretch=True)
        self._tv.column("cat",  width=120, stretch=False)
        self._tv.column("size", width=60,  stretch=False, anchor="center")
        sb = ttk.Scrollbar(tv_f, orient="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._tv.pack(fill="both", expand=True)
        self._tv.bind("<Double-Button-1>", lambda e: self._play_selected())

        # Detail panel
        det = tk.Frame(pane, bg=BG_PANEL, padx=12, pady=12)
        pane.add(det, minsize=200)
        tk.Label(det, text="SOUND DETAILS", bg=BG_PANEL, fg=ACCENT2,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Separator(det).pack(fill="x", pady=6)
        self._det_lbl = tk.Label(det, text="Select a file to preview",
                                 bg=BG_PANEL, fg=FG_DIM,
                                 font=("Segoe UI", 9), wraplength=180,
                                 justify="left", anchor="w")
        self._det_lbl.pack(anchor="w")

    def _load_all(self):
        self._status.set("Scanning sound files…")
        sounds = []
        # Music OGG tracks
        for snd_dir in EXTRACT_DIR.rglob("Sound"):
            if not snd_dir.is_dir():
                continue
            for f in sorted(snd_dir.iterdir()):
                if f.suffix.lower() in ('.ogg', '.wav'):
                    cat = "Music" if f.suffix.lower() == '.ogg' else "SFX"
                    sounds.append({"name": f.name, "cat": cat,
                                   "path": f, "size_kb": f.stat().st_size // 1024})
            # English voice / SFX subfolder
            eng = snd_dir / "english"
            if eng.is_dir():
                for f in sorted(eng.iterdir()):
                    if f.suffix.lower() in ('.mp3', '.wav', '.ogg'):
                        sounds.append({"name": f.name, "cat": "Voice/SFX",
                                       "path": f, "size_kb": f.stat().st_size // 1024})
        self._sounds = sounds
        self._populate(sounds)
        self._count_lbl.config(text=f"{len(sounds)} sounds")
        self._status.set(f"Sounds: {len(sounds)} files indexed")

    def _populate(self, data: List[Dict]):
        self._tv.delete(*self._tv.get_children())
        for s in data:
            self._tv.insert("", "end",
                values=(s["name"], s["cat"], s["size_kb"]),
                tags=(str(s["path"]),))

    def _filter(self, *_):
        flt = self._flt_var.get().strip().lower()
        filtered = ([s for s in self._sounds
                     if flt in s["name"].lower() or flt in s["cat"].lower()]
                    if flt else self._sounds)
        self._populate(filtered)
        self._count_lbl.config(text=f"{len(filtered)} / {len(self._sounds)}")

    def _selected_path(self) -> Optional[Path]:
        sel = self._tv.selection()
        if not sel:
            return None
        tags = self._tv.item(sel[0], "tags")
        return Path(tags[0]) if tags else None

    def _play_selected(self):
        p = self._selected_path()
        if p is None or not p.exists():
            self._status.set("Select a sound file first.")
            return
        self._stop()
        self._status.set(f"Playing: {p.name}")
        self._det_lbl.config(text=f"{p.name}\n{p.stat().st_size // 1024} KB")
        import subprocess, sys
        try:
            if sys.platform == "win32":
                import os
                os.startfile(str(p))
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except Exception as e:
            self._status.set(f"Playback error: {e}")

    def _stop(self):
        if self._current_proc and self._current_proc.poll() is None:
            try:
                self._current_proc.terminate()
            except Exception:
                pass
        self._current_proc = None


# ═══════════════════════════════════════════════════════════════════════════════
#  CINEMATIX TAB
# ═══════════════════════════════════════════════════════════════════════════════

class CinematiXTab(tk.Frame):
    """Browse and launch all Smacker (.SMK) video files."""

    _SMK_DIRS = [
        Path("C:/GOG Games/Revenant/Disk2"),
        GAME_DIR / "Disk2",
    ]

    def __init__(self, parent, status: StatusBar):
        super().__init__(parent, bg=BG_MID)
        self._status = status
        self._videos: List[Dict] = []
        self._build_ui()
        self.after(300, self._load_all)

    def _build_ui(self):
        bar = tk.Frame(self, bg=BG_DARK, pady=4)
        bar.pack(fill="x")
        tk.Label(bar, text="Revenant FMV / Cinematix Videos", bg=BG_DARK,
                 fg=FG_DIM, font=("Segoe UI", 10)).pack(side="left", padx=10)
        tk.Button(bar, text="▶ Play", bg=ACCENT, fg="white", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10,
                  command=self._play_selected).pack(side="left", padx=8)
        self._count_lbl = tk.Label(bar, text="", bg=BG_DARK, fg=FG_DIM,
                                   font=("Segoe UI", 9))
        self._count_lbl.pack(side="right", padx=12)

        pane = tk.PanedWindow(self, orient="horizontal", bg=BG_DARK,
                              sashwidth=6, sashrelief="flat")
        pane.pack(fill="both", expand=True)

        tv_f = tk.Frame(pane, bg=BG_MID)
        pane.add(tv_f, minsize=400)
        cols = ("name", "size", "path")
        self._tv = ttk.Treeview(tv_f, columns=cols, show="headings",
                                selectmode="browse")
        self._tv.heading("name", text="Video File", anchor="w")
        self._tv.heading("size", text="Size (MB)",  anchor="center")
        self._tv.heading("path", text="Location",   anchor="w")
        self._tv.column("name", width=240, stretch=False)
        self._tv.column("size", width=80,  stretch=False, anchor="center")
        self._tv.column("path", width=300, stretch=True)
        sb = ttk.Scrollbar(tv_f, orient="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._tv.pack(fill="both", expand=True)
        self._tv.bind("<Double-Button-1>", lambda e: self._play_selected())

        det = tk.Frame(pane, bg=BG_PANEL, padx=14, pady=12)
        pane.add(det, minsize=240)
        tk.Label(det, text="VIDEO INFO", bg=BG_PANEL, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Separator(det).pack(fill="x", pady=6)
        self._det_lbl = tk.Label(det, text="Select a video to preview info",
                                 bg=BG_PANEL, fg=FG_DIM, font=("Segoe UI", 9),
                                 wraplength=200, justify="left", anchor="w")
        self._det_lbl.pack(anchor="w")
        tk.Label(det, text="\nDouble-click or press ▶ Play to open\nwith the system's default video player\n(install VLC for best SMK support).",
                 bg=BG_PANEL, fg=FG_MUTED, font=("Segoe UI", 8),
                 justify="left").pack(anchor="w", pady=8)

    def _load_all(self):
        self._status.set("Scanning for SMK video files…")
        seen: set = set()
        videos = []
        search_dirs = list(self._SMK_DIRS) + [GAME_DIR, EXTRACT_DIR]
        for d in search_dirs:
            if not d.exists():
                continue
            for f in d.rglob("*.smk"):
                key = f.name.upper()
                if key not in seen:
                    seen.add(key)
                    videos.append({"name": f.name,
                                   "path": f,
                                   "size_mb": f.stat().st_size / (1024 * 1024)})
            for f in d.rglob("*.SMK"):
                key = f.name.upper()
                if key not in seen:
                    seen.add(key)
                    videos.append({"name": f.name,
                                   "path": f,
                                   "size_mb": f.stat().st_size / (1024 * 1024)})
        videos.sort(key=lambda x: x["name"].upper())
        self._videos = videos
        self._tv.delete(*self._tv.get_children())
        for v in videos:
            self._tv.insert("", "end",
                values=(v["name"], f"{v['size_mb']:.1f}", str(v["path"].parent)),
                tags=(str(v["path"]),))
        self._count_lbl.config(text=f"{len(videos)} video(s)")
        if videos:
            self._status.set(f"Cinematix: {len(videos)} SMK video(s) found")
        else:
            self._status.set("No SMK videos found — check GOG install path")

    def _play_selected(self):
        sel = self._tv.selection()
        if not sel:
            self._status.set("Select a video first.")
            return
        tags = self._tv.item(sel[0], "tags")
        if not tags:
            return
        p = Path(tags[0])
        if not p.exists():
            self._status.set(f"File not found: {p}")
            return
        import sys, os
        self._det_lbl.config(
            text=f"{p.name}\n{p.stat().st_size / (1024*1024):.1f} MB\n{p.parent}")
        self._status.set(f"Opening: {p.name}")
        try:
            if sys.platform == "win32":
                os.startfile(str(p))
            else:
                import subprocess
                subprocess.Popen(["xdg-open", str(p)])
        except Exception as e:
            self._status.set(f"Could not open video: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  UI RESOURCES TAB
# ═══════════════════════════════════════════════════════════════════════════════

_UI_CATEGORIES: Dict[str, List[str]] = {
    "Menus":        ["splash", "menus", "selstarttex", "selstartnotex",
                     "ingamemenutex", "ingamemenunotex", "death", "credits",
                     "demo", "exit"],
    "Save / Load":  ["loadgametex", "loadgamenotex", "loadgamealpha", "loadbar",
                     "savegametex", "savegamenotex", "savegamealpha",
                     "userinfonotex", "userinfotex"],
    "Character":    ["createchartex", "createcharnotex", "createcharalpha"],
    "HUD":          ["bottombar", "health", "stamina", "startbar",
                     "statusbar", "statusbarnotex", "sidepane",
                     "sidebartabs", "sidebartabsnotex"],
    "Inventory":    ["inventory", "equippane", "equipscr", "intrface",
                     "book", "buysell", "gamedata", "scroll", "spellscroll",
                     "spellpane", "spellicons", "automap"],
    "Dialog":       ["dialog", "dlg", "dlgfont", "dlgfonts"],
    "Fonts":        ["gamefont", "sysfont", "scrlfont", "smlfont", "gnrmfont"],
    "Multiplayer":  ["hostgame", "joingame", "connect", "mpingame",
                     "mpingamenotex", "mpingametex"],
    "Gold / Items": ["medgold", "medgoldg", "medgoldglow", "medgolds",
                     "medgoldsel", "medgoldshad", "medgoldsilv",
                     "smallgold", "smallgoldg", "smallgoldglow", "smallgolds",
                     "smallgoldsel", "smallgoldshad", "smallgoldsilv"],
    "Widgets":      ["widgetstex", "widgetsnotex", "widgetsalpha", "imagery"],
    "Editor (GCK)": ["editor"],
}


def _scan_dat_frames(path: Path) -> int:
    """Return frame count from CGSR .dat header, 0 if not valid CGSR."""
    try:
        raw = path.read_bytes()
        if len(raw) >= 5 and raw[:4] == b'CGSR':
            return raw[4]
    except Exception:
        pass
    return 0


class UIResourcesTab(tk.Frame):
    _THUMB = 80   # element tile size
    _BG_W  = 480  # preview max width
    _BG_H  = 320  # preview max height

    def __init__(self, parent, status: StatusBar):
        super().__init__(parent, bg=BG_MID)
        self._status      = status
        self._dat_files   : Dict[str, Path] = {}
        self._raw_imgs    : List[Optional["Image.Image"]] = []
        self._thumb_phs   : List["ImageTk.PhotoImage"] = []
        self._cur_file    : Optional[Path] = None
        self._cur_frame   : int = 0
        self._bg_idx      : int = 0
        self._anim_id     : Optional[str] = None
        self._playing     : bool = False
        self._fps_var     : tk.IntVar
        self._export_stop : bool = False
        self._build_ui()
        self.after(300, self._load_files)

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Top toolbar
        bar = tk.Frame(self, bg=BG_DARK, pady=4)
        bar.pack(fill="x")
        tk.Label(bar, text="UI Resources", bg=BG_DARK, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(side="left", padx=10)
        self._count_lbl = tk.Label(bar, text="", bg=BG_DARK, fg=FG_DIM,
                                   font=("Segoe UI", 9))
        self._count_lbl.pack(side="left", padx=6)
        tk.Button(bar, text="Export All UI", bg=ACCENT3, fg="#000",
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=8,
                  command=self._export_all).pack(side="right", padx=4)
        tk.Button(bar, text="Export Frames", bg=ACCENT2, fg="#000",
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=8,
                  command=self._export_file).pack(side="right", padx=4)

        # Horizontal split: tree | content
        pane = tk.PanedWindow(self, orient="horizontal", bg=BG_DARK,
                              sashwidth=4, sashpad=0)
        pane.pack(fill="both", expand=True)

        # ── Left: category tree ──────────────────────────────────────────────
        left = tk.Frame(pane, bg=BG_PANEL, width=220)
        pane.add(left, minsize=160)
        tk.Label(left, text="Files", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8, pady=(4, 0))
        sb_tv = ttk.Scrollbar(left, orient="vertical")
        sb_tv.pack(side="right", fill="y")
        self._tv = ttk.Treeview(left, yscrollcommand=sb_tv.set,
                                selectmode="browse", show="tree")
        sb_tv.config(command=self._tv.yview)
        self._tv.pack(fill="both", expand=True)
        self._tv.bind("<<TreeviewSelect>>", self._on_select)

        # ── Right: vertical split — preview top, tile grid bottom ────────────
        right = tk.Frame(pane, bg=BG_DARK)
        pane.add(right, minsize=500)

        v_pane = tk.PanedWindow(right, orient="vertical", bg=BG_DARK,
                                sashwidth=5)
        v_pane.pack(fill="both", expand=True)

        # ─ Preview panel ─────────────────────────────────────────────────────
        preview_outer = tk.Frame(v_pane, bg=BG_DARK)
        v_pane.add(preview_outer, minsize=180)

        # Info + animate controls on one bar above the canvas
        pbar = tk.Frame(preview_outer, bg=BG_MID, pady=3)
        pbar.pack(fill="x")
        self._file_lbl = tk.Label(pbar, text="Select a file", bg=BG_MID,
                                  fg=ACCENT, font=("Segoe UI", 10, "bold"))
        self._file_lbl.pack(side="left", padx=10)
        self._info_lbl = tk.Label(pbar, text="", bg=BG_MID, fg=FG_DIM,
                                  font=("Segoe UI", 9))
        self._info_lbl.pack(side="left", padx=6)

        self._fps_var = tk.IntVar(value=8)
        self._play_btn = tk.Button(pbar, text="▶ Animate", bg=BG_MID,
                                   fg=FG_TEXT, relief="flat",
                                   font=("Segoe UI", 8), padx=6,
                                   command=self._toggle_play)
        self._play_btn.pack(side="right", padx=4)
        tk.Spinbox(pbar, from_=1, to=30, textvariable=self._fps_var,
                   bg=BG_PANEL, fg=FG_TEXT, buttonbackground=BG_MID,
                   relief="flat", width=3,
                   font=("Segoe UI", 8)).pack(side="right", padx=(0, 2))
        tk.Label(pbar, text="fps", bg=BG_MID, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(side="right")

        # Large preview canvas (background / selected element)
        self._preview_canvas = tk.Canvas(preview_outer, bg="#080812",
                                         bd=0, highlightthickness=0)
        self._preview_canvas.pack(fill="both", expand=True, padx=6, pady=(0, 4))
        self._preview_canvas.bind("<Configure>", lambda e: self._draw_preview())

        # ─ Tile grid ─────────────────────────────────────────────────────────
        grid_outer = tk.Frame(v_pane, bg=BG_DARK)
        v_pane.add(grid_outer, minsize=120)

        gbar = tk.Frame(grid_outer, bg=BG_MID, pady=2)
        gbar.pack(fill="x")
        self._grid_lbl = tk.Label(gbar, text="Elements", bg=BG_MID,
                                  fg=ACCENT2, font=("Segoe UI", 9, "bold"))
        self._grid_lbl.pack(side="left", padx=10)
        self._frame_nav = tk.Label(gbar, text="", bg=BG_MID, fg=FG_DIM,
                                   font=("Segoe UI", 8))
        self._frame_nav.pack(side="left", padx=6)

        h_sb = ttk.Scrollbar(grid_outer, orient="horizontal")
        h_sb.pack(side="bottom", fill="x")
        v_sb = ttk.Scrollbar(grid_outer, orient="vertical")
        v_sb.pack(side="right", fill="y")
        self._grid_canvas = tk.Canvas(grid_outer, bg=BG_DARK, bd=0,
                                      highlightthickness=0,
                                      xscrollcommand=h_sb.set,
                                      yscrollcommand=v_sb.set)
        self._grid_canvas.pack(fill="both", expand=True)
        h_sb.config(command=self._grid_canvas.xview)
        v_sb.config(command=self._grid_canvas.yview)
        self._grid_inner = tk.Frame(self._grid_canvas, bg=BG_DARK)
        self._grid_win = self._grid_canvas.create_window(
            (0, 0), window=self._grid_inner, anchor="nw")
        self._grid_inner.bind("<Configure>", lambda e:
            self._grid_canvas.configure(
                scrollregion=self._grid_canvas.bbox("all")))
        self._grid_canvas.bind("<Configure>", lambda e:
            self._grid_canvas.itemconfig(self._grid_win, width=e.width))

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_files(self):
        self._dat_files.clear()
        for p in sorted(RESOURCES.glob("*.dat")):
            self._dat_files[p.stem.lower()] = p
        for p in sorted(IMAGERY.glob("*.dat")):
            if p.stem.lower() not in self._dat_files:
                self._dat_files[p.stem.lower()] = p

        stem_to_cat: Dict[str, str] = {}
        for cat, stems in _UI_CATEGORIES.items():
            for s in stems:
                stem_to_cat[s.lower()] = cat

        buckets: Dict[str, List[tuple]] = {c: [] for c in _UI_CATEGORIES}
        buckets["Misc"] = []
        for stem, path in sorted(self._dat_files.items()):
            cat = stem_to_cat.get(stem, "Misc")
            n = _scan_dat_frames(path)
            buckets.setdefault(cat, []).append((stem, path, n))

        self._tv.delete(*self._tv.get_children())
        total = 0
        for cat in list(_UI_CATEGORIES.keys()) + ["Misc"]:
            items = buckets.get(cat, [])
            if not items:
                continue
            node = self._tv.insert("", "end",
                                   text=f"  {cat}  ({len(items)})",
                                   open=False, tags=("cat",))
            for stem, path, n in items:
                tag = f"  {stem}.dat" + (f"  [{n}f]" if n else "  [?]")
                self._tv.insert(node, "end", text=tag,
                                values=(str(path),), tags=("file",))
                total += 1

        self._tv.tag_configure("cat",  foreground=ACCENT2,
                               font=("Segoe UI", 9, "bold"))
        self._tv.tag_configure("file", foreground=FG_TEXT,
                               font=("Segoe UI", 9))
        self._count_lbl.config(text=f"{total} .dat files")

    # ── Selection / display ───────────────────────────────────────────────────

    def _on_select(self, _=None):
        sel = self._tv.selection()
        if not sel:
            return
        vals = self._tv.item(sel[0], "values")
        if not vals:
            return
        path = Path(vals[0])
        if path != self._cur_file:
            self._stop_anim()
            self._cur_file = path
            self._show_file(path)

    def _show_file(self, path: Path):
        self._stop_anim()
        self._file_lbl.config(text=path.name)
        self._info_lbl.config(text="Decoding…")
        for w in self._grid_inner.winfo_children():
            w.destroy()
        self._raw_imgs.clear()
        self._thumb_phs.clear()
        self._cur_frame = 0

        n = _scan_dat_frames(path)
        if not HAS_PIL or n == 0:
            self._info_lbl.config(text="Not CGSR / PIL unavailable")
            self._preview_canvas.delete("all")
            return

        # Decode all frames using fast BGR555 path
        for i in range(n):
            img = _decode_dat_frame(path, i)
            # If standard decoder got it, convert pixels via fast path for large images
            self._raw_imgs.append(img)

        valid = [(i, img) for i, img in enumerate(self._raw_imgs) if img]
        if not valid:
            self._info_lbl.config(text=f"{n} frames — no decodable images")
            self._preview_canvas.delete("all")
            return

        # Background = largest image by area
        self._bg_idx, bg_img = max(valid, key=lambda t: t[1].width * t[1].height)

        # Detect font file: all images narrow & short (glyph sheet)
        all_glyphs = all(img.width <= 24 and img.height <= 32 for _, img in valid)
        if all_glyphs and len(valid) >= 20:
            self._show_font_map(valid)
            return

        # Info bar
        n_elem = len(valid) - 1
        self._info_lbl.config(
            text=f"{bg_img.width}×{bg_img.height} BG  |  "
                 f"{n_elem} element{'s' if n_elem != 1 else ''}  |  {n} frames")
        self._grid_lbl.config(text="Elements")

        # Build tile grid (only valid images shown)
        THUMB = self._THUMB
        cw = self._grid_canvas.winfo_width() or (8 * (THUMB + 10))
        cols = max(1, cw // (THUMB + 10))

        for gi, (fi, img) in enumerate(valid):
            is_bg = (fi == self._bg_idx)
            t = img.copy()
            t.thumbnail((THUMB, THUMB))
            ph = ImageTk.PhotoImage(t)
            self._thumb_phs.append(ph)

            hl_bg   = ACCENT  if is_bg else BG_CARD
            hl_brd  = ACCENT  if is_bg else BORDER
            fg_lbl  = "#000"  if is_bg else FG_DIM

            cell = tk.Frame(self._grid_inner, bg=hl_bg,
                            highlightthickness=2,
                            highlightbackground=hl_brd)
            cell.grid(row=gi // cols, column=gi % cols, padx=4, pady=4)

            img_lbl = tk.Label(cell, image=ph, bg=hl_bg,
                               width=THUMB, height=THUMB)
            img_lbl.image = ph
            img_lbl.pack(padx=2, pady=(2, 0))

            tag  = "BG" if is_bg else f"f{fi}"
            dims = f"{img.width}×{img.height}"
            tk.Label(cell, text=f"{tag}  {dims}", bg=hl_bg, fg=fg_lbl,
                     font=("Segoe UI", 7, "bold" if is_bg else "normal")).pack(pady=(0, 2))

            for w in (img_lbl, cell):
                w.bind("<Button-1>", lambda e, idx=fi: self._select_frame(idx))

        self._frame_nav.config(text=f"{len(valid)} images")
        self._select_frame(self._bg_idx)

    def _show_font_map(self, valid: List[Tuple[int, "Image.Image"]]):
        """Display glyph sheet — one tile per character glyph in ASCII order."""
        self._grid_lbl.config(text="Font Glyphs")
        # ASCII printable starts at 32 (space); glyph f1 = ASCII 32
        # gamefont.dat frame 0 is metadata, frames 1..86 = glyphs for ASCII 32..117
        COLS = 16
        for gi, (fi, img) in enumerate(valid):
            char_code = 31 + fi   # frame 1 → ASCII 32 = space
            char = chr(char_code) if 32 <= char_code <= 126 else "?"
            scale = max(1, 40 // max(img.width, img.height, 1))
            nw, nh = img.width * scale, img.height * scale
            ph = ImageTk.PhotoImage(img.resize((nw, nh), Image.NEAREST))
            self._thumb_phs.append(ph)

            cell = tk.Frame(self._grid_inner, bg=BG_CARD,
                            highlightthickness=1, highlightbackground=BORDER)
            cell.grid(row=gi // COLS, column=gi % COLS, padx=2, pady=2)

            tk.Label(cell, image=ph, bg=BG_CARD,
                     width=40, height=40).pack()
            tk.Label(cell, text=f"'{char}'", bg=BG_CARD, fg=ACCENT2,
                     font=("Consolas", 7)).pack()
            cell._ph = ph

        total = len(valid)
        self._info_lbl.config(text=f"{total} glyphs  (font)")
        self._frame_nav.config(text=f"ASCII {32}–{31+total}")
        # Show first glyph in preview
        self._select_frame(valid[0][0] if valid else 0)

    def _select_frame(self, idx: int):
        self._cur_frame = idx
        n = len(self._raw_imgs)
        self._frame_nav.config(text=f"f{idx}  |  {n} frames")
        self._draw_preview()

    def _draw_preview(self):
        c = self._preview_canvas
        c.delete("all")
        imgs = self._raw_imgs
        if not imgs or self._cur_frame >= len(imgs):
            return
        img = imgs[self._cur_frame]
        if not img:
            cw, ch = max(1, c.winfo_width()), max(1, c.winfo_height())
            c.create_text(cw // 2, ch // 2,
                          text="(metadata frame — no image)",
                          fill=FG_MUTED, font=("Segoe UI", 10))
            return
        cw = max(1, c.winfo_width())
        ch = max(1, c.winfo_height())
        # Never upscale beyond 2× for crisp pixel art; downscale freely
        scale = min(cw / img.width, ch / img.height, 2.0)
        nw = max(1, int(img.width  * scale))
        nh = max(1, int(img.height * scale))
        mode = Image.NEAREST if scale >= 1.5 else Image.LANCZOS
        ph = ImageTk.PhotoImage(img.resize((nw, nh), mode))
        c.create_image(cw // 2, ch // 2, image=ph, anchor="center")
        c._ph = ph
        # Dimension overlay bottom-left
        c.create_text(8, ch - 8,
                      text=f"{img.width}×{img.height}",
                      fill=FG_DIM, font=("Segoe UI", 8), anchor="sw")

    # ── Animation ─────────────────────────────────────────────────────────────

    def _toggle_play(self):
        if self._playing:
            self._stop_anim()
        else:
            self._start_anim()

    def _start_anim(self):
        valid = [i for i, img in enumerate(self._raw_imgs) if img]
        if len(valid) < 2:
            return
        self._anim_valid = valid
        self._anim_vi    = 0
        self._playing    = True
        self._play_btn.config(text="■ Stop")
        self._anim_tick()

    def _anim_tick(self):
        if not self._playing:
            return
        self._anim_vi = (self._anim_vi + 1) % len(self._anim_valid)
        self._select_frame(self._anim_valid[self._anim_vi])
        delay = max(33, 1000 // max(1, self._fps_var.get()))
        self._anim_id = self.after(delay, self._anim_tick)

    def _stop_anim(self):
        self._playing = False
        self._play_btn.config(text="▶ Animate")
        if self._anim_id:
            self.after_cancel(self._anim_id)
            self._anim_id = None

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_file(self):
        if not self._cur_file or not self._raw_imgs:
            self._status.set("No file selected")
            return
        dest = RENDERS_DIR / "UI" / self._cur_file.stem
        dest.mkdir(parents=True, exist_ok=True)
        ok = 0
        for i, img in enumerate(self._raw_imgs):
            if img:
                try:
                    img.save(str(dest / f"frame_{i:03d}.png"))
                    ok += 1
                except Exception:
                    pass
        self._status.set(f"Exported {ok} frames → {dest}")

    def _export_all(self):
        if not self._dat_files:
            self._status.set("No files loaded")
            return
        self._export_stop = False
        dest_root = RENDERS_DIR / "UI"
        files = sorted(self._dat_files.items())
        total = len(files)

        def _worker():
            ok_files = ok_frames = 0
            for i, (stem, path) in enumerate(files, 1):
                if self._export_stop:
                    break
                n = _scan_dat_frames(path)
                if n == 0:
                    continue
                dest = dest_root / stem
                dest.mkdir(parents=True, exist_ok=True)
                for fi in range(n):
                    img = _decode_dat_frame(path, fi)
                    if img:
                        try:
                            img.save(str(dest / f"frame_{fi:03d}.png"))
                            ok_frames += 1
                        except Exception:
                            pass
                ok_files += 1
                self.after(0, lambda i=i: self._status.set(
                    f"Exporting UI: {i}/{total} files…"))
            self.after(0, lambda: self._status.set(
                f"UI export done — {ok_files} files, {ok_frames} frames → {dest_root}"))

        threading.Thread(target=_worker, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════════════════
#  AHKUILON TAB  (zone scripts + object coordinate map)
# ═══════════════════════════════════════════════════════════════════════════════

_SCRIPT_KW: Dict[str, re.Pattern] = {
    "block":   re.compile(r'\b(OBJECT|BEGIN|END)\b'),
    "trigger": re.compile(r'\b(CUBE|SPHERE|CYLINDER)\b'),
    "action":  re.compile(r'\b(FADESCREENOUT|FADESCREENIN|WAIT|SCREENFADE)\b'),
    "cmd":     re.compile(r'\b(DIALOG|CINEMATIC|STARTQUEST|ENDQUEST|PLAYSOUND|TELEPORT|POS)\b'),
    "prop":    re.compile(r'\b(player|PLAYER|HEALTH|GOLD)\b'),
    "number":  re.compile(r'(?<!\w)-?\d+(?:\.\d+)?(?!\w)'),
    "comment": re.compile(r'//.*'),
    "string":  re.compile(r'"[^"]*"'),
}

_CUBE_RE   = re.compile(
    r'CUBE\s+\w+\s+(-?\d+),(-?\d+),(-?\d+)\s+(-?\d+),(-?\d+),(-?\d+)',
    re.IGNORECASE)
_OBJECT_RE = re.compile(r'OBJECT\s+"([^"]+)"', re.IGNORECASE)


def _parse_script_objects(text: str) -> List[Dict]:
    objects: List[Dict] = []
    current = None
    for line in text.splitlines():
        m = _OBJECT_RE.search(line)
        if m:
            current = m.group(1)
        c = _CUBE_RE.search(line)
        if c and current is not None:
            x1, y1, z1, x2, y2, z2 = (int(c.group(i)) for i in range(1, 7))
            objects.append({
                "name": current,
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "cx": (x1 + x2) // 2, "cy": (y1 + y2) // 2,
            })
    return objects


class AhkuilonTab(tk.Frame):
    _AREAS = ["arakna", "cave", "dungeon", "forest", "keep",
              "labyrinth", "ruins", "town", "tower"]

    def __init__(self, parent, status: StatusBar):
        super().__init__(parent, bg=BG_MID)
        self._status   = status
        self._cur_path : Optional[Path] = None
        self._objects  : List[Dict] = []
        self._map_dots : List[Tuple] = []
        self._build_ui()
        self.after(300, self._load_files)

    def _build_ui(self):
        bar = tk.Frame(self, bg=BG_DARK, pady=4)
        bar.pack(fill="x")
        tk.Label(bar, text="Ahkuilon — Zone Scripts", bg=BG_DARK, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(side="left", padx=10)
        self._count_lbl = tk.Label(bar, text="", bg=BG_DARK, fg=FG_DIM,
                                   font=("Segoe UI", 9))
        self._count_lbl.pack(side="left", padx=8)
        tk.Button(bar, text="Export Scripts", bg=ACCENT2, fg="#000",
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=8,
                  command=self._export_all).pack(side="right", padx=4)

        pane = tk.PanedWindow(self, orient="horizontal", bg=BG_DARK,
                              sashwidth=4)
        pane.pack(fill="both", expand=True)

        # Left: file tree
        left = tk.Frame(pane, bg=BG_PANEL, width=200)
        pane.add(left, minsize=150)
        tk.Label(left, text="Scripts", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=8, pady=(4, 0))
        sb = ttk.Scrollbar(left, orient="vertical")
        sb.pack(side="right", fill="y")
        self._tv = ttk.Treeview(left, yscrollcommand=sb.set,
                                selectmode="browse", show="tree")
        sb.config(command=self._tv.yview)
        self._tv.pack(fill="both", expand=True)
        self._tv.bind("<<TreeviewSelect>>", self._on_select)

        # Right: text + map
        right = tk.Frame(pane, bg=BG_DARK)
        pane.add(right, minsize=500)

        v_pane = tk.PanedWindow(right, orient="vertical", bg=BG_DARK,
                                sashwidth=4)
        v_pane.pack(fill="both", expand=True)

        # Text viewer
        txt_frame = tk.Frame(v_pane, bg=BG_PANEL)
        v_pane.add(txt_frame, minsize=200)

        info_bar = tk.Frame(txt_frame, bg=BG_MID, pady=3)
        info_bar.pack(fill="x")
        self._file_lbl = tk.Label(info_bar, text="Select a script", bg=BG_MID,
                                  fg=ACCENT, font=("Segoe UI", 10, "bold"))
        self._file_lbl.pack(side="left", padx=10)
        self._obj_lbl = tk.Label(info_bar, text="", bg=BG_MID, fg=FG_DIM,
                                 font=("Segoe UI", 9))
        self._obj_lbl.pack(side="left", padx=8)
        tk.Button(info_bar, text="Open in Explorer", bg=BG_MID, fg=FG_DIM,
                  relief="flat", font=("Segoe UI", 8),
                  command=self._open_in_explorer).pack(side="right", padx=8)

        sb_h = ttk.Scrollbar(txt_frame, orient="horizontal")
        sb_h.pack(side="bottom", fill="x")
        sb_v = ttk.Scrollbar(txt_frame, orient="vertical")
        sb_v.pack(side="right", fill="y")
        self._txt = tk.Text(txt_frame, bg=BG_PANEL, fg=FG_TEXT,
                            font=("Consolas", 9), wrap="none", relief="flat",
                            xscrollcommand=sb_h.set, yscrollcommand=sb_v.set,
                            state="disabled")
        self._txt.pack(fill="both", expand=True)
        sb_h.config(command=self._txt.xview)
        sb_v.config(command=self._txt.yview)

        self._txt.tag_configure("block",   foreground=ACCENT,
                                font=("Consolas", 9, "bold"))
        self._txt.tag_configure("trigger", foreground=ACCENT2,
                                font=("Consolas", 9, "bold"))
        self._txt.tag_configure("action",  foreground=ACCENT3)
        self._txt.tag_configure("cmd",     foreground=GOLD)
        self._txt.tag_configure("prop",    foreground=RED)
        self._txt.tag_configure("number",  foreground="#a8dadc")
        self._txt.tag_configure("comment", foreground=FG_MUTED,
                                font=("Consolas", 9, "italic"))
        self._txt.tag_configure("string",  foreground=ACCENT3)

        # Object map
        map_frame = tk.Frame(v_pane, bg=BG_DARK)
        v_pane.add(map_frame, minsize=160)

        map_bar = tk.Frame(map_frame, bg=BG_MID, pady=3)
        map_bar.pack(fill="x")
        tk.Label(map_bar, text="Object Map  (CUBE triggers)", bg=BG_MID,
                 fg=ACCENT2, font=("Segoe UI", 9, "bold")).pack(side="left", padx=10)
        self._map_info = tk.Label(map_bar, text="", bg=BG_MID, fg=FG_DIM,
                                  font=("Segoe UI", 8))
        self._map_info.pack(side="left", padx=8)

        self._map_canvas = tk.Canvas(map_frame, bg="#0a0a12", bd=0,
                                     highlightthickness=0)
        self._map_canvas.pack(fill="both", expand=True)
        self._map_canvas.bind("<Configure>", lambda e: self._draw_map())
        self._map_canvas.bind("<Motion>", self._on_map_hover)

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_files(self):
        self._tv.delete(*self._tv.get_children())
        ahk = AHKUILON
        total = 0

        scr_node = self._tv.insert("", "end", text="  Zone Scripts",
                                   open=True, tags=("cat",))
        for area in self._AREAS:
            p = ahk / f"{area}.s"
            if p.exists():
                self._tv.insert(scr_node, "end", text=f"  {area}.s",
                                values=(str(p),), tags=("script",))
                total += 1

        def_node = self._tv.insert("", "end", text="  Definitions",
                                   open=False, tags=("cat",))
        for p in sorted(ahk.glob("*.def")):
            self._tv.insert(def_node, "end", text=f"  {p.name}",
                            values=(str(p),), tags=("def",))
            total += 1

        self._tv.tag_configure("cat",    foreground=ACCENT2,
                               font=("Segoe UI", 9, "bold"))
        self._tv.tag_configure("script", foreground=ACCENT3,
                               font=("Consolas", 9))
        self._tv.tag_configure("def",    foreground=GOLD,
                               font=("Consolas", 9))
        self._count_lbl.config(text=f"{total} files")

    # ── Selection / display ───────────────────────────────────────────────────

    def _on_select(self, _=None):
        sel = self._tv.selection()
        if not sel:
            return
        vals = self._tv.item(sel[0], "values")
        if not vals:
            return
        path = Path(vals[0])
        if path == self._cur_path:
            return
        self._cur_path = path
        self._load_script(path)

    def _load_script(self, path: Path):
        self._file_lbl.config(text=path.name)
        try:
            content = path.read_text(encoding="latin-1")
        except Exception as e:
            self._status.set(f"Read error: {e}")
            return

        self._objects = _parse_script_objects(content)
        lines = [l for l in content.splitlines() if l.strip()]
        self._obj_lbl.config(
            text=f"{len(self._objects)} CUBE objects  |  {len(lines)} lines")

        self._txt.configure(state="normal")
        self._txt.delete("1.0", "end")
        self._txt.insert("end", content)

        for tag, pat in _SCRIPT_KW.items():
            for m in pat.finditer(content):
                line = content[:m.start()].count('\n') + 1
                col  = m.start() - content[:m.start()].rfind('\n') - 1
                self._txt.tag_add(tag, f"{line}.{col}",
                                  f"{line}.{col + len(m.group())}")

        self._txt.configure(state="disabled")
        self._draw_map()
        self._status.set(f"{path.name}  —  {len(self._objects)} objects")

    def _open_in_explorer(self):
        if self._cur_path and self._cur_path.exists():
            os.startfile(str(self._cur_path.parent))

    # ── Object map ────────────────────────────────────────────────────────────

    def _draw_map(self):
        c = self._map_canvas
        c.delete("all")
        objs = self._objects
        cw = max(1, c.winfo_width())
        ch = max(1, c.winfo_height())

        if not objs:
            c.create_text(cw // 2, ch // 2, text="No CUBE objects in this script",
                          fill=FG_MUTED, font=("Segoe UI", 10))
            return

        pad = 24
        xs = [o["cx"] for o in objs]
        ys = [o["cy"] for o in objs]
        mn_x, mx_x = min(xs), max(xs)
        mn_y, mx_y = min(ys), max(ys)
        dx = max(mx_x - mn_x, 1)
        dy = max(mx_y - mn_y, 1)
        sx = (cw - pad * 2) / dx
        sy = (ch - pad * 2) / dy
        scale = min(sx, sy)

        def px(x): return int(pad + (x - mn_x) * scale)
        def py(y): return int(pad + (y - mn_y) * scale)

        # Grid
        steps_x = max(1, dx // 8)
        steps_y = max(1, dy // 6)
        for gx in range(int(mn_x), int(mx_x) + 1, steps_x):
            x = px(gx)
            c.create_line(x, pad, x, ch - pad, fill=BORDER, width=1)
            c.create_text(x, ch - pad + 8, text=str(gx),
                          fill=FG_MUTED, font=("Segoe UI", 6), anchor="n")
        for gy in range(int(mn_y), int(mx_y) + 1, steps_y):
            y = py(gy)
            c.create_line(pad, y, cw - pad, y, fill=BORDER, width=1)
            c.create_text(pad - 2, y, text=str(gy),
                          fill=FG_MUTED, font=("Segoe UI", 6), anchor="e")

        # Dots
        self._map_dots = []
        for o in objs:
            x, y = px(o["cx"]), py(o["cy"])
            r = 5
            c.create_oval(x - r, y - r, x + r, y + r,
                          fill=ACCENT2, outline=ACCENT, width=1)
            self._map_dots.append((x, y, o["name"]))

        self._map_info.config(
            text=f"x {mn_x}…{mx_x}  y {mn_y}…{mx_y}  |  {len(objs)} objects")

    def _on_map_hover(self, event):
        if not self._map_dots:
            return
        nearest = min(self._map_dots,
                      key=lambda t: (t[0] - event.x) ** 2 + (t[1] - event.y) ** 2)
        dist_sq = (nearest[0] - event.x) ** 2 + (nearest[1] - event.y) ** 2
        if dist_sq < 400:
            self._map_info.config(text=f"  ▸  {nearest[2]}")

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_all(self):
        import shutil
        dest = RENDERS_DIR / "AhkuilonScripts"
        dest.mkdir(parents=True, exist_ok=True)
        ok = 0
        for p in list(AHKUILON.glob("*.s")) + list(AHKUILON.glob("*.def")):
            try:
                shutil.copy2(str(p), str(dest / p.name))
                ok += 1
            except Exception:
                pass
        self._status.set(f"Exported {ok} scripts → {dest}")


# ═══════════════════════════════════════════════════════════════════════════════
#  SETTINGS DIALOG
# ═══════════════════════════════════════════════════════════════════════════════

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("RevEngine — Settings")
        self.configure(bg=BG_DARK)
        self.resizable(False, False)
        self.grab_set()
        self.transient(parent)

        self._game_var    = tk.StringVar(value=str(GAME_DIR))
        self._extract_var = tk.StringVar(value=str(EXTRACT_DIR))
        self._renders_var = tk.StringVar(value=str(RENDERS_DIR))

        frm = tk.Frame(self, bg=BG_DARK, padx=24, pady=16)
        frm.pack(fill="both", expand=True)

        def _browse(var):
            d = filedialog.askdirectory(initialdir=var.get())
            if d:
                var.set(d)

        def _row(label, var, row):
            tk.Label(frm, text=label, bg=BG_DARK, fg=FG_DIM,
                     font=("Segoe UI", 9), anchor="w").grid(
                row=row, column=0, columnspan=2, sticky="w", pady=(10, 2))
            tk.Entry(frm, textvariable=var, bg=BG_PANEL, fg=FG_TEXT,
                     insertbackground=FG_TEXT, relief="flat", width=54,
                     font=("Segoe UI", 9)).grid(
                row=row+1, column=0, sticky="ew", padx=(0, 6))
            tk.Button(frm, text="Browse…", bg=BG_MID, fg=FG_TEXT,
                      relief="flat", font=("Segoe UI", 9),
                      command=lambda v=var: _browse(v)).grid(
                row=row+1, column=1, sticky="ew")

        _row("Game Directory", self._game_var, 0)
        _row("Extract Directory", self._extract_var, 2)
        _row("Export Directory (renders)", self._renders_var, 4)

        frm.columnconfigure(0, weight=1)

        btn_bar = tk.Frame(self, bg=BG_DARK, padx=24, pady=12)
        btn_bar.pack(fill="x")
        tk.Button(btn_bar, text="Cancel", bg=BG_MID, fg=FG_TEXT, relief="flat",
                  font=("Segoe UI", 9), command=self.destroy).pack(side="right", padx=(8, 0))
        tk.Button(btn_bar, text="Save", bg=ACCENT, fg="#000000", relief="flat",
                  font=("Segoe UI", 9, "bold"), command=self._save).pack(side="right")

    def _save(self):
        global GAME_DIR, EXTRACT_DIR, RENDERS_DIR, IMAGERY, RESOURCES, AHKUILON
        global IMAGERY_ASSETS, THUMBNAILS, CHAR_DEF, WEAPON_DEF, ARMOR_DEF, SPELL_DEF
        GAME_DIR    = Path(self._game_var.get())
        RENDERS_DIR = Path(self._renders_var.get())
        new_extract = Path(self._extract_var.get())
        if new_extract != EXTRACT_DIR:
            EXTRACT_DIR   = new_extract
            IMAGERY       = EXTRACT_DIR / "imagery"
            RESOURCES     = EXTRACT_DIR / "resources"
            AHKUILON      = EXTRACT_DIR / "Ahkuilon"
            IMAGERY_ASSETS = IMAGERY / "Imagery"
            THUMBNAILS    = IMAGERY / "Thumbnails"
            CHAR_DEF      = IMAGERY  / "char.def"
            WEAPON_DEF    = IMAGERY  / "weapon.def"
            ARMOR_DEF     = IMAGERY  / "armor.def"
            SPELL_DEF     = RESOURCES / "spell.def"
        _save_config()
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════════
#  UPSCALE TAB
# ═══════════════════════════════════════════════════════════════════════════════

class UpscaleTab(tk.Frame):
    """Batch upscaler with per-asset results review, before/after compare, and redo."""

    # ── NVIDIA NIM FLUX text-to-image pipeline ────────────────────────────────
    # Endpoint: POST https://ai.api.nvidia.com/v1/genai/{model}
    # Response: {"artifacts": [{"base64": "..."}]}
    # Auth: NVIDIA_API_KEY in .env  (free key at build.nvidia.com)
    # NIM only accepts: prompt, width, height, seed — nothing else.
    # Valid dimensions (each axis must be from this list):
    #   768 832 896 960 1024 1088 1152 1216 1280 1344
    NIM_BASE_URL     = "https://ai.api.nvidia.com/v1/genai"
    NIM_MODEL        = "black-forest-labs/flux.1-schnell"   # fast batch
    NIM_MODEL_T2I    = "black-forest-labs/flux.1-dev"       # quality textures
    NIM_TEX_SIZE     = 1024
    NIM_VALID_SIZES  = (768, 832, 896, 960, 1024, 1088, 1152, 1216, 1280, 1344)
    DEFAULT_PROMPT   = (
        "retro fantasy RPG game asset, epic heroic lighting, "
        "rich color depth, sharp pixel-art detail, cinematic glow, "
        "dark fantasy atmosphere"
    )
    # Texture-specific prompt — prepended when generating model textures
    DEFAULT_TEX_PROMPT = (
        "4K PBR game texture, dark fantasy RPG character, physically based "
        "rendering, high detail surface material, ultra sharp, seamless, "
        "subsurface scattering, specular highlights, normal map detail"
    )
    DEFAULT_NEG      = (
        "blurry, low quality, dithering artifacts, washed out, flat, "
        "oversaturated, deformed, extra limbs, watermark"
    )
    _SMALL_PX        = 32   # sprites ≤ this skip FLUX → NEAREST resize
    _THUMB_PX        = 56   # thumbnail size in the results list
    _STATUS_COLORS = {"ok": ACCENT3, "flagged": "#f59e0b", "failed": RED}

    def __init__(self, parent, status: StatusBar):
        super().__init__(parent, bg=BG_MID)
        self._status   = status
        self._stop     = False
        self._running  = False
        self._results: List[Dict] = []
        self._result_phs: List    = []   # PhotoImage refs — prevent GC
        self._sel_idx: Optional[int] = None
        self._redo_queue: List[int]  = []
        self._redo_chain = False
        self._ffmpeg_path: str = self._detect_ffmpeg() or ""
        self._build_ui()
        self.after(600, self._refresh_counts)

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Top toolbar
        bar = tk.Frame(self, bg=BG_DARK, pady=5)
        bar.pack(fill="x")
        tk.Label(bar, text="Asset Upscaler", bg=BG_DARK, fg=ACCENT,
                 font=("Segoe UI", 11, "bold")).pack(side="left", padx=10)

        self._stop_btn = tk.Button(bar, text="Stop", bg=RED, fg="#fff",
                                   relief="flat", font=("Segoe UI", 9, "bold"),
                                   padx=10, command=self._stop_upscale,
                                   state="disabled")
        self._stop_btn.pack(side="right", padx=4)

        self._start_btn = tk.Button(bar, text="Start Upscale", bg=ACCENT3,
                                    fg="#000", relief="flat",
                                    font=("Segoe UI", 9, "bold"), padx=12,
                                    command=self._start_upscale)
        self._start_btn.pack(side="right", padx=4)

        tk.Label(bar, text="Scale:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 9)).pack(side="right", padx=(10, 2))
        self._scale_var = tk.StringVar(value="4")
        ttk.Combobox(bar, textvariable=self._scale_var, values=["2", "4"],
                     state="readonly", width=3).pack(side="right")

        # NIM strength/label hidden — pipeline uses Real-ESRGAN ncnn
        self._strength_var = tk.StringVar(value="0.65")

        # Horizontal split: left (categories) | right (results + compare)
        pane = tk.PanedWindow(self, orient="horizontal", bg=BG_DARK, sashwidth=4)
        pane.pack(fill="both", expand=True)

        # ── Left: category checklist ─────────────────────────────────────────
        left = tk.Frame(pane, bg=BG_PANEL, width=270)
        pane.add(left, minsize=200)
        tk.Label(left, text="Categories", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(8, 4))

        self._cats = {}
        for key, label in [("ui_panels",      "UI Panels"),
                            ("equip_icons",    "Equipment Icons"),
                            ("talisman_icons", "Talisman Icons"),
                            ("model_textures", "Model Textures"),
                            ("sprites",        "Sprites (clean)"),
                            ("cinematix",      "Cinematix  (SMK→MP4)")]:
            row = tk.Frame(left, bg=BG_PANEL)
            row.pack(fill="x", padx=8, pady=2)
            var = tk.BooleanVar(value=(key not in ("sprites", "cinematix")))
            tk.Checkbutton(row, variable=var, text=label,
                           bg=BG_PANEL, fg=FG_TEXT, selectcolor=BG_CARD,
                           activebackground=BG_PANEL, activeforeground=FG_TEXT,
                           font=("Segoe UI", 9), anchor="w").pack(side="left", fill="x", expand=True)
            cnt = tk.Label(row, text="…", bg=BG_PANEL, fg=FG_DIM, font=("Segoe UI", 8))
            cnt.pack(side="right", padx=4)
            tk.Button(row, text="▶1", bg=BG_CARD, fg=ACCENT2, relief="flat",
                      font=("Segoe UI", 7, "bold"), padx=3, pady=0,
                      cursor="hand2",
                      command=lambda k=key: self._test_single(k)).pack(side="right", padx=(0, 2))
            self._cats[key] = (var, cnt)

        # FFmpeg section (required for Cinematix)
        tk.Frame(left, bg=BORDER, height=1).pack(fill="x", padx=8, pady=(6, 2))
        ff_hdr = tk.Frame(left, bg=BG_PANEL)
        ff_hdr.pack(fill="x", padx=8, pady=(2, 0))
        tk.Label(ff_hdr, text="FFmpeg", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        self._ffmpeg_status_lbl = tk.Label(ff_hdr, bg=BG_PANEL,
                                            font=("Segoe UI", 8, "bold"))
        self._ffmpeg_status_lbl.pack(side="left", padx=4)

        ff_btns = tk.Frame(left, bg=BG_PANEL)
        ff_btns.pack(fill="x", padx=8, pady=1)
        self._install_btn = tk.Button(ff_btns, text="Install to project",
                                      bg=ACCENT2, fg="#000", relief="flat",
                                      font=("Segoe UI", 8, "bold"), padx=6,
                                      command=self._install_ffmpeg)
        self._install_btn.pack(side="left")
        tk.Button(ff_btns, text="Browse", bg=BG_CARD, fg=FG_TEXT,
                  relief="flat", font=("Segoe UI", 8), padx=4,
                  command=self._browse_ffmpeg).pack(side="left", padx=4)

        self._ffmpeg_path_var = tk.StringVar(value=self._ffmpeg_path)
        tk.Entry(left, textvariable=self._ffmpeg_path_var, bg=BG_CARD, fg=FG_DIM,
                 font=("Consolas", 7), relief="flat",
                 insertbackground=FG_TEXT).pack(fill="x", padx=8, pady=(1, 4))
        self._ffmpeg_path_var.trace_add("write",
                                         lambda *_: self._on_ffmpeg_path_changed())
        self._update_ffmpeg_status()

        tk.Frame(left, bg=BORDER, height=1).pack(fill="x", padx=8, pady=(2, 4))

        # ── Real-ESRGAN ncnn (video upscaler) ────────────────────────────────
        ncnn_hdr = tk.Frame(left, bg=BG_PANEL)
        ncnn_hdr.pack(fill="x", padx=8, pady=(2, 0))
        tk.Label(ncnn_hdr, text="Real-ESRGAN (Video)", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 8, "bold")).pack(side="left")
        self._ncnn_status_lbl = tk.Label(ncnn_hdr, bg=BG_PANEL,
                                          font=("Segoe UI", 8, "bold"))
        self._ncnn_status_lbl.pack(side="left", padx=4)

        ncnn_btns = tk.Frame(left, bg=BG_PANEL)
        ncnn_btns.pack(fill="x", padx=8, pady=1)
        self._ncnn_install_btn = tk.Button(
            ncnn_btns, text="Install to project",
            bg=ACCENT2, fg="#000", relief="flat",
            font=("Segoe UI", 8, "bold"), padx=6,
            command=self._install_ncnn)
        self._ncnn_install_btn.pack(side="left")

        ncnn_model_row = tk.Frame(left, bg=BG_PANEL)
        ncnn_model_row.pack(fill="x", padx=8, pady=(2, 1))
        tk.Label(ncnn_model_row, text="Model:", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(side="left")
        self._ncnn_model_var = tk.StringVar(value="realesrgan-x4plus-anime")
        ttk.Combobox(ncnn_model_row, textvariable=self._ncnn_model_var,
                     values=["realesrgan-x4plus-anime", "realesrgan-x4plus",
                             "realesrnet-x4plus"],
                     state="readonly", width=22).pack(side="left", padx=(4, 0))
        self._update_ncnn_status()

        # Frame step: how often to apply FLUX/ncnn (every N frames; gaps use LANCZOS)
        step_row = tk.Frame(left, bg=BG_PANEL)
        step_row.pack(fill="x", padx=8, pady=(2, 1))
        tk.Label(step_row, text="FLUX every N frames:", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(side="left")
        self._cine_step_var = tk.StringVar(value="4")
        ttk.Combobox(step_row, textvariable=self._cine_step_var,
                     values=["1", "2", "4", "8", "16"],
                     state="readonly", width=4).pack(side="left", padx=(4, 0))
        tk.Label(step_row, text="(1=all, 16=fast)", bg=BG_PANEL, fg=FG_MUTED,
                 font=("Segoe UI", 7)).pack(side="left", padx=4)

        tk.Frame(left, bg=BORDER, height=1).pack(fill="x", padx=8, pady=(4, 4))

        # ── NIM text-to-image (future) ────────────────────────────────────────
        tk.Label(left,
                 text="NIM text-to-image: coming soon",
                 bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 8, "italic")).pack(anchor="w", padx=10, pady=(2, 1))
        tk.Label(left,
                 text="Prompt-driven regeneration will replace ESRGAN\n"
                      "once NVIDIA exposes img2img endpoints.",
                 bg=BG_PANEL, fg=FG_MUTED,
                 font=("Segoe UI", 7), justify="left").pack(anchor="w", padx=10, pady=(0, 4))

        # Hidden Text widgets — kept so _get_prompt()/_get_neg() work when NIM re-enables
        self._prompt_txt = tk.Text(left, height=3, font=("Segoe UI", 8))
        self._prompt_txt.insert("1.0", self.DEFAULT_PROMPT)
        self._neg_txt = tk.Text(left, height=2, font=("Segoe UI", 8))
        self._neg_txt.insert("1.0", self.DEFAULT_NEG)
        self._key_lbl = tk.Label(left, text="", bg=BG_PANEL)

        tk.Frame(left, bg=BORDER, height=1).pack(fill="x", padx=8, pady=(2, 8))
        tk.Label(left, text="Output", bg=BG_PANEL, fg=FG_DIM,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10)
        self._out_lbl = tk.Label(left, text="", bg=BG_PANEL, fg=FG_DIM,
                                 font=("Segoe UI", 8), wraplength=230, justify="left")
        self._out_lbl.pack(anchor="w", padx=10, pady=2)
        tk.Button(left, text="Open Folder", bg=BG_CARD, fg=FG_TEXT,
                  relief="flat", font=("Segoe UI", 8), padx=6,
                  command=self._open_output).pack(anchor="w", padx=10, pady=2)

        # ── Right: progress + results + compare ──────────────────────────────
        right = tk.Frame(pane, bg=BG_DARK)
        pane.add(right, minsize=500)

        # Progress strip
        prog_strip = tk.Frame(right, bg=BG_DARK, pady=3)
        prog_strip.pack(fill="x", padx=10, side="top")
        self._prog_lbl = tk.Label(prog_strip, text="Idle", bg=BG_DARK, fg=FG_DIM,
                                   font=("Segoe UI", 9))
        self._prog_lbl.pack(anchor="w")
        self._prog = ttk.Progressbar(prog_strip, orient="horizontal", mode="determinate")
        self._prog.pack(fill="x", pady=2)

        # System log (3 lines — errors, weights download status)
        self._log = tk.Text(right, bg=BG_DARK, fg=FG_DIM, font=("Consolas", 8),
                            height=3, wrap="none", state="disabled",
                            relief="flat", borderwidth=0, pady=1)
        self._log.pack(fill="x", padx=10, side="top")

        # Vertical pane: results list (top) | compare+redo (bottom)
        v_pane = tk.PanedWindow(right, orient="vertical", bg=BG_DARK, sashwidth=5)
        v_pane.pack(fill="both", expand=True)

        # ── Results list ──────────────────────────────────────────────────────
        res_outer = tk.Frame(v_pane, bg=BG_PANEL)
        v_pane.add(res_outer, minsize=120)

        res_hdr = tk.Frame(res_outer, bg=BG_MID, pady=3)
        res_hdr.pack(fill="x")
        tk.Label(res_hdr, text="Results", bg=BG_MID, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=8)
        self._res_count_lbl = tk.Label(res_hdr, text="0 items", bg=BG_MID, fg=FG_DIM,
                                       font=("Segoe UI", 8))
        self._res_count_lbl.pack(side="left", padx=4)
        tk.Button(res_hdr, text="Redo Flagged", bg=ACCENT, fg="#000",
                  relief="flat", font=("Segoe UI", 8, "bold"), padx=6,
                  command=self._redo_flagged).pack(side="right", padx=4)
        tk.Button(res_hdr, text="Clear", bg=BG_CARD, fg=FG_DIM,
                  relief="flat", font=("Segoe UI", 8), padx=6,
                  command=self._clear_results).pack(side="right", padx=4)

        # Column header row
        hdr = tk.Frame(res_outer, bg=BG_CARD, pady=2)
        hdr.pack(fill="x")
        for txt, anchor, expand, px in [
            ("Before/After", "w", False, (4, 2)),
            ("Name", "w", True, (2, 2)),
            ("Dimensions", "w", False, (2, 2)),
            ("Status", "center", False, (2, 4)),
            ("Actions", "center", False, (2, 8)),
        ]:
            tk.Label(hdr, text=txt, bg=BG_CARD, fg=FG_DIM,
                     font=("Segoe UI", 8, "bold"), anchor=anchor).pack(
                side="left", padx=px, fill="x" if expand else None, expand=expand)

        # Scrollable canvas for result cards
        res_body = tk.Frame(res_outer, bg=BG_PANEL)
        res_body.pack(fill="both", expand=True)
        self._res_canvas = tk.Canvas(res_body, bg=BG_PANEL, highlightthickness=0)
        res_sb = ttk.Scrollbar(res_body, orient="vertical", command=self._res_canvas.yview)
        res_sb.pack(side="right", fill="y")
        self._res_canvas.pack(side="left", fill="both", expand=True)
        self._res_canvas.configure(yscrollcommand=res_sb.set)

        self._results_inner = tk.Frame(self._res_canvas, bg=BG_PANEL)
        self._res_win = self._res_canvas.create_window((0, 0), window=self._results_inner,
                                                        anchor="nw")

        def _on_inner_cfg(e):
            self._res_canvas.configure(scrollregion=self._res_canvas.bbox("all"))

        def _on_canvas_cfg(e):
            self._res_canvas.itemconfig(self._res_win, width=self._res_canvas.winfo_width())

        self._results_inner.bind("<Configure>", _on_inner_cfg)
        self._res_canvas.bind("<Configure>", _on_canvas_cfg)
        self._res_canvas.bind("<MouseWheel>",
                              lambda e: self._res_canvas.yview_scroll(
                                  int(-1 * (e.delta / 120)), "units"))

        # ── Compare & Redo panel ──────────────────────────────────────────────
        cmp_outer = tk.Frame(v_pane, bg=BG_DARK)
        v_pane.add(cmp_outer, minsize=200)

        cmp_hdr = tk.Frame(cmp_outer, bg=BG_MID, pady=3)
        cmp_hdr.pack(fill="x")
        tk.Label(cmp_hdr, text="Compare & Redo", bg=BG_MID, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=8)
        self._cmp_name_lbl = tk.Label(cmp_hdr, text="Select a result above",
                                      bg=BG_MID, fg=FG_DIM, font=("Segoe UI", 9))
        self._cmp_name_lbl.pack(side="left", padx=8)

        cmp_body = tk.Frame(cmp_outer, bg=BG_DARK)
        cmp_body.pack(fill="both", expand=True)

        before_col = tk.Frame(cmp_body, bg=BG_DARK)
        before_col.pack(side="left", fill="both", expand=True, padx=(6, 3), pady=4)
        tk.Label(before_col, text="Before (original)", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(anchor="w")
        self._cmp_before = tk.Canvas(before_col, bg=BG_PANEL, highlightthickness=1,
                                      highlightbackground=BORDER)
        self._cmp_before.pack(fill="both", expand=True)

        after_col = tk.Frame(cmp_body, bg=BG_DARK)
        after_col.pack(side="left", fill="both", expand=True, padx=(3, 6), pady=4)
        tk.Label(after_col, text="After (upscaled)", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(anchor="w")
        self._cmp_after = tk.Canvas(after_col, bg=BG_PANEL, highlightthickness=1,
                                     highlightbackground=BORDER)
        self._cmp_after.pack(fill="both", expand=True)

        # Redo params bar
        params_bar = tk.Frame(cmp_outer, bg=BG_MID, pady=4)
        params_bar.pack(fill="x", side="bottom")

        tk.Label(params_bar, text="Strength:", bg=BG_MID, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(side="left", padx=(8, 2))
        self._redo_strength_var = tk.StringVar(value="0.65")
        ttk.Combobox(params_bar, textvariable=self._redo_strength_var,
                     values=["0.45", "0.55", "0.65", "0.75", "0.85"],
                     state="readonly", width=6).pack(side="left")

        tk.Label(params_bar, text="Scale:", bg=BG_MID, fg=FG_DIM,
                 font=("Segoe UI", 8)).pack(side="left", padx=(8, 2))
        self._redo_scale_var = tk.StringVar(value="4")
        ttk.Combobox(params_bar, textvariable=self._redo_scale_var,
                     values=["2", "4"], state="readonly", width=3).pack(side="left")

        tk.Button(params_bar, text="Open File", bg=BG_CARD, fg=FG_TEXT,
                  relief="flat", font=("Segoe UI", 8), padx=6,
                  command=self._open_selected).pack(side="right", padx=4)
        self._flag_btn = tk.Button(params_bar, text="Flag", bg="#f59e0b", fg="#000",
                                   relief="flat", font=("Segoe UI", 8, "bold"), padx=6,
                                   command=self._toggle_flag)
        self._flag_btn.pack(side="right", padx=4)
        tk.Button(params_bar, text="Redo This", bg=ACCENT3, fg="#000",
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=10,
                  command=self._redo_selected).pack(side="right", padx=4)

    # ── Basic helpers ─────────────────────────────────────────────────────────

    def _log_line(self, text: str):
        self._log.config(state="normal")
        self._log.insert("end", text + "\n")
        self._log.see("end")
        self._log.config(state="disabled")

    def _set_progress(self, done: int, total: int, msg: str = ""):
        self._prog["value"] = (done / total * 100) if total else 0
        self._prog_lbl.config(text=f"{msg}  {done}/{total}" if msg else f"{done}/{total}")

    def _open_output(self):
        out = RENDERS_DIR / "upscaled"
        if out.exists():
            os.startfile(str(out))

    def _refresh_counts(self):
        self._out_lbl.config(text=str(RENDERS_DIR / "upscaled"))
        ui_n  = sum(1 for _ in RESOURCES.glob("*.dat")) if RESOURCES.exists() else 0
        eq_n  = len(list((THUMBNAILS / "Equip").glob("*.tn"))) if (THUMBNAILS / "Equip").exists() else 0
        tal_n = len(list((THUMBNAILS / "Magic").glob("*.tn"))) if (THUMBNAILS / "Magic").exists() else 0
        i3d_n = len(list(IMAGERY_ASSETS.rglob("*.i3d"))) if IMAGERY_ASSETS.exists() else 0
        i2d_n = len(list(IMAGERY_ASSETS.rglob("*.i2d"))) if IMAGERY_ASSETS.exists() else 0
        smk_n = len(self._find_smk_files())
        self._cats["ui_panels"][1].config(text=f"{ui_n} files")
        self._cats["equip_icons"][1].config(text=f"{eq_n} icons")
        self._cats["talisman_icons"][1].config(text=f"{tal_n} icons")
        self._cats["model_textures"][1].config(text=f"{i3d_n} models")
        self._cats["sprites"][1].config(text=f"{i2d_n} sprites")
        self._cats["cinematix"][1].config(text=f"{smk_n} SMK")

    # ── Results management ────────────────────────────────────────────────────

    def _add_result(self, r: Dict):
        """Append a result card to the scrollable list. Called on main thread."""
        from PIL import ImageTk, Image as PILImage
        idx    = len(self._results)
        r["idx"] = idx
        self._results.append(r)

        row_bg = BG_PANEL if idx % 2 == 0 else BG_CARD
        row = tk.Frame(self._results_inner, bg=row_bg, pady=1, cursor="hand2")
        row.pack(fill="x")
        r["row_frame"] = row

        # Before thumbnail
        if r.get("before_pil"):
            ph_b = ImageTk.PhotoImage(r["before_pil"])
            self._result_phs.append(ph_b)
            tk.Label(row, image=ph_b, bg=row_bg, bd=0).pack(side="left", padx=(4, 0))
        else:
            tk.Label(row, text="  —  ", bg=row_bg, fg=FG_DIM,
                     font=("Segoe UI", 8), width=7).pack(side="left")

        tk.Label(row, text="→", bg=row_bg, fg=FG_DIM,
                 font=("Segoe UI", 9)).pack(side="left", padx=2)

        # After thumbnail
        if r.get("after_pil"):
            ph_a = ImageTk.PhotoImage(r["after_pil"])
            self._result_phs.append(ph_a)
            tk.Label(row, image=ph_a, bg=row_bg, bd=0).pack(side="left", padx=(0, 6))
        else:
            tk.Label(row, text="  —  ", bg=row_bg, fg=FG_DIM,
                     font=("Segoe UI", 8), width=7).pack(side="left")

        # Name + category
        tk.Label(row, text=f"[{r['cat']}]  {r['name']}", bg=row_bg, fg=FG_TEXT,
                 font=("Consolas", 8), anchor="w").pack(side="left", padx=4,
                                                         fill="x", expand=True)

        # Dimensions
        src_w, src_h = r.get("src_size", (0, 0))
        out_w, out_h = r.get("out_size", (0, 0))
        dims = f"{src_w}×{src_h}→{out_w}×{out_h}" if out_w else f"{src_w}×{src_h}"
        tk.Label(row, text=dims, bg=row_bg, fg=FG_DIM,
                 font=("Segoe UI", 8), width=16).pack(side="left", padx=2)

        # Status badge
        sl = tk.Label(row, text=r["status"].upper(), fg=self._STATUS_COLORS.get(r["status"], FG_DIM),
                      bg=row_bg, font=("Segoe UI", 8, "bold"), width=7)
        sl.pack(side="left", padx=4)
        r["status_lbl"] = sl

        # Action buttons
        tk.Button(row, text="Flag", bg=row_bg, fg="#f59e0b", relief="flat",
                  font=("Segoe UI", 8), padx=3,
                  command=lambda i=idx: self._flag_result(i)).pack(side="right", padx=2)
        tk.Button(row, text="Redo", bg=row_bg, fg=ACCENT2, relief="flat",
                  font=("Segoe UI", 8), padx=3,
                  command=lambda i=idx: self._redo_result(i)).pack(side="right", padx=2)

        # Click row → compare panel
        row.bind("<Button-1>", lambda e, i=idx: self._select_result(i))

        self._res_count_lbl.config(text=f"{len(self._results)} items")
        self._res_canvas.yview_moveto(1.0)

    def _select_result(self, idx: int):
        """Load result into the compare panel and sync redo params."""
        from PIL import Image as PILImage
        if idx >= len(self._results):
            return
        r = self._results[idx]
        self._sel_idx = idx

        # Highlight selected row (deselect others)
        for i, res in enumerate(self._results):
            bg = ACCENT2 if i == idx else (BG_PANEL if i % 2 == 0 else BG_CARD)
            rf = res.get("row_frame")
            if rf:
                try:
                    rf.config(bg=bg)
                    for w in rf.winfo_children():
                        w.config(bg=bg)
                except Exception:
                    pass

        self._cmp_name_lbl.config(text=f"{r['cat']} / {r['name']}")
        p = r.get("params", {})
        self._redo_strength_var.set(str(p.get("strength", "0.65")))
        self._redo_scale_var.set(str(p.get("scale", 4)))
        self._flag_btn.config(text="Unflag" if r["status"] == "flagged" else "Flag")

        # Load full-size images for compare (re-decode source, load output from disk)
        before_img = None
        try:
            fn = r.get("decode_fn")
            if fn:
                before_img = fn()
        except Exception:
            pass

        after_img = None
        try:
            op = r.get("out_path")
            if op and op.exists():
                after_img = PILImage.open(str(op))
        except Exception:
            pass

        self.after(10, lambda: self._draw_compare(self._cmp_before, before_img))
        self.after(10, lambda: self._draw_compare(self._cmp_after,  after_img))

    def _draw_compare(self, canvas: tk.Canvas, img):
        """Fit img into canvas, preserving aspect ratio. Up to 8x magnification."""
        from PIL import ImageTk, Image as PILImage
        canvas.delete("all")
        if img is None:
            canvas.create_text(max(canvas.winfo_width() // 2, 60), 40,
                               text="No image", fill=FG_DIM, font=("Segoe UI", 9))
            return
        cw = canvas.winfo_width()  or 300
        ch = canvas.winfo_height() or 200
        scale = min(cw / img.width, ch / img.height, 8.0)
        nw = max(1, int(img.width  * scale))
        nh = max(1, int(img.height * scale))
        display = img.resize((nw, nh), PILImage.NEAREST if scale > 1 else PILImage.LANCZOS)
        ph = ImageTk.PhotoImage(display)
        self._result_phs.append(ph)
        canvas.create_image(cw // 2, ch // 2, image=ph, anchor="center")

    def _flag_result(self, idx: int):
        r = self._results[idx]
        new_s = "ok" if r["status"] == "flagged" else "flagged"
        r["status"] = new_s
        r["status_lbl"].config(text=new_s.upper(), fg=self._STATUS_COLORS[new_s])
        if self._sel_idx == idx:
            self._flag_btn.config(text="Unflag" if new_s == "flagged" else "Flag")

    def _toggle_flag(self):
        if self._sel_idx is not None:
            self._flag_result(self._sel_idx)

    def _open_selected(self):
        if self._sel_idx is not None:
            p = self._results[self._sel_idx].get("out_path")
            if p and p.exists():
                os.startfile(str(p))

    def _clear_results(self):
        for w in self._results_inner.winfo_children():
            w.destroy()
        self._results.clear()
        self._result_phs.clear()
        self._sel_idx = None
        self._res_count_lbl.config(text="0 items")
        self._cmp_name_lbl.config(text="Select a result above")
        self._cmp_before.delete("all")
        self._cmp_after.delete("all")

    def _rebuild_card(self, idx: int):
        """Destroy and re-add a result card in-place after a redo."""
        r = self._results[idx]
        rf = r.get("row_frame")
        if rf:
            rf.destroy()
        # Temporarily remove from list so _add_result appends at end
        saved = self._results.pop(idx)
        # Re-insert at same slot
        self._results.insert(idx, saved)
        # Rebuild: destroy inner and recreate all cards
        for w in self._results_inner.winfo_children():
            w.destroy()
        all_results = list(self._results)
        self._results.clear()
        self._result_phs.clear()
        for res in all_results:
            self._add_result(res)

    # ── Single-file test ─────────────────────────────────────────────────────

    def _find_first_file(self, cat: str):
        """Return (cat, decode_fn, out_path) for first decodable asset, or None."""
        out_root = RENDERS_DIR / "upscaled"

        if cat == "ui_panels" and RESOURCES.exists():
            for dat in sorted(RESOURCES.glob("*.dat")):
                try:
                    raw = dat.read_bytes()
                    if len(raw) >= 20 and raw[:4] == b"CGSR":
                        return (cat,
                                lambda p=dat: _decode_dat_frame(p, 0),
                                out_root / cat / f"{dat.stem}_f0.png")
                except Exception:
                    pass

        elif cat == "equip_icons":
            eq_dir = THUMBNAILS / "Equip"
            if eq_dir.exists():
                for tn in sorted(eq_dir.glob("*.tn")):
                    return (cat,
                            lambda p=tn: self._tn_to_image(p),
                            out_root / cat / f"{tn.stem}.png")

        elif cat == "talisman_icons":
            mag_dir = THUMBNAILS / "Magic"
            if mag_dir.exists():
                for tn in sorted(mag_dir.glob("*.tn")):
                    return (cat,
                            lambda p=tn: self._tn_to_image(p),
                            out_root / cat / f"{tn.stem}.png")

        elif cat == "model_textures" and IMAGERY_ASSETS.exists():
            from decoders.i3d import decode_i3d_textures
            for i3d in sorted(IMAGERY_ASSETS.rglob("*.i3d")):
                try:
                    textures = decode_i3d_textures(i3d)
                    for ti, tex in enumerate(textures):
                        if tex is not None:
                            return (cat,
                                    lambda p=i3d, n=ti: self._decode_i3d_texture_n(p, n),
                                    out_root / cat / f"{i3d.stem}_t{ti}.png")
                except Exception:
                    pass

        elif cat == "sprites" and IMAGERY_ASSETS.exists():
            for i2d in sorted(IMAGERY_ASSETS.rglob("*.i2d")):
                return (cat,
                        lambda p=i2d: self._decode_sprite_safe(p),
                        out_root / cat / f"{i2d.stem}.png")

        elif cat == "cinematix":
            smks = self._find_smk_files()
            if smks:
                return (cat, None, smks[0])   # SMK handled separately in _test_single

        return None

    def _test_single(self, cat: str):
        """Upscale the first available file in *cat* and show it in the results list."""
        if self._running:
            self._status.set("Wait for current batch to finish")
            return

        job = self._find_first_file(cat)
        if job is None:
            self._status.set(f"No {cat} files found — check game directory")
            return

        cat, decode_fn, path = job
        scale    = int(self._scale_var.get())
        strength = float(self._strength_var.get())
        prompt   = self._get_prompt()
        neg      = self._get_neg()

        self._stop    = False
        self._running = True
        self._start_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")
        self._prog["value"] = 0
        self._prog_lbl.config(text=f"Testing {cat}…")

        def _worker():
            try:
                self.after(0, self._log_line,
                           f"[TEST {cat}]  {Path(path).name if cat == 'cinematix' else Path(path).name}")

                if cat == "cinematix":
                    ff = self._ffmpeg_path_var.get().strip()
                    if not ff:
                        self.after(0, self._log_line, "  Cinematix test skipped — FFmpeg not set")
                        return
                    out_root = RENDERS_DIR / "upscaled"
                    result = self._process_smk(path, scale, strength, prompt, neg, out_root)
                    if result:
                        self.after(0, self._add_result, result)
                    self.after(0, self._log_line, "  Cinematix test done")
                    return

                img = decode_fn()
                if img is None:
                    self.after(0, self._log_line, "  decode returned None — asset may be empty")
                    return

                self.after(0, self._log_line,
                           f"  source {img.width}×{img.height}  mode={img.mode}")

                out_path = Path(path)
                out_path.parent.mkdir(parents=True, exist_ok=True)

                up = self._upscale_with_ncnn(img, scale)
                up.save(str(out_path), format="PNG")

                self.after(0, self._log_line,
                           f"  → {up.width}×{up.height}  saved: {out_path.name}")
                self.after(0, self._add_result, {
                    "name":      out_path.stem,
                    "cat":       cat,
                    "decode_fn": decode_fn,
                    "out_path":  out_path,
                    "src_size":  (img.width, img.height),
                    "out_size":  (up.width,  up.height),
                    "before_pil": self._make_thumb(img),
                    "after_pil":  self._make_thumb(up),
                    "status":    "ok",
                    "params":    {"strength": strength, "scale": scale, "prompt": prompt},
                })
            except Exception as exc:
                import traceback
                self.after(0, self._log_line, f"  FAILED: {exc}")
                self.after(0, self._log_line, traceback.format_exc()[-600:])
            finally:
                self.after(0, self._on_done)

        threading.Thread(target=_worker, daemon=True).start()

    # ── Batch pipeline ────────────────────────────────────────────────────────

    def _start_upscale(self):
        if self._running:
            return
        selected = [k for k, (v, _) in self._cats.items() if v.get()]
        if not selected:
            self._status.set("Select at least one category")
            return
        self._stop    = False
        self._running = True
        self._start_btn.config(state="disabled")
        self._stop_btn.config(state="normal")
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")
        self._prog["value"] = 0
        scale    = int(self._scale_var.get())
        strength = float(self._strength_var.get())
        prompt   = self._get_prompt()
        neg      = self._get_neg()
        threading.Thread(target=self._pipeline_worker,
                         args=(selected, scale, strength, prompt, neg), daemon=True).start()

    def _stop_upscale(self):
        self._stop = True
        self._status.set("Stopping after current asset…")

    def _pipeline_worker(self, selected: List[str], scale: int,
                          strength: float, prompt: str, neg: str):
        try:
            self._run_pipeline(selected, scale, strength, prompt, neg)
        except Exception as exc:
            self.after(0, self._log_line, f"FATAL: {exc}")
        finally:
            self.after(0, self._on_done)

    def _on_done(self):
        self._running = False
        self._start_btn.config(state="normal")
        self._stop_btn.config(state="disabled")
        self._prog["value"] = 100
        self._prog_lbl.config(text="Done")
        self._status.set("Upscale complete.")
        if self._redo_chain:
            self._redo_chain = False
            self._process_redo_queue()

    # ── Core worker ──────────────────────────────────────────────────────────

    def _snap_nim_size(self, px: int) -> int:
        """Snap px to the nearest allowed NIM dimension."""
        return min(self.NIM_VALID_SIZES, key=lambda s: abs(s - px))

    def _nim_generate(self, model: str, prompt: str, width: int, height: int,
                      seed: int = -1):
        """POST to NVIDIA NIM genai endpoint; return PIL RGBA image.

        NIM FLUX only accepts: prompt, width, height, seed.
        Width/height must each be in NIM_VALID_SIZES.
        Raises RuntimeError with the full API error body on failure.
        """
        import base64, io, requests as req
        from PIL import Image as PILImage

        api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "NVIDIA_API_KEY not set — add it to .env"
            )
        url     = f"{self.NIM_BASE_URL}/{model}"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
            "Accept":        "application/json",
        }
        payload = {
            "prompt": prompt,
            "width":  self._snap_nim_size(width),
            "height": self._snap_nim_size(height),
        }
        if seed >= 0:
            payload["seed"] = seed
        r = req.post(url, headers=headers, json=payload, timeout=180)
        if not r.ok:
            raise RuntimeError(
                f"NIM {r.status_code}: {r.text[:400]}"
            )
        b64 = r.json()["artifacts"][0]["base64"]
        return PILImage.open(io.BytesIO(base64.b64decode(b64))).convert("RGBA")

    def _upscale_with_ncnn(self, img, scale: int):
        """
        Upscale a PIL image with Real-ESRGAN-ncnn-vulkan (Vulkan — works on Intel UHD).
        Falls back to PIL LANCZOS if the binary is not installed.
        """
        import subprocess, tempfile
        from PIL import Image as PILImage

        ncnn_exe = self._detect_ncnn()
        if not ncnn_exe:
            # Soft fallback — better than failing; user sees clean LANCZOS until ncnn installed
            w, h = img.width * scale, img.height * scale
            return img.resize((w, h), PILImage.LANCZOS)

        ncnn_model = self._ncnn_model_var.get()
        with tempfile.TemporaryDirectory(prefix="revengine_up_") as tmp:
            src = Path(tmp) / "src.png"
            out = Path(tmp) / "out.png"
            img.convert("RGBA").save(str(src))
            r = subprocess.run(
                [ncnn_exe,
                 "-i", str(src),
                 "-o", str(out),
                 "-n", ncnn_model,
                 "-s", str(scale),
                 "-f", "png",
                 "-g", "0"],
                capture_output=True, text=True, timeout=120,
            )
            if r.returncode != 0:
                raise RuntimeError(f"ncnn: {r.stderr[-300:]}")
            return PILImage.open(str(out)).convert("RGBA")

    def _enhance_with_flux(self, img, strength: float, prompt: str,
                            neg_prompt: str, scale: int):
        """
        Enhance one PIL Image via NVIDIA NIM FLUX.1-schnell (text-to-image).

        Tiny sprites (≤ _SMALL_PX) bypass FLUX → NEAREST resize.
        All others: snap target dims to nearest NIM-valid size.
        """
        from PIL import Image as PILImage

        if img.width <= self._SMALL_PX or img.height <= self._SMALL_PX:
            return img.resize((img.width * scale, img.height * scale), PILImage.NEAREST)

        tw = self._snap_nim_size(img.width  * scale)
        th = self._snap_nim_size(img.height * scale)

        return self._nim_generate(
            model  = self.NIM_MODEL,
            prompt = prompt,
            width  = tw,
            height = th,
        )

    def _generate_texture_flux(self, img, asset_stem: str,
                                user_prompt: str, neg_prompt: str):
        """
        Generate a 1024×1024 PBR texture via FLUX.1-dev text-to-image.

        Source textures are 64–256px RGB565 with no recoverable detail.
        Character name is derived from asset_stem ("locke_t0" → "locke").
        """
        clean = re.sub(r"[_\-]t\d+$", "", asset_stem)
        clean = clean.replace("_", " ").replace("-", " ")
        tex_prompt = (
            f"{self.DEFAULT_TEX_PROMPT}, character: {clean}. "
            f"{user_prompt}"
        )
        return self._nim_generate(
            model  = self.NIM_MODEL_T2I,
            prompt = tex_prompt,
            width  = self.NIM_TEX_SIZE,
            height = self.NIM_TEX_SIZE,
        )

    def _scale_pil_fast(self, img, scale: int):
        """Fast PIL resize for video frames (no API call)."""
        from PIL import Image as PILImage
        if img.width <= self._SMALL_PX or img.height <= self._SMALL_PX:
            return img.resize((img.width * scale, img.height * scale), PILImage.NEAREST)
        return img.resize((img.width * scale, img.height * scale), PILImage.LANCZOS)

    def _get_prompt(self) -> str:
        return self._prompt_txt.get("1.0", "end-1c").strip() or self.DEFAULT_PROMPT

    def _get_neg(self) -> str:
        return self._neg_txt.get("1.0", "end-1c").strip() or self.DEFAULT_NEG

    def _make_thumb(self, img):
        """Return a _THUMB_PX square thumbnail PIL Image."""
        from PIL import Image as PILImage
        t = self._THUMB_PX
        resample = PILImage.NEAREST if img.width <= t else PILImage.LANCZOS
        return img.resize((t, t), resample)

    def _run_pipeline(self, selected: List[str], scale: int,
                       strength: float, prompt: str, neg: str):
        from PIL import Image as PILImage

        ncnn_exe = self._detect_ncnn()
        self.after(0, self._log_line,
                   f"Real-ESRGAN-ncnn  model={self._ncnn_model_var.get()}  "
                   f"scale={scale}×  "
                   f"({'binary found' if ncnn_exe else 'LANCZOS fallback — install ncnn for ESRGAN'})")

        # Build job list: (cat, decode_fn, out_path)
        jobs = []
        out_root = RENDERS_DIR / "upscaled"

        if "ui_panels" in selected and RESOURCES.exists():
            out_dir = out_root / "ui_panels"
            for dat in sorted(RESOURCES.glob("*.dat")):
                try:
                    raw = dat.read_bytes()
                    if len(raw) < 20 or raw[:4] != b"CGSR":
                        continue
                    count = raw[4]
                    for fi in range(max(1, count)):
                        jobs.append(("ui_panels",
                                     lambda p=dat, f=fi: _decode_dat_frame(p, f),
                                     out_dir / f"{dat.stem}_f{fi}.png"))
                except Exception:
                    pass

        if "equip_icons" in selected:
            out_dir = out_root / "equip_icons"
            eq_dir  = THUMBNAILS / "Equip"
            if eq_dir.exists():
                for tn in sorted(eq_dir.glob("*.tn")):
                    jobs.append(("equip_icons",
                                 lambda p=tn: self._tn_to_image(p),
                                 out_dir / f"{tn.stem}.png"))

        if "talisman_icons" in selected:
            out_dir  = out_root / "talisman_icons"
            mag_dir  = THUMBNAILS / "Magic"
            if mag_dir.exists():
                for tn in sorted(mag_dir.glob("*.tn")):
                    jobs.append(("talisman_icons",
                                 lambda p=tn: self._tn_to_image(p),
                                 out_dir / f"{tn.stem}.png"))

        if "model_textures" in selected and IMAGERY_ASSETS.exists():
            out_dir = out_root / "model_textures"
            for i3d in sorted(IMAGERY_ASSETS.rglob("*.i3d")):
                try:
                    from decoders.i3d import decode_i3d_textures
                    textures = decode_i3d_textures(i3d)
                    for ti, tex in enumerate(textures):
                        if tex is not None:
                            jobs.append(("model_textures",
                                         lambda p=i3d, n=ti: self._decode_i3d_texture_n(p, n),
                                         out_dir / f"{i3d.stem}_t{ti}.png"))
                except Exception:
                    pass

        if "sprites" in selected and IMAGERY_ASSETS.exists():
            out_dir = out_root / "sprites"
            for i2d_p in sorted(IMAGERY_ASSETS.rglob("*.i2d")):
                jobs.append(("sprites",
                             lambda p=i2d_p: self._decode_sprite_safe(p),
                             out_dir / f"{i2d_p.stem}.png"))

        # Cinematix is handled separately (video pipeline, not per-frame jobs)
        cine_smks: List[Path] = []
        if "cinematix" in selected:
            ff = self._ffmpeg_path_var.get().strip()
            if not ff:
                self.after(0, self._log_line,
                           "Cinematix skipped — FFmpeg path not set. "
                           "Install FFmpeg and set path in left panel.")
            else:
                cine_smks = self._find_smk_files()
                if not cine_smks:
                    self.after(0, self._log_line,
                               "Cinematix: no SMK files found in game dirs")

        if not jobs and not cine_smks:
            self.after(0, self._log_line, "No assets found for selected categories")
            return

        total = len(jobs)
        self.after(0, self._log_line, f"{total} jobs queued")
        self.after(0, self._set_progress, 0, total, "Starting")

        ok = skip = 0
        for i, (cat, decode_fn, out_path) in enumerate(jobs, 1):
            if self._stop:
                self.after(0, self._log_line, "Stopped by user")
                break
            try:
                img = decode_fn()
                if img is None:
                    skip += 1
                    continue

                out_path.parent.mkdir(parents=True, exist_ok=True)

                up = self._upscale_with_ncnn(img, scale)

                up.save(str(out_path), format="PNG")
                ok += 1

                before_th = self._make_thumb(img)
                after_th  = self._make_thumb(up)
                self.after(0, self._add_result, {
                    "name":       out_path.stem,
                    "cat":        cat,
                    "decode_fn":  decode_fn,
                    "out_path":   out_path,
                    "src_size":   (img.width, img.height),
                    "out_size":   (up.width,  up.height),
                    "before_pil": before_th,
                    "after_pil":  after_th,
                    "status":     "ok",
                    "params":     {"strength": strength, "scale": scale, "prompt": prompt},
                })

            except Exception as exc:
                skip += 1
                self.after(0, self._log_line, f"SKIP {out_path.stem}: {exc}")
                self.after(0, self._add_result, {
                    "name":      out_path.stem,
                    "cat":       cat,
                    "decode_fn": decode_fn,
                    "out_path":  out_path,
                    "src_size":  (0, 0),
                    "status":    "failed",
                    "params":    {"strength": strength, "scale": scale, "prompt": prompt},
                })

            if i % 10 == 0 or i == total:
                self.after(0, self._set_progress, i, total, cat)

        # ── Cinematix video pipeline ──────────────────────────────────────────
        cine_ok = cine_skip = 0
        for smk in cine_smks:
            if self._stop:
                break
            try:
                result = self._process_smk(smk, scale, strength, prompt, neg, out_root)
                if result:
                    self.after(0, self._add_result, result)
                    cine_ok += 1
                else:
                    cine_skip += 1
            except Exception as exc:
                cine_skip += 1
                self.after(0, self._log_line, f"SMK failed [{smk.name}]: {exc}")

        total_ok   = ok   + cine_ok
        total_skip = skip + cine_skip
        self.after(0, self._log_line,
                   f"Done: {total_ok} ok  {total_skip} skipped  → {out_root}")
        self._status.set(f"Upscale: {total_ok} done, {total_skip} skipped")

    # ── Redo ─────────────────────────────────────────────────────────────────

    def _redo_result(self, idx: int):
        if self._running:
            self._status.set("Wait for current batch to finish")
            return
        r = self._results[idx]
        if not r.get("decode_fn"):
            return
        strength = float(self._redo_strength_var.get())
        scale    = int(self._redo_scale_var.get())
        prompt   = self._get_prompt()
        neg      = self._get_neg()

        self._running = True
        self._start_btn.config(state="disabled")
        self._prog["value"] = 0
        self._prog_lbl.config(text=f"Redoing {r['name']}…")

        def _worker():
            try:
                img = r["decode_fn"]()
                if img is None:
                    self.after(0, self._log_line, f"Redo: decode returned None for {r['name']}")
                    return
                up = self._upscale_with_ncnn(img, scale)
                r["out_path"].parent.mkdir(parents=True, exist_ok=True)
                up.save(str(r["out_path"]), format="PNG")

                r["src_size"]   = (img.width, img.height)
                r["out_size"]   = (up.width,  up.height)
                r["before_pil"] = self._make_thumb(img)
                r["after_pil"]  = self._make_thumb(up)
                r["status"]     = "ok"
                r["params"]     = {"strength": strength, "scale": scale, "prompt": prompt}

                self.after(0, self._rebuild_card, idx)
                if self._sel_idx == idx:
                    self.after(50, self._select_result, idx)
            except Exception as exc:
                self.after(0, self._log_line, f"Redo failed: {exc}")
            finally:
                self.after(0, self._on_done)

        threading.Thread(target=_worker, daemon=True).start()

    def _redo_selected(self):
        if self._sel_idx is not None:
            self._redo_result(self._sel_idx)

    def _redo_flagged(self):
        self._redo_queue = [i for i, r in enumerate(self._results) if r["status"] == "flagged"]
        if not self._redo_queue:
            self._status.set("No flagged items")
            return
        self._process_redo_queue()

    def _process_redo_queue(self):
        if not self._redo_queue:
            self._status.set("Redo flagged: complete")
            return
        idx = self._redo_queue.pop(0)
        self._redo_chain = True
        self._redo_result(idx)

    # ── FFmpeg helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _detect_ffmpeg() -> Optional[str]:
        """Return path to ffmpeg executable or None if not found."""
        import shutil
        # 1. Project-local tools/ffmpeg.exe (installed via "Install to project")
        local = ENGINE_DIR / "tools" / "ffmpeg.exe"
        if local.exists():
            return str(local)
        # 2. System PATH
        p = shutil.which("ffmpeg")
        if p:
            return p
        # 3. Common Windows install locations
        for c in [
            Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
            Path("C:/ffmpeg/bin/ffmpeg.exe"),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/WinGet/Links/ffmpeg.exe",
        ]:
            if c.exists():
                return str(c)
        return None

    def _update_ffmpeg_status(self):
        ff = self._ffmpeg_path_var.get().strip() if hasattr(self, "_ffmpeg_path_var") else self._ffmpeg_path
        found = self._probe_ffmpeg(ff)
        if found:
            self._ffmpeg_status_lbl.config(text="✓ found", fg=ACCENT3)
            if hasattr(self, "_install_btn"):
                self._install_btn.config(state="disabled", bg=BG_CARD, fg=FG_DIM)
        else:
            self._ffmpeg_status_lbl.config(text="✗ not found", fg=RED)
            if hasattr(self, "_install_btn"):
                self._install_btn.config(state="normal", bg=ACCENT2, fg="#000")

    @staticmethod
    def _probe_ffmpeg(ff: str) -> bool:
        """Return True if ff is a runnable ffmpeg binary."""
        import subprocess
        if not ff:
            return False
        try:
            r = subprocess.run([ff, "-version"], capture_output=True, timeout=5)
            return r.returncode == 0
        except Exception:
            return False

    def _on_ffmpeg_path_changed(self):
        self._ffmpeg_path = self._ffmpeg_path_var.get().strip()
        self._update_ffmpeg_status()

    def _browse_ffmpeg(self):
        p = filedialog.askopenfilename(
            title="Select ffmpeg.exe",
            filetypes=[("Executable", "*.exe"), ("All files", "*.*")])
        if p:
            self._ffmpeg_path_var.set(p)

    def _install_ffmpeg(self):
        """Download FFmpeg win64 binary to ENGINE_DIR/tools/ffmpeg.exe in a thread."""
        if self._running:
            self._status.set("Wait for current operation to finish")
            return
        self._install_btn.config(state="disabled", text="Installing…")
        threading.Thread(target=self._install_ffmpeg_worker, daemon=True).start()

    def _install_ffmpeg_worker(self):
        import zipfile, io
        FFMPEG_URL = (
            "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
            "ffmpeg-master-latest-win64-lgpl.zip"
        )
        dest = ENGINE_DIR / "tools" / "ffmpeg.exe"
        try:
            import requests as req
            self.after(0, self._log_line, "Downloading FFmpeg (~25 MB)…")

            resp = req.get(FFMPEG_URL, stream=True, timeout=60)
            resp.raise_for_status()

            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            chunks = []
            for chunk in resp.iter_content(chunk_size=1 << 16):  # 64 KB
                chunks.append(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    self.after(0, lambda p=pct: setattr(self._prog, "value", p)
                               if hasattr(self, "_prog") else None)

            self.after(0, self._log_line, "Extracting ffmpeg.exe…")
            data = b"".join(chunks)
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                # Find the ffmpeg.exe entry (inside bin/ subdirectory)
                entry = next((n for n in zf.namelist()
                              if n.endswith("/bin/ffmpeg.exe") or n == "ffmpeg.exe"), None)
                if not entry:
                    raise FileNotFoundError(
                        f"ffmpeg.exe not found in zip. Entries: {zf.namelist()[:10]}")
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(entry))

            self.after(0, self._log_line, f"FFmpeg installed → {dest}")
            self.after(0, self._ffmpeg_path_var.set, str(dest))
            self.after(0, self._update_ffmpeg_status)
            self.after(0, self._refresh_counts)

        except Exception as exc:
            self.after(0, self._log_line, f"FFmpeg install failed: {exc}")
        finally:
            self.after(0, self._install_btn.config,
                       {"state": "normal", "text": "Install to project"})

    # ── Real-ESRGAN-ncnn-vulkan helpers ───────────────────────────────────────

    @staticmethod
    def _detect_ncnn() -> Optional[str]:
        """Return path to realesrgan-ncnn-vulkan.exe or None."""
        import shutil
        local = ENGINE_DIR / "tools" / "realesrgan-ncnn" / "realesrgan-ncnn-vulkan.exe"
        if local.exists():
            return str(local)
        ncnn_dir = ENGINE_DIR / "tools" / "realesrgan-ncnn"
        candidates = list(ncnn_dir.glob("*ncnn-vulkan*.exe"))
        if candidates:
            return str(candidates[0])
        p = shutil.which("realesrgan-ncnn-vulkan")
        return p

    def _update_ncnn_status(self):
        exe = self._detect_ncnn()
        if exe:
            self._ncnn_status_lbl.config(text="✓ found", fg=ACCENT3)
            self._ncnn_install_btn.config(state="disabled", bg=BG_CARD, fg=FG_DIM)
        else:
            self._ncnn_status_lbl.config(text="✗ not found", fg=RED)
            self._ncnn_install_btn.config(state="normal", bg=ACCENT2, fg="#000")

    def _install_ncnn(self):
        if self._running:
            self._status.set("Wait for current operation to finish")
            return
        self._ncnn_install_btn.config(state="disabled", text="Installing…")
        threading.Thread(target=self._install_ncnn_worker, daemon=True).start()

    def _install_ncnn_worker(self):
        import zipfile, io
        # Portable ncnn-vulkan binary — works on any NVIDIA/AMD/Intel GPU via Vulkan
        NCNN_URL = (
            "https://github.com/xinntao/Real-ESRGAN/releases/download/"
            "v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip"
        )
        dest_dir = ENGINE_DIR / "tools" / "realesrgan-ncnn"
        try:
            import requests as req
            self.after(0, self._log_line, "Downloading Real-ESRGAN-ncnn-vulkan (~30 MB)…")
            resp = req.get(NCNN_URL, stream=True, timeout=120)
            resp.raise_for_status()

            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            chunks = []
            for chunk in resp.iter_content(chunk_size=1 << 16):
                chunks.append(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    self.after(0, lambda p=pct: setattr(self._prog, "value", p)
                               if hasattr(self, "_prog") else None)

            self.after(0, self._log_line, "Extracting…")
            data = b"".join(chunks)
            dest_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = zf.namelist()
                # Detect common top-level directory prefix (handles both flat and nested zips)
                top = ""
                if names:
                    candidate = names[0].split("/")[0] + "/"
                    if all(n.startswith(candidate) or n == candidate.rstrip("/") for n in names):
                        top = candidate
                for member in names:
                    rel = member[len(top):]
                    if not rel:
                        continue
                    dest = dest_dir / rel
                    if member.endswith("/"):
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(zf.read(member))

            exe = dest_dir / "realesrgan-ncnn-vulkan.exe"
            self.after(0, self._log_line,
                       f"Real-ESRGAN-ncnn installed → {exe}")
            self.after(0, self._update_ncnn_status)

        except Exception as exc:
            self.after(0, self._log_line, f"ncnn install failed: {exc}")
        finally:
            self.after(0, self._ncnn_install_btn.config,
                       {"state": "normal", "text": "Install to project"})

    def _find_smk_files(self) -> List[Path]:
        """Collect all .smk/.SMK files from known game directories."""
        search_dirs = [
            Path("C:/GOG Games/Revenant/Disk2"),
            GAME_DIR / "Disk2",
            GAME_DIR,
            EXTRACT_DIR,
        ]
        seen: set = set()
        results: List[Path] = []
        for d in search_dirs:
            if not d.exists():
                continue
            for ext in ("*.smk", "*.SMK"):
                for f in d.rglob(ext):
                    if f not in seen:
                        seen.add(f)
                        results.append(f)
        return sorted(results)

    def _process_smk(self, smk: Path, scale: int, strength: float,
                      prompt: str, neg: str, out_root: Path) -> Optional[Dict]:
        """
        SMK → upscaled MP4.

        Fast path  (ncnn installed):
          FFmpeg extracts PNG frames → realesrgan-ncnn-vulkan batch-upscales
          the entire frames directory on the GPU in one call → FFmpeg re-encodes.

        Fallback (ncnn not installed):
          Single FFmpeg pass with pp=de/fd deblock + lanczos scale filter.
        """
        import subprocess, tempfile
        from PIL import Image as PILImage

        ff = self._ffmpeg_path_var.get().strip()
        if not ff:
            raise RuntimeError("FFmpeg path not set")

        ncnn_exe   = self._detect_ncnn()
        ncnn_model = self._ncnn_model_var.get()
        out_dir    = out_root / "cinematix"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_mp4    = out_dir / f"{smk.stem}_{scale}x.mp4"

        first_before = first_after = None

        if ncnn_exe:
            # ── Fast GPU path ─────────────────────────────────────────────────
            with tempfile.TemporaryDirectory(prefix="revengine_cine_") as tmp:
                frames_raw = Path(tmp) / "raw"
                frames_up  = Path(tmp) / "up"
                frames_raw.mkdir()
                frames_up.mkdir()

                # 1. Decode SMK → PNG frames (15 fps)
                self.after(0, self._log_line,
                           f"  [{smk.name}] Extracting frames…")
                r1 = subprocess.run(
                    [ff, "-y", "-i", str(smk), "-vf", "fps=15",
                     str(frames_raw / "%04d.png")],
                    capture_output=True, text=True, timeout=120)
                if r1.returncode != 0:
                    raise RuntimeError(f"FFmpeg extract: {r1.stderr[-300:]}")

                frame_paths = sorted(frames_raw.glob("*.png"))
                if not frame_paths:
                    raise RuntimeError("No frames extracted from SMK")

                first_before = PILImage.open(str(frame_paths[0])).copy()

                # 2. Batch upscale entire directory on GPU
                self.after(0, self._log_line,
                           f"  [{smk.name}] {len(frame_paths)} frames → "
                           f"Real-ESRGAN-ncnn ×{scale} ({ncnn_model})…")
                r2 = subprocess.run(
                    [ncnn_exe,
                     "-i", str(frames_raw),
                     "-o", str(frames_up),
                     "-n", ncnn_model,
                     "-s", str(scale),
                     "-f", "png",
                     "-g", "0"],       # GPU 0 (Vulkan — picks NVIDIA automatically)
                    capture_output=True, text=True, timeout=600)
                if r2.returncode != 0:
                    raise RuntimeError(f"ncnn: {r2.stderr[-300:]}")

                up_paths = sorted(frames_up.glob("*.png"))
                if up_paths:
                    first_after = PILImage.open(str(up_paths[0])).copy()

                # 3. Re-encode upscaled frames → H.264
                self.after(0, self._log_line,
                           f"  [{smk.name}] Encoding MP4…")
                r3 = subprocess.run(
                    [ff, "-y", "-framerate", "15",
                     "-i", str(frames_up / "%04d.png"),
                     "-c:v", "libx264", "-crf", "16", "-preset", "slow",
                     "-pix_fmt", "yuv420p", str(out_mp4)],
                    capture_output=True, text=True, timeout=300)
                if r3.returncode != 0:
                    raise RuntimeError(f"FFmpeg encode: {r3.stderr[-300:]}")

            method_tag = f"esrgan-ncnn:{ncnn_model}"

        else:
            # ── FLUX NIM frame-by-frame (cloud, no local GPU needed) ──────────
            flux_step = int(self._cine_step_var.get())
            self.after(0, self._log_line,
                       f"  [{smk.name}] No ncnn — FLUX NIM ×{scale} "
                       f"every {flux_step} frame(s)…")

            with tempfile.TemporaryDirectory(prefix="revengine_cine_") as tmp:
                frames_raw = Path(tmp) / "raw"
                frames_up  = Path(tmp) / "up"
                frames_raw.mkdir()
                frames_up.mkdir()

                # 1. Decode SMK → PNG frames
                r1 = subprocess.run(
                    [ff, "-y", "-i", str(smk), "-vf", "fps=15",
                     str(frames_raw / "%04d.png")],
                    capture_output=True, text=True, timeout=120)
                if r1.returncode != 0:
                    raise RuntimeError(f"FFmpeg extract: {r1.stderr[-300:]}")

                frame_paths = sorted(frames_raw.glob("*.png"))
                if not frame_paths:
                    raise RuntimeError("No frames extracted from SMK")

                n_frames = len(frame_paths)
                self.after(0, self._log_line,
                           f"  [{smk.name}] {n_frames} frames — "
                           f"FLUX on {(n_frames + flux_step - 1) // flux_step} "
                           f"key frames, LANCZOS fill…")

                # 2. Enhance key frames with FLUX, fill gaps with LANCZOS
                for fi, fp in enumerate(frame_paths):
                    if self._stop:
                        raise RuntimeError("Stopped by user")
                    img = PILImage.open(str(fp))
                    up = self._scale_pil_fast(img, scale)

                    out_fp = frames_up / fp.name
                    up.convert("RGB").save(str(out_fp), format="PNG")

                    if fi == 0:
                        first_before = img.copy()
                        first_after  = up.copy()

                    if fi % 20 == 0 or fi == n_frames - 1:
                        self.after(0, self._log_line,
                                   f"    [{smk.name}] {fi + 1}/{n_frames}…")

                # 3. Re-encode → MP4
                self.after(0, self._log_line, f"  [{smk.name}] Encoding MP4…")
                r3 = subprocess.run(
                    [ff, "-y", "-framerate", "15",
                     "-i", str(frames_up / "%04d.png"),
                     "-c:v", "libx264", "-crf", "16", "-preset", "slow",
                     "-pix_fmt", "yuv420p", str(out_mp4)],
                    capture_output=True, text=True, timeout=300)
                if r3.returncode != 0:
                    raise RuntimeError(f"FFmpeg encode: {r3.stderr[-300:]}")

            method_tag = f"flux-nim:step={flux_step}"

        self.after(0, self._log_line,
                   f"  [{smk.name}] Done [{method_tag}] → {out_mp4.name}")

        t = self._THUMB_PX
        before_th = first_before.resize((t, t), PILImage.LANCZOS) if first_before else None
        after_th  = first_after.resize((t, t),  PILImage.LANCZOS) if first_after  else None

        def _redo_decode_fn(smk_path=smk):
            import subprocess, tempfile
            ff2 = self._ffmpeg_path_var.get().strip()
            with tempfile.TemporaryDirectory() as td:
                out_f = Path(td) / "frame.png"
                subprocess.run([ff2, "-y", "-i", str(smk_path),
                                "-vframes", "1", str(out_f)],
                               capture_output=True)
                if out_f.exists():
                    return PILImage.open(str(out_f)).copy()
            return None

        src_w = first_before.width  if first_before else 0
        src_h = first_before.height if first_before else 0
        out_w = first_after.width   if first_after  else 0
        out_h = first_after.height  if first_after  else 0

        return {
            "name":       smk.stem,
            "cat":        "cinematix",
            "decode_fn":  _redo_decode_fn,
            "out_path":   out_mp4,
            "src_size":   (src_w, src_h),
            "out_size":   (out_w, out_h),
            "before_pil": before_th,
            "after_pil":  after_th,
            "status":     "ok",
            "params":     {"strength": strength, "scale": scale, "prompt": prompt},
            "_smk_path":  smk,
        }

    # ── Asset decode helpers ─────────────────────────────────────────────────

    @staticmethod
    def _tn_to_image(tn_path: Path):
        from PIL import Image as PILImage
        raw = tn_path.read_bytes()
        rgba = _decode_tn_pixels(raw)
        if rgba is None:
            return None
        return PILImage.frombytes("RGBA", (16, 16), rgba)

    @staticmethod
    def _decode_i3d_texture_n(i3d_path: Path, texture_idx: int):
        from decoders.i3d import decode_i3d_textures
        try:
            textures = decode_i3d_textures(i3d_path)
            return textures[texture_idx] if texture_idx < len(textures) else None
        except Exception:
            return None

    @staticmethod
    def _decode_sprite_safe(i2d_path: Path):
        try:
            from decoders.i2d import decode_i2d
            return decode_i2d(i2d_path)
        except Exception:
            return None


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════

class AssetStudio(tk.Tk):
    def __init__(self):
        super().__init__()
        _load_config()
        self.title("RevEngine  —  Revenant (1999) Asset Encyclopedia")
        self.geometry("1400x880")
        self.configure(bg=BG_DARK)
        self.resizable(True, True)
        self._apply_style()
        self._build_ui()
        self._bind_shortcuts()

    def _apply_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("TNotebook",          background=BG_DARK,  borderwidth=0)
        style.configure("TNotebook.Tab",      background=BG_MID,   foreground=FG_DIM,
                         padding=[14, 6],     font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab",
                  background=[("selected", BG_PANEL)],
                  foreground=[("selected", FG_TEXT)])

        style.configure("Treeview",           background=BG_PANEL, foreground=FG_TEXT,
                         fieldbackground=BG_PANEL, rowheight=22,
                         font=("Segoe UI", 9))
        style.configure("Treeview.Heading",   background=BG_MID,   foreground=ACCENT2,
                         font=("Segoe UI", 9, "bold"), relief="flat")
        style.map("Treeview",
                  background=[("selected", BG_CARD)],
                  foreground=[("selected", FG_TEXT)])

        style.configure("TScrollbar",         background=BG_MID,   troughcolor=BG_DARK,
                         arrowcolor=FG_DIM,   borderwidth=0, relief="flat")
        style.configure("TCombobox",          background=BG_PANEL, foreground=FG_TEXT,
                         fieldbackground=BG_PANEL, arrowcolor=ACCENT2)
        style.configure("TSeparator",         background=BORDER)
        style.configure("TPanedwindow",       background=BG_DARK)

    def _build_ui(self):
        # ── Menu bar ─────────────────────────────────────────────────────────
        self._build_menu()

        # ── Header ───────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=BG_DARK, pady=8)
        hdr.pack(fill="x")

        tk.Label(hdr, text="REVENGINE", bg=BG_DARK, fg=ACCENT,
                 font=("Segoe UI", 18, "bold")).pack(side="left", padx=16)
        tk.Label(hdr, text="Revenant (1999) Asset Encyclopedia",
                 bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 11)).pack(side="left", padx=0)

        # Asset counts (filled after load)
        self._hdr_counts = tk.Label(hdr, text="", bg=BG_DARK, fg=ACCENT3,
                                     font=("Segoe UI", 9))
        self._hdr_counts.pack(side="right", padx=16)

        # ── Status bar ───────────────────────────────────────────────────────
        self._status = StatusBar(self)
        self._status.pack(side="bottom", fill="x")

        ttk.Separator(self).pack(side="bottom", fill="x")

        # ── Main notebook ────────────────────────────────────────────────────
        self._nb = ttk.Notebook(self)
        self._nb.pack(fill="both", expand=True, padx=0, pady=0)

        self._map_tab   = WorldMapTab(self._nb, self._status)
        self._char_tab  = CharacterGalleryTab(self._nb, self._status)
        self._equip_tab = EquipmentTab(self._nb, self._status)
        self._spr_tab   = SpritesTab(self._nb, self._status)
        self._spell_tab = SpellsTab(self._nb, self._status)
        self._scr_tab   = ScriptsTab(self._nb, self._status)
        self._mod_tab   = ModelsTab(self._nb, self._status)
        self._snd_tab   = SoundsTab(self._nb, self._status)
        self._cine_tab  = CinematiXTab(self._nb, self._status)
        self._ui_tab    = UIResourcesTab(self._nb, self._status)
        self._ahk_tab     = AhkuilonTab(self._nb, self._status)
        self._upscale_tab    = UpscaleTab(self._nb, self._status)
        from asset_studio_modernize import ModernizeTab
        self._modernize_tab  = ModernizeTab(self._nb, self._status)

        self._nb.add(self._map_tab,      text="  World Map  ")
        self._nb.add(self._char_tab,     text="  Characters  ")
        self._nb.add(self._equip_tab,    text="  Equipment  ")
        self._nb.add(self._spr_tab,      text="  Sprites  ")
        self._nb.add(self._spell_tab,    text="  Spells  ")
        self._nb.add(self._scr_tab,      text="  Scripts  ")
        self._nb.add(self._mod_tab,      text="  3D Models  ")
        self._nb.add(self._snd_tab,      text="  Sounds  ")
        self._nb.add(self._cine_tab,     text="  Cinematix  ")
        self._nb.add(self._ui_tab,       text="  UI Resources  ")
        self._nb.add(self._ahk_tab,      text="  Ahkuilon  ")
        self._nb.add(self._upscale_tab,   text="  Upscale  ")
        self._nb.add(self._modernize_tab, text="  Modernize 3D  ")

        # Update header counts after brief delay
        self.after(2000, self._update_counts)

    def _update_counts(self):
        try:
            i3d_count = len(list(IMAGERY_ASSETS.rglob("*.i3d")))
            bmp_count = len(list(IMAGERY_ASSETS.rglob("*.bmp")))
            def_count = len(list(EXTRACT_DIR.rglob("*.def")))
            mp3_count = len(list(EXTRACT_DIR.rglob("*.mp3")))
            ogg_count = len(list(EXTRACT_DIR.rglob("*.ogg")))
            self._hdr_counts.config(
                text=f"{i3d_count} models  |  {bmp_count} sprites  |  "
                     f"{def_count} scripts  |  {mp3_count + ogg_count} sounds")
        except Exception:
            pass

    # ── Menu ─────────────────────────────────────────────────────────────────

    def _build_menu(self):
        M = dict(bg=BG_MID, fg=FG_TEXT, activebackground=BG_CARD,
                 activeforeground=FG_TEXT, relief="flat")
        menubar = tk.Menu(self, **M, borderwidth=0)
        self.config(menu=menubar)

        # File
        file_m = tk.Menu(menubar, tearoff=0, **M)
        menubar.add_cascade(label="File", menu=file_m)
        file_m.add_command(label="Open Game Dir",
                           command=lambda: GAME_DIR.exists() and os.startfile(str(GAME_DIR)))
        file_m.add_command(label="Open Extract Dir",
                           command=lambda: EXTRACT_DIR.exists() and os.startfile(str(EXTRACT_DIR)))
        file_m.add_command(label="Open Export Dir",
                           command=self._open_export_dir)
        file_m.add_separator()
        file_m.add_command(label="Settings…\tCtrl+,", command=lambda: SettingsDialog(self))
        file_m.add_separator()
        file_m.add_command(label="Exit\tCtrl+Q", command=self.destroy)

        # View — jump to tab
        view_m = tk.Menu(menubar, tearoff=0, **M)
        menubar.add_cascade(label="View", menu=view_m)
        _tabs = ["World Map", "Characters", "Equipment", "Sprites",
                 "Spells", "Scripts", "3D Models", "Sounds", "Cinematix",
                 "UI Resources", "Ahkuilon"]
        for i, name in enumerate(_tabs):
            view_m.add_command(label=name, command=lambda i=i: self._nb.select(i))

        # Export
        exp_m = tk.Menu(menubar, tearoff=0, **M)
        menubar.add_cascade(label="Export", menu=exp_m)
        exp_m.add_command(label="Export Current Tab\tCtrl+E",
                          command=self._export_current_tab)
        exp_m.add_separator()
        exp_m.add_command(label="Characters (portraits)…",
                          command=lambda: self._char_tab._export_all())
        exp_m.add_command(label="Weapons (icons)…",
                          command=lambda: self._equip_tab._export_all_weapons())
        exp_m.add_command(label="Armors (icons)…",
                          command=lambda: self._equip_tab._export_all_armors())
        exp_m.add_command(label="Spell Icons…",
                          command=lambda: self._spell_tab._export_all())
        exp_m.add_command(label="Scripts (.def files)…",
                          command=lambda: self._scr_tab._export_all())
        exp_m.add_command(label="Models (OBJ batch)…",
                          command=lambda: self._mod_tab._batch_export_obj())
        exp_m.add_command(label="Sprites (current category)…",
                          command=lambda: self._spr_tab._export_all())
        exp_m.add_command(label="UI Resources (all .dat frames)…",
                          command=lambda: self._ui_tab._export_all())
        exp_m.add_command(label="Ahkuilon Scripts…",
                          command=lambda: self._ahk_tab._export_all())
        exp_m.add_separator()
        exp_m.add_command(label="Export All Assets…",
                          command=self._export_all_assets)

        # Help
        help_m = tk.Menu(menubar, tearoff=0, **M)
        menubar.add_cascade(label="Help", menu=help_m)
        help_m.add_command(label="Keyboard Shortcuts", command=self._show_shortcuts)
        help_m.add_command(label="About\tF1", command=self._show_about)

    def _bind_shortcuts(self):
        self.bind_all("<Control-q>", lambda e: self.destroy())
        self.bind_all("<Control-comma>", lambda e: SettingsDialog(self))
        self.bind_all("<Control-e>", lambda e: self._export_current_tab())
        self.bind_all("<F1>", lambda e: self._show_about())

    def _open_export_dir(self):
        RENDERS_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(RENDERS_DIR))

    # ── Export dispatch ───────────────────────────────────────────────────────

    def _export_current_tab(self):
        idx = self._nb.index("current")
        dispatch = {
            1: self._char_tab._export_all,
            2: self._equip_tab._export_all_weapons,
            3: self._spr_tab._export_all,
            4: self._spell_tab._export_all,
            5: self._scr_tab._export_all,
            6: self._mod_tab._batch_export_obj,
            9: self._ui_tab._export_all,
            10: self._ahk_tab._export_all,
        }
        fn = dispatch.get(idx)
        if fn:
            fn()
        else:
            self._status.set("No batch export for this tab — use the tab's own controls")

    def _export_all_assets(self):
        steps = [
            ("Characters",   self._char_tab._export_all),
            ("Weapons",      self._equip_tab._export_all_weapons),
            ("Armors",       self._equip_tab._export_all_armors),
            ("Scripts",      self._scr_tab._export_all),
            ("Spell Icons",  self._spell_tab._export_all),
            ("Models (OBJ)", self._mod_tab._batch_export_obj),
            ("UI Resources", self._ui_tab._export_all),
            ("Ahkuilon",     self._ahk_tab._export_all),
        ]
        total = len(steps)

        def _run(idx=0):
            if idx >= total:
                self._status.set("Export All complete — check export directories")
                return
            name, fn = steps[idx]
            self._status.set(f"Exporting {name}… ({idx + 1}/{total})")
            try:
                fn()
            except Exception as e:
                log.warning("Export All: %s failed: %s", name, e)
            self.after(150, _run, idx + 1)

        _run()

    # ── Help dialogs ─────────────────────────────────────────────────────────

    def _show_about(self):
        messagebox.showinfo(
            "About RevEngine",
            "RevEngine Asset Studio\n"
            "Revenant (1999) Game Encyclopedia\n\n"
            "Assets © Cinematix Studios / GOG release\n"
            "Viewer: RevEngine project",
            parent=self,
        )

    def _show_shortcuts(self):
        win = tk.Toplevel(self)
        win.title("Keyboard Shortcuts")
        win.configure(bg=BG_DARK)
        win.resizable(False, False)
        win.transient(self)
        rows = [
            ("Ctrl+E",   "Export Current Tab"),
            ("Ctrl+,",   "Settings"),
            ("Ctrl+Q",   "Exit"),
            ("F1",       "About"),
        ]
        for r, (key, desc) in enumerate(rows):
            tk.Label(win, text=key, bg=BG_DARK, fg=ACCENT,
                     font=("Consolas", 10, "bold"), width=10, anchor="e").grid(
                row=r, column=0, padx=(20, 10), pady=6)
            tk.Label(win, text=desc, bg=BG_DARK, fg=FG_TEXT,
                     font=("Segoe UI", 10), anchor="w").grid(
                row=r, column=1, sticky="w", padx=(0, 20))


# ═══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if not EXTRACT_DIR.exists():
        print(f"ERROR: Extracted files not found at {EXTRACT_DIR}")
        print("Run:  py RevEngine/setup.py   first.")
    elif not HAS_PIL:
        print("ERROR: Pillow not installed. Run:  py -m pip install Pillow")
    else:
        app = AssetStudio()
        app.mainloop()
