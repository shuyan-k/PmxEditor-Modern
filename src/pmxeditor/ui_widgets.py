# -*- coding: utf-8 -*-
"""通用界面组件：卡片、表单、列表、颜色按钮、开关等。"""
from __future__ import annotations

from PyQt5.QtCore import (QEasingCurve, QModelIndex, QPropertyAnimation, QRectF, QSize,
                          Qt, QTimer,
                          pyqtProperty, pyqtSignal)
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt5.QtWidgets import (QAbstractButton, QAction, QButtonGroup,
                             QColorDialog, QComboBox, QDialog, QDoubleSpinBox,
                             QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout,
                             QLineEdit, QListView, QPushButton,
                             QMenu, QSizePolicy, QStyle, QStyledItemDelegate,
                             QStyleOptionViewItem, QTreeView, QVBoxLayout, QWidget,
                             QAbstractItemView)

from .theme import (ACCENT, BORDER, CHESS_A, CHESS_B, CHESS_BG,
                   KNOB, OVERLAY_HOVER, SWATCH_BORDER, SWITCH_OFF, TEXT,
                   TEXT_DIM, TEXT_FAINT, TREE_DOT, TREE_DOT_DIM, TREE_DOT_SEL,
                   register_icon, ui_font)

# ---------------------------------------------------------------- 基础

