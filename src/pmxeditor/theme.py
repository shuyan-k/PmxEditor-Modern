# -*- coding: utf-8 -*-
"""界面主题：配色、字体、样式表与矢量图标。"""
from __future__ import annotations

import os
import re
import sys
import weakref

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import (QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath,
                         QPen, QPixmap, QPixmapCache, QPolygonF)
from PyQt5.QtWidgets import QApplication

from . import paths

ASSETS = str(paths.ASSETS)

GROUP_COLORS = [
    "#ef6b6b", "#f0b35b", "#e8d45a", "#5ec98a",
    "#38d6c4", "#4f9dff", "#8f7cf0", "#ef7cc0",
    "#c08457", "#8d9bb5", "#70c8ef", "#a6c95e",
    "#e58f5a", "#b6a5e8", "#7fa8a0", "#c9c9c9",
]

# 深色（默认）与亮色色板。
# 键名同时作为各模块的全局变量名，切换时由 sync_modules() 同步给已导入的模块。
DARK = {
    "BG": "#121419", "PANEL": "#181b21", "PANEL_2": "#1e222a", "ELEVATED": "#242932",
    "BORDER": "#2b313c", "BORDER_SOFT": "#232833",
    "TEXT": "#e7eaf0", "TEXT_DIM": "#9aa4b4", "TEXT_FAINT": "#6d7787",
    "ACCENT": "#4f9dff", "ACCENT_2": "#38d6c4",
    "WARN": "#f0b35b", "DANGER": "#ef6b6b", "OK": "#5ec98a",
    "SHELL_BORDER": "#05070a", "BAR_BG": "#0e1116", "HOVER": "#232a35",
    "MENU_SEL": "#2b3646", "RAIL_BG": "#101318", "RAIL_HOVER": "#1b2029",
    "RAIL_ACTIVE_BG": "#1c2735", "BADGE_BG": "#222a36",
    "FIELD_BG": "#151920", "SELECT_BG": "#2f5f9e", "BORDER_HOVER": "#3a4353",
    "FIELD_FOCUS_BG": "#171c25", "FIELD_DISABLED_BG": "#14171d",
    "SUBBTN_BG": "#1b2028", "SUBBTN_HOVER": "#2a3240",
    "BTN_BG": "#232935", "BTN_BORDER": "#2f3746", "BTN_HOVER": "#2b3342",
    "BTN_HOVER_BORDER": "#3c4657", "BTN_PRESSED": "#1d2430",
    "BTN_DISABLED": "#1a1e25", "BTN_DISABLED_BORDER": "#242a34",
    "PRIMARY_TEXT": "#08131f", "ACCENT_HOVER": "#66aaff",
    "DANGER_BORDER": "#4a2c31", "DANGER_BG": "#382226",
    "SEG_ACTIVE_BG": "#24354a", "GROOVE": "#262d38",
    "KNOB_BG": "#dbe6f7", "KNOB_HOVER": "#f6f9ff",
    "SCROLL": "#333b49", "SCROLL_HOVER": "#455066",
    "HEADER_BG": "#1b2028", "TOOLTIP_BG": "#202631", "PROGRESS_BG": "#222833",
    "VIEW_QSS": "#171a20",
    "CHESS_BG": "#20242c", "CHESS_A": "#3a4150", "CHESS_B": "#2a3039",
    "SWITCH_OFF": "#2a313c", "KNOB": "#f2f5fa",
    "TREE_DOT": "#3a4250", "TREE_DOT_DIM": "#4d5666", "TREE_DOT_SEL": "#586274",
    "TEX_MISS_BG": "#2a3039", "TEX_MISS_CELL": "#3a424f",
    "VIEW_BG_RGB": (0.078, 0.086, 0.106),
    "GRID_MINOR_RGB": (0.155, 0.175, 0.21),
    "GRID_MAJOR_RGB": (0.23, 0.26, 0.32),
    "GRID_X_RGB": (0.62, 0.26, 0.30),
    "GRID_Z_RGB": (0.26, 0.40, 0.66),
    "OVERLAY_HOVER": (255, 255, 255, 10),
    "SWATCH_BORDER": (255, 255, 255, 40),
    "BONE_RGB": (0.72, 0.78, 0.88),
    "RIGID_STATIC_RGB": (0.58, 0.60, 0.66),
}

