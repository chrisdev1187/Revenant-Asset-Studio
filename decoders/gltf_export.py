"""
RevEngine — glTF 2.0 Exporter
==============================
Exports Revenant .i3d models as glTF 2.0 with:
  - Skinned mesh (JOINTS_0 / WEIGHTS_0)
  - Full bone hierarchy
  - All animation states as named clips
  - Embedded textures (PNG, base64 data URI)

Usage:
    from decoders.gltf_export import export_gltf
    success = export_gltf(geom, textures, out_path)

The output is a self-contained .gltf with all data embedded as data URIs,
ready to import directly into Blender 3.x+ or Godot 4.
"""

from __future__ import annotations
import json
import math
import struct
import base64
import io
import logging
from pathlib import Path
from typing import List, Optional, Tuple

log = logging.getLogger("RevEngine.glTF")

# glTF component type constants
FLOAT       = 5126
UNSIGNED_SHORT = 5123
UNSIGNED_BYTE  = 5121

# glTF buffer view targets
ARRAY_BUFFER         = 34962
ELEMENT_ARRAY_BUFFER = 34963

# Animation assumed FPS (Revenant doesn't store FPS, 15 matches the feel)
ANIM_FPS = 15.0


# ---------------------------------------------------------------------------
# Matrix / quaternion helpers
# ---------------------------------------------------------------------------

def _mat_id():
    return [1.,0.,0.,0., 0.,1.,0.,0., 0.,0.,1.,0., 0.,0.,0.,1.]

def _mat_mul(a, b):
    c = [0.]*16
    for r in range(4):
        for col in range(4):
            c[r*4+col] = sum(a[r*4+k]*b[k*4+col] for k in range(4))
    return c

def _mat_inv4(m):
    """Invert a 4×4 matrix (general case via cofactor expansion)."""
    # Unpack into a list-of-rows for clarity
    m00,m01,m02,m03 = m[0],m[1],m[2],m[3]
    m10,m11,m12,m13 = m[4],m[5],m[6],m[7]
    m20,m21,m22,m23 = m[8],m[9],m[10],m[11]
    m30,m31,m32,m33 = m[12],m[13],m[14],m[15]

    t00 =  (m11*(m22*m33-m23*m32) - m12*(m21*m33-m23*m31) + m13*(m21*m32-m22*m31))
    t01 = -(m10*(m22*m33-m23*m32) - m12*(m20*m33-m23*m30) + m13*(m20*m32-m22*m30))
    t02 =  (m10*(m21*m33-m23*m31) - m11*(m20*m33-m23*m30) + m13*(m20*m31-m21*m30))
    t03 = -(m10*(m21*m32-m22*m31) - m11*(m20*m32-m22*m30) + m12*(m20*m31-m21*m30))

    det = m00*t00 + m01*t01 + m02*t02 + m03*t03
    if abs(det) < 1e-12:
        return _mat_id()

    inv_det = 1.0 / det
    return [
        t00*inv_det,
        -(m01*(m22*m33-m23*m32) - m02*(m21*m33-m23*m31) + m03*(m21*m32-m22*m31))*inv_det,
         (m01*(m12*m33-m13*m32) - m02*(m11*m33-m13*m31) + m03*(m11*m32-m12*m31))*inv_det,
        -(m01*(m12*m23-m13*m22) - m02*(m11*m23-m13*m21) + m03*(m11*m22-m12*m21))*inv_det,

        t01*inv_det,
         (m00*(m22*m33-m23*m32) - m02*(m20*m33-m23*m30) + m03*(m20*m32-m22*m30))*inv_det,
        -(m00*(m12*m33-m13*m32) - m02*(m10*m33-m13*m30) + m03*(m10*m32-m12*m30))*inv_det,
         (m00*(m12*m23-m13*m22) - m02*(m10*m23-m13*m20) + m03*(m10*m22-m12*m20))*inv_det,

        t02*inv_det,
        -(m00*(m21*m33-m23*m31) - m01*(m20*m33-m23*m30) + m03*(m20*m31-m21*m30))*inv_det,
         (m00*(m11*m33-m13*m31) - m01*(m10*m33-m13*m30) + m03*(m10*m31-m11*m30))*inv_det,
        -(m00*(m11*m23-m13*m21) - m01*(m10*m23-m13*m20) + m03*(m10*m21-m11*m20))*inv_det,

        t03*inv_det,
         (m00*(m21*m32-m22*m31) - m01*(m20*m32-m22*m30) + m02*(m20*m31-m21*m30))*inv_det,
        -(m00*(m11*m32-m12*m31) - m01*(m10*m32-m12*m30) + m02*(m10*m31-m11*m30))*inv_det,
         (m00*(m11*m22-m12*m21) - m01*(m10*m22-m12*m20) + m02*(m10*m21-m11*m20))*inv_det,
    ]

