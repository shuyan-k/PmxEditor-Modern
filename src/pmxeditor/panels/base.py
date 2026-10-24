"""检查器基类与共用小工具。"""
from __future__ import annotations

# -*- coding: utf-8 -*-
import math
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QScrollArea, QSpinBox, QVBoxLayout, QWidget)
from ..gl_names import bone_zh
from ..theme import TEXT_DIM
from ..ui_widgets import Card, Section, icon_button, label

PANEL_NAMES = {1: "眉", 2: "眼", 3: "口", 4: "其他"}


def _fmt(v, n=4):
    try:
        return ("%." + str(n) + "f") % float(v)
    except Exception:
        return str(v)


def _vec(v, n=3):
    try:
        return " ".join(_fmt(x, n) for x in v)
    except Exception:
        return str(v)


def _deg(v):
    return [math.degrees(float(x)) for x in v]


def _rad(v):
    return [math.radians(float(x)) for x in v]


def _cycle(model, start: int, parent: int) -> bool:
    seen = set()
    cur = parent
    while 0 <= cur < len(model.bones):
        if cur == start or cur in seen:
            return True
        seen.add(cur)
        cur = model.bones[cur].parent
    return False


def _fill_combo(cb: QComboBox, items, current=None, empty=None):
    cb.blockSignals(True)
    cb.clear()
    if empty is not None:
        cb.addItem(empty[1], empty[0])
    for data, text in items:
        cb.addItem(text, data)
    if current is not None:
        i = cb.findData(current)
        cb.setCurrentIndex(i if i >= 0 else 0)
    cb.blockSignals(False)


def _bone_combo_items(model, none_text="（无）"):
    out = []
    for i, b in enumerate(model.bones):
        zh = bone_zh(b.name)
        txt = "%03d · %s" % (i, b.name or "未命名")
        if zh and zh != b.name:
            txt += "   %s" % zh
        out.append((i, txt))
    return out


def _mode_spin(default=1, lo=-127, hi=127):
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(default)
    s.setKeyboardTracking(False)
    s.setButtonSymbols(QSpinBox.NoButtons)
    s.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return s


class PageBase(QWidget):
    selectRequested = pyqtSignal(str, int)

    def __init__(self, doc, title: str, hint: str = "", parent=None):
        super().__init__(parent)
        self.doc = doc
        self.idx = -1
        self.loading = False
        self.setObjectName("Panel")
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(12, 12, 12, 10)
        self.root.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(6)
        head.addWidget(label(title, "SectionTitle"))
        self.hint_label = label(hint, "SectionHint")
        head.addWidget(self.hint_label)
        head.addStretch(1)
        self.root.addLayout(head)
        self.tools = head

    # ------------------------------------------------------------ 工具
    def add_tool(self, kind: str, tip: str, slot, color: str = TEXT_DIM):
        b = icon_button(kind, tip, color, 15)
        b.clicked.connect(slot)
        self.tools.addWidget(b)
        return b

    def set_hint(self, text: str):
        self.hint_label.setText(text)

    def edit(self, name: str, fn, kind: str = "bone", coalesce: str = ""):
        if self.loading or self.doc.suppress or not self.doc.model:
            return
        self.doc.edit(name, fn, kind, coalesce)

    def scroll(self, widget: QWidget) -> QScrollArea:
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sa.setWidget(widget)
        return sa

    def scroll_area(self):
        """本页的滚动容器（整页刷新时用来保存/恢复滚动位置）。"""
        return self.findChild(QScrollArea)

    def select(self, kind: str, index: int):
        pass

    def refresh(self):
        pass

    def _card(self, title: str, hint: str = ""):
        card = Card()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(12, 9, 12, 12)
        lay.setSpacing(8)
        sec = Section(title, hint)
        lay.addWidget(sec)
        return card, sec
