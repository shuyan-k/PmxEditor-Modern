"""VMD 动作文件读写。

解析预览需要的骨骼段与形态段，并支持关键帧编辑与另存：
- 骨骼关键帧带 64 字节贝塞尔插值参数（X/Y/Z/旋转各一条），采样时用它们做缓动；
- 关键帧可以插入/覆盖/删除，写回的文件只包含骨骼与形态两段
  （相机、光照、阴影、IK 段在读取时丢弃，保存时写 0 条）。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

_MAGIC = b"Vocaloid Motion Data 0002"
_HEADER = 30                 # 头部固定 30 字节（魔数只有 26 字节，补 0）
_NAME_LEN = 15
_BONE_RECORD = 111           # 15 + 4 + 12 + 16 + 64
_MORPH_RECORD = 23           # 15 + 4 + 4

# 一条曲线的四个控制点：(x1, y1, x2, y2)，取值 0..127；y=x 即线性。
LINEAR_CURVE = (0.0, 0.0, 127.0, 127.0)
DEFAULT_CURVES = (LINEAR_CURVE, LINEAR_CURVE, LINEAR_CURVE, LINEAR_CURVE)


def _name(raw: bytes) -> str:
    text = raw.split(b"\x00", 1)[0]
    for enc in ("cp932", "utf-8"):
        try:
            return text.decode(enc)
        except UnicodeDecodeError:
            continue
    return text.decode("cp932", errors="replace")


def _encode_name(name: str, size: int) -> bytes:
    return name.encode("cp932", errors="replace")[:size].ljust(size, b"\x00")


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


def is_linear_curve(curve) -> bool:
    x1, y1, x2, y2 = curve
    return abs(y1 - x1) < 0.5 and abs(y2 - x2) < 0.5


def bezier_ease(curve, t: float) -> float:
    """按三次贝塞尔把线性时间 t 映射成缓动时间（曲线两端固定为 (0,0)-(1,1)）。"""
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    if is_linear_curve(curve):
        return t
    x1, y1, x2, y2 = [float(v) / 127.0 for v in curve]
    lo, hi = 0.0, 1.0
    for _ in range(24):                # 二分求 x(u)=t 的参数 u
        mid = (lo + hi) * 0.5
        u = 1.0 - mid
        bx = 3.0 * u * u * mid * x1 + 3.0 * u * mid * mid * x2 + mid ** 3
        if bx < t:
            lo = mid
        else:
            hi = mid
    s = (lo + hi) * 0.5
    u = 1.0 - s
    return 3.0 * u * u * s * y1 + 3.0 * u * s * s * y2 + s ** 3


@dataclass
class BoneTrack:
    """一根骨骼的关键帧：(帧号, 位移, 四元数, 四条贝塞尔曲线)，按帧号升序。"""

    keys: List[Tuple[int, np.ndarray, np.ndarray, tuple]] = field(default_factory=list)

    def sample(self, frame: float) -> Optional[Tuple[np.ndarray, np.ndarray]]:
        if not self.keys:
            return None
        if frame <= self.keys[0][0]:
            _f, pos, rot, _c = self.keys[0]
            return pos, rot
        if frame >= self.keys[-1][0]:
            _f, pos, rot, _c = self.keys[-1]
            return pos, rot
        lo, hi = 0, len(self.keys) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.keys[mid][0] <= frame:
                lo = mid
            else:
                hi = mid
        f0, p0, r0, curves = self.keys[lo]
        _f1, p1, r1, _c1 = self.keys[hi]
        span = float(self.keys[hi][0] - f0) or 1.0
        t = (float(frame) - f0) / span
        curves = curves or DEFAULT_CURVES
        pos = np.empty(3, dtype=np.float32)
        for axis in range(3):
            k = bezier_ease(curves[axis], t)
            pos[axis] = p0[axis] + (p1[axis] - p0[axis]) * k
        return pos, _slerp(r0, r1, bezier_ease(curves[3], t))

    def set_key(self, frame: int, pos, rot, curves=None) -> None:
        entry = (int(frame), np.asarray(pos, dtype=np.float32),
                 np.asarray(rot, dtype=np.float32),
                 tuple(curves) if curves else DEFAULT_CURVES)
        for i, key in enumerate(self.keys):
            if key[0] == frame:
                self.keys[i] = entry
                return
            if key[0] > frame:
                self.keys.insert(i, entry)
                return
        self.keys.append(entry)

    def remove_key(self, frame: int) -> bool:
        for i, key in enumerate(self.keys):
            if key[0] == frame:
                del self.keys[i]
                return True
        return False


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

    def set_key(self, frame: int, weight: float) -> None:
        for i, key in enumerate(self.keys):
            if key[0] == frame:
                self.keys[i] = (int(frame), float(weight))
                return
            if key[0] > frame:
                self.keys.insert(i, (int(frame), float(weight)))
                return
        self.keys.append((int(frame), float(weight)))

    def remove_key(self, frame: int) -> bool:
        for i, key in enumerate(self.keys):
            if key[0] == frame:
                del self.keys[i]
                return True
        return False


@dataclass
class Vmd:
    path: str = ""
    model_name: str = ""
    bones: Dict[str, BoneTrack] = field(default_factory=dict)
    morphs: Dict[str, MorphTrack] = field(default_factory=dict)
    edited: bool = False

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

    def key_frames(self) -> List[int]:
        """所有轨道出现过的帧号（时间轴上画标记用）。"""
        frames = set()
        for track in self.bones.values():
            frames.update(k[0] for k in track.keys)
        for track in self.morphs.values():
            frames.update(k[0] for k in track.keys)
        return sorted(frames)

    def frame_keys(self, name: str, frame: int) -> Dict[str, bool]:
        """当前帧上该骨骼/形态是否已有关键帧（界面提示用）。"""
        bone = self.bones.get(name)
        return {"bone": bool(bone and any(k[0] == frame for k in bone.keys))}

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
    if not data.startswith(_MAGIC):
        raise ValueError("不是 VMD 动作文件（Vocaloid Motion Data 0002）")
    offset = _HEADER
    vmd = Vmd(path=path, model_name=_name(data[offset:offset + 20]))
    offset += 20

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
        frame = struct.unpack_from("<I", data, offset + _NAME_LEN)[0]
        px, py, pz = struct.unpack_from("<3f", data, offset + _NAME_LEN + 4)
        qx, qy, qz, qw = struct.unpack_from("<4f", data, offset + _NAME_LEN + 16)
        raw = data[offset + _NAME_LEN + 32:offset + _BONE_RECORD]
        # 64 字节按 4 个控制点分组，每个控制点一行 (X, Y, Z, 旋转)；
        # 后面 48 字节是同一组数值的重复，忽略。
        curves = tuple(tuple(float(raw[i * 4 + c]) for i in range(4)) for c in range(4))
        track = vmd.bones.setdefault(bone_name, BoneTrack())
        track.keys.append((int(frame),
                           np.array([px, py, pz], dtype=np.float32),
                           np.array([qx, qy, qz, qw], dtype=np.float32),
                           curves))
        offset += _BONE_RECORD
    for track in vmd.bones.values():
        track.keys.sort(key=lambda item: item[0])

    if offset + 4 <= len(data):
        count = read_u32(offset)
        offset += 4
        for _ in range(count):
            if offset + _MORPH_RECORD > len(data):
                raise ValueError("VMD 形态帧数据不完整")
            morph_name = _name(data[offset:offset + _NAME_LEN])
            frame = struct.unpack_from("<I", data, offset + _NAME_LEN)[0]
            weight = struct.unpack_from("<f", data, offset + _NAME_LEN + 4)[0]
            track = vmd.morphs.setdefault(morph_name, MorphTrack())
            track.keys.append((int(frame), float(weight)))
            offset += _MORPH_RECORD
        for track in vmd.morphs.values():
            track.keys.sort(key=lambda item: item[0])

    # 相机 / 光照 / 阴影 / IK 段与预览无关，忽略。
    return vmd


def save_vmd(vmd: Vmd, path: str, model_name: Optional[str] = None) -> None:
    """把动作写回 VMD（只含骨骼与形态段，其它段写 0 条）。"""
    out = bytearray(_MAGIC + b"\x00" * (_HEADER - len(_MAGIC)))
    out += _encode_name(model_name if model_name is not None else vmd.model_name, 20)
    bones = []
    for bone_name, track in vmd.bones.items():
        for frame, pos, rot, curves in track.keys:
            record = bytearray(_encode_name(bone_name, _NAME_LEN))
            record += struct.pack("<I", int(frame))
            record += struct.pack("<3f", *[float(v) for v in pos])
            record += struct.pack("<4f", *[float(v) for v in rot])
            curves = curves or DEFAULT_CURVES
            block = bytearray(16)
            for c in range(4):
                for i in range(4):
                    block[i * 4 + c] = max(0, min(255, int(round(float(curves[c][i])))))
            record += bytes(block) * 4
            bones.append(bytes(record))
    out += struct.pack("<I", len(bones))
    for record in bones:
        out += record
    morphs = []
    for morph_name, track in vmd.morphs.items():
        for frame, weight in track.keys:
            record = bytearray(_encode_name(morph_name, _NAME_LEN))
            record += struct.pack("<I", int(frame))
            record += struct.pack("<f", float(weight))
            morphs.append(bytes(record))
    out += struct.pack("<I", len(morphs))
    for record in morphs:
        out += record
    for _ in range(4):                 # 相机 / 光照 / 阴影 / IK
        out += struct.pack("<I", 0)
    with open(path, "wb") as handle:
        handle.write(bytes(out))
    vmd.path = path
    vmd.edited = False
