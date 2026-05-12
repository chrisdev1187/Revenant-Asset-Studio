"""
RevEngine - i3d Geometry Decoder  (v8 — Source-Confirmed Format)
=================================================================
Decodes Revenant (1999) .i3d 3D model geometry.

FILE STRUCTURE (confirmed from Revenant source: 3dimage.cpp, 3dimagebody.h, resourcehdr.h):

  FileResHdr (20 bytes) at offset 0:
    [0:4]   'CGSR' magic
    [4:6]   topbm   (uint16)
    [6]     comptype (0=none)
    [7]     version  (1)
    [8:12]  datasize
    [12:16] objsize
    [16:20] hdrsize  (uint32) — size of SImageryHeader, NOT including FileResHdr

  SImageryHeader at offset 20:
    [0:4]   imageryid  (int32)
    [4:8]   numstates  (int32)
    [8 + i*76]  SImageryStateHeader[i] (76 bytes each):
      [0:32]  animname  (null-terminated ASCII, 32 bytes)
      [32:36] OFFSET walkmap
      [36:40] DWORD flags
      [40:42] short aniflags
      [42:44] short frames
      ... (more state metadata, not needed for geometry)

  Body starts at:  body_base = 20 + hdrsize

  NEW FORMAT (I3D_3DIMAGEBODY2 = 0x10 set in flags):
    S3DImageryBody (all offsets are TOffset — relative to the field's own address):
      [0]  DWORD flags
      [4]  DWORD version
      [8]  OS3DImageryState  statedata   (OFFSET)
      [12] int   numverts
      [16] OOOD3DVERTEX  verts           (3-level OFFSET chain)
      [20] int   numfaces
      [24] OS3DFace  faces               (1-level OFFSET)
      [28] int   nummaterials
      [32] OD3DMATERIAL  materials       (OFFSET)
      [36] int   numtextures
      [40] OS3DImageryTexture textures   (OFFSET)
      [44] int   numobjects
      [48] OS3DImageryObject objects     (OFFSET)
      [52] int   numtags
      [56] OS3DImageryTag tags           (OFFSET)

    D3DVERTEX (32 bytes): x,y,z (12) + nx,ny,nz (12) + tu,tv (8)

    S3DFace (6 bytes): WORD v1, WORD v2, WORD v3  — LOCAL indices per object!

    S3DImageryObject (48 bytes, at objects_base + i*48):
      [0:32]  char name[32]
      [32:34] WORD material
      [34:36] WORD vertpos    — first vertex index in global vert array
      [36:38] WORD vertnum    — number of vertices for this object
      [38:40] WORD pad
      [40:44] OS3DImageryObjectTexture textures  (OFFSET to array)
      [44:48] OS3DImageryObjectState   states    (OFFSET to array)

    S3DImageryObjectTexture (4 bytes): WORD facepos, WORD facenum
      — textures[0] = "no texture" group
      — textures[1..numtextures] = one entry per texture

    CRITICAL: Face indices (v1,v2,v3) in each S3DFace are LOCAL to the owning
    object's vertex range (0..vertnum-1). To get global vertex indices, add vertpos.

  OLD FORMAT (I3D_3DIMAGEBODY2 = 0x10 NOT set):
    SOld3DImageryBody — used by magic effects (simple quads, fire, etc.):
      [0]  DWORD flags
      [4]  int   numverts
      [8]  OFFSET verts[64]   — verts[0] → frame-array of OFFSETs → vertex data
      [264] int  numfaces
      [268] OFFSET faces      — 1-level OFFSET to S3DFace array
    Face indices are global (single-object models).
"""

from __future__ import annotations
import math
import struct
import json
import base64
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List, Tuple

log = logging.getLogger("RevEngine.i3d")

CGSR_MAGIC = b'CGSR'
STRIDE     = 32          # D3DVERTEX stride in bytes
MAX_COORD  = 50_000.0

# Source flags
I3D_3DIMAGEBODY2 = 0x10   # Uses S3DImageryBody (new format)


# --- Data classes -------------------------------------------------------------

@dataclass
class AnimState:
    name      : str
    index     : int
    anim_type : int = 0   # placeholder (skeletal anim, not morph)
    nframes   : int = 0   # placeholder
    vbase     : int = 0   # placeholder
    vpc       : int = 0   # placeholder


@dataclass
class I3DRig:
    """Skeletal rig — populated only for new-format (I3D_3DIMAGEBODY2) models."""
    num_bones    : int
    bone_names   : List[str]         # object name[32] per bone
    bone_parents : List[int]         # parent index, -1 = root
    world_mats   : List[List[float]] # bind-pose (state0/frame0) 4×4 row-major per bone
    vertex_bone  : List[int]         # owning bone index per vertex
    _raw         : bytes = field(default_factory=bytes, repr=False)
    _body_base   : int = 0
    _objs_start  : int = 0
    _numstates   : int = 0


@dataclass
class I3DGeometry:
    vertices         : List[Tuple[float, float, float]]
    faces            : List[Tuple[int,   int,   int  ]]
    stride           : int
    vert_count       : int
    idx_count        : int
    path             : Path
    normals          : List[Tuple[float, float, float]] = field(default_factory=list)
    uvs              : List[Tuple[float, float]]        = field(default_factory=list)
    anim_states      : List[AnimState]                  = field(default_factory=list)
    face_tex_indices : List[int]                        = field(default_factory=list)
    rig              : Optional['I3DRig']               = None
    state_index      : int = 0
    _raw_vbuf        : bytes = field(default_factory=bytes, repr=False)
    _vbuf_start      : int   = 0
    _bind_vc         : int   = 0
    _body_base       : int   = 0


