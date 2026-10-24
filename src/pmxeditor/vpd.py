# -*- coding: utf-8 -*-
"""VPD（Vocaloid Pose Data）姿态文件的解析、骨骼匹配与应用。"""
from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Sequence, Tuple

import numpy as np

from .skinning import IDENTITY_Q


class VpdError(ValueError):
    """VPD 内容无效。"""


@dataclass(frozen=True)
class VpdBone:
    name: str
    parent: int
    pos: Tuple[float, float, float]
    rot: Tuple[float, float, float, float]
    line: int = 0


@dataclass(frozen=True)
class VpdMorph:
    name: str
    weight: float
    line: int = 0


@dataclass
class VpdFile:
    bones: List[VpdBone] = field(default_factory=list)
    morphs: List[VpdMorph] = field(default_factory=list)
    source: str = ""
    encoding: str = ""


@dataclass
class VpdExport:
    """VPD 导出结果。"""

    path: str
    encoding: str
    bones: int
    morphs: int


@dataclass
class VpdMatch:
    """VPD 骨骼/形态与目标 PMX 的匹配结果。"""

    pairs: List[Tuple[VpdBone, int]] = field(default_factory=list)
    missing: List[VpdBone] = field(default_factory=list)
    renamed: List[Tuple[str, str]] = field(default_factory=list)
    duplicate_vpd: List[str] = field(default_factory=list)
    duplicate_target: List[str] = field(default_factory=list)
    morph_pairs: List[Tuple[VpdMorph, int]] = field(default_factory=list)
    morph_missing: List[VpdMorph] = field(default_factory=list)
    morph_renamed: List[Tuple[str, str]] = field(default_factory=list)
    morph_duplicate_vpd: List[str] = field(default_factory=list)
    morph_duplicate_target: List[str] = field(default_factory=list)

    @property
    def matched(self) -> int:
        return len(self.pairs)

    @property
    def total(self) -> int:
        return len(self.pairs) + len(self.missing)

    @property
    def morph_matched(self) -> int:
        return len(self.morph_pairs)

    @property
    def morph_total(self) -> int:
        return len(self.morph_pairs) + len(self.morph_missing)



def _decode(data: bytes) -> Tuple[str, str]:
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig"), "utf-8"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("cp932", errors="replace"), "cp932"


def _is_ignorable(line: str) -> bool:
    s = line.strip()
    return (not s) or s.startswith("//") or s.startswith("#") \
        or s.startswith(";")


def _strip_comment(line: str) -> str:
    """去掉 VPD 数值行的 ';' 或 '//' 注释。"""
    for marker in (";", "//"):
        pos = line.find(marker)
        if pos >= 0:
            line = line[:pos]
    return line.strip()


def _block_body(lines: Sequence[str], index: int, kind: str,
                line_no: int) -> Tuple[List[Tuple[str, int]], int]:
    """读取块体直到右花括号，返回 (内容行, 行号) 与后续索引。"""
    body: List[Tuple[str, int]] = []
    while index < len(lines):
        content_no = index + 1
        content = _strip_comment(lines[index])
        index += 1
        if not content:
            continue
        if "}" in content:
            head = content.split("}", 1)[0].strip()
            if head:
                body.append((head, content_no))
            return body, index
        body.append((content, content_no))
    raise VpdError("第 %d 行的%s块缺少右花括号" % (line_no, kind))


def _index_value(line: str, line_no: int, what: str) -> int:
    parts = line.replace(",", " ").split()
    if len(parts) != 1:
        raise VpdError("第 %d 行的%s应只有 1 个整数" % (line_no, what))
    try:
        return int(parts[0])
    except ValueError:
        raise VpdError("第 %d 行的%s不是整数" % (line_no, what))


def _numbers(line: str, count: int, what: str, line_no: int) -> List[float]:
    parts = line.replace(",", " ").split()
    if len(parts) != count:
        raise VpdError("第 %d 行的%s应有 %d 个数值，实际为 %d 个"
                       % (line_no, what, count, len(parts)))
    try:
        values = [float(part) for part in parts]
    except ValueError:
        raise VpdError("第 %d 行的%s不是有效数字" % (line_no, what))
    if not all(math.isfinite(value) for value in values):
        raise VpdError("第 %d 行的%s包含非有限数值" % (line_no, what))
    return values


