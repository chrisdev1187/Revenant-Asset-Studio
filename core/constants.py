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