# --- Low-level helpers --------------------------------------------------------

def _deref(raw: bytes, field_pos: int) -> int:
    """Dereference a TOffset field: returns field_pos + stored_int32 value."""
    val = struct.unpack_from('<i', raw, field_pos)[0]
    if val == 0:
        return 0   # NULL offset
    return field_pos + val


def _read_verts(raw: bytes, vstart: int, vc: int):
    """Parse vc D3DVERTEX structs (stride 32) from file offset vstart."""
    vertices, normals, uvs = [], [], []
    for i in range(vc):
        voff = vstart + i * STRIDE
        if voff + STRIDE > len(raw):
            vertices.append((0., 0., 0.))
            normals.append((0., 1., 0.))
            uvs.append((0., 0.))
            continue
        x,  y,  z  = struct.unpack_from('<fff', raw, voff)
        nx, ny, nz = struct.unpack_from('<fff', raw, voff + 12)
        u,  v      = struct.unpack_from('<ff',  raw, voff + 24)
        vertices.append((x, y, z)   if all(math.isfinite(c) and abs(c) < MAX_COORD for c in (x, y, z))   else (0., 0., 0.))
        normals.append((nx, ny, nz) if all(math.isfinite(c) and abs(c) <= 1.01     for c in (nx, ny, nz)) else (0., 1., 0.))
        uvs.append((u, v)           if all(math.isfinite(c) and abs(c) <= 16.0     for c in (u, v))       else (0., 0.))
    return vertices, normals, uvs


# --- 4×4 matrix helpers (row-major, row-vector convention) -------------------
# Matches Revenant's d3dmath.cpp exactly:
#   MultiplyD3DMATRIX: C[r][c] = sum(A[r][k]*B[k][c])
#   D3DMATRIXTransform: d.x = _11*v.x + _21*v.y + _31*v.z + _41  (col 0 of mat)
#   i.e. vertex transform is  v_out = v_in @ M  (row vector on left)

def _mat_id():
    return [1.,0.,0.,0., 0.,1.,0.,0., 0.,0.,1.,0., 0.,0.,0.,1.]

def _mat_mul(a, b):
    c = [0.]*16
    for r in range(4):
        for col in range(4):
            s = 0.
            for k in range(4):
                s += a[r*4+k] * b[k*4+col]
            c[r*4+col] = s
    return c

def _mat_rx(a):
    c, s = math.cos(a), math.sin(a)
    m = _mat_id(); m[5]=c; m[6]=s; m[9]=-s; m[10]=c; return m

def _mat_ry(a):
    c, s = math.cos(a), math.sin(a)
    m = _mat_id(); m[0]=c; m[2]=-s; m[8]=s; m[10]=c; return m

def _mat_rz(a):
    c, s = math.cos(a), math.sin(a)
    m = _mat_id(); m[0]=c; m[1]=s; m[4]=-s; m[5]=c; return m

def _mat_t(tx, ty, tz):
    m = _mat_id(); m[12]=tx; m[13]=ty; m[14]=tz; return m

def _mat_s(sx, sy, sz):
    m = _mat_id(); m[0]=sx; m[5]=sy; m[10]=sz; return m

def _make_bone_mat(pos, rot, scl):
    """Build bone local matrix: identity → RotX → RotY → RotZ → Translate → Scale.
    Matches MakeMatrix() in 3dimage.cpp."""
    m = _mat_id()
    if rot[0]: m = _mat_mul(m, _mat_rx(rot[0]))
    if rot[1]: m = _mat_mul(m, _mat_ry(rot[1]))
    if rot[2]: m = _mat_mul(m, _mat_rz(rot[2]))
    if pos[0] or pos[1] or pos[2]: m = _mat_mul(m, _mat_t(*pos))
    if scl[0]!=1. or scl[1]!=1. or scl[2]!=1.: m = _mat_mul(m, _mat_s(*scl))
    return m

def _xform_pos(v, m):
    """v' = [vx, vy, vz, 1] @ m  (row-vector, row-major)."""
    x, y, z = v
    return (x*m[0]+y*m[4]+z*m[8]+m[12],
            x*m[1]+y*m[5]+z*m[9]+m[13],
            x*m[2]+y*m[6]+z*m[10]+m[14])

def _xform_nrm(n, m):
    """Transform normal by 3×3 rotation sub-matrix, then renormalize."""
    nx, ny, nz = n
    ox = nx*m[0]+ny*m[4]+nz*m[8]
    oy = nx*m[1]+ny*m[5]+nz*m[9]
    oz = nx*m[2]+ny*m[6]+nz*m[10]
    mag = math.sqrt(ox*ox+oy*oy+oz*oz)
    return (ox/mag, oy/mag, oz/mag) if mag > 1e-6 else (0., 1., 0.)


# --- SAniKey32 frame-0 parser -------------------------------------------------
# SAniKey32 bit layout (confirmed from 3dimagebody.h):
#   bits  0- 1: flags  (0=CODE, 1=POS, 2=ROT, 3=SCL)
#   bits  2-11: x  (10-bit signed) OR  bits 2-7: code (6-bit) + bits 8-31: value (24-bit signed)
#   bits 12-21: y  (10-bit signed)
#   bits 22-31: z  (10-bit signed)
# Scales: POSSCALE=4, ROTSCALE=512/π, SCLSCALE=64, CODESCALE=256

