import re
import struct
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from core.constants import *

def _read_def(path: Path) -> str:
    """Read a .def file, tolerating latin-1 encoding."""
    try:
        return path.read_text(encoding='latin-1')
    except Exception:
        return ""

def parse_char_def(config) -> List[Dict]:
    """Parse char.def into a list of character dicts."""
    text = _read_def(config.char_def)
    chars = []
    pattern = re.compile(r'CHARACTER\s+"([^"]+)"[^\n]*\nBEGIN(.*?)END', re.DOTALL)
    for m in pattern.finditer(text):
        name, body = m.group(1).strip(), m.group(2)
        entry = {"name": name, "_raw": body.strip()}
        def _get(tag, default=""):
            rx = re.search(rf'\b{tag}\s+"?([^"\n]+)"?', body)
            return rx.group(1).strip() if rx else default
        def _get_nums(tag):
            rx = re.search(rf'\b{tag}\b\s+([\d,\s\-]+)', body)
            if rx: return [int(x.strip()) for x in rx.group(1).split(',') if x.strip().lstrip('-').isdigit()]
            return []
        entry["class"], entry["groups"], entry["enemies"], entry["script"], entry["sound"] = _get("CLASS"), _get("GROUPS"), _get("ENEMIES"), _get("SCRIPT"), _get("SOUND")
        sight = _get_nums("SIGHT")
        entry["sight"] = sight[2] if len(sight) >= 3 else (sight[0] if sight else 0)
        entry["block_pct"] = _get_nums("BLOCK")[0] if _get_nums("BLOCK") else 0
        entry["weapon_dmg"] = _get_nums("WEAPONDAMAGE")[0] if _get_nums("WEAPONDAMAGE") else 0
        entry["health"] = _get_nums("HEALTH")[0] if _get_nums("HEALTH") else 0
        entry["speed"] = _get_nums("SPEED")[0] if _get_nums("SPEED") else 0
        attack_blocks = re.findall(r'ATTACK\s+"?([^"\n]+)"?\s+BEGIN(.*?)END', body, re.DOTALL)
        entry["attacks"] = []
        for aname, abody in attack_blocks:
            atk = {"name": aname.strip()}
            dmg = re.search(r'\bDAMAGE\b\s+([\d\s,]+)', abody)
            atk["damage"] = dmg.group(1).strip() if dmg else ""
            anim = re.search(r'\bANIMATION\s+"?([^"\n]+)"?', abody)
            atk["anim"] = anim.group(1).strip() if anim else ""
            entry["attacks"].append(atk)
        entry["attack_count"] = len(entry["attacks"]) or len(re.findall(r'\bATTACK\b', body))
        impact_blocks = re.findall(r'IMPACT\s+"?([^"\n]+)"?\s+BEGIN(.*?)END', body, re.DOTALL)
        entry["impacts"] = [{"name": iname.strip()} for iname, ibody in impact_blocks]
        entry["impact_count"] = len(entry["impacts"]) or len(re.findall(r'\bIMPACT\b', body))
        entry["spells"] = [s.strip() for s in re.findall(r'\bSPELL\s+"?([^"\n]+)"?', body)]
        entry["anim_refs"] = sorted(set(a.strip() for a in re.findall(r'\bANIMATION\s+"?([^"\n]+)"?', body)))
        chars.append(entry)
    return chars

def parse_weapon_def(config) -> List[Dict]:
    text = _read_def(config.weapon_def)
    weapons = []
    pattern = re.compile(r'WEAPON\s+"([^"]+)"\s*\nBEGIN(.*?)END', re.DOTALL)
    for m in pattern.finditer(text):
        name, body = m.group(1).strip(), m.group(2)
        nums_m = re.search(r'BASICMODS\s+([\d,\s\-]+)', body)
        nums = [int(x.strip()) for x in nums_m.group(1).split(',') if x.strip().lstrip('-').isdigit()] if nums_m else []
        w = {"name": name, "eq_slot": nums[0] if len(nums)>0 else 0, "type": nums[1] if len(nums)>1 else 0, "damage": nums[2] if len(nums)>2 else 0, "combining": nums[3] if len(nums)>3 else 0, "poison": nums[4] if len(nums)>4 else 0, "value": nums[5] if len(nums)>5 else 0, "damage_mod": nums[6] if len(nums)>6 else 0, "min_str": nums[7] if len(nums)>7 else 0}
        w["type_name"] = WEAPON_TYPE.get(w["type"], "?")
        weapons.append(w)
    return weapons

