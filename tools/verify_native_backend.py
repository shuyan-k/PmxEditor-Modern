# -*- coding: utf-8 -*-
"""对拍并测量 pybind11 C++ 后端与 Python/NumPy 参考路径。"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pmxeditor import physics
from pmxeditor import skinning
from pmxeditor.native_backend import backend_label, core
from pmxeditor.pmx import (
    BF_INHERIT_MOV, BF_INHERIT_ROT, Bone, Morph, PMXModel, load_pmx,
)
from pmxeditor.skinning import (
    Pose, SkinDeformer, apply_vertex_morphs, axis_angle_quat,
)


def _elapsed(fn, runs):
    samples = []
    for _ in range(runs):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1000.0)
    return statistics.fmean(samples)


_RECORDS = []
_TIMINGS = {}

# IK 是迭代求解：原生用 float32，NumPy 参考用 float64，迭代到收敛后会出现
# 约 1e-4 量级的量化差（实测 rotation 1.25e-4 / world 3.2e-4）。链接遍历
# 顺序与限位阈值已对齐，剩下的差值属于数值精度而非语义差异。
IK_TOL = 2e-4
IK_WORLD_TOL = 5e-4


def _assert_close(name, actual, expected, tolerance=1e-4):
    error = float(np.max(np.abs(actual - expected))) if actual.size else 0.0
    _RECORDS.append({"name": name, "max_error": error,
                     "tolerance": tolerance})
    if error > tolerance:
        raise AssertionError("%s max error %.8g exceeds %.8g" %
                             (name, error, tolerance))
    print("%s max error: %.8g" % (name, error))


def _record_timing(name, values):
    _TIMINGS[name] = values
    print("%s: NumPy %.3f ms / C++ %.3f ms" %
          (name, values["numpy"], values["C++"]))


def _make_pose(model, ik_index):
    pose = Pose(model)
    if ik_index >= 0:
        pose.translate_world(ik_index, (0.0, 0.02, 0.0))
        pose.world_update()
        pose.solve_ik(max_loops=3)
    return pose


def verify_pose(model, runs):
    original_core = skinning.native_core
    native_pose = Pose(model)
    python_pose = Pose(model)
    for pose in (native_pose, python_pose):
        for bone in range(0, min(pose.n, 100), 17):
            pose.rotate_local(
                bone, axis_angle_quat((1.0, 0.3, 0.2), 0.03 + bone * 0.0001))
        pose.world_update()
    try:
        skinning.native_core = original_core
        native_world = native_pose.world().copy()
        skinning.native_core = None
        python_world = python_pose.world().copy()
        _assert_close("pose world matrices", native_world, python_world)

        subset_indices = {min(93, native_pose.n - 1), min(89, native_pose.n - 1)}
        skinning.native_core = original_core
        native_subset = native_pose.world_subset(subset_indices)
        skinning.native_core = None
        python_subset = python_pose.world_subset(subset_indices)
        _assert_close("pose world subset", native_subset, python_subset)

        for pose in (native_pose, python_pose):
            pose.rotate_local(min(12, pose.n - 1),
                              axis_angle_quat((0.2, 1.0, 0.1), 0.11))
            pose.world_update()
        skinning.native_core = original_core
        native_dirty_world = native_pose.world().copy()
        skinning.native_core = None
        python_dirty_world = python_pose.world().copy()
        _assert_close("pose incremental world matrices",
                      native_dirty_world, python_dirty_world)

        rng = np.random.default_rng(20261022)
        append_bones = [
            i for i, bone in enumerate(model.bones)
            if bone.flags & (BF_INHERIT_ROT | BF_INHERIT_MOV)
        ]
        changed_bones = sorted(set(
            append_bones + list(range(0, native_pose.n, 7))))
        perturbations = {
            bone: (rng.normal(size=3), float(rng.uniform(-0.8, 0.8)),
                   rng.normal(0.0, 0.04, 3).astype(np.float32))
            for bone in changed_bones
        }
        append_native_pose = Pose(model)
        append_python_pose = Pose(model)
        for pose in (append_native_pose, append_python_pose):
            for bone, (axis, angle, translation) in perturbations.items():
                pose.rotate_local(bone, axis_angle_quat(axis, angle))
                pose.base_trans[bone] = translation
            pose.world_update()
        skinning.native_core = original_core
        append_native_world = append_native_pose.world().copy()
        skinning.native_core = None
        append_python_world = append_python_pose.world().copy()
        _assert_close("append world matrices", append_native_world,
                      append_python_world)
        if append_bones:
            skinning.native_core = original_core
            append_native_subset = append_native_pose.world_subset(append_bones)
            skinning.native_core = None
            append_python_subset = append_python_pose.world_subset(append_bones)
            _assert_close("append world subset", append_native_subset,
                          append_python_subset)

        ik_indices = [i for i, bone in enumerate(model.bones)
                      if bone.flags & 0x20 and bone.ik]
        if ik_indices:
            for max_loops in (1, 3, 0):
                native_ik_pose = Pose(model)
                python_ik_pose = Pose(model)
                for pose in (native_ik_pose, python_ik_pose):
                    for bone in range(min(120, pose.n)):
                        if bone % 11 == 3:
                            pose.rotate_local(
                                bone, axis_angle_quat((1, 0.3, 0.2), 0.03))
                    pose.world_update()
                selected = set(ik_indices[:2])
                skinning.native_core = original_core
                native_solved = native_ik_pose.solve_ik(max_loops, selected)
                skinning.native_core = None
                python_solved = python_ik_pose.solve_ik(max_loops, selected)
                if native_solved != python_solved:
                    raise AssertionError("IK chain count differs between backends")
                # 链接顺序与限位阈值已统一；max_loops=0 会按 PMX 的 loop 数
                # 迭代到收敛（合成长链 40 次），只剩 float32/float64 量化差。
                _assert_close("IK rotations",
                              native_ik_pose.base_rot,
                              python_ik_pose.base_rot,
                              tolerance=IK_TOL)
                _assert_close("IK world matrices", native_ik_pose.world(),
                              python_ik_pose.world(),
                              tolerance=IK_WORLD_TOL)

            for ik_bone in ik_indices:
                native_ik_pose = Pose(model)
                python_ik_pose = Pose(model)
                relevant = {ik_bone, model.bones[ik_bone].ik.target}
                relevant.update(link.bone for link in
                                model.bones[ik_bone].ik.links)
                for pose in (native_ik_pose, python_ik_pose):
                    for bone in relevant:
                        pose.rotate_local(
                            bone, axis_angle_quat((0.2, 1.0, 0.3), 0.37))
                    pose.world_update()
                skinning.native_core = original_core
                native_solved = native_ik_pose.solve_ik(
                    max_loops=5, only={ik_bone})
                skinning.native_core = None
                python_solved = python_ik_pose.solve_ik(
                    max_loops=5, only={ik_bone})
                if native_solved != python_solved:
                    raise AssertionError("Perturbed IK chain count differs")
                _assert_close("perturbed IK rotations",
                              native_ik_pose.base_rot,
                              python_ik_pose.base_rot,
                              tolerance=IK_TOL)

        timings = {}
        for label, backend in (("numpy", None), ("C++", original_core)):
            skinning.native_core = backend
            timings[label] = _elapsed(
                lambda: _world_uncached(native_pose), runs)
        _record_timing("world_full", timings)

        ik_index = ik_indices[0] if ik_indices else -1
        if ik_index >= 0:
            timings = {}
            for label, backend in (("numpy", None), ("C++", original_core)):
                skinning.native_core = backend
                timings[label] = _elapsed(
                    lambda: _solve_fresh_ik(model, ik_index), runs)
            _record_timing("ik_solve", timings)
    finally:
        skinning.native_core = original_core


def _world_uncached(pose):
    pose._invalidate_world()
    return pose.world()


def _solve_fresh_ik(model, ik_index):
    pose = Pose(model)
    pose.translate_world(ik_index, (0.0, 0.02, 0.0))
    pose.world_update()
    return pose.solve_ik(max_loops=3)


def verify_deformation(model, runs):
    pose = _make_pose(
        model, next((i for i, bone in enumerate(model.bones)
                     if bone.flags & 0x20 and bone.ik), -1))
    deformer = SkinDeformer(model)
    world = pose.world()
    original_core = skinning.native_core
    if original_core is None:
        raise RuntimeError("C++ 后端未加载，请先运行 native\\build_core.ps1")
    try:
        skinning.native_core = None
        reference_pos, reference_nrm = deformer.deform(
            model.v_pos, model.v_nrm, world)
        native_pos, native_nrm = original_core.deform(
            model.v_pos, model.v_nrm, model.v_bones, model.v_weights,
            model.v_wtype, deformer.rest_pos, world, model.v_sdef)
        _assert_close("full positions", native_pos, reference_pos)
        _assert_close("full normals", native_nrm, reference_nrm)

        dirty = pose.changed_subtrees({0}) if pose.n else set()
        affected = []
        for bone in dirty:
            start, count = deformer.offsets[bone]
            if count:
                affected.append(deformer.entries_vi[start:start + count])
        indices = (np.unique(np.concatenate(affected)).astype(np.int32)
                   if affected else np.zeros(0, dtype=np.int32))
        if indices.size:
            reference_subset = deformer.deform_subset(
                model.v_pos, model.v_nrm, world, dirty,
                reference_pos, reference_nrm)
            native_subset = original_core.deform_subset(
                model.v_pos, model.v_nrm, model.v_bones, model.v_weights,
                model.v_wtype, deformer.rest_pos, world,
                np.ascontiguousarray(indices), reference_pos, reference_nrm,
                model.v_sdef)
            _assert_close("subset positions", native_subset[0],
                          reference_subset[0])
            _assert_close("subset normals", native_subset[1],
                          reference_subset[1])

        timings = {}
        for label, backend in (("numpy", None), ("C++", original_core)):
            skinning.native_core = backend
            timings[label] = _elapsed(
                lambda: deformer.deform(model.v_pos, model.v_nrm, world), runs)
        _record_timing("deform_full", timings)
    finally:
        skinning.native_core = original_core


def verify_morphs(model, runs):
    original_core = skinning.native_core
    if original_core is None:
        raise RuntimeError("C++ 后端未加载，请先运行 native\\build_core.ps1")
    try:
        deformer = SkinDeformer(model)
        vertex_weights = {
            index: ((index % 7) - 3) / 5.0
            for index, morph in enumerate(model.morphs)
            if morph.type in (1, 3) and morph.offsets
        }
        skinning.native_core = original_core
        native_pos, native_uv = apply_vertex_morphs(
            model, vertex_weights, deformer)
        skinning.native_core = None
        python_pos, python_uv = apply_vertex_morphs(
            model, vertex_weights, deformer)
        _assert_close("vertex morph positions", native_pos, python_pos,
                      tolerance=2e-5)
        _assert_close("vertex morph UV", native_uv, python_uv,
                      tolerance=2e-6)
        if vertex_weights:
            timings = {}
            for label, backend in (("numpy", None), ("C++", original_core)):
                skinning.native_core = backend
                timings[label] = _elapsed(
                    lambda: apply_vertex_morphs(
                        model, vertex_weights, deformer), runs)
            _record_timing("vertex_morph", timings)

        bone_weights = {
            index: ((index % 5) - 2) / 4.0
            for index, morph in enumerate(model.morphs)
            if morph.type == 2 and morph.offsets
        }
        if bone_weights:
            native_pose = Pose(model)
            python_pose = Pose(model)
            skinning.native_core = original_core
            native_pose.apply(bone_weights, model.morphs)
            skinning.native_core = None
            python_pose.apply(bone_weights, model.morphs)
            _assert_close("bone morph rotations", native_pose.rot,
                          python_pose.rot, tolerance=2e-6)
            _assert_close("bone morph translations", native_pose.trans,
                          python_pose.trans, tolerance=2e-6)

        synthetic = PMXModel()
        synthetic.v_pos = np.arange(12, dtype=np.float32).reshape(4, 3)
        synthetic.v_uv = np.arange(8, dtype=np.float32).reshape(4, 2)
        synthetic.v_bones = np.zeros((4, 4), dtype=np.int32)
        synthetic.v_weights = np.zeros((4, 4), dtype=np.float32)
        synthetic.v_weights[:, 0] = 1.0
        synthetic.v_wtype = np.zeros(4, dtype=np.uint8)
        synthetic.bones = [Bone() for _ in range(3)]
        synthetic.morphs = [
            Morph(type=1, offsets=[
                {"vertex": 1, "offset": [0.1, -0.2, 0.3]},
                {"vertex": 1, "offset": [0.5, 0.6, 0.7]},
                {"vertex": -1, "offset": [1.0, 1.0, 1.0]},
                {"vertex": 8, "offset": [1.0, 1.0, 1.0]},
            ]),
            Morph(type=1, offsets=[
                {"vertex": 1, "offset": [-0.3, 0.1, 0.2]},
            ]),
            Morph(type=3, offsets=[
                {"vertex": 2, "offset": [0.1, 0.2, 0.3, 0.4]},
                {"vertex": 2, "offset": [-0.2, 0.5, 0.6, 0.7]},
                {"vertex": 8, "offset": [1.0, 1.0, 1.0, 1.0]},
            ]),
            Morph(type=2, offsets=[
                {"bone": 1, "move": [0.2, -0.1, 0.3],
                 "rot": [0.2, 0.1, -0.3]},
                {"bone": 1, "move": [0.1, 0.4, -0.2],
                 "rot": [-0.1, 0.2, 0.05]},
                {"bone": -1, "move": [1.0, 1.0, 1.0],
                 "rot": [1.0, 1.0, 1.0]},
            ]),
            Morph(type=2, offsets=[
                {"bone": 2, "move": [-0.4, 0.2, 0.1],
                 "rot": [0.1, -0.3, 0.2]},
            ]),
            Morph(type=1, offsets=[
                {"vertex": 3, "offset": [1.0, 1.0, 1.0]},
            ]),
        ]
        synthetic_weights = {0: 0.4, 1: -0.1, 2: -0.25,
                             3: 0.3, 4: -0.5, 5: 0.0,
                             -1: 1.0, 20: 1.0}
        synthetic_deformer = SkinDeformer(synthetic)
        skinning.native_core = original_core
        native_pos, native_uv = apply_vertex_morphs(
            synthetic, synthetic_weights, synthetic_deformer)
        native_pose = Pose(synthetic)
        native_pose.apply(synthetic_weights, synthetic.morphs)
        skinning.native_core = None
        python_pos, python_uv = apply_vertex_morphs(
            synthetic, synthetic_weights, synthetic_deformer)
        python_pose = Pose(synthetic)
        python_pose.apply(synthetic_weights, synthetic.morphs)
        _assert_close("synthetic vertex morph positions",
                      native_pos, python_pos, tolerance=2e-6)
        _assert_close("synthetic vertex morph UV",
                      native_uv, python_uv, tolerance=2e-6)
        _assert_close("synthetic bone morph rotations",
                      native_pose.rot, python_pose.rot, tolerance=2e-6)
        _assert_close("synthetic bone morph translations",
                      native_pose.trans, python_pose.trans,
                      tolerance=2e-6)
    finally:
        skinning.native_core = original_core


def verify_physics(model, runs):
    original_core = physics.native_core
    if original_core is None:
        raise RuntimeError("C++ 后端未加载，请先运行 native\\build_core.ps1")
    ik_index = next((i for i, bone in enumerate(model.bones)
                     if bone.flags & 0x20 and bone.ik), -1)
    native_pose = _make_pose(model, ik_index)
    python_pose = _make_pose(model, ik_index)
    native_physics = physics.MMDPhysics()
    python_physics = physics.MMDPhysics()
    try:
        if not native_physics.build(model) or not python_physics.build(model):
            raise RuntimeError("Bullet 初始化失败: %s / %s" %
                               (native_physics.error, python_physics.error))
        native_physics.reset(native_pose)
        python_physics.reset(python_pose)
        native_physics.enabled = True
        python_physics.enabled = True
        for _ in range(runs):
            native_physics.step(native_pose, 1.0 / 60.0)
            physics.native_core = None
            python_physics.step(python_pose, 1.0 / 60.0)
            physics.native_core = original_core
        _assert_close("physics world", native_pose.world(),
                      python_pose.world())
        _assert_close("physics output buffer positions",
                      native_physics._body_positions,
                      python_physics._body_positions)
    finally:
        physics.native_core = original_core
        native_physics.release()
        python_physics.release()


def _default_exe():
    """优先使用最新的发行包；也可用 PMX_VERIFY_EXE 环境变量覆盖。"""
    override = os.environ.get("PMX_VERIFY_EXE")
    if override:
        path = Path(override)
        return path if path.is_file() else None
    dist = Path(__file__).resolve().parents[1] / "dist"
    candidates = [path for path in dist.glob("release-*/PmxStudio.exe")
                  if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def run_checks(model_path, runs):
    """在当前解释器内执行全部对拍，返回可序列化的报告。"""
    global _RECORDS, _TIMINGS
    _RECORDS = []
    _TIMINGS = {}
    started = time.perf_counter()
    report = {
        "ok": False,
        "model": str(model_path),
        "runs": runs,
        "backend": backend_label(),
        "native_module": str(getattr(core, "__file__", "") or ""),
        "python": sys.version,
        "executable": sys.executable,
        "checks": [],
        "timings": {},
        "error": "",
        "elapsed_seconds": 0.0,
    }
    try:
        if core is None:
            raise RuntimeError(
                "C++ backend unavailable; use the packaged PmxStudio.exe "
                "or build native\\build_core.ps1")
        model = load_pmx(str(model_path))
        report["model_info"] = {
            "vertices": int(getattr(model, "n_vertices", len(model.v_pos))),
            "bones": len(model.bones),
            "materials": len(model.materials),
            "morphs": len(model.morphs),
            "rigid_bodies": len(model.rigid),
            "joints": len(model.joints),
        }
        verify_pose(model, runs)
        verify_morphs(model, runs)
        verify_deformation(model, runs)
        verify_physics(model, min(runs, 10))
        report["ok"] = True
    except Exception as exc:  # 报告必须落盘，供调用方判断失败原因
        report["error"] = "%s: %s" % (type(exc).__name__, exc)
    finally:
        report["checks"] = list(_RECORDS)
        report["timings"] = dict(_TIMINGS)
        report["elapsed_seconds"] = time.perf_counter() - started
    return report


def _print_report(report):
    print("对拍模型：%s" % report.get("model", ""))
    info = report.get("model_info") or {}
    if info:
        print("顶点 %(vertices)s · 骨骼 %(bones)s · 材质 %(materials)s · "
              "形态 %(morphs)s · 刚体 %(rigid_bodies)s · "
              "关节 %(joints)s" % info)
    print("后端：%s" % report.get("backend", ""))
    for check in report.get("checks", []):
        print("  %-32s max error %.8g (tol %.8g)" %
              (check["name"], check["max_error"], check["tolerance"]))
    if report.get("ok"):
        print("对拍通过：%d 项检查" % len(report.get("checks", [])))
    else:
        print("对拍失败：%s" % report.get("error", "unknown error"))


def run_cli(argv=None, in_process=False, require_out=False):
    parser = argparse.ArgumentParser(
        description="用打包后的 PmxStudio.exe 对拍 C++/NumPy 后端")
    parser.add_argument("model", type=Path)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--out", type=Path, help="JSON 报告输出路径")
    parser.add_argument("--exe", type=Path, help="指定打包后的程序")
    parser.add_argument("--in-process", action="store_true",
                        help="当前解释器内对拍（需匹配的 C++ 后端）")
    args = parser.parse_args(argv)
    if args.runs < 1:
        parser.error("--runs must be positive")
    if not args.model.is_file():
        parser.error("Model file not found: %s" % args.model)
    if require_out and args.out is None:
        parser.error("--out is required when running the packaged verifier")

    if in_process or args.in_process:
        out = args.out or (Path.cwd() / "verify_native_report.json")
        report = run_checks(args.model.resolve(), args.runs)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        _print_report(report)
        print("报告：%s" % out)
        return 0 if report["ok"] else 1

    exe = args.exe or _default_exe()
    if exe is None or not exe.is_file():
        if core is None:
            print("未找到打包后的程序，且当前解释器没有 C++ 后端。"
                  "请用 --exe 指定包含对拍入口的 PmxStudio.exe。")
            return 2
        print("未找到打包后的程序，改在当前解释器内对拍。")
        return run_cli(argv, in_process=True, require_out=require_out)

    out = args.out
    temporary = out is None
    if temporary:
        fd, name = tempfile.mkstemp(prefix="pmx_verify_", suffix=".json")
        os.close(fd)
        out = Path(name)
    command = [str(exe), "--verify-backend", str(args.model.resolve()),
               "--runs", str(args.runs), "--out", str(out)]
    print("调用打包程序对拍：%s" % exe)
    try:
        completed = subprocess.run(command, timeout=900)
    except subprocess.TimeoutExpired:
        print("打包程序对拍超时（900 s）")
        if temporary:
            out.unlink(missing_ok=True)
        return 2
    report = None
    if out.is_file():
        try:
            report = json.loads(out.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print("读取对拍报告失败：%s" % exc)
    if temporary:
        out.unlink(missing_ok=True)
    if report is None:
        print("打包程序未生成报告（退出码 %s）" % completed.returncode)
        return 2
    _print_report(report)
    return 0 if report.get("ok") else 1


def main():
    return run_cli()


if __name__ == "__main__":
    sys.exit(main())