def _parse_frame0_anikey32(raw: bytes, keys_start: int, numkeys: int):
    """Return (pos, rot, scl) lists for frame 0 of an SAniKey32 stream."""
    POSSCALE  = 4.0
    ROTSCALE  = 512.0 / math.pi
    SCLSCALE  = 64.0
    CODESCALE = 256.0

    def s10(n): n &= 0x3FF; return n - 1024 if n >= 512 else n
    def s24(kv): v = kv >> 8; return (v - 0x1000000) if (v & 0x800000) else v

    posidx = rotidx = sclidx = -1
    fflags = 0  # bit0=POSCHANGED, bit1=ROTCHANGED, bit2=SCLCHANGED

    i = 0
    while i < numkeys:
        kp = keys_start + i * 4
        if kp + 4 > len(raw): break
        kv = struct.unpack_from('<I', raw, kp)[0]
        t  = kv & 0x3
        if t == 0:   # CODE
            code = (kv >> 2) & 0x3F
            if code <= 1:                   break        # NEXTFRAME / SKIP → end of frame
            elif code == 2:                              # POSX
                if fflags: break
                posidx = i
            elif code == 3:                              # POSY
                if fflags: break
            elif code == 4:                              # POSZ
                if fflags: break
                fflags |= 1
            elif code == 5:                              # ROTX
                if fflags & 6: break
                rotidx = i
            elif code == 6:                              # ROTY
                if fflags & 6: break
            elif code == 7:                              # ROTZ
                if fflags & 6: break
                fflags |= 2
            elif code == 8:                              # SCLX
                if fflags & 4: break
                sclidx = i
            elif code in (9, 10):                        # SCLY / SCLZ
                if fflags & 4: break
                if code == 10: fflags |= 4
        elif t == 1:  # ANIFLAG32_POS (10-bit xyz)
            if fflags: break
            posidx = i; fflags |= 1
        elif t == 2:  # ANIFLAG32_ROT (10-bit xyz)
            if fflags & 6: break
            rotidx = i; fflags |= 2
        elif t == 3:  # ANIFLAG32_SCL (10-bit xyz)
            if fflags & 4: break
            sclidx = i; fflags |= 4
        i += 1

    pos = [0., 0., 0.]; rot = [0., 0., 0.]; scl = [1., 1., 1.]

    if posidx >= 0:
        kp = keys_start + posidx * 4
        kv = struct.unpack_from('<I', raw, kp)[0]
        if (kv & 0x3) == 0:   # CODE (POSX, POSY, POSZ — 3 consecutive keys)
            for j in range(3):
                pos[j] = s24(struct.unpack_from('<I', raw, kp + j*4)[0]) / CODESCALE
        else:                  # 10-bit packed
            pos[0] = s10(kv >>  2) / POSSCALE
            pos[1] = s10(kv >> 12) / POSSCALE
            pos[2] = s10(kv >> 22) / POSSCALE

    if rotidx >= 0:
        kp = keys_start + rotidx * 4
        kv = struct.unpack_from('<I', raw, kp)[0]
        if (kv & 0x3) == 0:   # CODE (ROTX, ROTY, ROTZ)
            for j in range(3):
                rot[j] = s24(struct.unpack_from('<I', raw, kp + j*4)[0]) / CODESCALE
        else:
            rot[0] = s10(kv >>  2) / ROTSCALE
            rot[1] = s10(kv >> 12) / ROTSCALE
            rot[2] = s10(kv >> 22) / ROTSCALE

    if sclidx >= 0:
        kp = keys_start + sclidx * 4
        kv = struct.unpack_from('<I', raw, kp)[0]
        if (kv & 0x3) == 0:   # CODE (SCLX, SCLY, SCLZ)
            for j in range(3):
                scl[j] = s24(struct.unpack_from('<I', raw, kp + j*4)[0]) / CODESCALE
        else:
            scl[0] = s10(kv >>  2) / SCLSCALE
            scl[1] = s10(kv >> 12) / SCLSCALE
            scl[2] = s10(kv >> 22) / SCLSCALE

    return pos, rot, scl


def _parse_frameN_anikey32(raw: bytes, keys_start: int, numkeys: int,
                            target_frame: int):
    """Return (pos, rot, scl) for frame target_frame of an SAniKey32 stream.

    SAniKey32 layout (no NEXTFRAME markers):
      - Frame 0: CODE keys (t=0, codes 2-10) giving full-precision pos/rot/scl.
      - Frames 1..N: packed keys (t=1 POS, t=2 ROT, t=3 SCL) follow the CODE
        header grouped by channel.  rot_packed[k] → frame k+1.
    """
    POSSCALE = 4.0
    ROTSCALE = 512.0 / math.pi
    SCLSCALE = 64.0

    def s10(n): n &= 0x3FF; return n - 1024 if n >= 512 else n

    # Always parse frame 0 first to get base pose and locate header end.
    pos0, rot0, scl0 = _parse_frame0_anikey32(raw, keys_start, numkeys)

    if target_frame == 0:
        return pos0, rot0, scl0

    # Find where the CODE header ends (first non-CODE key).
    header_len = 0
    for i in range(numkeys):
        kp = keys_start + i * 4
        if kp + 4 > len(raw):
            break
        if (struct.unpack_from('<I', raw, kp)[0] & 0x3) != 0:
            header_len = i
            break
    else:
        header_len = numkeys   # all CODE keys — no per-frame packed data

    # Collect per-channel packed keys after the header.
    # Each channel's keys are stored consecutively: rot_keys[0]=frame1, [1]=frame2, …
    pos_keys, rot_keys, scl_keys = [], [], []
    for i in range(header_len, numkeys):
        kp = keys_start + i * 4
        if kp + 4 > len(raw):
            break
        kv = struct.unpack_from('<I', raw, kp)[0]
        t  = kv & 0x3
        if   t == 1: pos_keys.append(kv)
        elif t == 2: rot_keys.append(kv)
        elif t == 3: scl_keys.append(kv)

    fi = target_frame - 1   # 0-based index into packed arrays

    pos = list(pos0)
    rot = list(rot0)
    scl = list(scl0)

    if fi < len(rot_keys):
        kv = rot_keys[fi]
        rot[0] = s10(kv >>  2) / ROTSCALE
        rot[1] = s10(kv >> 12) / ROTSCALE
        rot[2] = s10(kv >> 22) / ROTSCALE

    if fi < len(pos_keys):
        kv = pos_keys[fi]
        pos[0] = s10(kv >>  2) / POSSCALE
        pos[1] = s10(kv >> 12) / POSSCALE
        pos[2] = s10(kv >> 22) / POSSCALE

    if fi < len(scl_keys):
        kv = scl_keys[fi]
        scl[0] = s10(kv >>  2) / SCLSCALE
        scl[1] = s10(kv >> 12) / SCLSCALE
        scl[2] = s10(kv >> 22) / SCLSCALE

    return pos, rot, scl


