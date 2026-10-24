"""骨骼页。"""
from __future__ import annotations

# -*- coding: utf-8 -*-
import math
from PyQt5.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QLineEdit, QListWidget, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)
from ..config import Config
from ..doc import add_bone, duplicate_bone, move_bone, remove_bone
from ..gl_names import bone_zh
from ..pmx import (BF_AFTER_PHYSICS, BF_ENABLED, BF_FIXED_AXIS, BF_IK, BF_INHERIT_MOV, BF_INHERIT_ROT, BF_LOCAL_APPEND, BF_LOCAL_AXIS, BF_ROTATABLE, BF_TAIL_INDEX, BF_TRANSLATABLE, BF_VISIBLE, IKLink, shift_bone_vertices)
from ..theme import ACCENT, DANGER, TEXT_FAINT
from ..ui_widgets import (AxisSpin, BoneTree, Card, ConfirmDialog, Form, Segmented, Switch, SearchEdit, label, make_spin, text_button)
from .base import _cycle, _fill_combo, _mode_spin, _bone_combo_items, PageBase

# ================================================================= 骨骼

class BonePage(PageBase):
    def __init__(self, doc, parent=None):
        super().__init__(doc, "骨骼", "选择骨骼进行编辑", parent)
        self.add_tool("plus", "新建骨骼（作为当前骨骼的子级）", self._add)
        self.add_tool("duplicate", "复制当前骨骼", self._duplicate)
        self.add_tool("trash", "删除当前骨骼", self._remove, DANGER)

        self.search = SearchEdit("搜索骨骼名 / 中文译名")
        self.search.changed.connect(self._search)
        self.root.addWidget(self.search)

        self.tree = BoneTree()
        self.tree.boneSelected.connect(self._on_tree)
        holder = Card()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(6, 6, 6, 6)
        hl.addWidget(self.tree)
        self.root.addWidget(holder, 1)

        self.detail = QWidget()
        dl = QVBoxLayout(self.detail)
        dl.setContentsMargins(0, 0, 2, 4)
        dl.setSpacing(8)

        card, sec = self._card("基本", "")
        self.zh_badge = label("", "Accent")
        sec.add(self.zh_badge)
        form = Form(64)
        self.name_edit = QLineEdit()
        self.name_en_edit = QLineEdit()
        self.parent_combo = QComboBox()
        self.layer_spin = _mode_spin(0, 0, 31)
        self.pos_spin = AxisSpin(4, 0.01)
        form.add("名称", self.name_edit)
        form.add("英文名", self.name_en_edit)
        form.add("父骨骼", self.parent_combo)
        form.add("变形层级", self.layer_spin)
        form.add("位置", self.pos_spin)
        order_row = QHBoxLayout()
        order_row.setContentsMargins(0, 0, 0, 0)
        order_row.setSpacing(6)
        self.up_btn = text_button("上移", "Ghost", tip="在骨骼列表里上移一位（会重映射所有引用）")
        self.down_btn = text_button("下移", "Ghost", tip="在骨骼列表里下移一位（会重映射所有引用）")
        self.up_btn.clicked.connect(lambda: self._move_bone(-1))
        self.down_btn.clicked.connect(lambda: self._move_bone(1))
        order_row.addWidget(self.up_btn)
        order_row.addWidget(self.down_btn)
        order_row.addStretch(1)
        form.add_full(order_row)
        self.move_verts_sw = Switch(False)
        self.move_verts_sw.setChecked(
            bool(Config.load().get("editor/move_bone_vertices", False)))
        self.move_verts_sw.toggled.connect(self._move_verts_toggled)
        self.move_verts_sw.setToolTip(
            "开启后修改位置会按蒙皮权重把位移写进顶点（PMXEditor 习惯）")
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.move_verts_sw)
        row.addWidget(label("移动时带动顶点", "Muted"))
        row.addStretch(1)
        form.add_full(row)
        sec.add(form)
        self.name_edit.editingFinished.connect(self._name_changed)
        self.name_en_edit.editingFinished.connect(self._name_en_changed)
        self.parent_combo.currentIndexChanged.connect(self._parent_changed)
        self.layer_spin.valueChanged.connect(self._layer_changed)
        self.pos_spin.valueChanged.connect(self._pos_changed)
        dl.addWidget(card)

        card, sec = self._card("连接与显示", "尾端用于视图中的骨骼长度")
        self.conn_seg = Segmented([("offset", "坐标偏移"), ("bone", "骨骼")])
        self.conn_seg.changed.connect(self._conn_changed)
        sec.add(self.conn_seg)
        self.conn_stack = QStackedWidget()
        w1 = QWidget()
        l1 = QVBoxLayout(w1)
        l1.setContentsMargins(0, 0, 0, 0)
        self.tail_spin = AxisSpin(4, 0.01)
        l1.addWidget(self.tail_spin)
        w2 = QWidget()
        l2 = QVBoxLayout(w2)
        l2.setContentsMargins(0, 0, 0, 0)
        self.tail_combo = QComboBox()
        l2.addWidget(self.tail_combo)
        self.conn_stack.addWidget(w1)
        self.conn_stack.addWidget(w2)
        sec.add(self.conn_stack)
        self.tail_spin.valueChanged.connect(self._tail_offset_changed)
        self.tail_combo.currentIndexChanged.connect(self._tail_bone_changed)

        grid = QGridLayout()
        grid.setContentsMargins(0, 2, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        self.switches = {}
        for i, (key, txt, flag) in enumerate((
                ("rot", "可旋转", BF_ROTATABLE), ("mov", "可移动", BF_TRANSLATABLE),
                ("vis", "显示", BF_VISIBLE), ("op", "可操作", BF_ENABLED),
                ("after", "物理后变形", BF_AFTER_PHYSICS),
                ("local", "本地付与", BF_LOCAL_APPEND))):
            sw = Switch(True)
            sw.toggled.connect(lambda on, f=flag: self._flag_changed(f, on))
            self.switches[key] = sw
            grid.addWidget(sw, i // 2, (i % 2) * 2)
            grid.addWidget(label(txt, "Muted"), i // 2, (i % 2) * 2 + 1)
        sec.add_layout(grid)
        dl.addWidget(card)

        card, sec = self._card("付与", "继承父级或指定骨骼的旋转/位移")
        form = Form(64)
        self.inherit_parent = QComboBox()
        self.inherit_ratio = make_spin(3, -10.0, 10.0, 0.01)
        self.inherit_rot = Switch(False)
        self.inherit_mov = Switch(False)
        form.add("付与父级", self.inherit_parent)
        form.add("付与率", self.inherit_ratio)
        row = QHBoxLayout()
        row.addWidget(self.inherit_rot)
        row.addWidget(label("旋转付与", "Muted"))
        row.addSpacing(8)
        row.addWidget(self.inherit_mov)
        row.addWidget(label("移动付与", "Muted"))
        row.addStretch(1)
        form.add_full(row)
        sec.add(form)
        self.inherit_parent.currentIndexChanged.connect(self._inherit_changed)
        self.inherit_ratio.valueChanged.connect(self._inherit_ratio_changed)
        self.inherit_rot.toggled.connect(lambda on: self._inherit_flag(BF_INHERIT_ROT, on))
        self.inherit_mov.toggled.connect(lambda on: self._inherit_flag(BF_INHERIT_MOV, on))
        dl.addWidget(card)

        card, sec = self._card("轴固定 / 局部轴")
        self.fixed_sw = Switch(False)
        self.axis_spin = AxisSpin(3, 0.01)
        self.local_sw = Switch(False)
        self.localx_spin = AxisSpin(3, 0.01)
        self.localz_spin = AxisSpin(3, 0.01)
        form = Form(64)
        row = QHBoxLayout()
        row.addWidget(self.fixed_sw)
        row.addWidget(label("轴固定", "Muted"))
        row.addStretch(1)
        form.add_full(row)
        form.add("轴方向", self.axis_spin)
        row2 = QHBoxLayout()
        row2.addWidget(self.local_sw)
        row2.addWidget(label("局部轴", "Muted"))
        row2.addStretch(1)
        form.add_full(row2)
        form.add("X 轴", self.localx_spin)
        form.add("Z 轴", self.localz_spin)
        sec.add(form)
        self.fixed_sw.toggled.connect(lambda on: self._axis_flag_changed(BF_FIXED_AXIS, on))
        self.local_sw.toggled.connect(lambda on: self._axis_flag_changed(BF_LOCAL_AXIS, on))
        self.axis_spin.valueChanged.connect(self._axis_changed)
        self.localx_spin.valueChanged.connect(self._localx_changed)
        self.localz_spin.valueChanged.connect(self._localz_changed)
        dl.addWidget(card)

        card, sec = self._card("IK", "逆向运动学")
        self.ik_sw = Switch(False)
        row = QHBoxLayout()
        row.addWidget(self.ik_sw)
        row.addWidget(label("启用 IK", "Muted"))
        row.addStretch(1)
        sec.add_layout(row)
        form = Form(64)
        self.ik_target = QComboBox()
        self.ik_loop = QSpinBox()
        self.ik_loop.setRange(1, 255)
        self.ik_loop.setKeyboardTracking(False)
        self.ik_loop.setButtonSymbols(QSpinBox.NoButtons)
        self.ik_angle = make_spin(2, 0.0, 180.0, 0.5)
        form.add("目标骨骼", self.ik_target)
        form.add("循环次数", self.ik_loop)
        form.add("单次角度", self.ik_angle)
        sec.add(form)
        self.ik_links = QListWidget()
        self.ik_links.setObjectName("Entry")
        self.ik_links.setFixedHeight(84)
        self.ik_links.currentRowChanged.connect(lambda _r: self._sync_link_editor())
        sec.add(self.ik_links)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.ik_link_combo = QComboBox()
        self.ik_link_add = text_button("添加链接", "Ghost", tip="把选中的骨骼加进 IK 链")
        self.ik_link_del = text_button("移除", "Ghost", tip="从 IK 链里移除选中骨骼")
        self.ik_link_add.clicked.connect(self._ik_link_add)
        self.ik_link_del.clicked.connect(self._ik_link_del)
        row.addWidget(self.ik_link_combo, 1)
        row.addWidget(self.ik_link_add)
        row.addWidget(self.ik_link_del)
        sec.add_layout(row)
        lform = Form(64)
        self.link_limit_sw = Switch(False)
        lrow = QHBoxLayout()
        lrow.setContentsMargins(0, 0, 0, 0)
        lrow.addWidget(self.link_limit_sw)
        lrow.addWidget(label("角度限制", "Muted"))
        lrow.addStretch(1)
        lform.add_full(lrow)
        self.link_lo = AxisSpin(2, 1.0, -180.0, 180.0)
        self.link_hi = AxisSpin(2, 1.0, -180.0, 180.0)
        lform.add("最小", self.link_lo)
        lform.add("最大", self.link_hi)
        sec.add(lform)
        self.link_limit_sw.toggled.connect(self._link_limit_changed)
        self.link_lo.valueChanged.connect(lambda: self._link_range_changed(0))
        self.link_hi.valueChanged.connect(lambda: self._link_range_changed(1))
        dl.addWidget(card)
        self.ik_sw.toggled.connect(self._ik_toggled)
        self.ik_target.currentIndexChanged.connect(self._ik_target_changed)
        self.ik_loop.valueChanged.connect(self._ik_loop_changed)
        self.ik_angle.valueChanged.connect(self._ik_angle_changed)
        dl.addWidget(card)
        dl.addStretch(1)

        self.detail_scroll = self.scroll(self.detail)
        self.root.addWidget(self.detail_scroll, 2)
        self._set_enabled(False)

    def _set_enabled(self, on: bool):
        self.detail_scroll.setEnabled(on)

    # ------------------------------------------------------------ 数据
    def _bone(self):
        m = self.doc.model
        if m and 0 <= self.idx < len(m.bones):
            return m.bones[self.idx]
        return None

    def refresh(self):
        m = self.doc.model
        self.loading = True
        try:
            if not m:
                self.idx = -1
            self.tree.set_model_data(m, self.search.text(), self.doc.sel_index
                                     if self.doc.sel_kind == "bone" else -1)
            if m and m.bones and not (0 <= self.idx < len(m.bones)):
                self.idx = 0
                self.tree.select_bone(0)
            self._fill()
        finally:
            self.loading = False

    def select(self, kind: str, index: int):
        if kind != "bone":
            return
        self.idx = index
        self.loading = True
        try:
            self.tree.select_bone(index)
            self._fill()
        finally:
            self.loading = False

    def _search(self, text: str):
        m = self.doc.model
        if not m:
            return
        self.loading = True
        try:
            self.tree.set_model_data(m, text, self.idx)
        finally:
            self.loading = False

    def _on_tree(self, index: int):
        if self.loading:
            return
        self.doc.select("bone", index)

    def _fill(self):
        m = self.doc.model
        b = self._bone()
        prev = self.loading
        self.loading = True
        self._set_enabled(b is not None)
        if not m or not b:
            self.set_hint("未选择")
            self.zh_badge.setText("")
            self.loading = prev
            return
        self.set_hint("索引 %d · %d 根骨骼" % (self.idx, len(m.bones)))
        zh = bone_zh(b.name)
        self.zh_badge.setText(("中文：%s" % zh) if zh and zh != b.name else "无中文对照")
        self.zh_badge.setStyleSheet("color:%s;" % (ACCENT if zh and zh != b.name else TEXT_FAINT))
        self.name_edit.setText(b.name)
        self.name_en_edit.setText(b.name_en)
        _fill_combo(self.parent_combo, _bone_combo_items(m), b.parent,
                    empty=(-1, "（无 · 根骨骼）"))
        self.layer_spin.setValue(int(b.layer))
        self.pos_spin.set_value(b.pos)
        is_bone = bool(b.flags & BF_TAIL_INDEX)
        self.conn_seg.set_value("bone" if is_bone else "offset")
        self.conn_stack.setCurrentIndex(1 if is_bone else 0)
        self.tail_spin.set_value(b.tail_offset)
        _fill_combo(self.tail_combo, _bone_combo_items(m), b.tail_bone,
                    empty=(-1, "（无）"))
        self.switches["rot"].setChecked(bool(b.flags & BF_ROTATABLE))
        self.switches["mov"].setChecked(bool(b.flags & BF_TRANSLATABLE))
        self.switches["vis"].setChecked(bool(b.flags & BF_VISIBLE))
        self.switches["op"].setChecked(bool(b.flags & BF_ENABLED))
        self.switches["after"].setChecked(bool(b.flags & BF_AFTER_PHYSICS))
        self.switches["local"].setChecked(bool(b.flags & BF_LOCAL_APPEND))
        self.inherit_rot.setChecked(bool(b.flags & BF_INHERIT_ROT))
        self.inherit_mov.setChecked(bool(b.flags & BF_INHERIT_MOV))
        inherit_on = bool(b.flags & (BF_INHERIT_ROT | BF_INHERIT_MOV))
        _fill_combo(self.inherit_parent, _bone_combo_items(m), b.append_parent,
                    empty=(-1, "（父骨骼）"))
        self.inherit_parent.setEnabled(inherit_on)
        self.inherit_ratio.setEnabled(inherit_on)
        self.inherit_ratio.setValue(float(b.append_ratio))
        self.fixed_sw.setChecked(bool(b.flags & BF_FIXED_AXIS))
        self.axis_spin.set_value(b.axis)
        self.axis_spin.set_enabled(bool(b.flags & BF_FIXED_AXIS))
        self.local_sw.setChecked(bool(b.flags & BF_LOCAL_AXIS))
        self.localx_spin.set_value(b.local_x)
        self.localz_spin.set_value(b.local_z)
        self.localx_spin.set_enabled(bool(b.flags & BF_LOCAL_AXIS))
        self.localz_spin.set_enabled(bool(b.flags & BF_LOCAL_AXIS))
        self.ik_sw.setChecked(bool(b.flags & BF_IK and b.ik))
        _fill_combo(self.ik_target, _bone_combo_items(m), b.ik.target if b.ik else -1,
                    empty=(-1, "（无）"))
        self.ik_target.setEnabled(bool(b.ik))
        self.ik_loop.setValue(int(b.ik.loop) if b.ik else 40)
        self.ik_loop.setEnabled(bool(b.ik))
        self.ik_angle.setValue(math.degrees(b.ik.angle) if b.ik else 30.0)
        self.ik_angle.setEnabled(bool(b.ik))
        self._fill_links(m, b)
        self.loading = prev
        self._sync_link_editor()

    # ------------------------------------------------------------ IK 链
    def _link(self):
        b = self._bone()
        if not b or not b.ik:
            return None
        row = self.ik_links.currentRow()
        if 0 <= row < len(b.ik.links):
            return b.ik.links[row]
        return None

    def _fill_links(self, m, b):
        links = list(b.ik.links) if b.ik else []
        keep = self.ik_links.currentRow()
        self.ik_links.blockSignals(True)
        self.ik_links.clear()
        for link in links:
            nm = m.bones[link.bone].name if 0 <= link.bone < len(m.bones) else "?"
            if link.limited:
                rng = "  X[%.0f,%.0f] Y[%.0f,%.0f] Z[%.0f,%.0f]" % (
                    math.degrees(link.lo[0]), math.degrees(link.hi[0]),
                    math.degrees(link.lo[1]), math.degrees(link.hi[1]),
                    math.degrees(link.lo[2]), math.degrees(link.hi[2]))
            else:
                rng = "  · 无限制"
            self.ik_links.addItem("· %s%s" % (nm, rng))
        if links:
            self.ik_links.setCurrentRow(max(0, min(keep, len(links) - 1)))
        self.ik_links.blockSignals(False)
        used = {l.bone for l in links}
        items = [(i, "%03d · %s" % (i, bb.name or "未命名"))
                 for i, bb in enumerate(m.bones) if i not in used]
        _fill_combo(self.ik_link_combo, items, self.ik_link_combo.currentData())

    def _sync_link_editor(self):
        link = self._link()
        on = link is not None
        self.link_limit_sw.setEnabled(on)
        self.link_lo.set_enabled(on)
        self.link_hi.set_enabled(on)
        self.ik_link_del.setEnabled(on)
        self.ik_link_add.setEnabled(self.ik_link_combo.count() > 0)
        prev = self.loading
        self.loading = True
        try:
            if link is None:
                self.link_limit_sw.setChecked(False)
                self.link_lo.set_value([0.0, 0.0, 0.0])
                self.link_hi.set_value([0.0, 0.0, 0.0])
            else:
                self.link_limit_sw.setChecked(bool(link.limited))
                self.link_lo.set_value([math.degrees(x) for x in link.lo])
                self.link_hi.set_value([math.degrees(x) for x in link.hi])
        finally:
            self.loading = prev

    def _ik_link_add(self):
        if self.loading:
            return
        m = self.doc.model
        b = self._bone()
        if not m or not b or not self.ik_link_combo.count():
            return
        bone = int(self.ik_link_combo.currentData())
        idx = self.idx

        def fn(mm):
            bb = mm.bones[idx]
            if bb.ik is None:
                from ..pmx import IK
                bb.ik = IK(target=-1, links=[])
                bb.flags |= BF_IK
            bb.ik.links.append(IKLink(bone=bone))
        self.edit("添加 IK 链接", fn, "bone")
        self._fill()

    def _ik_link_del(self):
        if self.loading:
            return
        b = self._bone()
        row = self.ik_links.currentRow()
        if not b or not b.ik or row < 0:
            return
        idx = self.idx

        def fn(mm):
            bb = mm.bones[idx]
            if bb.ik and 0 <= row < len(bb.ik.links):
                del bb.ik.links[row]
        self.edit("移除 IK 链接", fn, "bone")
        self._fill()

    def _link_limit_changed(self, on: bool):
        link = self._link()
        if self.loading or link is None or bool(link.limited) == bool(on):
            return
        row = self.ik_links.currentRow()
        idx = self.idx

        def fn(mm):
            lk = mm.bones[idx].ik.links[row]
            lk.limited = bool(on)
        self.edit("修改 IK 角度限制", fn, "bone", "bone.iklimit")
        self._fill()

    def _link_range_changed(self, which: int):
        link = self._link()
        if self.loading or link is None:
            return
        vals = [math.radians(x) for x in
                (self.link_lo.value() if which == 0 else self.link_hi.value())]
        cur = link.lo if which == 0 else link.hi
        if all(abs(float(c) - v) < 1e-6 for c, v in zip(cur, vals)):
            return
        row = self.ik_links.currentRow()
        idx = self.idx

        def fn(mm):
            lk = mm.bones[idx].ik.links[row]
            if which == 0:
                lk.lo = list(vals)
            else:
                lk.hi = list(vals)
        self.edit("修改 IK 角度范围", fn, "bone", "bone.ikrange")

    # ------------------------------------------------------------ 编辑
    def _name_changed(self):
        b = self._bone()
        if not b or self.loading:
            return
        v = self.name_edit.text()
        if v != b.name:
            self.edit("重命名骨骼", lambda m: setattr(m.bones[self.idx], "name", v),
                      "bone", "bone.name")

    def _name_en_changed(self):
        b = self._bone()
        if not b or self.loading:
            return
        v = self.name_en_edit.text()
        if v != b.name_en:
            self.edit("修改骨骼英文名", lambda m: setattr(m.bones[self.idx], "name_en", v),
                      "bone", "bone.name_en")

    def _parent_changed(self, _i):
        if self.loading:
            return
        m = self.doc.model
        b = self._bone()
        if not m or not b:
            return
        p = self.parent_combo.currentData()
        if p is None:
            return
        p = int(p)
        if p == b.parent:
            return
        if p >= 0 and _cycle(m, self.idx, p):
            self._fill()
            self.set_hint("不能设置形成环路的父骨骼")
            return
        self.edit("修改父骨骼", lambda mm: setattr(mm.bones[self.idx], "parent", p),
                  "structure", "bone.parent")

    def _layer_changed(self, v):
        if self.loading:
            return
        self.edit("修改变形层级", lambda m: setattr(m.bones[self.idx], "layer", int(v)),
                  "bone", "bone.layer")

    def _move_verts_toggled(self, on):
        Config.load().set("editor/move_bone_vertices", bool(on))

    def _pos_changed(self):
        if self.loading:
            return
        v = [float(x) for x in self.pos_spin.value()]
        idx = self.idx
        move = self.move_verts_sw.isChecked()

        def apply(m):
            b = m.bones[idx]
            if move:
                delta = [v[0] - float(b.pos[0]), v[1] - float(b.pos[1]),
                         v[2] - float(b.pos[2])]
                b.pos = list(v)
                if any(delta):
                    shift_bone_vertices(m, idx, delta)
            else:
                b.pos = list(v)

        self.edit("移动骨骼并带动顶点" if move else "移动骨骼", apply,
                  "structure", "bone.pos")

    def _conn_changed(self, key):
        if self.loading:
            return
        self.conn_stack.setCurrentIndex(1 if key == "bone" else 0)
        self.edit("修改连接方式", lambda m: _set_flag(
            m.bones[self.idx], BF_TAIL_INDEX, key == "bone"), "bone")

    def _tail_offset_changed(self):
        if self.loading:
            return
        v = self.tail_spin.value()
        self.edit("修改尾端偏移", lambda m: setattr(m.bones[self.idx], "tail_offset", list(v)),
                  "bone", "bone.tail")

    def _tail_bone_changed(self, _i):
        if self.loading:
            return
        v = self.tail_combo.currentData()
        if v is None or v < 0:
            return
        self.edit("修改尾端骨骼", lambda m: setattr(m.bones[self.idx], "tail_bone", int(v)),
                  "bone")

    def _flag_changed(self, flag: int, on: bool):
        if self.loading:
            return
        self.edit("修改骨骼标志", lambda m: _set_flag(m.bones[self.idx], flag, on), "bone")

    def _inherit_changed(self, _i):
        if self.loading:
            return
        v = self.inherit_parent.currentData()
        if v is None:
            return
        self.edit("修改付与父级", lambda m: setattr(m.bones[self.idx], "append_parent", int(v)),
                  "bone")

    def _inherit_ratio_changed(self, v):
        if self.loading:
            return
        self.edit("修改付与率",
                  lambda m: setattr(m.bones[self.idx], "append_ratio", float(v)),
                  "bone", "bone.ratio")

    def _inherit_flag(self, flag: int, on: bool):
        if self.loading:
            return
        self.edit("修改付与标志", lambda m: _set_flag(m.bones[self.idx], flag, on), "bone")
        inherit_on = on or bool(self._bone() and (self._bone().flags & (
            BF_INHERIT_ROT | BF_INHERIT_MOV)))
        self.inherit_parent.setEnabled(inherit_on)
        self.inherit_ratio.setEnabled(inherit_on)

    def _axis_flag_changed(self, flag: int, on: bool):
        if self.loading:
            return
        self.edit("修改轴标志", lambda m: _set_flag(m.bones[self.idx], flag, on), "bone")
        if flag == BF_FIXED_AXIS:
            self.axis_spin.set_enabled(on)
        else:
            self.localx_spin.set_enabled(on)
            self.localz_spin.set_enabled(on)

    def _axis_changed(self):
        if self.loading:
            return
        v = self.axis_spin.value()
        self.edit("修改固定轴", lambda m: setattr(m.bones[self.idx], "axis", list(v)),
                  "bone", "bone.axis")

    def _localx_changed(self):
        if self.loading:
            return
        v = self.localx_spin.value()
        self.edit("修改局部 X 轴", lambda m: setattr(m.bones[self.idx], "local_x", list(v)),
                  "bone", "bone.localx")

    def _localz_changed(self):
        if self.loading:
            return
        v = self.localz_spin.value()
        self.edit("修改局部 Z 轴", lambda m: setattr(m.bones[self.idx], "local_z", list(v)),
                  "bone", "bone.localz")

    def _ik_toggled(self, on: bool):
        if self.loading:
            return
        m = self.doc.model
        if not m:
            return

        def fn(mm):
            b = mm.bones[self.idx]
            if on:
                from ..pmx import IK
                _set_flag(b, BF_IK, True)
                b.ik = IK(target=-1, links=[])
            else:
                _set_flag(b, BF_IK, False)
                b.ik = None

        self.edit("切换 IK", fn, "bone", "bone.ik")
        self.loading = True
        try:
            self._fill()
        finally:
            self.loading = False

    def _ik_target_changed(self, _i):
        if self.loading:
            return
        v = self.ik_target.currentData()
        b = self._bone()
        if b is None or b.ik is None or v is None:
            return
        self.edit("修改 IK 目标", lambda m: setattr(m.bones[self.idx].ik, "target", int(v)),
                  "bone")

    def _ik_loop_changed(self, v):
        if self.loading:
            return
        b = self._bone()
        if b is None or b.ik is None:
            return
        self.edit("修改 IK 循环", lambda m: setattr(m.bones[self.idx].ik, "loop", int(v)),
                  "bone", "bone.ikloop")

    def _ik_angle_changed(self, v):
        if self.loading:
            return
        b = self._bone()
        if b is None or b.ik is None:
            return
        self.edit("修改 IK 单次角度",
                  lambda m: setattr(m.bones[self.idx].ik, "angle", math.radians(float(v))),
                  "bone", "bone.ikangle")

    def _move_bone(self, delta: int):
        m = self.doc.model
        if not m or not (0 <= self.idx < len(m.bones)):
            return
        old = self.idx
        new = old + int(delta)
        if not (0 <= new < len(m.bones)):
            return
        self.doc.push_undo("调整骨骼顺序")
        move_bone(m, old, delta)
        self.doc.mark_dirty()
        self.doc.edited.emit("structure")
        self.doc.select("bone", new)

    # ------------------------------------------------------------ 结构
    def _add(self):
        m = self.doc.model
        if not m:
            return
        parent = self.idx
        self.doc.push_undo("新建骨骼")
        idx = add_bone(m, parent)
        self.doc.mark_dirty()
        self.doc.edited.emit("structure")
        self.doc.select("bone", idx)

    def _duplicate(self):
        m = self.doc.model
        if not m or self.idx < 0:
            return
        self.doc.push_undo("复制骨骼")
        idx = duplicate_bone(m, self.idx)
        self.doc.mark_dirty()
        self.doc.edited.emit("structure")
        self.doc.select("bone", idx)

    def _remove(self):
        m = self.doc.model
        if not m or self.idx < 0:
            return
        b = m.bones[self.idx]
        dlg = ConfirmDialog("删除骨骼", "确定删除「%s」？\n引用此骨骼的权重、刚体与形态将被重映射。"
                            % b.name, danger=True, parent=self)
        if dlg.exec_() != dlg.Accepted:
            return
        self.doc.push_undo("删除骨骼")
        idx = remove_bone(m, self.idx)
        self.doc.mark_dirty()
        self.doc.edited.emit("structure")
        self.doc.select("bone", idx)


def _set_flag(bone, flag: int, on: bool):
    if on:
        bone.flags |= flag
    else:
        bone.flags &= ~flag
