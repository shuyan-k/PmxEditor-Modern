# -*- coding: utf-8 -*-
"""顶点页：位置、法线、UV、边缩放与蒙皮权重。

PMX 的顶点数据是扁平数组（`v_pos`/`v_nrm`/`v_uv`/`v_edge`），蒙皮权重是
`v_wtype` + `v_bones(4)` + `v_weights(4)` + SDEF 的 `v_sdef(C,R0,R1)`。本页
按索引逐点编辑：先在「定位」里选一个顶点，改完值后按「写入模型」，编辑走
`Document.edit`（可撤销）；「诊断」用 NumPy 统计权重分布与异常，便于找出
PMXEditor 里也会标红的那种权重。
"""
from __future__ import annotations

import numpy as np
from PyQt5.QtWidgets import (QComboBox, QHBoxLayout, QSpinBox,
                             QVBoxLayout, QWidget)

from ..ui_widgets import AxisSpin, Form, label, make_spin, text_button
from .base import PageBase

WEIGHT_TYPES = ((0, "BDEF1"), (1, "BDEF2"), (2, "BDEF4"), (3, "SDEF"), (4, "QDEF"))


class VertexPage(PageBase):
    def __init__(self, doc, parent=None):
        super().__init__(doc, "顶点", "位置、UV 与蒙皮权重", parent)
        self.idx = -1
        self.add_tool("search", "跳转到顶点索引", self._jump)
        self.add_tool("mesh", "刷新诊断", self._refresh_stats)

        card, sec = self._card("定位")
        self.detail_hint = label("未载入模型", "Faint", True)
        sec.add(self.detail_hint)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.index_spin = QSpinBox()
        self.index_spin.setRange(0, 0)
        self.index_spin.valueChanged.connect(self._go)
        self.prev_btn = text_button("上一个", "Ghost")
        self.next_btn = text_button("下一个", "Ghost")
        self.prev_btn.clicked.connect(lambda: self._step(-1))
        self.next_btn.clicked.connect(lambda: self._step(1))
        row.addWidget(self.index_spin, 1)
        row.addWidget(self.prev_btn)
        row.addWidget(self.next_btn)
        sec.add_layout(row)
        self.pos_hint = label("", "Faint", True)
        sec.add(self.pos_hint)
        self.root.addWidget(card)

        card, sec = self._card("属性")
        self.pos_spin = AxisSpin(4, 0.01)
        self.nrm_spin = AxisSpin(4, 0.01)
        self.uv_spin = UVSpin()
        self.edge_spin = make_spin(5, 0.0, 1000.0, 0.01)
        form = Form(58)
        form.add("位置", self.pos_spin)
        form.add("法线", self.nrm_spin)
        form.add("UV", self.uv_spin)
        form.add("边缩放", self.edge_spin)
        sec.add(form)
        self.root.addWidget(card)

        card, sec = self._card("蒙皮")
        self.wtype_combo = QComboBox()
        for t, nm in WEIGHT_TYPES:
            self.wtype_combo.addItem(nm, t)
        self.wtype_combo.currentIndexChanged.connect(self._wtype_changed)
        sec.add(self.wtype_combo)
        self.bone_combos = []
        self.weight_spins = []
        for i in range(4):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            combo = QComboBox()
            tag = label("W%d" % (i + 1), "Faint")
            tag.setFixedWidth(20)
            spin = make_spin(4, 0.0, 1.0, 0.01)
            spin.setFixedWidth(72)
            row.addWidget(tag)
            row.addWidget(combo, 1)
            row.addWidget(spin)
            sec.add_layout(row)
            self.bone_combos.append(combo)
            self.weight_spins.append(spin)
        self.wsum = label("", "Faint", True)
        sec.add(self.wsum)
        self.sdef_box = QWidget()
        sl = QFormRow()
        self.center_spin = AxisSpin(4, 0.01)
        self.r0_spin = AxisSpin(4, 0.01)
        self.r1_spin = AxisSpin(4, 0.01)
        sl.add("中心 C", self.center_spin)
        sl.add("R0", self.r0_spin)
        sl.add("R1", self.r1_spin)
        bl = QVBoxLayout(self.sdef_box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.addWidget(sl)
        sec.add(self.sdef_box)
        self.root.addWidget(card)

        card, sec = self._card("诊断")
        self.stats_label = label("", "Faint", True)
        sec.add(self.stats_label)
        self.root.addWidget(card)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.apply_btn = text_button("写入模型", "Primary")
        self.reload_btn = text_button("重新载入", "Ghost")
        self.apply_btn.clicked.connect(self._apply)
        self.reload_btn.clicked.connect(self._fill)
        row.addStretch(1)
        row.addWidget(self.reload_btn)
        row.addWidget(self.apply_btn)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.addLayout(row)
        self.root.addWidget(holder)
        self.root.addStretch(1)

        self._refresh_stats()

    # ------------------------------------------------------------ 数据
    def _vertex_count(self) -> int:
        m = self.doc.model
        return int(len(m.v_pos)) if m else 0

    def refresh(self):
        n = self._vertex_count()
        self.index_spin.blockSignals(True)
        self.index_spin.setRange(0, max(0, n - 1))
        self.index_spin.blockSignals(False)
        if n and (self.idx >= n or self.idx < 0):
            self.idx = max(0, min(self.idx, n - 1)) if self.idx >= 0 else 0
        self.detail_hint.setText("共 %d 个顶点" % n if n else "未载入模型")
        self.pos_hint.setText("未载入模型" if not n else "")
        self._fill()
        self._refresh_stats()

    def select(self, kind: str, index: int):
        if kind != "vertex":
            return
        self.idx = int(index)
        self._fill()

    def _go(self, v):
        self.idx = int(v)
        self._fill()

    def _step(self, d):
        n = self._vertex_count()
        if not n:
            return
        self.idx = max(0, min(n - 1, (self.idx if self.idx >= 0 else 0) + d))
        self.index_spin.blockSignals(True)
        self.index_spin.setValue(self.idx)
        self.index_spin.blockSignals(False)
        self._fill()

    def _jump(self):
        self.index_spin.setFocus()
        self.index_spin.selectAll()

    def _fill(self):
        m = self.doc.model
        n = self._vertex_count()
        enabled = bool(m and 0 <= self.idx < n)
        for w in (self.index_spin, self.pos_spin, self.nrm_spin, self.uv_spin,
                  self.edge_spin, self.wtype_combo):
            w.setEnabled(bool(n))
        self.apply_btn.setEnabled(enabled)
        if not enabled:
            self.pos_hint.setText("未选择顶点")
            return
        if self.index_spin.value() != self.idx:
            self.index_spin.blockSignals(True)
            self.index_spin.setValue(self.idx)
            self.index_spin.blockSignals(False)
        i = self.idx
        with self._suspend():
            self.pos_hint.setText("顶点 %d / %d" % (i, n))
            self.pos_spin.set_value([float(x) for x in m.v_pos[i]])
            self.nrm_spin.set_value([float(x) for x in m.v_nrm[i]])
            uv = [float(m.v_uv[i, 0]), float(m.v_uv[i, 1]) if m.v_uv.shape[1] > 1 else 0.0]
            self.uv_spin.set_value(uv)
            self.edge_spin.setValue(float(m.v_edge[i]))
            wt = int(m.v_wtype[i])
            at = self.wtype_combo.findData(wt)
            self.wtype_combo.setCurrentIndex(at if at >= 0 else 0)
            items = [(j, b.name or "未命名") for j, b in enumerate(m.bones)]
            for k, combo in enumerate(self.bone_combos):
                self._fill_bone_combo(combo, items, int(m.v_bones[i, k]))
                self.weight_spins[k].setValue(float(m.v_weights[i, k]))
            sd = m.v_sdef[i]
            self.center_spin.set_value([float(x) for x in sd[0:3]])
            self.r0_spin.set_value([float(x) for x in sd[3:6]])
            self.r1_spin.set_value([float(x) for x in sd[6:9]])
        self._sync_wtype()

    def _fill_bone_combo(self, combo, items, cur):
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("（无）", -1)
        for j, nm in items:
            combo.addItem("%03d · %s" % (j, nm), j)
        at = combo.findData(int(cur))
        combo.setCurrentIndex(at if at >= 0 else 0)
        combo.blockSignals(False)

    def _sync_wtype(self):
        wt = self.wtype_combo.currentData()
        if wt is None:
            return
        n = 1 if wt == 0 else 2 if wt in (1, 3) else 4
        for k in range(4):
            self.bone_combos[k].setEnabled(k < n)
            self.weight_spins[k].setEnabled(k < n and wt != 0)
        self.sdef_box.setVisible(wt == 3)
        self.wsum.setText("权重和 %.4f（%s）" % (
            sum(float(s.value()) for s in self.weight_spins[:n]),
            "应为 1" if wt in (0, 1, 2, 4) else "SDEF 按前两根骨骼"))

    def _wtype_changed(self, _i):
        if self.loading:
            return
        self._sync_wtype()

    # ------------------------------------------------------------ 写回
    def _apply(self):
        m = self.doc.model
        if not m or not (0 <= self.idx < len(m.v_pos)):
            return
        i = self.idx
        pos = [float(x) for x in self.pos_spin.value()]
        nrm = [float(x) for x in self.nrm_spin.value()]
        uv = [float(x) for x in self.uv_spin.value()]
        edge = float(self.edge_spin.value())
        wt = int(self.wtype_combo.currentData())
        bones = [int(c.currentData()) if c.currentData() is not None else -1
                 for c in self.bone_combos]
        weights = [float(s.value()) for s in self.weight_spins]
        if wt == 0:
            weights = [1.0, 0.0, 0.0, 0.0]
        sd = ([float(x) for x in self.center_spin.value()]
              + [float(x) for x in self.r0_spin.value()]
              + [float(x) for x in self.r1_spin.value()])

        def fn(mm):
            # 只写回真的被改过的分量。数值框位数有限（位置/法线 4 位、UV 与描边
            # 5 位），整行写回会把没动过的分量按位数四舍五入，产生原版 PmxEditor
            # 没有的末位漂移（例如未改动的 Y 从 16.8058395 变成 16.8058）。
            def differs(cur, new, nd):
                return abs(round(float(cur), nd) - float(new)) > 1e-9

            cur = [float(x) for x in mm.v_pos[i]]
            for k in range(3):
                if differs(cur[k], pos[k], 4):
                    mm.v_pos[i, k] = pos[k]
            cur = [float(x) for x in mm.v_nrm[i]]
            for k in range(3):
                if differs(cur[k], nrm[k], 4):
                    mm.v_nrm[i, k] = nrm[k]
            cur = [float(x) for x in mm.v_uv[i]]
            for k in range(min(2, mm.v_uv.shape[1])):
                if differs(cur[k], uv[k], 5):
                    mm.v_uv[i, k] = uv[k]
            if differs(mm.v_edge[i], edge, 5):
                mm.v_edge[i] = edge
            cur_w = [float(x) for x in mm.v_weights[i]]
            changed_w = any(differs(cur_w[k], weights[k], 4) for k in range(4))
            cur_b = [int(x) for x in mm.v_bones[i]]
            if int(mm.v_wtype[i]) != wt or cur_b != list(bones) or changed_w:
                mm.v_wtype[i] = wt
                mm.v_bones[i] = bones
                mm.v_weights[i] = weights
            if mm.v_sdef is not None and len(mm.v_sdef) > i:
                cur_s = [float(x) for x in mm.v_sdef[i]]
                for k in range(min(len(sd), len(cur_s))):
                    if differs(cur_s[k], sd[k], 4):
                        mm.v_sdef[i, k] = sd[k]
        self.edit("修改顶点 %d" % i, fn, "vertex")
        self.doc.select("vertex", i)
        self._fill()
        self._refresh_stats()

    def _refresh_stats(self):
        m = self.doc.model
        if not m:
            self.stats_label.setText("未载入模型")
            return
        try:
            wt = np.asarray(m.v_wtype)
            w = np.asarray(m.v_weights, dtype=np.float64)
            bones = np.asarray(m.v_bones)
            n = len(wt)
            parts = ["顶点 %d 个" % n]
            for t, nm in WEIGHT_TYPES:
                c = int((wt == t).sum())
                if c:
                    parts.append("%s %d" % (nm, c))
            sums = w.sum(axis=1)
            bad = int(((sums < 0.999) & (wt != 3)).sum())
            if bad:
                parts.append("权重和不足 %d" % bad)
            orphan = int(((bones[:, 0] < 0) & (wt != 3)).sum())
            if orphan:
                parts.append("无主骨骼 %d" % orphan)
            self.stats_label.setText(" · ".join(parts))
        except Exception as exc:  # pragma: no cover - 诊断失败不该拖垮页面
            self.stats_label.setText("诊断失败：%s" % exc)


class UVSpin(QWidget):
    """UV 两个分量。"""

    AXIS_COLORS = ("#e07a7a", "#7fc98a")

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.spins = []
        for i, ax in enumerate("UV"):
            tag = label(ax, "")
            tag.setFixedWidth(12)
            tag.setStyleSheet("color:%s; font-size:8pt; font-weight:600;"
                              % self.AXIS_COLORS[i])
            sp = make_spin(5, -99999.0, 99999.0, 0.001)
            sp.setMinimumWidth(52)
            lay.addWidget(tag)
            lay.addWidget(sp, 1)
            self.spins.append(sp)

    def value(self):
        return [float(x.value()) for x in self.spins]

    def set_value(self, vals):
        vals = list(vals) + [0.0] * (2 - len(vals))
        for sp, v in zip(self.spins, vals[:2]):
            sp.blockSignals(True)
            sp.setValue(float(v))
            sp.blockSignals(False)


class QFormRow(QWidget):
    """紧凑的三轴行容器（复用 Form 的观感，但不需要那么多列宽）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(6)

    def add(self, text, widget):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        tag = label(text, "Faint")
        tag.setFixedWidth(52)
        row.addWidget(tag)
        row.addWidget(widget, 1)
        self.lay.addLayout(row)
