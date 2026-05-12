"""
RevEngine — Character Modernization Pipeline
============================================
Blender headless script that takes a RevEngine-exported GLB and applies:

  1. Merge-by-distance  — welds UV-split coincident vertices so Catmull-Clark
                          doesn't collapse them toward the centroid
  2. Catmull-Clark subdivision — smooth geometry, bone weights interpolated
  3. Shade smooth        — interpolated normals for visual softening
  4. AO bake             — ambient occlusion baked onto original UVs (Cycles)
  5. PBR material wiring — normal + roughness maps wired into BSDF nodes
  6. Export GLB          — mesh + skin + animations + all textures

Usage (headless):
    blender --background --python tools/modernize_pipeline.py -- ^
        --input         test_renders/acolyte_full.gltf ^
        --output        test_renders_hd/acolyte_modern.glb ^
        --levels        2 ^
        --ao-size       512 ^
        --upscaled-tex  test_renders_hd/acolyte_diffuse.png ^
        --normal-map    test_renders_hd/acolyte_normal.png ^
        --roughness-map test_renders_hd/acolyte_roughness.png

Flags:
    --levels N           Catmull-Clark subdivision levels (default 2)
    --ao-size N          AO texture resolution (default 512; 0 = skip AO bake)
    --upscaled-tex PATH  Swap in an upscaled diffuse texture (optional)
    --normal-map PATH    Wire a normal map PNG into the BSDF material (optional)
    --roughness-map PATH Wire a roughness map PNG into the BSDF material (optional)
    --no-ao              Skip AO bake entirely
"""

import sys
import argparse
from pathlib import Path


def _parse():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    p = argparse.ArgumentParser()
    p.add_argument("--input",         required=True)
    p.add_argument("--output",        required=True)
    p.add_argument("--levels",        type=int,  default=2)
    p.add_argument("--ao-size",       type=int,  default=512)
    p.add_argument("--upscaled-tex",  default="")
    p.add_argument("--normal-map",    default="")
    p.add_argument("--roughness-map", default="")
    p.add_argument("--no-ao",         action="store_true")
    return p.parse_args(argv)


# ---------------------------------------------------------------------------
# Step 1 — Subdivision (CC with pre-weld)
# ---------------------------------------------------------------------------

def _subdivide(obj, levels: int):
    import bpy

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    # Merge coincident vertices (UV-seam splits share the same XYZ).
    # Without this, Catmull-Clark averages disconnected verts toward centroid.
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=1e-5)
    bpy.ops.object.mode_set(mode="OBJECT")

    # Insert Subsurf BEFORE the Armature modifier (index = arm position)
    arm_idx = next(
        (i for i, m in enumerate(obj.modifiers) if m.type == "ARMATURE"),
        len(obj.modifiers),
    )
    sub = obj.modifiers.new(name="Subsurf_RevEngine", type="SUBSURF")
    sub.subdivision_type = "CATMULL_CLARK"
    sub.levels       = levels
    sub.render_levels = levels

    obj.modifiers.move(len(obj.modifiers) - 1, arm_idx)
    bpy.ops.object.modifier_apply(modifier=sub.name)

    with bpy.context.temp_override(object=obj):
        bpy.ops.object.shade_smooth()

    obj.select_set(False)


# ---------------------------------------------------------------------------
# Step 2 — Swap in upscaled texture
# ---------------------------------------------------------------------------

def _swap_texture(obj, tex_path: str):
    """
    Apply tex_path as the base-color texture on every material slot.
    Replaces existing TEX_IMAGE nodes if present; otherwise builds a full
    Principled BSDF → Image Texture → UV Map node tree from scratch.
    """
    import bpy
    img = bpy.data.images.load(tex_path, check_existing=True)
    for slot in obj.material_slots:
        mat = slot.material
        if not mat:
            continue
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links

        # Try to reuse an existing Image Texture node
        existing = [n for n in nodes if n.type == "TEX_IMAGE"]
        if existing:
            for n in existing:
                n.image = img
            print(f"  Swapped texture → {Path(tex_path).name} on {mat.name}")
            continue

        # No Image Texture node found — build PBR node tree from scratch
        nodes.clear()
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.location = (0, 0)

        tex_node = nodes.new("ShaderNodeTexImage")
        tex_node.image = img
        tex_node.location = (-400, 0)

        uv_node = nodes.new("ShaderNodeUVMap")
        uv_node.uv_map = "UVMap"
        uv_node.location = (-600, 0)

        out_node = nodes.new("ShaderNodeOutputMaterial")
        out_node.location = (300, 0)

        links.new(uv_node.outputs["UV"],    tex_node.inputs["Vector"])
        links.new(tex_node.outputs["Color"], bsdf.inputs["Base Color"])
        links.new(bsdf.outputs["BSDF"],     out_node.inputs["Surface"])
        print(f"  Built texture node tree → {Path(tex_path).name} on {mat.name}")


# ---------------------------------------------------------------------------
# Step 2b — Wire PBR maps into BSDF material nodes
# ---------------------------------------------------------------------------

