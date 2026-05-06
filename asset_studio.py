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
from pathlib import Path
from typing import Optional, List, Dict, Tuple

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
    """Parse spell.def into a list of spell dicts."""
    text = _read_def(SPELL_DEF)
    spells = []
    pattern = re.compile(r'SPELL\s+"([^"]+)"\s*\nBEGIN(.*?)END', re.DOTALL)
    for m in pattern.finditer(text):
        name = m.group(1).strip()
        body = m.group(2)

        def _tag(t):
            rx = re.search(rf'\b{t}\b\s+(-?[\w\.]+)', body)
            return rx.group(1) if rx else ""

        s = {
            "name":        name,
            "mana":        _tag("MANA"),
            "damage":      _tag("DAMAGE"),
            "duration":    _tag("DURATION"),
            "description": "",
        }
        # grab text description (DESC tag or first comment)
        desc_m = re.search(r'(?:DESCRIPTION|//)\s+(.+)', body)
        if desc_m:
            s["description"] = desc_m.group(1).strip()
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

        self._export_all_btn = tk.Button(
                  bar, text="Export All Zones", command=self._export_all_zones,
                  bg="#2a6040", fg="white", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10)
        self._export_all_btn.pack(side="left", padx=4)

        self._extract_btn = tk.Button(
                  bar, text="⬇ Extract Modules", command=self._extract_missing_modules,
                  bg="#5a3070", fg="white", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10)
        self._extract_btn.pack(side="left", padx=4)

        tk.Button(bar, text="🔍 Diagnose", command=self._show_diagnose,
                  bg="#304050", fg="white", relief="flat",
                  font=("Segoe UI", 10, "bold"), padx=10
                  ).pack(side="left", padx=4)

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
        """Save the currently displayed zone map as a PNG."""
        if self._img is None:
            self._status.set("Nothing to save — stitch a zone first.")
            return
        module, zone = self._current_zone_key()
        RENDERS_DIR.mkdir(parents=True, exist_ok=True)
        out = RENDERS_DIR / f"world_map_{module}_zone{zone}.png"
        self._img.save(out)
        self._status.set(f"Saved: {out}")

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


        self._zoom = z
        self._refresh_display()

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
        """Try to load .tn thumbnail from Thumbnails/Equip/ folder."""
        if not HAS_PIL:
            return
        equip_dir = THUMBNAILS / "Equip"
        if not equip_dir.exists():
            return
        norm = name.replace(" ", "").replace("-", "")
        for f in equip_dir.iterdir():
            fn = f.stem.lower().replace(" ", "").replace("-", "")
            if f.suffix.lower() == '.tn' and (fn == norm or norm in fn or fn in norm):
                try:
                    raw = f.read_bytes()
                    px  = _decode_tn_pixels(raw)
                    if px is not None:
                        img = Image.frombytes('RGB', (16, 16), px)
                        img = img.resize((64, 64), Image.NEAREST)
                        ph  = ImageTk.PhotoImage(img)
                        lbl.config(image=ph)
                        lbl._photo = ph
                    return
                except Exception:
                    pass
        lbl.config(image="")


# ═══════════════════════════════════════════════════════════════════════════════
#  SPELLS TAB
# ═══════════════════════════════════════════════════════════════════════════════