def parse_armor_def(config) -> List[Dict]:
    text = _read_def(config.armor_def)
    armors = []
    pattern = re.compile(r'ARMOR\s+"([^"]+)"\s*\nBEGIN(.*?)END', re.DOTALL)
    for m in pattern.finditer(text):
        name, body = m.group(1).strip(), m.group(2)
        nums_m = re.search(r'BASICMODS\s+([\d,\s\-]+)', body)
        nums = [int(x.strip()) for x in nums_m.group(1).split(',') if x.strip().lstrip('-').isdigit()] if nums_m else []
        a = {"name": name, "eq_slot": nums[0] if len(nums)>0 else 0, "protection": nums[1] if len(nums)>1 else 0, "combining": nums[2] if len(nums)>2 else 0, "resist_psn": nums[3] if len(nums)>3 else 0, "stealth": nums[4] if len(nums)>4 else 0, "value": nums[5] if len(nums)>5 else 0, "min_str": nums[6] if len(nums)>6 else 0, "min_con": nums[7] if len(nums)>7 else 0}
        a["slot_name"] = ARMOR_SLOT.get(a["eq_slot"], "?")
        armors.append(a)
    return armors

def parse_spell_def(config) -> List[Dict]:
    text = _read_def(config.spell_def)
    spells = []
    pattern = re.compile(r'SPELL\s+"([^"]+)"\s*\nBEGIN(.*?)END', re.DOTALL)
    variant_re = re.compile(r'VARIANT\s+"([^"]+)"\s*,\s*\w+\s*,\s*"([^"]*)"\s*,\s*"([^"]*)"\s*,\s*(\d+)(?:\s*,\s*(\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+))?', re.DOTALL)
    for m in pattern.finditer(text):
        name, body = m.group(1).strip(), m.group(2)
        def _tag(t):
            rx = re.search(rf'\b{t}\b\s+(-?[\w\.]+)', body)
            return rx.group(1) if rx else ""
        desc_m = re.search(r'\bDESCRIPTION\s+"([^"]+)"', body)
        icon_m = re.search(r'\bICONNAME\s+"([^"]+)"', body)
        anim_m = re.search(r'\bANIMATION\s+"?([^"\n]+)"?', body)
        dt_m = re.search(r'\bDAMAGETYPE\s+(\w+)', body)
        variants = []
        for vm in variant_re.finditer(body):
            talis_str = vm.group(2).strip()
            variants.append({'name': vm.group(1).strip(), 'talismans': talis_str, 'talis_names': [TALISMAN_MAP.get(c.upper(), c) for c in talis_str], 'effect': vm.group(3).strip(), 'mana': int(vm.group(4)), 'min_d': vm.group(6) or "—", 'max_d': vm.group(7) or "—"})
        spells.append({"name": name, "icon_name": icon_m.group(1).strip() if icon_m else name, "mana": str(variants[0]['mana']) if variants else _tag("MANA") or "—", "damage": _tag("DAMAGE"), "duration": _tag("DURATION"), "description": desc_m.group(1).strip() if desc_m else "", "animation": anim_m.group(1).strip() if anim_m else "", "damage_type": dt_m.group(1) if dt_m else "", "variants": variants})
    return spells

def find_char_i3d(config, char_name: str) -> Optional[Path]:
    chars_dir = config.imagery_assets / "Chars"
    if not chars_dir.exists(): return None
    norm = re.sub(r'[^a-z0-9]', '', char_name.lower())
    for f in chars_dir.iterdir():
        if f.suffix.lower() == '.i3d':
            s_norm = re.sub(r'[^a-z0-9]', '', f.stem.lower())
            if s_norm == norm or norm.startswith(s_norm) or s_norm.startswith(norm[:4]): return f
    return None

def find_portrait(config, char_name: str) -> Optional[Path]:
    chars_dir = config.imagery_assets / "Chars"
    if not chars_dir.exists(): return None
    norm = char_name.lower().split()[0]
    for f in chars_dir.iterdir():
        if f.suffix.lower() == '.bmp' and f.stem.lower() == norm: return f
    return None

def parse_i3d_anim_states(path: Path) -> List[Dict]:
    states = []
    import struct
    try:
        raw = path.read_bytes()
        if len(raw) < 84 or raw[:4] != b'CGSR': return states
        topbm, hdrsize = struct.unpack_from('<H', raw, 0x06)[0], struct.unpack_from('<I', raw, 0x10)[0]
        n_states = topbm + 1
        for i in range(n_states):
            off = 52 + i * 32
            if off + 32 > hdrsize: break
            frames = struct.unpack_from('<I', raw, off + 4)[0]
            name = raw[off + 8: off + 16].split(b'\x00')[0].decode('ascii', errors='replace')
            w, h = struct.unpack_from('<HH', raw, off + 24) if off + 28 <= hdrsize else (0,0)
            states.append({"name": name or f"state{i}", "frames": frames, "width": w, "height": h})
    except Exception: pass
    return states

