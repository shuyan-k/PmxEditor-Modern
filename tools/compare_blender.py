# -*- coding: utf-8 -*-
"""把 Blender 参考结果的骨骼世界矩阵与本项目 Pose 逐个对拍。

    .\build\python\python.exe tools\compare_blender.py tests\blender_ref.npz "<model.pmx>"
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import numpy as np

from pmxeditor.pmx import load_pmx
from pmxeditor.skinning import Pose
from pmxeditor.vmd import load_vmd

# 我们 Y 轴朝上；mmd_tools 导入后 Z 轴朝上，坐标映射 (x, y, z) -> (x, -z, y)
# mmd_tools 把 (x, y, z) 映射成 (x, z, y)（交换 Y/Z），实测得出，不是旋转而是换轴
RZ = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]])


def main():
    npz_path, model_path = sys.argv[1], sys.argv[2]
    ref = np.load(npz_path, allow_pickle=True)
    frames = [int(f) for f in ref["frames"]]
    bones = ref["bones"]
    names = [str(n) for n in ref["names"]]

    model = load_pmx(model_path)
    pose = Pose(model)
    index = {name: i for i, name in enumerate(names)}
    pairs = [(i, index[b.name]) for i, b in enumerate(model.bones) if b.name in index]
    print("骨骼匹配 %d / 模型 %d / Blender %d" % (len(pairs), len(model.bones), len(names)))
    if not pairs:
        return

    ours_i = np.array([p[0] for p in pairs])
    ref_i = np.array([p[1] for p in pairs])

    # 用静止姿势确定映射方向是否要额外转置
    world0 = pose.world()
    cands = {
        "R*W*R^T": lambda m: RZ @ m @ RZ.T,
        "R*W": lambda m: RZ @ m,
        "W*R^T": lambda m: m @ RZ.T,
    }
    best = None
    for tag, fn in cands.items():
        errs = []
        for oi, ri in zip(ours_i, ref_i):
            m = fn(world0[oi])
            errs.append(np.linalg.norm(m[:3, 3] - bones[0][ri][:3, 3]))
        err = float(np.median(errs))
        print("映射 %-8s 静止中位误差 %.4f" % (tag, err))
        if best is None or err < best[1]:
            best = (tag, err, fn)
    tag, _err, fn = best
    print("采用映射 %s" % tag)

    vmd_path = sys.argv[3]
    action = load_vmd(vmd_path)
    by_name = {b.name: i for i, b in enumerate(model.bones)}
    for f in frames:
        for bone_name, (pos, rot) in action.frame_bones(f).items():
            i = by_name.get(bone_name)
            if i is not None:
                pose.base_trans[i] = pos
                pose.base_rot[i] = rot
        pose.apply({}, model.morphs)
        pose.world_update()
        pose.solve_ik(0)
        world = pose.world()
        errs, worst = [], None
        for oi, ri in zip(ours_i, ref_i):
            m = fn(world[oi])
            d = float(np.linalg.norm(m[:3, 3] - bones[frames.index(f)][ri][:3, 3]))
            errs.append(d)
            if worst is None or d > worst[0]:
                worst = (d, model.bones[oi].name)
        errs = np.array(errs)
        print("帧 %3d 位移误差 中位=%.4f 均值=%.4f p95=%.4f 最大=%.3f (%s)"
              % (f, np.median(errs), errs.mean(), np.percentile(errs, 95),
                 errs.max(), worst[1]))


main()