LIGHT = {
    "BG": "#f3f5f9", "PANEL": "#ffffff", "PANEL_2": "#f8fafc", "ELEVATED": "#eef2f7",
    "BORDER": "#d7dde7", "BORDER_SOFT": "#e6eaf1",
    "TEXT": "#1c222b", "TEXT_DIM": "#5c6675", "TEXT_FAINT": "#737e8d",
    "ACCENT": "#2f7fe0", "ACCENT_2": "#0f9e8e",
    "WARN": "#b7791f", "DANGER": "#d14343", "OK": "#2f9e5f",
    "SHELL_BORDER": "#c9d1dd", "BAR_BG": "#fbfcfe", "HOVER": "#e9eef6",
    "MENU_SEL": "#e3ebf7", "RAIL_BG": "#f7f9fc", "RAIL_HOVER": "#eaeff7",
    "RAIL_ACTIVE_BG": "#dfeafb", "BADGE_BG": "#eef2f8",
    "FIELD_BG": "#ffffff", "SELECT_BG": "#cfe1fb", "BORDER_HOVER": "#aab6c7",
    "FIELD_FOCUS_BG": "#ffffff", "FIELD_DISABLED_BG": "#f1f4f8",
    "SUBBTN_BG": "#f0f3f8", "SUBBTN_HOVER": "#e5eaf2",
    "BTN_BG": "#ffffff", "BTN_BORDER": "#d7dde7", "BTN_HOVER": "#f2f6fc",
    "BTN_HOVER_BORDER": "#b9c6d8", "BTN_PRESSED": "#e8eef7",
    "BTN_DISABLED": "#f2f4f7", "BTN_DISABLED_BORDER": "#e3e7ee",
    "PRIMARY_TEXT": "#ffffff", "ACCENT_HOVER": "#4f94ea",
    "DANGER_BORDER": "#e7c2c2", "DANGER_BG": "#fbeeee",
    "SEG_ACTIVE_BG": "#dfeafb", "GROOVE": "#dde4ee",
    "KNOB_BG": "#ffffff", "KNOB_HOVER": "#f7faff",
    "SCROLL": "#c2ccda", "SCROLL_HOVER": "#a9b6c7",
    "HEADER_BG": "#f0f3f8", "TOOLTIP_BG": "#ffffff", "PROGRESS_BG": "#e3e8f0",
    "VIEW_QSS": "#e9edf3",
    "CHESS_BG": "#e8ecf2", "CHESS_A": "#cfd6e0", "CHESS_B": "#eef1f6",
    "SWITCH_OFF": "#c3ccd8", "KNOB": "#ffffff",
    "TREE_DOT": "#b8c1cd", "TREE_DOT_DIM": "#a3adbb", "TREE_DOT_SEL": "#7f8b9b",
    "TEX_MISS_BG": "#e6eaf0", "TEX_MISS_CELL": "#f2f5f9",
    "VIEW_BG_RGB": (0.913, 0.929, 0.953),
    "GRID_MINOR_RGB": (0.78, 0.81, 0.85),
    "GRID_MAJOR_RGB": (0.65, 0.69, 0.75),
    "GRID_X_RGB": (0.80, 0.35, 0.38),
    "GRID_Z_RGB": (0.38, 0.52, 0.75),
    "OVERLAY_HOVER": (15, 25, 45, 14),
    "SWATCH_BORDER": (20, 30, 45, 45),
    "BONE_RGB": (0.28, 0.34, 0.45),
    "RIGID_STATIC_RGB": (0.40, 0.42, 0.47),
}

# 样式表中写死的深色值 → 亮色值（build_qss 输出后整体替换）
_QSS_LIGHT = {
    "#05070a": "#c9d1dd", "#0e1116": "#fbfcfe", "#232a35": "#e9eef6",
    "#2b3646": "#e3ebf7", "#101318": "#f7f9fc", "#1b2029": "#eaeff7",
    "#1c2735": "#dfeafb", "#222a36": "#eef2f8", "#151920": "#ffffff",
    "#2f5f9e": "#cfe1fb", "#3a4353": "#aab6c7", "#171c25": "#ffffff",
    "#14171d": "#f1f4f8", "#1b2028": "#f0f3f8", "#2a3240": "#e5eaf2",
    "#232935": "#ffffff", "#2f3746": "#d7dde7", "#2b3342": "#f2f6fc",
    "#3c4657": "#b9c6d8", "#1d2430": "#e8eef7", "#1a1e25": "#f2f4f7",
    "#242a34": "#e3e7ee", "#08131f": "#ffffff", "#66aaff": "#4f94ea",
    "#4a2c31": "#e7c2c2", "#382226": "#fbeeee", "#24354a": "#dfeafb",
    "#262d38": "#dde4ee", "#dbe6f7": "#ffffff", "#333b49": "#c2ccda",
    "#455066": "#a9b6c7", "#202631": "#ffffff", "#171a20": "#e9edf3",
    "#222833": "#e3e8f0",
}

