# -*- coding: utf-8 -*-
"""文档状态、撤销栈与结构性编辑操作。"""
from __future__ import annotations

import copy
import time
from typing import List, Optional

import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal

from .pmx import (BF_IK, BF_TAIL_INDEX, Bone, DisplayFrame, Joint, Material,
                 Morph, PMXModel, RigidBody, load_pmx, save_pmx)

UNDO_LIMIT = 12
POSE_UNDO_LIMIT = 12


class Document(QObject):
    edited = pyqtSignal(str)          # bone/material/morph/physics/structure/reload
    status = pyqtSignal(str)
    dirtyChanged = pyqtSignal(bool)
    selectionChanged = pyqtSignal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model: Optional[PMXModel] = None
        self.path = ""
        self.dirty = False
        self._undo: List[tuple] = []
        self._redo: List[tuple] = []
        self._last_undo = ("", 0.0)
        self.pose_capture = None
        self.pose_restore = None
        self.morph_capture = None
        self.morph_restore = None
        self.sel_kind = ""
        self.sel_index = -1
        self.suppress = False

    # ------------------------------------------------------------ 文件
    def load(self, path: str):
        model = load_pmx(path)
        self.model = model
        self.path = path
        self.dirty = False
        self._undo.clear()
        self._redo.clear()
        self.sel_kind, self.sel_index = "", -1
        self.dirtyChanged.emit(False)
        self.edited.emit("reload")
        self.status.emit("已打开 %s" % path)
        return model

    def clear(self):
        self.model = None
        self.path = ""
        self.dirty = False
        self._undo.clear()
        self._redo.clear()
        self._last_undo = ("", 0.0)
        self.sel_kind, self.sel_index = "", -1
        self.dirtyChanged.emit(False)
        self.selectionChanged.emit("", -1)

    def save(self, path: str):
        if not self.model:
            return
        save_pmx(self.model, path)
        self.path = path
        self.dirty = False
        self.dirtyChanged.emit(False)
        self.status.emit("已保存 %s" % path)

    def mark_dirty(self):
        if not self.dirty:
            self.dirty = True
            self.dirtyChanged.emit(True)

    # ------------------------------------------------------------ 撤销
    @staticmethod
    def _trim(stack: List[tuple]):
        """按类别分别限制深度：模型快照与姿态条目各 12 步，互不挤占。"""
        for want_pose in (False, True):
            limit = POSE_UNDO_LIMIT if want_pose else UNDO_LIMIT
            while True:
                idxs = [i for i, item in enumerate(stack)
                        if (item[1] is None) == want_pose]
                if len(idxs) <= limit:
                    break
                del stack[idxs[0]]

    def push_undo(self, label: str, coalesce: str = ""):
        if self.suppress or not self.model:
            return
        now = time.monotonic()
        if coalesce and self._last_undo[0] == coalesce and now - self._last_undo[1] < 0.9:
            self._last_undo = (coalesce, now)
            return
        pose = self.pose_capture() if self.pose_capture else None
        morphs = self.morph_capture() if self.morph_capture else None
        self._undo.append((label, copy.deepcopy(self.model), pose, morphs))
        self._trim(self._undo)
        self._redo.clear()
        self._last_undo = (coalesce, now)

    def push_pose_undo(self, label: str, coalesce: str = ""):
        """姿态类编辑（拖骨骼、重置姿态、导入 VPD）的轻量撤销条目。

        姿态只影响视口显示，不改 PMX 数据，所以不需要 deepcopy 整个模型
        （大模型一次 18 ms，拖一下就要压一条）：条目里 model = None，
        undo/redo 见到它只回滚姿态与形态权重快照。
        """
        if self.suppress or not self.model:
            return
        now = time.monotonic()
        if coalesce and self._last_undo[0] == coalesce and now - self._last_undo[1] < 0.9:
            self._last_undo = (coalesce, now)
            return
        pose = self.pose_capture() if self.pose_capture else None
        morphs = self.morph_capture() if self.morph_capture else None
        if pose is None and morphs is None:
            return
        self._undo.append((label, None, pose, morphs))
        self._trim(self._undo)
        self._redo.clear()
        self._last_undo = (coalesce, now)

    def edit(self, label: str, fn, kind: str = "bone", coalesce: str = ""):
        if not self.model:
            return
        self.push_undo(label, coalesce)
        fn(self.model)
        self.mark_dirty()
        self.edited.emit(kind)

    def undo(self) -> bool:
        if not self._undo:
            self.status.emit("没有可撤销的操作")
            return False
        label, model, pose, morphs = self._undo.pop()
        # 撤销后若立刻改同一字段，不能再被 coalesce 吞掉（否则这次改动无法撤销）
        self._last_undo = ("", 0.0)
        if model is None:
            # 姿态条目：模型没变，只回滚姿态/形态权重
            cur_pose = self.pose_capture() if self.pose_capture else None
            cur_morphs = self.morph_capture() if self.morph_capture else None
            self._redo.append((label, None, cur_pose, cur_morphs))
            self._trim(self._redo)
            if morphs is not None and self.morph_restore:
                self.morph_restore(morphs)
            if pose and self.pose_restore:
                self.pose_restore(pose)
            self.edited.emit("pose")
            self.status.emit("已撤销：%s" % label)
            return True
        current_pose = self.pose_capture() if self.pose_capture else None
        current_morphs = self.morph_capture() if self.morph_capture else None
        self._redo.append((label, copy.deepcopy(self.model), current_pose,
                           current_morphs))
        self._trim(self._redo)
        self.model = model
        if morphs is not None and self.morph_restore:
            self.morph_restore(morphs)
        if pose and self.pose_restore:
            self.pose_restore(pose)
        self.mark_dirty()
        self._clamp_selection()
        self.edited.emit("reload")
        self.status.emit("已撤销：%s" % label)
        return True

    def redo(self) -> bool:
        if not self._redo:
            self.status.emit("没有可重做的操作")
            return False
        label, model, pose, morphs = self._redo.pop()
        self._last_undo = ("", 0.0)
        if model is None:
            cur_pose = self.pose_capture() if self.pose_capture else None
            cur_morphs = self.morph_capture() if self.morph_capture else None
            self._undo.append((label, None, cur_pose, cur_morphs))
            self._trim(self._undo)
            if morphs is not None and self.morph_restore:
                self.morph_restore(morphs)
            if pose and self.pose_restore:
                self.pose_restore(pose)
            self.edited.emit("pose")
            self.status.emit("已重做：%s" % label)
            return True
        current_pose = self.pose_capture() if self.pose_capture else None
        current_morphs = self.morph_capture() if self.morph_capture else None
        self._undo.append((label, copy.deepcopy(self.model), current_pose,
                           current_morphs))
        self._trim(self._undo)
        self.model = model
        if morphs is not None and self.morph_restore:
            self.morph_restore(morphs)
        if pose and self.pose_restore:
            self.pose_restore(pose)
        self.mark_dirty()
        self._clamp_selection()
        self.edited.emit("reload")
        self.status.emit("已重做：%s" % label)
        return True

    def _clamp_selection(self):
        m = self.model
        if not m:
            return
        if self.sel_kind == "bone" and not (0 <= self.sel_index < len(m.bones)):
            self.sel_kind, self.sel_index = "", -1
        elif self.sel_kind == "material" and not (0 <= self.sel_index < len(m.materials)):
            self.sel_kind, self.sel_index = "", -1
        elif self.sel_kind == "morph" and not (0 <= self.sel_index < len(m.morphs)):
            self.sel_kind, self.sel_index = "", -1
        elif self.sel_kind == "rigid" and not (0 <= self.sel_index < len(m.rigid)):
            self.sel_kind, self.sel_index = "", -1
        elif self.sel_kind == "joint" and not (0 <= self.sel_index < len(m.joints)):
            self.sel_kind, self.sel_index = "", -1

    def select(self, kind: str, index: int):
        self.sel_kind, self.sel_index = kind, int(index)
        self.selectionChanged.emit(kind, int(index))


