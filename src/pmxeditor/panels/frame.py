"""表示枠页：MMD 操作面板里的分组。"""
from __future__ import annotations

# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QComboBox, QHBoxLayout, QLineEdit, QListWidget,
                             QListWidgetItem, QVBoxLayout, QWidget)

from ..doc import (add_frame, duplicate_frame, frame_add_item,
                   frame_move_item, frame_remove_item, move_frame,
                   remove_frame)
from ..gl_names import bone_zh, morph_zh
from ..theme import ACCENT, ACCENT_2, DANGER
from ..ui_widgets import (Card, ConfirmDialog, EntryList, Form, SearchEdit,
                          Switch, label, text_button)
from .base import PageBase


class FramePage(PageBase):
    """显示枠等价的编辑器：每个枠是「操作パネル」里的一个分组。"""

    def __init__(self, doc, parent=None):
        super().__init__(doc, "表示枠", "操作面板里的分组", parent)
        self.add_tool("plus", "新建表示枠", self._add)
        self.add_tool("duplicate", "复制表示枠", self._duplicate)
        self.add_tool("trash", "删除表示枠", self._remove, DANGER)

        self.search = SearchEdit("搜索表示枠名")
        self.search.changed.connect(self._refresh_list)
        self.root.addWidget(self.search)

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
        form.add("名称", self.name_edit)
        form.add("英文名", self.name_en_edit)
        self.special_sw = Switch(False)
        self.special_sw.setToolTip("特殊枠（通常是「センター」这类固定分组）")
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.special_sw)
        row.addWidget(label("特殊枠", "Muted"))
        row.addStretch(1)
        form.add_full(row)
        sec.add(form)
        self.name_edit.editingFinished.connect(self._name_changed)
        self.name_en_edit.editingFinished.connect(self._name_en_changed)
        self.special_sw.toggled.connect(self._special_changed)
        dl.addWidget(card)

        card, sec = self._card("项目", "骨骼与形态，顺序即操作面板里的顺序")
        self.items = QListWidget()
        self.items.setObjectName("Entry")
        self.items.setFixedHeight(168)
        self.items.currentRowChanged.connect(lambda _r: self._sync_buttons())
        sec.add(self.items)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.btn_up = text_button("上移", "Ghost", tip="在分组里上移一项")
        self.btn_down = text_button("下移", "Ghost", tip="在分组里下移一项")
        self.btn_del = text_button("移除", "Ghost", tip="从分组里移除选中项")
        self.btn_up.clicked.connect(lambda: self._move_item(-1))
        self.btn_down.clicked.connect(lambda: self._move_item(1))
        self.btn_del.clicked.connect(self._remove_item)
        row.addWidget(self.btn_up)
        row.addWidget(self.btn_down)
        row.addWidget(self.btn_del)
        row.addStretch(1)
        sec.add_layout(row)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.bone_combo = QComboBox()
        self.bone_button = text_button("加骨骼", "Ghost")
        self.bone_button.clicked.connect(self._add_bone_item)
        row.addWidget(self.bone_combo, 1)
        row.addWidget(self.bone_button)
        sec.add_layout(row)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.morph_combo = QComboBox()
        self.morph_button = text_button("加形态", "Ghost")
        self.morph_button.clicked.connect(self._add_morph_item)
        row.addWidget(self.morph_combo, 1)
        row.addWidget(self.morph_button)
        sec.add_layout(row)
        self.items_note = label("", "Faint", True)
        sec.add(self.items_note)
        dl.addWidget(card)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 2, 0)
        row.addStretch(1)
        self.btn_up_frame = text_button("枠上移", "Ghost")
        self.btn_down_frame = text_button("枠下移", "Ghost")
        self.btn_up_frame.clicked.connect(lambda: self._move_frame(-1))
        self.btn_down_frame.clicked.connect(lambda: self._move_frame(1))
        row.addWidget(self.btn_up_frame)
        row.addWidget(self.btn_down_frame)
        dl.addLayout(row)
        dl.addStretch(1)
        self.root.addWidget(self.scroll(self.detail), 2)
        self._set_enabled(False)

    def _set_enabled(self, on: bool):
        self.detail.setEnabled(on)

    # ------------------------------------------------------------ 数据
    def _frame(self):
        m = self.doc.model
        if m and 0 <= self.idx < len(m.frames):
            return m.frames[self.idx]
        return None

    def refresh(self):
        m = self.doc.model
        self.loading = True
        try:
            if not m:
                self.idx = -1
            self._refresh_list()
            if m and m.frames and not (0 <= self.idx < len(m.frames)):
                self.idx = 0
                self._select_row(0)
            self._set_enabled(bool(m and 0 <= self.idx < len(m.frames)))
            self._fill()
        finally:
            self.loading = False

    def _refresh_list(self, *_):
        m = self.doc.model
        if not m:
            self._show_empty()
            self._set_enabled(False)
            return
        kw = self.search.text().strip().lower()
        entries = []
        for i, f in enumerate(m.frames):
            if kw and kw not in f.name.lower() and kw not in f.name_en.lower():
                continue
            entries.append({
                "name": f.name or "未命名表示枠",
                "hint": ("特殊枠 · " if f.special else "") + "%d 项" % len(f.items),
                "right": "",
                "color": ACCENT if f.special else ACCENT_2,
                "index": i,
            })
        self._show_entries(entries)

    def select(self, kind: str, index: int):
        if kind != "frame":
            return
        self.idx = index
        self._select_row(index)
        self._set_enabled(bool(self._frame()))
        self._fill()

    def _on_list(self, i):
        self._select_from_list("frame", i)

    def _fill(self):
        m = self.doc.model
        f = self._frame()
        prev = self.loading
        self.loading = True
        try:
            if not m or not f:
                self.set_hint("未选择")
                self.items.clear()
                return
            self.set_hint("索引 %d · %d 个表示枠" % (self.idx, len(m.frames)))
            self.name_edit.setText(f.name)
            self.name_en_edit.setText(f.name_en)
            self.special_sw.setChecked(bool(f.special))
            self._fill_items(m, f)
            self._fill_combos(m, f)
        finally:
            self.loading = prev
        self._sync_buttons()

    def _fill_items(self, m, f):
        keep = None
        cur = self.items.currentItem()
        if cur is not None:
            keep = cur.data(Qt.UserRole)
        self.items.clear()
        for pos, (ty, idx) in enumerate(f.items):
            if ty == 0:
                name = m.bones[idx].name if 0 <= idx < len(m.bones) else "?"
                zh = bone_zh(name)
                text = "骨骼 · %s" % name
                if zh and zh != name:
                    text += "   %s" % zh
            else:
                name = m.morphs[idx].name if 0 <= idx < len(m.morphs) else "?"
                zh = morph_zh(name)
                text = "形态 · %s" % name
                if zh and zh != name:
                    text += "   %s" % zh
            it = QListWidgetItem("%02d  %s" % (pos, text))
            it.setData(Qt.UserRole, pos)
            self.items.addItem(it)
        self.items_note.setText("共 %d 项" % len(f.items))
        if self.items.count():
            row = 0
            if keep is not None:
                for i in range(self.items.count()):
                    if self.items.item(i).data(Qt.UserRole) == keep:
                        row = i
                        break
            self.items.setCurrentRow(row)

    def _fill_combos(self, m, f):
        have_bones = {idx for ty, idx in f.items if ty == 0}
        have_morphs = {idx for ty, idx in f.items if ty == 1}
        self.bone_combo.blockSignals(True)
        self.bone_combo.clear()
        for i, b in enumerate(m.bones):
            if i in have_bones:
                continue
            self.bone_combo.addItem("%03d · %s" % (i, b.name or "未命名"), i)
        self.bone_combo.blockSignals(False)
        self.bone_combo.setEnabled(self.bone_combo.count() > 0)

        self.morph_combo.blockSignals(True)
        self.morph_combo.clear()
        for i, mo in enumerate(m.morphs):
            if i in have_morphs:
                continue
            self.morph_combo.addItem("%03d · %s" % (i, mo.name or "未命名"), i)
        self.morph_combo.blockSignals(False)
        self.morph_combo.setEnabled(self.morph_combo.count() > 0)

    def _sync_buttons(self):
        row = self.items.currentRow()
        n = self.items.count()
        self.btn_up.setEnabled(0 < row)
        self.btn_down.setEnabled(0 <= row < n - 1)
        self.btn_del.setEnabled(0 <= row < n)
        m = self.doc.model
        self.btn_up_frame.setEnabled(bool(m and self.idx > 0))
        self.btn_down_frame.setEnabled(bool(m and 0 <= self.idx < len(m.frames) - 1))

    # ------------------------------------------------------------ 编辑
    def _name_changed(self):
        f = self._frame()
        if not f:
            return
        text = self.name_edit.text()
        if text == f.name:
            return
        self.edit("重命名表示枠", lambda m: setattr(m.frames[self.idx], "name", text),
                  "frame", "frame.name")

    def _name_en_changed(self):
        f = self._frame()
        if not f:
            return
        text = self.name_en_edit.text()
        if text == f.name_en:
            return
        self.edit("修改表示枠英文名",
                  lambda m: setattr(m.frames[self.idx], "name_en", text),
                  "frame", "frame.name_en")

    def _special_changed(self, on: bool):
        f = self._frame()
        if not f or bool(f.special) == bool(on):
            return
        self.edit("修改特殊枠标志",
                  lambda m: setattr(m.frames[self.idx], "special", 1 if on else 0),
                  "frame", "frame.special")

    def _add(self):
        m = self.doc.model
        if not m:
            return
        self.doc.push_undo("新建表示枠")
        idx = add_frame(m)
        self.doc.mark_dirty()
        self.doc.edited.emit("structure")
        self.doc.select("frame", idx)

    def _duplicate(self):
        m = self.doc.model
        if not m or self.idx < 0:
            return
        self.doc.push_undo("复制表示枠")
        idx = duplicate_frame(m, self.idx)
        self.doc.mark_dirty()
        self.doc.edited.emit("structure")
        if idx >= 0:
            self.doc.select("frame", idx)

    def _remove(self):
        m = self.doc.model
        f = self._frame()
        if not m or not f:
            return
        dlg = ConfirmDialog("删除表示枠", "确定删除「%s」？\n其中的 %d 个项目会一起移除，"
                            "骨骼与形态本身不受影响。" % (f.name, len(f.items)),
                            danger=True, parent=self)
        if dlg.exec_() != dlg.Accepted:
            return
        self.doc.push_undo("删除表示枠")
        idx = remove_frame(m, self.idx)
        self.doc.mark_dirty()
        self.doc.edited.emit("structure")
        self.doc.select("frame", idx)

    def _move_frame(self, delta: int):
        m = self.doc.model
        if not m or self.idx < 0:
            return
        self.doc.push_undo("调整表示枠顺序")
        idx = move_frame(m, self.idx, delta)
        self.doc.mark_dirty()
        self.doc.edited.emit("structure")
        self.doc.select("frame", idx)

    def _add_bone_item(self):
        m = self.doc.model
        if not m or self.idx < 0 or not self.bone_combo.count():
            return
        bone = int(self.bone_combo.currentData())
        self.doc.push_undo("加入骨骼到表示枠")
        if frame_add_item(m, self.idx, 0, bone):
            self.doc.mark_dirty()
            self.doc.edited.emit("structure")

    def _add_morph_item(self):
        m = self.doc.model
        if not m or self.idx < 0 or not self.morph_combo.count():
            return
        morph = int(self.morph_combo.currentData())
        self.doc.push_undo("加入形态到表示枠")
        if frame_add_item(m, self.idx, 1, morph):
            self.doc.mark_dirty()
            self.doc.edited.emit("structure")

    def _remove_item(self):
        m = self.doc.model
        if not m or self.idx < 0:
            return
        pos = self.items.currentRow()
        if pos < 0 and self.items.count():
            pos = 0
        if pos < 0:
            return
        self.doc.push_undo("从表示枠移除项目")
        if frame_remove_item(m, self.idx, pos):
            self.doc.mark_dirty()
            self.doc.edited.emit("structure")

    def _move_item(self, delta: int):
        m = self.doc.model
        if not m or self.idx < 0:
            return
        pos = self.items.currentRow()
        if pos < 0 and self.items.count():
            pos = 0
        if pos < 0:
            return
        self.doc.push_undo("调整表示枠内顺序")
        new = frame_move_item(m, self.idx, pos, delta)
        self.doc.mark_dirty()
        self.doc.edited.emit("structure")
        self.loading = True
        try:
            self._fill()
            self.items.setCurrentRow(new)
        finally:
            self.loading = False
