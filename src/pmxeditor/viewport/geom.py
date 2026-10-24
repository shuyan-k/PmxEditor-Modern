"""几何小工具。"""
from __future__ import annotations

import math
import numpy as np
from ..skinning import euler_to_quat


def _deg_quat(rot):
    """PMX 旋转角为角度制，转为弧度后构造四元数。"""
    k = math.pi / 180.0
    return euler_to_quat(float(rot[0]) * k, float(rot[1]) * k, float(rot[2]) * k)


def _line_geom(segments):
    verts = []
    colors = []
    for p0, p1, c in segments:
        verts.extend([p0, p1])
        colors.extend([c, c])
    return np.array(verts, dtype=np.float32).reshape(-1, 3), \
        np.array(colors, dtype=np.float32).reshape(-1, 3)


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