# ---------------------------------------------------------------- 结构编辑

def _remap(i: int, removed: int) -> int:
    if i == removed:
        return -1
    return i - 1 if i > removed else i


def add_bone(model: PMXModel, parent: int = -1) -> int:
    b = Bone()
    b.name = "新建骨骼"
    b.name_en = "new_bone"
    if 0 <= parent < len(model.bones):
        p = model.bones[parent]
        b.parent = parent
        tail = [p.pos[0], p.pos[1] + 1.0, p.pos[2]]
        if (p.flags & BF_TAIL_INDEX) and 0 <= p.tail_bone < len(model.bones):
            tail = list(model.bones[p.tail_bone].pos)
        elif any(abs(v) > 1e-6 for v in p.tail_offset):
            tail = [p.pos[i] + p.tail_offset[i] for i in range(3)]
        if abs(tail[0] - p.pos[0]) < 1e-4 and abs(tail[1] - p.pos[1]) < 0.05 \
                and abs(tail[2] - p.pos[2]) < 1e-4:
            tail = [tail[0], p.pos[1] + 1.0, tail[2]]
        b.pos = tail
    model.bones.append(b)
    return len(model.bones) - 1


def move_bone(model: PMXModel, index: int, delta: int) -> int:
    """把骨骼在列表里上移/下移 delta 位，并重映射所有骨骼索引。"""
    n = len(model.bones)
    if not (0 <= index < n):
        return index
    dst = index + int(delta)
    if not (0 <= dst < n):
        return index
    perm = list(range(n))
    perm[index], perm[dst] = perm[dst], perm[index]
    model.bones[index], model.bones[dst] = model.bones[dst], model.bones[index]

    def m(i: int) -> int:
        return perm[i] if 0 <= i < n else i

    for b in model.bones:
        b.parent = m(b.parent)
        if b.flags & BF_TAIL_INDEX and b.tail_bone >= 0:
            b.tail_bone = m(b.tail_bone)
        b.append_parent = m(b.append_parent)
        if b.ik:
            b.ik.target = m(b.ik.target)
            for link in b.ik.links:
                link.bone = m(link.bone)
    if model.n_vertices:
        bones = model.v_bones
        flat = bones.ravel()
        ok = (flat >= 0) & (flat < n)
        table = np.asarray(perm, dtype=flat.dtype)
        bones[:] = np.where(ok, table[np.clip(flat, 0, n - 1)], flat).reshape(bones.shape)
    for mo in model.morphs:
        if mo.type == 2:
            for off in mo.offsets:
                bi = int(off.get("bone", -1))
                if 0 <= bi < n:
                    off["bone"] = m(bi)
    for rb in model.rigid:
        rb.bone = m(rb.bone)
    for f in model.frames:
        f.items = [(ty, m(idx) if ty == 0 else idx) for ty, idx in f.items]
    return dst


