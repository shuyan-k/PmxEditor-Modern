# -*- coding: utf-8 -*-
"""生成测试用 PMX 模型（含骨骼/材质/形态/刚体/关节）与贴图。"""
import os, sys, math
import numpy as np
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))
from pmxeditor.pmx import (PMXModel, Bone, Material, Morph, RigidBody, Joint, DisplayFrame,
                 IK, IKLink, BF_IK, BF_TAIL_INDEX, BF_ROTATABLE, BF_TRANSLATABLE,
                 BF_VISIBLE, BF_ENABLED, BF_INHERIT_ROT, MF_EDGE,
                 MF_DOUBLE_SIDED, MF_GROUND_SHADOW)
from PIL import Image, ImageDraw

OUT = os.path.dirname(os.path.abspath(__file__))

def make_tex():
    im = Image.new("RGB", (256, 256), (210, 190, 170))
    d = ImageDraw.Draw(im)
    for y in range(0, 256, 32):
        for x in range(0, 256, 32):
            if (x // 32 + y // 32) % 2 == 0:
                d.rectangle([x, y, x + 31, y + 31], fill=(170, 150, 200))
    d.text((8, 8), "TEX", fill=(20, 20, 20))
    im.save(os.path.join(OUT, "tex_body.png"))
    sph = Image.new("RGB", (256, 128), (30, 30, 60))
    d2 = ImageDraw.Draw(sph)
    for y in range(0, 128, 8):
        d2.line([(0, y), (255, y)], fill=(60 + y, 60, 120))
    sph.save(os.path.join(OUT, "sph.png"))


def box(cx, cy, cz, sx, sy, sz, uv_off=(0.0, 0.0)):
    """返回 8 顶点 + 12 三角形（36 索引）。"""
    hs = np.array([sx, sy, sz]) * 0.5
    c = np.array([cx, cy, cz])
    v = []
    for sz_ in (-1, 1):
        for sy_ in (-1, 1):
            for sx_ in (-1, 1):
                v.append(c + hs * np.array([sx_, sy_, sz_]))
    v = np.array(v, np.float32)
    uv = np.array([[0.02, 0.02], [0.48, 0.02], [0.02, 0.48], [0.48, 0.48]] * 2, np.float32) + np.array(uv_off, np.float32)
    f = [
        (0, 1, 3), (0, 3, 2),   # back
        (4, 6, 7), (4, 7, 5),   # front
        (0, 4, 5), (0, 5, 1),   # bottom
        (2, 3, 7), (2, 7, 6),   # top
        (0, 2, 6), (0, 6, 4),   # left
        (1, 5, 7), (1, 7, 3),   # right
    ]
    return v, uv, np.array(f, np.int32).reshape(-1)


def build(with_softbody=False, name="TestModel"):
    m = PMXModel()
    m.name = name
    m.name_en = "TestModel"
    m.comment = "测试模型 comment"
    m.encoding = 1
    m.textures = ["tex_body.png", "sph.png"]

    vt, ut, ft = box(0, 1.6, 0, 1.2, 1.2, 0.6)      # 躯干
    vh, uh, fh = box(0, 2.75, 0, 0.75, 0.7, 0.7)     # 头
    va, ua, fa = box(1.5, 1.9, 0, 1.6, 0.35, 0.35)   # 右臂
    n0 = 0; n1 = len(vt); n2 = len(vt) + len(vh)
    m.v_pos = np.vstack([vt, vh, va]).astype(np.float32)
    m.v_uv = np.vstack([ut, uh, ua]).astype(np.float32)
    m.indices = np.concatenate([ft, fh + n1, fa + n2]).astype(np.int32)
    nv = len(m.v_pos)
    # 法线用球面近似
    nrm = m.v_pos - m.v_pos.mean(axis=0)
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-9
    m.v_nrm = nrm.astype(np.float32)
    m.v_edge = np.ones((nv,), np.float32) * 1.0
    m.v_wtype = np.zeros((nv,), np.uint8)
    m.v_bones = np.full((nv, 4), -1, np.int32)
    m.v_weights = np.zeros((nv, 4), np.float32)
    m.v_sdef = np.zeros((nv, 9), np.float32)
    # 躯干 -> BDEF1 上半身(1)；头 -> BDEF1 頭(2)；手臂 -> BDEF2 腕/ひじ
    for i in range(nv):
        if n1 <= i < n2:
            m.v_bones[i, 0] = 2; m.v_weights[i, 0] = 1.0
        elif i >= n2:
            m.v_wtype[i] = 1
            m.v_bones[i, 0] = 3; m.v_bones[i, 1] = 4
            m.v_weights[i, 0] = 0.5; m.v_weights[i, 1] = 0.5
        else:
            m.v_bones[i, 0] = 1; m.v_weights[i, 0] = 1.0

    base = BF_ROTATABLE | BF_TRANSLATABLE | BF_VISIBLE | BF_ENABLED
    b0 = Bone(name="センター", name_en="center", pos=[0, 1.0, 0], parent=-1, flags=base)
    b1 = Bone(name="上半身", name_en="upper body", pos=[0, 1.1, 0], parent=0, flags=base)
    b2 = Bone(name="頭", name_en="head", pos=[0, 2.4, 0], parent=1, flags=base)
    b3 = Bone(name="右腕", name_en="arm", pos=[0.6, 1.9, 0], parent=1, flags=base)
    b4 = Bone(name="右ひじ", name_en="elbow", pos=[1.9, 1.9, 0], parent=3, flags=base)
    b5 = Bone(name="右腕ＩＫ", name_en="arm ik", pos=[2.7, 1.9, 0], parent=1, flags=base | BF_IK)
    b5.ik = IK(target=4, loop=40, angle=0.5, links=[IKLink(bone=3, limited=False)])
    b6 = Bone(name="付与テスト", name_en="append", pos=[0, 3.2, 0], parent=2,
              flags=base | BF_INHERIT_ROT, append_parent=2, append_ratio=0.5)
    m.bones = [b0, b1, b2, b3, b4, b5, b6]

    mt0 = Material(name="体", name_en="body", texture=0, sphere=1, sphere_mode=1,
                   draw_flags=MF_DOUBLE_SIDED | MF_GROUND_SHADOW | MF_EDGE, face_count=36 * 2)
    mt1 = Material(name="顔", name_en="face", texture=0, toon_shared=1, toon=1,
                   draw_flags=MF_EDGE, face_count=36)
    m.materials = [mt0, mt1]

    mv = Morph(name="スマイル", name_en="smile", panel=3, type=1,
               offsets=[{"vertex": 3, "offset": [0.0, 0.35, 0.0]},
                        {"vertex": 9, "offset": [0.25, 0.0, 0.0]}])
    mb = Morph(name="首振り", name_en="nod", panel=4, type=2,
               offsets=[{"bone": 2, "move": [0, 0, 0], "rot": [0.0, 0.0, 0.3827, 0.9239]}])
    mm = Morph(name="赤面", name_en="blush", panel=1, type=8,
               offsets=[{"material": 1, "calc": 1, "diffuse": [0.3, 0.0, 0.0, 0.0]}])
    mu = Morph(name="UVずらし", name_en="uv", panel=4, type=3,
               offsets=[{"vertex": 2, "offset": [0.1, 0.0, 0.0, 0.0]}])
    mg = Morph(name="グループ", name_en="group", panel=0, type=0,
               offsets=[{"morph": 0, "ratio": 1.0}])
    # 翻转（PMX 类型 9，语义 1-w）与附加 UV1（类型 4，独立通道）
    mf = Morph(name="ウインク", name_en="wink", panel=1, type=9,
               offsets=[{"morph": 0, "ratio": 1.0}])
    ma = Morph(name="追加UV", name_en="adduv", panel=4, type=4,
               offsets=[{"vertex": 2, "offset": [0.05, 0.0, 0.0, 0.0]}])
    m.morphs = [mv, mb, mm, mu, mg, mf, ma]

    m.frames = [DisplayFrame(name="Root", name_en="Root", special=1,
                             items=[(0, 0), (0, 1), (0, 2), (1, 0)]),
                DisplayFrame(name="表情", name_en="exp", special=0,
                             items=[(1, 0), (1, 1)])]

    r0 = RigidBody(name="頭剛体", bone=2, group=0, mask=0xFFFF, shape=0,
                   size=[0.35, 0.35, 0.35], pos=[0, 2.75, 0], mass=1.0, mode=0)
    r1 = RigidBody(name="腕剛体A", bone=3, group=1, mask=0xFFFE, shape=1,
                   size=[0.8, 0.2, 0.2], pos=[1.2, 1.9, 0], mass=2.0, mode=1)
    r2 = RigidBody(name="腕剛体B", bone=4, group=1, mask=0xFFFE, shape=2,
                   size=[0.15, 0.6, 0.15], pos=[2.2, 1.9, 0], mass=1.5, mode=1)
    m.rigid = [r0, r1, r2]
    m.joints = [Joint(name="腕ジョイント", type=0, rigid_a=1, rigid_b=2,
                      pos=[1.9, 1.9, 0], rot=[0, 0, 0],
                      min_loc=[-0.1] * 3, max_loc=[0.1] * 3,
                      min_rot=[-0.5] * 3, max_rot=[0.5] * 3),
                Joint(name="固定", type=1, rigid_a=0, rigid_b=1, pos=[0, 1.9, 0])]
    return m


if __name__ == "__main__":
    make_tex()
    m = build()
    p = os.path.join(OUT, "test_model.pmx")
    from pmxeditor.pmx import save_pmx, load_pmx, validate_model, model_stats
    save_pmx(m, p)
    m2 = load_pmx(p)
    print("roundtrip:", model_stats(m2))
    print("validate:", validate_model(m2)[:6] if isinstance(validate_model(m2), list) else validate_model(m2))
    print("saved", p, os.path.getsize(p))