def _mat_to_quat(m):
    """Extract unit quaternion [x,y,z,w] from a 4×4 row-major rotation matrix."""
    tr = m[0] + m[5] + m[10]
    if tr > 0:
        s = 0.5 / math.sqrt(tr + 1.0)
        return [(m[9]-m[6])*s, (m[2]-m[8])*s, (m[4]-m[1])*s, 0.25/s]
    elif m[0] > m[5] and m[0] > m[10]:
        s = 2.0 * math.sqrt(1.0 + m[0] - m[5] - m[10])
        return [0.25*s, (m[1]+m[4])/s, (m[2]+m[8])/s, (m[9]-m[6])/s]
    elif m[5] > m[10]:
        s = 2.0 * math.sqrt(1.0 + m[5] - m[0] - m[10])
        return [(m[1]+m[4])/s, 0.25*s, (m[6]+m[9])/s, (m[2]-m[8])/s]
    else:
        s = 2.0 * math.sqrt(1.0 + m[10] - m[0] - m[5])
        return [(m[2]+m[8])/s, (m[6]+m[9])/s, 0.25*s, (m[4]-m[1])/s]

def _mat_translation(m):
    return [m[12], m[13], m[14]]

def _mat_scale(m):
    sx = math.sqrt(m[0]*m[0]+m[1]*m[1]+m[2]*m[2])
    sy = math.sqrt(m[4]*m[4]+m[5]*m[5]+m[6]*m[6])
    sz = math.sqrt(m[8]*m[8]+m[9]*m[9]+m[10]*m[10])
    return [sx if sx > 1e-8 else 1.0,
            sy if sy > 1e-8 else 1.0,
            sz if sz > 1e-8 else 1.0]


# ---------------------------------------------------------------------------
# Binary buffer helpers
# ---------------------------------------------------------------------------

class BufBuilder:
    """Accumulates binary data and tracks aligned byte offsets."""

    def __init__(self):
        self._data = bytearray()

    def _align(self, n=4):
        r = len(self._data) % n
        if r:
            self._data.extend(b'\x00' * (n - r))

    def add_floats(self, values) -> Tuple[int, int]:
        self._align(4)
        start = len(self._data)
        self._data.extend(struct.pack(f'<{len(values)}f', *values))
        return start, len(self._data) - start

    def add_ushorts(self, values) -> Tuple[int, int]:
        self._align(2)
        start = len(self._data)
        self._data.extend(struct.pack(f'<{len(values)}H', *values))
        return start, len(self._data) - start

    def add_ubytes(self, values) -> Tuple[int, int]:
        start = len(self._data)
        self._data.extend(bytes(values))
        return start, len(self._data) - start

    def data_uri(self) -> str:
        b64 = base64.b64encode(bytes(self._data)).decode('ascii')
        return f"data:application/octet-stream;base64,{b64}"

    def __len__(self):
        return len(self._data)


# ---------------------------------------------------------------------------
# Batched per-bone TRS extraction — all frames at once for one state
# ---------------------------------------------------------------------------

