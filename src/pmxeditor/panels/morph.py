"""形态页。"""
from __future__ import annotations

# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import (QComboBox, QHBoxLayout, QLabel, QLineEdit, QMenu, QSlider, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)
from ..doc import add_morph, duplicate_morph, remove_morph
from ..gl_names import morph_zh
from ..pmx import MORPH_TYPE_NAMES
from ..theme import (ACCENT, ACCENT_2, BORDER, BORDER_SOFT, DANGER, FIELD_BG, HEADER_BG, TEXT, TEXT_DIM, TEXT_FAINT)
from ..ui_widgets import (Card, ConfirmDialog, EntryList, Form, SearchEdit, label, text_button)
from .base import _vec, PANEL_NAMES, PageBase

# ================================================================= 形态

class MorphPage(PageBase):
    previewChanged = pyqtSignal(dict)

    def __init__(self, doc, parent=None):
        super().__init__(doc, "形态", "表情与变形预览", parent)
        self.add_tool("plus", "新建形态", self._add_menu)
        self.add_tool("duplicate", "复制形态", self._duplicate)
        self.add_tool("trash", "删除形态", self._remove, DANGER)
        self.search = SearchEdit("搜索形态名 / 中文译名")
        self.search.changed.connect(self._refresh_list)
        self.root.addWidget(self.search)
        self.list = EntryList("diamond")
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
        self.panel_combo = QComboBox()
        for k in (1, 2, 3, 4):
            self.panel_combo.addItem(PANEL_NAMES[k], k)
        self.type_label = QLabel("—")
        self.type_label.setObjectName("Faint")
        form.add("名称", self.name_edit)
        form.add("英文名", self.name_en_edit)
        form.add("操作面板", self.panel_combo)
        form.add("类型", self.type_label)
        sec.add(form)
        self.name_edit.editingFinished.connect(self._name_changed)
        self.name_en_edit.editingFinished.connect(self._name_en_changed)
        self.panel_combo.currentIndexChanged.connect(self._panel_changed)
        dl.addWidget(card)

        card, sec = self._card("预览", "仅影响当前视图，不写入文件")
        row = QHBoxLayout()
        self.weight = QSlider(Qt.Horizontal)
        self.weight.setRange(0, 100)
        self.weight.setValue(0)
        self.weight_label = label("0%", "Value")
        self.weight_label.setFixedWidth(38)
        self.weight_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        reset = text_button("清零", "Ghost")
        row.addWidget(self.weight, 1)
        row.addWidget(self.weight_label)
        row.addWidget(reset)
        sec.add_layout(row)
        self.weight.valueChanged.connect(self._preview)
        reset.clicked.connect(lambda: self.weight.setValue(0))
        dl.addWidget(card)

        card, sec = self._card("偏移数据")
        self.offset_table = QTableWidget(0, 2)
        self.offset_table.setHorizontalHeaderLabels(["目标", "数值"])
        self.offset_table.verticalHeader().setVisible(False)
        self.offset_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.offset_table.setSelectionMode(QTableWidget.NoSelection)
        self.offset_table.setShowGrid(False)
        self.offset_table.horizontalHeader().setStretchLastSection(True)
        self.offset_table.horizontalHeader().setVisible(True)
        self.offset_table.setFixedHeight(190)
        self.offset_table.setStyleSheet(
            "QTableWidget{background:%s;border:1px solid %s;border-radius:6px;"
            "color:%s;font-size:8.6pt;}"
            "QHeaderView::section{background:%s;border:none;"
            "border-bottom:1px solid %s;padding:4px 6px;color:%s;font-size:8.4pt;}"
            % (FIELD_BG, BORDER, TEXT, HEADER_BG, BORDER_SOFT, TEXT_DIM))
        sec.add(self.offset_table)
        self.offset_note = label("", "Faint", True)
        sec.add(self.offset_note)
        dl.addWidget(card)
        dl.addStretch(1)
        self.root.addWidget(self.scroll(self.detail), 3)

    def _refresh_list(self, *_):
        m = self.doc.model
        if not m:
            self.list.empty_text = "未载入模型"
            self.list.set_entries([])
            self.detail.setEnabled(False)
            return
        kw = self.search.text().strip().lower()
        entries = []
        for i, mo in enumerate(m.morphs):
            zh = morph_zh(mo.name)
            if kw and kw not in mo.name.lower() and kw not in zh.lower():
                continue
            entries.append({
                "name": mo.name or "未命名形态",
                "hint": "%s · %s%s" % (PANEL_NAMES.get(mo.panel, "其他"),
                                       MORPH_TYPE_NAMES.get(mo.type, "?"),
                                       ("  %s" % zh) if zh and zh != mo.name else ""),
                "right": "%d 项" % len(mo.offsets),
                "color": ACCENT_2,
                "index": i,
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
        self.idx = self.doc.sel_index if self.doc.sel_kind == "morph" else self.idx
        self._refresh_list()
        if m and m.morphs and not (0 <= self.idx < len(m.morphs)):
            self.idx = 0
            self.loading = True
            try:
                self.list.select_data_index(0)
            finally:
                self.loading = False
        if m and 0 <= self.idx < len(m.morphs):
            self.detail.setEnabled(True)
            self._fill()
        else:
            self.detail.setEnabled(False)
            self.idx = -1
            if not m:
                self.weight.blockSignals(True)
                self.weight.setValue(0)
                self.weight_label.setText("0%")
                self.weight.blockSignals(False)
                self.offset_table.setRowCount(0)
                self.offset_note.setText("")

    def select(self, kind: str, index: int):
        if kind != "morph":
            return
        self.idx = index
        self.loading = True
        try:
            self.list.select_data_index(index)
        finally:
            self.loading = False
        m = self.doc.model
        self.detail.setEnabled(bool(m and 0 <= index < len(m.morphs)))
        self._fill()
        # 切换形态时清空预览
        self.weight.blockSignals(True)
        self.weight.setValue(0)
        self.weight_label.setText("0%")
        self.weight.blockSignals(False)
        self.previewChanged.emit({})

    def _on_list(self, i):
        if self.loading:
            return
        self.doc.select("morph", i)

    def _morph(self):
        m = self.doc.model
        if m and 0 <= self.idx < len(m.morphs):
            return m.morphs[self.idx]
        return None

    def _fill(self):
        m = self.doc.model
        mo = self._morph()
        prev = self.loading
        self.loading = True
        try:
            if not m or not mo:
                return
            self.set_hint("索引 %d · %d 个形态" % (self.idx, len(m.morphs)))
            zh = morph_zh(mo.name)
            self.zh_badge.setText(("中文：%s" % zh) if zh and zh != mo.name else "无中文对照")
            self.zh_badge.setStyleSheet("color:%s;" % (ACCENT if zh and zh != mo.name else TEXT_FAINT))
            self.name_edit.setText(mo.name)
            self.name_en_edit.setText(mo.name_en)
            i = self.panel_combo.findData(mo.panel)
            self.panel_combo.setCurrentIndex(i if i >= 0 else 3)
            self.type_label.setText(MORPH_TYPE_NAMES.get(mo.type, "未知"))
            self._fill_offsets(m, mo)
        finally:
            self.loading = prev

    def _fill_offsets(self, m, mo):
        rows = mo.offsets
        cap = 120
        self.offset_table.setRowCount(0)
        for n, off in enumerate(rows[:cap]):
            target, value = self._offset_desc(m, mo, off)
            self.offset_table.insertRow(n)
            a = QTableWidgetItem(target)
            b = QTableWidgetItem(value)
            a.setToolTip(target)
            b.setToolTip(value)
            self.offset_table.setItem(n, 0, a)
            self.offset_table.setItem(n, 1, b)
        self.offset_table.resizeColumnToContents(0)
        if len(rows) > cap:
            self.offset_note.setText("共 %d 项，仅显示前 %d 项" % (len(rows), cap))
        else:
            self.offset_note.setText("共 %d 项" % len(rows))

    def _offset_desc(self, m, mo, off):
        t = mo.type
        if t == 0:
            mi = int(off.get("morph", -1))
            nm = m.morphs[mi].name if 0 <= mi < len(m.morphs) else "?"
            return "形态 · " + nm, "× %.3f" % float(off.get("ratio", 0))
        if t == 1:
            return "顶点 %d" % int(off.get("vertex", -1)), _vec(off.get("offset", []))
        if t == 2:
            bi = int(off.get("bone", -1))
            nm = m.bones[bi].name if 0 <= bi < len(m.bones) else "?"
            return "骨骼 · " + nm, "移动 %s / 旋转 %s" % (
                _vec(off.get("move", [])), _vec(off.get("rot", [])))
        if 3 <= t <= 7:
            return "UV %d" % int(off.get("vertex", -1)), _vec(off.get("offset", []))
        if t == 8:
            mi = int(off.get("material", -1))
            nm = m.materials[mi].name if 0 <= mi < len(m.materials) else "全部材质"
            calc = "加法" if int(off.get("calc", 0)) == 1 else "乘法"
            return "材质 · " + nm, "%s · 漫反射 %s" % (
                calc, _vec(off.get("diffuse", [])[:3]))
        if t == 9:
            mi = int(off.get("morph", -1))
            nm = m.morphs[mi].name if 0 <= mi < len(m.morphs) else "?"
            return "翻转 · " + nm, "× %.3f" % float(off.get("ratio", 0))
        if t == 10:
            ri = int(off.get("rigid", -1))
            nm = m.rigid[ri].name if 0 <= ri < len(m.rigid) else "?"
            return "冲量 · " + nm, "速度 %s / 扭矩 %s" % (
                _vec(off.get("velocity", [])), _vec(off.get("torque", [])))
        return "?", ""

    # ------------------------------------------------------------ 编辑
    def _name_changed(self):
        mo = self._morph()
        if not mo or self.loading:
            return
        v = self.name_edit.text()
        if v != mo.name:
            self.edit("重命名形态", lambda m: setattr(m.morphs[self.idx], "name", v),
                      "morph", "morph.name")

    def _name_en_changed(self):
        mo = self._morph()
        if not mo or self.loading:
            return
        v = self.name_en_edit.text()
        if v != mo.name_en:
            self.edit("修改形态英文名",
                      lambda m: setattr(m.morphs[self.idx], "name_en", v),
                      "morph", "morph.name_en")

    def _panel_changed(self, _i):
        if self.loading:
            return
        v = self.panel_combo.currentData()
        if v is None:
            return
        self.edit("修改操作面板",
                  lambda m: setattr(m.morphs[self.idx], "panel", int(v)), "morph")
        self._refresh_list()

    def _preview(self, v):
        if self.loading or self.idx < 0:
            return
        self.weight_label.setText("%d%%" % v)
        self.previewChanged.emit({self.idx: v / 100.0} if v else {})

    # ------------------------------------------------------------ 结构
    def _add_menu(self):
        m = self.doc.model
        if not m:
            return
        menu = QMenu(self)
        for t in (1, 2, 3, 8, 0, 9, 10):
            menu.addAction("新建%s形态" % MORPH_TYPE_NAMES.get(t, "?"),
                           lambda t=t: self._add(t))
        menu.exec_(QCursor.pos())

    def _add(self, morph_type: int):
        m = self.doc.model
        if not m:
            return
        self.doc.push_undo("新建形态")
        idx = add_morph(m, morph_type)
        self.doc.mark_dirty()
        self.doc.edited.emit("structure")
        self.doc.select("morph", idx)

    def _duplicate(self):
        m = self.doc.model
        if not m or self.idx < 0:
            return
        self.doc.push_undo("复制形态")
        idx = duplicate_morph(m, self.idx)
        self.doc.mark_dirty()
        self.doc.edited.emit("structure")
        self.doc.select("morph", idx)

    def _remove(self):
        m = self.doc.model
        if not m or self.idx < 0:
            return
        mo = m.morphs[self.idx]
        dlg = ConfirmDialog("删除形态", "确定删除「%s」？" % mo.name,
                            danger=True, parent=self)
        if dlg.exec_() != dlg.Accepted:
            return
        self.doc.push_undo("删除形态")
        idx = remove_morph(m, self.idx)
        self.doc.mark_dirty()
        self.doc.edited.emit("structure")
        self.doc.select("morph", idx)
        self.previewChanged.emit({})
