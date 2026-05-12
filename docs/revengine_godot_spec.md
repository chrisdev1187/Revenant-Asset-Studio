# RevEngine-Godot: Technical Specification

## 1. Overview
The goal is to provide a seamless "one-click" experience where a user can launch a Godot-based environment that is automatically populated with Revenant's 1999 world data and assets, utilizing modern rendering techniques (PBR, Dynamic Lighting, Physics).

## 2. The Custom Engine Shell
Instead of a separate binary, we will provide a **Godot Project Template** coupled with a **GDExtension Bridge**.

### A. Core GDExtension (The Bridge)
- **Language**: C++ or Rust for performance.
- **Responsibility**:
  - On-the-fly decoding of .RVI, .RVR, and .RVM archives.
  - Runtime conversion of .i3d geometry into Godot `ArrayMesh`.
  - Memory-efficient streaming of .DAT map chunks.
- **Why?**: Bypasses the need for massive intermediate file exports (PNG/glTF) unless the user specifically wants to bake them for performance.

### B. The "Smart" World Loader
- **System**: Custom implementation of Godot 4's `VisibleOnScreenNotifier3D` or `WorldPartition`.
- **Logic**:
  - As the player moves, the engine calculates which `X_Y_Z.DAT` chunks are needed.
  - Chunks are decoded in a background thread and instantiated as `Node3D` branches.
  - Objects within chunks (Statues, Barrels, Monsters) are mapped to Godot scenes based on their original ObjectIDs.

## 3. Game State & Logic Reproduction
The original game state will be mirrored in Godot using `Resources`.

- **State Sync**: The Python Command Center will maintain a JSON-based "World State" file. Godot watches this file and updates its world accordingly.
- **Logic Transpilation**:
  - **Combat**: Re-implement the original fixed-point physics and hitbox logic using Godot's `CharacterBody3D` and `Area3D`.
  - **AI**: Map original script commands to Godot `BehaviorTree` nodes.

## 4. Professional User Interface (In-Editor)
When launching the Godot project, the "RevEngine Addon" will activate:
- **Revenant File Browser**: Browse the original archives directly within the Godot FileSystem dock.
- **Object Inspector**: Selecting an object in the 3D view shows its original `char.def` or `weapon.def` properties (e.g., "Sight: 180 degrees", "Base Damage: 12").
- **Asset Modernizer**: Right-click any asset to trigger an AI upscale via the Python Command Center bridge.

## 5. Deployment & Distribution
- The project will be packaged as a "Revenant Project Template."
- Users point the template to their `C:/GOG Games/Revenant` path.
- The template "inflates" itself into a full modern RPG project.
