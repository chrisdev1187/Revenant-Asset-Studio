import os
import json
import logging
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from core.config import Config
from core.parsers import parse_char_def, parse_spell_def, parse_weapon_def, parse_armor_def
from decoders.i3d import decode_i3d_geometry, decode_i3d_textures
from decoders.gltf_export import export_gltf

log = logging.getLogger('RevEngine.Godot')

class GodotExporter:
    def __init__(self, config: Config, project_root: Path):
        self.cfg = config
        self.project_root = Path(project_root)
        self.dirs = {
            'models':   self.project_root / 'assets/models',
            'textures': self.project_root / 'assets/textures',
            'scenes':   self.project_root / 'scenes',
            'data':     self.project_root / 'data',
            'scripts':  self.project_root / 'scripts'
        }
        for d in self.dirs.values(): d.mkdir(parents=True, exist_ok=True)

    def export_character(self, i3d_path: Path) -> bool:
        stem = i3d_path.stem; out_path = self.dirs['models'] / f'{stem}.gltf'
        try:
            geom = decode_i3d_geometry(i3d_path)
            if not geom: return False
            textures = decode_i3d_textures(i3d_path)
            if export_gltf(geom, textures, out_path):
                self.generate_tscn_wrapper(stem, 'models')
                return True
        except Exception as e: log.error(f'Error: {e}')
        return False

    def generate_tscn_wrapper(self, name, type_dir):
        content = f'[gd_scene load_steps=2 format=3]\n[ext_resource type=PackedScene path=res://assets/{type_dir}/{name}.gltf id=1]\n[node name={name} instance=ExtResource(1)]\n'
        (self.dirs['models'] / f'{name}.tscn').write_text(content)

    def export_all_characters(self, status_cb=None):
        chars_dir = self.cfg.imagery_assets / 'Chars'
        if not chars_dir.exists(): return False, 'Chars dir not found'
        files = list(chars_dir.glob('*.i3d')); ok = 0
        for i, f in enumerate(files, 1):
            if status_cb: status_cb(f'Exporting {i}/{len(files)}: {f.name}')
            if self.export_character(f): ok += 1
        return True, f'Exported {ok} characters.'

    def export_game_data(self):
        data = {'characters': parse_char_def(self.cfg), 'spells': parse_spell_def(self.cfg), 'weapons': parse_weapon_def(self.cfg), 'armor': parse_armor_def(self.cfg)}
        (self.dirs['data'] / 'revenant_data.json').write_text(json.dumps(data, indent=2))
        return True, 'Metadata exported.'

    def generate_full_world_scene(self, status_cb=None):
        map_dir = self.cfg.ahkuilon / 'Map'
        if not map_dir.exists(): return False, 'Map directory not found'
        tscn = ['[gd_scene format=3]', '[node name=RevenantWorld type=Node3D]', '']
        chunks = list(map_dir.glob('*.DAT'))
        for i, chunk in enumerate(chunks):
            parts = chunk.stem.split('_')
            if len(parts) != 3: continue
            x, y, z = parts
            tscn.append(f'[node name=Chunk_{chunk.stem} type=Node3D parent=.]')
            tscn.append(f'transform = Transform3D(1, 0, 0, 0, 1, 0, 0, 0, 1, {int(x)*64}, {int(z)*10}, {int(y)*64})\n')
            if status_cb and i%10==0: status_cb(f'World: {i}/{len(chunks)} chunks')
        (self.dirs['scenes'] / 'ahkuilon_world.tscn').write_text('\n'.join(tscn))
        return True, 'World Scene generated.'

    def systematic_rebuild(self, status_cb=None):
        self.export_game_data()
        self.export_all_characters(status_cb)
        self.generate_full_world_scene(status_cb)
        return True, 'Systematic rebuild complete.'
