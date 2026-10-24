# -*- coding: utf-8 -*-
"""PMX 2.0 / 2.1 读取与写入核心。

设计要点：
- 顶点/面数据使用 numpy 数组，保证大模型（十万级顶点）的加载、蒙皮与渲染性能；
- 骨骼、材质、刚体、关节、形态等使用轻量 dataclass，便于界面直接编辑；
- 读写严格遵循 PMX 2.0/2.1 规范，保留原始编码、索引宽度与全部字段。
"""
from __future__ import annotations

import copy
import os
import struct
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

# ---------------------------------------------------------------- 常量

WT_BDEF1, WT_BDEF2, WT_BDEF4, WT_SDEF, WT_QDEF = range(5)
WT_NAMES = {0: "BDEF1", 1: "BDEF2", 2: "BDEF4", 3: "SDEF", 4: "QDEF"}

# 骨骼标志位（与 PMX 规范一致）
BF_TAIL_INDEX = 0x0001
BF_ROTATABLE = 0x0002
BF_TRANSLATABLE = 0x0004
BF_VISIBLE = 0x0008
BF_ENABLED = 0x0010
BF_IK = 0x0020
BF_LOCAL_APPEND = 0x0080
BF_INHERIT_ROT = 0x0100
BF_INHERIT_MOV = 0x0200
BF_FIXED_AXIS = 0x0400
BF_LOCAL_AXIS = 0x0800
BF_AFTER_PHYSICS = 0x1000
BF_EXTERNAL_PARENT = 0x2000

# 材质绘制标志
MF_DOUBLE_SIDED = 0x01
MF_GROUND_SHADOW = 0x02
MF_SHADOW_MAP = 0x04
MF_SELF_SHADOW = 0x08
MF_EDGE = 0x10
MF_VERTEX_COLOR = 0x20
MF_POINT = 0x40
MF_LINE = 0x80

SHAPE_NAMES = {0: "球", 1: "箱", 2: "胶囊"}
SPHERE_MODE_NAMES = {0: "无", 1: "乘法 (sph)", 2: "加法 (spa)", 3: "子纹理"}
RB_MODE_NAMES = {0: "骨骼跟随", 1: "物理演算", 2: "物理演算 + 骨骼对齐"}
JOINT_TYPE_NAMES = {0: "弹簧 6DOF", 1: "6DOF", 2: "P2P", 3: "ConeTwist", 4: "Slider", 5: "Hinge"}
MORPH_TYPE_NAMES = {
    0: "组", 1: "顶点", 2: "骨骼", 3: "UV", 4: "附加 UV1", 5: "附加 UV2",
    6: "附加 UV3", 7: "附加 UV4", 8: "材质", 9: "翻转", 10: "冲量",
}
MORPH_PANEL_NAMES = {0: "系统", 1: "眉", 2: "眼", 3: "口", 4: "其他"}

# ---------------------------------------------------------------- 数据结构

class _FastCopy:
    """dataclass 的快速深拷贝。

    通用 copy.deepcopy 对每个 dataclass 实例都要走 __reduce_ex__ 协议，
    十万级顶点 + 数百个骨骼/刚体/关节的模型因此多花一倍以上时间；
    这里逐字段按类型手写规则，语义与 deepcopy 一致（数组、列表、嵌套对象都复制）。
    """

    def __deepcopy__(self, memo):
        cls = self.__class__
        new = cls.__new__(cls)
        memo[id(self)] = new
        for key, val in self.__dict__.items():
            setattr(new, key, _copy_value(val, memo))
        return new


def _copy_value(val, memo):
    if val is None or isinstance(val, (int, float, str, bool, np.integer, np.floating)):
        return val
    if isinstance(val, np.ndarray):
        return val.copy()
    if isinstance(val, _FastCopy):
        return val.__deepcopy__(memo)
    if isinstance(val, list):
        return [_copy_value(v, memo) for v in val]
    if isinstance(val, tuple):
        return tuple(_copy_value(v, memo) for v in val)
    if isinstance(val, dict):
        # 形态偏移项是「dict + 平坦 float 列表」，这里做一层特化避免逐项走递归
        out = {}
        for key, item in val.items():
            kind = type(item)
            if kind is float or kind is int or kind is str or item is None:
                out[key] = item
            elif kind is list and (not item or type(item[0]) is not list):
                out[key] = item.copy()
            else:
                out[key] = _copy_value(item, memo)
        return out
    return copy.deepcopy(val, memo)


@dataclass
class IKLink(_FastCopy):
    bone: int = -1
    limited: bool = False
    lo: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    hi: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

@dataclass
class IK(_FastCopy):
    target: int = -1
    loop: int = 40
    angle: float = 0.5
    links: List[IKLink] = field(default_factory=list)