_current = "dark"
# 模块级默认值即深色，供各模块 import 时取用
globals().update(DARK)
# 深色值 → 亮色值 映射：覆盖全部色板键，并补充样式表中写死的深色字面量。
# 亮色值刻意避开所有深色键，保证该映射单向无歧义。
_map = {}
for _key, _dark in DARK.items():
    if isinstance(_dark, str):
        _map.setdefault(_dark.lower(), LIGHT[_key])
_map.update(_QSS_LIGHT)


def current_name() -> str:
    return _current


def apply_theme(name: str) -> str:
    """切换当前色板并更新本模块的全局变量，返回实际生效的主题名。"""
    global _current
    name = "light" if str(name).lower() in ("light", "亮色", "浅色") else "dark"
    new = LIGHT if name == "light" else DARK
    for key, value in new.items():
        globals()[key] = value
    _current = name
    return _current


# 需要跟随主题刷新的模块：按末段名字匹配，兼容 pmxeditor.xxx 与直接运行 xxx
_SYNC_SUFFIXES = ("app", "main", "panels", "ui_widgets", "viewport")
# 子包内的模块（pmxeditor.panels.bone / pmxeditor.viewport.core 等）末段不是
# "panels"/"viewport"，需按包前缀匹配
_SYNC_PREFIXES = (__package__ + ".panels.", __package__ + ".viewport.")


def sync_modules():
    """把当前色板同步到已 from theme import ... 的模块全局变量。

    这些模块在 import 时按值取走了 VIEW_BG_RGB / GRID_* / TEXT_* 等常量，
    切换主题后必须用 setattr 覆盖回去，否则视口背景与叠加层颜色不跟随。"""
    me = sys.modules.get(__name__)
    for name, mod in list(sys.modules.items()):
        if mod is None or mod is me:
            continue
        if not (name == "__main__"
                or name.rsplit(".", 1)[-1] in _SYNC_SUFFIXES
                or name.startswith(_SYNC_PREFIXES)):
            continue
        for key in DARK:
            if hasattr(mod, key):
                setattr(mod, key, globals()[key])


_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}")


def map_text(text: str) -> str:
    return _HEX_RE.sub(lambda m: _map.get(m.group(0).lower(), m.group(0)), text)


def map_color(color: str) -> str:
    return _map.get(str(color).lower(), color) if _current == "light" else color


def remap_stylesheets():
    """把已构建控件上的内联样式表在深/亮两套色板之间切换。

    首次切到亮色时把原始深色样式记录在控件的 _qss_dark 属性上，
    之后切回深色即可精确还原，避免亮色值反向映射产生歧义。"""
    app = QApplication.instance()
    if app is None:
        return
    for w in app.allWidgets():
        try:
            ss = w.styleSheet()
            base = w.property("_qss_dark")
        except RuntimeError:
            continue
        if not ss:
            continue
        if _current == "light":
            if not base:
                base = ss
                w.setProperty("_qss_dark", base)
            new = map_text(base)
        else:
            new = base or ss
        if new != ss:
            w.setStyleSheet(new)


_ICONS = {}


def register_icon(obj, kind: str, color: str = "", size: int = 20) -> QIcon:
    """创建并登记图标，主题切换时可由 refresh_icons() 重新着色。"""
    icon = make_icon(kind, color or TEXT_DIM, size)
    try:
        _ICONS[id(obj)] = (weakref.ref(obj), kind, color, size)
    except TypeError:
        pass
    return icon


def refresh_icons():
    for key, (ref, kind, color, size) in list(_ICONS.items()):
        obj = ref()
        if obj is None:
            _ICONS.pop(key, None)
            continue
        try:
            obj.setIcon(make_icon(kind, map_color(color) if color else TEXT_DIM, size))
        except RuntimeError:
            _ICONS.pop(key, None)


def ui_font(size: float = 9.0, weight: int = QFont.Normal) -> QFont:
    families = QFontDatabase().families()
    for name in ("Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans SC",
                 "Source Han Sans SC", "SimHei"):
        if name in families:
            f = QFont(name, 0)
            f.setPointSizeF(size)
            f.setWeight(weight)
            return f
    f = QFont()
    f.setPointSizeF(size)
    f.setWeight(weight)
    return f


