# RevEngine-Godot Pipeline Design Specification

## 1. Asset Conversion Pipeline

### 3D Models (.i3d)
- **Source**: `decoders/i3d.py`
- **Target**: glTF 2.0 (.gltf / .glb)
- **Mapping**:
  - Vertices, Faces -> Godot `Mesh`
  - Animation States -> Godot `AnimationPlayer`
  - Stride/UVs -> Godot `StandardMaterial3D`
- **Optimization**: Use Godot's `ResourceImporter` to automatically convert .i3d to .res on import.

### 2D Sprites (.i2d)
- **Source**: `decoders/i2d.py`
- **Target**: PNG (Compressed with Godot's VRAM compression)
- **Integration**:
  - Static objects -> `Sprite3D` with Billboard mode enabled.
  - Multi-frame sprites -> `AnimatedSprite3D` or `SpriteFrames` resource.

### Game Data (.def)
- **Source**: `core/parsers.py` (Regex block parser)
- **Target**: Godot `Resource` (.tres)
- **Classes**:
  - `RevenantCharacter` (Health, Speed, Block, Attacks)
  - `RevenantItem` (Value, MinStr, Stats)
  - `RevenantSpell` (Mana, Damage, Talismans)

## 2. World & Level Construction

### Map Chunks (.DAT)
- **Format**: `MAP ` magic + Versioned blocks.
- **Stitching**:
  - World grid: 64x64 units per chunk.
  - Layering: Z-coordinate maps to Godot's Y-axis.
- **Node Hierarchy**:
  - `World` (Node3D)
    - `Layer_0` (Node3D)
      - `Chunk_X_Y` (Node3D)
        - `StaticTiles` (MultiMeshInstance3D for performance)
        - `DynamicObjects` (Individual Nodes)
        - `Lights` (OmniLight3D / SpotLight3D)
- **Navigation**: Generate `NavigationRegion3D` based on chunk collision flags.

## 3. The Custom Godot Environment

### RevEngine-Godot "Addon"
- A dedicated `addons/revengine/` folder in the Godot project.
- **EditorPlugin**: Adds a "Revenant" menu to the Godot top bar.
- **FileSystem Dock Extension**: Color-codes .i3d/.i2d files and shows custom previews.
- **Inspector Plugin**: Displays original game properties when selecting converted assets.

### Standalone Runtime
- Godot build with `main_scene` set to a `WorldLoader` that dynamically streams chunks based on player position.
- Embedded Python interpreter (via `godot-python` or custom GDExtension) to allow on-the-fly decoding of original archives if the game path is provided.

## 4. Integration Flow
1. **Python Command Center**: User selects game path and clicks "Sync to Godot".
2. **Transpilation**: Python scripts parse all assets and generate a Godot Project structure.
3. **Godot Launch**: Python launches the pre-configured Godot Editor.
4. **Live-Sync**: Any changes made in the Python UI (e.g., upscaling a texture) trigger a re-export of that specific asset, which Godot hot-reloads via `ResourceWatcher`.
