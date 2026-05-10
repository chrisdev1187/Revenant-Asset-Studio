from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[1]  # RevEngine/
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from decoders.i3d import decode_i3d_geometry, export_gltf, export_obj


def main(argv: list[str]) -> int:
    # Default to a known i3d that exists in typical installs.
    default_i3d = Path(r"C:\Users\chris\OneDrive\Desktop\Revengine\extracted\imagery\Imagery\Chars\acolyte.i3d")
    i3d_path = Path(argv[1]) if len(argv) > 1 else default_i3d

    if not i3d_path.exists():
        print(f"Missing i3d: {i3d_path}")
        return 2

    state_index = int(argv[2]) if len(argv) > 2 else 0
    geom = decode_i3d_geometry(i3d_path, state_index=state_index)
    if geom is None:
        print(f"Failed to decode: {i3d_path}")
        return 1

    out_dir = Path("test_renders")
    out_obj = out_dir / f"{i3d_path.stem}_state{state_index}.obj"
    out_gltf = out_dir / f"{i3d_path.stem}_state{state_index}.gltf"

    ok_obj = export_obj(geom, out_obj)
    ok_gltf = export_gltf(geom, out_gltf)

    print(f"Decoded: {i3d_path}")
    print(f"  verts={len(geom.vertices)} faces={len(geom.faces)} states={len(geom.anim_states)}")
    print(f"Export OBJ : {ok_obj} -> {out_obj}")
    print(f"Export glTF: {ok_gltf} -> {out_gltf}")
    return 0 if (ok_obj and ok_gltf) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
