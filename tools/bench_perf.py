# -*- coding: utf-8 -*-
"""对 PMX 加载、姿态求解、蒙皮与视口叠加层构建进行 CPU 基准测试。"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pmxeditor.pmx import load_pmx
from pmxeditor.skinning import Pose, SkinDeformer, active_ik_indices
from pmxeditor.viewport import Viewport


WARMUP_RUNS = 3


class _OverlayProbe:
    _prepare_bone_cache = Viewport._prepare_bone_cache
    _build_bone_lines = Viewport._build_bone_lines
    _build_bone_lines_reference = Viewport._build_bone_lines_reference
    _build_rigid_lines = Viewport._build_rigid_lines
    _build_joint_lines = Viewport._build_joint_lines
    _pose_delta_from = Viewport._pose_delta_from
    _pose_delta_matrix = Viewport._pose_delta_matrix
    _rigid_rest_matrix = Viewport._rigid_rest_matrix
    _rigid_rest_matrices = Viewport._rigid_rest_matrices
    _rigid_rest_inverses = Viewport._rigid_rest_inverses
    _joint_rest_matrices = Viewport._joint_rest_matrices
    _global_pose_delta_from = Viewport._global_pose_delta_from
    _global_pose_delta = Viewport._global_pose_delta
    _rigid_current_matrix = Viewport._rigid_current_matrix
    _joint_current_matrix = Viewport._joint_current_matrix
    _overlay_arrays = Viewport._overlay_arrays
    _global_root_bone = Viewport._global_root_bone
    _pose_delta_all = Viewport._pose_delta_all
    _physics_body_matrices = Viewport._physics_body_matrices
    _physics_sim_mask = Viewport._physics_sim_mask
    _solid_mesh = Viewport._solid_mesh
    _build_solid_template = Viewport._build_solid_template
    _changed_slots = Viewport._changed_slots
    _slot_matrices = Viewport._slot_matrices
    _apply_solid_rows = Viewport._apply_solid_rows
    _solid_static_geometry = Viewport._solid_static_geometry
    _bone_solid_geometry = Viewport._bone_solid_geometry
    _build_solid_geometry = Viewport._build_solid_geometry

    def __init__(self, model):
        self.model = model
        self.selection_kind = ""
        self.selection_index = -1
        self.physics = SimpleNamespace(
            enabled=False, _ready=False, body_map=[],
            _body_positions=np.zeros((0, 3), np.float32),
            _body_rotations=np.zeros((0, 4), np.float32))
        self._rb_world = np.zeros((0, 4, 4), np.float32)
        self._joint_world = np.zeros((0, 4, 4), np.float32)
        self._rb_dirty = False
        self._perf_enabled = False
        self._bone_static = None
        self._rb_rest_cache = None
        self._rb_rest_inv_cache = None
        self._joint_rest_cache = None
        self._overlay_arrays_cache = None
        self._rb_changed = None
        self._joint_changed = None
        self._solid_template = None
        self._solid_tpl_dirty = True
        self._solid_tpl_serial = 0
        self._solid_out_pos = None
        self._solid_out_nrm = None
        self._solid_parts = []
        self._solid_count = 0
        self._solid_attr_sig = None
        self._solid_attr_sig_uploaded = None
        self._solid_mesh_cache = {}
        self._solid_geom = None
        self.show_bones = True
        self.show_rigid = True
        self.show_joints = True
        self.bone_opacity = 0.16
        self.rigid_opacity = 0.22
        self.joint_opacity = 0.33
        # 叠加层要乘上骨骼相对静止姿态的增量，视口的这套计算依赖 self.pose；
        # 基准只关心 CPU 几何，构造一个中性姿态即可，不涉及 GL 上下文。
        self.pose = Pose(model)
        self._prepare_bone_cache()


def _measure(fn, runs, prepare=None):
    for _ in range(WARMUP_RUNS):
        if prepare:
            prepare()
        fn()
    samples = []
    for _ in range(runs):
        if prepare:
            prepare()
        start = time.perf_counter_ns()
        fn()
        samples.append((time.perf_counter_ns() - start) / 1_000_000.0)
    ordered = sorted(samples)
    p90_index = min(len(ordered) - 1, math.ceil(0.9 * len(ordered)) - 1)
    return {
        "min_ms": min(samples),
        "avg_ms": statistics.fmean(samples),
        "p90_ms": ordered[p90_index],
    }


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_benchmarks(model_path, runs):
    model = load_pmx(str(model_path))
    pose = Pose(model)
    deformer = SkinDeformer(model)
    probe = _OverlayProbe(model)
    world = pose.world()
    ik_indices = [
        i for i, bone in enumerate(model.bones)
        if bone.flags & 0x0020 and bone.ik
    ]
    drag_bone = ik_indices[0] if ik_indices else (0 if pose.n else -1)
    subset_bones = pose.changed_subtrees({drag_bone}) if drag_bone >= 0 else set()
    if drag_bone >= 0:
        active_subset = active_ik_indices(pose, drag_bone)
        for index in active_subset:
            subset_bones.add(index)
            subset_bones.update(link.bone for link in model.bones[index].ik.links)
        subset_bones = pose.changed_subtrees(subset_bones)
    previous_pos, previous_nrm = deformer.deform(model.v_pos, model.v_nrm, world)

    def world_full():
        pose.world_cache = None
        pose.world()

    def prepare_world_incremental():
        pose.reset()
        pose.world()

    def prepare_pose():
        pose.reset()
        pose.world()

    def prepare_drag():
        pose.reset()
        pose.world()
        if drag_bone >= 0:
            pose.translate_world(drag_bone, (0.0, 0.02, 0.0))
            pose.world_update()

    def world_incremental():
        if drag_bone >= 0:
            pose.rotate_world(drag_bone, (0.0, 1.0, 0.0), 0.02)
            pose.world_update()
        pose.world()

    def deform_full():
        deformer.deform(model.v_pos, model.v_nrm, world)

    def deform_subset():
        deformer.deform_subset(
            model.v_pos, model.v_nrm, world, subset_bones,
            previous_pos, previous_nrm)

    def solve_idle():
        pose.solve_ik(max_loops=6)

    def solve_drag():
        pose.solve_ik(max_loops=6)

    def solve_drag_3():
        pose.solve_ik(max_loops=3)

    def solve_drag_active():
        active = active_ik_indices(pose, drag_bone) if drag_bone >= 0 else set()
        pose.solve_ik(max_loops=3, only=active or None)

    def solve_full():
        pose.solve_ik()

    def solid_geometry():
        # 完整叠加层：刚体/关节矩阵 → 批量变换实体网格 → 骨骼实体
        probe._build_rigid_lines()
        probe._build_joint_lines()
        probe._build_solid_geometry()

    flip = [0]

    def prepare_solid():
        # 交替小幅旋转一根骨骼，模拟摆姿/物理帧：只有该子树对应的刚体变了，
        # 增量更新应当只重算这一小部分。
        flip[0] += 1
        probe.pose.reset()
        if drag_bone >= 0:
            probe.pose.rotate_world(drag_bone, (0.0, 1.0, 0.0),
                                    0.02 if flip[0] % 2 else -0.02)
            probe.pose.world_update()

    benchmarks = {
        "load": lambda: load_pmx(str(model_path)),
        "world_full": world_full,
        "deform_full": deform_full,
        "deform_subset": deform_subset,
        "bone_lines": lambda: probe._build_bone_lines(world),
        "rigid_matrices": lambda: probe._build_rigid_lines(),
        "joint_matrices": lambda: probe._build_joint_lines(),
        "solid_geometry": solid_geometry,
        "solve_idle": solve_idle,
        "solve_drag_6": solve_drag,
        "solve_drag_3": solve_drag_3,
        "solve_drag_active_3": solve_drag_active,
        "solve_full": solve_full,
    }
    prepares = {
        "solid_geometry": prepare_solid,
        "solve_idle": prepare_pose,
        "solve_drag_6": prepare_drag,
        "solve_drag_3": prepare_drag,
        "solve_drag_active_3": prepare_drag,
        "solve_full": prepare_drag,
    }
    return {
        "model": {
            "path": str(model_path),
            "sha256": _sha256(model_path),
            "vertices": model.n_vertices,
            "bones": len(model.bones),
            "rigid_bodies": len(model.rigid),
            "joints": len(model.joints),
            "ik_bones": len(ik_indices),
        },
        "runs": runs,
        "warmup_runs": WARMUP_RUNS,
        "results": {
            name: _measure(fn, runs, prepare=prepares.get(name))
            for name, fn in benchmarks.items()
        } | {
            "world_incremental": _measure(
                world_incremental, runs, prepare=prepare_world_incremental)
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path, help="待测试的 PMX 模型")
    parser.add_argument("--runs", type=int, default=20, help="每项测量次数（默认：20）")
    parser.add_argument("--json", type=Path, help="将完整结果写入 JSON 文件")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs 必须大于 0")
    if not args.model.is_file():
        parser.error("模型文件不存在：%s" % args.model)

    result = run_benchmarks(args.model.resolve(), args.runs)
    print("模型：{path}".format(**result["model"]))
    print("SHA-256：{sha256}".format(**result["model"]))
    print("顶点 {vertices} · 骨骼 {bones} · 刚体 {rigid_bodies} · 关节 {joints}".format(
        **result["model"]))
    print("{:<16} {:>10} {:>10} {:>10}".format("阶段", "min ms", "avg ms", "p90 ms"))
    for name, values in result["results"].items():
        print("{:<16} {:>10.2f} {:>10.2f} {:>10.2f}".format(
            name, values["min_ms"], values["avg_ms"], values["p90_ms"]))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("JSON：%s" % args.json.resolve())


if __name__ == "__main__":
    main()