def duplicate_bone(model: PMXModel, index: int) -> int:
    if not (0 <= index < len(model.bones)):
        return -1
    src = model.bones[index]
    b = copy.deepcopy(src)
    b.name = src.name + "_副本"
    b.name_en = (src.name_en or "bone") + "_copy"
    model.bones.append(b)
    return len(model.bones) - 1


def remove_bone(model: PMXModel, index: int) -> int:
    """删除骨骼并重映射所有引用；返回删除后的选中索引。"""
    n = len(model.bones)
    if not (0 <= index < n):
        return -1
    parent = model.bones[index].parent
    del model.bones[index]
    for b in model.bones:
        b.parent = _remap(b.parent, index)
        if b.flags & BF_TAIL_INDEX:
            b.tail_bone = _remap(b.tail_bone, index)
            if b.tail_bone < 0:
                b.flags &= ~BF_TAIL_INDEX
                b.tail_offset = [0.0, 0.0, 0.0]
        b.append_parent = _remap(b.append_parent, index)
        if b.ik:
            b.ik.target = _remap(b.ik.target, index)
            for link in b.ik.links:
                link.bone = _remap(link.bone, index)
            b.ik.links = [l for l in b.ik.links if l.bone >= 0]
            if b.ik.target < 0:
                b.ik = None
                b.flags &= ~BF_IK
    # 顶点权重：被删骨骼替换为父骨骼
    if model.n_vertices:
        bones = model.v_bones
        for k in range(4):
            col = bones[:, k]
            hit = col == index
            if hit.any():
                bones[hit, k] = parent if parent >= 0 else 0
            col2 = bones[:, k]
            bones[:, k] = np.where(col2 > index, col2 - 1, col2)
    for mo in model.morphs:
        if mo.type == 2:
            for off in mo.offsets:
                bi = int(off.get("bone", -1))
                off["bone"] = _remap(bi, index)
            mo.offsets = [o for o in mo.offsets if o.get("bone", -1) >= 0]
    for rb in model.rigid:
        rb.bone = _remap(rb.bone, index)
    for f in model.frames:
        items = []
        for ty, ii in f.items:
            if ty == 0:
                ii = _remap(ii, index)
                if ii < 0:
                    continue
            items.append((ty, ii))
        f.items = items
    for s in model.soft_bodies:
        s.anchors = [(rid, vi, nr) for rid, vi, nr in s.anchors]
    return min(index, len(model.bones) - 1)