def parse_vpd_text(text: str, source: str = "<memory>",
                   encoding: str = "") -> VpdFile:
    """解析 VPD 文本；兼容带父索引与不带父索引两种骨骼块格式。"""
    lines = text.splitlines()
    bones: List[VpdBone] = []
    morphs: List[VpdMorph] = []
    index = 0
    while index < len(lines):
        raw = lines[index].strip()
        line_no = index + 1
        index += 1
        if _is_ignorable(raw):
            continue
        lower = raw.lower()
        is_bone = lower.startswith("bone")
        is_morph = lower.startswith("morph")
        if "{" not in raw or not (is_bone or is_morph):
            # 文件头、文件名字段和块计数行按兼容处理跳过。
            continue

        name = raw.split("{", 1)[1].strip()
        if not name:
            raise VpdError("第 %d 行的%s名称为空"
                           % (line_no, "骨骼" if is_bone else "形态"))
        kind = "骨骼" if is_bone else "形态"
        body, index = _block_body(lines, index, kind, line_no)

        if is_morph:
            if len(body) != 1:
                raise VpdError("第 %d 行的形态块应只有 1 行权重，实际为 %d 行"
                               % (line_no, len(body)))
            weight = _numbers(body[0][0], 1, "形态权重", body[0][1])[0]
            morphs.append(VpdMorph(name=name, weight=weight, line=line_no))
            continue

        if len(body) == 2:
            # 标准 VPD：省略父骨骼索引。
            parent = -1
            pos_line, pos_no = body[0]
            rot_line, rot_no = body[1]
        elif len(body) == 3:
            parent = _index_value(body[0][0], body[0][1], "父骨骼索引")
            pos_line, pos_no = body[1]
            rot_line, rot_no = body[2]
        else:
            raise VpdError(
                "第 %d 行的骨骼块应有 2 行（位移、四元数）或 3 行"
                "（父索引、位移、四元数），实际为 %d 行"
                % (line_no, len(body)))

        pos = _numbers(pos_line, 3, "位移", pos_no)
        rot = _numbers(rot_line, 4, "四元数", rot_no)
        length = math.sqrt(sum(value * value for value in rot))
        if length < 1e-8:
            raise VpdError("第 %d 行的四元数长度为 0" % rot_no)
        rot = [value / length for value in rot]

        bones.append(VpdBone(
            name=name, parent=parent,
            pos=(pos[0], pos[1], pos[2]),
            rot=(rot[0], rot[1], rot[2], rot[3]),
            line=line_no))

    if not bones and not morphs:
        raise VpdError("没有找到任何骨骼或形态块")
    return VpdFile(bones=bones, morphs=morphs, source=source,
                   encoding=encoding)


def load_vpd(path: str) -> VpdFile:
    data = Path(path).read_bytes()
    text, encoding = _decode(data)
    return parse_vpd_text(text, source=str(path), encoding=encoding)


def _loose_key(name: str) -> str:
    """宽松名称键：统一全/半角、去掉空白和下划线、忽略大小写。"""
    normalized = unicodedata.normalize("NFKC", name)
    normalized = normalized.replace("_", "").replace(" ", "")
    normalized = normalized.replace("\u3000", "")
    return normalized.casefold()


def match_vpd(model, vpd: VpdFile) -> VpdMatch:
    """按名称匹配 VPD 骨骼与形态；优先原名，其次 name_en 与宽松名。"""
    exact_bones = {}
    loose_bones = {}
    exact_morphs = {}
    loose_morphs = {}

    def add(table, key, index):
        if not key:
            return
        bucket = table.setdefault(key, [])
        if index not in bucket:
            bucket.append(index)

    for index, bone in enumerate(model.bones):
        add(exact_bones, bone.name.strip(), index)
        add(exact_bones, (bone.name_en or "").strip(), index)
        add(loose_bones, _loose_key(bone.name), index)
        add(loose_bones, _loose_key(bone.name_en or ""), index)
    for index, morph in enumerate(model.morphs):
        add(exact_morphs, morph.name.strip(), index)
        add(exact_morphs, (morph.name_en or "").strip(), index)
        add(loose_morphs, _loose_key(morph.name), index)
        add(loose_morphs, _loose_key(morph.name_en or ""), index)

    result = VpdMatch()
    seen = set()
    for entry in vpd.bones:
        if entry.name in seen:
            result.duplicate_vpd.append(entry.name)
        seen.add(entry.name)

        hits = exact_bones.get(entry.name.strip(), [])
        if not hits:
            hits = loose_bones.get(_loose_key(entry.name), [])
        if not hits:
            result.missing.append(entry)
            continue
        if len(hits) > 1:
            result.duplicate_target.append(entry.name)
        target = hits[0]
        result.pairs.append((entry, target))
        target_name = model.bones[target].name
        if entry.name != target_name:
            result.renamed.append((entry.name, target_name))

    seen = set()
    for entry in vpd.morphs:
        if entry.name in seen:
            result.morph_duplicate_vpd.append(entry.name)
        seen.add(entry.name)

        hits = exact_morphs.get(entry.name.strip(), [])
        if not hits:
            hits = loose_morphs.get(_loose_key(entry.name), [])
        if not hits:
            result.morph_missing.append(entry)
            continue
        if len(hits) > 1:
            result.morph_duplicate_target.append(entry.name)
        target = hits[0]
        result.morph_pairs.append((entry, target))
        target_name = model.morphs[target].name
        if entry.name != target_name:
            result.morph_renamed.append((entry.name, target_name))
    return result


