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
from pathlib import Path
from typing import Optional, List, Dict, Tuple

# ─── Paths ───────────────────────────────────────────────────────────────────
GAME_DIR    = Path("C:/GOG Games/Revenant")
EXTRACT_DIR = GAME_DIR / "_extracted"
ENGINE_DIR  = GAME_DIR / "RevEngine"
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

    # Split into CHARACTER blocks
    pattern = re.compile(
        r'CHARACTER\s+"([^"]+)"[^\n]*\nBEGIN(.*?)END',
        re.DOTALL
    )
    for m in pattern.finditer(text):
        name  = m.group(1).strip()
        body  = m.group(2)
        entry = {"name": name}

        # Extract key tags
        def _get(tag, default=""):
            rx = re.search(rf'\b{tag}\s+"?([^"\n]+)"?', body)
            return rx.group(1).strip() if rx else default

        def _get_nums(tag):
            rx = re.search(rf'\b{tag}\b\s+([\d,\s\-]+)', body)
            if rx:
                return [int(x.strip()) for x in rx.group(1).split(',') if x.strip().lstrip('-').isdigit()]
            return []

        entry["class"]    = _get("CLASS")
        entry["groups"]   = _get("GROUPS")
        entry["enemies"]  = _get("ENEMIES")

        sight = _get_nums("SIGHT")
        entry["sight"] = sight[2] if len(sight) >= 3 else 0

        block = _get_nums("BLOCK")
        entry["block_pct"] = block[0] if block else 0

        entry["weapon_dmg"] = _get_nums("WEAPONDAMAGE")[0] if _get_nums("WEAPONDAMAGE") else 0

        # Count ATTACKs
        entry["attack_count"] = len(re.findall(r'\bATTACK\b', body))

        # Count IMPACTs
        entry["impact_count"] = len(re.findall(r'\bIMPACT\b', body))

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
    try:
        raw = path.read_bytes()
        if len(raw) < 0x1C or raw[:4] != b'CGSR':
            return 0
        return struct.unpack_from('<I', raw, 0x18)[0]
    except Exception:
        return 0


def get_automap_tiles(zone: int) -> List[Path]:
    """Get all automap BMP tiles for a zone number."""
    tiles = []
    automap_dir = AHKUILON / "Automaps"
    if not automap_dir.exists():
        return tiles
    prefix = f"{zone}_"
    for f in automap_dir.iterdir():
        if f.suffix.lower() == '.bmp' and f.name.startswith(prefix):
            tiles.append(f)
    return tiles


def get_available_zones() -> List[int]:
    """Return sorted list of zone numbers that have automap tiles."""
    automap_dir = AHKUILON / "Automaps"
    if not automap_dir.exists():
        return []
    zones = set()
    for f in automap_dir.iterdir():
        if f.suffix.lower() == '.bmp':
            parts = f.stem.split('_')
            if parts:
                try:
                    zones.add(int(parts[0]))
                except ValueError:
                    pass
    return sorted(zones)