def add_material(model: PMXModel, index: int = -1) -> int:
    mt = Material()
    mt.name = "新建材质"
    mt.name_en = "new_material"
    mt.face_count = 0
    model.materials.append(mt)
    return len(model.materials) - 1


def duplicate_material(model: PMXModel, index: int) -> int:
    if not (0 <= index < len(model.materials)):
        return -1
    src = model.materials[index]
    mt = copy.deepcopy(src)
    mt.name = src.name + "_副本"
    mt.name_en = (src.name_en or "material") + "_copy"
    model.materials.append(mt)
    return len(model.materials) - 1


def remove_material(model: PMXModel, index: int, merge: bool = False) -> int:
    """删除材质；merge=True 时把它的三角面并入上一个材质（保留几何）。"""
    if not (0 <= index < len(model.materials)):
        return -1
    if merge and index > 0:
        prev = model.materials[index - 1]
        prev.face_count = int(prev.face_count) + int(model.materials[index].face_count)
        del model.materials[index]
        for mo in model.morphs:
            if mo.type == 8:
                for off in mo.offsets:
                    mi = int(off.get("material", -1))
                    if mi == index:
                        off["material"] = index - 1
                    elif mi > index:
                        off["material"] = mi - 1
                mo.offsets = [o for o in mo.offsets if o.get("material", -1) >= 0]
        return index - 1
    start = sum(int(m.face_count) for m in model.materials[:index])
    count = int(model.materials[index].face_count)
    if count > 0:
        a = start * 3
        b = (start + count) * 3
        model.indices = np.concatenate([model.indices[:a], model.indices[b:]])
    del model.materials[index]
    for mo in model.morphs:
        if mo.type == 8:
            for off in mo.offsets:
                mi = int(off.get("material", -1))
                if mi == index:
                    off["material"] = -1
                elif mi > index:
                    off["material"] = mi - 1
            mo.offsets = [o for o in mo.offsets if o.get("material", -1) >= 0]
    for s in model.soft_bodies:
        if s.material == index:
            s.material = -1
        elif s.material > index:
            s.material -= 1
    return min(index, len(model.materials) - 1)


def add_morph(model: PMXModel, morph_type: int = 1) -> int:
    mo = Morph()
    mo.name = "新建形态"
    mo.name_en = "new_morph"
    mo.type = morph_type
    mo.panel = 4
    model.morphs.append(mo)
    return len(model.morphs) - 1


def duplicate_morph(model: PMXModel, index: int) -> int:
    if not (0 <= index < len(model.morphs)):
        return -1
    src = model.morphs[index]
    mo = copy.deepcopy(src)
    mo.name = src.name + "_副本"
    mo.name_en = (src.name_en or "morph") + "_copy"
    model.morphs.append(mo)
    return len(model.morphs) - 1


def remove_morph(model: PMXModel, index: int) -> int:
    if not (0 <= index < len(model.morphs)):
        return -1
    del model.morphs[index]
    for mo in model.morphs:
        if mo.type in (0, 9):
            for off in mo.offsets:
                mi = int(off.get("morph", -1))
                if mi == index:
                    off["morph"] = -1
                elif mi > index:
                    off["morph"] = mi - 1
            mo.offsets = [o for o in mo.offsets if o.get("morph", -1) >= 0]
    for f in model.frames:
        items = []
        for ty, ii in f.items:
            if ty == 1:
                if ii == index:
                    continue
                if ii > index:
                    ii -= 1
            items.append((ty, ii))
        f.items = items
    return min(index, len(model.morphs) - 1)


def add_frame(model: PMXModel, special: int = 0) -> int:
    """新建表示枠；调用方负责把骨骼/形态挂进去。"""
    f = DisplayFrame()
    f.name = "新建表示枠"
    f.name_en = "new_frame"
    f.special = int(special) & 1
    model.frames.append(f)
    return len(model.frames) - 1


def duplicate_frame(model: PMXModel, index: int) -> int:
    if not (0 <= index < len(model.frames)):
        return -1
    src = model.frames[index]
    f = copy.deepcopy(src)
    f.name = src.name + "_副本"
    f.name_en = (src.name_en or "frame") + "_copy"
    f.special = 0
    model.frames.append(f)
    return len(model.frames) - 1