class SpellsTab(tk.Frame):
    def __init__(self, parent, status: StatusBar):
        super().__init__(parent, bg=BG_MID)
        self._status = status
        self._spells = []
        self._build_ui()
        self.after(400, self._load_all)

    def _build_ui(self):
        bar = tk.Frame(self, bg=BG_DARK, pady=4)
        bar.pack(fill="x")
        self._flt_var = tk.StringVar()
        tk.Label(bar, text="Filter:", bg=BG_DARK, fg=FG_DIM,
                 font=("Segoe UI", 10)).pack(side="left", padx=(10,4))
        tk.Entry(bar, textvariable=self._flt_var,
                  bg=BG_PANEL, fg=FG_TEXT, insertbackground=FG_TEXT,
                  font=("Segoe UI", 10), relief="flat", width=20
                  ).pack(side="left", padx=4)
        self._flt_var.trace_add("write", self._filter)
        self._count_lbl = tk.Label(bar, text="", bg=BG_DARK, fg=FG_DIM,
                                    font=("Segoe UI", 9))
        self._count_lbl.pack(side="right", padx=12)

        pane = tk.PanedWindow(self, orient="horizontal", bg=BG_DARK,
                               sashwidth=6, sashrelief="flat")
        pane.pack(fill="both", expand=True)

        # List
        lf = tk.Frame(pane, bg=BG_MID)
        pane.add(lf, minsize=260)
        cols = ("name","mana","damage")
        self._tv = ttk.Treeview(lf, columns=cols, show="headings",
                                  selectmode="browse")
        self._tv.heading("name",   text="Spell",  anchor="w")
        self._tv.heading("mana",   text="Mana",   anchor="center")
        self._tv.heading("damage", text="Damage", anchor="center")
        self._tv.column("name",   width=200, stretch=True)
        self._tv.column("mana",   width=60,  stretch=False, anchor="center")
        self._tv.column("damage", width=70,  stretch=False, anchor="center")
        sb = ttk.Scrollbar(lf, orient="vertical", command=self._tv.yview)
        self._tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._tv.pack(fill="both", expand=True)
        self._tv.bind("<<TreeviewSelect>>", self._on_select)

        # Detail
        det = tk.Frame(pane, bg=BG_PANEL, padx=12, pady=12)
        pane.add(det, minsize=320)
        tk.Label(det, text="SPELL DETAILS", bg=BG_PANEL, fg=RED,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w")
        ttk.Separator(det).pack(fill="x", pady=6)
        self._det_text = tk.Text(det, bg=BG_PANEL, fg=FG_TEXT,
                                  font=("Consolas", 9), relief="flat",
                                  state="disabled", wrap="word")
        self._det_text.pack(fill="both", expand=True)
        self._det_text.tag_configure("h",  foreground=RED,    font=("Segoe UI",10,"bold"))
        self._det_text.tag_configure("kv", foreground=ACCENT2,font=("Segoe UI", 9))

    def _load_all(self):
        self._status.set("Parsing spell.def...")
        self._spells = parse_spell_def()
        self._populate(self._spells)
        self._count_lbl.config(text=f"{len(self._spells)} spells")
        self._status.set(f"Spells loaded: {len(self._spells)}")

    def _populate(self, data: List[Dict]):
        self._tv.delete(*self._tv.get_children())
        for s in data:
            self._tv.insert("", "end",
                values=(s["name"], s.get("mana","—"), s.get("damage","—")))

    def _filter(self, *_):
        flt = self._flt_var.get().strip().lower()
        filtered = [s for s in self._spells
                    if flt in s["name"].lower()] if flt else self._spells
        self._populate(filtered)
        self._count_lbl.config(text=f"{len(filtered)} / {len(self._spells)}")

    def _on_select(self, _):
        sel = self._tv.selection()
        if not sel:
            return
        name = self._tv.item(sel[0], "values")[0]
        s = next((x for x in self._spells if x["name"] == name), None)
        if not s:
            return
        txt = self._det_text
        txt.configure(state="normal")
        txt.delete("1.0", "end")
        txt.insert("end", f"{s['name']}\n", "h")

        def row(k, v):
            txt.insert("end", f"  {k:<18}", "kv")
            txt.insert("end", f"{v}\n")

        row("Mana cost",  s.get("mana","—"))
        row("Damage",     s.get("damage","—"))
        row("Duration",   s.get("duration","—"))
        if s.get("description"):
            txt.insert("end", "\nNotes:\n", "kv")
            txt.insert("end", f"  {s['description']}\n")
        txt.configure(state="disabled")


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
        self._mode_var = tk.StringVar(value="shaded")
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
            self._viewer.load(geom.vertices, geom.faces, info,
                              normals=geom.normals if has_nrm else None,
                              uvs=geom.uvs if has_uvs else None)

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
    Decode a 768-byte .tn file to 768 bytes of flat RGB888 (16×16 image).

    .tn format:
      [0:512]   256 × uint16 LE X1R5G5B5 palette  (R=bits14-10, G=9-5, B=4-0)
      [512:768] 256 bytes = 16×16 pixels as 8-bit palette indices
    """
    if len(raw) < 768:
        return None
    # Decode palette
    pal = []
    for i in range(256):
        word = struct.unpack_from('<H', raw, i * 2)[0]
        r = ((word >> 10) & 0x1F) << 3
        g = ((word >>  5) & 0x1F) << 3
        b = ( word        & 0x1F) << 3
        pal.append((r, g, b))
    # Map 16×16 indices to RGB
    indices = raw[512:768]
    pixels  = bytearray(256 * 3)
    for j in range(256):
        r, g, b = pal[indices[j]]
        pixels[j * 3]     = r
        pixels[j * 3 + 1] = g
        pixels[j * 3 + 2] = b
    return bytes(pixels)


def _load_tn_image(tn_path: Path, size: int = THUMB_SIZE) -> Optional["Image.Image"]:
    """Load a 16×16 .tn thumbnail (X1R5G5B5 palette + indexed pixels)."""
    if not HAS_PIL:
        return None
    try:
        raw = tn_path.read_bytes()
        px  = _decode_tn_pixels(raw)
        if px is None:
            return None
        img = Image.frombytes('RGB', (16, 16), px)
        return img.resize((size, size), Image.NEAREST)
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
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════════════════

class AssetStudio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("RevEngine  —  Revenant (1999) Asset Encyclopedia")
        self.geometry("1400x880")
        self.configure(bg=BG_DARK)
        self.resizable(True, True)
        self._apply_style()
        self._build_ui()

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

        self._map_tab  = WorldMapTab(self._nb, self._status)
        self._char_tab = CharacterGalleryTab(self._nb, self._status)
        self._equip_tab= EquipmentTab(self._nb, self._status)
        self._spr_tab  = SpritesTab(self._nb, self._status)
        self._spell_tab= SpellsTab(self._nb, self._status)
        self._scr_tab  = ScriptsTab(self._nb, self._status)
        self._mod_tab  = ModelsTab(self._nb, self._status)

        self._nb.add(self._map_tab,   text="  World Map  ")
        self._nb.add(self._char_tab,  text="  Characters  ")
        self._nb.add(self._equip_tab, text="  Equipment  ")
        self._nb.add(self._spr_tab,   text="  Sprites  ")
        self._nb.add(self._spell_tab, text="  Spells  ")
        self._nb.add(self._scr_tab,   text="  Scripts  ")
        self._nb.add(self._mod_tab,   text="  3D Models  ")

        # Update header counts after brief delay
        self.after(2000, self._update_counts)

    def _update_counts(self):
        try:
            i3d_count = len(list(IMAGERY_ASSETS.rglob("*.i3d")))
            bmp_count = len(list(IMAGERY_ASSETS.rglob("*.bmp")))
            def_count = len(list(EXTRACT_DIR.rglob("*.def")))
            mp3_count = len(list(EXTRACT_DIR.rglob("*.mp3")))
            self._hdr_counts.config(
                text=f"{i3d_count} models  |  {bmp_count} sprites  |  "
                     f"{def_count} scripts  |  {mp3_count} music tracks")
        except Exception:
            pass


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
