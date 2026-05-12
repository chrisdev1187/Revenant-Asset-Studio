"""
RevEngine — Blender Batch Subdivision (Animated/Skinned GLB)
============================================================
Adds a Catmull-Clark Subdivision Surface modifier to every mesh in each input
GLB, applies it (interpolating bone weights), then re-exports as GLB.

Run headless:
    blender --background --python tools/subdivide_batch.py -- \
        --input  path/to/input_dir  \
        --output path/to/output_dir \
        --levels 2

Or single file:
    blender --background --python tools/subdivide_batch.py -- \
        --input  model.glb \
        --output model_sub2.glb \
        --levels 2

Armature modifier order is preserved: Subsurf is inserted BEFORE Armature so
Blender evaluates subdivision on the rest-pose mesh (correct weight baking).
"""

import sys
import argparse
from pathlib import Path

# ---------------------------------------------------------------------------
# Parse args after the "--" separator Blender uses for user-supplied args
# ---------------------------------------------------------------------------
def _parse():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    p = argparse.ArgumentParser()
    p.add_argument("--input",  required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--levels", type=int, default=2)
    return p.parse_args(argv)


def _collect_inputs(raw: str) -> list[tuple[Path, Path]]:
    """Return list of (src, dst) Path pairs."""
    src = Path(raw)
    args = _parse()
    dst_root = Path(args.output)
    if src.is_dir():
        pairs = []
        for f in src.glob("*.glb"):
            pairs.append((f, dst_root / f.name))
        for f in src.glob("*.gltf"):
            pairs.append((f, dst_root / f.name))
        return pairs
    else:
        dst = dst_root if dst_root.suffix else dst_root / src.name
        return [(src, dst)]


def subdivide_file(src: Path, dst: Path, levels: int) -> None:
    import bpy

    # Reset to blank scene
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # Import
    bpy.ops.import_scene.gltf(filepath=str(src))

    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        print(f"[SKIP] {src.name} — no mesh objects found")
        return

    for obj in meshes:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)

        # Find armature modifier index (insert subsurf before it)
        arm_idx = next(
            (i for i, m in enumerate(obj.modifiers) if m.type == "ARMATURE"),
            len(obj.modifiers),  # fallback: append at end
        )

        # SIMPLE subdivision: splits faces without repositioning vertices.
        # Catmull-Clark collapses 1999-era split-vertex meshes into a blob
        # because UV-seam vertices share the same position but are topologically
        # disconnected — CC averages them toward the centroid.
        sub = obj.modifiers.new(name="Subsurf_RevEngine", type="SUBSURF")
        sub.subdivision_type = "SIMPLE"
        sub.levels = levels
        sub.render_levels = levels

        # Move subsurf to correct position (before armature)
        # obj.modifiers.move() is available in Blender 4.0+ and avoids the
        # deprecated context-dict override on bpy.ops operators.
        current_idx = len(obj.modifiers) - 1
        obj.modifiers.move(current_idx, arm_idx)

        # Apply — Blender interpolates vertex groups (bone weights) correctly
        bpy.ops.object.modifier_apply(modifier=sub.name)

        # Shade smooth so interpolated normals give visual softening
        # even though geometry is linearly subdivided
        with bpy.context.temp_override(object=obj):
            bpy.ops.object.shade_smooth()

        obj.select_set(False)

    dst.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(dst),
        export_format="GLB",
        export_animations=True,
        export_skins=True,
        export_morph=True,
        export_apply=False,     # modifiers already applied above
        export_yup=True,
    )
    print(f"[OK] {src.name} -> {dst} (levels={levels})")


def main():
    args = _parse()
    pairs = _collect_inputs(args.input)
    if not pairs:
        print("[ERROR] No .glb/.gltf files found in input path")
        sys.exit(1)
    for src, dst in pairs:
        print(f"Processing {src.name} ...")
        subdivide_file(src, dst, args.levels)


main()