@dataclass
class Bone(_FastCopy):
    name: str = ""
    name_en: str = ""
    pos: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    parent: int = -1
    layer: int = 0
    flags: int = BF_ROTATABLE | BF_TRANSLATABLE | BF_VISIBLE | BF_ENABLED
    tail_bone: int = -1
    tail_offset: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    append_parent: int = -1
    append_ratio: float = 0.0
    axis: List[float] = field(default_factory=lambda: [0.0, 0.0, 1.0])
    local_x: List[float] = field(default_factory=lambda: [1.0, 0.0, 0.0])
    local_z: List[float] = field(default_factory=lambda: [0.0, 0.0, 1.0])
    ext_key: int = 0
    ik: Optional[IK] = None

@dataclass
class Material(_FastCopy):
    name: str = ""
    name_en: str = ""
    diffuse: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0, 1.0])
    specular: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    specular_coef: float = 0.0
    ambient: List[float] = field(default_factory=lambda: [0.5, 0.5, 0.5])
    draw_flags: int = MF_DOUBLE_SIDED | MF_GROUND_SHADOW | MF_EDGE
    edge_color: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 1.0])
    edge_size: float = 1.0
    texture: int = -1
    sphere: int = -1
    sphere_mode: int = 0
    toon_shared: int = 0
    toon: int = 0
    memo: str = ""
    face_count: int = 0

    @property
    def alpha(self) -> float:
        return float(self.diffuse[3])

@dataclass
class Morph(_FastCopy):
    name: str = ""
    name_en: str = ""
    panel: int = 4
    type: int = 1
    offsets: List[dict] = field(default_factory=list)

    def __deepcopy__(self, memo):
        """形态快照只复制外层列表与每个偏移字典的平坦列表。

        形态偏移是全模型里对象数最多的部分（大模型可达数万项），通用
        _copy_value 要逐项做类型分派；这里就地展开成两层循环，既保持
        「快照与在线模型互不影响」的隔离性，又省掉函数调用开销。
        """
        new = Morph.__new__(Morph)
        memo[id(self)] = new
        new.name = self.name
        new.name_en = self.name_en
        new.panel = self.panel
        new.type = self.type
        copied = []
        for off in self.offsets:
            d = off.copy()
            for key, val in off.items():
                if type(val) is list:
                    d[key] = val.copy()
            copied.append(d)
        new.offsets = copied
        return new


@dataclass
class DisplayFrame(_FastCopy):
    name: str = ""
    name_en: str = ""
    special: int = 0
    items: List[tuple] = field(default_factory=list)  # (0=骨骼,1=形态, index)

@dataclass
class RigidBody(_FastCopy):
    name: str = ""
    name_en: str = ""
    bone: int = -1
    group: int = 0
    mask: int = 0xFFFF
    shape: int = 0
    size: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    pos: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rot: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    mass: float = 1.0
    mov_damp: float = 0.5
    rot_damp: float = 0.5
    repel: float = 0.0
    friction: float = 0.5
    mode: int = 0

@dataclass
class Joint(_FastCopy):
    name: str = ""
    name_en: str = ""
    type: int = 0
    rigid_a: int = -1
    rigid_b: int = -1
    pos: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rot: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    min_loc: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    max_loc: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    min_rot: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    max_rot: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    spring_loc: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    spring_rot: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

@dataclass
class SoftBody(_FastCopy):
    name: str = ""
    name_en: str = ""
    shape: int = 0
    material: int = -1
    group: int = 0
    mask: int = 0xFFFF
    flags: int = 0
    b_link_dist: int = 0
    cluster_count: int = 0
    total_mass: float = 0.0
    collision_margin: float = 0.0
    aero_model: int = 0
    config: List[float] = field(default_factory=lambda: [0.0] * 12)
    cluster: List[float] = field(default_factory=lambda: [0.0] * 6)
    iteration: List[int] = field(default_factory=lambda: [0, 0, 0, 0])
    material_params: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    anchors: List[tuple] = field(default_factory=list)  # (刚体, 顶点, near)
    pins: List[int] = field(default_factory=list)

