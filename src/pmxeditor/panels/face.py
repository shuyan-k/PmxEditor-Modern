"""面页：按材质查看三角面区间，并把一段面重分配给其他材质。"""
from __future__ import annotations

# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QComboBox, QHBoxLayout, QSpinBox, QVBoxLayout

from ..doc import reassign_faces
from ..gl_names import material_zh
from ..ui_widgets import Card, EntryList, Form, SearchEdit, label, text_button
from .base import _fill_combo, PageBase


def _face_spin() -> QSpinBox:
    s = QSpinBox()
    s.setRange(0, 0)
    s.setKeyboardTracking(False)
    s.setButtonSymbols(QSpinBox.NoButtons)
    s.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return s


class FacePage(PageBase):
    """原版「面」页的等价入口：查看材质面数并把面移动到别的材质。"""

    def __init__(self, doc, parent=None):
        super().__init__(doc, "面", "按材质查看三角面并重分配", parent)
        self.search = SearchEdit("搜索材质名")
        self.search.changed.connect(self._refresh_list)
        self.root.addWidget(self.search)

        self.list = EntryList("swatch")
        self.list.indexSelected.connect(self._on_list)
        holder = Card()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(6, 6, 6, 6)
        hl.addWidget(self.list)
        self.root.addWidget(holder, 1)

        card, sec = self._card("重分配", "移到目标材质的面会追加在它原有面之后")
        form = Form(64)
        self.src_combo = QComboBox()
        self.start_spin = _face_spin()
        self.count_spin = _face_spin()
        self.dst_combo = QComboBox()
        form.add("源材质", self.src_combo)
        form.add("起始面", self.start_spin)
        form.add("数量", self.count_spin)
        form.add("目标材质", self.dst_combo)
        sec.add(form)
        self.note = label("", "Faint", True)
        sec.add(self.note)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        self.move_btn = text_button("移动这些面", "Primary")
        self.move_btn.clicked.connect(self._move)
        row.addWidget(self.move_btn)
        sec.add_layout(row)
        self.root.addWidget(card)
        self.panel = card
        self.panel.setEnabled(False)

        self.src_combo.currentIndexChanged.connect(self._src_changed)
        self.dst_combo.currentIndexChanged.connect(self._update_note)
        self.start_spin.valueChanged.connect(self._update_note)
        self.count_spin.valueChanged.connect(self._update_note)

    # ------------------------------------------------------------ 列表
    def _refresh_list(self, *_):
        m = self.doc.model
        if not m:
            self.list.empty_text = "未载入模型"
            self.list.set_entries([])
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
                "right": "%d 面" % (int(mt.face_count) // 3),
                "color": "#%02x%02x%02x" % (r, g, b),
                "index": i,
                "dim": int(mt.face_count) <= 0,
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
        self.idx = -1 if not m else self.idx
        if m and self.doc.sel_kind == "material" \
                and 0 <= self.doc.sel_index < len(m.materials):
            self.idx = self.doc.sel_index
        self._refresh_list()
        if m and m.materials and not (0 <= self.idx < len(m.materials)):
            self.idx = 0
            self.loading = True
            try:
                self.list.select_data_index(0)
            finally:
                self.loading = False
        self.panel.setEnabled(bool(m and 0 <= self.idx < len(m.materials)))
        if not m or not m.materials:
            self.idx = -1
            self.note.setText("")
            return
        self.set_hint("共 %d 个三角面 · %d 个材质"
                      % (len(m.indices) // 3, len(m.materials)))
        self._fill()

    def _on_list(self, i):
        if self.loading:
            return
        self.idx = i
        self.loading = True
        try:
            _fill_combo(self.src_combo, self._material_items(), i)
        finally:
            self.loading = False
        self._sync_dst()
        self._update_ranges()
        self._update_note()

    def _src_changed(self, _i):
        if self.loading:
            return
        v = self.src_combo.currentData()
        if v is None:
            return
        self.idx = int(v)
        self.loading = True
        try:
            self.list.select_data_index(self.idx)
        finally:
            self.loading = False
        self._sync_dst()
        self._update_ranges()
        self._update_note()

    # ------------------------------------------------------------ 数据
    def _material_items(self):
        m = self.doc.model
        out = []
        for i, mt in enumerate(m.materials if m else []):
            out.append((i, "%02d · %s" % (i, mt.name or "未命名材质")))
        return out

    def _material(self):
        m = self.doc.model
        if m and 0 <= self.idx < len(m.materials):
            return m.materials[self.idx]
        return None

    def _fill(self):
        m = self.doc.model
        prev = self.loading
        self.loading = True
        try:
            _fill_combo(self.src_combo, self._material_items(), self.idx)
        finally:
            self.loading = prev
        self._sync_dst()
        self._update_ranges()
        self._update_note()

    def _sync_dst(self):
        m = self.doc.model
        if not m or not m.materials:
            return
        cur = self.dst_combo.currentData()
        if cur is None or cur == self.idx or not (0 <= cur < len(m.materials)):
            cur = (self.idx + 1) % len(m.materials) if len(m.materials) > 1 else -1
        prev = self.loading
        self.loading = True
        try:
            _fill_combo(self.dst_combo, self._material_items(), cur)
        finally:
            self.loading = prev

    def _update_ranges(self):
        mt = self._material()
        faces = int(mt.face_count) // 3 if mt else 0
        self.start_spin.setRange(0, max(0, faces - 1))
        self.count_spin.setRange(0 if not faces else 1, faces)
        if faces and self.count_spin.value() == 0:
            self.count_spin.setValue(1)

    def _update_note(self, *_):
        mt = self._material()
        dst = self.dst_combo.currentData()
        m = self.doc.model
        if not mt or dst is None or not m or not (0 <= dst < len(m.materials)):
            self.note.setText("")
            self.move_btn.setEnabled(False)
            return
        faces = int(mt.face_count) // 3
        start = min(self.start_spin.value(), max(0, faces - 1))
        count = min(self.count_spin.value(), max(0, faces - start))
        dst_name = m.materials[dst].name or "未命名材质"
        if dst == self.idx:
            self.note.setText("源材质与目标材质相同，无法移动。")
            self.move_btn.setEnabled(False)
            return
        if count <= 0:
            self.note.setText("当前材质没有可移动的面。")
            self.move_btn.setEnabled(False)
            return
        span = ("第 %d 个面" % (start + 1)) if count == 1 \
            else ("第 %d–%d 个面" % (start + 1, start + count))
        self.note.setText("%s：%s → %s" % ((mt.name or "未命名材质"), span, dst_name))
        self.move_btn.setEnabled(True)

    # ------------------------------------------------------------ 编辑
    def _move(self):
        m = self.doc.model
        src = self.src_combo.currentData()
        dst = self.dst_combo.currentData()
        if not m or src is None or dst is None or src == dst:
            return
        start = self.start_spin.value()
        count = self.count_spin.value()
        if count <= 0:
            return
        self.edit("移动面到材质",
                  lambda model: reassign_faces(model, int(src), start, count, int(dst)),
                  "structure")