def _parse_anim_states(raw: bytes, body_hdr_start: int, numstates: int) -> List[AnimState]:
    """
    Read animation state names from SImageryHeader.states[] array.
    SImageryStateHeader (76 bytes each) at body_hdr_start+8 + i*76:
      [0:32]  animname[32]
      [32:36] OFFSET walkmap
      [36:40] DWORD flags
      [40:42] short aniflags
      [42:44] short frames
    """
    states = []
    for i in range(numstates):
        off = body_hdr_start + 8 + i * 76    # 8 = sizeof(imageryid)+sizeof(numstates)
        if off + 44 > len(raw):
            break
        name   = raw[off:off + 32].split(b'\x00')[0].decode('ascii', errors='replace').strip()
        nframes = struct.unpack_from('<h', raw, off + 42)[0]
        states.append(AnimState(name=name, index=i, nframes=max(0, nframes)))
    return states


# --- New format decoder (I3D_3DIMAGEBODY2) ------------------------------------

def _decode_new(raw: bytes, body_base: int, numverts_hint: int,
                numfaces_hint: int, path: Path, anim_states: List[AnimState],
                state_index: int = 0, frame: int = 0,
                ) -> Optional[I3DGeometry]:
    """
    Decode S3DImageryBody (new format, I3D_3DIMAGEBODY2 set).

    Key insight: face indices are LOCAL to each object's vertex range.
    Global index = local_index + object.vertpos.
    """
    if body_base + 60 > len(raw):
        return None

    numverts   = struct.unpack_from('<i', raw, body_base + 12)[0]
    numfaces   = struct.unpack_from('<i', raw, body_base + 20)[0]
    numtex     = struct.unpack_from('<i', raw, body_base + 36)[0]
    numobjects = struct.unpack_from('<i', raw, body_base + 44)[0]

    if numverts <= 0 or numfaces <= 0:
        return None

    # --- Vertices: 3-level TOffset chain ---
    # OOOD3DVERTEX is a fixed triple indirection to the single bone-local vertex buffer.
    # Animation is skeletal (SAniKey32 bone transforms), not morph — vertices are constant.
    l1 = _deref(raw, body_base + 16)
    if not l1:
        return None
    l2 = _deref(raw, l1)
    if not l2:
        return None
    verts_start = _deref(raw, l2)
    if not verts_start:
        return None

    if verts_start + numverts * STRIDE > len(raw):
        return None

    # --- Faces: 1-level TOffset ---
    faces_start = _deref(raw, body_base + 24)
    if not faces_start:
        return None
    if faces_start + numfaces * 6 > len(raw):
        return None

    # --- Objects: 1-level TOffset ---
    objs_start = _deref(raw, body_base + 48)
    if not objs_start:
        return None

    # --- Read vertices ---
    vertices, normals, uvs = _read_verts(raw, verts_start, numverts)

    # --- Apply bone transforms for (state_index, frame) ---
    # Vertices are stored in local bone space; each object's vertex range must be
    # transformed by that bone's world matrix to produce model-space geometry.
    #
    # S3DImageryObject layout (48 bytes, compiler-padded):
    #   [44:48] OS3DImageryObjectState states  → array of S3DImageryObjectState (12 bytes each)
    # S3DImageryObjectState (12 bytes):
    #   [0:4]  int parent        — parent object index (-1 = root)
    #   [4:8]  int numanikeys
    #   [8:12] OSAniKey32 anikeys — TOffset to SAniKey32 array
    #
    # World matrix = local_matrix × parent_world_matrix  (CalcObjectMatrix convention)

    parents    = [-1] * numobjects
    local_mats = [_mat_id() for _ in range(numobjects)]

    for i in range(numobjects):
        opos_i = objs_start + i * 48
        if opos_i + 48 > len(raw):
            continue
        states_arr = _deref(raw, opos_i + 44)
        if not states_arr:
            continue
        # Select the S3DImageryObjectState entry for state_index (each entry 12 bytes)
        state_entry = states_arr + state_index * 12
        if state_entry + 12 > len(raw):
            continue
        parent_idx  = struct.unpack_from('<i', raw, state_entry    )[0]
        numanikeys  = struct.unpack_from('<i', raw, state_entry + 4)[0]
        anikeys_ptr = _deref(raw, state_entry + 8)

        parents[i] = parent_idx
        if anikeys_ptr and numanikeys > 0:
            pos, rot, scl = _parse_frameN_anikey32(raw, anikeys_ptr, numanikeys, frame)
            local_mats[i] = _make_bone_mat(pos, rot, scl)

    # Compute world matrices in topological order (root → leaves)
    # Using iterative DFS to build parent-first ordering.
    world_mats = [None] * numobjects

    def _get_world(idx, depth=0):
        if world_mats[idx] is not None:
            return world_mats[idx]
        if depth > numobjects:                      # cycle guard
            world_mats[idx] = local_mats[idx]
            return world_mats[idx]
        p = parents[idx]
        if 0 <= p < numobjects:
            pw = _get_world(p, depth + 1)
            world_mats[idx] = _mat_mul(local_mats[idx], pw)
        else:
            world_mats[idx] = local_mats[idx]
        return world_mats[idx]

    for i in range(numobjects):
        _get_world(i)

    # Apply world matrices to each object's vertex range
    for i in range(numobjects):
        opos_i  = objs_start + i * 48
        if opos_i + 48 > len(raw):
            continue
        vertpos = struct.unpack_from('<H', raw, opos_i + 34)[0]
        vertnum = struct.unpack_from('<H', raw, opos_i + 36)[0]
        if vertnum == 0:
            continue
        wm = world_mats[i]
        for vi in range(vertpos, vertpos + vertnum):
            if vi < numverts:
                vertices[vi] = _xform_pos(vertices[vi], wm)
                if vi < len(normals):
                    normals[vi] = _xform_nrm(normals[vi], wm)

    # --- Read faces with local→global index conversion ---
    # For each object: read its face range [facepos, facepos+facenum),
    # add object.vertpos to each index to get global vertex index.
    # d=0 → no-texture group (tex_index=-1), d=1..numtex → texture d-1.
    all_faces       = []
    all_tex_indices = []
    for i in range(numobjects):
        opos    = objs_start + i * 48
        if opos + 48 > len(raw):
            break
        vertpos = struct.unpack_from('<H', raw, opos + 34)[0]
        vertnum = struct.unpack_from('<H', raw, opos + 36)[0]
        if vertnum == 0:
            continue

        # Follow textures TOffset to get S3DImageryObjectTexture array
        tex_arr = _deref(raw, opos + 40)
        if not tex_arr:
            continue

        # Iterate over texture groups: d=0 (no-tex) + d=1..numtex
        for d in range(numtex + 1):
            entry = tex_arr + d * 4
            if entry + 4 > len(raw):
                break
            facepos, facenum = struct.unpack_from('<HH', raw, entry)
            if facenum == 0:
                continue
            tex_index = d - 1   # -1 = no texture, 0 = tex[0], 1 = tex[1], …
            for j in range(facenum):
                fp = faces_start + (facepos + j) * 6
                if fp + 6 > len(raw):
                    break
                a, b, c = struct.unpack_from('<HHH', raw, fp)
                ga = a + vertpos
                gb = b + vertpos
                gc = c + vertpos
                if ga < numverts and gb < numverts and gc < numverts:
                    all_faces.append((ga, gb, gc))
                    all_tex_indices.append(tex_index)

    # Fallback: per-object tex-group parsing produced no faces (e.g. all tex_arr
    # TOffsets are null).  Read faces globally treating indices as-is; correct for
    # single-object models, approximate for multi-object ones.
    if not all_faces and numfaces > 0:
        for i in range(numfaces):
            fp = faces_start + i * 6
            if fp + 6 > len(raw):
                break
            a, b, c = struct.unpack_from('<HHH', raw, fp)
            if a < numverts and b < numverts and c < numverts:
                all_faces.append((a, b, c))
                all_tex_indices.append(-1)

    if not vertices or not all_faces:
        return None

    # --- Build rig (only at bind pose — state 0, frame 0) ---
    # Rig is geometry-independent and always reflects the bind pose regardless
    # of which state/frame was decoded for the mesh.
    rig = None
    if state_index == 0 and frame == 0:
        bone_names   = []
        bone_parents_rig = []
        world_mats_rig   = []
        vertex_bone_rig  = [0] * numverts
        for i in range(numobjects):
            opos_i = objs_start + i * 48
            if opos_i + 48 > len(raw):
                bone_names.append(f"bone{i}")
                bone_parents_rig.append(-1)
                world_mats_rig.append(_mat_id())
                continue
            raw_name = raw[opos_i:opos_i + 32].split(b'\x00')[0]
            bone_names.append(raw_name.decode('ascii', errors='replace').strip() or f"bone{i}")
            bone_parents_rig.append(parents[i])
            world_mats_rig.append(world_mats[i] if world_mats[i] is not None else _mat_id())
            vertpos = struct.unpack_from('<H', raw, opos_i + 34)[0]
            vertnum = struct.unpack_from('<H', raw, opos_i + 36)[0]
            for vi in range(vertpos, min(vertpos + vertnum, numverts)):
                vertex_bone_rig[vi] = i
        numstates_hdr = struct.unpack_from('<i', raw, 24)[0]
        rig = I3DRig(
            num_bones    = numobjects,
            bone_names   = bone_names,
            bone_parents = bone_parents_rig,
            world_mats   = world_mats_rig,
            vertex_bone  = vertex_bone_rig,
            _raw         = raw,
            _body_base   = body_base,
            _objs_start  = objs_start,
            _numstates   = max(0, numstates_hdr),
        )

    return I3DGeometry(
        vertices=vertices, faces=all_faces, stride=STRIDE,
        vert_count=numverts, idx_count=len(all_faces),
        path=path, normals=normals, uvs=uvs,
        anim_states=anim_states, face_tex_indices=all_tex_indices,
        rig=rig, state_index=state_index,
        _raw_vbuf=raw, _vbuf_start=verts_start, _bind_vc=numverts,
        _body_base=body_base,
    )