def mono_font(size: float = 9.0) -> QFont:
    for name in ("Consolas", "JetBrains Mono", "Cascadia Mono", "Courier New"):
        if name in QFontDatabase().families():
            f = QFont(name, 0)
            f.setPointSizeF(size)
            return f
    return ui_font(size)


def build_qss() -> str:
    check = os.path.join(ASSETS, "check.svg").replace("\\", "/")
    dash = os.path.join(ASSETS, "dash.svg").replace("\\", "/")
    arrow = os.path.join(ASSETS, "chevron.svg").replace("\\", "/")
    arrow_up = os.path.join(ASSETS, "chevron_up.svg").replace("\\", "/")
    qss = f"""
* {{
    outline: none;
}}
QWidget {{
    color: {TEXT};
    font-size: 9pt;
}}
QMainWindow, QDialog {{
    background: {BG};
}}
#Shell {{
    background: {BG};
    border: 1px solid #05070a;
}}
#TitleBar {{
    background: #0e1116;
    border-bottom: 1px solid {BORDER_SOFT};
}}
#TitleText {{
    color: {TEXT};
    font-size: 9.5pt;
    font-weight: 600;
}}
#TitleSub {{
    color: {TEXT_FAINT};
    font-size: 8.5pt;
}}
#WinBtn {{
    background: transparent;
    border: none;
    border-radius: 5px;
}}
#WinBtn:hover {{
    background: #232a35;
}}
#WinBtnClose:hover {{
    background: #c8423f;
}}
#MenuBar {{
    background: #0e1116;
    border-bottom: 1px solid {BORDER_SOFT};
    padding: 2px 6px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 4px 10px;
    border-radius: 5px;
    color: {TEXT_DIM};
}}
QMenuBar::item:selected {{
    background: #232a35;
    color: {TEXT};
}}
QMenu {{
    background: {PANEL_2};
    border: 1px solid {BORDER};
    padding: 5px;
}}
QMenu::item {{
    padding: 6px 26px 6px 12px;
    border-radius: 5px;
    color: {TEXT};
}}
QMenu::item:selected {{
    background: #2b3646;
}}
QMenu::item:disabled {{
    color: {TEXT_FAINT};
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 5px 8px;
}}
#Rail {{
    background: #101318;
    border-right: 1px solid {BORDER_SOFT};
}}
#RailBtn {{
    background: transparent;
    border: none;
    border-radius: 7px;
    color: {TEXT_DIM};
    padding: 0px 8px 0px 9px;
    text-align: left;
    font-size: 9pt;
}}
#RailBtn:hover {{
    background: #1b2029;
    color: {TEXT};
}}
#RailBtn:checked {{
    background: #1c2735;
    color: {ACCENT};
    font-weight: 600;
}}
#Panel {{
    background: {PANEL};
    border: none;
}}
#Card {{
    background: {PANEL_2};
    border: 1px solid {BORDER_SOFT};
    border-radius: 8px;
}}
#SectionTitle {{
    color: {TEXT};
    font-size: 9.5pt;
    font-weight: 600;
}}
#SectionHint {{
    color: {TEXT_FAINT};
    font-size: 8.5pt;
}}
#Muted {{
    color: {TEXT_DIM};
    font-size: 8.5pt;
}}
#Faint {{
    color: {TEXT_FAINT};
    font-size: 8.5pt;
}}
#Value {{
    color: {TEXT};
    font-size: 9pt;
}}
#Accent {{
    color: {ACCENT};
}}
#DangerText {{
    color: {DANGER};
    font-size: 8.5pt;
}}
#WarnText {{
    color: {WARN};
    font-size: 8.5pt;
}}
#OkText {{
    color: {OK};
    font-size: 8.5pt;
}}
#Badge {{
    background: #222a36;
    border: 1px solid {BORDER};
    border-radius: 9px;
    color: {TEXT_DIM};
    padding: 1px 8px;
    font-size: 8pt;
}}
#Divider {{
    background: {BORDER_SOFT};
    max-height: 1px;
    min-height: 1px;
}}
#HLine {{
    background: {BORDER_SOFT};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: #151920;
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 7px;
    selection-background-color: #2f5f9e;
    min-height: 18px;
    color: {TEXT};
}}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {{
    border-color: #3a4353;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {ACCENT};
    background: #171c25;
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    color: {TEXT_FAINT};
    background: #14171d;
}}
QLineEdit[readOnly="true"] {{
    color: {TEXT_DIM};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 15px;
    border-left: 1px solid {BORDER_SOFT};
    border-top-right-radius: 6px;
    background: #1b2028;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 15px;
    border-left: 1px solid {BORDER_SOFT};
    border-bottom-right-radius: 6px;
    background: #1b2028;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: #2a3240;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url({arrow_up});
    width: 7px;
    height: 7px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url({arrow});
    width: 7px;
    height: 7px;
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 20px;
    border: none;
}}
QComboBox::down-arrow {{
    image: url({arrow});
    width: 9px;
    height: 9px;
}}
QComboBox QAbstractItemView {{
    background: {PANEL_2};
    border: 1px solid {BORDER};
    selection-background-color: #2b3646;
    padding: 4px;
    outline: none;
}}
QPushButton {{
    background: #232935;
    border: 1px solid #2f3746;
    border-radius: 6px;
    padding: 5px 12px;
    color: {TEXT};
}}
QPushButton:hover {{
    background: #2b3342;
    border-color: #3c4657;
}}
QPushButton:pressed {{
    background: #1d2430;
}}
QPushButton:disabled {{
    color: {TEXT_FAINT};
    background: #1a1e25;
    border-color: #242a34;
}}
QPushButton#Primary {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: #08131f;
    font-weight: 600;
}}
QPushButton#Primary:hover {{
    background: #66aaff;
    border-color: #66aaff;
}}
QPushButton#Ghost {{
    background: transparent;
    border: 1px solid transparent;
    color: {TEXT_DIM};
    padding: 4px 8px;
}}
QPushButton#Ghost:hover {{
    background: #232a35;
    color: {TEXT};
}}
QPushButton#Danger {{
    background: transparent;
    border: 1px solid #4a2c31;
    color: {DANGER};
}}
QPushButton#Danger:hover {{
    background: #382226;
}}
QPushButton#Segment {{
    background: transparent;
    border: none;
    border-radius: 5px;
    padding: 4px 6px;
    color: {TEXT_DIM};
}}
QPushButton#Segment:hover {{
    color: {TEXT};
    background: #232a35;
}}
QPushButton#Segment:checked {{
    background: #24354a;
    color: {ACCENT};
    font-weight: 600;
}}
QCheckBox, QRadioButton {{
    color: {TEXT};
    spacing: 7px;
    padding: 2px 0px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    background: #151920;
    border: 1px solid #3a4353;
    border-radius: 4px;
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {ACCENT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    image: url({check});
}}
QCheckBox::indicator:indeterminate {{
    background: {ACCENT};
    border-color: {ACCENT};
    image: url({dash});
}}
QRadioButton::indicator {{
    border-radius: 7px;
}}
QRadioButton::indicator:checked {{
    background: {ACCENT};
    border: 3px solid #151920;
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: #262d38;
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 12px;
    height: 12px;
    margin: -5px 0;
    border-radius: 6px;
    background: #dbe6f7;
    border: 2px solid {ACCENT};
}}
QSlider::handle:horizontal:hover {{
    background: #ffffff;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #333b49;
    border-radius: 3px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: #455066;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #333b49;
    border-radius: 3px;
    min-width: 24px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QTreeView, QListView {{
    background: transparent;
    border: none;
    selection-background-color: transparent;
    alternate-background-color: transparent;
}}
QTreeView::branch {{
    background: transparent;
}}
QTreeView::branch:has-children:closed {{
    image: url({arrow});
}}
QTreeView::branch:has-children:open {{
    image: url({arrow_up});
}}
QTreeView::branch:!has-children {{
    image: none;
}}
QHeaderView::section {{
    background: #1b2028;
    color: {TEXT_DIM};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 4px 6px;
    font-size: 8.5pt;
}}
QSplitter::handle {{
    background: {BORDER_SOFT};
}}
QSplitter::handle:horizontal {{
    width: 1px;
}}
QSplitter::handle:vertical {{
    height: 1px;
}}
QToolTip {{
    background: #202631;
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 4px 6px;
}}
QStatusBar {{
    background: #0e1116;
    border-top: 1px solid {BORDER_SOFT};
    color: {TEXT_DIM};
}}
QStatusBar::item {{
    border: none;
}}
#Viewport {{
    background: #171a20;
}}
QProgressBar {{
    background: #222833;
    border: none;
    border-radius: 3px;
    height: 6px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 3px;
}}
"""
    return map_text(qss) if _current == "light" else qss


