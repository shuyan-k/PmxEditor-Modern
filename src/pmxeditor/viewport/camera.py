"""轨道相机：目标点 + 球面角 + 距离。"""
from __future__ import annotations

import math
import numpy as np


class OrbitCamera:
    def __init__(self):
        self.target = np.array([0.0, 10.0, 0.0], dtype=np.float32)
        self.distance = 40.0
        self.yaw = math.pi
        self.pitch = 0.18
        self.fov = 38.0
        self.near = 0.1
        self.far = 4000.0

    def eye(self):
        cp = math.cos(self.pitch)
        return self.target + self.distance * np.array(
            [cp * math.sin(self.yaw), math.sin(self.pitch), cp * math.cos(self.yaw)],
            dtype=np.float32)

    def view(self):
        eye = self.eye()
        f = self.target - eye
        f /= max(1e-6, np.linalg.norm(f))
        up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        if abs(float(np.dot(f, up))) > 0.999:
            up = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        s = np.cross(f, up)
        s /= max(1e-6, np.linalg.norm(s))
        u = np.cross(s, f)
        m = np.eye(4, dtype=np.float32)
        m[0, :3] = s
        m[1, :3] = u
        m[2, :3] = -f
        m[0, 3] = -float(np.dot(s, eye))
        m[1, 3] = -float(np.dot(u, eye))
        m[2, 3] = float(np.dot(f, eye))
        return m

    def projection(self, aspect):
        f = 1.0 / math.tan(math.radians(self.fov) * 0.5)
        m = np.zeros((4, 4), dtype=np.float32)
        m[0, 0] = f / max(0.01, aspect)
        m[1, 1] = f
        m[2, 2] = (self.far + self.near) / (self.near - self.far)
        m[2, 3] = (2 * self.far * self.near) / (self.near - self.far)
        m[3, 2] = -1.0
        return m

    def right(self):
        view = self.view()
        return view[0, :3].copy()

    def up_vec(self):
        return self.view()[1, :3].copy()

    def project(self, p, width, height):
        eye = self.eye()
        v = self.view()
        proj = self.projection(max(0.01, width / max(1, height)))
        clip = proj @ v @ np.array([p[0], p[1], p[2], 1.0], dtype=np.float32)
        if clip[3] <= 1e-5:
            return None
        ndc = clip[:3] / clip[3]
        return ((ndc[0] * 0.5 + 0.5) * width, (1.0 - (ndc[1] * 0.5 + 0.5)) * height)

    def fit(self, lo, hi):
        lo = np.asarray(lo, dtype=np.float32)
        hi = np.asarray(hi, dtype=np.float32)
        center = (lo + hi) * 0.5
        size = float(np.linalg.norm(hi - lo))
        self.target = center
        self.distance = max(1.0, size * 1.45)
        self.pitch = 0.16
        self.yaw = math.pi