# --- Old format decoder (SOld3DImageryBody) -----------------------------------

def _decode_old(raw: bytes, body_base: int, path: Path,
                anim_states: List[AnimState]) -> Optional[I3DGeometry]:
    """
    Decode SOld3DImageryBody (no I3D_3DIMAGEBODY2 flag).
    Used by magic effects and other simple objects (typically single-object quad meshes).
    Face indices are global.
    """
    if body_base + 272 > len(raw):
        return None

    numverts = struct.unpack_from('<i', raw, body_base + 4)[0]
    numfaces = struct.unpack_from('<i', raw, body_base + 264)[0]

    if numverts <= 0 or numfaces <= 0:
        return None

    # Vertices: verts[0] is OFFSET at body+8 → frame OFFSET array → vertex data
    l1 = _deref(raw, body_base + 8)
    if not l1:
        return None
    verts_start = _deref(raw, l1)
    if not verts_start:
        return None

    if verts_start + numverts * STRIDE > len(raw):
        return None

    # Faces: 1-level OFFSET at body+268
    faces_start = _deref(raw, body_base + 268)
    if not faces_start:
        return None
    if faces_start + numfaces * 6 > len(raw):
        return None

    vertices, normals, uvs = _read_verts(raw, verts_start, numverts)

    faces = []
    for i in range(numfaces):
        fp = faces_start + i * 6
        if fp + 6 > len(raw):
            break
        a, b, c = struct.unpack_from('<HHH', raw, fp)
        if a < numverts and b < numverts and c < numverts:
            faces.append((a, b, c))

    if not vertices or not faces:
        return None

    return I3DGeometry(
        vertices=vertices, faces=faces, stride=STRIDE,
        vert_count=numverts, idx_count=len(faces),
        path=path, normals=normals, uvs=uvs,
        anim_states=anim_states, state_index=0,
        _raw_vbuf=raw, _vbuf_start=verts_start, _bind_vc=numverts,
    )


