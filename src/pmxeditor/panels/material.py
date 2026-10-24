"""材质页。"""
from __future__ import annotations

# -*- coding: utf-8 -*-
import os
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QSizePolicy, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)
from ..doc import add_material, duplicate_material, remove_material
from ..gl_names import material_zh
from ..pmx import (MF_DOUBLE_SIDED, MF_EDGE, MF_GROUND_SHADOW, MF_SELF_SHADOW, MF_SHADOW_MAP)
from ..theme import ACCENT, DANGER, TEXT_FAINT
from ..ui_widgets import (Card, ColorButton, ConfirmDialog, EntryList, Form, Segmented, Switch, SearchEdit, label, make_spin)
from .base import _fill_combo, PageBase

# ================================================================= 材质

class MaterialPage(PageBase):
    def __init__(self, doc, parent=None):
        super().__init__(doc, "材质", "颜色、贴图与描边", parent)
        self.add_tool("plus", "新建材质", self._add)
        self.add_tool("duplicate", "复制材质", self._duplicate)
        self.add_tool("trash", "删除材质", self._remove, DANGER)
        self.search = SearchEdit("搜索材质名 / 中文译名")
        self.search.changed.connect(self._refresh_list)
        self.root.addWidget(self.search)
        self.list = EntryList("swatch")
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
        self.zh_badge = label("", "Accent")
        sec.add(self.zh_badge)
        form = Form(64)
        self.name_edit = QLineEdit()
        self.name_en_edit = QLineEdit()
        self.face_label = QLabel("0")
        self.face_label.setObjectName("Faint")
        form.add("名称", self.name_edit)
        form.add("英文名", self.name_en_edit)
        form.add("面数", self.face_label)
        sec.add(form)
        self.name_edit.editingFinished.connect(self._name_changed)
        self.name_en_edit.editingFinished.connect(self._name_en_changed)
        dl.addWidget(card)

        card, sec = self._card("颜色")
        form = Form(64)
        self.diffuse = ColorButton([1, 1, 1, 1])
        self.specular = ColorButton([0, 0, 0, 1])
        self.ambient = ColorButton([0.5, 0.5, 0.5, 1])
        self.spec_coef = make_spin(3, 0.0, 200.0, 0.1)
        form.add("漫反射", self.diffuse)
        form.add("高光色", self.specular)
        form.add("高光强度", self.spec_coef)
        form.add("环境色", self.ambient)
        sec.add(form)
        self.diffuse.colorChanged.connect(lambda c: self._color("diffuse", c))
        self.specular.colorChanged.connect(lambda c: self._color("specular", c))
        self.ambient.colorChanged.connect(lambda c: self._color("ambient", c))
        self.spec_coef.valueChanged.connect(self._spec_coef_changed)
        dl.addWidget(card)

        card, sec = self._card("贴图", "")
        form = Form(64)
        self.tex_combo = QComboBox()
        self.sphere_combo = QComboBox()
        self.sphere_seg = Segmented([("0", "无"), ("1", "乘法"), ("2", "加法"), ("3", "子纹理")])
        self.tex_path = label("—", "Faint", True)
        form.add("通常贴图", self.tex_combo)
        form.add_full(self.tex_path)
        form.add("球面贴图", self.sphere_combo)
        form.add("球面模式", self.sphere_seg)
        self.toon_sw = Switch(False)
        row = QHBoxLayout()
        row.addWidget(self.toon_sw)
        row.addWidget(label("共享 Toon", "Muted"))
        row.addStretch(1)
        form.add_full(row)
        self.toon_stack = QStackedWidget()
        self.toon_combo = QComboBox()
        w1 = QWidget()
        l1 = QVBoxLayout(w1)
        l1.setContentsMargins(0, 0, 0, 0)
        l1.addWidget(self.toon_combo)
        w2 = QWidget()
        l2 = QHBoxLayout(w2)
        l2.setContentsMargins(0, 0, 0, 0)
        self.toon_index = QSpinBox()
        self.toon_index.setRange(1, 10)
        self.toon_index.setButtonSymbols(QSpinBox.NoButtons)
        self.toon_index.setKeyboardTracking(False)
        l2.addWidget(self.toon_index)
        l2.addWidget(label("对应 toon01–toon10", "Faint"))
        l2.addStretch(1)
        self.toon_stack.addWidget(w1)
        self.toon_stack.addWidget(w2)
        form.add("Toon", self.toon_stack)
        sec.add(form)
        self.tex_combo.currentIndexChanged.connect(self._tex_changed)
        self.sphere_combo.currentIndexChanged.connect(self._sphere_changed)
        self.sphere_seg.changed.connect(self._sphere_mode_changed)
        self.toon_sw.toggled.connect(self._toon_shared_changed)
        self.toon_combo.currentIndexChanged.connect(self._toon_changed)
        self.toon_index.valueChanged.connect(self._toon_index_changed)
        dl.addWidget(card)

        card, sec = self._card("描边与阴影")
        self.edge_color = ColorButton([0, 0, 0, 1])
        self.edge_size = make_spin(4, 0.0, 100.0, 0.1)
        form = Form(64)
        form.add("描边颜色", self.edge_color)
        form.add("描边大小", self.edge_size)
        sec.add(form)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        self.flags = {}
        for i, (key, txt, flag) in enumerate((
                ("double", "双面显示", MF_DOUBLE_SIDED),
                ("ground", "地面阴影", MF_GROUND_SHADOW),
                ("shadow", "自阴影", MF_SELF_SHADOW),
                ("map", "阴影贴图", MF_SHADOW_MAP),
                ("edge", "描边", MF_EDGE))):
            cb = QCheckBox(txt)
            # 复选框只让"指示器+文字"可点（QSS 带 padding 时 QStyleSheetStyle 的
            # SE_CheckBoxClickRect 只覆盖这段），把控件宽度收到 sizeHint 才不会出现右侧死区
            cb.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
            cb.toggled.connect(lambda on, f=flag: self._flag_changed(f, on))
            self.flags[key] = cb
            grid.addWidget(cb, i // 2, i % 2)
        sec.add_layout(grid)
        self.edge_color.colorChanged.connect(self._edge_color_changed)
        self.edge_size.valueChanged.connect(self._edge_size_changed)
        dl.addWidget(card)

        card, sec = self._card("备注")
        self.memo = QLineEdit()
        sec.add(self.memo)
        self.memo.editingFinished.connect(self._memo_changed)
        dl.addWidget(card)
        dl.addStretch(1)
        self.root.addWidget(self.scroll(self.detail), 3)

    # ------------------------------------------------------------ 列表
    def _refresh_list(self, *_):
        m = self.doc.model
        if not m:
            self.list.empty_text = "未载入模型"
            self.list.set_entries([])
            self.detail.setEnabled(False)
            return
        kw = self.search.text().strip().lower()
        entries = []
        for i, mt in enumerate(m.materials):
            zh = material_zh(mt.name)
            if kw and kw not in mt.name.lower() and kw not in zh.lower():
                continue
            r = int(mt.diffuse[0] * 255)
            g = int(mt.diffuse[1] * 255)
            b = int(mt.diffuse[2] * 255)
            entries.append({
                "name": mt.name or "未命名材质",
                "hint": zh if zh and zh != mt.name else "",
                "right": "%d 面" % mt.face_count,
                "color": "#%02x%02x%02x" % (r, g, b),
                "index": i,
                "dim": mt.diffuse[3] < 0.5,
            })
        prev = self.loading
        self.loading = True
        try:
            self.list.empty_text = "无匹配结果"
            self.list.set_entries(entries, self.idx)
        finally:
            self.loading = prev

    def refresh(self):
        m = self.doc.model
        if not m:
            self.idx = -1
        self.idx = self.doc.sel_index if self.doc.sel_kind == "material" else self.idx
        self._refresh_list()
        if m and m.materials and not (0 <= self.idx < len(m.materials)):
            self.idx = 0
            self.loading = True
            try:
                self.list.select_data_index(0)
            finally:
                self.loading = False
        if m and 0 <= self.idx < len(m.materials):
            self.detail.setEnabled(True)
            self._fill()
        else:
            self.detail.setEnabled(False)
            self.idx = -1

    def select(self, kind: str, index: int):
        if kind != "material":
            return
        self.idx = index
        self.loading = True
        try:
            self.list.select_data_index(index)
        finally:
            self.loading = False
        m = self.doc.model
        self.detail.setEnabled(bool(m and 0 <= index < len(m.materials)))
        self._fill()

    def _on_list(self, i):
        if self.loading:
            return
        self.doc.select("material", i)

    def _material(self):
        m = self.doc.model
        if m and 0 <= self.idx < len(m.materials):
            return m.materials[self.idx]
        return None

    def _texture_items(self, model):
        out = []
        for i, path in enumerate(model.textures):
            import os
            base = os.path.basename(path.replace("\\", "/"))
            out.append((i, "%d · %s" % (i, base)))
        return out

    def _fill(self):
        m = self.doc.model
        mt = self._material()
        prev = self.loading
        self.loading = True
        try:
            if not m or not mt:
                return
            self._fill_fields(m, mt)
        finally:
            self.loading = prev

    def _fill_fields(self, m, mt):
        self.set_hint("索引 %d · %d 个材质" % (self.idx, len(m.materials)))
        zh = material_zh(mt.name)
        self.zh_badge.setText(("中文：%s" % zh) if zh and zh != mt.name else "无中文对照")
        self.zh_badge.setStyleSheet("color:%s;" % (ACCENT if zh and zh != mt.name else TEXT_FAINT))
        self.name_edit.setText(mt.name)
        self.name_en_edit.setText(mt.name_en)
        self.face_label.setText("%d" % mt.face_count)
        self.diffuse.set_color(mt.diffuse)
        self.specular.set_color(list(mt.specular) + [1.0])
        self.ambient.set_color(list(mt.ambient) + [1.0])
        self.spec_coef.setValue(float(mt.specular_coef))
        items = self._texture_items(m)
        _fill_combo(self.tex_combo, items, mt.texture, empty=(-1, "（无贴图）"))
        _fill_combo(self.sphere_combo, items, mt.sphere, empty=(-1, "（无球面贴图）"))
        self.sphere_seg.set_value(str(int(mt.sphere_mode)))
        self.toon_sw.setChecked(int(mt.toon_shared) == 1)
        self.toon_stack.setCurrentIndex(1 if int(mt.toon_shared) == 1 else 0)
        if int(mt.toon_shared) == 1:
            self.toon_index.setValue(max(1, min(10, int(mt.toon) + 1)))
        else:
            _fill_combo(self.toon_combo, items, mt.toon, empty=(-1, "（无 Toon）"))
        self.edge_color.set_color(mt.edge_color)
        self.edge_size.setValue(float(mt.edge_size))
        self.flags["double"].setChecked(bool(mt.draw_flags & MF_DOUBLE_SIDED))
        self.flags["ground"].setChecked(bool(mt.draw_flags & MF_GROUND_SHADOW))
        self.flags["shadow"].setChecked(bool(mt.draw_flags & MF_SELF_SHADOW))
        self.flags["map"].setChecked(bool(mt.draw_flags & MF_SHADOW_MAP))
        self.flags["edge"].setChecked(bool(mt.draw_flags & MF_EDGE))
        self.memo.setText(mt.memo)
        path = m.resolve_texture(mt.texture) if mt.texture >= 0 else ""
        self.tex_path.setText(path or "—")
        self.tex_path.setToolTip(path)

    # ------------------------------------------------------------ 编辑
    def _name_changed(self):
        mt = self._material()
        if not mt or self.loading:
            return
        v = self.name_edit.text()
        if v != mt.name:
            self.edit("重命名材质", lambda m: setattr(m.materials[self.idx], "name", v),
                      "material", "material.name")

    def _name_en_changed(self):
        mt = self._material()
        if not mt or self.loading:
            return
        v = self.name_en_edit.text()
        if v != mt.name_en:
            self.edit("修改材质英文名",
                      lambda m: setattr(m.materials[self.idx], "name_en", v),
                      "material", "material.name_en")

    def _color(self, field: str, color):
        # ColorButton 发出 RGBA 四分量，而 PMX 的 specular/ambient 只有 RGB
        n = 4 if field in ("diffuse", "edge_color") else 3
        vals = [float(v) for v in list(color)[:4]]
        while len(vals) < n:
            vals.append(1.0)
        vals = vals[:n]
        self.edit("修改颜色", lambda m: setattr(m.materials[self.idx], field,
                                                list(vals)), "material", "material.color")
        self._refresh_list()

    def _spec_coef_changed(self, v):
        if self.loading:
            return
        self.edit("修改高光强度",
                  lambda m: setattr(m.materials[self.idx], "specular_coef", float(v)),
                  "material", "material.spec")

    def _tex_changed(self, _i):
        if self.loading:
            return
        v = self.tex_combo.currentData()
        if v is None:
            return
        self.edit("修改通常贴图", lambda m: setattr(m.materials[self.idx], "texture", int(v)),
                  "material")
        m = self.doc.model
        mt = self._material()
        if m and mt:
            path = m.resolve_texture(mt.texture) if mt.texture >= 0 else ""
            self.tex_path.setText(path or "—")
            self.tex_path.setToolTip(path)

    def _sphere_changed(self, _i):
        if self.loading:
            return
        v = self.sphere_combo.currentData()
        if v is None:
            return
        self.edit("修改球面贴图", lambda m: setattr(m.materials[self.idx], "sphere", int(v)),
                  "material")

    def _sphere_mode_changed(self, key):
        if self.loading:
            return
        self.edit("修改球面模式",
                  lambda m: setattr(m.materials[self.idx], "sphere_mode", int(key)),
                  "material")

    def _toon_shared_changed(self, on: bool):
        if self.loading:
            return
        self.toon_stack.setCurrentIndex(1 if on else 0)

        def fn(m):
            mt = m.materials[self.idx]
            mt.toon_shared = 1 if on else 0
            mt.toon = 0 if on else -1

        self.edit("切换共享 Toon", fn, "material")

    def _toon_changed(self, _i):
        if self.loading:
            return
        v = self.toon_combo.currentData()
        if v is None:
            return
        self.edit("修改 Toon 贴图", lambda m: setattr(m.materials[self.idx], "toon", int(v)),
                  "material")

    def _toon_index_changed(self, v):
        if self.loading:
            return
        self.edit("修改共享 Toon",
                  lambda m: setattr(m.materials[self.idx], "toon", int(v) - 1),
                  "material", "material.toon")

    def _edge_color_changed(self, c):
        self.edit("修改描边颜色",
                  lambda m: setattr(m.materials[self.idx], "edge_color", list(c)),
                  "material", "material.edgecolor")

    def _edge_size_changed(self, v):
        if self.loading:
            return
        self.edit("修改描边大小",
                  lambda m: setattr(m.materials[self.idx], "edge_size", float(v)),
                  "material", "material.edgesize")

    def _flag_changed(self, flag: int, on: bool):
        if self.loading:
            return

        def fn(m):
            mt = m.materials[self.idx]
            mt.draw_flags = (mt.draw_flags | flag) if on else (mt.draw_flags & ~flag)

        self.edit("修改绘制标志", fn, "material")

    def _memo_changed(self):
        mt = self._material()
        if not mt or self.loading:
            return
        v = self.memo.text()
        if v != mt.memo:
            self.edit("修改材质备注", lambda m: setattr(m.materials[self.idx], "memo", v),
                      "material")

    # ------------------------------------------------------------ 结构
    def _add(self):
        m = self.doc.model
        if not m:
            return
        self.doc.push_undo("新建材质")
        idx = add_material(m)
        self.doc.mark_dirty()
        self.doc.edited.emit("structure")
        self.doc.select("material", idx)

    def _duplicate(self):
        m = self.doc.model
        if not m or self.idx < 0:
            return
        self.doc.push_undo("复制材质")
        idx = duplicate_material(m, self.idx)
        self.doc.mark_dirty()
        self.doc.edited.emit("structure")
        self.doc.select("material", idx)

    def _remove(self):
        m = self.doc.model
        if not m or self.idx < 0:
            return
        mt = m.materials[self.idx]
        box = QMessageBox(self)
        box.setWindowTitle("删除材质")
        box.setText("删除「%s」（%d 个三角面）" % (mt.name, int(mt.face_count)))
        box.setInformativeText(
            "「并入上一个材质」保留几何，只把这些面归给上一个材质；"
            "「连同三角面删除」会真正删掉这些面。")
        merge_btn = None
        if self.idx > 0:
            merge_btn = box.addButton("并入上一个材质", QMessageBox.AcceptRole)
        face_btn = box.addButton("连同三角面删除", QMessageBox.DestructiveRole)
        box.addButton("取消", QMessageBox.RejectRole)
        box.exec_()
        clicked = box.clickedButton()
        if merge_btn is not None and clicked is merge_btn:
            self.doc.push_undo("并入材质")
            idx = remove_material(m, self.idx, merge=True)
        elif clicked is face_btn:
            self.doc.push_undo("删除材质")
            idx = remove_material(m, self.idx)
        else:
            return
        self.doc.mark_dirty()
        self.doc.edited.emit("structure")
        self.doc.select("material", idx)
