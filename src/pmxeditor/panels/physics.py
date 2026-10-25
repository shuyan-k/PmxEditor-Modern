"""物理页（刚体 / 关节）。"""
from __future__ import annotations

# -*- coding: utf-8 -*-
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLineEdit, QSizePolicy, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)
from ..doc import (add_joint, add_rigid, duplicate_joint, duplicate_rigid, remove_joint, remove_rigid)
from ..gl_names import bone_zh
from ..theme import ACCENT_2, DANGER, GROUP_COLORS
from ..ui_widgets import (AxisSpin, Card, ConfirmDialog, EntryList, Form, Segmented, SearchEdit, label, make_spin, text_button)
from .base import _deg, _fill_combo, _rad, _bone_combo_items, PageBase

# ================================================================= 物理

class PhysicsPage(PageBase):
    def __init__(self, doc, parent=None):
        super().__init__(doc, "物理", "Bullet 刚体与关节", parent)
        self.kind = "rigid"
        self.add_tool("plus", "新建刚体 / 关节", self._add)
        self.add_tool("duplicate", "复制当前项目", self._duplicate)
        self.add_tool("trash", "删除当前项目", self._remove, DANGER)
        self.seg = Segmented([("rigid", "刚体"), ("joint", "关节")])
        self.seg.changed.connect(self._switch_kind)
        self.root.addWidget(self.seg)
        self.search = SearchEdit("搜索名称 / 关联骨骼")
        self.search.changed.connect(self._refresh_list)
        self.root.addWidget(self.search)
        self.list = EntryList("dot")
        self.list.indexSelected.connect(self._on_list)
        # 列表当前展示的类型；select() 只在类型变化时重建列表。
        # 每次选中都重建会把外部持有的 QModelIndex 变成悬空指针（Qt 侧直接崩溃）。
        self._list_kind = None
        holder = Card()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(6, 6, 6, 6)
        hl.addWidget(self.list)
        self.root.addWidget(holder, 1)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_rigid_editor())
        self.stack.addWidget(self._build_joint_editor())
        self.root.addWidget(self.stack, 3)
        self._set_enabled(False)

    # ------------------------------------------------------------ 刚体编辑
    def _build_rigid_editor(self):
        self.rigid_detail = QWidget()
        dl = QVBoxLayout(self.rigid_detail)
        dl.setContentsMargins(0, 0, 2, 4)
        dl.setSpacing(8)
        card, sec = self._card("基本")
        form = Form(64)
        self.rb_name = QLineEdit()
        self.rb_name_en = QLineEdit()
        self.rb_bone = QComboBox()
        self.rb_mode = Segmented([("0", "跟随"), ("1", "演算"), ("2", "演算+对齐")])
        form.add("名称", self.rb_name)
        form.add("英文名", self.rb_name_en)
        form.add("关联骨骼", self.rb_bone)
        form.add("刚体模式", self.rb_mode)
        sec.add(form)
        self.rb_name.editingFinished.connect(self._rb_name_changed)
        self.rb_name_en.editingFinished.connect(self._rb_name_en_changed)
        self.rb_bone.currentIndexChanged.connect(self._rb_bone_changed)
        self.rb_mode.changed.connect(self._rb_mode_changed)
        dl.addWidget(card)

        card, sec = self._card("形状与变换", "旋转以角度显示")
        form = Form(64)
        self.rb_shape = Segmented([("0", "球"), ("1", "箱"), ("2", "胶囊")])
        self.rb_size = AxisSpin(4, 0.01, 0.0, 9999.0)
        self.rb_pos = AxisSpin(4, 0.01)
        self.rb_rot = AxisSpin(1, 5.0)
        form.add("形状", self.rb_shape)
        form.add("尺寸", self.rb_size)
        form.add("位置", self.rb_pos)
        form.add("旋转", self.rb_rot)
        sec.add(form)
        self.rb_shape.changed.connect(self._rb_shape_changed)
        self.rb_size.valueChanged.connect(self._rb_size_changed)
        self.rb_pos.valueChanged.connect(self._rb_pos_changed)
        self.rb_rot.valueChanged.connect(self._rb_rot_changed)
        dl.addWidget(card)

        card, sec = self._card("物理参数")
        form = Form(64)
        self.rb_mass = make_spin(3, 0.0, 1000.0, 0.1)
        self.rb_mdamp = make_spin(4, 0.0, 1.0, 0.01)
        self.rb_rdamp = make_spin(4, 0.0, 1.0, 0.01)
        self.rb_repel = make_spin(4, 0.0, 1.0, 0.01)
        self.rb_friction = make_spin(4, 0.0, 1.0, 0.01)
        form.add("质量", self.rb_mass)
        form.add("移动衰减", self.rb_mdamp)
        form.add("旋转衰减", self.rb_rdamp)
        form.add("反弹力", self.rb_repel)
        form.add("摩擦力", self.rb_friction)
        sec.add(form)
        self.rb_mass.valueChanged.connect(self._rb_mass_changed)
        self.rb_mdamp.valueChanged.connect(self._rb_mdamp_changed)
        self.rb_rdamp.valueChanged.connect(self._rb_rdamp_changed)
        self.rb_repel.valueChanged.connect(self._rb_repel_changed)
        self.rb_friction.valueChanged.connect(self._rb_friction_changed)
        dl.addWidget(card)

        card, sec = self._card("碰撞组", "组号 0–15；勾选可碰撞的组")
        form = Form(64)
        self.rb_group = QSpinBox()
        self.rb_group.setRange(0, 15)
        self.rb_group.setButtonSymbols(QSpinBox.NoButtons)
        self.rb_group.setKeyboardTracking(False)
        form.add("所属组", self.rb_group)
        sec.add(form)
        self.rb_group.valueChanged.connect(self._rb_group_changed)
        self.mask_box = QWidget()
        mg = QGridLayout(self.mask_box)
        mg.setContentsMargins(0, 2, 0, 0)
        mg.setHorizontalSpacing(2)
        mg.setVerticalSpacing(2)
        self.mask_checks = []
        for g in range(16):
            cb = QCheckBox(str(g))
            cb.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            cb.setStyleSheet("color:%s; font-size:8pt; spacing:3px;"
                             "QCheckBox::indicator{width:12px;height:12px;}"
                             % GROUP_COLORS[g])
            cb.toggled.connect(lambda on, g=g: self._mask_toggled(g, on))
            self.mask_checks.append(cb)
            mg.addWidget(cb, g // 4, g % 4)
        sec.add(self.mask_box)
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
        self.rb_warn = label("", "WarnText", True)
        dl.addWidget(self.rb_warn)
        dl.addStretch(1)
        return self.scroll(self.rigid_detail)

    # ------------------------------------------------------------ 关节编辑
    def _build_joint_editor(self):
        self.joint_detail = QWidget()
        dl = QVBoxLayout(self.joint_detail)
        dl.setContentsMargins(0, 0, 2, 4)
        dl.setSpacing(8)
        card, sec = self._card("基本")
        form = Form(64)
        self.jt_name = QLineEdit()
        self.jt_name_en = QLineEdit()
        self.jt_type = Segmented([("0", "弹簧"), ("1", "6DOF"), ("2", "P2P"),
                                  ("3", "锥形"), ("4", "滑块"), ("5", "铰链")])
        self.jt_a = QComboBox()
        self.jt_b = QComboBox()
        self.jt_pos = AxisSpin(4, 0.01)
        self.jt_rot = AxisSpin(1, 5.0)
        form.add("名称", self.jt_name)
        form.add("英文名", self.jt_name_en)
        form.add("类型", self.jt_type)
        form.add("刚体 A", self.jt_a)
        form.add("刚体 B", self.jt_b)
        form.add("位置", self.jt_pos)
        form.add("旋转", self.jt_rot)
        sec.add(form)
        self.jt_name.editingFinished.connect(self._jt_name_changed)
        self.jt_name_en.editingFinished.connect(self._jt_name_en_changed)
        self.jt_type.changed.connect(self._jt_type_changed)
        self.jt_a.currentIndexChanged.connect(self._jt_a_changed)
        self.jt_b.currentIndexChanged.connect(self._jt_b_changed)
        self.jt_pos.valueChanged.connect(self._jt_pos_changed)
        self.jt_rot.valueChanged.connect(self._jt_rot_changed)
        dl.addWidget(card)

        card, sec = self._card("移动限制")
        form = Form(64)
        self.jt_min_loc = AxisSpin(4, 0.01, -9999.0, 9999.0)
        self.jt_max_loc = AxisSpin(4, 0.01, -9999.0, 9999.0)
        form.add("最小", self.jt_min_loc)
        form.add("最大", self.jt_max_loc)
        sec.add(form)
        self.jt_min_loc.valueChanged.connect(self._jt_limits_changed)
        self.jt_max_loc.valueChanged.connect(self._jt_limits_changed)
        dl.addWidget(card)

        card, sec = self._card("旋转限制", "以角度显示；最小 > 最大 表示自由轴")
        form = Form(64)
        self.jt_min_rot = AxisSpin(1, 5.0, -360.0, 360.0)
        self.jt_max_rot = AxisSpin(1, 5.0, -360.0, 360.0)
        form.add("最小", self.jt_min_rot)
        form.add("最大", self.jt_max_rot)
        sec.add(form)
        self.jt_min_rot.valueChanged.connect(self._jt_limits_changed)
        self.jt_max_rot.valueChanged.connect(self._jt_limits_changed)
        dl.addWidget(card)

        card, sec = self._card("弹簧", "仅弹簧 6DOF 生效")
        form = Form(64)
        self.jt_spr_loc = AxisSpin(3, 0.1, 0.0, 999.0)
        self.jt_spr_rot = AxisSpin(3, 0.1, 0.0, 999.0)
        form.add("移动弹簧", self.jt_spr_loc)
        form.add("旋转弹簧", self.jt_spr_rot)
        sec.add(form)
        self.jt_spr_loc.valueChanged.connect(self._jt_spring_changed)
        self.jt_spr_rot.valueChanged.connect(self._jt_spring_changed)
        dl.addWidget(card)
        self.jt_warn = label("", "WarnText", True)
        dl.addWidget(self.jt_warn)
        dl.addStretch(1)
        return self.scroll(self.joint_detail)

    # ------------------------------------------------------------ 通用
    def _set_enabled(self, on: bool):
        self.stack.setEnabled(on)

    def _switch_kind(self, key):
        if key == self.kind:
            return
        self.kind = key
        self.idx = -1
        self.stack.setCurrentIndex(0 if key == "rigid" else 1)
        self._refresh_list()
        self._set_enabled(False)
        m = self.doc.model
        if m is None:
            return
        # 切换类型后选中新类型的第一项，而不是把选择整个清空
        if (len(m.rigid) if key == "rigid" else len(m.joints)):
            self.doc.select(key, 0)
        else:
            self.doc.select("", -1)

    def _refresh_list(self, *_):
        self._list_kind = self.kind
        m = self.doc.model
        if not m:
            self._show_empty()
            self._set_enabled(False)
            return
        kw = self.search.text().strip().lower()
        entries = []
        if self.kind == "rigid":
            for i, rb in enumerate(m.rigid):
                bn = m.bones[rb.bone].name if 0 <= rb.bone < len(m.bones) else "未关联"
                zh = bone_zh(bn) if bn else ""
                text = "%s  %s" % (bn, zh) if zh and zh != bn else bn
                if kw and kw not in rb.name.lower() and kw not in text.lower():
                    continue
                entries.append({
                    "name": rb.name or "未命名刚体",
                    "hint": text,
                    "right": "组 %d" % rb.group,
                    "color": GROUP_COLORS[rb.group % 16],
                    "index": i,
                    "dim": rb.mode == 0,
                })
            self.set_hint("刚体 %d 个" % len(m.rigid))
        else:
            for i, jt in enumerate(m.joints):
                if kw and kw not in jt.name.lower():
                    continue
                entries.append({
                    "name": jt.name or "未命名关节",
                    "hint": "%s · %d → %d" % (["弹簧 6DOF", "6DOF", "P2P", "锥形",
                                               "滑块", "铰链"][min(5, max(0, jt.type))],
                                              jt.rigid_a, jt.rigid_b),
                    "right": "J%d" % i,
                    "color": ACCENT_2,
                    "index": i,
                })
            self.set_hint("关节 %d 个" % len(m.joints))
        self._show_entries(entries)

    def refresh(self):
        m = self.doc.model
        if not m:
            self.idx = -1
            self.kind = "rigid"
            self.seg.set_value(self.kind)
            self.stack.setCurrentIndex(0)
            self._refresh_list()
            self._set_enabled(False)
            self.set_hint("未载入模型")
            return
        if self.doc.sel_kind in ("rigid", "joint"):
            self.kind = "rigid" if self.doc.sel_kind == "rigid" else "joint"
            self.seg.set_value(self.kind)
            self.stack.setCurrentIndex(0 if self.kind == "rigid" else 1)
            self.idx = self.doc.sel_index
        self._refresh_list()
        count = len(m.rigid) if self.kind == "rigid" else len(m.joints)
        if not (0 <= self.idx < count):
            self.idx = 0
            self._select_row(0)
        if self.kind == "rigid" and 0 <= self.idx < len(m.rigid):
            self._set_enabled(True)
            self._fill_rigid()
        elif self.kind == "joint" and 0 <= self.idx < len(m.joints):
            self._set_enabled(True)
            self._fill_joint()
        else:
            self._set_enabled(False)
            self.idx = -1

    def select(self, kind: str, index: int):
        if kind not in ("rigid", "joint"):
            return
        self.kind = "rigid" if kind == "rigid" else "joint"
        with self._suspend():
            self.seg.set_value(self.kind)
            self.stack.setCurrentIndex(0 if kind == "rigid" else 1)
            # 同类型选中时列表内容不变；重建会清掉模型里的条目，
            # 让调用方（或 Qt 正在处理的选中事件）手里的索引失效。
            if self._list_kind != self.kind:
                self._refresh_list()
            self.list.select_data_index(index)
        self.idx = index
        self._set_enabled(True)
        if kind == "rigid":
            self._fill_rigid()
        else:
            self._fill_joint()

    def _on_list(self, i):
        self._select_from_list(self.kind, i)

    def _rigid(self):
        m = self.doc.model
        if m and 0 <= self.idx < len(m.rigid):
            return m.rigid[self.idx]
        return None

    def _joint(self):
        m = self.doc.model
        if m and 0 <= self.idx < len(m.joints):
            return m.joints[self.idx]
        return None

    def _fill_rigid(self):
        m = self.doc.model
        rb = self._rigid()
        if not m or not rb:
            return
        with self._suspend():
            self.rb_name.setText(rb.name)
            self.rb_name_en.setText(rb.name_en)
            _fill_combo(self.rb_bone, _bone_combo_items(m), rb.bone, empty=(-1, "（未关联）"))
            self.rb_mode.set_value(str(int(rb.mode)))
            self.rb_shape.set_value(str(int(rb.shape)))
            self.rb_size.set_value(rb.size)
            self.rb_pos.set_value(rb.pos)
            self.rb_rot.set_value(_deg(rb.rot))
            self.rb_mass.setValue(float(rb.mass))
            self.rb_mdamp.setValue(float(rb.mov_damp))
            self.rb_rdamp.setValue(float(rb.rot_damp))
            self.rb_repel.setValue(float(rb.repel))
            self.rb_friction.setValue(float(rb.friction))
            self.rb_group.setValue(int(rb.group))
            for g, cb in enumerate(self.mask_checks):
                cb.setChecked(bool(rb.mask & (1 << g)))
            dims = {0: "半径", 1: "半宽 X / 高 Y / 深 Z", 2: "半径 / 总高 / -"}
            self.rb_size.setToolTip(dims.get(int(rb.shape), ""))
        warns = []
        if int(rb.mode) == 0 and float(rb.mass) > 0:
            warns.append("骨骼跟随模式的刚体质量为 0，导出时可能被修正")
        if int(rb.mode) != 0 and float(rb.mass) <= 0:
            warns.append("物理演算刚体的质量为 0，Bullet 中不会运动")
        self.rb_warn.setText("\n".join(warns))

    def _fill_joint(self):
        m = self.doc.model
        jt = self._joint()
        if not m or not jt:
            return
        with self._suspend():
            self.jt_name.setText(jt.name)
            self.jt_name_en.setText(jt.name_en)
            self.jt_type.set_value(str(int(jt.type)))
            self.jt_a.blockSignals(True)
            self.jt_a.clear()
            for i, rb in enumerate(m.rigid):
                self.jt_a.addItem("%02d · %s" % (i, rb.name or "未命名"), i)
            self.jt_a.setCurrentIndex(self.jt_a.findData(jt.rigid_a))
            self.jt_a.blockSignals(False)
            self.jt_b.blockSignals(True)
            self.jt_b.clear()
            for i, rb in enumerate(m.rigid):
                self.jt_b.addItem("%02d · %s" % (i, rb.name or "未命名"), i)
            self.jt_b.setCurrentIndex(self.jt_b.findData(jt.rigid_b))
            self.jt_b.blockSignals(False)
            self.jt_pos.set_value(jt.pos)
            self.jt_rot.set_value(_deg(jt.rot))
            self.jt_min_loc.set_value(jt.min_loc)
            self.jt_max_loc.set_value(jt.max_loc)
            self.jt_min_rot.set_value(_deg(jt.min_rot))
            self.jt_max_rot.set_value(_deg(jt.max_rot))
            self.jt_spr_loc.set_value(jt.spring_loc)
            self.jt_spr_rot.set_value(jt.spring_rot)
        warns = []
        for i, ax in enumerate("XYZ"):
            if jt.min_rot[i] > jt.max_rot[i]:
                warns.append("%s 轴旋转 min > max：自由轴（MMD 中不限制）" % ax)
            if jt.min_loc[i] > jt.max_loc[i]:
                warns.append("%s 轴移动 min > max：自由轴" % ax)
        self.jt_warn.setText("\n".join(warns))

    # ------------------------------------------------------------ 刚体编辑
    def _rb_name_changed(self):
        rb = self._rigid()
        if not rb or self.loading:
            return
        v = self.rb_name.text()
        if v != rb.name:
            self.edit("重命名刚体", lambda m: setattr(m.rigid[self.idx], "name", v),
                      "physics", "rb.name")

    def _rb_name_en_changed(self):
        rb = self._rigid()
        if not rb or self.loading:
            return
        v = self.rb_name_en.text()
        if v != rb.name_en:
            self.edit("修改刚体英文名",
                      lambda m: setattr(m.rigid[self.idx], "name_en", v),
                      "physics", "rb.name_en")

    def _rb_bone_changed(self, _i):
        if self.loading:
            return
        v = self.rb_bone.currentData()
        if v is None:
            return
        self.edit("修改刚体骨骼",
                  lambda m: setattr(m.rigid[self.idx], "bone", int(v)),
                  "physics", "rb.bone")

    def _rb_mode_changed(self, key):
        if self.loading:
            return
        self.edit("修改刚体模式",
                  lambda m: setattr(m.rigid[self.idx], "mode", int(key)),
                  "physics", "rb.mode")

    def _rb_shape_changed(self, key):
        if self.loading:
            return
        self.edit("修改刚体形状",
                  lambda m: setattr(m.rigid[self.idx], "shape", int(key)),
                  "physics", "rb.shape")
        dims = {0: "半径", 1: "半宽 X / 高 Y / 深 Z", 2: "半径 / 总高 / -"}
        self.rb_size.setToolTip(dims.get(int(key), ""))

    def _rb_size_changed(self):
        if self.loading:
            return
        v = self.rb_size.value()
        self.edit("修改刚体尺寸", lambda m: setattr(m.rigid[self.idx], "size", list(v)),
                  "physics", "rb.size")

    def _rb_pos_changed(self):
        if self.loading:
            return
        v = self.rb_pos.value()
        self.edit("移动刚体", lambda m: setattr(m.rigid[self.idx], "pos", list(v)),
                  "physics", "rb.pos")

    def _rb_rot_changed(self):
        if self.loading:
            return
        v = _rad(self.rb_rot.value())
        self.edit("旋转刚体", lambda m: setattr(m.rigid[self.idx], "rot", list(v)),
                  "physics", "rb.rot")

    def _rb_mass_changed(self, v):
        if self.loading:
            return
        # 质量可以热更新到 Bullet（静态/运动学刚体除外），无需重建物理世界
        self.edit("修改质量", lambda m: setattr(m.rigid[self.idx], "mass", float(v)),
                  "physics_live", "rb.mass")

    def _rb_mdamp_changed(self, v):
        if self.loading:
            return
        self.edit("修改移动衰减",
                  lambda m: setattr(m.rigid[self.idx], "mov_damp", float(v)),
                  "physics", "rb.mdamp")

    def _rb_rdamp_changed(self, v):
        if self.loading:
            return
        self.edit("修改旋转衰减",
                  lambda m: setattr(m.rigid[self.idx], "rot_damp", float(v)),
                  "physics", "rb.rdamp")

    def _rb_repel_changed(self, v):
        if self.loading:
            return
        self.edit("修改反弹力", lambda m: setattr(m.rigid[self.idx], "repel", float(v)),
                  "physics", "rb.repel")

    def _rb_friction_changed(self, v):
        if self.loading:
            return
        self.edit("修改摩擦力", lambda m: setattr(m.rigid[self.idx], "friction", float(v)),
                  "physics_live", "rb.friction")

    def _rb_group_changed(self, v):
        if self.loading:
            return
        self.edit("修改刚体组", lambda m: setattr(m.rigid[self.idx], "group", int(v)),
                  "physics", "rb.group")
        self._refresh_list()

    def _mask_toggled(self, g, on):
        if self.loading:
            return

        def fn(m):
            rb = m.rigid[self.idx]
            rb.mask = (rb.mask | (1 << g)) if on else (rb.mask & ~(1 << g))

        self.edit("修改碰撞掩码", fn, "physics", "rb.mask")

    def _set_mask(self, mask):
        self.edit("修改碰撞掩码",
                  lambda m: setattr(m.rigid[self.idx], "mask", mask), "physics")
        with self._suspend():
            for g, cb in enumerate(self.mask_checks):
                cb.setChecked(bool(mask & (1 << g)))

    # ------------------------------------------------------------ 关节编辑
    def _jt_name_changed(self):
        jt = self._joint()
        if not jt or self.loading:
            return
        v = self.jt_name.text()
        if v != jt.name:
            self.edit("重命名关节", lambda m: setattr(m.joints[self.idx], "name", v),
                      "physics", "jt.name")

    def _jt_name_en_changed(self):
        jt = self._joint()
        if not jt or self.loading:
            return
        v = self.jt_name_en.text()
        if v != jt.name_en:
            self.edit("修改关节英文名",
                      lambda m: setattr(m.joints[self.idx], "name_en", v),
                      "physics", "jt.name_en")

    def _jt_type_changed(self, key):
        if self.loading:
            return
        self.edit("修改关节类型",
                  lambda m: setattr(m.joints[self.idx], "type", int(key)),
                  "physics", "jt.type")

    def _jt_a_changed(self, _i):
        if self.loading:
            return
        v = self.jt_a.currentData()
        if v is None:
            return
        self.edit("修改关节刚体 A",
                  lambda m: setattr(m.joints[self.idx], "rigid_a", int(v)),
                  "physics", "jt.a")

    def _jt_b_changed(self, _i):
        if self.loading:
            return
        v = self.jt_b.currentData()
        if v is None:
            return
        self.edit("修改关节刚体 B",
                  lambda m: setattr(m.joints[self.idx], "rigid_b", int(v)),
                  "physics", "jt.b")

    def _jt_pos_changed(self):
        if self.loading:
            return
        v = self.jt_pos.value()
        self.edit("移动关节", lambda m: setattr(m.joints[self.idx], "pos", list(v)),
                  "physics", "jt.pos")

    def _jt_rot_changed(self):
        if self.loading:
            return
        v = _rad(self.jt_rot.value())
        self.edit("旋转关节", lambda m: setattr(m.joints[self.idx], "rot", list(v)),
                  "physics", "jt.rot")

    def _jt_limits_changed(self):
        if self.loading:
            return
        mn_l, mx_l = self.jt_min_loc.value(), self.jt_max_loc.value()
        mn_r, mx_r = _rad(self.jt_min_rot.value()), _rad(self.jt_max_rot.value())

        def fn(m):
            jt = m.joints[self.idx]
            jt.min_loc, jt.max_loc = list(mn_l), list(mx_l)
            jt.min_rot, jt.max_rot = list(mn_r), list(mx_r)

        self.edit("修改关节限制", fn, "physics", "jt.limits")
        jt = self._joint()
        if jt:
            warns = []
            for i, ax in enumerate("XYZ"):
                if jt.min_rot[i] > jt.max_rot[i]:
                    warns.append("%s 轴旋转 min > max：自由轴" % ax)
                if jt.min_loc[i] > jt.max_loc[i]:
                    warns.append("%s 轴移动 min > max：自由轴" % ax)
            self.jt_warn.setText("\n".join(warns))

    def _jt_spring_changed(self):
        if self.loading:
            return
        a, b = self.jt_spr_loc.value(), self.jt_spr_rot.value()

        def fn(m):
            jt = m.joints[self.idx]
            jt.spring_loc, jt.spring_rot = list(a), list(b)

        self.edit("修改关节弹簧", fn, "physics", "jt.spring")

    # ------------------------------------------------------------ 结构
    def _add(self):
        m = self.doc.model
        if not m:
            return
        self.doc.push_undo("新建刚体" if self.kind == "rigid" else "新建关节")
        if self.kind == "rigid":
            bone = self.doc.sel_index if self.doc.sel_kind == "bone" else -1
            idx = add_rigid(m, bone)
        else:
            idx = add_joint(m)
        self.doc.mark_dirty()
        self.doc.edited.emit("structure")
        self.doc.select(self.kind, idx)

    def _duplicate(self):
        m = self.doc.model
        if not m or self.idx < 0:
            return
        self.doc.push_undo("复制物理项目")
        if self.kind == "rigid":
            idx = duplicate_rigid(m, self.idx)
        else:
            idx = duplicate_joint(m, self.idx)
        self.doc.mark_dirty()
        self.doc.edited.emit("structure")
        self.doc.select(self.kind, idx)

    def _remove(self):
        m = self.doc.model
        if not m or self.idx < 0:
            return
        if self.kind == "rigid":
            name = m.rigid[self.idx].name
        else:
            name = m.joints[self.idx].name
        dlg = ConfirmDialog("删除物理项目", "确定删除「%s」？" % name,
                            danger=True, parent=self)
        if dlg.exec_() != dlg.Accepted:
            return
        self.doc.push_undo("删除物理项目")
        if self.kind == "rigid":
            idx = remove_rigid(m, self.idx)
        else:
            idx = remove_joint(m, self.idx)
        self.doc.mark_dirty()
        self.doc.edited.emit("structure")
        self.doc.select(self.kind, idx)