# --- Embedded texture extractor -----------------------------------------------

def decode_i3d_textures(path: Path) -> "List[object]":
    """
    Extract all embedded DirectDraw textures from a new-format CGSR .i3d file.
    Returns a list of PIL RGBA Images (one per texture slot), empty list if none.

    S3DImageryBody texture layout (confirmed from 3dimagebody.h):
      body+36: int numtextures
      body+40: OS3DImageryTexture textures  (TOffset)

    S3DImageryTexture (120 bytes):
      [0:108]  DDSURFACEDESC desc
        +8 dwHeight, +12 dwWidth
        +72 DDPIXELFORMAT (32 bytes):
           +76 dwFlags  (DDPF_RGB=0x40, DDPF_PALETTEINDEXED8=0x20)
           +84 dwRGBBitCount
           +88/92/96 R/G/B masks
      [108:112] OFFSET bits  → TOffset to array of frame OFFSETs
      [112:116] OFFSET pals  → TOffset to X1R5G5B5 palette (or 0)
      [116:120] int frames

    Character models use 16-bit RGB565 (pf_flags=DDPF_RGB, bitcount=16).
    """
    try:
        from PIL import Image
    except ImportError:
        return []
    try:
        raw = path.read_bytes()
        if len(raw) < 24 or raw[:4] != CGSR_MAGIC:
            return []

        hdrsize   = struct.unpack_from('<I', raw, 16)[0]
        body_base = 20 + hdrsize
        if body_base + 44 > len(raw):
            return []

        if not (struct.unpack_from('<I', raw, body_base)[0] & I3D_3DIMAGEBODY2):
            return []

        numtex = struct.unpack_from('<i', raw, body_base + 36)[0]
        if numtex <= 0:
            return []

        textures_p = _deref(raw, body_base + 40)
        if not textures_p:
            return []

        DDPF_RGB            = 0x40
        DDPF_PALETTEINDEXED8 = 0x20
        TEX_STRIDE          = 120   # sizeof(S3DImageryTexture)

        def _shift(mask): return (mask & -mask).bit_length() - 1 if mask else 0
        def _bits(mask):  return (mask >> _shift(mask)).bit_length() if mask else 0

        result = []
        for tex_i in range(numtex):
            tp = textures_p + tex_i * TEX_STRIDE
            if tp + TEX_STRIDE > len(raw):
                result.append(None)
                continue

            dw_height = struct.unpack_from('<I', raw, tp +  8)[0]
            dw_width  = struct.unpack_from('<I', raw, tp + 12)[0]
            if dw_width == 0 or dw_height == 0:
                result.append(None)
                continue

            # DDPIXELFORMAT at DDSURFACEDESC+72
            pf_flags    = struct.unpack_from('<I', raw, tp + 76)[0]
            pf_bitcount = struct.unpack_from('<I', raw, tp + 84)[0]
            pf_rmask    = struct.unpack_from('<I', raw, tp + 88)[0]
            pf_gmask    = struct.unpack_from('<I', raw, tp + 92)[0]
            pf_bmask    = struct.unpack_from('<I', raw, tp + 96)[0]
            frames      = struct.unpack_from('<i', raw, tp + 116)[0]
            if frames <= 0:
                result.append(None)
                continue

            bits_arr   = _deref(raw, tp + 108)
            if not bits_arr:
                result.append(None)
                continue
            frame0_ptr = _deref(raw, bits_arr)
            if not frame0_ptr:
                result.append(None)
                continue

            img = None
            if (pf_flags & DDPF_RGB) and pf_bitcount == 16:
                data_size = dw_width * dw_height * 2
                if frame0_ptr + data_size <= len(raw):
                    rs, gs, bs = _shift(pf_rmask), _shift(pf_gmask), _shift(pf_bmask)
                    rb, gb, bb = _bits(pf_rmask),  _bits(pf_gmask),  _bits(pf_bmask)
                    rsc = 8 - rb; gsc = 8 - gb; bsc = 8 - bb
                    words = struct.unpack_from(f'<{dw_width * dw_height}H', raw, frame0_ptr)
                    pixels = [
                        (((w >> rs) & (pf_rmask >> rs)) << rsc,
                         ((w >> gs) & (pf_gmask >> gs)) << gsc,
                         ((w >> bs) & (pf_bmask >> bs)) << bsc)
                        for w in words
                    ]
                    img = Image.new('RGB', (dw_width, dw_height))
                    img.putdata(pixels)
                    img = img.convert('RGBA')

            elif pf_flags & DDPF_PALETTEINDEXED8:
                pals_ptr = _deref(raw, tp + 112)
                data_size = dw_width * dw_height
                if pals_ptr and pals_ptr + 512 <= len(raw) and frame0_ptr + data_size <= len(raw):
                    pal = []
                    for pi in range(256):
                        w = struct.unpack_from('<H', raw, pals_ptr + pi * 2)[0]
                        pal.append((((w >> 10) & 0x1F) << 3,
                                    ((w >>  5) & 0x1F) << 3,
                                     (w        & 0x1F) << 3,
                                     0 if pi == 0 else 255))
                    pixels = [pal[b] for b in raw[frame0_ptr:frame0_ptr + data_size]]
                    img = Image.new('RGBA', (dw_width, dw_height))
                    img.putdata(pixels)

            result.append(img)

        return [img for img in result if img is not None]

    except Exception:
        pass
    return []