def stitch_zone_map(zone: int, tile_size: int = 64) -> Optional["Image.Image"]:
    """Stitch all automap tiles for a zone into a single PIL Image.

    Tile filenames use the format:  Zone_Y_X.bmp
    Y is a *signed* integer (negative values are common, e.g. 0_-10_25.bmp).
    X may also be non-zero-based (e.g. 15-39 for zone 0).
    We normalise both axes so the grid starts at (0, 0).
    """
    if not HAS_PIL:
        return None
    tiles = get_automap_tiles(zone)
    if not tiles:
        return None

    # Parse (Y, X) from filename: zone_Y_X.bmp  — Y/X are signed integers
    coords = []
    for t in tiles:
        parts = t.stem.split('_')
        # stem may look like "0_-10_25" → split gives ['0', '-10', '25']
        # but "0_-10" splits into ['0', '', '10'] with a leading '-' issue on
        # some Python versions, so we re-join after the zone prefix to be safe.
        if len(parts) < 3:
            continue
        try:
            # parts[0] = zone, parts[1] = Y (may be negative), parts[2] = X
            y_val = int(parts[1])
            x_val = int(parts[2])
            coords.append((y_val, x_val, t))
        except ValueError:
            pass

    if not coords:
        return None

    min_y = min(y for y, x, _ in coords)
    min_x = min(x for y, x, _ in coords)
    max_y = max(y for y, x, _ in coords)
    max_x = max(x for y, x, _ in coords)

    n_cols = max_x - min_x + 1
    n_rows = max_y - min_y + 1

    canvas_w = n_cols * tile_size
    canvas_h = n_rows * tile_size
    canvas = Image.new('RGB', (canvas_w, canvas_h), (20, 20, 30))

    for y_val, x_val, path in coords:
        norm_col = x_val - min_x
        # Y axis: most-negative Y (northernmost) maps to top row (row 0)
        norm_row = y_val - min_y
        try:
            tile = Image.open(path).convert('RGB').resize((tile_size, tile_size), Image.NEAREST)
            canvas.paste(tile, (norm_col * tile_size, norm_row * tile_size))
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

ZONE_NAMES = {
    0:  "Ahkuilon (Main World)",
    2:  "Dungeon Zone 2",
    3:  "Interior Zone 3",
    4:  "Interior Zone 4",
    5:  "Interior Zone 5",
}
for _z in range(30, 60):
    ZONE_NAMES.setdefault(_z, f"Zone {_z}")


