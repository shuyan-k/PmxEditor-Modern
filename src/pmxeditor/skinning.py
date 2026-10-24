# -*- coding: utf-8 -*-
"""姿态求解、IK 与顶点蒙皮。

姿态使用「局部旋转四元数 + 局部位移」表示，骨骼世界矩阵按
W(b) = W(parent) · T(静止偏移 + 位移) · R(旋转) 计算。
物理驱动或 IK 的结果只写入姿态缓存，不修改 PMX 原始数据。
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Set

import numpy as np

from .native_backend import core as native_core
from .pmx import BF_INHERIT_MOV, BF_INHERIT_ROT, BF_LOCAL_APPEND

IDENTITY_Q = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)

# ---------------------------------------------------------------- 四元数/矩阵

def quat_to_mat(q) -> np.ndarray:
    x, y, z, w = [float(v) for v in q]
    n = x * x + y * y + z * z + w * w
    if n < 1e-12:
        return np.eye(3, dtype=np.float32)
    s = 2.0 / n
    xx, yy, zz = x * x * s, y * y * s, z * z * s
    xy, xz, yz = x * y * s, x * z * s, y * z * s
    wx, wy, wz = w * x * s, w * y * s, w * z * s
    return np.array([
        [1 - (yy + zz), xy - wz, xz + wy],
        [xy + wz, 1 - (xx + zz), yz - wx],
        [xz - wy, yz + wx, 1 - (xx + yy)],
    ], dtype=np.float32)

def mat_to_quat(R) -> np.ndarray:
    m = np.asarray(R, dtype=np.float64)
    tr = m[0, 0] + m[1, 1] + m[2, 2]
    if tr > 0:
        s = math.sqrt(tr + 1.0) * 2
        w = 0.25 * s
        x = (m[2, 1] - m[1, 2]) / s
        y = (m[0, 2] - m[2, 0]) / s
        z = (m[1, 0] - m[0, 1]) / s
    elif m[0, 0] > m[1, 1] and m[0, 0] > m[2, 2]:
        s = math.sqrt(1.0 + m[0, 0] - m[1, 1] - m[2, 2]) * 2
        w = (m[2, 1] - m[1, 2]) / s
        x = 0.25 * s
        y = (m[0, 1] + m[1, 0]) / s
        z = (m[0, 2] + m[2, 0]) / s
    elif m[1, 1] > m[2, 2]:
        s = math.sqrt(1.0 + m[1, 1] - m[0, 0] - m[2, 2]) * 2
        w = (m[0, 2] - m[2, 0]) / s
        x = (m[0, 1] + m[1, 0]) / s
        y = 0.25 * s
        z = (m[1, 2] + m[2, 1]) / s
    else:
        s = math.sqrt(1.0 + m[2, 2] - m[0, 0] - m[1, 1]) * 2
        w = (m[1, 0] - m[0, 1]) / s
        x = (m[0, 2] + m[2, 0]) / s
        y = (m[1, 2] + m[2, 1]) / s
        z = 0.25 * s
    q = np.array([x, y, z, w], dtype=np.float32)
    return normalize_quat(q)

def normalize_quat(q) -> np.ndarray:
    q = np.asarray(q, dtype=np.float32)
    n = float(np.linalg.norm(q))
    return q / n if n > 1e-8 else IDENTITY_Q.copy()

def slerp_quat(a, b, t: float) -> np.ndarray:
    """四元数插值；t 允许超出 [0,1]（付与率为负时表示反向旋转）。"""
    a = normalize_quat(a)
    b = normalize_quat(b)
    d = float(np.dot(a, b))
    if d < 0.0:
        b = -b
        d = -d
    d = min(1.0, max(-1.0, d))
    if d > 0.9995:
        return normalize_quat(a * (1.0 - t) + b * t)
    th = math.acos(d)
    s = math.sin(th)
    return normalize_quat(a * (math.sin((1.0 - t) * th) / s)
                         + b * (math.sin(t * th) / s))

def quat_mul(a, b) -> np.ndarray:
    ax, ay, az, aw = [float(v) for v in a]
    bx, by, bz, bw = [float(v) for v in b]
    return np.array([
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz,
    ], dtype=np.float32)

def axis_angle_quat(axis, angle) -> np.ndarray:
    a = np.asarray(axis, dtype=np.float64)
    n = np.linalg.norm(a)
    if n < 1e-8:
        return IDENTITY_Q.copy()
    a = a / n
    h = angle * 0.5
    s = math.sin(h)
    return np.array([a[0] * s, a[1] * s, a[2] * s, math.cos(h)], dtype=np.float32)

def euler_to_quat(rx, ry, rz) -> np.ndarray:
    qx = axis_angle_quat((1, 0, 0), rx)
    qy = axis_angle_quat((0, 1, 0), ry)
    qz = axis_angle_quat((0, 0, 1), rz)
    return normalize_quat(quat_mul(qz, quat_mul(qy, qx)))

def quat_to_euler(q):
    x, y, z, w = [float(v) for v in normalize_quat(q)]
    # R = Rz·Ry·Rx
    sinr = 2 * (w * x + y * z)
    cosr = 1 - 2 * (x * x + y * y)
    rx = math.atan2(sinr, cosr)
    sinp = 2 * (w * y - z * x)
    ry = math.asin(max(-1.0, min(1.0, sinp)))
    siny = 2 * (w * z + x * y)
    cosy = 1 - 2 * (y * y + z * z)
    rz = math.atan2(siny, cosy)
    return rx, ry, rz


def euler_alt(rx, ry, rz):
    """Rz.Ry.Rx 分解的另一个等价解：绕 Y 反号、X/Z 各差 PI。"""
    def wrap(a):
        a = (a + math.pi) % (2.0 * math.pi) - math.pi
        return a
    return wrap(rx + math.pi), wrap(math.pi - ry), wrap(rz + math.pi)


def euler_distance(a, b) -> float:
    """两组欧拉角的环面距离（逐轴取最短差值后平方和）。"""
    total = 0.0
    for u, v in zip(a, b):
        d = (float(u) - float(v) + math.pi) % (2.0 * math.pi) - math.pi
        total += d * d
    return total


def quat_to_euler_stable(q, prev=None):
    """转欧拉角，并在 prev 存在时选择与上一帧同分支的解。

    Rz.Ry.Rx 在俯仰接近 +-90 度时有两组等价解，按默认公式会在奇点附近
    突然切分支，表现为 X/Z 轴瞬间跳 180 度（就是「轴歧义」）。IK 每轮都
    重新分解绝对旋转，因此必须按上一轮的角度选解，才能保持连续。
    """
    rx, ry, rz = quat_to_euler(q)
    if prev is None:
        return rx, ry, rz
    alt = euler_alt(rx, ry, rz)
    if euler_distance(alt, prev) < euler_distance((rx, ry, rz), prev):
        return alt
    return rx, ry, rz

def translation(x, y, z) -> np.ndarray:
    m = np.eye(4, dtype=np.float32)
    m[0, 3], m[1, 3], m[2, 3] = x, y, z
    return m

def transform_to_mat4(pos, quat) -> np.ndarray:
    m = np.eye(4, dtype=np.float32)
    m[:3, :3] = quat_to_mat(quat)
    m[:3, 3] = pos
    return m

def mat4_inverse(m) -> np.ndarray:
    R = m[:3, :3]
    t = m[:3, 3]
    out = np.eye(4, dtype=np.float32)
    out[:3, :3] = R.T
    out[:3, 3] = -R.T @ t
    return out

# ---------------------------------------------------------------- 姿态

SDEF_AS_BDEF2 = False  # 规避开关：为 True 时把 SDEF(3) 当 BDEF2(1) 处理


def _sdef_fallback_table(wtype) -> np.ndarray:
    """生效的权重类型表：SDEF_AS_BDEF2 打开时把 SDEF(3) 降级成 BDEF2(1)。"""
    base = np.asarray(wtype, dtype=np.uint8).ravel()
    if not SDEF_AS_BDEF2:
        return base
    return np.where(base == 3, 1, base)


class Pose:
    def __init__(self, model):
        self.model = model
        n = len(model.bones)
        self.n = n
        self.parent = np.full(n, -1, dtype=np.int32)
        rest_off = np.zeros((n, 3), dtype=np.float32)
        pos = np.array([b.pos for b in model.bones], dtype=np.float32) if n else np.zeros((0, 3))
        children: List[List[int]] = [[] for _ in range(n)]
        for i, b in enumerate(model.bones):
            p = b.parent
            if 0 <= p < n and p != i:
                self.parent[i] = p
                rest_off[i] = pos[i] - pos[p]
            else:
                rest_off[i] = pos[i]
            if 0 <= p < n and p != i:
                children[p].append(i)
        self.rest_off = rest_off
        self.children = children
        self.order = self._topo_order()
        self.subtrees = self._subtrees()
        self.eval_order = self._eval_order()
        self.append_users = [[] for _ in range(n)]
        for i, bone in enumerate(model.bones):
            if (bone.flags & (BF_INHERIT_ROT | BF_INHERIT_MOV)
                    and 0 <= bone.append_parent < n and bone.append_parent != i):
                self.append_users[bone.append_parent].append(i)
        self._native_flags = np.ascontiguousarray(
            [bone.flags for bone in model.bones], dtype=np.uint32)
        self._native_append_parents = np.ascontiguousarray(
            [bone.append_parent for bone in model.bones], dtype=np.int32)
        self._native_append_ratios = np.ascontiguousarray(
            [bone.append_ratio for bone in model.bones], dtype=np.float32)
        self._native_rest_positions = np.ascontiguousarray(pos, dtype=np.float32)
        self._native_order = np.ascontiguousarray(self.eval_order, dtype=np.int32)
        self._native_ik_targets = np.full(n, -1, dtype=np.int32)
        self._native_ik_loops = np.zeros(n, dtype=np.int32)
        self._native_ik_angles = np.zeros(n, dtype=np.float32)
        self._native_link_offsets = np.zeros(n + 1, dtype=np.int32)
        native_link_bones = []
        native_link_limited = []
        native_link_limits = []
        for i, bone in enumerate(model.bones):
            if bone.ik:
                self._native_ik_targets[i] = bone.ik.target
                self._native_ik_loops[i] = bone.ik.loop
                self._native_ik_angles[i] = bone.ik.angle
                for link in bone.ik.links:
                    if not 0 <= link.bone < n:
                        continue
                    native_link_bones.append(link.bone)
                    native_link_limited.append(bool(link.limited))
                    native_link_limits.append(
                        np.stack((link.lo, link.hi), axis=0)
                        if link.limited else np.zeros((2, 3), dtype=np.float32))
            self._native_link_offsets[i + 1] = len(native_link_bones)
        self._native_link_bones = np.ascontiguousarray(
            native_link_bones, dtype=np.int32)
        self._native_link_limited = np.ascontiguousarray(
            native_link_limited, dtype=np.uint8)
        self._native_link_limits = np.ascontiguousarray(
            native_link_limits, dtype=np.float32).reshape(-1, 2, 3)
        self._native_bone_morph_starts = np.zeros(
            len(model.morphs) + 1, dtype=np.int32)
        native_morph_bones = []
        native_morph_rotations = []
        native_morph_translations = []
        for morph_index, morph in enumerate(model.morphs):
            if morph.type == 2:
                for offset in morph.offsets:
                    bone = int(offset.get("bone", -1))
                    if not 0 <= bone < n:
                        continue
                    native_morph_bones.append(bone)
                    native_morph_rotations.append(
                        offset.get("rot", [0, 0, 0])[:3])
                    native_morph_translations.append(
                        offset.get("move", [0, 0, 0])[:3])
            self._native_bone_morph_starts[morph_index + 1] = len(
                native_morph_bones)
        self._native_bone_morph_bones = np.ascontiguousarray(
            native_morph_bones, dtype=np.int32)
        self._native_bone_morph_rotations = np.ascontiguousarray(
            native_morph_rotations, dtype=np.float32).reshape(-1, 3)
        self._native_bone_morph_translations = np.ascontiguousarray(
            native_morph_translations, dtype=np.float32).reshape(-1, 3)
        self.base_rot = np.tile(IDENTITY_Q, (n, 1))
        self.base_trans = np.zeros((n, 3), dtype=np.float32)
        self.rot = self.base_rot.copy()
        self.trans = self.base_trans.copy()
        self.ov_rot: Dict[int, np.ndarray] = {}
        self.ov_trans: Dict[int, np.ndarray] = {}
        # IK 限位用：每根受限骨骼上一轮的欧拉角（保持分支连续）与钳制次数统计
        self._ik_euler: Dict[int, tuple] = {}
        self.ik_clamp_hits = 0
        # 求解失败时是否允许把链上骨骼旋转清零后重试（见 solve_ik 注释）。
        self.ik_reset_links = True
        # 末帧残差超过该值（模型单位）的链视为 CCD 收敛到坏解，需要重解。
        self.ik_retry_tolerance = 0.05
        self.world_cache: Optional[np.ndarray] = None
        self._world_dirty: Set[int] = set()
        self.last_morph_key = None

    def _topo_order(self):
        order = []
        seen = set()
        for root in range(self.n):
            if self.parent[root] >= 0:
                continue
            stack = [root]
            while stack:
                i = stack.pop()
                if i in seen:
                    continue
                seen.add(i)
                order.append(i)
                for c in reversed(self.children[i]):
                    stack.append(c)
        for i in range(self.n):
            if i not in seen:
                order.append(i)
        return order

    def _subtrees(self):
        subs = []
        for i in range(self.n):
            stack = [i]
            acc = []
            while stack:
                j = stack.pop()
                acc.append(j)
                stack.extend(self.children[j])
            subs.append(acc)
        return subs

    def _eval_order(self):
        """世界矩阵求值顺序：父骨骼、付与来源都必须先于当前骨骼。"""
        from collections import deque
        n = self.n
        deps = [set() for _ in range(n)]
        for i in range(n):
            if self.parent[i] >= 0:
                deps[i].add(int(self.parent[i]))
            b = self.model.bones[i]
            if (b.flags & (BF_INHERIT_ROT | BF_INHERIT_MOV)) \
                    and 0 <= b.append_parent < n and b.append_parent != i:
                deps[i].add(int(b.append_parent))
        users = [[] for _ in range(n)]
        indeg = [0] * n
        for i in range(n):
            indeg[i] = len(deps[i])
            for d in deps[i]:
                users[d].append(i)
        queue = deque(i for i in range(n) if indeg[i] == 0)
        order = []
        while queue:
            i = queue.popleft()
            order.append(i)
            for u in users[i]:
                indeg[u] -= 1
                if indeg[u] == 0:
                    queue.append(u)
        if len(order) < n:
            # 付与关系成环等异常数据：剩余骨骼按索引补齐，避免丢骨骼。
            seen = set(order)
            order.extend(i for i in range(n) if i not in seen)
        return order

    def reset(self):
        self.base_rot[:] = IDENTITY_Q
        self.base_trans[:] = 0
        self.ov_rot.clear()
        self.ov_trans.clear()
        self._ik_euler.clear()
        self.ik_clamp_hits = 0
        self._invalidate_world()
        self.apply()

    def apply(self, morph_weights=None, morphs=None):
        if (native_core is not None and morph_weights and
                morphs is self.model.morphs):
            active = [(int(index), float(weight))
                      for index, weight in morph_weights.items()
                      if weight and 0 <= index < len(morphs)]
            if active:
                indices = np.ascontiguousarray(
                    [item[0] for item in active], dtype=np.int32)
                weights = np.ascontiguousarray(
                    [item[1] for item in active], dtype=np.float32)
                rot, trans = native_core.apply_bone_morphs(
                    self.base_rot, self.base_trans, indices, weights,
                    self._native_bone_morph_starts,
                    self._native_bone_morph_bones,
                    self._native_bone_morph_rotations,
                    self._native_bone_morph_translations)
            else:
                rot = self.base_rot.copy()
                trans = self.base_trans.copy()
        else:
            rot = self.base_rot.copy()
            trans = self.base_trans.copy()
        if morph_weights and morphs and native_core is None:
            for mi, w in morph_weights.items():
                if not w or not (0 <= mi < len(morphs)):
                    continue
                mo = morphs[mi]
                if mo.type != 2:
                    continue
                for off in mo.offsets:
                    bi = int(off.get("bone", -1))
                    if not (0 <= bi < self.n):
                        continue
                    dq = euler_to_quat(*[float(v) for v in off.get("rot", [0, 0, 0])[:3]])
                    rot[bi] = normalize_quat(quat_mul(rot[bi], dq))
                    mv = off.get("move", [0, 0, 0])
                    trans[bi] += np.array([mv[0], mv[1], mv[2]], dtype=np.float32) * float(w)
        if morph_weights and morphs and native_core is not None and \
                morphs is not self.model.morphs:
            for mi, w in morph_weights.items():
                if not w or not (0 <= mi < len(morphs)):
                    continue
                mo = morphs[mi]
                if mo.type != 2:
                    continue
                for off in mo.offsets:
                    bi = int(off.get("bone", -1))
                    if not (0 <= bi < self.n):
                        continue
                    dq = euler_to_quat(*[
                        float(v) for v in off.get("rot", [0, 0, 0])[:3]])
                    rot[bi] = normalize_quat(quat_mul(rot[bi], dq))
                    mv = off.get("move", [0, 0, 0])
                    trans[bi] += np.array(
                        [mv[0], mv[1], mv[2]], dtype=np.float32) * float(w)
        for bi, q in self.ov_rot.items():
            if 0 <= bi < self.n:
                rot[bi] = q
        for bi, t in self.ov_trans.items():
            if 0 <= bi < self.n:
                trans[bi] = t
        changed = np.flatnonzero(
            np.any(rot != self.rot, axis=1)
            | np.any(trans != self.trans, axis=1)
        )
        self.rot = rot
        self.trans = trans
        self._invalidate_world(changed)

    def world(self) -> np.ndarray:
        if self.world_cache is not None and self._world_dirty:
            self.world_cache = self._world_rows(self._world_dirty, self.world_cache)
            self._world_dirty.clear()
        if self.world_cache is not None:
            return self.world_cache
        W = self._world_rows(None)
        self.world_cache = W
        self._world_dirty.clear()
        return W

    def _invalidate_world(self, changed=None):
        if self.world_cache is None:
            self._world_dirty.clear()
        elif changed is None:
            self.world_cache = None
            self._world_dirty.clear()
        elif len(changed):
            self._world_dirty.update(self.changed_subtrees(changed))

    def _world_rows(self, need, base=None):
        """计算世界矩阵；need 为 None 时计算全部，否则只算指定骨骼及其祖先。

        PMX 的「付与回転/付与移動」必须在此实现：足首D、腕捩等 D 骨骼
        本身没有蒙皮顶点之外的动画，网格只靠付与继承主骨骼的旋转。
        不实现付与会造成抬腿时脚部网格一半跟随、一半留在原地而被拉长。"""
        if native_core is not None:
            world = (base.copy() if base is not None else
                     np.zeros((self.n, 4, 4), dtype=np.float32))
            required = np.zeros(self.n, dtype=np.uint8)
            if need is None:
                required.fill(1)
            elif need:
                required[np.fromiter(need, dtype=np.int32)] = 1
            native_core.world_rows(
                self._native_flags, self._native_append_parents,
                self._native_append_ratios, self.parent, self.rest_off,
                self._native_rest_positions, self.rot, self.trans,
                self._native_order, required, world)
            return world
        n = self.n
        W = (base.copy() if base is not None else
             np.zeros((n, 4, 4), dtype=np.float32))
        eye4 = np.eye(4, dtype=np.float32)
        bones = self.model.bones
        for i in self.eval_order:
            if need is not None and i not in need:
                continue
            b = bones[i]
            p = self.parent[i]
            Wp = W[p] if p >= 0 else eye4
            q = self.rot[i]
            t_local = self.rest_off[i] + self.trans[i]
            if (b.flags & (BF_INHERIT_ROT | BF_INHERIT_MOV)) \
                    and 0 <= b.append_parent < n and b.append_parent != i:
                ratio = float(b.append_ratio)
                if ratio != 0.0:
                    src = b.append_parent
                    if b.flags & BF_INHERIT_ROT:
                        if b.flags & BF_LOCAL_APPEND:
                            q_src = self.rot[src]
                        else:
                            # 付与源的世界旋转转换到当前骨骼的父空间
                            Rs = W[src][:3, :3]
                            q_src = mat_to_quat(Wp[:3, :3].T @ Rs)
                        # 付与率允许为负（右肩C 等骨骼用 -1 表示反向旋转）
                        q = normalize_quat(quat_mul(
                            slerp_quat(IDENTITY_Q, q_src, ratio), q))
                    if b.flags & BF_INHERIT_MOV:
                        if b.flags & BF_LOCAL_APPEND:
                            d = self.trans[src] * ratio
                        else:
                            d_world = W[src][:3, 3] - np.array(
                                bones[src].pos, dtype=np.float32)
                            d = (Wp[:3, :3].T @ d_world) * ratio
                        t_local = t_local + d
            R = np.eye(4, dtype=np.float32)
            R[:3, :3] = quat_to_mat(q)
            T = translation(*t_local)
            W[i] = Wp @ T @ R
        return W

    def world_subset(self, indices):
        need = set()
        stack = list(indices)
        bones = self.model.bones
        while stack:
            j = stack.pop()
            if j < 0 or j >= self.n or j in need:
                continue
            need.add(j)
            p = self.parent[j]
            if p >= 0:
                stack.append(int(p))
            b = bones[j]
            if (b.flags & (BF_INHERIT_ROT | BF_INHERIT_MOV)) \
                    and 0 <= b.append_parent < self.n:
                stack.append(int(b.append_parent))
        return self._world_rows(need)

    def changed_subtrees(self, changed) -> Set[int]:
        """展开层级后代及受付与来源变化影响的骨骼。"""
        dirty = set()
        stack = list(changed)
        while stack:
            bone = stack.pop()
            if bone < 0 or bone >= self.n or bone in dirty:
                continue
            for affected in self.subtrees[bone]:
                if affected in dirty:
                    continue
                dirty.add(affected)
                stack.extend(self.append_users[affected])
        return dirty

    def world_update(self) -> None:
        """把 base_rot / base_trans 的改动立即反映到 rot / trans。

        视口拖拽直接调用 rotate_world / translate_world，需要立刻生效，
        否则要等到下一次 apply() 才更新，表现为骨骼在松开鼠标后才跳变。"""
        changed = np.flatnonzero(
            np.any(self.rot != self.base_rot, axis=1)
            | np.any(self.trans != self.base_trans, axis=1)
        )
        self.rot = self.base_rot.copy()
        self.trans = self.base_trans.copy()
        self._invalidate_world(changed)

    def rotate_local(self, bone: int, dq) -> None:
        if 0 <= bone < self.n:
            self.base_rot[bone] = normalize_quat(quat_mul(self.base_rot[bone], dq))
            self._invalidate_world({bone})

    def rotate_world(self, bone: int, axis, angle: float) -> None:
        """绕世界轴旋转骨骼（用于视口拖拽）。"""
        if not (0 <= bone < self.n) or abs(angle) < 1e-9:
            return
        W = self.world()
        Rp = W[self.parent[bone]][:3, :3] if self.parent[bone] >= 0 else np.eye(3, dtype=np.float32)
        dq = axis_angle_quat(axis, angle)
        dR = quat_to_mat(dq)
        localR = Rp.T @ dR @ Rp
        self.base_rot[bone] = normalize_quat(quat_mul(mat_to_quat(localR), self.base_rot[bone]))
        self._invalidate_world({bone})

    def translate_world(self, bone: int, delta) -> None:
        if not (0 <= bone < self.n):
            return
        W = self.world()
        Rp = W[self.parent[bone]][:3, :3] if self.parent[bone] >= 0 else np.eye(3, dtype=np.float32)
        self.base_trans[bone] = self.base_trans[bone] + Rp.T @ np.asarray(delta, dtype=np.float32)
        self._invalidate_world({bone})

    def clear_overrides(self):
        changed = set(self.ov_rot) | set(self.ov_trans)
        self.ov_rot.clear()
        self.ov_trans.clear()
        self._invalidate_world(changed)

    # ------------------------------------------------------------ IK
    def _ik_chains(self, only: Optional[Set[int]] = None):
        """列出需要求解的 IK 链：(IK 骨索引, target, links)。"""
        out = []
        for i, b in enumerate(self.model.bones):
            if only is not None and i not in only:
                continue
            if not (b.flags & 0x0020) or not b.ik:
                continue
            if not (0 <= b.ik.target < self.n):
                continue
            links = [l for l in b.ik.links if 0 <= l.bone < self.n]
            if links:
                out.append((i, b.ik.target, links))
        return out

    def _retry_stuck_chains(self, max_loops: int, only: Optional[Set[int]]) -> int:
        """把没收敛的链从静止姿态重解一次。

        MMD 的 IK 以 FK 旋转作为迭代初值，但初值偏离目标很远时 CCD 会收敛到
        镜像解（实测米娅帧 136 双膝跨到身体另一侧）。这里只在**末端残差仍然
        很大**时才把该链骨骼旋转清零重试，正常链保持原样，避免整体姿态被抹平。
        """
        if native_core is None:
            return 0
        ident = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)
        retried = 0
        for i, target, links in self._ik_chains(only):
            goal = self.world_subset([i])[0][:3, 3].copy()
            eff = self.world_subset([target])[0][:3, 3].copy()
            if float(np.linalg.norm(goal - eff)) <= self.ik_retry_tolerance:
                continue
            if all(
                abs(float(self.rot[l.bone][0])) < 1e-6
                and abs(float(self.rot[l.bone][1])) < 1e-6
                and abs(float(self.rot[l.bone][2])) < 1e-6
                for l in links
            ):
                continue  # 本来就是单位元，重解也只会得到同一个解
            prev_rot = {l.bone: self.rot[l.bone].copy() for l in links}
            prev_base = {l.bone: self.base_rot[l.bone].copy() for l in links}
            dirty = set()
            for l in links:
                self.rot[l.bone] = ident
                self.base_rot[l.bone] = ident
                dirty.add(l.bone)
            self._invalidate_world(dirty)
            selected = np.zeros(self.n, dtype=np.uint8)
            selected[i] = 1
            changed = np.zeros(self.n, dtype=np.uint8)
            native_core.solve_ik(
                self._native_flags, self._native_append_parents,
                self._native_append_ratios, self.parent, self.rest_off,
                self._native_rest_positions, self._native_order,
                self._native_ik_targets, self._native_ik_loops,
                self._native_ik_angles, self._native_link_offsets,
                self._native_link_bones, self._native_link_limited,
                self._native_link_limits, selected, int(max_loops),
                self.rot, self.trans, self.base_rot, changed)
            hit = np.flatnonzero(changed)
            if hit.size:
                self._invalidate_world(hit)
            new_eff = self.world_subset([target])[0][:3, 3].copy()
            if (float(np.linalg.norm(goal - new_eff))
                    >= float(np.linalg.norm(goal - eff)) - 1e-3):
                # 从静止姿态重解并没有更接近目标 → 回滚，保留 MMD 的 FK 结果。
                for bone, value in prev_rot.items():
                    self.rot[bone] = value
                for bone, value in prev_base.items():
                    self.base_rot[bone] = value
                self._invalidate_world(set(prev_rot))
                continue
            retried += 1
        return retried

    def solve_ik(self, max_loops: int = 0, only: Optional[Set[int]] = None) -> int:
        """求解 IK 链；only=None 时遍历全部链，max_loops 限制单链迭代次数。"""
        if native_core is not None:
            selected = np.ones(self.n, dtype=np.uint8)
            if only is not None:
                selected.fill(0)
                valid = [i for i in only if 0 <= i < self.n]
                if valid:
                    selected[valid] = 1
            changed = np.zeros(self.n, dtype=np.uint8)
            solved = native_core.solve_ik(
                self._native_flags, self._native_append_parents,
                self._native_append_ratios, self.parent, self.rest_off,
                self._native_rest_positions, self._native_order,
                self._native_ik_targets, self._native_ik_loops,
                self._native_ik_angles, self._native_link_offsets,
                self._native_link_bones, self._native_link_limited,
                self._native_link_limits, selected, int(max_loops),
                self.rot, self.trans, self.base_rot, changed)
            dirty = np.flatnonzero(changed)
            if dirty.size:
                self._invalidate_world(dirty)
            if self.ik_reset_links:
                solved += self._retry_stuck_chains(max_loops, only)
            if solved:
                self.apply()
            return solved
        solved = 0
        for i, b in enumerate(self.model.bones):
            if only is not None and i not in only:
                continue
            if not (b.flags & 0x0020) or not b.ik:
                continue
            ik = b.ik
            if not (0 <= ik.target < self.n):
                continue
            links = [l for l in ik.links if 0 <= l.bone < self.n]
            if not links:
                continue
            chains = [ik.target, i] + [l.bone for l in links]
            goal = self.world_subset(chains)[i][:3, 3].copy()
            loops = max(1, min(ik.loop, 200))
            if max_loops > 0:
                loops = min(loops, max_loops)
            for _ in range(loops):
                W = self.world_subset(chains)
                eff = W[ik.target][:3, 3].copy()
                if np.linalg.norm(goal - eff) < 1e-3:
                    break
                moved = False
                for link in links:
                    if link.limited and all(
                            abs(float(link.hi[k]) - float(link.lo[k])) < 1e-6
                            for k in range(3)):
                        # 三轴全锁死：这个链接不允许转动，直接跳过。
                        continue
                    W = self.world_subset(chains)
                    pivot = W[link.bone][:3, 3].copy()
                    v1 = eff - pivot
                    v2 = goal - pivot
                    n1 = np.linalg.norm(v1)
                    n2 = np.linalg.norm(v2)
                    if n1 < 1e-6 or n2 < 1e-6:
                        continue
                    c = float(np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0))
                    ang = math.acos(c)
                    if ang < 1e-4:
                        continue
                    ang = min(ang, max(0.01, ik.angle))
                    axis = np.cross(v1, v2)
                    if np.linalg.norm(axis) < 1e-8:
                        continue
                    Rp = W[self.parent[link.bone]][:3, :3] if self.parent[link.bone] >= 0 else np.eye(3, dtype=np.float32)
                    dR = quat_to_mat(axis_angle_quat(axis, ang))
                    localR = Rp.T @ dR @ Rp
                    # 世界空间的增量旋转需左乘到现有局部旋转上，右乘会把旋转轴
                    # 解释成骨骼局部轴，导致 CCD 收敛方向错误甚至越转越远。
                    new_local = localR @ quat_to_mat(self.rot[link.bone])
                    if link.limited:
                        lo, hi = link.lo, link.hi
                        prev = self._ik_euler.get(link.bone)
                        rx, ry, rz = quat_to_euler_stable(mat_to_quat(new_local), prev)
                        cx = min(max(rx, float(lo[0])), float(hi[0]))
                        cy = min(max(ry, float(lo[1])), float(hi[1]))
                        cz = min(max(rz, float(lo[2])), float(hi[2]))
                        if (cx, cy, cz) != (rx, ry, rz):
                            self.ik_clamp_hits += 1
                            # 增量钳制：本轮的钳制结果与上一轮一致，说明这一轴
                            # 已经顶在限制上，继续累计只会来回抖动，直接放弃本轮。
                            if prev is not None and euler_distance((cx, cy, cz), prev) < 1e-12:
                                continue
                            self._ik_euler[link.bone] = (cx, cy, cz)
                            new_local = quat_to_mat(euler_to_quat(cx, cy, cz))
                        else:
                            self._ik_euler[link.bone] = (rx, ry, rz)
                    q = mat_to_quat(new_local)
                    self.base_rot[link.bone] = q
                    # rot 必须同步更新，否则下一次 world 计算仍用旧姿态，
                    # CCD 相当于每轮都在同一初始状态上重复同一旋转。
                    self.rot[link.bone] = q
                    self._invalidate_world({link.bone})
                    moved = True
                    # CCD 逐链修正后要立即刷新末端位置，否则下一条链会重复
                    # 施加同一份修正量，造成来回振荡、无法收敛。
                    eff = self.world_subset(chains)[ik.target][:3, 3].copy()
                    if np.linalg.norm(goal - eff) < 1e-3:
                        break
                if not moved:
                    break
            solved += 1
        if self.ik_reset_links:
            # 与原生路径保持一致：链上旋转会把 CCD 引向镜像解时，
            # 从静止姿势重解一次，残差没变小就回滚。
            solved += self._retry_stuck_chains(max_loops, only)
        if solved:
            self.apply()
        return solved

def active_ik_indices(pose: Pose, changed_bone: int) -> Set[int]:
    """返回受骨骼变化影响的 IK 链，并展开链间依赖闭包。"""
    if not 0 <= changed_bone < pose.n:
        return set()
    dirty = pose.changed_subtrees({changed_bone})
    ik_bones = [
        (i, bone) for i, bone in enumerate(pose.model.bones)
        if (bone.flags & 0x0020) and bone.ik
    ]
    active = set()
    while True:
        added = False
        for index, bone in ik_bones:
            if index in active:
                continue
            ik = bone.ik
            if not (
                index == changed_bone
                or index in dirty
                or ik.target in dirty
                or any(link.bone in dirty for link in ik.links)
            ):
                continue
            active.add(index)
            dirty.update(pose.changed_subtrees({index}))
            dirty.update(pose.changed_subtrees(
                link.bone for link in ik.links if 0 <= link.bone < pose.n))
            added = True
        if not added:
            return active

# ---------------------------------------------------------------- 蒙皮

def _f32(value) -> np.ndarray:
    """原生接口只接受 float32 连续数组；姿态矩阵可能是 float64 视图。"""
    return np.ascontiguousarray(value, dtype=np.float32)


def _sdef(model) -> np.ndarray:
    """SDEF 参数统一成 (n, 9) float32 连续数组；没有 SDEF 时返回空表。"""
    data = getattr(model, "v_sdef", None)
    if data is None:
        return np.zeros((0, 9), dtype=np.float32)
    return np.ascontiguousarray(data, dtype=np.float32).reshape(-1, 9)


class SkinDeformer:
    def __init__(self, model):
        n = model.n_vertices
        nb = len(model.bones)
        self.model = model
        self.n = n
        self._wtype_cache = None
        self._wtype_cache_flag = None
        self._wtype_cache_src = None
        self.rest_pos = (np.array([b.pos for b in model.bones], dtype=np.float32)
                         if nb else np.zeros((0, 3), dtype=np.float32))
        self.entries_bone = []
        self.entries_vi = []
        self.entries_w = []
        self._morph_pos_starts = np.zeros(
            len(model.morphs) + 1, dtype=np.int32)
        self._morph_uv_starts = np.zeros(
            len(model.morphs) + 1, dtype=np.int32)
        morph_pos_vertices = []
        morph_pos_offsets = []
        morph_uv_vertices = []
        morph_uv_offsets = []
        for morph_index, morph in enumerate(model.morphs):
            if morph.type == 1:
                for offset in morph.offsets:
                    morph_pos_vertices.append(int(offset.get("vertex", 0)))
                    morph_pos_offsets.append(
                        offset.get("offset", [0, 0, 0])[:3])
            elif morph.type == 3:
                for offset in morph.offsets:
                    morph_uv_vertices.append(int(offset.get("vertex", 0)))
                    morph_uv_offsets.append(
                        offset.get("offset", [0, 0, 0, 0])[:2])
            self._morph_pos_starts[morph_index + 1] = len(
                morph_pos_vertices)
            self._morph_uv_starts[morph_index + 1] = len(morph_uv_vertices)
        self._morph_pos_vertices = np.ascontiguousarray(
            morph_pos_vertices, dtype=np.int32)
        self._morph_pos_offsets = np.ascontiguousarray(
            morph_pos_offsets, dtype=np.float32).reshape(-1, 3)
        self._morph_uv_vertices = np.ascontiguousarray(
            morph_uv_vertices, dtype=np.int32)
        self._morph_uv_offsets = np.ascontiguousarray(
            morph_uv_offsets, dtype=np.float32).reshape(-1, 2)
        if n == 0:
            self.offsets = np.zeros((0, 2), dtype=np.int64)
            return
        bones = model.v_bones
        wtype = model.v_wtype
        weights = model.v_weights
        counts = np.where(wtype == 0, 1, np.where((wtype == 1) | (wtype == 3), 2, 4))
        counts = counts.astype(np.int64, copy=False)
        # 顶点数组理论上总有 4 列；数据异常时按实际列数收窄，避免越界索引。
        if bones.ndim == 2:
            counts = np.minimum(counts, bones.shape[1])
        total = int(counts.sum())
        # 一次展开成 (顶点索引, 权重槽) 两条数组，再向量化取骨骼与权重：
        # 旧实现按顶点做 8 万次 Python 循环（真机 321 骨骼 / 79848 顶点约 39 ms）。
        vi_idx = np.repeat(np.arange(n, dtype=np.int64), counts)
        starts_v = np.zeros(n + 1, dtype=np.int64)
        np.cumsum(counts, out=starts_v[1:])
        slot = np.arange(total, dtype=np.int64) - starts_v[vi_idx]
        eb = np.asarray(bones[vi_idx, slot], dtype=np.int32)
        bad = (eb < 0) | (eb >= nb)
        if bad.any():
            eb[bad] = 0
        ew = np.asarray(weights[vi_idx, slot], dtype=np.float32)
        ev = vi_idx.astype(np.int32)
        order = np.argsort(eb, kind="stable")
        self.entries_bone = eb[order]
        self.entries_vi = ev[order]
        self.entries_w = ew[order]
        # 每个骨骼的条目区间
        counts_b = np.bincount(self.entries_bone, minlength=nb)
        starts = np.zeros(nb, dtype=np.int64)
        if nb > 1:
            starts[1:] = np.cumsum(counts_b)[:-1]
        self.offsets = np.stack([starts, counts_b], axis=1)
        self.entries_vi = self.entries_vi.astype(np.int32)
        self.total = total

        # 同一顶点可能把同一根骨骼写进两个权重槽（BDEF2/BDEF4 都允许），
        # 这时按骨骼分批的 out[idx] += 会互相覆盖，必须单独向量化重算。
        dup = np.zeros(n, dtype=bool)
        for first in range(4):
            for second in range(first + 1, 4):
                dup |= (bones[:, first] == bones[:, second]) & (counts > second)
        self._slot_counts = counts
        self._dup_vertices = np.nonzero(dup)[0].astype(np.int32)

    def _trim_world(self, world):
        """把 world 裁到与静止位置表一致的行数。

        追加骨骼后 Pose 会多出一行，但没有任何顶点引用新骨骼，
        旧 Deformer 的 rest_pos 只有旧骨骼的行，多出来的行用不到。
        """
        w = np.asarray(world)
        rows = self.rest_pos.shape[0]
        if w.shape[0] > rows:
            return w[:rows]
        return w

    def wtype_table(self) -> np.ndarray:
        """生效的权重类型表：SDEF_AS_BDEF2 打开时把 SDEF(3) 降级成 BDEF2(1)。"""
        flag = SDEF_AS_BDEF2
        src = self.model.v_wtype
        if (self._wtype_cache is None or self._wtype_cache_flag is not flag
                or self._wtype_cache_src is not src):
            self._wtype_cache = _sdef_fallback_table(src)
            self._wtype_cache_flag = flag
            self._wtype_cache_src = src
        return self._wtype_cache

    def deform(self, base_pos, base_nrm, world) -> tuple:
        if self.n == 0:
            return base_pos, base_nrm
        world = self._trim_world(world)
        if native_core is not None:
            return native_core.deform(
                base_pos, base_nrm, self.model.v_bones, self.model.v_weights,
                self.wtype_table(), self.rest_pos, _f32(world), _sdef(self.model))
        out = np.zeros_like(base_pos)
        nout = np.zeros_like(base_nrm)
        ev = self.entries_vi
        ew = self.entries_w
        eb = self.entries_bone
        # 按骨骼批量处理，避免逐顶点 Python 循环
        for bi in range(len(self.offsets)):
            st, cnt = int(self.offsets[bi, 0]), int(self.offsets[bi, 1])
            if cnt <= 0:
                continue
            sl = slice(st, st + cnt)
            idx = ev[sl]
            w = ew[sl][:, None]
            M = world[bi]
            R = M[:3, :3]
            t = M[:3, 3]
            p = base_pos[idx] - self.rest_pos[bi]
            out[idx] += (p @ R.T + t) * w
            nout[idx] += (base_nrm[idx] @ R.T) * w
        if self._dup_vertices.size:
            dv = self._dup_vertices
            acc_p = np.zeros((dv.size, 3), dtype=base_pos.dtype)
            acc_n = np.zeros((dv.size, 3), dtype=base_nrm.dtype)
            for slot_index in range(4):
                active = self._slot_counts[dv] > slot_index
                if not active.any():
                    continue
                slot_bone = np.where(active, self.model.v_bones[dv, slot_index], 0)
                slot_w = np.where(active, self.model.v_weights[dv, slot_index], 0.0)
                M = world[slot_bone]
                R = M[:, :3, :3]
                T = M[:, :3, 3]
                rel = base_pos[dv] - self.rest_pos[slot_bone]
                acc_p += (np.einsum("mij,mj->mi", R, rel) + T) * slot_w[:, None]
                acc_n += np.einsum("mij,mj->mi", R, base_nrm[dv]) * slot_w[:, None]
            out[dv] = acc_p
            nout[dv] = acc_n
        out = self._special_blend(base_pos, world, out)
        n = np.linalg.norm(nout, axis=1, keepdims=True)
        n[n < 1e-6] = 1.0
        return out, nout / n

    def _special_blend(self, base_pos, world, out):
        """SDEF 球面插值 / QDEF 双四元数混合的回退实现。

        与 native/pmx_core.cpp 的 deform_vertices 保持同一语义：
        SDEF 只取第 0/1 槽骨骼与 C 点，并按 R0 椭球半轴求静止方向半径；
        QDEF 按双四元数混合
        （参考骨骼做符号对齐，避免四元数取反导致插值绕远路）。
        仅对 weight_type >= 3 的少量顶点生效，逐顶点循环可接受。
        """
        model = self.model
        wtype = _sdef_fallback_table(model.v_wtype)
        # BDEF2/BDEF4 也走双四元数混合（DQS），与 native/pmx_core.cpp 一致：
        # 线性混合在「关节大角度弯曲 + 轴向自转」时会拧成糖纸。
        todo = np.nonzero((wtype <= 2) | (wtype == 3) | (wtype == 4))[0]
        if todo.size == 0:
            return out
        sdef = np.asarray(model.v_sdef, dtype=np.float32).reshape(-1, 9)
        for vi in todo:
            vi = int(vi)
            if int(wtype[vi]) <= 2 and int(np.count_nonzero(
                    np.asarray(model.v_weights[vi]).ravel())) < 2:
                continue  # 单骨骼（BDEF1）没有混合，线性即刚性
            bones = np.asarray(model.v_bones[vi]).ravel()
            wts = np.asarray(model.v_weights[vi]).ravel()
            pos = np.asarray(base_pos[vi], dtype=np.float64)
            if int(wtype[vi]) == 3:
                b0 = int(bones[0])
                w1 = float(wts[1])
                w0 = 1.0 - w1
                b1 = int(bones[1]) if w1 > 0.0 else b0
                point_c = np.asarray(sdef[vi, 0:3], dtype=np.float64)
                m0 = np.asarray(world[b0], dtype=np.float64)
                m1 = np.asarray(world[b1], dtype=np.float64)
                c0 = m0[:3, :3] @ (point_c - self.rest_pos[b0]) + m0[:3, 3]
                c1 = m1[:3, :3] @ (point_c - self.rest_pos[b1]) + m1[:3, 3]
                p0 = m0[:3, :3] @ (pos - self.rest_pos[b0]) + m0[:3, 3]
                p1 = m1[:3, :3] @ (pos - self.rest_pos[b1]) + m1[:3, 3]
                center = c0 * w0 + c1 * w1
                direction = (p0 - c0) * w0 + (p1 - c1) * w1
                dlen = float(np.linalg.norm(direction))
                radius = float(np.linalg.norm(pos - point_c))
                # R0 是静止椭球半轴、R1 是形变后半轴：静止方向与当前方向
                # 都用同一组半轴比较（R1 优先，全零回退 R0），未变形时比值
                # 恒为 1，从而逐位还原静止姿态。
                # R0/R1 在 PMX 里存的是「点」而不是半径向量（模型库里实测
                # R0-C 与 R1-C 恒为 180° 反向、|R0| 是骨骼长度量级），
                # 半轴取逐轴 |R - C|；两者都为零时保持球面半径。
                r0 = np.abs(np.asarray(sdef[vi, 3:6], dtype=np.float64) - point_c)
                r1 = np.abs(np.asarray(sdef[vi, 6:9], dtype=np.float64) - point_c)
                rmax = float(r0.max()) if r0.size == 3 else 0.0
                r1max = float(r1.max()) if r1.size == 3 else 0.0
                # 是否给了 R1 要看原始值：R1 全零表示「没有 R1」，但 C 非零
                # 时 |0-C| 不为零，不能用平移后的半轴来判定。
                raw_r1 = np.asarray(sdef[vi, 6:9], dtype=np.float64)
                if float(np.abs(raw_r1).max()) > 1e-6:
                    axes0, amax = r1, r1max
                else:
                    axes0, amax = r0, rmax
                d_rest = pos - point_c
                if amax > 1e-6 and dlen > 1e-6:
                    rot = m0[:3, :3]
                    rest_local = d_rest
                    cur_local = rot.T @ direction
                    lr = float(np.linalg.norm(rest_local))
                    lc = float(np.linalg.norm(cur_local))
                    if lr > 1e-6 and lc > 1e-6:
                        # 与 C++ 一致：静止距离 x 椭球伸缩比
                        axes = np.where(axes0 < 1e-6, amax, axes0)
                        sum_rest = float(np.sum(((rest_local / lr) / axes) ** 2))
                        sum_cur = float(np.sum(((cur_local / lc) / axes) ** 2))
                        if sum_rest > 1e-12 and sum_cur > 1e-12:
                            radius = float(np.linalg.norm(d_rest)) * math.sqrt(
                                sum_rest / sum_cur)
                            # 与 C++ 一致：椭球修正量夹在 [0.6, 1.4] 倍静止半径内，
                            # 避免极端弯曲时把网格拉出尖刺。
                            rest_len = float(np.linalg.norm(d_rest))
                            radius = min(max(radius, rest_len * 0.6), rest_len * 1.4)
                if dlen > 1e-6 and radius > 1e-6:
                    out[vi] = center + direction * (radius / dlen)
                continue
            qsum = np.zeros(4, dtype=np.float64)
            dsum = np.zeros(4, dtype=np.float64)
            ref = None
            for k in range(4):
                wk = float(wts[k])
                if wk <= 0.0:
                    continue
                bi = int(bones[k])
                m = np.asarray(world[bi], dtype=np.float64)
                rot = m[:3, :3]
                trans = m[:3, 3] - rot @ self.rest_pos[bi]
                qr = np.asarray(mat_to_quat(rot), dtype=np.float64)
                dq = 0.5 * np.asarray(
                    quat_mul(np.array([trans[0], trans[1], trans[2], 0.0]), qr),
                    dtype=np.float64)
                if ref is None:
                    ref = qr
                elif float(np.dot(qr, ref)) < 0.0:
                    qr = -qr
                    dq = -dq
                qsum += wk * qr
                dsum += wk * dq
            qlen = float(np.linalg.norm(qsum))
            if qlen <= 1e-9:
                continue
            qsum /= qlen
            dsum /= qlen
            conj = np.array([-qsum[0], -qsum[1], -qsum[2], qsum[3]])
            trans = 2.0 * np.asarray(quat_mul(dsum, conj), dtype=np.float64)[:3]
            out[vi] = quat_to_mat(qsum) @ pos + trans
        return out

    def deform_subset(self, base_pos, base_nrm, world, dirty_bones,
                      prev_pos, prev_nrm) -> tuple:
        if prev_pos is None or prev_nrm is None:
            return self.deform(base_pos, base_nrm, world)
        if (prev_pos.shape != base_pos.shape or prev_nrm.shape != base_nrm.shape
                or len(dirty_bones) > len(self.offsets) * 0.3):
            return self.deform(base_pos, base_nrm, world)
        affected = []
        for bone in dirty_bones:
            if not 0 <= bone < len(self.offsets):
                continue
            start, count = self.offsets[bone]
            if count:
                affected.append(self.entries_vi[start:start + count])
        if not affected:
            return prev_pos, prev_nrm
        vertex_indices = np.unique(np.concatenate(affected))
        if vertex_indices.size > self.n * 0.3:
            return self.deform(base_pos, base_nrm, world)
        world = self._trim_world(world)
        wtype = self.wtype_table()
        if native_core is not None:
            return native_core.deform_subset(
                base_pos, base_nrm, self.model.v_bones, self.model.v_weights,
                wtype, self.rest_pos, world,
                np.ascontiguousarray(vertex_indices, dtype=np.int32),
                prev_pos, prev_nrm, _sdef(self.model))

        if (bool(np.any(wtype[vertex_indices] >= 3))
                or np.isin(vertex_indices, self._dup_vertices).any()):
            # SDEF / QDEF 顶点在回退路径里统一走整次 deform，避免重复实现
            return self.deform(base_pos, base_nrm, world)
        weights = self.model.v_weights[vertex_indices].copy()
        bones = self.model.v_bones[vertex_indices].astype(np.int64, copy=True)
        weight_counts = np.where(
            wtype[vertex_indices] == 0,
            1,
            np.where((wtype[vertex_indices] == 1) | (wtype[vertex_indices] == 3),
                     2, 4),
        )
        active_slots = np.arange(4)[None, :] < weight_counts[:, None]
        bones[(bones < 0) | (bones >= len(self.offsets))] = 0
        weights[~active_slots] = 0.0

        matrices = world[bones]
        rotations = matrices[:, :, :3, :3]
        translations = matrices[:, :, :3, 3]
        offsets = base_pos[vertex_indices, None, :] - self.rest_pos[bones]
        positions = np.einsum("mkij,mkj->mki", rotations, offsets)
        positions = ((positions + translations) * weights[:, :, None]).sum(axis=1)
        normals = np.einsum(
            "mkij,mj->mki", rotations, base_nrm[vertex_indices])
        normals = (normals * weights[:, :, None]).sum(axis=1)
        lengths = np.linalg.norm(normals, axis=1, keepdims=True)
        lengths[lengths < 1e-6] = 1.0

        out = prev_pos.copy()
        nout = prev_nrm.copy()
        out[vertex_indices] = positions
        nout[vertex_indices] = normals / lengths
        return out, nout

# ---------------------------------------------------------------- 形态应用

MORPH_FLIP = 9  # PMX 形态类型：9 是翻转；4~7 是附加 UV，不能混为一谈


def resolve_morph_weights(model, weights: dict, depth: int = 0,
                          seen=None) -> dict:
    """把组形态(0)与翻转形态(9)展开成"实际生效"的形态权重。

    组形态的 offsets 形如 {"morph": i, "ratio": r}，子形态权重 = w * r；
    翻转形态同样引用子形态，但语义是 1 - w，所以子权重 = (1 - w) * r。
    展开后顶点/UV/骨骼/材质四类形态都能按普通权重生效。
    """
    if not weights:
        return {}
    if seen is None:
        seen = set()
    out = {}
    for mi, w in weights.items():
        if not w or not (0 <= mi < len(model.morphs)):
            continue
        mo = model.morphs[mi]
        if mo.type in (0, MORPH_FLIP) and depth < 8 and mi not in seen:
            child = {}
            for o in mo.offsets:
                ti = int(o.get("morph", -1))
                ratio = float(o.get("ratio", 0.0))
                if not (0 <= ti < len(model.morphs)) or ratio == 0.0:
                    continue
                cw = float(w) * ratio if mo.type == 0 else (1.0 - float(w)) * ratio
                child[ti] = child.get(ti, 0.0) + cw
            sub = resolve_morph_weights(model, child, depth + 1, seen | {mi})
            for k, v in sub.items():
                out[k] = out.get(k, 0.0) + v
        elif mo.type not in (0, MORPH_FLIP):
            out[mi] = out.get(mi, 0.0) + float(w)
        # 组/翻转形态若因自引用或层数上限没能展开，就直接丢弃：
        # 它们本身不产生顶点/UV/骨骼/材质偏移，留在结果里只会让调用方
        # 误以为有形态在生效。
    return out


def apply_vertex_morphs(model, weights: dict, deformer=None):
    """返回应用顶点/UV 形态后的数组（无形态时直接复用原数组）。"""
    if not weights:
        return model.v_pos, model.v_uv
    if (native_core is not None and deformer is not None
            and deformer.model is model):
        active = [(int(index), float(weight))
                  for index, weight in weights.items()
                  if weight and 0 <= index < len(model.morphs)
                  and (deformer._morph_pos_starts[index + 1]
                       > deformer._morph_pos_starts[index]
                       or deformer._morph_uv_starts[index + 1]
                       > deformer._morph_uv_starts[index])]
        if active:
            return native_core.apply_vertex_morphs(
                model.v_pos, model.v_uv,
                np.ascontiguousarray([item[0] for item in active],
                                     dtype=np.int32),
                np.ascontiguousarray([item[1] for item in active],
                                     dtype=np.float32),
                deformer._morph_pos_starts,
                deformer._morph_pos_vertices, deformer._morph_pos_offsets,
                deformer._morph_uv_starts,
                deformer._morph_uv_vertices, deformer._morph_uv_offsets)
    pos = None
    uv = None
    for mi, w in weights.items():
        if not w or not (0 <= mi < len(model.morphs)):
            continue
        mo = model.morphs[mi]
        if mo.type == 1:
            if pos is None:
                pos = model.v_pos.copy()
            vi = np.array([int(o.get("vertex", 0)) for o in mo.offsets], dtype=np.int64)
            off = np.array([o.get("offset", [0, 0, 0]) for o in mo.offsets], dtype=np.float32)
            if vi.size:
                ok = (vi >= 0) & (vi < model.n_vertices)
                np.add.at(pos, vi[ok], off[ok] * float(w))
        elif mo.type == 3:
            if uv is None:
                uv = model.v_uv.copy()
            vi = np.array([int(o.get("vertex", 0)) for o in mo.offsets], dtype=np.int64)
            off = np.array([o.get("offset", [0, 0, 0, 0]) for o in mo.offsets], dtype=np.float32)
            if vi.size:
                ok = (vi >= 0) & (vi < model.n_vertices)
                np.add.at(uv, vi[ok], off[ok][:, :2] * float(w))
    return (pos if pos is not None else model.v_pos,
            uv if uv is not None else model.v_uv)

def material_morph_colors(model, weights: dict) -> dict:
    """返回材质形态造成的 (加法/乘法) 颜色调整。"""
    out = {}
    if not weights:
        return out
    for mi, w in weights.items():
        if not w or not (0 <= mi < len(model.morphs)):
            continue
        mo = model.morphs[mi]
        if mo.type != 8:
            continue
        for off in mo.offsets:
            mi2 = int(off.get("material", -1))
            if not (0 <= mi2 < len(model.materials)):
                continue
            calc = int(off.get("calc", 0))
            cur = out.setdefault(mi2, {"mul": np.ones(4), "add": np.zeros(4), "calc": calc})
            d = np.array(off.get("diffuse", [1, 1, 1, 1]), dtype=np.float32) - 1.0
            s = np.array(off.get("specular", [0, 0, 0]), dtype=np.float32)
            a = np.array(off.get("ambient", [0, 0, 0]), dtype=np.float32)
            if calc == 0:
                cur["mul"][:3] *= 1.0 + d[:3] * float(w)
                cur["mul"][3] *= 1.0 + d[3] * float(w)
                cur["add"][:3] += s * float(w) + a * float(w) * 0.5
            else:
                cur["mul"][:3] += d[:3] * float(w)
                cur["mul"][3] += d[3] * float(w)
                cur["add"][:3] += s * float(w)
    return out