def decode_i3d_texture(path: Path) -> "Optional[object]":
    """Return the first embedded texture, or None. (Backward-compat wrapper.)"""
    textures = decode_i3d_textures(path)
    return textures[0] if textures else None


# --- Main decoder -------------------------------------------------------------

def decode_i3d_geometry(path: Path, state_index: int = 0,
                        frame: int = 0) -> Optional[I3DGeometry]:
    """
    Parse a CGSR .i3d file and return geometry for the given state and frame.

    Handles both S3DImageryBody (new) and SOld3DImageryBody (old) formats.
    Old format only supports state 0 / frame 0 (single static mesh).
    """
    try:
        raw = path.read_bytes()
    except Exception as exc:
        log.error("Cannot read %s: %s", path.name, exc)
        return None

    if len(raw) < 24 or raw[:4] != CGSR_MAGIC:
        log.debug("Not a CGSR file: %s", path.name)
        return None

    hdrsize   = struct.unpack_from('<I', raw, 16)[0]
    body_base = 20 + hdrsize

    if body_base + 8 > len(raw):
        return None

    numstates = struct.unpack_from('<i', raw, 24)[0]
    if numstates < 0 or numstates > 4096:
        numstates = 0

    anim_states = _parse_anim_states(raw, 20, numstates)

    flags = struct.unpack_from('<I', raw, body_base)[0]
    fmt   = "new (S3DImageryBody)" if (flags & I3D_3DIMAGEBODY2) else "old (SOld3DImageryBody)"
    log.debug("Decoding %s  format=%s  states=%d  state_idx=%d  frame=%d",
              path.name, fmt, numstates, state_index, frame)

    if flags & I3D_3DIMAGEBODY2:
        geom = _decode_new(raw, body_base, 0, 0, path, anim_states,
                           state_index=state_index, frame=frame)
    else:
        geom = _decode_old(raw, body_base, path, anim_states)

    if geom is None:
        log.warning("Decode returned None for %s", path.name)
    return geom


# --- Animation state listing --------------------------------------------------

def list_anim_states(path: Path) -> List[AnimState]:
    """Return animation state names for a .i3d file (geometry-free)."""
    try:
        raw = path.read_bytes()
        if len(raw) < 28 or raw[:4] != CGSR_MAGIC:
            return []
        numstates = struct.unpack_from('<i', raw, 24)[0]
        if numstates < 0 or numstates > 4096:
            return []
        return _parse_anim_states(raw, 20, numstates)
    except Exception:
        return []


# --- load_state (bind-pose only — no morph animation in these files) ----------

def load_state(geom: I3DGeometry, state_index: int, frame: int = 0) -> bool:
    """
    Mutate geom in-place to show the given animation state and frame.
    Returns True on success, False if the state/frame is out of range or
    the raw bytes are unavailable (old-format models).
    """
    raw       = geom._raw_vbuf
    body_base = geom._body_base
    if not raw or not body_base:
        return False

    flags = struct.unpack_from('<I', raw, body_base)[0]
    if not (flags & I3D_3DIMAGEBODY2):
        return False   # old format: single static mesh

    numstates = struct.unpack_from('<i', raw, 24)[0]
    if numstates <= 0 or state_index >= numstates:
        return False

    nframes = geom.anim_states[state_index].nframes if state_index < len(geom.anim_states) else 0
    if nframes > 0 and frame >= nframes:
        frame = frame % nframes

    new_geom = _decode_new(raw, body_base, 0, 0, geom.path, geom.anim_states,
                           state_index=state_index, frame=frame)
    if new_geom is None:
        return False

    geom.vertices    = new_geom.vertices
    geom.normals     = new_geom.normals
    geom.uvs         = new_geom.uvs
    geom.state_index = state_index
    return True


# --- OBJ exporter -------------------------------------------------------------