def all_automap_dirs(config) -> List[Path]:
    if not config.extract_dir.exists(): return []
    return [c / "Automaps" for c in config.extract_dir.iterdir() if c.is_dir() and (c / "Automaps").is_dir()]

def get_all_zone_keys(config) -> List[Tuple[str, int]]:
    seen = set()
    for adir in all_automap_dirs(config):
        module = adir.parent.name
        for f in adir.rglob("*.bmp"):
            parts = f.stem.split('_')
            if len(parts) >= 3:
                try: seen.add((module, int(parts[0])))
                except ValueError: pass
    return sorted(seen, key=lambda mk: (mk[0].lower() != "ahkuilon", mk[0].lower(), mk[1]))

def get_automap_tiles(config, zone: int, module: str = "Ahkuilon") -> List[Path]:
    adir = config.extract_dir / module / "Automaps"
    dirs = [adir] if adir.exists() else all_automap_dirs(config)
    tiles = []
    for d in dirs:
        for f in d.rglob("*.bmp"):
            parts = f.stem.split('_')
            if len(parts) >= 3:
                try:
                    if int(parts[0]) == zone: tiles.append(f)
                except ValueError: pass
    return tiles

def stitch_zone_map(config, zone: int, module: str = "Ahkuilon", tile_size: int = 64) -> Optional["Image.Image"]:
    if not HAS_PIL: return None
    from PIL import Image
    tiles = get_automap_tiles(config, zone, module)
    if not tiles: return None
    coords = []
    for t in tiles:
        parts = t.stem.split('_')
        try: coords.append((int(parts[1]), int(parts[2]), t))
        except (ValueError, IndexError): pass
    if not coords: return None
    min_x, max_x = min(x for x,y,t in coords), max(x for x,y,t in coords)
    min_y, max_y = min(y for x,y,t in coords), max(y for x,y,t in coords)
    canvas = Image.new('RGB', (tile_size * (max_x - min_x + 1), tile_size * (max_y - min_y + 1)), (20, 20, 30))
    for xv, yv, path in coords:
        try:
            tile = Image.open(path).convert('RGB').resize((tile_size, tile_size), Image.NEAREST)
            canvas.paste(tile, (tile_size * (xv - min_x), tile_size * (yv - min_y)))
        except Exception: pass
    return canvas

def make_placeholder_portrait(name: str, size: int = 96) -> Optional["Image.Image"]:
    if not HAS_PIL: return None
    from PIL import Image, ImageDraw, ImageFont
    h = hashlib.md5(name.encode()).digest()
    color = (40 + (h[0] % 100), 40 + (h[1] % 100), 80 + (h[2] % 100))
    img = Image.new('RGB', (size, size), color); draw = ImageDraw.Draw(img)
    for i in range(4): draw.rectangle([i, i, size - 1 - i, size - 1 - i], outline=tuple(max(0, x - i * 20) for x in color))
    initials = ''.join(w[0].upper() for w in name.split()[:2])
    try: font = ImageFont.truetype("arial.ttf", size // 3)
    except Exception: font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), initials, font=font); tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) // 2, (size - th) // 2), initials, fill=(220, 230, 255), font=font)
    return img

def decode_tn_pixels(raw: bytes) -> Optional[bytes]:
    import struct
    if len(raw) < 768: return None
    pal = []
    for i in range(256):
        w = struct.unpack_from('<H', raw, i*2)[0]
        pal.append((((w >> 10) & 0x1F) << 3, ((w >> 5) & 0x1F) << 3, (w & 0x1F) << 3, 0 if i == 0 else 255))
    px = []
    for i in range(512, 768): px.extend(pal[raw[i]])
    return bytes(px)

def load_tn_image(path: Path, size: int = 48) -> Optional["Image.Image"]:
    if not HAS_PIL: return None
    from PIL import Image
    try:
        px = decode_tn_pixels(path.read_bytes())
        if px: return Image.frombytes('RGBA', (16, 16), px).resize((size, size), Image.NEAREST)
    except Exception: pass
    return None

