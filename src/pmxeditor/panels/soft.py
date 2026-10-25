"""柔体页（PMX 2.1 SoftBody）。"""
from __future__ import annotations

# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout,
                             QLineEdit, QListWidget, QListWidgetItem,
                             QSizePolicy, QSpinBox, QVBoxLayout, QWidget)

from ..doc import add_softbody, remove_softbody
from ..pmx import SB_BEND_LINK, SB_CLUSTER, SB_RANDOMIZE
from ..theme import ACCENT_2, DANGER, GROUP_COLORS
from ..ui_widgets import (Card, ConfirmDialog, EntryList, Form, Segmented,
                          Switch, label, make_spin, text_button)
from .base import _fill_combo, PageBase

AERO_NAMES = ((0, "无"), (1, "顶点单面"), (2, "顶点双面"),
              (3, "双面升降力"), (4, "顶点单面（旧）"))
CONFIG_NAMES = ("VCF", "DP", "DG", "LF", "PR", "VC",
                "DF", "MT", "CHR", "KHR", "SHR", "AHR")
CLUSTER_NAMES = ("SRHR", "SKHR", "SSHR", "SR_SPLT", "SK_SPLT", "SS_SPLT")
ITER_NAMES = ("V_IT", "P_IT", "D_IT", "C_IT")
MAT_NAMES = ("LST", "AST", "VST")


def _int_spin(lo: int = 0, hi: int = 100) -> QSpinBox:
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setKeyboardTracking(False)
    s.setButtonSymbols(QSpinBox.NoButtons)
    s.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return s