def _parse_all_frames_bone(raw: bytes, keys_start: int, numkeys: int, nframes: int):
    """
    Parse all nframes TRS values for one bone's SAniKey32 stream efficiently.
    Returns (pos_list, rot_list, scl_list) each of length nframes.
    Single pass: frame0 parsed once; packed channel arrays indexed per frame.
    """
    POSSCALE = 4.0
    ROTSCALE = 512.0 / math.pi
    SCLSCALE = 64.0
    CODESCALE = 256.0

    def s10(n): n &= 0x3FF; return n - 1024 if n >= 512 else n
    def s24(kv): v = kv >> 8; return (v - 0x1000000) if (v & 0x800000) else v

    # --- Parse frame 0 (CODE header) ---
    pos0 = [0., 0., 0.]; rot0 = [0., 0., 0.]; scl0 = [1., 1., 1.]
    posidx = rotidx = sclidx = -1
    fflags = 0
    i = 0
    while i < numkeys:
        kp = keys_start + i * 4
        if kp + 4 > len(raw): break
        kv = struct.unpack_from('<I', raw, kp)[0]
        t  = kv & 0x3
        if t == 0:
            code = (kv >> 2) & 0x3F
            if code <= 1: break
            elif code == 2:
                if fflags: break
                posidx = i
            elif code == 4: fflags |= 1
            elif code == 5:
                if fflags & 6: break
                rotidx = i
            elif code == 7: fflags |= 2
            elif code == 8:
                if fflags & 4: break
                sclidx = i
            elif code == 10: fflags |= 4
        elif t == 1:
            if fflags: break
            posidx = i; fflags |= 1
        elif t == 2:
            if fflags & 6: break
            rotidx = i; fflags |= 2
        elif t == 3:
            if fflags & 4: break
            sclidx = i; fflags |= 4
        i += 1
    header_end = i

    if posidx >= 0:
        kv = struct.unpack_from('<I', raw, keys_start + posidx * 4)[0]
        if (kv & 3) == 0:
            pos0 = [s24(struct.unpack_from('<I', raw, keys_start + (posidx+j)*4)[0]) / CODESCALE for j in range(3)]
        else:
            pos0 = [s10(kv >> 2)/POSSCALE, s10(kv >> 12)/POSSCALE, s10(kv >> 22)/POSSCALE]
    if rotidx >= 0:
        kv = struct.unpack_from('<I', raw, keys_start + rotidx * 4)[0]
        if (kv & 3) == 0:
            rot0 = [s24(struct.unpack_from('<I', raw, keys_start + (rotidx+j)*4)[0]) / CODESCALE for j in range(3)]
        else:
            rot0 = [s10(kv >> 2)/ROTSCALE, s10(kv >> 12)/ROTSCALE, s10(kv >> 22)/ROTSCALE]
    if sclidx >= 0:
        kv = struct.unpack_from('<I', raw, keys_start + sclidx * 4)[0]
        if (kv & 3) == 0:
            scl0 = [s24(struct.unpack_from('<I', raw, keys_start + (sclidx+j)*4)[0]) / CODESCALE for j in range(3)]
        else:
            scl0 = [s10(kv >> 2)/SCLSCALE, s10(kv >> 12)/SCLSCALE, s10(kv >> 22)/SCLSCALE]

    # --- Collect packed per-channel keys after header ---
    pos_keys = []; rot_keys = []; scl_keys = []
    for i in range(header_end, numkeys):
        kp = keys_start + i * 4
        if kp + 4 > len(raw): break
        kv = struct.unpack_from('<I', raw, kp)[0]
        t  = kv & 3
        if   t == 1: pos_keys.append(kv)
        elif t == 2: rot_keys.append(kv)
        elif t == 3: scl_keys.append(kv)

    # --- Build all frames ---
    pos_list = [list(pos0)]; rot_list = [list(rot0)]; scl_list = [list(scl0)]
    for fi in range(1, nframes):
        idx = fi - 1
        p = list(pos0); r = list(rot0); s = list(scl0)
        if idx < len(rot_keys):
            kv = rot_keys[idx]
            r = [s10(kv>>2)/ROTSCALE, s10(kv>>12)/ROTSCALE, s10(kv>>22)/ROTSCALE]
        if idx < len(pos_keys):
            kv = pos_keys[idx]
            p = [s10(kv>>2)/POSSCALE, s10(kv>>12)/POSSCALE, s10(kv>>22)/POSSCALE]
        if idx < len(scl_keys):
            kv = scl_keys[idx]
            s = [s10(kv>>2)/SCLSCALE, s10(kv>>12)/SCLSCALE, s10(kv>>22)/SCLSCALE]
        pos_list.append(p); rot_list.append(r); scl_list.append(s)

    return pos_list, rot_list, scl_list