# ---------------------------------------------------------------- 图标

def _pen(p: QPainter, color: str, w: float = 1.6) -> QPen:
    pen = QPen(QColor(color))
    pen.setWidthF(w)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    return pen


def make_icon(kind: str, color: str = "", size: int = 20) -> QIcon:
    color = color or TEXT_DIM
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing, True)
    s = size
    _pen(p, color, max(1.3, s / 13.0))
    p.setBrush(Qt.NoBrush)

    if kind == "open":
        p.drawPolygon(QPolygonF([QPointF(s * .16, s * .32), QPointF(s * .42, s * .32),
                                 QPointF(s * .5, s * .42), QPointF(s * .86, s * .42),
                                 QPointF(s * .78, s * .78), QPointF(s * .18, s * .78)]))
        p.drawLine(QPointF(s * .2, s * .64), QPointF(s * .82, s * .64))
    elif kind == "save":
        p.drawRoundedRect(QRectF(s * .22, s * .18, s * .56, s * .64), 2, 2)
        p.drawRect(QRectF(s * .34, s * .2, s * .32, s * .2))
        p.drawRect(QRectF(s * .34, s * .55, s * .32, s * .2))
    elif kind == "undo":
        path = QPainterPath(QPointF(s * .3, s * .62))
        path.cubicTo(QPointF(s * .3, s * .3), QPointF(s * .78, s * .32), QPointF(s * .74, s * .62))
        p.drawPath(path)
        p.drawPolyline(QPolygonF([QPointF(s * .18, s * .5), QPointF(s * .3, s * .64), QPointF(s * .44, s * .5)]))
    elif kind == "redo":
        path = QPainterPath(QPointF(s * .7, s * .62))
        path.cubicTo(QPointF(s * .7, s * .3), QPointF(s * .22, s * .32), QPointF(s * .26, s * .62))
        p.drawPath(path)
        p.drawPolyline(QPolygonF([QPointF(s * .58, s * .5), QPointF(s * .7, s * .64), QPointF(s * .82, s * .5)]))
    elif kind == "play":
        p.setBrush(QColor(color))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([QPointF(s * .34, s * .24), QPointF(s * .76, s * .5), QPointF(s * .34, s * .76)]))
    elif kind == "pause":
        p.setBrush(QColor(color))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(s * .3, s * .26, s * .14, s * .48), 1, 1)
        p.drawRoundedRect(QRectF(s * .56, s * .26, s * .14, s * .48), 1, 1)
    elif kind == "model":
        p.drawPolygon(QPolygonF([QPointF(s * .5, s * .16), QPointF(s * .8, s * .34),
                                 QPointF(s * .8, s * .66), QPointF(s * .5, s * .84),
                                 QPointF(s * .2, s * .66), QPointF(s * .2, s * .34)]))
        p.drawLine(QPointF(s * .5, s * .5), QPointF(s * .5, s * .84))
        p.drawLine(QPointF(s * .2, s * .34), QPointF(s * .5, s * .5))
        p.drawLine(QPointF(s * .8, s * .34), QPointF(s * .5, s * .5))
    elif kind == "bone":
        p.drawEllipse(QRectF(s * .16, s * .16, s * .13, s * .13))
        p.drawEllipse(QRectF(s * .71, s * .71, s * .13, s * .13))
        p.drawLine(QPointF(s * .28, s * .28), QPointF(s * .72, s * .72))
        p.setBrush(QColor(color))
        p.drawEllipse(QRectF(s * .38, s * .38, s * .1, s * .1))
    elif kind == "material":
        p.drawEllipse(QRectF(s * .2, s * .2, s * .6, s * .6))
        p.drawEllipse(QRectF(s * .34, s * .34, s * .14, s * .14))
        p.drawLine(QPointF(s * .62, s * .62), QPointF(s * .82, s * .82))
    elif kind == "morph":
        p.drawEllipse(QRectF(s * .18, s * .18, s * .64, s * .64))
        p.drawArc(QRectF(s * .3, s * .34, s * .4, s * .3), 200 * 16, 140 * 16)
        p.drawLine(QPointF(s * .36, s * .42), QPointF(s * .4, s * .46))
        p.drawLine(QPointF(s * .64, s * .42), QPointF(s * .6, s * .46))
    elif kind == "physics":
        p.drawArc(QRectF(s * .22, s * .2, s * .56, s * .62), 0, 180 * 16)
        p.drawLine(QPointF(s * .5, s * .5), QPointF(s * .5, s * .72))
        p.setBrush(QColor(color))
        p.drawEllipse(QRectF(s * .44, s * .68, s * .12, s * .12))
    elif kind == "settings":
        p.drawEllipse(QRectF(s * .36, s * .36, s * .28, s * .28))
        for i in range(6):
            import math
            a = math.radians(i * 60)
            p.drawLine(QPointF(s * .5 + math.cos(a) * s * .24, s * .5 + math.sin(a) * s * .24),
                       QPointF(s * .5 + math.cos(a) * s * .34, s * .5 + math.sin(a) * s * .34))
    elif kind == "grid":
        for i in range(3):
            v = s * (.2 + i * .28)
            p.drawLine(QPointF(s * .14, v), QPointF(s * .86, v))
            p.drawLine(QPointF(v, s * .14), QPointF(v, s * .86))
    elif kind == "eye":
        path = QPainterPath(QPointF(s * .14, s * .5))
        path.quadTo(QPointF(s * .5, s * .16), QPointF(s * .86, s * .5))
        path.quadTo(QPointF(s * .5, s * .84), QPointF(s * .14, s * .5))
        p.drawPath(path)
        p.drawEllipse(QRectF(s * .41, s * .41, s * .18, s * .18))
    elif kind == "search":
        p.drawEllipse(QRectF(s * .2, s * .2, s * .4, s * .4))
        p.drawLine(QPointF(s * .58, s * .58), QPointF(s * .82, s * .82))
    elif kind == "plus":
        p.drawLine(QPointF(s * .5, s * .24), QPointF(s * .5, s * .76))
        p.drawLine(QPointF(s * .24, s * .5), QPointF(s * .76, s * .5))
    elif kind == "minus":
        p.drawLine(QPointF(s * .24, s * .5), QPointF(s * .76, s * .5))
    elif kind == "trash":
        p.drawRect(QRectF(s * .3, s * .32, s * .4, s * .46))
        p.drawLine(QPointF(s * .22, s * .28), QPointF(s * .78, s * .28))
        p.drawLine(QPointF(s * .4, s * .22), QPointF(s * .6, s * .22))
        p.drawLine(QPointF(s * .42, s * .42), QPointF(s * .42, s * .68))
        p.drawLine(QPointF(s * .58, s * .42), QPointF(s * .58, s * .68))
    elif kind == "duplicate":
        p.drawRoundedRect(QRectF(s * .2, s * .2, s * .42, s * .42), 2, 2)
        p.drawRoundedRect(QRectF(s * .38, s * .38, s * .42, s * .42), 2, 2)
    elif kind == "fit":
        p.drawLine(QPointF(s * .2, s * .32), QPointF(s * .2, s * .2))
        p.drawLine(QPointF(s * .2, s * .2), QPointF(s * .32, s * .2))
        p.drawLine(QPointF(s * .68, s * .2), QPointF(s * .8, s * .2))
        p.drawLine(QPointF(s * .8, s * .2), QPointF(s * .8, s * .32))
        p.drawLine(QPointF(s * .2, s * .68), QPointF(s * .2, s * .8))
        p.drawLine(QPointF(s * .2, s * .8), QPointF(s * .32, s * .8))
        p.drawLine(QPointF(s * .68, s * .8), QPointF(s * .8, s * .8))
        p.drawLine(QPointF(s * .8, s * .68), QPointF(s * .8, s * .8))
    elif kind == "reset":
        p.drawArc(QRectF(s * .22, s * .22, s * .56, s * .56), 40 * 16, 300 * 16)
        p.drawPolyline(QPolygonF([QPointF(s * .74, s * .12), QPointF(s * .7, s * .3), QPointF(s * .54, s * .24)]))
    elif kind == "frame":
        p.drawRoundedRect(QRectF(s * .16, s * .2, s * .68, s * .6), 2, 2)
        for i in range(3):
            v = s * (.34 + i * .16)
            p.drawLine(QPointF(s * .28, v), QPointF(s * .56, v))
            p.drawLine(QPointF(s * .62, v), QPointF(s * .72, v))
    elif kind == "vertex":
        tri = QPolygonF([QPointF(s * .5, s * .2), QPointF(s * .82, s * .7), QPointF(s * .18, s * .7)])
        p.drawPolygon(tri)
        p.setBrush(QColor(color))
        for pt in tri:
            p.drawEllipse(pt, s * .085, s * .085)
    elif kind == "face":
        p.drawPolygon(QPolygonF([QPointF(s * .18, s * .28), QPointF(s * .5, s * .16),
                                 QPointF(s * .82, s * .34), QPointF(s * .5, s * .8)]))
        p.drawLine(QPointF(s * .5, s * .16), QPointF(s * .5, s * .8))
    elif kind == "soft":
        path = QPainterPath(QPointF(s * .18, s * .6))
        path.cubicTo(QPointF(s * .18, s * .3), QPointF(s * .4, s * .18),
                     QPointF(s * .5, s * .3))
        path.cubicTo(QPointF(s * .6, s * .18), QPointF(s * .82, s * .3),
                     QPointF(s * .82, s * .6))
        path.cubicTo(QPointF(s * .82, s * .82), QPointF(s * .18, s * .82),
                     QPointF(s * .18, s * .6))
        p.drawPath(path)
    elif kind == "mesh":
        p.drawPolygon(QPolygonF([QPointF(s * .16, s * .66), QPointF(s * .38, s * .3),
                                 QPointF(s * .62, s * .58), QPointF(s * .84, s * .3)]))
        p.drawLine(QPointF(s * .16, s * .66), QPointF(s * .62, s * .58))
        p.drawLine(QPointF(s * .62, s * .58), QPointF(s * .84, s * .3))
        p.drawLine(QPointF(s * .38, s * .3), QPointF(s * .84, s * .3))
    elif kind == "close":
        p.drawLine(QPointF(s * .3, s * .3), QPointF(s * .7, s * .7))
        p.drawLine(QPointF(s * .7, s * .3), QPointF(s * .3, s * .7))
    elif kind == "min":
        p.drawLine(QPointF(s * .28, s * .54), QPointF(s * .72, s * .54))
    elif kind == "max":
        p.drawRect(QRectF(s * .3, s * .3, s * .4, s * .4))
    elif kind == "restore":
        p.drawRect(QRectF(s * .26, s * .36, s * .34, s * .34))
        p.drawPolyline(QPolygonF([QPointF(s * .4, s * .3), QPointF(s * .74, s * .3),
                                  QPointF(s * .74, s * .64)]))
    elif kind == "info":
        p.drawEllipse(QRectF(s * .2, s * .2, s * .6, s * .6))
        p.drawLine(QPointF(s * .5, s * .46), QPointF(s * .5, s * .68))
        p.setBrush(QColor(color))
        p.drawEllipse(QRectF(s * .47, s * .32, s * .06, s * .06))
    elif kind == "camera":
        p.drawRoundedRect(QRectF(s * .18, s * .32, s * .48, s * .38), 2, 2)
        p.drawPolygon(QPolygonF([QPointF(s * .66, s * .44), QPointF(s * .84, s * .34),
                                 QPointF(s * .84, s * .68), QPointF(s * .66, s * .58)]))
    p.end()
    return QIcon(px)


