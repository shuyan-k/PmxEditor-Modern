"""VMD 动作文件读取。

只解析预览需要的两段：骨骼关键帧与形态关键帧。
格式参考 Vocaloid Motion Data 0002（头部 30 字节 + 20 字节模型名）。

已知限制：VMD 的贝塞尔插值曲线（每根骨骼 64 字节）暂未使用，
关键帧之间按线性/球面线性插值，因此与 MMD 的缓入缓出会有细微差异。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

_MAGIC_V2 = b"Vocaloid Motion Data 0002\x00"
_NAME_LEN = 15
_BONE_RECORD = 111          # 15 + 4 + 12 + 16 + 64
_MORPH_RECORD = 23          # 15 + 4 + 4


def _name(raw: bytes) -> str:
    text = raw.split(b"\x00", 1)[0]
    for enc in ("cp932", "utf-8"):
        try:
            return text.decode(enc)
        except UnicodeDecodeError:
            continue
    return text.decode("cp932", errors="replace")


def _lerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    return a + (b - a) * t


def _slerp(a: np.ndarray, b: np.ndarray, t: float) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    dot = float(np.dot(a, b))
    if dot < 0.0:                      # 取近端，避免绕远路
        b = -b
        dot = -dot
    if dot > 0.9995:
        out = a + (b - a) * t
    else:
        theta = np.arccos(max(-1.0, min(1.0, dot)))
        sin_theta = np.sin(theta)
        out = (np.sin((1.0 - t) * theta) * a + np.sin(t * theta) * b) / sin_theta
    norm = float(np.linalg.norm(out))
    return out / norm if norm > 1e-12 else a


@dataclass
class BoneTrack:
    """一根骨骼的关键帧（按帧号升序）。"""

    keys: List[Tuple[int, np.ndarray, np.ndarray]] = field(default_factory=list)

    def sample(self, frame: float) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        if not self.keys:
            return None
        if frame <= self.keys[0][0]:
            _f, pos, rot = self.keys[0]
            return pos, rot
        if frame >= self.keys[-1][0]:
            _f, pos, rot = self.keys[-1]
            return pos, rot
        lo, hi = 0, len(self.keys) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.keys[mid][0] <= frame:
                lo = mid
            else:
                hi = mid
        f0, p0, r0 = self.keys[lo]
        f1, p1, r1 = self.keys[hi]
        span = float(f1 - f0) or 1.0
        t = (float(frame) - f0) / span
        return _lerp(p0, p1, t), _slerp(r0, r1, t)


@dataclass
class MorphTrack:
    keys: List[Tuple[int, float]] = field(default_factory=list)

    def sample(self, frame: float) -> float:
        if not self.keys:
            return 0.0
        if frame <= self.keys[0][0]:
            return self.keys[0][1]
        if frame >= self.keys[-1][0]:
            return self.keys[-1][1]
        for (f0, w0), (f1, w1) in zip(self.keys, self.keys[1:]):
            if f0 <= frame <= f1:
                span = float(f1 - f0) or 1.0
                t = (float(frame) - f0) / span
                return w0 + (w1 - w0) * t
        return self.keys[-1][1]


@dataclass
class Vmd:
    path: str = ""
    model_name: str = ""
    bones: Dict[str, BoneTrack] = field(default_factory=dict)
    morphs: Dict[str, MorphTrack] = field(default_factory=dict)

    @property
    def max_frame(self) -> int:
        top = 0
        for track in self.bones.values():
            if track.keys:
                top = max(top, track.keys[-1][0])
        for track in self.morphs.values():
            if track.keys:
                top = max(top, track.keys[-1][0])
        return top

    def frame_bones(self, frame: float) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
        out = {}
        for name, track in self.bones.items():
            got = track.sample(frame)
            if got is not None:
                out[name] = got
        return out

    def frame_morphs(self, frame: float) -> Dict[str, float]:
        return {name: track.sample(frame) for name, track in self.morphs.items()}


def load_vmd(path: str) -> Vmd:
    with open(path, "rb") as handle:
        data = handle.read()
    if not data.startswith(_MAGIC_V2):
        raise ValueError("不是 VMD 动作文件（Vocaloid Motion Data 0002）")
    offset = 30
    name_len = 20
    model_name = _name(data[offset:offset + name_len])
    offset += name_len
    vmd = Vmd(path=path, model_name=model_name)

    def read_u32(pos: int) -> int:
        if pos + 4 > len(data):
            raise ValueError("VMD 文件不完整")
        return struct.unpack_from("<I", data, pos)[0]

    count = read_u32(offset)
    offset += 4
    for _ in range(count):
        if offset + _BONE_RECORD > len(data):
            raise ValueError("VMD 骨骼帧数据不完整")
        bone_name = _name(data[offset:offset + _NAME_LEN])
        offset += _NAME_LEN
        frame = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        px, py, pz = struct.unpack_from("<3f", data, offset)
        offset += 12
        qx, qy, qz, qw = struct.unpack_from("<4f", data, offset)
        offset += 16
        offset += 64                                  # 插值曲线暂不使用
        track = vmd.bones.setdefault(bone_name, BoneTrack())
        track.keys.append((int(frame),
                           np.array([px, py, pz], dtype=np.float32),
                           np.array([qx, qy, qz, qw], dtype=np.float32)))
    for track in vmd.bones.values():
        track.keys.sort(key=lambda item: item[0])

    if offset + 4 <= len(data):
        count = read_u32(offset)
        offset += 4
        for _ in range(count):
            if offset + _MORPH_RECORD > len(data):
                raise ValueError("VMD 形态帧数据不完整")
            morph_name = _name(data[offset:offset + _NAME_LEN])
            offset += _NAME_LEN
            frame = struct.unpack_from("<I", data, offset)[0]
            offset += 4
            weight = struct.unpack_from("<f", data, offset)[0]
            offset += 4
            track = vmd.morphs.setdefault(morph_name, MorphTrack())
            track.keys.append((int(frame), float(weight)))
        for track in vmd.morphs.values():
            track.keys.sort(key=lambda item: item[0])

    # 相机 / 光照 / 阴影 / IK 段与预览无关，忽略。
    return vmd