class PMXModel(_FastCopy):
    """PMX 模型。顶点/面为 numpy 数组，其余为对象列表。"""

    def __init__(self):
        self.path = ""
        self.version = 2.0
        self.encoding = 0          # 0 = UTF-16LE, 1 = UTF-8
        self.add_uv = 0
        self.vsz = 2
        self.tsz = 1
        self.msz = 1
        self.bsz = 2
        self.mosz = 1
        self.rsz = 1
        self.name = ""
        self.name_en = ""
        self.comment = ""
        self.comment_en = ""

        self.v_pos = np.zeros((0, 3), np.float32)
        self.v_nrm = np.zeros((0, 3), np.float32)
        self.v_uv = np.zeros((0, 2), np.float32)
        self.v_add = np.zeros((0, 0), np.float32)
        self.v_edge = np.zeros((0,), np.float32)
        self.v_wtype = np.zeros((0,), np.uint8)
        self.v_bones = np.zeros((0, 4), np.int32)
        self.v_weights = np.zeros((0, 4), np.float32)
        self.v_sdef = np.zeros((0, 9), np.float32)
        self.indices = np.zeros((0,), np.int32)
        self.textures: List[str] = []
        self.materials: List[Material] = []
        self.bones: List[Bone] = []
        self.morphs: List[Morph] = []
        self.frames: List[DisplayFrame] = []
        self.rigid: List[RigidBody] = []
        self.joints: List[Joint] = []
        self.soft_bodies: List[SoftBody] = []

    # ------------------------------------------------------------ 便捷属性
    @property
    def n_vertices(self) -> int:
        return int(self.v_pos.shape[0])

    @property
    def n_faces(self) -> int:
        return int(self.indices.shape[0] // 3)

    @property
    def n_bones(self) -> int:
        return len(self.bones)

    @property
    def n_morphs(self) -> int:
        return len(self.morphs)

    def bone_index(self, name: str) -> int:
        for i, b in enumerate(self.bones):
            if b.name == name:
                return i
        return -1

    def material_ranges(self):
        """按材质面数返回 (material, start_index, count)。"""
        out, start = [], 0
        for m in self.materials:
            cnt = int(m.face_count)
            if cnt > 0:
                out.append((m, start, cnt))
            start += cnt
        if start < len(self.indices):
            out.append((None, start, len(self.indices) - start))
        return out

    def base_dir(self) -> str:
        return os.path.dirname(os.path.abspath(self.path)) if self.path else ""

    def resolve_texture(self, index: int) -> str:
        if not (0 <= index < len(self.textures)):
            return ""
        p = self.textures[index].replace("\\", os.sep)
        if os.path.isabs(p):
            return p
        return os.path.normpath(os.path.join(self.base_dir(), p))

# ---------------------------------------------------------------- 读取

class _Reader:
    __slots__ = ("d", "o", "enc")

    def __init__(self, data: bytes, enc: int):
        self.d = data
        self.o = 0
        self.enc = enc

    def u8(self) -> int:
        v = self.d[self.o]
        self.o += 1
        return v

    def u16(self) -> int:
        v = struct.unpack_from("<H", self.d, self.o)[0]
        self.o += 2
        return v

    def i32(self) -> int:
        v = struct.unpack_from("<i", self.d, self.o)[0]
        self.o += 4
        return v

    def f32(self) -> float:
        v = struct.unpack_from("<f", self.d, self.o)[0]
        self.o += 4
        return v

    def f3(self):
        v = struct.unpack_from("<3f", self.d, self.o)
        self.o += 12
        return [v[0], v[1], v[2]]

    def f4(self):
        v = struct.unpack_from("<4f", self.d, self.o)
        self.o += 16
        return [v[0], v[1], v[2], v[3]]

    def text(self) -> str:
        n = self.i32()
        raw = self.d[self.o:self.o + n]
        self.o += n
        return raw.decode("utf-16-le" if self.enc == 0 else "utf-8", "replace")

    def sindex(self, size: int) -> int:
        fmt = {1: "<b", 2: "<h", 4: "<i"}[size]
        v = struct.unpack_from(fmt, self.d, self.o)[0]
        self.o += size
        return v

    def uindex(self, size: int) -> int:
        fmt = {1: "<B", 2: "<H", 4: "<I"}[size]
        v = struct.unpack_from(fmt, self.d, self.o)[0]
        self.o += size
        return v

def load_pmx(path: str) -> PMXModel:
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"PMX ":
        raise ValueError("不是有效的 PMX 文件（文件头应为 'PMX '）")

    m = PMXModel()
    m.path = path
    o = 4
    m.version = round(struct.unpack_from("<f", data, o)[0], 3)
    o += 4
    glob_n = data[o]
    o += 1
    glob = data[o:o + glob_n]
    o += glob_n
    m.encoding, m.add_uv, m.vsz, m.tsz, m.msz, m.bsz, m.mosz, m.rsz = list(glob[:8])
    r = _Reader(data, m.encoding)
    r.o = o

    m.name = r.text()
    m.name_en = r.text()
    m.comment = r.text()
    m.comment_en = r.text()

    # ---- 顶点
    nv = r.i32()
    pos = np.empty((nv, 3), np.float32)
    nrm = np.empty((nv, 3), np.float32)
    uv = np.empty((nv, 2), np.float32)
    add = np.empty((nv, m.add_uv * 4), np.float32) if m.add_uv else np.zeros((nv, 0), np.float32)
    edge = np.empty((nv,), np.float32)
    wtype = np.empty((nv,), np.uint8)
    bones = np.zeros((nv, 4), np.int32)
    weights = np.zeros((nv, 4), np.float32)
    sdef = np.zeros((nv, 9), np.float32)
    d = data
    unpack = struct.unpack_from
    for i in range(nv):
        pos[i] = unpack("<3f", d, r.o)
        r.o += 12
        nrm[i] = unpack("<3f", d, r.o)
        r.o += 12
        uv[i] = unpack("<2f", d, r.o)
        r.o += 8
        for k in range(m.add_uv):
            add[i, k * 4:k * 4 + 4] = unpack("<4f", d, r.o)
            r.o += 16
        wt = d[r.o]
        r.o += 1
        wtype[i] = wt
        if wt == 0:
            bones[i, 0] = r.sindex(m.bsz)
            weights[i, 0] = 1.0
        elif wt == 1:
            bones[i, 0] = r.sindex(m.bsz)
            bones[i, 1] = r.sindex(m.bsz)
            weights[i, 0] = r.f32()
            weights[i, 1] = 1.0 - weights[i, 0]
        elif wt in (2, 4):
            for k in range(4):
                bones[i, k] = r.sindex(m.bsz)
            for k in range(4):
                weights[i, k] = r.f32()
        elif wt == 3:
            bones[i, 0] = r.sindex(m.bsz)
            bones[i, 1] = r.sindex(m.bsz)
            weights[i, 0] = r.f32()
            weights[i, 1] = 1.0 - weights[i, 0]
            sdef[i, 0:3] = unpack("<3f", d, r.o)
            r.o += 12
            sdef[i, 3:6] = unpack("<3f", d, r.o)
            r.o += 12
            sdef[i, 6:9] = unpack("<3f", d, r.o)
            r.o += 12
        else:
            raise ValueError("未知的顶点权重类型 %d（顶点 %d）" % (wt, i))
        edge[i] = r.f32()

    m.v_pos, m.v_nrm, m.v_uv, m.v_add = pos, nrm, uv, add
    m.v_edge, m.v_wtype, m.v_bones, m.v_weights, m.v_sdef = edge, wtype, bones, weights, sdef

    # ---- 面
    nf = r.i32()
    dtype = {1: np.uint8, 2: np.uint16, 4: np.int32}[m.vsz]
    m.indices = np.frombuffer(d, dtype=dtype, count=nf, offset=r.o).astype(np.int32)
    r.o += nf * m.vsz

    # ---- 贴图表
    nt = r.i32()
    m.textures = [r.text() for _ in range(nt)]

    # ---- 材质
    nm = r.i32()
    for _ in range(nm):
        mt = Material()
        mt.name = r.text()
        mt.name_en = r.text()
        mt.diffuse = r.f4()
        mt.specular = r.f3()
        mt.specular_coef = r.f32()
        mt.ambient = r.f3()
        mt.draw_flags = r.u8()
        mt.edge_color = r.f4()
        mt.edge_size = r.f32()
        mt.texture = r.sindex(m.tsz)
        mt.sphere = r.sindex(m.tsz)
        mt.sphere_mode = r.u8()
        mt.toon_shared = r.u8()
        mt.toon = r.sindex(m.tsz) if mt.toon_shared == 0 else r.u8()
        mt.memo = r.text()
        mt.face_count = r.i32()
        m.materials.append(mt)

    # ---- 骨骼
    nb = r.i32()
    for _ in range(nb):
        b = Bone()
        b.name = r.text()
        b.name_en = r.text()
        b.pos = r.f3()
        b.parent = r.sindex(m.bsz)
        b.layer = r.i32()
        b.flags = r.u16()
        if b.flags & BF_TAIL_INDEX:
            b.tail_bone = r.sindex(m.bsz)
            b.tail_offset = [0.0, 0.0, 0.0]
        else:
            b.tail_bone = -1
            b.tail_offset = r.f3()
        if b.flags & (BF_INHERIT_ROT | BF_INHERIT_MOV):
            b.append_parent = r.sindex(m.bsz)
            b.append_ratio = r.f32()
        if b.flags & BF_FIXED_AXIS:
            b.axis = r.f3()
        if b.flags & BF_LOCAL_AXIS:
            b.local_x = r.f3()
            b.local_z = r.f3()
        if b.flags & BF_EXTERNAL_PARENT:
            b.ext_key = r.i32()
        if b.flags & BF_IK:
            ik = IK()
            ik.target = r.sindex(m.bsz)
            ik.loop = r.i32()
            ik.angle = r.f32()
            n = r.i32()
            for _ in range(n):
                link = IKLink()
                link.bone = r.sindex(m.bsz)
                link.limited = bool(r.u8())
                if link.limited:
                    link.lo = r.f3()
                    link.hi = r.f3()
                ik.links.append(link)
            b.ik = ik
        m.bones.append(b)

    # ---- 形态
    nmo = r.i32()
    for _ in range(nmo):
        mo = Morph()
        mo.name = r.text()
        mo.name_en = r.text()
        mo.panel = r.u8()
        mo.type = r.u8()
        n = r.i32()
        t = mo.type
        for _ in range(n):
            if t == 0:
                mo.offsets.append({"morph": r.sindex(m.mosz), "ratio": r.f32()})
            elif t == 1:
                mo.offsets.append({"vertex": r.uindex(m.vsz), "offset": r.f3()})
            elif t == 2:
                mo.offsets.append({"bone": r.sindex(m.bsz), "move": r.f3(), "rot": r.f4()})
            elif 3 <= t <= 7:
                mo.offsets.append({"vertex": r.uindex(m.vsz), "offset": r.f4()})
            elif t == 8:
                mo.offsets.append({
                    "material": r.sindex(m.msz),
                    "calc": r.u8(),
                    "diffuse": r.f4(),
                    "specular": r.f3(),
                    "specular_coef": r.f32(),
                    "ambient": r.f3(),
                    "edge_color": r.f4(),
                    "edge_size": r.f32(),
                    "texture": r.f4(),
                    "sphere": r.f4(),
                    "toon": r.f4(),
                })
            elif t == 9:
                mo.offsets.append({"morph": r.sindex(m.mosz), "ratio": r.f32()})
            elif t == 10:
                mo.offsets.append({
                    "rigid": r.sindex(m.rsz), "local": r.u8(),
                    "velocity": r.f3(), "torque": r.f3(),
                })
            else:
                raise ValueError("未知形态类型 %d" % t)
        m.morphs.append(mo)

    # ---- 显示枠
    nd = r.i32()
    for _ in range(nd):
        f = DisplayFrame()
        f.name = r.text()
        f.name_en = r.text()
        f.special = r.u8()
        n = r.i32()
        for _ in range(n):
            ty = r.u8()
            idx = r.sindex(m.bsz) if ty == 0 else r.sindex(m.mosz)
            f.items.append((ty, idx))
        m.frames.append(f)

    # ---- 刚体
    nr = r.i32()
    for _ in range(nr):
        rb = RigidBody()
        rb.name = r.text()
        rb.name_en = r.text()
        rb.bone = r.sindex(m.bsz)
        rb.group = r.u8()
        rb.mask = r.u16()
        rb.shape = r.u8()
        rb.size = r.f3()
        rb.pos = r.f3()
        rb.rot = r.f3()
        rb.mass = r.f32()
        rb.mov_damp = r.f32()
        rb.rot_damp = r.f32()
        rb.repel = r.f32()
        rb.friction = r.f32()
        rb.mode = r.u8()
        m.rigid.append(rb)

    # ---- 关节
    nj = r.i32()
    for _ in range(nj):
        j = Joint()
        j.name = r.text()
        j.name_en = r.text()
        j.type = r.u8()
        j.rigid_a = r.sindex(m.rsz)
        j.rigid_b = r.sindex(m.rsz)
        j.pos = r.f3()
        j.rot = r.f3()
        j.min_loc = r.f3()
        j.max_loc = r.f3()
        j.min_rot = r.f3()
        j.max_rot = r.f3()
        j.spring_loc = r.f3()
        j.spring_rot = r.f3()
        m.joints.append(j)

    # ---- 柔体（PMX 2.1）
    if m.version >= 2.1 and r.o < len(d):
        nsoft = r.i32()
        for _ in range(nsoft):
            s = SoftBody()
            s.name = r.text()
            s.name_en = r.text()
            s.shape = r.u8()
            s.material = r.sindex(m.msz)
            s.group = r.u8()
            s.mask = r.u16()
            s.flags = r.u8()
            s.b_link_dist = r.i32()
            s.cluster_count = r.i32()
            s.total_mass = r.f32()
            s.collision_margin = r.f32()
            s.aero_model = r.i32()
            s.config = [r.f32() for _ in range(12)]
            s.cluster = [r.f32() for _ in range(6)]
            s.iteration = [r.i32() for _ in range(4)]
            s.material_params = [r.f32() for _ in range(3)]
            na = r.i32()
            for _ in range(na):
                s.anchors.append((r.sindex(m.rsz), r.uindex(m.vsz), r.u8()))
            npin = r.i32()
            for _ in range(npin):
                s.pins.append(r.uindex(m.vsz))
            m.soft_bodies.append(s)

    return m

# ---------------------------------------------------------------- 写入

class _Writer:
    __slots__ = ("buf", "enc")

    def __init__(self, enc: int):
        self.buf = bytearray()
        self.enc = enc

    def u8(self, v):
        self.buf.append(int(v) & 0xFF)

    def u16(self, v):
        self.buf += struct.pack("<H", int(v) & 0xFFFF)

    def i32(self, v):
        self.buf += struct.pack("<i", int(v))

    def f32(self, v):
        self.buf += struct.pack("<f", float(v))

    def f3(self, v):
        self.buf += struct.pack("<3f", float(v[0]), float(v[1]), float(v[2]))

    def f4(self, v):
        self.buf += struct.pack("<4f", float(v[0]), float(v[1]), float(v[2]), float(v[3]))

    def text(self, s: str):
        raw = s.encode("utf-16-le" if self.enc == 0 else "utf-8", "replace")
        self.buf += struct.pack("<i", len(raw))
        self.buf += raw

    def sindex(self, v, size):
        if size == 1:
            self.buf += struct.pack("<b", max(-128, min(127, int(v))))
        elif size == 2:
            self.buf += struct.pack("<h", max(-32768, min(32767, int(v))))
        else:
            self.buf += struct.pack("<i", int(v))

    def uindex(self, v, size):
        if size == 1:
            self.buf += struct.pack("<B", int(v) & 0xFF)
        elif size == 2:
            self.buf += struct.pack("<H", int(v) & 0xFFFF)
        else:
            self.buf += struct.pack("<I", int(v) & 0xFFFFFFFF)

def _size_for(count: int, signed: bool, preferred: int) -> int:
    limit = {1: 127, 2: 32767, 4: 2147483647}[preferred]
    low = -limit - 1 if signed else 0
    if count <= limit and count >= 0:
        return preferred
    if count <= 32767:
        return 2
    return 4

def save_pmx(model: PMXModel, path: str):
    version = 2.1 if (model.soft_bodies or any(m.type >= 9 for m in model.morphs)) else 2.0
    nv = model.n_vertices
    vsz = 1 if nv < 256 else (2 if nv < 65536 else 4)
    tsz = _size_for(max(len(model.textures), 1), True, model.tsz)
    msz = _size_for(max(len(model.materials), 1), True, model.msz)
    bsz = _size_for(max(len(model.bones), 1), True, model.bsz)
    mosz = _size_for(max(len(model.morphs), 1), True, model.mosz)
    rsz = _size_for(max(len(model.rigid), 1), True, model.rsz)

    w = _Writer(model.encoding)
    w.buf += b"PMX "
    w.f32(version)
    w.u8(8)
    w.buf += bytes([model.encoding, model.add_uv, vsz, tsz, msz, bsz, mosz, rsz])
    w.text(model.name)
    w.text(model.name_en)
    w.text(model.comment)
    w.text(model.comment_en)

    # 顶点
    w.i32(nv)
    add_uv = model.add_uv
    for i in range(nv):
        w.f3(model.v_pos[i])
        w.f3(model.v_nrm[i])
        w.buf += struct.pack("<2f", float(model.v_uv[i, 0]), float(model.v_uv[i, 1]))
        for k in range(add_uv):
            w.buf += struct.pack("<4f", *[float(x) for x in model.v_add[i, k * 4:k * 4 + 4]])
        wt = int(model.v_wtype[i])
        w.u8(wt)
        if wt == 0:
            w.sindex(model.v_bones[i, 0], bsz)
        elif wt == 1:
            w.sindex(model.v_bones[i, 0], bsz)
            w.sindex(model.v_bones[i, 1], bsz)
            w.f32(model.v_weights[i, 0])
        elif wt in (2, 4):
            for k in range(4):
                w.sindex(model.v_bones[i, k], bsz)
            for k in range(4):
                w.f32(model.v_weights[i, k])
        elif wt == 3:
            w.sindex(model.v_bones[i, 0], bsz)
            w.sindex(model.v_bones[i, 1], bsz)
            w.f32(model.v_weights[i, 0])
            w.f3(model.v_sdef[i, 0:3])
            w.f3(model.v_sdef[i, 3:6])
            w.f3(model.v_sdef[i, 6:9])
        else:
            raise ValueError("未知权重类型 %d" % wt)
        w.f32(model.v_edge[i])

    # 面
    idx = np.ascontiguousarray(model.indices, dtype={1: np.uint8, 2: np.uint16, 4: np.int32}[vsz])
    w.i32(idx.size)
    w.buf += idx.tobytes()

    # 贴图
    w.i32(len(model.textures))
    for t in model.textures:
        w.text(t)

    # 材质
    w.i32(len(model.materials))
    for mt in model.materials:
        w.text(mt.name)
        w.text(mt.name_en)
        w.f4(mt.diffuse)
        w.f3(mt.specular)
        w.f32(mt.specular_coef)
        w.f3(mt.ambient)
        w.u8(mt.draw_flags)
        w.f4(mt.edge_color)
        w.f32(mt.edge_size)
        w.sindex(mt.texture, tsz)
        w.sindex(mt.sphere, tsz)
        w.u8(mt.sphere_mode)
        w.u8(mt.toon_shared)
        if mt.toon_shared == 0:
            w.sindex(mt.toon, tsz)
        else:
            w.u8(mt.toon)
        w.text(mt.memo)
        w.i32(mt.face_count)

    # 骨骼
    w.i32(len(model.bones))
    for b in model.bones:
        w.text(b.name)
        w.text(b.name_en)
        w.f3(b.pos)
        w.sindex(b.parent, bsz)
        w.i32(b.layer)
        w.u16(b.flags)
        if b.flags & BF_TAIL_INDEX:
            w.sindex(b.tail_bone, bsz)
        else:
            w.f3(b.tail_offset)
        if b.flags & (BF_INHERIT_ROT | BF_INHERIT_MOV):
            w.sindex(b.append_parent, bsz)
            w.f32(b.append_ratio)
        if b.flags & BF_FIXED_AXIS:
            w.f3(b.axis)
        if b.flags & BF_LOCAL_AXIS:
            w.f3(b.local_x)
            w.f3(b.local_z)
        if b.flags & BF_EXTERNAL_PARENT:
            w.i32(b.ext_key)
        if b.flags & BF_IK:
            ik = b.ik or IK()
            w.sindex(ik.target, bsz)
            w.i32(ik.loop)
            w.f32(ik.angle)
            w.i32(len(ik.links))
            for link in ik.links:
                w.sindex(link.bone, bsz)
                w.u8(1 if link.limited else 0)
                if link.limited:
                    w.f3(link.lo)
                    w.f3(link.hi)

    # 形态
    w.i32(len(model.morphs))
    for mo in model.morphs:
        w.text(mo.name)
        w.text(mo.name_en)
        w.u8(mo.panel)
        w.u8(mo.type)
        w.i32(len(mo.offsets))
        t = mo.type
        for off in mo.offsets:
            if t in (0, 9):
                w.sindex(off.get("morph", -1), mosz)
                w.f32(off.get("ratio", 0.0))
            elif t == 1:
                w.uindex(off.get("vertex", 0), vsz)
                w.f3(off.get("offset", [0, 0, 0]))
            elif t == 2:
                w.sindex(off.get("bone", -1), bsz)
                w.f3(off.get("move", [0, 0, 0]))
                w.f4(off.get("rot", [0, 0, 0, 1]))
            elif 3 <= t <= 7:
                w.uindex(off.get("vertex", 0), vsz)
                w.f4(off.get("offset", [0, 0, 0, 0]))
            elif t == 8:
                w.sindex(off.get("material", -1), msz)
                w.u8(off.get("calc", 0))
                w.f4(off.get("diffuse", [1, 1, 1, 1]))
                w.f3(off.get("specular", [0, 0, 0]))
                w.f32(off.get("specular_coef", 0.0))
                w.f3(off.get("ambient", [0, 0, 0]))
                w.f4(off.get("edge_color", [0, 0, 0, 1]))
                w.f32(off.get("edge_size", 0.0))
                w.f4(off.get("texture", [1, 1, 1, 1]))
                w.f4(off.get("sphere", [1, 1, 1, 1]))
                w.f4(off.get("toon", [1, 1, 1, 1]))
            elif t == 10:
                w.sindex(off.get("rigid", -1), rsz)
                w.u8(off.get("local", 0))
                w.f3(off.get("velocity", [0, 0, 0]))
                w.f3(off.get("torque", [0, 0, 0]))

    # 显示枠
    w.i32(len(model.frames))
    for f in model.frames:
        w.text(f.name)
        w.text(f.name_en)
        w.u8(f.special)
        w.i32(len(f.items))
        for ty, index in f.items:
            w.u8(ty)
            if ty == 0:
                w.sindex(index, bsz)
            else:
                w.sindex(index, mosz)

    # 刚体
    w.i32(len(model.rigid))
    for rb in model.rigid:
        w.text(rb.name)
        w.text(rb.name_en)
        w.sindex(rb.bone, bsz)
        w.u8(rb.group)
        w.u16(rb.mask)
        w.u8(rb.shape)
        w.f3(rb.size)
        w.f3(rb.pos)
        w.f3(rb.rot)
        w.f32(rb.mass)
        w.f32(rb.mov_damp)
        w.f32(rb.rot_damp)
        w.f32(rb.repel)
        w.f32(rb.friction)
        w.u8(rb.mode)

    # 关节
    w.i32(len(model.joints))
    for j in model.joints:
        w.text(j.name)
        w.text(j.name_en)
        w.u8(j.type)
        w.sindex(j.rigid_a, rsz)
        w.sindex(j.rigid_b, rsz)
        w.f3(j.pos)
        w.f3(j.rot)
        w.f3(j.min_loc)
        w.f3(j.max_loc)
        w.f3(j.min_rot)
        w.f3(j.max_rot)
        w.f3(j.spring_loc)
        w.f3(j.spring_rot)

    # 柔体
    if version >= 2.1:
        w.i32(len(model.soft_bodies))
        for s in model.soft_bodies:
            w.text(s.name)
            w.text(s.name_en)
            w.u8(s.shape)
            w.sindex(s.material, msz)
            w.u8(s.group)
            w.u16(s.mask)
            w.u8(s.flags)
            w.i32(s.b_link_dist)
            w.i32(s.cluster_count)
            w.f32(s.total_mass)
            w.f32(s.collision_margin)
            w.i32(s.aero_model)
            for v in s.config:
                w.f32(v)
            for v in s.cluster:
                w.f32(v)
            for v in s.iteration:
                w.i32(v)
            for v in s.material_params:
                w.f32(v)
            w.i32(len(s.anchors))
            for rid, vid, near in s.anchors:
                w.sindex(rid, rsz)
                w.uindex(vid, vsz)
                w.u8(near)
            w.i32(len(s.pins))
            for vid in s.pins:
                w.uindex(vid, vsz)

    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(w.buf)
    os.replace(tmp, path)

    model.path = path
    model.version = version
    model.vsz, model.tsz, model.msz, model.bsz, model.mosz, model.rsz = vsz, tsz, msz, bsz, mosz, rsz

# ---------------------------------------------------------------- 校验与统计

def shift_bone_vertices(model: PMXModel, index: int, delta) -> int:
    """把骨骼位移按蒙皮权重写进顶点（PMXEditor「移动骨骼同时带动顶点」习惯）。"""
    if model is None or index < 0 or index >= len(model.bones):
        return 0
    bones = np.asarray(model.v_bones)
    if bones.size == 0:
        return 0
    mask = bones == int(index)
    if not mask.any():
        return 0
    w = np.where(mask, np.asarray(model.v_weights, dtype=np.float32), 0.0).sum(axis=1)
    hit = w > 0.0
    if not hit.any():
        return 0
    d = np.asarray(delta, dtype=np.float32)[None, :]
    model.v_pos[hit] += w[hit, None] * d
    return int(hit.sum())


def model_stats(m: PMXModel) -> dict:
    tris = m.n_faces
    return {
        "vertices": m.n_vertices,
        "faces": tris,
        "materials": len(m.materials),
        "bones": len(m.bones),
        "morphs": len(m.morphs),
        "textures": len(m.textures),
        "rigid": len(m.rigid),
        "joints": len(m.joints),
        "soft": len(m.soft_bodies),
    }

def validate_model(m: PMXModel) -> List[str]:
    """返回便于定位的模型问题列表（中文）。"""
    issues = []
    nb = len(m.bones)
    for i, b in enumerate(m.bones):
        if b.parent >= nb:
            issues.append("骨骼 %d「%s」的父骨骼索引越界 (%d)" % (i, b.name, b.parent))
        if b.flags & BF_TAIL_INDEX and b.tail_bone >= nb:
            issues.append("骨骼 %d「%s」的尾端骨骼索引越界 (%d)" % (i, b.name, b.tail_bone))
        if b.ik:
            for link in b.ik.links:
                if link.bone >= nb:
                    issues.append("骨骼 %d「%s」的 IK 链接索引越界 (%d)" % (i, b.name, link.bone))
    total = sum(mt.face_count for mt in m.materials)
    if total != len(m.indices):
        issues.append("材质面数合计 %d 与索引数 %d 不一致" % (total, len(m.indices)))
    for i, rb in enumerate(m.rigid):
        if rb.bone >= nb:
            issues.append("刚体 %d「%s」关联骨骼越界 (%d)" % (i, rb.name, rb.bone))
    for i, j in enumerate(m.joints):
        if j.rigid_a >= len(m.rigid) or j.rigid_b >= len(m.rigid):
            issues.append("关节 %d「%s」关联刚体越界 (%d, %d)" % (i, j.name, j.rigid_a, j.rigid_b))
    return issues