def _wire_pbr_maps(obj, normal_path: str, roughness_path: str):
    """
    Add normal + roughness texture nodes to every material on obj and connect
    them into the Principled BSDF inputs.

    Node layout added per material:
      [TexImage normal]  → [NormalMap] → BSDF.Normal
      [TexImage rough]               → BSDF.Roughness
    """
    import bpy

    normal_img    = bpy.data.images.load(normal_path,    check_existing=True) if normal_path    else None
    roughness_img = bpy.data.images.load(roughness_path, check_existing=True) if roughness_path else None

    for slot in obj.material_slots:
        mat = slot.material
        if not mat:
            continue
        mat.use_nodes = True
        tree  = mat.node_tree
        nodes = tree.nodes
        links = tree.links

        bsdf = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
        if bsdf is None:
            continue

        if normal_img:
            tex_n = nodes.new("ShaderNodeTexImage")
            tex_n.image = normal_img
            tex_n.image.colorspace_settings.name = "Non-Color"
            tex_n.location = (bsdf.location[0] - 500, bsdf.location[1] - 200)

            nmap = nodes.new("ShaderNodeNormalMap")
            nmap.location = (bsdf.location[0] - 250, bsdf.location[1] - 200)

            links.new(tex_n.outputs["Color"],  nmap.inputs["Color"])
            links.new(nmap.outputs["Normal"],  bsdf.inputs["Normal"])
            print(f"  Wired normal map → {mat.name}")

        if roughness_img:
            tex_r = nodes.new("ShaderNodeTexImage")
            tex_r.image = roughness_img
            tex_r.image.colorspace_settings.name = "Non-Color"
            tex_r.location = (bsdf.location[0] - 500, bsdf.location[1] - 400)

            links.new(tex_r.outputs["Color"], bsdf.inputs["Roughness"])
            print(f"  Wired roughness map → {mat.name}")


# ---------------------------------------------------------------------------
# Step 3 — AO bake
# ---------------------------------------------------------------------------

def _bake_ao(obj, ao_size: int) -> "bpy.types.Image | None":
    """
    Bake ambient occlusion onto existing UV channel using Cycles.
    Returns the baked Image so it can be saved alongside the GLB.
    """
    import bpy

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 64       # enough for AO; fast headless
    scene.cycles.use_denoising = False

    ao_name = f"{obj.name}_ao"
    ao_img  = bpy.data.images.new(ao_name, width=ao_size, height=ao_size,
                                   alpha=False, float_buffer=False)

    # Add an AO image texture node to every material (Cycles needs a selected
    # TEX_IMAGE node as the bake target)
    ao_nodes = []
    for slot in obj.material_slots:
        mat = slot.material
        if not mat:
            continue
        mat.use_nodes = True
        node = mat.node_tree.nodes.new("ShaderNodeTexImage")
        node.image = ao_img
        node.select = True
        mat.node_tree.nodes.active = node
        ao_nodes.append((mat, node))

    # Deselect everything, then select only the mesh — bake fails if armature selected
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    print(f"  Baking AO ({ao_size}×{ao_size}, 64 spp)…")
    bpy.ops.object.bake(type="AO", use_clear=True)

    # Remove the temporary AO nodes so they don't clutter the export material
    for mat, node in ao_nodes:
        mat.node_tree.nodes.remove(node)

    obj.select_set(False)
    return ao_img


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import bpy

    args = _parse()
    src  = Path(args.input)
    dst  = Path(args.output)
    dst.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n=== RevEngine Modernize: {src.name} ===")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(src))

    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        print(f"[SKIP] No mesh objects in {src.name}")
        sys.exit(1)

    obj = meshes[0]

    # 1. Subdivision
    print(f"  Subdividing (CC levels={args.levels})…")
    _subdivide(obj, args.levels)
    print(f"  Verts after subdivision: {len(obj.data.vertices)}")

    # 2. Upscaled texture swap
    if args.upscaled_tex and Path(args.upscaled_tex).exists():
        print(f"  Swapping upscaled texture…")
        _swap_texture(obj, args.upscaled_tex)
    elif args.upscaled_tex:
        print(f"  [WARN] Upscaled texture not found: {args.upscaled_tex} — keeping original")

    # 2b. PBR map wiring (normal + roughness)
    nmap_path = args.normal_map    if (args.normal_map    and Path(args.normal_map).exists())    else ""
    rmap_path = args.roughness_map if (args.roughness_map and Path(args.roughness_map).exists()) else ""
    if nmap_path or rmap_path:
        print(f"  Wiring PBR maps…")
        _wire_pbr_maps(obj, nmap_path, rmap_path)
    else:
        print(f"  No PBR maps provided — skipping normal/roughness wiring")

    # 3. AO bake
    ao_img = None
    if not args.no_ao and args.ao_size > 0:
        ao_img = _bake_ao(obj, args.ao_size)
    else:
        print("  Skipping AO bake")

    # Save AO as a sidecar PNG next to the output GLB
    if ao_img:
        ao_out = dst.with_name(dst.stem + "_ao.png")
        ao_img.filepath_raw = str(ao_out)
        ao_img.file_format  = "PNG"
        ao_img.save()
        print(f"  AO map saved: {ao_out.name}")

    # 4. Pack all images into the blend data so they're embedded in the GLB.
    # This is required for images loaded from glTF data-URIs — Blender does not
    # automatically re-pack them unless they are explicitly packed first.
    for img in bpy.data.images:
        if img.has_data and not img.packed_file:
            try:
                img.pack()
            except Exception:
                pass

    # 5. Export
    bpy.ops.export_scene.gltf(
        filepath=str(dst),
        export_format="GLB",
        export_image_format="AUTO",
        export_animations=True,
        export_skins=True,
        export_morph=True,
        export_apply=False,
        export_yup=True,
    )
    print(f"[OK] → {dst}")


main()
