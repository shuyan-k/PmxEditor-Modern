# -*- coding: utf-8 -*-
"""Bullet 物理预览：按 PMX 刚体/关节参数构建世界，驱动骨骼姿态。

物理语义与 MMD 对齐：
- 「骨骼跟随」刚体为运动学体，由骨骼姿态直接驱动；
- 「物理演算」刚体由 Bullet 求解，结果回写给对应骨骼；
- 关节使用 btGeneric6DofSpringConstraint，保留三轴限位与弹簧；
- 限位 min > max 由 Bullet 视为自由轴，与 MMD 行为一致。
"""
from __future__ import annotations

import ctypes
import math
import os
from typing import List

import numpy as np

from . import paths
from .native_backend import core as native_core
from .pmx import BF_AFTER_PHYSICS
from .skinning import (Pose, euler_to_quat, mat4_inverse, mat_to_quat, quat_to_mat,
                      translation, transform_to_mat4)

DLL_NAME = "bullet_phys.dll"

def _find_dll() -> str:
    for cand in (os.path.join(str(paths.NATIVE), DLL_NAME),
                 os.path.join(str(paths.PKG), DLL_NAME)):
        if os.path.exists(cand):
            return cand
    raise FileNotFoundError("未找到 Bullet 物理库：%s" % DLL_NAME)

