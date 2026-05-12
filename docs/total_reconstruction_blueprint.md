# RevEngine-Godot: Total Engine Reconstruction Blueprint

## 1. The "Invisible Engine" Core
To modernise Revenant, we must port the logic that governs how the world behaves, not just how it looks.

### A. Fixed-Point Math & Isometric Physics
Original Revenant (1999) likely uses a custom fixed-point math library for deterministic physics.
- **Strategy**: Implement a `RevenantPhysics` module in GDExtension (C++) that mimics the original coordinate system.
- **Mapping**:
  - `Revenant Coord (X, Y, Z)` -> `Godot Coord (X, Z, Y)`.
  - Elevation (Z) in Revenant becomes Godot's vertical Y-axis.
  - Implement the original tile-snapping and isometric movement constraints.

### B. Animation & State Logic (The "Action" System)
Animation states are more than just frames; they contain the game's state transitions.
- **Extraction**:
  - Analyze the 76-byte state entries in `.i3d` files to extract frame-perfect event tags (e.g., Hit connect frame, Sound trigger frame).
- **Godot Mapping**:
  - Map every character's state machine to a Godot `AnimationTree` with an `AnimationNodeStateMachine`.
  - Synchronise Godot signals with the original frame-event indices.

### C. Combat & Hitbox System
- **Invisible Data**: Extrapolate "Attack Spheres" and "Impact Cubes" from `char.def` and the original source logic.
- **Porting**:
  - Re-implement the original damage formula (Weapon Dmg + STR vs Armor Prot + CON) as a Godot `Resource`-based system.
  - Convert "Impact Cubes" into Godot `Area3D` nodes attached to character skeletons.

## 2. Scripting & Logic Modernization Layer

Revenant's scripts (found in `Ahkuilon/Script/`) use a proprietary event-driven language.

### A. The Script Transpiler
Build a Python-based **Transpiler** that:
1.  Parses the `.s` and `.def` script files.
2.  Translates high-level Revenant commands (e.g., `ON_TOUCH`, `GIVE_ITEM`, `SPAWN_MONSTER`) into modern GDScript components.
3.  Wires these events to Godot's signal system.

### B. "Invisible" World Metadata
Map chunks contain triggers, event boundaries, and light sources.
- **Godot Conversion**:
  - Expand `map_parser.py` to identify these metadata blocks within `.DAT` chunks.
  - Instantiate `CollisionShape3D` triggers and `OmniLight3D` nodes dynamically based on this data.

## 3. Custom Godot Build Specification
- **Engine Core**: GDExtension-powered archive decoders for real-time asset loading.
- **Developer Tools**:
  - **State Inspector**: Click any object in-game to see its original 1999 variables and AI state.
  - **Live Logic Editor**: Modify character stats in the Python UI and see the combat simulation update in Godot instantly.

## 4. Porting Path Summary
1.  **Phase 1**: Research & Blueprinting (Current).
2.  **Phase 2**: GDExtension Math & Binary Bridge development.
3.  **Phase 4**: Automated World & Metadata Export.
4.  **Phase 5**: Logic & State Machine Injection.