def _bake_state_all_frames(rig, state_index: int, nframes: int):
    """
    Return list[frame][bone] of (trans, quat, scale).
    Batched: each bone's SAniKey32 stream parsed once; topo-sorted world
    matrices computed iteratively (no recursion, no hot-path imports).
    """
    from decoders.i3d import _make_bone_mat, _mat_mul, _deref
    import struct as _struct

    raw        = rig._raw
    objs_start = rig._objs_start
    nb         = rig.num_bones
    parents    = rig.bone_parents

    # --- Parse all frames for each bone ---
    all_local = []   # [bone][frame] = 4×4 mat
    id_frames  = [_mat_id()] * nframes   # shared identity list (read-only)
    for i in range(nb):
        opos_i = objs_start + i * 48
        if opos_i + 48 > len(raw):
            all_local.append(id_frames); continue
        states_arr = _deref(raw, opos_i + 44)
        if not states_arr:
            all_local.append(id_frames); continue
        state_entry = states_arr + state_index * 12
        if state_entry + 12 > len(raw):
            all_local.append(id_frames); continue
        numanikeys  = _struct.unpack_from('<i', raw, state_entry + 4)[0]
        anikeys_ptr = _deref(raw, state_entry + 8)
        if not anikeys_ptr or numanikeys <= 0:
            all_local.append(id_frames); continue
        pos_list, rot_list, scl_list = _parse_all_frames_bone(raw, anikeys_ptr, numanikeys, nframes)
        all_local.append([_make_bone_mat(pos_list[f], rot_list[f], scl_list[f])
                          for f in range(nframes)])

    # --- Topological order (parents before children) using Kahn's algorithm ---
    in_deg = [0] * nb
    children = [[] for _ in range(nb)]
    for i in range(nb):
        p = parents[i]
        if 0 <= p < nb:
            in_deg[i] += 1
            children[p].append(i)
    queue = [i for i in range(nb) if in_deg[i] == 0]
    topo  = []
    while queue:
        n = queue.pop()
        topo.append(n)
        for c in children[n]:
            in_deg[c] -= 1
            if in_deg[c] == 0:
                queue.append(c)
    # Any remaining (cycles) appended in order
    topo.extend(i for i in range(nb) if i not in set(topo))

    # --- Compute world matrices per frame in topological order ---
    result_frames = []
    world = [None] * nb
    for fr in range(nframes):
        for i in range(nb):
            world[i] = None
        for i in topo:
            p = parents[i]
            lm = all_local[i][fr]
            if 0 <= p < nb and world[p] is not None:
                world[i] = _mat_mul(lm, world[p])
            else:
                world[i] = lm
        result_frames.append([
            (_mat_translation(world[i]), _mat_to_quat(world[i]), _mat_scale(world[i]))
            for i in range(nb)
        ])

    return result_frames


# ---------------------------------------------------------------------------
# Main export function
# ---------------------------------------------------------------------------