class SoftPage(PageBase):
    def __init__(self, doc, parent=None):
        super().__init__(doc, "柔体", "PMX 2.1 SoftBody", parent)
        self.add_tool("plus", "新建柔体", self._add)
        self.add_tool("trash", "删除柔体", self._remove, DANGER)

        self.list = EntryList("dot")
        self.list.indexSelected.connect(self._on_list)
        holder = Card()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(6, 6, 6, 6)
        hl.addWidget(self.list)
        self.root.addWidget(holder, 1)

        self.detail = QWidget()
        dl = QVBoxLayout(self.detail)
        dl.setContentsMargins(0, 0, 2, 4)
        dl.setSpacing(8)
        self.detail.setEnabled(False)

        card, sec = self._card("基本")
        form = Form(64)
        self.name_edit = QLineEdit()
        self.name_en_edit = QLineEdit()
        self.shape_seg = Segmented([("0", "三角网格"), ("1", "四面体")])
        self.mat_combo = QComboBox()
        self.group_spin = _int_spin(0, 15)
        form.add("名称", self.name_edit)
        form.add("英文名", self.name_en_edit)
        form.add("形状", self.shape_seg)
        form.add("材质", self.mat_combo)
        form.add("所属组", self.group_spin)
        sec.add(form)
        dl.addWidget(card)

        card, sec = self._card("生成选项")
        self.flag_bend = self._flag_row(sec, "生成弯曲链接", SB_BEND_LINK)
        self.flag_cluster = self._flag_row(sec, "生成簇", SB_CLUSTER)
        self.flag_random = self._flag_row(sec, "随机化约束", SB_RANDOMIZE)
        form = Form(64)
        self.bdist_spin = _int_spin(0, 1000)
        self.cluster_spin = _int_spin(0, 100000)
        form.add("弯曲链接距离", self.bdist_spin)
        form.add("簇数量", self.cluster_spin)
        sec.add(form)
        dl.addWidget(card)

        card, sec = self._card("质量与碰撞")
        form = Form(64)
        self.mass_spin = make_spin(3, 0.0, 100000.0, 0.1)
        self.margin_spin = make_spin(4, 0.0, 1000.0, 0.01)
        self.aero_combo = QComboBox()
        for data, text in AERO_NAMES:
            self.aero_combo.addItem("%d · %s" % (data, text), data)
        form.add("总质量", self.mass_spin)
        form.add("碰撞余量", self.margin_spin)
        form.add("气动模型", self.aero_combo)
        sec.add(form)
        dl.addWidget(card)

        card, sec = self._card("碰撞组", "组号 0–15；勾选可碰撞的组")
        self.mask_checks = []
        mg = QGridLayout()
        mg.setHorizontalSpacing(2)
        mg.setVerticalSpacing(2)
        for g in range(16):
            cb = QCheckBox(str(g))
            cb.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            cb.setStyleSheet("color:%s; font-size:8pt; spacing:3px;"
                             "QCheckBox::indicator{width:12px;height:12px;}"
                             % GROUP_COLORS[g])
            cb.toggled.connect(lambda on, g=g: self._mask_toggled(g, on))
            self.mask_checks.append(cb)
            mg.addWidget(cb, g // 8, g % 8)
        sec.add_layout(mg)
        row = QHBoxLayout()
        row.addStretch(1)
        all_btn = text_button("全选", "Ghost")
        none_btn = text_button("清空", "Ghost")
        all_btn.clicked.connect(lambda: self._set_mask(0xFFFF))
        none_btn.clicked.connect(lambda: self._set_mask(0))
        row.addWidget(all_btn)
        row.addWidget(none_btn)
        sec.add_layout(row)
        dl.addWidget(card)

        card, sec = self._card("求解参数", "名称沿用 Bullet 软体参数")
        self.config_spins = self._float_grid(sec, CONFIG_NAMES, 12, "config")
        self.cluster_spins = self._float_grid(sec, CLUSTER_NAMES, 6, "cluster")
        self.iter_spins = self._int_grid(sec, ITER_NAMES, 4)
        self.mat_spins = self._float_grid(sec, MAT_NAMES, 3, "material_params")
        dl.addWidget(card)

        card, sec = self._card("锚点", "把柔体固定在刚体上的顶点")
        self.anchor_list = QListWidget()
        self.anchor_list.setObjectName("Entry")
        self.anchor_list.setFixedHeight(96)
        self.anchor_list.currentRowChanged.connect(lambda _r: self._sync_buttons())
        sec.add(self.anchor_list)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.anchor_rigid = QComboBox()
        row.addWidget(self.anchor_rigid, 1)
        sec.add_layout(row)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.anchor_vertex = _int_spin(0, 0)
        self.anchor_near = Switch(False)
        row.addWidget(label("顶点", "Muted"))
        row.addWidget(self.anchor_vertex, 1)
        row.addWidget(self.anchor_near)
        row.addWidget(label("近", "Muted"))
        sec.add_layout(row)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addStretch(1)
        self.anchor_add = text_button("添加锚点", "Ghost")
        self.anchor_del = text_button("移除锚点", "Ghost")
        self.anchor_add.clicked.connect(self._anchor_add)
        self.anchor_del.clicked.connect(self._anchor_del)
        row.addWidget(self.anchor_add)
        row.addWidget(self.anchor_del)
        sec.add_layout(row)
        dl.addWidget(card)

        card, sec = self._card("固定点", "不参与演算的顶点")
        self.pin_list = QListWidget()
        self.pin_list.setObjectName("Entry")
        self.pin_list.setFixedHeight(76)
        self.pin_list.currentRowChanged.connect(lambda _r: self._sync_buttons())
        sec.add(self.pin_list)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.pin_spin = _int_spin(0, 0)
        row.addWidget(label("顶点", "Muted"))
        row.addWidget(self.pin_spin, 1)
        self.pin_add = text_button("添加", "Ghost")
        self.pin_del = text_button("移除", "Ghost")
        self.pin_add.clicked.connect(self._pin_add)
        self.pin_del.clicked.connect(self._pin_del)
        row.addWidget(self.pin_add)
        row.addWidget(self.pin_del)
        sec.add_layout(row)
        dl.addWidget(card)

        dl.addStretch(1)
        self.root.addWidget(self.scroll(self.detail), 3)

        self.name_edit.editingFinished.connect(self._name_changed)
        self.name_en_edit.editingFinished.connect(self._name_en_changed)
        self.shape_seg.changed.connect(lambda k: self._set_field("shape", int(k)))
        self.mat_combo.currentIndexChanged.connect(self._material_changed)
        self.group_spin.valueChanged.connect(self._group_changed)
        self.bdist_spin.valueChanged.connect(lambda v: self._set_field("b_link_dist", int(v)))
        self.cluster_spin.valueChanged.connect(
            lambda v: self._set_field("cluster_count", int(v)))
        self.mass_spin.valueChanged.connect(self._mass_changed)
        self.margin_spin.valueChanged.connect(
            lambda v: self._set_field("collision_margin", float(v)))
        self.aero_combo.currentIndexChanged.connect(self._aero_changed)

    # ------------------------------------------------------------ 构建辅助
    def _flag_row(self, sec, text: str, flag: int) -> Switch:
        sw = Switch(False)
        sw.toggled.connect(lambda on, f=flag: self._flag_changed(f, on))
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(sw)
        row.addWidget(label(text, "Muted"))
        row.addStretch(1)
        sec.add_layout(row)
        return sw

    def _float_grid(self, sec, names, count: int, field: str):
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(5)
        spins = []
        for i in range(count):
            nm = label(names[i] if i < len(names) else "P%d" % i, "Faint")
            nm.setFixedWidth(44)
            sp = make_spin(4, -99999.0, 99999.0, 0.01)
            sp.setMinimumWidth(56)
            sp.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            sp.valueChanged.connect(
                lambda v, i=i: self._array_changed(field, i, float(v)))
            row, col = divmod(i, 3)
            grid.addWidget(nm, row, col * 2)
            grid.addWidget(sp, row, col * 2 + 1)
            spins.append(sp)
        sec.add_layout(grid)
        return spins

    def _int_grid(self, sec, names, count: int):
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(5)
        spins = []
        for i in range(count):
            nm = label(names[i] if i < len(names) else "I%d" % i, "Faint")
            nm.setFixedWidth(44)
            sp = _int_spin(-1000, 1000)
            sp.setMinimumWidth(56)
            sp.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            sp.valueChanged.connect(lambda v, i=i: self._iter_changed(i, int(v)))
            row, col = divmod(i, 2)
            grid.addWidget(nm, row, col * 2)
            grid.addWidget(sp, row, col * 2 + 1)
            spins.append(sp)
        sec.add_layout(grid)
        return spins

    # ------------------------------------------------------------ 列表
    def _refresh_list(self, *_):
        m = self.doc.model
        if not m:
            self._show_empty()
            return
        entries = []
        for i, s in enumerate(m.soft_bodies):
            entries.append({
                "name": s.name or "未命名柔体",
                "hint": "材质 %d · 组 %d" % (s.material, s.group),
                "right": "质量 %.2f" % float(s.total_mass),
                "color": ACCENT_2,
                "index": i,
            })
        self._show_entries(entries, "无柔体（PMX 2.1 才能保存）")

    def refresh(self):
        m = self.doc.model
        if not m:
            self.idx = -1
            self._refresh_list()
            self.detail.setEnabled(False)
            self.set_hint("未载入模型")
            return
        if self.doc.sel_kind == "soft" and 0 <= self.doc.sel_index < len(m.soft_bodies):
            self.idx = self.doc.sel_index
        self._refresh_list()
        if m.soft_bodies and not (0 <= self.idx < len(m.soft_bodies)):
            self.idx = 0
            self._select_row(0)
        self.set_hint("柔体 %d 个 · PMX %s" % (len(m.soft_bodies), "2.1" if m.version >= 2.1 else "2.0"))
        if 0 <= self.idx < len(m.soft_bodies):
            self.detail.setEnabled(True)
            self._fill()
        else:
            self.idx = -1
            self.detail.setEnabled(False)

    def select(self, kind: str, index: int):
        if kind != "soft":
            return
        self.idx = index
        self._select_row(index)
        m = self.doc.model
        self.detail.setEnabled(bool(m and 0 <= index < len(m.soft_bodies)))
        self._fill()

    def _on_list(self, i):
        self._select_from_list("soft", i)

    def _soft(self):
        m = self.doc.model
        if m and 0 <= self.idx < len(m.soft_bodies):
            return m.soft_bodies[self.idx]
        return None

    # ------------------------------------------------------------ 回填
    def _fill(self):
        m = self.doc.model
        s = self._soft()
        if not m or not s:
            return
        with self._suspend():
            self.name_edit.setText(s.name)
            self.name_en_edit.setText(s.name_en)
            self.shape_seg.set_value(str(int(s.shape)))
            items = [(i, "%02d · %s" % (i, mt.name or "未命名材质"))
                     for i, mt in enumerate(m.materials)]
            _fill_combo(self.mat_combo, items, int(s.material), empty=(-1, "（无材质）"))
            self.group_spin.setValue(int(s.group))
            for g, cb in enumerate(self.mask_checks):
                cb.setChecked(bool(int(s.mask) & (1 << g)))
            self.flag_bend.setChecked(bool(int(s.flags) & SB_BEND_LINK))
            self.flag_cluster.setChecked(bool(int(s.flags) & SB_CLUSTER))
            self.flag_random.setChecked(bool(int(s.flags) & SB_RANDOMIZE))
            self.bdist_spin.setValue(int(s.b_link_dist))
            self.cluster_spin.setValue(int(s.cluster_count))
            self.mass_spin.setValue(float(s.total_mass))
            self.margin_spin.setValue(float(s.collision_margin))
            idx = self.aero_combo.findData(int(s.aero_model))
            self.aero_combo.setCurrentIndex(idx if idx >= 0 else 0)
            for spin, v in zip(self.config_spins, s.config):
                spin.setValue(float(v))
            for spin, v in zip(self.cluster_spins, s.cluster):
                spin.setValue(float(v))
            for spin, v in zip(self.iter_spins, s.iteration):
                spin.setValue(int(v))
            for spin, v in zip(self.mat_spins, s.material_params):
                spin.setValue(float(v))
            self.anchor_vertex.setRange(0, max(0, m.n_vertices - 1))
            self.pin_spin.setRange(0, max(0, m.n_vertices - 1))
            rigid_items = [(i, "%02d · %s" % (i, rb.name or "未命名刚体"))
                           for i, rb in enumerate(m.rigid)]
            _fill_combo(self.anchor_rigid, rigid_items)
            self._fill_anchors(m, s)
            self._fill_pins(s)
        self._sync_buttons()

    def _fill_anchors(self, m, s):
        self.anchor_list.clear()
        for rid, vid, near in s.anchors:
            name = m.rigid[rid].name if 0 <= rid < len(m.rigid) else "?"
            it = QListWidgetItem("%02d · 刚体 %d「%s」· 顶点 %d%s"
                                 % (self.anchor_list.count(), rid, name, vid,
                                    " · 近" if near else ""))
            it.setData(Qt.UserRole, self.anchor_list.count())
            self.anchor_list.addItem(it)
        if self.anchor_list.count():
            self.anchor_list.setCurrentRow(0)

    def _fill_pins(self, s):
        self.pin_list.clear()
        for vid in s.pins:
            it = QListWidgetItem("%02d · 顶点 %d" % (self.pin_list.count(), vid))
            it.setData(Qt.UserRole, self.pin_list.count())
            self.pin_list.addItem(it)
        if self.pin_list.count():
            self.pin_list.setCurrentRow(0)

    def _sync_buttons(self):
        self.anchor_del.setEnabled(self.anchor_list.currentRow() >= 0)
        self.pin_del.setEnabled(self.pin_list.currentRow() >= 0)
        self.anchor_add.setEnabled(self.anchor_rigid.count() > 0)

    # ------------------------------------------------------------ 编辑
    def _set_field(self, field: str, value, label_text: str = "修改柔体参数"):
        if self.loading or not self._soft():
            return
        self.edit(label_text,
                  lambda m: setattr(m.soft_bodies[self.idx], field, value),
                  "soft", "soft." + field)

    def _name_changed(self):
        s = self._soft()
        if not s or self.loading:
            return
        text = self.name_edit.text()
        if text != s.name:
            self._set_field("name", text, "重命名柔体")

    def _name_en_changed(self):
        s = self._soft()
        if not s or self.loading:
            return
        text = self.name_en_edit.text()
        if text != s.name_en:
            self._set_field("name_en", text, "修改柔体英文名")

    def _material_changed(self, _i):
        if self.loading:
            return
        v = self.mat_combo.currentData()
        if v is not None:
            self._set_field("material", int(v), "修改柔体材质")

    def _aero_changed(self, _i):
        if self.loading:
            return
        v = self.aero_combo.currentData()
        if v is not None:
            self._set_field("aero_model", int(v), "修改气动模型")

    def _group_changed(self, v):
        if self.loading:
            return
        self._set_field("group", int(v), "修改柔体所属组")
        self._refresh_list()

    def _mass_changed(self, v):
        if self.loading:
            return
        self._set_field("total_mass", float(v), "修改柔体总质量")
        self._refresh_list()

    def _flag_changed(self, flag: int, on: bool):
        if self.loading or not self._soft():
            return

        def fn(m):
            s = m.soft_bodies[self.idx]
            s.flags = (int(s.flags) | flag) if on else (int(s.flags) & ~flag)

        self.edit("修改柔体生成选项", fn, "soft")

    def _mask_toggled(self, g: int, on: bool):
        if self.loading or not self._soft():
            return
        bit = 1 << g

        def fn(m):
            s = m.soft_bodies[self.idx]
            s.mask = (int(s.mask) | bit) if on else (int(s.mask) & ~bit)

        self.edit("修改柔体碰撞组", fn, "soft")

    def _set_mask(self, value: int):
        if not self._soft():
            return
        with self._suspend():
            for g, cb in enumerate(self.mask_checks):
                cb.setChecked(bool(value & (1 << g)))
        self._set_field("mask", int(value), "修改柔体碰撞组")

    def _array_changed(self, field: str, i: int, value: float):
        if self.loading or not self._soft():
            return

        def fn(m):
            getattr(m.soft_bodies[self.idx], field)[i] = float(value)

        self.edit("修改柔体参数", fn, "soft", "soft.%s%d" % (field, i))

    def _iter_changed(self, i: int, value: int):
        if self.loading or not self._soft():
            return

        def fn(m):
            m.soft_bodies[self.idx].iteration[i] = int(value)

        self.edit("修改柔体迭代次数", fn, "soft", "soft.iter%d" % i)

    # ------------------------------------------------------------ 锚点 / 固定点
    def _anchor_add(self):
        m = self.doc.model
        s = self._soft()
        rid = self.anchor_rigid.currentData()
        if not m or not s or rid is None:
            return
        item = (int(rid), int(self.anchor_vertex.value()),
                1 if self.anchor_near.isChecked() else 0)
        self.edit("添加柔体锚点",
                  lambda model: model.soft_bodies[self.idx].anchors.append(item), "soft")
        self._fill_anchors(m, s)
        self._sync_buttons()

    def _anchor_del(self):
        m = self.doc.model
        s = self._soft()
        if not m or not s:
            return
        row = self.anchor_list.currentRow()
        if row < 0 and s.anchors:
            row = 0
        if row < 0:
            return
        self.edit("移除柔体锚点",
                  lambda model: model.soft_bodies[self.idx].anchors.pop(row), "soft")
        self._fill_anchors(m, s)
        self._sync_buttons()

    def _pin_add(self):
        m = self.doc.model
        s = self._soft()
        if not m or not s:
            return
        vid = int(self.pin_spin.value())
        self.edit("添加柔体固定点",
                  lambda model: model.soft_bodies[self.idx].pins.append(vid), "soft")
        self._fill_pins(s)
        self._sync_buttons()

    def _pin_del(self):
        m = self.doc.model
        s = self._soft()
        if not m or not s:
            return
        row = self.pin_list.currentRow()
        if row < 0 and s.pins:
            row = 0
        if row < 0:
            return
        self.edit("移除柔体固定点",
                  lambda model: model.soft_bodies[self.idx].pins.pop(row), "soft")
        self._fill_pins(s)
        self._sync_buttons()

    # ------------------------------------------------------------ 结构
    def _add(self):
        m = self.doc.model
        if not m:
            return
        self.doc.push_undo("新建柔体")
        idx = add_softbody(m)
        self.doc.mark_dirty()
        self.doc.edited.emit("structure")
        self.doc.select("soft", idx)

    def _remove(self):
        m = self.doc.model
        s = self._soft()
        if not m or not s:
            return
        dlg = ConfirmDialog("删除柔体", "确定删除「%s」？\n"
                            "它的 %d 个锚点与 %d 个固定点会一起移除。"
                            % (s.name, len(s.anchors), len(s.pins)),
                            danger=True, parent=self)
        if dlg.exec_() != dlg.Accepted:
            return
        self.doc.push_undo("删除柔体")
        idx = remove_softbody(m, self.idx)
        self.doc.mark_dirty()
        self.doc.edited.emit("structure")
        self.doc.select("soft", idx)