class WorldMapTab(tk.Frame):
    def __init__(self, parent, status: StatusBar):
        super().__init__(parent, bg=BG_MID)
        self._status  = status
        self._photo   = None
        self._img     = None
        self._zoom    = 1.0
        self._zones   = []
        self._cur_zone = tk.IntVar(value=0)
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
        self._zones = get_available_zones()
        if not self._zones:
            self._status.set("No automap tiles found in _extracted/Ahkuilon/Automaps/")
            return

        labels = [f"{z}  —  {ZONE_NAMES.get(z, f'Zone {z}')}" for z in self._zones]
        self._zone_combo['values'] = labels
        self._zone_combo.current(0)

        # Check for pre-rendered zone 0
        cached_path = RENDERS_DIR / "world_map_zone0.png"
        if cached_path.exists() and HAS_PIL:
            self._status.set("Loading pre-rendered world map...")
            img = Image.open(cached_path)
            self._cache[0] = img
            self._img = img
            self._zoom = 0.25
            self._refresh_display()
            tiles = get_automap_tiles(0)
            self._tile_lbl.config(
                text=f"Zone 0: {len(tiles)} tiles  |  {img.width}x{img.height}px")
            self._status.set(
                f"World Map loaded — {len(tiles)} tiles stitched into "
                f"{img.width}x{img.height}px")
        else:
            self._stitch_current()

    def _on_zone_change(self, _=None):
        idx = self._zone_combo.current()
        if 0 <= idx < len(self._zones):
            z = self._zones[idx]
            self._cur_zone.set(z)
            if z in self._cache:
                self._img  = self._cache[z]
                self._zoom = 0.25
                self._refresh_display()
                self._tile_lbl.config(
                    text=f"Zone {z}: {self._img.width}x{self._img.height}px (cached)")
            else:
                self._stitch_current()

    def _stitch_current(self):
        idx = self._zone_combo.current()
        zone = self._zones[idx] if 0 <= idx < len(self._zones) else 0
        self._status.set(f"Stitching zone {zone}...")

        def _worker():
            img = stitch_zone_map(zone)
            self.after(0, lambda: self._on_stitch_done(zone, img))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_stitch_done(self, zone: int, img):
        if img is None:
            self._status.set(f"No tiles found for zone {zone}")
            return
        self._cache[zone] = img
        self._img   = img
        self._zoom  = 0.25
        self._refresh_display()
        tiles = get_automap_tiles(zone)
        self._tile_lbl.config(
            text=f"Zone {zone}: {len(tiles)} tiles  |  {img.width}x{img.height}px")
        self._status.set(
            f"Zone {zone} stitched — {len(tiles)} tiles, {img.width}x{img.height}px")

    def _set_zoom(self, z: float):
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
        self._detail_name.pack(anchor="w", pady=(0, 8))

        self._detail_portrait = tk.Label(right, bg=BG_PANEL)
        self._detail_portrait.pack(anchor="w", pady=4)

        self._detail_text = tk.Text(right, bg=BG_PANEL, fg=FG_TEXT,
                                     font=("Consolas", 9),
                                     relief="flat", wrap="word",
                                     state="disabled", height=28)
        self._detail_text.pack(fill="both", expand=True, pady=(8, 0))

        # Configure text tags
        self._detail_text.tag_configure("h",  foreground=ACCENT,  font=("Segoe UI", 9, "bold"))
        self._detail_text.tag_configure("v",  foreground=FG_TEXT, font=("Consolas", 9))
        self._detail_text.tag_configure("kv", foreground=ACCENT2, font=("Segoe UI", 9))
        self._detail_text.tag_configure("dim",foreground=FG_DIM,  font=("Segoe UI", 8))

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
                        or flt in c.get("groups", "").lower()]
        self._render_gallery(filtered)
        self._count_lbl.config(text=f"{len(filtered)} / {len(self._chars)}")

    def _show_detail(self, char: Dict):
        name = char["name"]
        self._detail_name.config(text=name)

        # Portrait
        photo = self._photos.get(name)
        if photo:
            self._detail_portrait.config(image=photo)
            self._detail_portrait._photo = photo
        else:
            self._detail_portrait.config(image="", text="")

        # i3d info
        i3d_path = find_char_i3d(name)
        anim_count = 0
        i3d_name = "not found"
        if i3d_path:
            i3d_name   = i3d_path.name
            anim_count = parse_i3d_anim_count(i3d_path)

        # Build detail text
        txt = self._detail_text
        txt.configure(state="normal")
        txt.delete("1.0", "end")

        def row(label, value, tag="v"):
            txt.insert("end", f"  {label:<18}", "kv")
            txt.insert("end", f"{value}\n", tag)

        txt.insert("end", "IDENTITY\n", "h")
        row("Name",       name)
        row("Class",      char.get("class", "—") or "—")
        row("Group",      char.get("groups", "—") or "—")

        txt.insert("end", "\nCOMBAT\n", "h")
        row("Enemies",    char.get("enemies", "—") or "—")
        row("Block %",    f"{char.get('block_pct',0)}%")
        row("Weapon DMG", str(char.get("weapon_dmg",0)))
        row("Sight range",str(char.get("sight", 0)))
        row("Attacks",    str(char.get("attack_count", 0)))
        row("Impacts",    str(char.get("impact_count", 0)))

        txt.insert("end", "\n3D MODEL\n", "h")
        row("File",       i3d_name)
        row("Anim states",str(anim_count))

        txt.configure(state="disabled")


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
    Orthographic wireframe viewer for i3d geometry.
    Drag to rotate, scroll wheel to zoom.
    Falls back to a point cloud when no face data is available.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG_DARK, **kwargs)
        self._verts  : List[tuple] = []
        self._faces  : List[tuple] = []
        self._az     = 0.4    # azimuth  (radians, rotation around Y)
        self._el     = 0.25   # elevation (radians, rotation around X)
        self._zoom   = 1.0
        self._drag   = None   # (x, y, az0, el0) drag start state
        self._build()

    def _build(self):
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

    def load(self, verts: list, faces: list, info: str = ""):
        self._verts  = verts
        self._faces  = faces
        self._az     = 0.4
        self._el     = 0.25
        self._zoom   = 1.0
        self._info_lbl.config(text=info or ("No geometry" if not verts else ""))
        self._redraw()

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
        c  = self._canvas
        cw = c.winfo_width()  or 300
        ch = c.winfo_height() or 240
        c.delete("all")

        if not self._verts:
            c.create_text(cw // 2, ch // 2, text="No geometry decoded",
                          fill=FG_MUTED, font=("Segoe UI", 10))
            return

        # ── Rotate vertices ────────────────────────────────────────────────
        az, el = self._az, self._el
        caz, saz = math.cos(az), math.sin(az)
        cel, sel = math.cos(el), math.sin(el)

        rot = []
        for x, y, z in self._verts:
            # Y-axis rotation (azimuth)
            rx =  x * caz + z * saz
            ry =  y
            rz = -x * saz + z * caz
            # X-axis rotation (elevation)
            rot.append((rx,
                         ry * cel - rz * sel,
                         ry * sel + rz * cel))

        # ── Scale to fit canvas ────────────────────────────────────────────
        xs = [v[0] for v in rot]; ys = [v[1] for v in rot]
        cx_v = (max(xs) + min(xs)) / 2
        cy_v = (max(ys) + min(ys)) / 2
        span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-6)
        scale = self._zoom * min(cw, ch) * 0.42 / span

        def proj(v):
            return (int(cw // 2 + (v[0] - cx_v) * scale),
                    int(ch // 2 - (v[1] - cy_v) * scale),
                    v[2])

        pts = [proj(v) for v in rot]

        # ── Draw faces or point cloud ──────────────────────────────────────
        if self._faces:
            # Painter's algorithm: sort faces back→front (lowest avg Z first)
            def _fz(f):
                a, b, fc = f
                if a < len(pts) and b < len(pts) and fc < len(pts):
                    return (pts[a][2] + pts[b][2] + pts[fc][2]) / 3
                return 0

            edge_col  = "#3a5a9a"
            for face in sorted(self._faces, key=_fz):
                a, b, fc = face
                if a >= len(pts) or b >= len(pts) or fc >= len(pts):
                    continue
                ax, ay, _ = pts[a]
                bx, by, _ = pts[b]
                cx_, cy_, _ = pts[fc]
                c.create_line(ax, ay, bx, by, fill=edge_col, width=1)
                c.create_line(bx, by, cx_, cy_, fill=edge_col, width=1)
                c.create_line(cx_, cy_, ax, ay, fill=edge_col, width=1)
        else:
            # Point cloud
            dot_col = "#5080d0"
            r = max(1, int(scale * 0.05))
            for px, py, _ in pts:
                c.create_oval(px - r, py - r, px + r, py + r,
                              fill=dot_col, outline="")

        c.create_text(6, 6, text="Drag to rotate  ·  Scroll to zoom",
                      anchor="nw", fill=FG_MUTED, font=("Segoe UI", 8))


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
        tk.Button(hdr, text="Export OBJ", bg=ACCENT3, fg="#000000",
                  relief="flat", font=("Segoe UI", 9, "bold"), padx=8,
                  command=self._export_obj).pack(side="right")

        ttk.Separator(det).pack(fill="x")

        # Vertical split: metadata text (top) + 3D viewer (bottom)
        vpane = tk.PanedWindow(det, orient="vertical", bg=BG_DARK,
                               sashwidth=5, sashrelief="flat")
        vpane.pack(fill="both", expand=True)

        meta_frame = tk.Frame(vpane, bg=BG_PANEL, padx=8, pady=4)
        vpane.add(meta_frame, minsize=120)
        self._det_text = tk.Text(meta_frame, bg=BG_PANEL, fg=FG_TEXT,
                                  font=("Consolas", 9), relief="flat",
                                  state="disabled", wrap="word", height=9)
        self._det_text.pack(fill="both", expand=True)
        self._det_text.tag_configure("h",   foreground=ACCENT,  font=("Segoe UI", 10, "bold"))
        self._det_text.tag_configure("kv",  foreground=ACCENT2, font=("Segoe UI", 9))
        self._det_text.tag_configure("list",foreground=ACCENT3, font=("Consolas", 8))

        self._viewer = ModelViewer3D(vpane)
        vpane.add(self._viewer, minsize=200)

        self._current_geom = None   # holds last decoded I3DGeometry

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
            # Quick geometry read
            verts = 0
            try:
                raw = f.read_bytes()
                count = struct.unpack_from('<I', raw, 0x18)[0]
                geom_off = 0x54 + count * 76
                if len(raw) >= geom_off + 8:
                    verts = struct.unpack_from('<I', raw, geom_off + 4)[0]
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

        # Read animation state names
        state_names = []
        try:
            raw      = m["path"].read_bytes()
            count    = struct.unpack_from('<I', raw, 0x18)[0]
            def_name = raw[0x1C:0x40].split(b'\x00')[0].decode('ascii', 'replace')
            for i in range(min(count, 500)):
                off        = 0x54 + i * 76
                name_bytes = raw[off + 20:off + 76].split(b'\x00')[0]
                sname      = name_bytes.decode('ascii', 'replace').strip()
                if sname:
                    state_names.append(sname)
        except Exception:
            def_name = "?"

        txt = self._det_text
        txt.configure(state="normal")
        txt.delete("1.0", "end")
        txt.insert("end", f"{m['name']}\n", "h")

        def row(k, v):
            txt.insert("end", f"  {k:<20}", "kv")
            txt.insert("end", f"{v}\n")

        row("Folder",        m["folder"])
        row("File size",     f"{m['size_kb']:,} KB  ({m['path'].stat().st_size:,} bytes)")
        row("Anim states",   str(m["anims"]))
        row("Est. vertices", str(m["verts"]) if m["verts"] else "unknown")
        row("Default state", def_name)

        if state_names:
            txt.insert("end", f"\nAnimation States ({len(state_names)}):\n", "kv")
            for sn in state_names:
                txt.insert("end", f"  • {sn}\n", "list")

        txt.configure(state="disabled")

        # ── Async geometry decode → 3D viewer ────────────────────────────────
        self._current_geom = None
        self._viewer.load([], [], "Decoding geometry…")

        def _decode(path=m["path"]):
            try:
                from decoders.i3d import decode_i3d_geometry
                geom = decode_i3d_geometry(path)
            except Exception:
                geom = None
            self._current_geom = geom
            if geom:
                info = (f"{len(geom.vertices):,} verts  ·  "
                        f"{len(geom.faces):,} faces  ·  "
                        f"stride {geom.stride} B")
            else:
                info = "Geometry format not detected"
            self.after(0, lambda: self._viewer.load(
                geom.vertices if geom else [],
                geom.faces    if geom else [],
                info,
            ))

        threading.Thread(target=_decode, daemon=True).start()

    def _export_obj(self):
        """Save current model geometry as Wavefront OBJ."""
        if self._current_geom is None:
            self._status.set("No geometry — select a model and wait for decode first")
            return
        geom = self._current_geom
        default_name = geom.path.stem + ".obj"
        out = filedialog.asksaveasfilename(
            title="Export OBJ",
            initialfile=default_name,
            defaultextension=".obj",
            filetypes=[("Wavefront OBJ", "*.obj"), ("All files", "*.*")],
        )
        if not out:
            return
        from decoders.i3d import export_obj
        if export_obj(geom, Path(out)):
            self._status.set(f"OBJ saved: {Path(out).name}  "
                             f"({len(geom.vertices):,} verts, {len(geom.faces):,} faces)")
        else:
            self._status.set("OBJ export failed")


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
            if i2d_path.exists():
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
                if i2d_path.exists():
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