def label(text: str, obj: str = "", wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    lb.setWordWrap(wrap)
    return lb

def icon_button(kind: str, tip: str, color: str = TEXT_DIM, size: int = 18,
                obj: str = "Ghost") -> QPushButton:
    b = QPushButton()
    b.setObjectName(obj)
    b.setIcon(register_icon(b, kind, color, size))
    b.setIconSize(QSize(size, size))
    b.setFixedSize(28, 28)
    b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    return b

def text_button(text: str, kind: str = "Ghost", icon: str = "", tip: str = "") -> QPushButton:
    b = QPushButton(text)
    b.setObjectName(kind)
    if icon:
        b.setIcon(register_icon(b, icon, TEXT_DIM, 16))
        b.setIconSize(QSize(16, 16))
    if tip:
        b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    return b

class Card(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")

class Section(QWidget):
    """带标题的内容区块。"""

    def __init__(self, title: str, hint: str = "", parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(6)
        bar = QFrame()
        bar.setFixedSize(3, 13)
        bar.setStyleSheet("background:%s; border-radius:1px;" % ACCENT)
        head.addWidget(bar)
        head.addWidget(label(title, "SectionTitle"))
        if hint:
            head.addWidget(label(hint, "SectionHint"))
        head.addStretch(1)
        self.head = head
        lay.addLayout(head)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(8)
        lay.addLayout(self.body)

    def add(self, w):
        self.body.addWidget(w)
        return w

    def add_layout(self, l):
        self.body.addLayout(l)
        return l

class Form(QWidget):
    """两列对齐表单：标签宽度统一，数值排版整齐。"""

    def __init__(self, label_width: int = 74, parent=None):
        super().__init__(parent)
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(7)
        self.grid.setColumnStretch(1, 1)
        self.label_width = label_width
        self._row = 0

    def add(self, name: str, field: QWidget, tip: str = ""):
        lb = label(name, "Muted")
        lb.setFixedWidth(self.label_width)
        lb.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        if tip:
            lb.setToolTip(tip)
            field.setToolTip(tip)
        if isinstance(field, QComboBox):
            field.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            field.setMinimumWidth(60)
        self.grid.addWidget(lb, self._row, 0)
        self.grid.addWidget(field, self._row, 1)
        self._row += 1
        return field

    def add_full(self, field):
        if isinstance(field, QLayout):
            self.grid.addLayout(field, self._row, 0, 1, 2)
        else:
            self.grid.addWidget(field, self._row, 0, 1, 2)
        self._row += 1
        return field

    def row(self) -> int:
        return self._row

def make_spin(decimals: int = 4, lo: float = -99999.0, hi: float = 99999.0,
              step: float = 0.01, width: int = 0) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setDecimals(decimals)
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setKeyboardTracking(False)
    s.setButtonSymbols(QDoubleSpinBox.NoButtons)
    s.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    s.setFont(ui_font(8.6))
    if width:
        s.setFixedWidth(width)
    return s

class AxisSpin(QWidget):
    """XYZ 三轴数值输入，轴标签带颜色提示。"""

    valueChanged = pyqtSignal()

    AXIS_COLORS = ("#e07a7a", "#7fc98a", "#6fa8e8")

    def __init__(self, decimals: int = 4, step: float = 0.01,
                 lo: float = -99999.0, hi: float = 99999.0, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.spins = []
        for i, ax in enumerate("XYZ"):
            tag = label(ax, "")
            tag.setFixedWidth(10)
            tag.setStyleSheet("color:%s; font-size:8pt; font-weight:600;" % self.AXIS_COLORS[i])
            tag.setAlignment(Qt.AlignCenter)
            sp = make_spin(decimals, lo, hi, step)
            sp.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            sp.setMinimumWidth(46)
            sp.valueChanged.connect(lambda _v: self.valueChanged.emit())
            lay.addWidget(tag)
            lay.addWidget(sp, 1)
            self.spins.append(sp)

    def value(self):
        return [s.value() for s in self.spins]

    def set_value(self, vals):
        for s, v in zip(self.spins, vals):
            s.blockSignals(True)
            s.setValue(float(v))
            s.blockSignals(False)

    def set_enabled(self, on: bool):
        for s in self.spins:
            s.setEnabled(on)

class ColorButton(QPushButton):
    colorChanged = pyqtSignal(list)
    pressedSnapshot = pyqtSignal()

    def __init__(self, color=None, parent=None):
        super().__init__(parent)
        self._color = QColor(255, 255, 255, 255)
        self.set_color(color or [1.0, 1.0, 1.0, 1.0])
        self.setFixedHeight(24)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self._pick)
        self.pressed.connect(self.pressedSnapshot.emit)

    def color(self):
        return [self._color.redF(), self._color.greenF(), self._color.blueF(),
                self._color.alphaF()]

    def set_color(self, c):
        vals = [float(v) for v in list(c)[:4]]
        while len(vals) < 4:
            vals.append(1.0)
        self._color = QColor.fromRgbF(*vals)
        self.update()

    def _pick(self):
        c = QColorDialog.getColor(self._color, self, "选择颜色",
                                  QColorDialog.ShowAlphaChannel)
        if c.isValid():
            self._color = c
            self.update()
            self.colorChanged.emit(self.color())

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        # 棋盘格底纹体现透明度
        p.setPen(QPen(QColor(BORDER), 1))
        p.setBrush(QColor(CHESS_BG))
        p.drawRoundedRect(r, 5, 5)
        sw = QRectF(5, 5, 16, 16)
        for yy in range(2):
            for xx in range(2):
                p.setBrush(QColor(CHESS_A if (xx + yy) % 2 == 0 else CHESS_B))
                p.setPen(Qt.NoPen)
                p.drawRect(QRectF(sw.x() + xx * 8, sw.y() + yy * 8, 8, 8))
        p.setBrush(self._color)
        p.setPen(QPen(QColor(*SWATCH_BORDER), 1))
        p.drawRoundedRect(sw, 3, 3)
        c = self._color
        txt = "#%02X%02X%02X" % (c.red(), c.green(), c.blue())
        if c.alpha() < 255:
            txt += " · %d%%" % round(c.alphaF() * 100)
        p.setPen(QColor(TEXT))
        p.setFont(ui_font(8.4))
        p.drawText(QRectF(27, 0, self.width() - 30, self.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, txt)
        p.end()

class ColorSpins(QWidget):
    """RGBA 精确数值输入，与 ColorButton 双向同步。

    取色对话框走 QColor，分量只有 8 位精度（0.5 会变成 127/255）；原版 PmxEditor
    的材质色可以直接键入 0.5 这样的浮点值，这里补上等价的精确入口。
    """

    colorChanged = pyqtSignal(list)

    def __init__(self, color=None, decimals: int = 3, alpha: bool = True, parent=None):
        super().__init__(parent)
        vals = [float(v) for v in list(color or [1.0, 1.0, 1.0, 1.0])][:4]
        while len(vals) < 4:
            vals.append(1.0)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        self.spins = []
        names = ("R", "G", "B", "A") if alpha else ("R", "G", "B")
        for i, nm in enumerate(names):
            tag = label(nm, "")
            tag.setStyleSheet("color:%s; font-size:8pt;" % TEXT_FAINT)
            tag.setAlignment(Qt.AlignCenter)
            tag.setFixedWidth(10)
            sp = make_spin(decimals, 0.0, 1.0, 0.01)
            sp.setMinimumWidth(50)
            sp.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            sp.setValue(vals[i])
            sp.valueChanged.connect(lambda _v: self.colorChanged.emit(self.color()))
            lay.addWidget(tag)
            lay.addWidget(sp, 1)
            self.spins.append(sp)

    def color(self):
        return [float(s.value()) for s in self.spins]

    def set_color(self, c):
        vals = [float(v) for v in list(c)[:4]]
        while len(vals) < 4:
            vals.append(1.0)
        for sp, v in zip(self.spins, vals):
            sp.blockSignals(True)
            sp.setValue(v)
            sp.blockSignals(False)

class Switch(QAbstractButton):
    """现代开关，带滑动动画。"""

    def __init__(self, checked: bool = False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFixedSize(36, 20)
        self.setCursor(Qt.PointingHandCursor)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate)

    def _get_knob(self):
        return self._pos

    def _set_knob(self, v):
        self._pos = v
        self.update()

    knob = pyqtProperty(float, _get_knob, _set_knob)

    def _animate(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 2, self.width() - 2, self.height() - 4)
        off = QColor(SWITCH_OFF)
        on = QColor(ACCENT)
        col = QColor(int(off.red() + (on.red() - off.red()) * self._pos),
                     int(off.green() + (on.green() - off.green()) * self._pos),
                     int(off.blue() + (on.blue() - off.blue()) * self._pos))
        p.setPen(QPen(QColor(BORDER), 1))
        p.setBrush(col)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = self.height() - 9
        x = 4 + (self.width() - 8 - d) * self._pos
        p.setPen(QPen(QColor(0, 0, 0, 40), 1))
        p.setBrush(QColor(KNOB))
        p.drawEllipse(QRectF(x, 4.5, d, d))
        p.end()

class Segmented(QWidget):
    changed = pyqtSignal(str)

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.setObjectName("Segmented")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.setStyleSheet("QWidget#Segmented{background:#151920;border:1px solid %s;"
                           "border-radius:7px;}" % BORDER)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        for key, text in items:
            b = QPushButton(text)
            b.setObjectName("Segment")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _c, k=key: self.changed.emit(k))
            lay.addWidget(b)
            self.group.addButton(b)
            self.buttons[key] = b
        if items:
            self.buttons[items[0][0]].setChecked(True)

    def value(self):
        for k, b in self.buttons.items():
            if b.isChecked():
                return k
        return ""

    def set_value(self, key):
        if key in self.buttons:
            self.buttons[key].setChecked(True)

class SearchEdit(QLineEdit):
    changed = pyqtSignal(str)

    def __init__(self, placeholder: str = "搜索", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        act = QAction(self)
        act.setIcon(register_icon(act, "search", TEXT_FAINT, 15))
        self.addAction(act, QLineEdit.LeadingPosition)
        self.setClearButtonEnabled(True)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(lambda: self.changed.emit(self.text()))
        self.textChanged.connect(lambda _t: self._timer.start())

class Badge(QLabel):
    def __init__(self, text: str = "", color: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("Badge")
        if color:
            self.setStyleSheet("background:%s; border:1px solid %s; border-radius:9px;"
                               "padding:1px 8px; font-size:8pt;" % (color, color))

# ---------------------------------------------------------------- 列表

class RowDelegate(QStyledItemDelegate):
    """统一列表行：主名称 + 中文译名 + 右侧统计数据。"""

    def __init__(self, marker: str = "dot", height: int = 46, parent=None):
        super().__init__(parent)
        self.marker = marker
        self.height = height
        self.width_hint = 0

    def sizeHint(self, option, index):
        # 行宽跟随视图视口宽度；不能用 option.rect.width()，那个值在
        # uniformItemSizes 下会被首次布局宽度锁死（窗口缩小后行宽不变、
        # 右侧统计文本被推出可视区并出现横向滚动条）。
        w = self.width_hint or option.rect.width()
        return QSize(max(120, w), self.height)

    def paint(self, p: QPainter, opt: QStyleOptionViewItem, index):
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(opt.rect).adjusted(3, 2, -3, -2)
        selected = bool(opt.state & QStyle.State_Selected)
        hovered = bool(opt.state & QStyle.State_MouseOver)
        if selected:
            p.setPen(QPen(QColor(ACCENT), 1))
            c = QColor(ACCENT)
            c.setAlpha(28)
            p.setBrush(c)
            p.drawRoundedRect(r, 7, 7)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(ACCENT))
            p.drawRoundedRect(QRectF(r.x() + 1, r.y() + 6, 3, r.height() - 12), 1.5, 1.5)
        elif hovered:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(*OVERLAY_HOVER))
            p.drawRoundedRect(r, 7, 7)

        name = index.data(Qt.DisplayRole) or ""
        hint = index.data(Qt.UserRole + 1) or ""
        right = index.data(Qt.UserRole + 2) or ""
        color = index.data(Qt.UserRole + 3)
        dim = bool(index.data(Qt.UserRole + 5))

        x = r.x() + 12
        # 标记
        if self.marker == "swatch":
            p.setPen(QPen(QColor(*SWATCH_BORDER), 1))
            p.setBrush(QColor(color) if color else QColor(TREE_DOT))
            p.drawRoundedRect(QRectF(x, r.y() + (r.height() - 14) / 2, 14, 14), 4, 4)
            x += 22
        elif self.marker == "diamond":
            from PyQt5.QtCore import QPointF
            from PyQt5.QtGui import QPolygonF
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(color) if color else QColor(TREE_DOT_DIM))
            cx, cy = x + 4, r.center().y()
            p.drawPolygon(QPolygonF([QPointF(cx, cy - 5), QPointF(cx + 5, cy),
                                     QPointF(cx, cy + 5), QPointF(cx - 5, cy)]))
            x += 16
        elif self.marker == "bone":
            p.setPen(QPen(QColor(ACCENT if selected else TEXT_DIM), 1.4))
            p.setBrush(Qt.NoBrush)
            p.drawLine(QRectF(x, r.y() + r.height() / 2, 0, 0).topLeft(),
                       QRectF(x + 10, r.y() + r.height() / 2, 0, 0).topLeft())
            p.setBrush(QColor(ACCENT if selected else TREE_DOT_SEL))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QRectF(x + 3, r.y() + r.height() / 2 - 3, 6, 6))
            x += 16

        # 名称与译名
        right_w = 0
        if right:
            right_w = QFontMetrics(ui_font(8.4)).horizontalAdvance(str(right)) + 14
        text_w = r.width() - (x - r.x()) - right_w - 12
        name_font = ui_font(9.4, QFont.DemiBold if selected else QFont.Normal)
        p.setFont(name_font)
        p.setPen(QColor(TEXT if not dim else TEXT_DIM))
        fm = QFontMetrics(name_font)
        name_txt = fm.elidedText(str(name), Qt.ElideRight, max(24, int(text_w)))
        if hint and self.height < 40:
            name_font = ui_font(9.0, QFont.DemiBold if selected else QFont.Normal)
            p.setFont(name_font)
            p.setPen(QColor(TEXT if not dim else TEXT_DIM))
            fm = QFontMetrics(name_font)
            name_txt = fm.elidedText(str(name), Qt.ElideRight, max(24, int(text_w)))
            p.drawText(QRectF(x, r.y(), text_w, r.height()),
                       Qt.AlignLeft | Qt.AlignVCenter, name_txt)
            hw = fm.horizontalAdvance(name_txt)
            hf = ui_font(8.2)
            p.setFont(hf)
            p.setPen(QColor(TEXT_FAINT))
            hm = QFontMetrics(hf)
            if text_w - hw - 8 > 20:
                p.drawText(QRectF(x + hw + 8, r.y(), text_w - hw - 8, r.height()),
                           Qt.AlignLeft | Qt.AlignVCenter,
                           hm.elidedText(str(hint), Qt.ElideRight,
                                         int(text_w - hw - 8)))
        elif hint:
            p.drawText(QRectF(x, r.y() + 6, text_w, 17), Qt.AlignLeft | Qt.AlignVCenter, name_txt)
            hf = ui_font(8.2)
            p.setFont(hf)
            p.setPen(QColor(TEXT_FAINT))
            hm = QFontMetrics(hf)
            p.drawText(QRectF(x, r.y() + 23, text_w, 15), Qt.AlignLeft | Qt.AlignVCenter,
                       hm.elidedText(str(hint), Qt.ElideRight, max(24, int(text_w))))
        else:
            p.drawText(QRectF(x, r.y(), text_w, r.height()), Qt.AlignLeft | Qt.AlignVCenter, name_txt)

        if right:
            p.setFont(ui_font(8.3))
            p.setPen(QColor(TEXT_FAINT))
            p.drawText(QRectF(r.right() - right_w, r.y(), right_w - 6, r.height()),
                       Qt.AlignRight | Qt.AlignVCenter, str(right))
        p.restore()

class EntryList(QListView):
    indexSelected = pyqtSignal(int)

    def __init__(self, marker: str = "dot", parent=None):
        super().__init__(parent)
        self._model = QStandardItemModelCompat(self)
        self.setModel(self._model)
        self.setItemDelegate(RowDelegate(marker, 46, self))
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setUniformItemSizes(True)
        self.setMouseTracking(True)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        # 列表没有右键菜单：不要留 setContextMenuPolicy(CustomContextMenu) 却没人接
        # customContextMenuRequested（旧代码就是这样，右键点了毫无反应）
        self._data_index = []
        self._selected = -1
        self._updating = False
        self.empty_text = "无匹配结果"
        self.selectionModel().selectionChanged.connect(self._on_selection)

    def set_entries(self, entries, selected: int = -1):
        """entries: list of dict(name, hint, right, color, dim, index)"""
        from PyQt5.QtGui import QStandardItem
        self._updating = True
        try:
            self._model.clear()
            self._data_index = []
            for e in entries:
                it = QStandardItem(str(e.get("name", "")))
                it.setEditable(False)
                it.setData(e.get("hint", ""), Qt.UserRole + 1)
                it.setData(e.get("right", ""), Qt.UserRole + 2)
                it.setData(e.get("color", None), Qt.UserRole + 3)
                it.setData(e.get("index", -1), Qt.UserRole + 4)
                it.setData(bool(e.get("dim", False)), Qt.UserRole + 5)
                it.setToolTip(str(e.get("tooltip", e.get("name", ""))))
                self._model.appendRow(it)
                self._data_index.append(e.get("index", -1))
        finally:
            self._updating = False
        self._selected = -1
        self._updating = True
        try:
            idx = next((i for i, d in enumerate(self._data_index) if d == selected), -1)
            if idx >= 0:
                self.setCurrentIndex(self._model.index(idx, 0))
                self._selected = self._data_index[idx]
            else:
                # 之前这里总回落到第 0 行：搜索过滤掉当前项后会悄悄改掉文档选中项
                self.setCurrentIndex(QModelIndex())
                self.clearSelection()
        finally:
            self._updating = False

    def select_data_index(self, data_index: int):
        try:
            row = self._data_index.index(data_index)
        except ValueError:
            return
        if row != self.currentIndex().row():
            self.setCurrentIndex(self._model.index(row, 0))
        self._selected = data_index

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._sync_row_width()

    def _sync_row_width(self):
        w = self.viewport().width()
        d = self.itemDelegate()
        if getattr(d, "width_hint", 0) == w:
            return
        d.width_hint = w
        # 关掉再打开 uniformItemSizes，强制 QListView 丢弃缓存的行尺寸
        self.setUniformItemSizes(False)
        self.setUniformItemSizes(True)
        self.doItemsLayout()
        self.viewport().update()

    def _on_selection(self, *_):
        idx = self.currentIndex()
        if idx.isValid() and 0 <= idx.row() < len(self._data_index):
            self._selected = self._data_index[idx.row()]
            if not self._updating:
                self.indexSelected.emit(self._selected)
        elif not self._model.rowCount():
            self._selected = -1

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self._model.rowCount():
            return
        # 列表为空时给一句说明，避免整块面板纯空白
        p = QPainter(self.viewport())
        p.setPen(QColor(TEXT_FAINT))
        p.setFont(ui_font(10))
        p.drawText(self.viewport().rect(), Qt.AlignCenter, self.empty_text)

# QStandardItemModel 仅在需要时导入，避免顶部导入冗余
from PyQt5.QtGui import QStandardItemModel  # noqa: E402

class QStandardItemModelCompat(QStandardItemModel):
    pass

class BoneTree(QTreeView):
    boneSelected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = QStandardItemModel(self)
        self.setModel(self._model)
        self.setItemDelegate(RowDelegate("none", 28, self))
        self.setHeaderHidden(True)
        self.setRootIsDecorated(True)
        self.setIndentation(8)
        self.setUniformRowHeights(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.setExpandsOnDoubleClick(False)
        self._items = {}
        self._selected = -1
        self.empty_text = "无匹配结果"
        self.selectionModel().selectionChanged.connect(self._on_selection)

    def paintEvent(self, ev):
        super().paintEvent(ev)
        if self._model.rowCount():
            return
        p = QPainter(self.viewport())
        p.setPen(QColor(TEXT_FAINT))
        p.setFont(ui_font(10))
        p.drawText(self.viewport().rect(), Qt.AlignCenter, self.empty_text)

    def _context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction("全部展开", self.expandAll)
        menu.addAction("全部折叠", self.collapseAll)
        menu.exec_(self.viewport().mapToGlobal(pos))

    def set_model_data(self, model, keyword: str = "", selected: int = -1):
        from PyQt5.QtGui import QStandardItem
        self._model.clear()
        self._items = {}
        self._selected = -1
        if model is None:
            self.empty_text = "未载入模型"
            return
        self.empty_text = "无匹配结果"
        kw = keyword.strip().lower()
        bones = model.bones
        children = [[] for _ in bones]
        roots = []
        for i, b in enumerate(bones):
            p = b.parent
            if 0 <= p < len(bones) and p != i and not self._creates_cycle(bones, i):
                children[p].append(i)
            else:
                roots.append(i)

        def visible(i, seen):
            if i in seen:
                return False
            name = bones[i].name.lower()
            hint = ""
            from .gl_names import bone_zh
            hint = bone_zh(bones[i].name).lower()
            if not kw or kw in name or kw in hint:
                return True
            return any(visible(c, seen | {i}) for c in children[i])

        made = []

        def build(i, parent_item, depth):
            if not visible(i, set()):
                return
            b = bones[i]
            from .gl_names import bone_zh
            it = QStandardItem(b.name or "(未命名骨骼)")
            it.setEditable(False)
            it.setData(bone_zh(b.name) if bone_zh(b.name) != b.name.strip() else "",
                       Qt.UserRole + 1)
            it.setData("", Qt.UserRole + 2)
            it.setData("#4f9dff" if b.flags & 0x0020 else ("#38d6c4" if b.flags & 0x1000 else None),
                       Qt.UserRole + 3)
            it.setData(i, Qt.UserRole + 4)
            it.setData(False, Qt.UserRole + 5)
            it.setToolTip("%s\n索引 %d · 父级 %d" % (b.name, i, b.parent))
            if parent_item is None:
                self._model.appendRow(it)
            else:
                parent_item.appendRow(it)
            made.append((i, it))
            for c in children[i]:
                build(c, it, depth + 1)

        for r in roots:
            build(r, None, 0)
        self._items = dict(made)
        self.expandAll()
        self._selected = -1
        if selected in self._items:
            self.select_bone(selected)

    @staticmethod
    def _creates_cycle(bones, start: int) -> bool:
        seen = set()
        cur = start
        while 0 <= cur < len(bones):
            if cur in seen:
                return True
            seen.add(cur)
            cur = bones[cur].parent
        return False

    def select_bone(self, index: int):
        it = self._items.get(index)
        if it is None:
            return
        idx = it.index()
        self.setCurrentIndex(idx)
        self.scrollTo(idx, QAbstractItemView.PositionAtCenter)
        self._selected = index

    def _on_selection(self, *_):
        idx = self.currentIndex()
        if idx.isValid():
            v = idx.data(Qt.UserRole + 4)
            if isinstance(v, int):
                self._selected = v
                self.boneSelected.emit(v)

# ---------------------------------------------------------------- 对话框

class ConfirmDialog(QDialog):
    def __init__(self, title: str, message: str, danger: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(12)
        lay.addWidget(label(title, "SectionTitle"))
        body = label(message, "Muted", True)
        lay.addWidget(body)
        row = QHBoxLayout()
        row.addStretch(1)
        cancel = text_button("取消")
        ok = text_button("确定", "Primary" if not danger else "Danger")
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        lay.addLayout(row)
        self._ok = ok