def export_obj(geom: I3DGeometry, out_path: Path, texture=None) -> bool:
    """
    Export I3DGeometry as Wavefront OBJ with normals and UVs.

    If `texture` is a PIL Image, also writes a sidecar .mtl and saves the
    texture as a .png next to the OBJ so the material loads in Blender/viewers.
    """
    try:
        has_n = len(geom.normals) == len(geom.vertices)
        has_u = len(geom.uvs)     == len(geom.vertices)
        stem  = out_path.stem

        mtl_lines = None
        tex_path  = None
        if texture is not None and has_u:
            tex_path = out_path.with_name(stem + "_tex.png")
            mtl_path = out_path.with_suffix(".mtl")
            mtl_lines = [
                f"# RevEngine material for {stem}",
                f"newmtl mat0",
                f"Kd 1 1 1",
                f"map_Kd {tex_path.name}",
            ]

        lines = [
            "# RevEngine - Revenant (1999) i3d export",
            f"# Source: {geom.path.name}  v={len(geom.vertices)}  f={len(geom.faces)}",
            f"# States: {', '.join(s.name for s in geom.anim_states) or 'none'}",
            "",
        ]
        if mtl_lines:
            lines.append(f"mtllib {stem}.mtl")
        lines += ["", f"o {stem}", ""]
        if mtl_lines:
            lines.append("usemtl mat0")

        for x, y, z in geom.vertices:
            lines.append(f"v {x:.6f} {y:.6f} {z:.6f}")
        lines.append("")
        if has_u:
            for u, v in geom.uvs:
                lines.append(f"vt {u:.6f} {1.0 - v:.6f}")
            lines.append("")
        if has_n:
            for nx, ny, nz in geom.normals:
                lines.append(f"vn {nx:.6f} {ny:.6f} {nz:.6f}")
            lines.append("")
        for a, b, c in geom.faces:
            ai, bi, ci = a + 1, b + 1, c + 1
            if has_u and has_n:
                lines.append(f"f {ai}/{ai}/{ai} {bi}/{bi}/{bi} {ci}/{ci}/{ci}")
            elif has_u:
                lines.append(f"f {ai}/{ai} {bi}/{bi} {ci}/{ci}")
            elif has_n:
                lines.append(f"f {ai}//{ai} {bi}//{bi} {ci}//{ci}")
            else:
                lines.append(f"f {ai} {bi} {ci}")

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("\n".join(lines), encoding="ascii")

        if mtl_lines:
            mtl_path.write_text("\n".join(mtl_lines), encoding="ascii")
            texture.convert("RGB").save(str(tex_path))

        return True
    except Exception:
        return False


# --- glTF 2.0 exporter --------------------------------------------------------

def export_gltf(geom: I3DGeometry, out_path: Path) -> bool:
    """Export I3DGeometry as self-contained glTF 2.0 (base64 embedded)."""
    try:
        has_n = len(geom.normals) == len(geom.vertices)
        has_u = len(geom.uvs)     == len(geom.vertices)
        vc = len(geom.vertices); fc = len(geom.faces)

        pos_data = bytearray()
        min_p = [float('inf')] * 3; max_p = [float('-inf')] * 3
        for x, y, z in geom.vertices:
            pos_data += struct.pack('<fff', x, y, z)
            for k, val in enumerate((x, y, z)):
                if val < min_p[k]: min_p[k] = val
                if val > max_p[k]: max_p[k] = val

        nrm_data = bytearray()
        if has_n:
            for nx, ny, nz in geom.normals:
                nrm_data += struct.pack('<fff', nx, ny, nz)

        uv_data = bytearray()
        if has_u:
            for u, v in geom.uvs:
                uv_data += struct.pack('<ff', u, v)

        idx_data = bytearray()
        for a, b, c in geom.faces:
            idx_data += struct.pack('<HHH', a, b, c)
        if len(idx_data) % 4:
            idx_data += b'\x00' * (4 - len(idx_data) % 4)

        combined = bytes(pos_data + nrm_data + uv_data + idx_data)
        buf_uri  = "data:application/octet-stream;base64," + base64.b64encode(combined).decode()

        offsets = [0, len(pos_data), len(pos_data) + len(nrm_data),
                   len(pos_data) + len(nrm_data) + len(uv_data)]
        bvs, acs, attrs = [], [], {}
        bvs.append({"buffer": 0, "byteOffset": offsets[0], "byteLength": len(pos_data)})
        acs.append({"bufferView": 0, "componentType": 5126, "count": vc, "type": "VEC3",
                    "min": min_p, "max": max_p})
        attrs["POSITION"] = 0
        bv_i = ac_i = 1

        if has_n:
            bvs.append({"buffer": 0, "byteOffset": offsets[1], "byteLength": len(nrm_data)})
            acs.append({"bufferView": bv_i, "componentType": 5126, "count": vc, "type": "VEC3"})
            attrs["NORMAL"] = ac_i; bv_i += 1; ac_i += 1

        if has_u:
            bvs.append({"buffer": 0, "byteOffset": offsets[2], "byteLength": len(uv_data)})
            acs.append({"bufferView": bv_i, "componentType": 5126, "count": vc, "type": "VEC2"})
            attrs["TEXCOORD_0"] = ac_i; bv_i += 1; ac_i += 1

        bvs.append({"buffer": 0, "byteOffset": offsets[3], "byteLength": fc * 6})
        acs.append({"bufferView": bv_i, "componentType": 5123, "count": fc * 3, "type": "SCALAR"})

        gltf = {
            "asset": {"version": "2.0", "generator": "RevEngine"},
            "scene": 0,
            "scenes": [{"name": geom.path.stem, "nodes": [0]}],
            "nodes":  [{"name": geom.path.stem, "mesh": 0,
                        "extras": {"allStates": [s.name for s in geom.anim_states]}}],
            "meshes": [{"name": geom.path.stem,
                        "primitives": [{"attributes": attrs, "indices": ac_i, "mode": 4}]}],
            "bufferViews": bvs,
            "accessors":   acs,
            "buffers": [{"uri": buf_uri, "byteLength": len(combined)}],
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(gltf, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False