class _Bullet:
    _instance = None

    def __init__(self):
        lib = ctypes.CDLL(_find_dll())
        f = ctypes.c_float
        p = ctypes.POINTER(f)
        vp = ctypes.c_void_p
        self.lib = lib
        lib.bw_create.restype = vp
        lib.bw_create.argtypes = [f, f, f, ctypes.c_int]
        lib.bw_destroy.argtypes = [vp]
        lib.bw_set_gravity.argtypes = [vp, f, f, f]
        lib.bw_set_iterations.argtypes = [vp, ctypes.c_int]
        lib.bw_add_ground.argtypes = [vp, f]
        lib.bw_clear_forces.argtypes = [vp]
        lib.bw_add_body.restype = ctypes.c_int
        lib.bw_add_body.argtypes = [vp, ctypes.c_int] + [f] * 14 + [ctypes.c_int] * 3
        lib.bw_set_body.argtypes = [vp, ctypes.c_int, p, p]
        lib.bw_get_body.argtypes = [vp, ctypes.c_int, p, p]
        lib.bw_apply_impulse.argtypes = [vp, ctypes.c_int] + [f] * 6
        if hasattr(lib, "bw_set_body_mass"):
            lib.bw_set_body_mass.restype = ctypes.c_int
            lib.bw_set_body_mass.argtypes = [vp, ctypes.c_int, f]
            lib.bw_set_body_friction.argtypes = [vp, ctypes.c_int, f]
            lib.bw_set_body_restitution.argtypes = [vp, ctypes.c_int, f]
        lib.bw_add_joint.restype = ctypes.c_int
        lib.bw_add_joint.argtypes = [vp, ctypes.c_int, ctypes.c_int, ctypes.c_int] + [p] * 8
        lib.bw_step.argtypes = [vp, f, ctypes.c_int]
        lib.bw_body_count.argtypes = [vp]

    @classmethod
    def get(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

def _arr(vals) -> ctypes.Array:
    return (ctypes.c_float * len(vals))(*[float(v) for v in vals])

class MMDPhysics:
    def __init__(self):
        self.world = None
        self.model = None
        self.body_map: List[int] = []      # 刚体索引 -> Bullet 索引
        self.bone_of_body: List[int] = []
        self.offsets: List[np.ndarray] = []  # 骨骼静止系到刚体静止系
        self.rest: List[tuple] = []          # (pos, quat)
        self.modes: List[int] = []
        self._body_map_array = np.zeros(0, dtype=np.int32)
        self._bone_of_body_array = np.zeros(0, dtype=np.int32)
        self._modes_array = np.zeros(0, dtype=np.int32)
        self._offsets_array = np.zeros((0, 4, 4), dtype=np.float32)
        self._body_positions = np.zeros((0, 3), dtype=np.float32)
        self._body_rotations = np.zeros((0, 4), dtype=np.float32)
        self._inverse_offsets_array = np.zeros((0, 4, 4), dtype=np.float32)
        self._rigid_for_bone = np.zeros(0, dtype=np.int32)
        self._pose_order_array = np.zeros(0, dtype=np.int32)
        self._pose_parent_array = np.zeros(0, dtype=np.int32)
        self._pose_rest_offsets = np.zeros((0, 3), dtype=np.float32)
        self._override_rotations = np.zeros((0, 4), dtype=np.float32)
        self._override_translations = np.zeros((0, 3), dtype=np.float32)
        self._override_mask = np.zeros(0, dtype=np.uint8)
        self._pose_layout_id = None
        self.enabled = False
        self.gravity = -9.8
        self.iterations = 10
        self.ground = True
        self.error = ""
        self._ready = False

    # ------------------------------------------------------------ 构建
    def build(self, model) -> bool:
        self.release()
        self.model = model
        self.error = ""
        try:
            bullet = _Bullet.get()
        except Exception as e:  # 缺少 DLL 时不影响主界面
            self.error = str(e)
            return False
        lib = bullet.lib
        self.world = lib.bw_create(0.0, float(self.gravity), 0.0, int(self.iterations))
        if not self.world:
            self.error = "Bullet 世界创建失败"
            return False
        if self.ground:
            lib.bw_add_ground(self.world, 0.0)
        self.body_map = [-1] * len(model.rigid)
        self.bone_of_body = [-1] * len(model.rigid)
        self.offsets = [np.eye(4, dtype=np.float32)] * len(model.rigid)
        self.rest = [((0, 0, 0), (0, 0, 0, 1))] * len(model.rigid)
        self.modes = [0] * len(model.rigid)
        nb = len(model.bones)
        radians = math.pi / 180.0
        for i, rb in enumerate(model.rigid):
            bone = rb.bone if 0 <= rb.bone < nb else -1
            mass = float(rb.mass) if rb.mode != 0 else 0.0
            kinematic = 1 if rb.mode == 0 else 0
            shape = int(rb.shape)
            sx, sy, sz = [float(v) for v in rb.size]
            if shape == 0:
                sx = abs(sx)
                sy = sz = sx
            elif shape == 2:
                r = abs(sx)
                total = abs(sy)
                sx = r
                sy = max(0.01, total - 2.0 * r)
                sz = r
            else:
                sx, sy, sz = max(0.001, abs(sx)), max(0.001, abs(sy)), max(0.001, abs(sz))
            rot_rad = [float(v) * radians for v in rb.rot[:3]]
            q = euler_to_quat(*rot_rad)
            bi = lib.bw_add_body(self.world, shape, sx, sy, sz,
                                 *[float(v) for v in rb.pos], *rot_rad,
                                 mass, float(rb.mov_damp), float(rb.rot_damp),
                                 float(rb.repel), float(rb.friction),
                                 int(rb.group) & 15, int(rb.mask) & 0xFFFF, kinematic)
            self.body_map[i] = bi
            self.bone_of_body[i] = bone
            self.modes[i] = int(rb.mode)
            self.rest[i] = (tuple(float(v) for v in rb.pos), tuple(float(v) for v in q))
            if bone >= 0:
                bone_t = translation(*[float(v) for v in model.bones[bone].pos])
                self.offsets[i] = np.linalg.inv(bone_t) @ transform_to_mat4(rb.pos, q)
            else:
                self.offsets[i] = transform_to_mat4(rb.pos, q)
        self._body_map_array = np.ascontiguousarray(self.body_map, dtype=np.int32)
        self._bone_of_body_array = np.ascontiguousarray(self.bone_of_body, dtype=np.int32)
        self._modes_array = np.ascontiguousarray(self.modes, dtype=np.int32)
        self._offsets_array = np.ascontiguousarray(self.offsets, dtype=np.float32)
        self._body_positions = np.empty((len(model.rigid), 3), dtype=np.float32)
        self._body_rotations = np.empty((len(model.rigid), 4), dtype=np.float32)
        self._inverse_offsets_array = (
            np.ascontiguousarray(
                [mat4_inverse(offset) for offset in self.offsets],
                dtype=np.float32).reshape(-1, 4, 4)
            if self.offsets else np.zeros((0, 4, 4), dtype=np.float32)
        )
        self._rigid_for_bone = np.full(nb, -1, dtype=np.int32)
        for i, bone in enumerate(self.bone_of_body):
            if bone >= 0 and self.modes[i] != 0:
                self._rigid_for_bone[bone] = i
        self._override_rotations = np.empty((nb, 4), dtype=np.float32)
        self._override_translations = np.empty((nb, 3), dtype=np.float32)
        self._override_mask = np.empty(nb, dtype=np.uint8)
        self._pose_layout_id = None
        for joint in model.joints:
            a, b = joint.rigid_a, joint.rigid_b
            if not (0 <= a < len(self.body_map) and 0 <= b < len(self.body_map)):
                continue
            if self.body_map[a] < 0 or self.body_map[b] < 0:
                continue
            lib.bw_add_joint(self.world, int(joint.type),
                             self.body_map[a], self.body_map[b],
                             _arr(joint.pos), _arr([v * radians for v in joint.rot]),
                             _arr(joint.min_loc), _arr(joint.max_loc),
                             _arr([v * radians for v in joint.min_rot]),
                             _arr([v * radians for v in joint.max_rot]),
                             _arr(joint.spring_loc), _arr(joint.spring_rot))
        self._ready = True
        self.enabled = False
        return True

    def set_params(self, gravity=None, iterations=None) -> bool:
        """热更新重力/迭代次数：直接改现有 Bullet 世界，不重建刚体。

        原来调参要 build() 重建整个世界（大模型约 77 ms 并丢失当前姿态），
        而刚体形状/位置与这两个参数无关，能直接改就足够了。
        """
        if gravity is not None:
            self.gravity = float(gravity)
        if iterations is not None:
            self.iterations = int(iterations)
        if not self.world:
            return False
        try:
            lib = _Bullet.get().lib
            lib.bw_set_gravity(self.world, 0.0, float(self.gravity), 0.0)
            lib.bw_set_iterations(self.world, int(self.iterations))
        except Exception as e:  # 老 DLL 没有这两个入口时退回重建
            self.error = str(e)
            return False
        return True

    def set_body_params(self, index, mass=None, friction=None,
                        restitution=None) -> bool:
        """热更新单个刚体的质量/摩擦/弹性，不重建 Bullet 世界。

        改质量要重算惯性张量并唤醒刚体，静态与运动学刚体没有可改的质量，
        由 bw_set_body_mass 返回 0 表示跳过（物理跟随模式下这是正常情况）。
        """
        if not self.world or index < 0 or index >= len(self.body_map):
            return False
        bi = self.body_map[index]
        if bi < 0:
            return False
        try:
            lib = _Bullet.get().lib
            if mass is not None and hasattr(lib, "bw_set_body_mass"):
                if not lib.bw_set_body_mass(self.world, bi, float(mass)):
                    return False
            if friction is not None and hasattr(lib, "bw_set_body_friction"):
                lib.bw_set_body_friction(self.world, bi, float(friction))
            if restitution is not None and hasattr(lib, "bw_set_body_restitution"):
                lib.bw_set_body_restitution(self.world, bi, float(restitution))
        except Exception as e:  # 老 DLL 缺少入口时退回重建
            self.error = str(e)
            return False
        return True

    def release(self):
        if self.world:
            try:
                _Bullet.get().lib.bw_destroy(self.world)
            except Exception:
                pass
        self.world = None
        self._ready = False
        self.enabled = False
        self._body_map_array = np.zeros(0, dtype=np.int32)
        self._bone_of_body_array = np.zeros(0, dtype=np.int32)
        self._modes_array = np.zeros(0, dtype=np.int32)
        self._offsets_array = np.zeros((0, 4, 4), dtype=np.float32)
        self._body_positions = np.zeros((0, 3), dtype=np.float32)
        self._body_rotations = np.zeros((0, 4), dtype=np.float32)
        self._inverse_offsets_array = np.zeros((0, 4, 4), dtype=np.float32)
        self._rigid_for_bone = np.zeros(0, dtype=np.int32)
        self._pose_order_array = np.zeros(0, dtype=np.int32)
        self._pose_parent_array = np.zeros(0, dtype=np.int32)
        self._pose_rest_offsets = np.zeros((0, 3), dtype=np.float32)
        self._override_rotations = np.zeros((0, 4), dtype=np.float32)
        self._override_translations = np.zeros((0, 3), dtype=np.float32)
        self._override_mask = np.zeros(0, dtype=np.uint8)
        self._pose_layout_id = None

    def reset(self, pose: Pose, morph_weights=None, morphs=None):
        if not self._ready:
            return
        lib = _Bullet.get().lib
        pose.clear_overrides()
        pose.apply(morph_weights, morphs)
        world = pose.world()
        for i, bi in enumerate(self.body_map):
            if bi < 0:
                continue
            bone = self.bone_of_body[i]
            if 0 <= bone < len(pose.model.bones):
                body = world[bone] @ self.offsets[i]
                pos = body[:3, 3]
                quat = mat_to_quat(body[:3, :3])
            else:
                pos, quat = self.rest[i]
            lib.bw_set_body(self.world, bi, _arr(pos),
                            _arr([quat[0], quat[1], quat[2], quat[3]]))
            self._body_positions[i] = pos
            self._body_rotations[i] = quat
        lib.bw_clear_forces(self.world)

    # ------------------------------------------------------------ 仿真
    def step(self, pose: Pose, dt: float, morph_weights=None, morphs=None):
        if not (self._ready and self.enabled and self.world):
            return
        lib = _Bullet.get().lib
        W = pose.world()
        nb = len(pose.model.bones)
        if native_core is not None:
            if self._pose_layout_id != id(pose):
                self._pose_order_array = np.ascontiguousarray(
                    pose.order, dtype=np.int32)
                self._pose_parent_array = np.ascontiguousarray(
                    pose.parent, dtype=np.int32)
                self._pose_rest_offsets = np.ascontiguousarray(
                    pose.rest_off, dtype=np.float32)
                self._pose_layout_id = id(pose)
            native_core.physics_step(
                int(self.world), self._body_map_array,
                self._bone_of_body_array, self._modes_array,
                self._offsets_array, W, float(dt),
                self._body_positions, self._body_rotations,
                self._pose_order_array, self._pose_parent_array,
                self._rigid_for_bone, self._pose_rest_offsets,
                pose.rot, pose.trans, self._inverse_offsets_array,
                self._override_rotations, self._override_translations,
                self._override_mask)
            pose.clear_overrides()
            after = np.fromiter(
                (bool(b.flags & BF_AFTER_PHYSICS) for b in pose.model.bones),
                dtype=bool, count=nb)
            for bone in np.flatnonzero(self._override_mask):
                bone = int(bone)
                if after[bone]:
                    # 「物理后变形」：物理算完再套用手工姿态，刚体不覆盖骨骼
                    continue
                pose.ov_rot[bone] = self._override_rotations[bone]
                pose.ov_trans[bone] = self._override_translations[bone]
        else:
            posbuf = (ctypes.c_float * 3)()
            quatbuf = (ctypes.c_float * 4)()
            for i, bi in enumerate(self.body_map):
                if bi < 0 or self.modes[i] != 0:
                    continue
                bone = self.bone_of_body[i]
                if not (0 <= bone < nb):
                    continue
                M = W[bone] @ self.offsets[i]
                pos = [float(M[0, 3]), float(M[1, 3]), float(M[2, 3])]
                q = mat_to_quat(M[:3, :3])
                lib.bw_set_body(
                    self.world, bi, _arr(pos),
                    _arr([q[0], q[1], q[2], q[3]]))
            lib.bw_step(self.world, float(dt), 3)
            for i, bi in enumerate(self.body_map):
                if bi < 0:
                    continue
                lib.bw_get_body(self.world, bi, posbuf, quatbuf)
                self._body_positions[i] = posbuf
                self._body_rotations[i] = quatbuf

            by_bone = {}
            for i, bi in enumerate(self.body_map):
                if bi < 0 or self.modes[i] == 0:
                    continue
                bone = self.bone_of_body[i]
                if 0 <= bone < nb:
                    by_bone.setdefault(bone, []).append(i)
            if not by_bone:
                return
            pose.clear_overrides()
            Wcur = np.empty_like(W)
            ident = np.eye(4, dtype=np.float32)
            for bone in pose.order:
                p = pose.parent[bone]
                Wp = Wcur[p] if p >= 0 else ident
                hit = by_bone.get(bone)
                if hit and not (pose.model.bones[bone].flags & BF_AFTER_PHYSICS):
                    i = hit[-1]
                    body_m = transform_to_mat4(
                        self._body_positions[i], self._body_rotations[i])
                    local = (mat4_inverse(Wp) @ body_m
                             @ mat4_inverse(self.offsets[i]))
                    pose.ov_rot[bone] = mat_to_quat(local[:3, :3])
                    pose.ov_trans[bone] = (
                        local[:3, 3] - pose.rest_off[bone])
                    q = pose.ov_rot[bone]
                    t = pose.ov_trans[bone]
                else:
                    q = pose.rot[bone]
                    t = pose.trans[bone]
                R = np.eye(4, dtype=np.float32)
                R[:3, :3] = quat_to_mat(q)
                Wcur[bone] = Wp @ translation(*(pose.rest_off[bone] + t)) @ R
        pose.apply(morph_weights, morphs)
        pose.world()