def apply_vpd_pose(pose, match: VpdMatch, morph_weights=None, morphs=None,
                   solve_ik: bool = True) -> None:
    """用 VPD 替换当前姿态；未匹配骨骼回到初始姿态。

    VPD 含骨骼块时重置全部骨骼；含可匹配形态时用 VPD 权重替换当前形态预览。
    导入后执行一次完整 IK 求解，使 IK 控制器位置与脚部等末端保持一致。
    """
    if match.pairs:
        pose.base_rot[:] = IDENTITY_Q
        pose.base_trans[:] = 0
    for entry, target in match.pairs:
        if 0 <= target < pose.n:
            pose.base_rot[target] = np.asarray(entry.rot, dtype=np.float32)
            pose.base_trans[target] = np.asarray(entry.pos, dtype=np.float32)
    pose.ov_rot.clear()
    pose.ov_trans.clear()
    if morph_weights is not None and morphs is not None and match.morph_pairs:
        morph_weights.clear()
        for entry, target in match.morph_pairs:
            if 0 <= target < len(morphs):
                morph_weights[target] = float(entry.weight)
    pose.apply(morph_weights, morphs)
    pose.world_update()
    if solve_ik:
        if pose.solve_ik(max_loops=0):
            # solve_ik 的 C++ 路径会重新 apply 而不带形态权重，这里补回。
            pose.apply(morph_weights, morphs)
            pose.world_update()


def _format_values(values, digits: int = 6) -> str:
    parts = []
    for value in values:
        value = float(value)
        if abs(value) < 0.5 * (10.0 ** -digits):
            value = 0.0
        parts.append("%.*f" % (digits, value))
    return ",".join(parts)


def build_vpd_text(model, pose, morph_weights=None, model_name: str = "",
                   include_all: bool = False, digits: int = 6):
    """生成标准 VPD 文本，返回 (文本, 骨骼数, 形态数)。

    默认只导出与初始姿态不同的骨骼，以及非零形态权重；`include_all`
    可导出全部骨骼。文本使用 MMD 常见的无父索引两行骨骼块格式。
    """
    entries = []
    count = min(int(pose.n), len(model.bones))
    for index in range(count):
        rot = np.asarray(pose.base_rot[index], dtype=np.float64)
        trans = np.asarray(pose.base_trans[index], dtype=np.float64)
        length = float(np.linalg.norm(rot))
        if not math.isfinite(length) or length < 1e-8:
            rot = np.asarray(IDENTITY_Q, dtype=np.float64)
        else:
            rot = rot / length
        if not np.all(np.isfinite(trans)):
            continue
        moved = bool(np.any(np.abs(trans) > 1e-6))
        turned = (abs(float(rot[3]) - 1.0) > 1e-6
                  or float(np.abs(rot[:3]).max()) > 1e-6)
        if include_all or moved or turned:
            entries.append((index, trans, rot))

    morph_entries = []
    if morph_weights and model.morphs:
        for index, morph in enumerate(model.morphs):
            weight = float(morph_weights.get(index, 0.0))
            if abs(weight) > 1e-4:
                morph_entries.append((morph.name, weight))

    if not model_name:
        model_name = (getattr(model, "name", "") or "model") + ".pmx"

    lines = ["Vocaloid Pose Data file", "",
             "%s;" % model_name, "%d;" % len(entries), ""]
    for seq, (index, trans, rot) in enumerate(entries):
        lines.append("Bone%d{%s" % (seq, model.bones[index].name))
        lines.append("%s;" % _format_values(trans, digits))
        lines.append("%s;" % _format_values(rot, digits))
        lines.append("}")
        lines.append("")
    for seq, (name, weight) in enumerate(morph_entries):
        lines.append("Morph%d{%s" % (seq, name))
        lines.append("%s;" % _format_values((weight,), digits))
        lines.append("}")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n", len(entries), len(morph_entries)


def write_vpd_text(path: str, text: str, bones: int,
                   morphs: int) -> VpdExport:
    """以 Shift-JIS 写入 VPD；名称无法编码时退回 UTF-8。"""
    data = text.replace("\n", "\r\n")
    try:
        payload = data.encode("cp932")
        encoding = "cp932"
    except UnicodeEncodeError:
        payload = data.encode("utf-8")
        encoding = "utf-8"
    Path(path).write_bytes(payload)
    return VpdExport(path=str(path), encoding=encoding,
                     bones=bones, morphs=morphs)


def save_vpd(path: str, model, pose, morph_weights=None,
             model_name: str = "", include_all: bool = False) -> VpdExport:
    """把当前姿态与形态权重导出为 VPD 文件。"""
    text, bones, morphs = build_vpd_text(
        model, pose, morph_weights, model_name=model_name,
        include_all=include_all)
    return write_vpd_text(path, text, bones, morphs)
