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
_DEFAULT_GAME_DIR = Path(__file__).resolve().parent / "game"

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
EXTRACT_DIR = Path(__file__).parent.resolve() / "extracted"
ENGINE_DIR  = Path(__file__).parent.resolve()
IMAGERY     = EXTRACT_DIR / "imagery"
RESOURCES   = EXTRACT_DIR / "resources"
AHKUILON    = EXTRACT_DIR / "Ahkuilon"
RENDERS_DIR = ENGINE_DIR / "test_renders"

_CONFIG_PATH = ENGINE_DIR / "revengine.json"

from core.config import Config, resolve_game_dir
from core.constants import HAS_PIL
from ui.app import AssetStudio

def main():
    engine_dir = Path(__file__).parent.resolve()
    config = Config(engine_dir)
    config.game_dir = resolve_game_dir(config.game_dir)

    if not config.extract_dir.exists():
        print(f"ERROR: Extracted files not found at {config.extract_dir}")
        print("Run: python setup.py   first.")
        # sys.exit(1) # Don't exit here so we can at least open the UI if possible? No, we should probably exit or warn.

    if not HAS_PIL:
        print("ERROR: Pillow not installed. Run: pip install Pillow")
        # sys.exit(1)

    app = AssetStudio(config)
    app.mainloop()

if __name__ == "__main__":
    main()
