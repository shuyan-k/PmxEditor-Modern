"""几何小工具。"""
from __future__ import annotations

import math
import numpy as np
from ..skinning import rigid_euler_quat


def _rigid_quat(rot):
    """刚体/关节旋转：PMX 存的就是弧度，且采用 MMD 的 YXZ 顺序。"""
    return rigid_euler_quat(float(rot[0]), float(rot[1]), float(rot[2]))


def _line_geom(segments):
    verts = []
    colors = []
    for p0, p1, c in segments:
        verts.extend([p0, p1])
        colors.extend([c, c])
    return np.array(verts, dtype=np.float32).reshape(-1, 3), \
        np.array(colors, dtype=np.float32).reshape(-1, 3)


def _mesh_winding(pos, nrm, idx):
    """保证三角形绕序朝外；实体叠加层用背面剔除做前后两次透明绘制。"""
    tri = np.asarray(idx, dtype=np.int32).reshape(-1, 3)
    p = np.asarray(pos, dtype=np.float32)
    n = np.asarray(nrm, dtype=np.float32)
    a, b, c = p[tri[:, 0]], p[tri[:, 1]], p[tri[:, 2]]
    face = np.cross(b - a, c - a)
    # 球体极点处相邻顶点重合，会产生零面积三角形；直接丢弃，
    # 既避免退化绘制，也避免法线对拍时被 0 点积误判为朝向错误
    valid = np.linalg.norm(face, axis=1) > 1e-10
    tri, face = tri[valid], face[valid]
    avg = n[tri[:, 0]] + n[tri[:, 1]] + n[tri[:, 2]]
    flip = (face * avg).sum(axis=1) < 0.0
    if flip.any():
        tri[flip] = tri[flip][:, [0, 2, 1]]
    return np.asarray(pos, np.float32), np.asarray(nrm, np.float32), tri.reshape(-1)


def box_mesh(hx, hy, hz):
    """以原点为中心的盒体；PMX 的 size 是半边长。"""
    hx, hy, hz = abs(float(hx)), abs(float(hy)), abs(float(hz))
    faces = (
        ((0, 0, 1), ((-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz))),
        ((0, 0, -1), ((-hx, -hy, -hz), (-hx, hy, -hz), (hx, hy, -hz), (hx, -hy, -hz))),
        ((1, 0, 0), ((hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz), (hx, -hy, hz))),
        ((-1, 0, 0), ((-hx, -hy, -hz), (-hx, -hy, hz), (-hx, hy, hz), (-hx, hy, -hz))),
        ((0, 1, 0), ((-hx, hy, -hz), (-hx, hy, hz), (hx, hy, hz), (hx, hy, -hz))),
        ((0, -1, 0), ((-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz))),
    )
    pos, nrm, idx = [], [], []
    for normal, quad in faces:
        base = len(pos)
        pos.extend(quad)
        nrm.extend([normal] * 4)
        idx.extend((base, base + 1, base + 2, base, base + 2, base + 3))
    return _mesh_winding(pos, nrm, idx)


def sphere_mesh(radius, segments=18, rings=12):
    """UV 球；法线直接取归一化坐标。"""
    r = abs(float(radius))
    pos, nrm, idx = [], [], []
    for iy in range(rings + 1):
        theta = math.pi * iy / rings
        y = math.cos(theta) * r
        rr = math.sin(theta) * r
        for ix in range(segments):
            phi = 2.0 * math.pi * ix / segments
            p = (rr * math.cos(phi), y, rr * math.sin(phi))
            pos.append(p)
            if r > 1e-9:
                nrm.append((p[0] / r, p[1] / r, p[2] / r))
            else:
                nrm.append((0.0, 1.0, 0.0))
    for iy in range(rings):
        for ix in range(segments):
            a = iy * segments + ix
            b = iy * segments + (ix + 1) % segments
            c = (iy + 1) * segments + ix
            d = (iy + 1) * segments + (ix + 1) % segments
            idx.extend((a, c, b, b, c, d))
    return _mesh_winding(pos, nrm, idx)


def capsule_mesh(radius, height, segments=18, cap_rings=5):
    """沿 Y 轴的胶囊：半径 radius，圆柱段高度 height，对应 PMX shape=2。

    与 Bullet 的 btCapsuleShape(radius, height) 保持一致，总长为 height + 2r。
    """
    r = abs(float(radius))
    half = abs(float(height)) * 0.5
    # 底部极点 -> 底部半球 -> 圆柱下沿 -> 圆柱上沿 -> 顶部半球 -> 顶部极点
    profile = []
    for i in range(cap_rings + 1):
        a = -0.5 * math.pi + (0.5 * math.pi) * i / cap_rings
        profile.append((-half + r * math.sin(a), math.cos(a), math.sin(a)))
    for i in range(cap_rings + 1):
        a = 0.5 * math.pi * i / cap_rings
        profile.append((half + r * math.sin(a), math.cos(a), math.sin(a)))
    pos, nrm, idx = [], [], []
    for y, radial, ny in profile:
        for ix in range(segments):
            phi = 2.0 * math.pi * ix / segments
            pos.append((r * radial * math.cos(phi), y, r * radial * math.sin(phi)))
            nrm.append((radial * math.cos(phi), ny, radial * math.sin(phi)))
    rows = len(profile)
    for iy in range(rows - 1):
        for ix in range(segments):
            a = iy * segments + ix
            b = iy * segments + (ix + 1) % segments
            c = (iy + 1) * segments + ix
            d = (iy + 1) * segments + (ix + 1) % segments
            idx.extend((a, c, b, b, c, d))
    return _mesh_winding(pos, nrm, idx)


def octahedron_mesh(head, tail, side, up2, width):
    """骨骼实心八面体：头、尾 + 中部四边环，三角面用平面法线。"""
    head = np.asarray(head, np.float32)
    tail = np.asarray(tail, np.float32)
    side = np.asarray(side, np.float32)
    up2 = np.asarray(up2, np.float32)
    mid = head + (tail - head) * 0.22
    ring = (mid + side * width, mid + up2 * width,
            mid - side * width, mid - up2 * width)
    pos, nrm, idx = [], [], []
    for i in range(4):
        a, b = ring[i], ring[(i + 1) % 4]
        for tri in ((head, a, b), (tail, b, a)):
            pa, pb, pc = (np.asarray(v, np.float32) for v in tri)
            n = np.cross(pb - pa, pc - pa)
            ln = float(np.linalg.norm(n))
            n = n / ln if ln > 1e-9 else np.array([0.0, 1.0, 0.0], np.float32)
            base = len(pos)
            pos.extend((pa, pb, pc))
            nrm.extend((n, n, n))
            idx.extend((base, base + 1, base + 2))
    return _mesh_winding(pos, nrm, idx)


def _point_segment_dist(px, py, a, b):
    """点到线段的最短距离（屏幕像素），用于骨骼拾取的启发式打分。"""
    ax, ay = float(a[0]), float(a[1])
    bx, by = float(b[0]), float(b[1])
    dx, dy = bx - ax, by - ay
    d2 = dx * dx + dy * dy
    if d2 <= 1e-9:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / d2
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return math.hypot(px - (ax + dx * t), py - (ay + dy * t))