def remove_frame(model: PMXModel, index: int) -> int:
    if not (0 <= index < len(model.frames)):
        return -1
    del model.frames[index]
    return min(index, len(model.frames) - 1)


def move_frame(model: PMXModel, index: int, delta: int) -> int:
    """在列表里上移/下移表示枠（delta = -1 / +1），返回新的索引。"""
    n = len(model.frames)
    if not (0 <= index < n):
        return index
    dst = index + delta
    if not (0 <= dst < n):
        return index
    model.frames[index], model.frames[dst] = model.frames[dst], model.frames[index]
    return dst


def frame_add_item(model: PMXModel, index: int, kind: int, item: int) -> bool:
    """把骨骼(0)/形态(1) 加进表示枠；重复项直接忽略（MMD 里一项只能挂一次）。"""
    if not (0 <= index < len(model.frames)):
        return False
    f = model.frames[index]
    entry = (int(kind), int(item))
    if entry in f.items or int(item) < 0:
        return False
    f.items.append(entry)
    return True


def frame_remove_item(model: PMXModel, index: int, pos: int) -> bool:
    if not (0 <= index < len(model.frames)):
        return False
    f = model.frames[index]
    if not (0 <= pos < len(f.items)):
        return False
    del f.items[pos]
    return True


def frame_move_item(model: PMXModel, index: int, pos: int, delta: int) -> int:
    if not (0 <= index < len(model.frames)):
        return pos
    items = model.frames[index].items
    dst = pos + delta
    if not (0 <= pos < len(items)) or not (0 <= dst < len(items)):
        return pos
    items[pos], items[dst] = items[dst], items[pos]
    return dst


def add_rigid(model: PMXModel, bone: int = -1) -> int:
    rb = RigidBody()
    rb.name = "新建刚体"
    rb.name_en = "new_rigid"
    rb.bone = bone
    rb.mode = 1
    rb.mass = 1.0
    rb.group = 0
    rb.mask = 0xFFFF
    if 0 <= bone < len(model.bones):
        rb.pos = list(model.bones[bone].pos)
    model.rigid.append(rb)
    return len(model.rigid) - 1


def duplicate_rigid(model: PMXModel, index: int) -> int:
    if not (0 <= index < len(model.rigid)):
        return -1
    src = model.rigid[index]
    rb = copy.deepcopy(src)
    rb.name = src.name + "_副本"
    rb.name_en = (src.name_en or "rigid") + "_copy"
    model.rigid.append(rb)
    return len(model.rigid) - 1


def remove_rigid(model: PMXModel, index: int) -> int:
    if not (0 <= index < len(model.rigid)):
        return -1
    del model.rigid[index]
    for j in model.joints:
        j.rigid_a = _remap(j.rigid_a, index)
        j.rigid_b = _remap(j.rigid_b, index)
    model.joints = [j for j in model.joints if j.rigid_a >= 0 and j.rigid_b >= 0]
    for mo in model.morphs:
        if mo.type == 10:
            for off in mo.offsets:
                ri = int(off.get("rigid", -1))
                off["rigid"] = _remap(ri, index)
            mo.offsets = [o for o in mo.offsets if o.get("rigid", -1) >= 0]
    for s in model.soft_bodies:
        anchors = []
        for rid, vi, nr in s.anchors:
            rid = _remap(rid, index)
            if rid >= 0:
                anchors.append((rid, vi, nr))
        s.anchors = anchors
    return min(index, len(model.rigid) - 1)


def add_joint(model: PMXModel) -> int:
    j = Joint()
    j.name = "新建关节"
    j.name_en = "new_joint"
    n = len(model.rigid)
    j.rigid_a = n - 2 if n >= 2 else -1
    j.rigid_b = n - 1 if n >= 1 else -1
    if n:
        j.pos = list(model.rigid[n - 1].pos)
    model.joints.append(j)
    return len(model.joints) - 1


def duplicate_joint(model: PMXModel, index: int) -> int:
    if not (0 <= index < len(model.joints)):
        return -1
    src = model.joints[index]
    j = copy.deepcopy(src)
    j.name = src.name + "_副本"
    j.name_en = (src.name_en or "joint") + "_copy"
    model.joints.append(j)
    return len(model.joints) - 1


def remove_joint(model: PMXModel, index: int) -> int:
    if not (0 <= index < len(model.joints)):
        return -1
    del model.joints[index]
    return min(index, len(model.joints) - 1)