def svg_assets():
    """写入样式表所需的小型矢量资源。"""
    os.makedirs(ASSETS, exist_ok=True)
    files = {
        "check.svg": f'<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14">'
                     f'<path d="M3 7.2 L5.8 10 L11 4.2" fill="none" stroke="{PRIMARY_TEXT}" stroke-width="2" '
                     f'stroke-linecap="round" stroke-linejoin="round"/></svg>',
        "dash.svg": f'<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 14 14">'
                    f'<path d="M3.4 7 L10.6 7" fill="none" stroke="{PRIMARY_TEXT}" stroke-width="2" '
                    f'stroke-linecap="round"/></svg>',
        "chevron.svg": f'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10">'
                       f'<path d="M2 3.6 L5 6.6 L8 3.6" fill="none" stroke="{TEXT_DIM}" stroke-width="1.4" '
                       f'stroke-linecap="round" stroke-linejoin="round"/></svg>',
        "chevron_up.svg": f'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10">'
                          f'<path d="M2 6.4 L5 3.4 L8 6.4" fill="none" stroke="{TEXT_DIM}" stroke-width="1.4" '
                          f'stroke-linecap="round" stroke-linejoin="round"/></svg>',
    }
    for name, content in files.items():
        with open(os.path.join(ASSETS, name), "w", encoding="utf-8") as f:
            f.write(content)
    QPixmapCache.clear()