def export_gltf(geom, textures: list, out_path: Path,
                status_cb=None) -> bool:
    """
    Export I3DGeometry + textures as a self-contained glTF 2.0 file.

    Parameters
    ----------
    geom       : I3DGeometry (must have rig populated — bind pose, state 0 frame 0)
    textures   : list of PIL Images (one per texture slot)
    out_path   : destination .gltf path
    status_cb  : optional callable(str) for progress messages
    """
    try:
        from PIL import Image as PILImage
    except ImportError:
        PILImage = None

    def _status(msg):
        log.info(msg)
        if status_cb:
            status_cb(msg)

    rig = geom.rig
    has_rig = rig is not None and rig.num_bones > 0

    _status("Building geometry buffers…")

    nv  = len(geom.vertices)
    nf  = len(geom.faces)
    nb  = rig.num_bones if has_rig else 0

    has_normals = len(geom.normals) == nv
    has_uvs     = len(geom.uvs)     == nv
    has_tex     = PILImage is not None and bool(textures)

    buf = BufBuilder()
    accessors     = []
    buffer_views  = []

    def _add_bv(byte_offset, byte_length, target=None):
        bv = {"buffer": 0, "byteOffset": byte_offset, "byteLength": byte_length}
        if target:
            bv["target"] = target
        buffer_views.append(bv)
        return len(buffer_views) - 1

    def _add_acc(bv_idx, comp_type, count, acc_type, min_v=None, max_v=None):
        acc = {"bufferView": bv_idx, "componentType": comp_type,
               "count": count, "type": acc_type}
        if min_v is not None: acc["min"] = min_v
        if max_v is not None: acc["max"] = max_v
        accessors.append(acc)
        return len(accessors) - 1

    # ── Positions ──────────────────────────────────────────────────────────
    pos_flat = [c for v in geom.vertices for c in v]
    boff, blen = buf.add_floats(pos_flat)
    bv_pos = _add_bv(boff, blen, ARRAY_BUFFER)
    xs = [v[0] for v in geom.vertices]; ys = [v[1] for v in geom.vertices]; zs = [v[2] for v in geom.vertices]
    acc_pos = _add_acc(bv_pos, FLOAT, nv, "VEC3",
                       min_v=[min(xs), min(ys), min(zs)],
                       max_v=[max(xs), max(ys), max(zs)])

    # ── Normals ────────────────────────────────────────────────────────────
    acc_nrm = None
    if has_normals:
        nrm_flat = [c for n in geom.normals for c in n]
        boff, blen = buf.add_floats(nrm_flat)
        bv_nrm = _add_bv(boff, blen, ARRAY_BUFFER)
        acc_nrm = _add_acc(bv_nrm, FLOAT, nv, "VEC3")

    # ── UVs ────────────────────────────────────────────────────────────────
    acc_uv = None
    if has_uvs:
        uv_flat = [c for uv in geom.uvs for c in uv]
        boff, blen = buf.add_floats(uv_flat)
        bv_uv = _add_bv(boff, blen, ARRAY_BUFFER)
        acc_uv = _add_acc(bv_uv, FLOAT, nv, "VEC2")

    # ── JOINTS_0 / WEIGHTS_0 (single-bone hard assignment) ─────────────────
    acc_joints = acc_weights = None
    if has_rig:
        vbone = rig.vertex_bone
        joints_flat = []
        for vi in range(nv):
            bi = vbone[vi] if vi < len(vbone) else 0
            joints_flat.extend([bi, 0, 0, 0])
        boff, blen = buf.add_ushorts(joints_flat)
        bv_j = _add_bv(boff, blen, ARRAY_BUFFER)
        acc_joints = _add_acc(bv_j, UNSIGNED_SHORT, nv, "VEC4")

        weights_flat = [1., 0., 0., 0.] * nv
        boff, blen = buf.add_floats(weights_flat)
        bv_w = _add_bv(boff, blen, ARRAY_BUFFER)
        acc_weights = _add_acc(bv_w, FLOAT, nv, "VEC4")

    # ── Indices ────────────────────────────────────────────────────────────
    idx_flat = [i for tri in geom.faces for i in tri]
    boff, blen = buf.add_ushorts(idx_flat)
    bv_idx = _add_bv(boff, blen, ELEMENT_ARRAY_BUFFER)
    acc_idx = _add_acc(bv_idx, UNSIGNED_SHORT, nf * 3, "SCALAR",
                       min_v=[0], max_v=[nv - 1])

    # ── Inverse bind matrices ──────────────────────────────────────────────
    acc_ibm = None
    if has_rig:
        _status("Computing inverse bind matrices…")
        ibm_flat = []
        for wm in rig.world_mats:
            inv = _mat_inv4(wm)
            # glTF MAT4 is column-major; our matrix is row-major → transpose
            col_major = [inv[c*4+r] for c in range(4) for r in range(4)]
            ibm_flat.extend(col_major)
        boff, blen = buf.add_floats(ibm_flat)
        bv_ibm = _add_bv(boff, blen)
        acc_ibm = _add_acc(bv_ibm, FLOAT, nb, "MAT4")

    # ── Textures → PNG data URIs ───────────────────────────────────────────
    images_gltf   = []
    textures_gltf = []
    materials_gltf = []

    if has_tex and PILImage:
        _status(f"Encoding {len(textures)} texture(s)…")
        for i, tex in enumerate(textures):
            buf_io = io.BytesIO()
            tex.convert("RGBA").save(buf_io, format="PNG")
            b64 = base64.b64encode(buf_io.getvalue()).decode('ascii')
            images_gltf.append({"uri": f"data:image/png;base64,{b64}",
                                 "name": f"tex{i}"})
            textures_gltf.append({"source": i, "name": f"tex{i}"})
            materials_gltf.append({
                "name": f"mat{i}",
                "pbrMetallicRoughness": {
                    "baseColorTexture": {"index": i},
                    "metallicFactor": 0.0,
                    "roughnessFactor": 0.9,
                },
                "doubleSided": True,
            })
    else:
        # Single untextured material
        materials_gltf = [{"name": "mat0",
                           "pbrMetallicRoughness": {"metallicFactor": 0.0}}]

    # ── Mesh primitives (one per texture group) ────────────────────────────
    # Build per-material face lists so each material gets its own primitive.
    # face_tex_indices: -1=no-tex, 0..N-1=tex slot.
    face_by_mat: dict = {}
    for fi, (a, b, c) in enumerate(geom.faces):
        t_idx = geom.face_tex_indices[fi] if fi < len(geom.face_tex_indices) else 0
        mat_idx = max(0, t_idx)          # -1 no-tex → mat 0
        face_by_mat.setdefault(mat_idx, []).append((a, b, c))

    primitives = []
    for mat_idx in sorted(face_by_mat):
        face_group = face_by_mat[mat_idx]
        g_idx_flat = [i for tri in face_group for i in tri]
        boff, blen = buf.add_ushorts(g_idx_flat)
        bv_g = _add_bv(boff, blen, ELEMENT_ARRAY_BUFFER)
        a_g  = _add_acc(bv_g, UNSIGNED_SHORT, len(g_idx_flat), "SCALAR",
                        min_v=[0], max_v=[nv - 1])
        attrs = {"POSITION": acc_pos}
        if acc_nrm is not None:  attrs["NORMAL"]     = acc_nrm
        if acc_uv  is not None:  attrs["TEXCOORD_0"] = acc_uv
        if acc_joints is not None: attrs["JOINTS_0"]  = acc_joints
        if acc_weights is not None: attrs["WEIGHTS_0"] = acc_weights
        prim = {"attributes": attrs, "indices": a_g}
        prim["material"] = min(mat_idx, len(materials_gltf) - 1)
        primitives.append(prim)

    if not primitives:
        # Fallback: single primitive with all faces
        attrs = {"POSITION": acc_pos}
        if acc_nrm is not None:  attrs["NORMAL"]     = acc_nrm
        if acc_uv  is not None:  attrs["TEXCOORD_0"] = acc_uv
        if acc_joints is not None: attrs["JOINTS_0"]  = acc_joints
        if acc_weights is not None: attrs["WEIGHTS_0"] = acc_weights
        primitives = [{"attributes": attrs, "indices": acc_idx, "material": 0}]

    mesh_gltf = {"name": geom.path.stem, "primitives": primitives}

    # ── Nodes ──────────────────────────────────────────────────────────────
    # Node 0 = mesh node; nodes 1..N = bone nodes.
    nodes_gltf = []
    skin_node_offset = 1   # bone nodes start at index 1

    if has_rig:
        # Find root bones
        roots = [i for i in range(nb) if rig.bone_parents[i] < 0 or
                 rig.bone_parents[i] >= nb]
        # Build children lists
        children_of = {i: [] for i in range(nb)}
        for i in range(nb):
            p = rig.bone_parents[i]
            if 0 <= p < nb:
                children_of[p].append(i)

        def _node_for_bone(bi):
            """Build glTF node dict for bone bi."""
            wm = rig.world_mats[bi]
            node = {"name": rig.bone_names[bi]}
            node["translation"] = _mat_translation(wm)
            node["rotation"]    = _mat_to_quat(wm)
            node["scale"]       = _mat_scale(wm)
            ch = [c + skin_node_offset for c in children_of[bi]]
            if ch:
                node["children"] = ch
            return node

        # Mesh node
        mesh_node = {
            "name": geom.path.stem,
            "mesh": 0,
        }
        if has_rig:
            mesh_node["skin"] = 0
        # Mesh node children = root bones
        mesh_node["children"] = [r + skin_node_offset for r in roots]
        nodes_gltf.append(mesh_node)

        # Bone nodes (in order 0..nb-1, offset by 1 for mesh node)
        for bi in range(nb):
            nodes_gltf.append(_node_for_bone(bi))
    else:
        nodes_gltf = [{"name": geom.path.stem, "mesh": 0}]

    # ── Skin ───────────────────────────────────────────────────────────────
    skins_gltf = []
    if has_rig and acc_ibm is not None:
        skins_gltf = [{
            "name": f"{geom.path.stem}_armature",
            "inverseBindMatrices": acc_ibm,
            "joints": [i + skin_node_offset for i in range(nb)],
            "skeleton": skin_node_offset,  # root joint
        }]

    # ── Animations ─────────────────────────────────────────────────────────
    animations_gltf = []
    if has_rig and geom.anim_states:
        _status(f"Baking {len(geom.anim_states)} animation state(s)...")
        for state in geom.anim_states:
            nframes = max(1, state.nframes)

            # Batch-bake all frames for this state in one pass
            all_frames_trs = _bake_state_all_frames(rig, state.index, nframes)

            # Time input accessor (shared across all channels in this clip)
            times = [f / ANIM_FPS for f in range(nframes)]
            boff, blen = buf.add_floats(times)
            bv_t = _add_bv(boff, blen)
            acc_t = _add_acc(bv_t, FLOAT, nframes, "SCALAR",
                             min_v=[times[0]], max_v=[times[-1]])

            channels = []
            samplers = []

            for bi in range(nb):
                node_idx = bi + skin_node_offset
                trans_vals = []; rot_vals = []; scl_vals = []
                for fr in range(nframes):
                    t, q, s = all_frames_trs[fr][bi]
                    trans_vals.extend(t)
                    rot_vals.extend(q)
                    scl_vals.extend(s)

                for path_name, values, acc_type in [
                    ("translation", trans_vals, "VEC3"),
                    ("rotation",    rot_vals,   "VEC4"),
                    ("scale",       scl_vals,   "VEC3"),
                ]:
                    boff, blen = buf.add_floats(values)
                    bv_v = _add_bv(boff, blen)
                    acc_v = _add_acc(bv_v, FLOAT, nframes, acc_type)
                    samp_idx = len(samplers)
                    samplers.append({"input": acc_t, "output": acc_v,
                                     "interpolation": "LINEAR"})
                    channels.append({"sampler": samp_idx,
                                     "target": {"node": node_idx,
                                                "path": path_name}})

            animations_gltf.append({
                "name": state.name or f"state{state.index}",
                "channels": channels,
                "samplers": samplers,
            })
            _status(f"  Baked '{state.name}' ({nframes} frames)")

    # ── Assemble glTF JSON ─────────────────────────────────────────────────
    _status("Writing glTF…")

    gltf = {
        "asset": {
            "version":   "2.0",
            "generator": "RevEngine — Revenant (1999) Asset Studio",
        },
        "scene":  0,
        "scenes": [{"nodes": [0], "name": "Scene"}],
        "nodes":  nodes_gltf,
        "meshes": [mesh_gltf],
        "accessors":    accessors,
        "bufferViews":  buffer_views,
        "buffers": [{
            "byteLength": len(buf),
            "uri": buf.data_uri(),
        }],
    }

    if materials_gltf: gltf["materials"] = materials_gltf
    if images_gltf:    gltf["images"]    = images_gltf
    if textures_gltf:  gltf["textures"]  = textures_gltf
    if skins_gltf:     gltf["skins"]     = skins_gltf
    if animations_gltf: gltf["animations"] = animations_gltf

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(gltf, separators=(',', ':')), encoding='utf-8')

    n_anim   = len(animations_gltf)
    n_states = len(geom.anim_states)
    sz_kb    = out_path.stat().st_size // 1024
    summary  = (f"Exported {nv} verts / {nf} faces / {nb} bones / "
                f"{n_anim}/{n_states} anims -> {out_path.name} ({sz_kb} KB)")
    _status(summary)
    log.info("glTF write complete: %s", out_path)
    return True