def decode_dat_frame(dat_path: Path, frame_idx: int, size: Optional[int] = None) -> Optional["Image.Image"]:
    if not HAS_PIL: return None
    from PIL import Image
    import struct
    try:
        raw = dat_path.read_bytes()
        if len(raw) < 20 or raw[:4] != b'CGSR': return None
        n = raw[4]
        if frame_idx < 0 or frame_idx >= n: return None
        offsets = [struct.unpack_from('<I', raw, 16 + i * 4)[0] for i in range(n)]
        abs_off = 16 + n * 4 + offsets[frame_idx]
        fd = raw[abs_off : (16 + n * 4 + offsets[frame_idx + 1] if frame_idx + 1 < n else len(raw))]
        for i in range(0, max(0, len(fd) - 76), 4):
            w, h = struct.unpack_from('<ii', fd, i)
            if not (1 <= w <= 2048 and 1 <= h <= 2048): continue
            ps = struct.unpack_from('<I', fd, i + 60)[0]
            ds = struct.unpack_from('<I', fd, i + 68)[0]
            if ps == 0 and ds == w * h * 2 and i + 72 + ds <= len(fd):
                img = bgr555_fast(fd[i + 72: i + 72 + ds], w, h)
                return img.resize((size, size), Image.LANCZOS) if size else img
    except Exception: pass
    return None

def bgr555_fast(px: bytes, w: int, h: int) -> "Image.Image":
    from PIL import Image
    import struct
    try:
        import numpy as np
        arr = np.frombuffer(px, dtype='<u2').reshape(h, w)
        r = ((arr >> 10) & 0x1F).astype(np.uint8) << 3
        g = ((arr >> 5) & 0x1F).astype(np.uint8) << 3
        b = (arr & 0x1F).astype(np.uint8) << 3
        a = np.where(arr == 0, np.uint8(0), np.uint8(255))
        return Image.fromarray(np.stack([r, g, b, a], axis=-1), 'RGBA')
    except ImportError: pass
    img = Image.new('RGBA', (w, h)); pix = img.load()
    for idx in range(w * h):
        word = struct.unpack_from('<H', px, idx * 2)[0]
        pix[idx % w, idx // w] = (((word >> 10) & 0x1F) << 3, ((word >> 5) & 0x1F) << 3, (word & 0x1F) << 3, 0 if word == 0 else 255)
    return img

def parse_script_objects(text: str) -> List[Dict]:
    objects = []; current = None
    _OBJECT_RE = re.compile(r'OBJECT\s+"([^"]+)"', re.IGNORECASE)
    _CUBE_RE = re.compile(r'CUBE\s+\w+\s+(-?\d+),(-?\d+),(-?\d+)\s+(-?\d+),(-?\d+),(-?\d+)', re.IGNORECASE)
    for line in text.splitlines():
        m = _OBJECT_RE.search(line)
        if m: current = m.group(1)
        c = _CUBE_RE.search(line)
        if c and current:
            x1,y1,z1,x2,y2,z2 = (int(c.group(i)) for i in range(1, 7))
            objects.append({"name":current, "cx":(x1+x2)//2, "cy":(y1+y2)//2})
    return objects

def load_spell_icon(cfg, icon_name: str, size: int = 48) -> Optional["Image.Image"]:
    magic_dir = cfg.thumbnails / "Magic"
    if not magic_dir.exists(): return None
    norm = icon_name.lower().replace(" ", "").replace("-", "")
    for f in magic_dir.iterdir():
        if f.suffix.lower() == '.tn':
            fn = f.stem.lower().replace(" ", "").replace("-", "")
            if fn == norm: return load_tn_image(f, size)
    return None

def load_talisman_icons(cfg, size: int = 24) -> Dict[str, "ImageTk.PhotoImage"]:
    from PIL import ImageTk
    result = {}
    magic_dir = cfg.thumbnails / "Magic"
    if not magic_dir.exists(): return result
    for name in TALISMAN_MAP.values():
        fn = magic_dir / f"{name.lower()}.tn"
        if fn.exists():
            img = load_tn_image(fn, size)
            if img: result[name] = ImageTk.PhotoImage(img)
    return result

def scan_dat_frames(path: Path) -> int:
    """Return frame count from CGSR .dat header, 0 if not valid CGSR."""
    try:
        raw = path.read_bytes()
        if len(raw) >= 5 and raw[:4] == b'CGSR':
            return raw[4]
    except Exception:
        pass
    return 0

def get_unextracted_modules(config) -> List[str]:
    unextracted = []
    modules_dir = config.game_dir / "Modules"
    candidates = list(modules_dir.glob("*.rvm")) + list(config.game_dir.glob("*.rvm"))
    for rvm in candidates:
        stem = rvm.stem
        out_dir = config.extract_dir / stem
        if not out_dir.exists() or not any(out_dir.rglob("*")):
            unextracted.append(stem)
    return sorted(list(set(unextracted)))
