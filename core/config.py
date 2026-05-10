import os
import json
import logging
from pathlib import Path

log = logging.getLogger("RevEngine.Config")

_HERE = Path(__file__).resolve().parent.parent
_DEFAULT_GAME_DIR = _HERE / "game"

class Config:
    def __init__(self, engine_dir: Path):
        self.engine_dir = engine_dir.resolve()
        self.game_dir = _DEFAULT_GAME_DIR
        self.extract_dir = self.engine_dir / "extracted"
        self.renders_dir = self.engine_dir / "test_renders"
        self.config_path = self.engine_dir / "revengine.json"

        self.load()

    @property
    def imagery(self): return self.extract_dir / "imagery"
    @property
    def resources(self): return self.extract_dir / "resources"
    @property
    def ahkuilon(self): return self.extract_dir / "Ahkuilon"
    @property
    def imagery_assets(self): return self.imagery / "Imagery"
    @property
    def thumbnails(self): return self.imagery / "Thumbnails"
    @property
    def char_def(self): return self.imagery / "char.def"
    @property
    def weapon_def(self): return self.imagery / "weapon.def"
    @property
    def armor_def(self): return self.imagery / "armor.def"
    @property
    def spell_def(self): return self.resources / "spell.def"

    def load(self):
        if not self.config_path.exists():
            return
        try:
            cfg = json.loads(self.config_path.read_text())
            if "game_dir" in cfg: self.game_dir = Path(cfg["game_dir"])
            if "extract_dir" in cfg: self.extract_dir = Path(cfg["extract_dir"])
            if "renders_dir" in cfg: self.renders_dir = Path(cfg["renders_dir"])
        except Exception as e:
            log.error(f"Failed to load config: {e}")

    def save(self):
        try:
            self.config_path.write_text(json.dumps({
                "game_dir": str(self.game_dir),
                "extract_dir": str(self.extract_dir),
                "renders_dir": str(self.renders_dir),
            }, indent=2))
        except Exception as e:
            log.error(f"Failed to save config: {e}")

def resolve_game_dir(default_dir: Path) -> Path:
    import sys
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg in ("--game-dir", "--game_dir") and i < len(sys.argv):
            return Path(sys.argv[i + 1])
        if arg.startswith("--game-dir="):
            return Path(arg.split("=", 1)[1])
        if arg.startswith("--game_dir="):
            return Path(arg.split("=", 1)[1])
    return default_dir
