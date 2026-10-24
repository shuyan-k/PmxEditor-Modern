# -*- coding: utf-8 -*-
"""PMX 编辑器 · 主窗口。"""
from __future__ import annotations

import os
import sys
import traceback

import numpy as np

from .native_backend import backend_label, unavailable_reason

# Load the MSVC extension before Qt DLLs on Windows.
from PyQt5.QtCore import QByteArray, QEvent, QSize, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import (QApplication, QButtonGroup, QFileDialog, QFrame,
                             QHBoxLayout, QLabel, QMainWindow, QMenuBar,
                             QMessageBox, QPushButton, QSplitter,
                             QStackedWidget, QVBoxLayout, QWidget)

from . import theme
from .config import Config
from .doc import Document
from .panels import (BonePage, FramePage, InfoPage, MaterialPage, MorphPage,
                     PhysicsPage, SettingsPage, VertexPage)
from .theme import (ACCENT, ACCENT_2, BORDER, BORDER_SOFT, TEXT_DIM,
                   build_qss, make_icon, mono_font, svg_assets, ui_font)
from .ui_widgets import Switch, icon_button, label
from .viewport import Viewport
from .vpd import (apply_vpd_pose, build_vpd_text, load_vpd, match_vpd,
                 write_vpd_text)

APP_NAME = "PMX 编辑器"
APP_VERSION = "1.0"
PAGES = (
    ("info", "info", "模型信息"),
    ("bone", "bone", "骨骼"),
    ("material", "material", "材质"),
    ("morph", "morph", "形态"),
    ("physics", "physics", "物理"),
    ("settings", "settings", "设置"),
    ("frame", "frame", "表示枠"),
    ("vertex", "vertex", "顶点"),
)
# new pages go last so the existing indices stay stable
RAIL_ORDER = (0, 1, 6, 7, 2, 3, 4, 5)
KIND_PAGE = {"bone": 1, "frame": 6, "vertex": 7, "material": 2, "morph": 3, "rigid": 4, "joint": 4}
# 只改姿态的编辑（压姿态快照即可，不必克隆整模型）
POSE_EDIT_LABELS = ("调整骨骼姿态", "移动骨骼", "旋转骨骼")

# ---------------------------------------------------------------- 无边框支持

def _app_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(ACCENT))
    p.drawRoundedRect(2, 2, 60, 60, 14, 14)
    p.setBrush(QColor("#0f1319"))
    p.drawRoundedRect(11, 11, 42, 42, 9, 9)
    p.setBrush(QColor(ACCENT_2))
    p.drawEllipse(26, 26, 12, 12)
    p.end()
    return QIcon(pm)

class TitleBar(QWidget):
    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self.win = window
        self.setObjectName("TitleBar")
        self.setFixedHeight(40)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 6, 0)
        lay.setSpacing(8)
        self.icon = QLabel()
        self.icon.setPixmap(_app_icon().pixmap(18, 18))
        lay.addWidget(self.icon)
        self.title = label(APP_NAME, "TitleText")
        lay.addWidget(self.title)
        self.sub = label("", "TitleSub")
        lay.addWidget(self.sub)
        lay.addStretch(1)
        self.btn_min = icon_button("min", "最小化", TEXT_DIM, 14, "WinBtn")
        self.btn_max = icon_button("max", "最大化", TEXT_DIM, 14, "WinBtn")
        self.btn_close = icon_button("close", "关闭", TEXT_DIM, 14)
        self.btn_min.setFixedSize(30, 28)
        self.btn_max.setFixedSize(30, 28)
        self.btn_close.setFixedSize(30, 28)
        self.btn_min.setObjectName("WinBtn")
        self.btn_max.setObjectName("WinBtn")
        self.btn_close.setStyleSheet(
            "QPushButton{background:transparent;border:none;border-radius:5px;}"
            "QPushButton:hover{background:#c8423f;}")
        for b in (self.btn_min, self.btn_max, self.btn_close):
            lay.addWidget(b)
        self.btn_min.clicked.connect(window.showMinimized)
        self.btn_max.clicked.connect(self._toggle_max)
        self.btn_close.clicked.connect(window.close)
        window.installEventFilter(self)

    def _toggle_max(self):
        if self.win.isMaximized():
            self.win.showNormal()
        else:
            self.win.showMaximized()

    def set_document(self, name: str, dirty: bool):
        self.sub.setText(("· %s%s" % (name, "  •" if dirty else "")) if name else "")

    def eventFilter(self, obj, e):
        if obj is self.win:
            if e.type() == QEvent.WindowStateChange:
                theme.register_icon(self.btn_max,
                                    "restore" if self.win.isMaximized() else "max",
                                    TEXT_DIM, 14)
        return False

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            wh = self.win.windowHandle()
            if wh is not None:
                try:
                    wh.startSystemMove()
                    return
                except Exception:
                    pass
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._toggle_max()
        super().mouseDoubleClickEvent(e)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(_app_icon())
        self.setMinimumSize(1120, 700)
        self.resize(1560, 920)
        self.setMouseTracking(True)

        self.doc = Document(self)
        self.viewport = Viewport(self)
        # 结构编辑后只刷新当前页，其余页标记为脏，切换过去时再刷新，
        # 避免每次编辑都重建 6 个页面（大模型里 321 项下拉重建很贵）。
        self._pages_dirty = set()
        # 偏好写在 settings.json 里（见 config.py），不再用注册表：
        # 改坏了可以直接打开文件改，删掉就是恢复出厂设置。
        self.config = Config.load()
        self._pages = []
        self._current_page = 0

        self._build_ui()
        self._build_menus()
        self._wire()

        self._set_status("就绪 · 打开一个 PMX 模型开始编辑")
        self._update_title()

    # ------------------------------------------------------------ 界面
    def _build_ui(self):
        shell = QWidget()
        shell.setObjectName("Shell")
        self.setCentralWidget(shell)
        root = QVBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.titlebar = TitleBar(self)
        root.addWidget(self.titlebar)

        self.menubar = QMenuBar()
        self.menubar.setObjectName("MenuBar")
        self.menubar.setNativeMenuBar(False)
        self.menubar.setFixedHeight(28)
        root.addWidget(self.menubar)
        self._root = root

        body = QWidget()
        body_lay = QHBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)
        root.addWidget(body, 1)

        # 左侧导航
        rail = QWidget()
        rail.setObjectName("Rail")
        rail.setFixedWidth(118)
        rail_lay = QVBoxLayout(rail)
        rail_lay.setContentsMargins(8, 10, 8, 10)
        rail_lay.setSpacing(3)
        self.rail_group = QButtonGroup(self)
        self.rail_group.setExclusive(True)
        self.rail_buttons = []
        self._rail_of = {}
        for slot, pi in enumerate(RAIL_ORDER):
            key, icon, text = PAGES[pi]
            b = QPushButton(text)
            b.setObjectName("RailBtn")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setIcon(theme.register_icon(b, icon, TEXT_DIM, 18))
            b.setIconSize(QSize(18, 18))
            b.setFixedHeight(34)
            b.setToolTip(text)
            b.clicked.connect(lambda _c, i=pi: self._select_page(i))
            self.rail_group.addButton(b)
            self.rail_buttons.append(b)
            self._rail_of[pi] = slot
            rail_lay.addWidget(b)
        rail_lay.addStretch(1)
        body_lay.addWidget(rail)

        # 中央 + 右侧检查器
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(1)

        center = QWidget()
        center_lay = QVBoxLayout(center)
        center_lay.setContentsMargins(0, 0, 0, 0)
        center_lay.setSpacing(0)
        center_lay.addWidget(self._build_toolbar())
        center_lay.addWidget(self.viewport, 1)
        self.splitter.addWidget(center)

        self.inspector = QStackedWidget()
        self.inspector.setObjectName("Panel")
        self.inspector.setMinimumWidth(300)
        self._pages = [InfoPage(self.doc), BonePage(self.doc),
                       MaterialPage(self.doc), MorphPage(self.doc),
                       PhysicsPage(self.doc), SettingsPage(self.doc),
                       FramePage(self.doc), VertexPage(self.doc)]
        for p in self._pages:
            self.inspector.addWidget(p)
        self.splitter.addWidget(self.inspector)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([980, 372])
        body_lay.addWidget(self.splitter, 1)

        root.addWidget(self._build_status())
        self._select_page(0)
        self._refresh_pages()

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(44)
        bar.setStyleSheet("background:%s; border-bottom:1px solid %s;" % (theme.BAR_BG, BORDER_SOFT))
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 6, 12, 6)
        lay.setSpacing(4)

        self.btn_open = icon_button("open", "打开 PMX 模型  Ctrl+O", TEXT_DIM, 17)
        self.btn_save = icon_button("save", "保存  Ctrl+S", TEXT_DIM, 17)
        self.btn_undo = icon_button("undo", "撤销  Ctrl+Z", TEXT_DIM, 17)
        self.btn_redo = icon_button("redo", "重做  Ctrl+Y", TEXT_DIM, 17)
        for b in (self.btn_open, self.btn_save):
            lay.addWidget(b)
        sep = QFrame()
        sep.setFixedSize(1, 20)
        sep.setStyleSheet("background:%s;" % BORDER)
        lay.addSpacing(4)
        lay.addWidget(sep)
        lay.addSpacing(4)
        for b in (self.btn_undo, self.btn_redo):
            lay.addWidget(b)
        lay.addSpacing(10)

        self.physics_box = QWidget()
        pbox = QHBoxLayout(self.physics_box)
        pbox.setContentsMargins(10, 0, 6, 0)
        pbox.setSpacing(7)
        self.physics_label = label("物理演算", "Faint")
        pbox.addWidget(self.physics_label)
        self.physics_switch = Switch(False)
        self.physics_switch.setToolTip("物理演算开关（可与姿态编辑同时生效）")
        pbox.addWidget(self.physics_switch)
        self.physics_box.setFixedWidth(124)
        lay.addWidget(self.physics_box)
        lay.addStretch(1)

        self.btn_fit = icon_button("fit", "视图居中  F", TEXT_DIM, 17)
        self.btn_reset = icon_button("reset", "重置姿态  R", TEXT_DIM, 17)
        lay.addWidget(self.btn_fit)
        lay.addWidget(self.btn_reset)
        return bar

    def _build_status(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(26)
        bar.setStyleSheet("background:%s; border-top:1px solid %s;" % (theme.BAR_BG, BORDER_SOFT))
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(10)
        dot = QLabel()
        dot.setPixmap(make_icon("info", ACCENT, 12).pixmap(12, 12))
        lay.addWidget(dot)
        self.status_label = label("就绪", "Faint")
        lay.addWidget(self.status_label)
        lay.addStretch(1)
        self.sel_label = label("", "Faint")
        lay.addWidget(self.sel_label)
        self.phys_label = label(backend_label(), "Faint")
        self.phys_label.setFont(mono_font(8.4))
        if unavailable_reason():
            self.phys_label.setToolTip(
                "C++ 计算后端尚不可用，当前使用 NumPy 回退。运行 "
                "native\\build_core.ps1 构建。\n%s" % unavailable_reason())
        else:
            self.phys_label.setToolTip("pybind11 C++ 计算后端已启用")
        lay.addWidget(self.phys_label)
        return bar

    def _build_menus(self):
        mb = self.menubar

        m_file = mb.addMenu("文件")
        a = m_file.addAction("打开模型…")
        a.setShortcut("Ctrl+O")
        a.triggered.connect(self.open_dialog)
        a = m_file.addAction("导入 VPD 姿态…")
        a.triggered.connect(self.import_vpd_dialog)
        a = m_file.addAction("导出 VPD 姿态…")
        a.triggered.connect(self.export_vpd_dialog)
        m_file.addSeparator()
        a = m_file.addAction("保存")
        a.setShortcut("Ctrl+S")
        a.triggered.connect(self.save)
        a = m_file.addAction("另存为…")
        a.setShortcut("Ctrl+Shift+S")
        a.triggered.connect(self.save_as)
        m_file.addSeparator()
        a = m_file.addAction("关闭模型")
        a.triggered.connect(self.close_model)
        m_file.addSeparator()
        a = m_file.addAction("退出")
        a.triggered.connect(self.close)

        m_edit = mb.addMenu("编辑")
        a = m_edit.addAction("撤销")
        a.setShortcut("Ctrl+Z")
        a.triggered.connect(self.undo)
        a = m_edit.addAction("重做")
        a.setShortcut("Ctrl+Y")
        a.triggered.connect(self.redo)

        m_view = mb.addMenu("视图")
        self.act_physics = m_view.addAction("物理演算")
        self.act_physics.setCheckable(True)
        self.act_physics.setShortcut("P")
        self.act_physics.triggered.connect(self.toggle_physics)
        m_view.addSeparator()
        a = m_view.addAction("视图全部")
        a.setShortcut("F")
        a.triggered.connect(self.viewport.frame_all)
        a = m_view.addAction("定位选中")
        a.triggered.connect(self.viewport.frame_selected)
        m_view.addSeparator()
        self.display_actions = {}
        for text, key in (("地面网格", "show_grid"), ("骨骼", "show_bones"),
                          ("刚体", "show_rigid"), ("关节", "show_joints"),
                          ("材质贴图", "show_texture"), ("卡通光照", "toon"),
                          ("描边", "outline"), ("线框", "wireframe")):
            act = m_view.addAction(text)
            act.setCheckable(True)
            act.setChecked(bool(getattr(self.viewport, key)))
            act.toggled.connect(lambda on, k=key: self._toggle_display(k, on))
            self.display_actions[key] = act

        m_help = mb.addMenu("帮助")
        a = m_help.addAction("快捷键与说明")
        a.triggered.connect(lambda: self._select_page(5))
        a = m_help.addAction("关于")
        a.triggered.connect(self._about)

    # ------------------------------------------------------------ 信号
    def _wire(self):
        doc = self.doc
        doc.edited.connect(self._on_edited)
        doc.selectionChanged.connect(self._on_selection)
        doc.status.connect(self._set_status)
        doc.dirtyChanged.connect(self._on_dirty)
        doc.pose_capture = self._capture_pose
        doc.pose_restore = self._restore_pose
        doc.morph_capture = self._capture_morphs
        doc.morph_restore = self._restore_morphs

        vp = self.viewport
        vp.boneClicked.connect(lambda i: doc.select("bone", i))
        vp.rigidClicked.connect(lambda i: doc.select("rigid", i))
        vp.jointClicked.connect(lambda i: doc.select("joint", i))
        vp.selectionCleared.connect(lambda: doc.select("", -1))
        vp.editStarted.connect(self._on_edit_started)
        vp.poseAboutToReset.connect(lambda: self.doc.push_pose_undo("重置姿态"))
        vp.statusChanged.connect(self._set_status)

        self.btn_open.clicked.connect(self.open_dialog)
        self.btn_save.clicked.connect(self.save)
        self.btn_undo.clicked.connect(self.undo)
        self.btn_redo.clicked.connect(self.redo)
        self.btn_fit.clicked.connect(vp.frame_all)
        self.btn_reset.clicked.connect(vp.reset_pose)
        # F / R 由「视图」菜单的 QAction 提供窗口级快捷键（QAction 本身就是全局的），
        # 这里不再额外建 QShortcut，否则会与菜单项冲突成 "Ambiguous shortcut overload"。
        self.physics_switch.toggled.connect(self.set_physics)

        morph = self._pages[3]
        morph.previewChanged.connect(vp.set_morph_weights)
        settings = self._pages[5]
        settings.displayChanged.connect(self._apply_display)
        settings.physicsApply.connect(self._apply_physics)
        settings.themeChanged.connect(self._set_theme)
        settings.brightnessChanged.connect(self._set_brightness)
        settings.configReloaded.connect(self._reload_settings)
        self._restore_view_settings()

        self.setAcceptDrops(True)

    def _on_edit_started(self, label: str):
        # 姿态类编辑只压姿态快照（不含 18 ms 的整模型 deepcopy），
        # 撤销时也不会触发 _reload_structure 全量重建。
        if label in POSE_EDIT_LABELS or "姿态" in label:
            self.doc.push_pose_undo(label)
        else:
            self.doc.push_undo(label)

    def _capture_pose(self):
        p = self.viewport.pose
        if p is None:
            return None
        return (p.base_rot.copy(), p.base_trans.copy())

    def _restore_pose(self, snap):
        p = self.viewport.pose
        if p is None or snap is None:
            return
        rot, trans = snap
        if rot.shape != p.base_rot.shape:
            return
        p.base_rot = rot.copy()
        p.base_trans = trans.copy()
        p.apply(self.viewport.morph_weights,
                self.doc.model.morphs if self.doc.model else None)
        self.viewport.mark_dirty()

    def _capture_morphs(self):
        return dict(self.viewport.morph_weights)

    def _restore_morphs(self, weights):
        self.viewport.set_morph_weights(weights or {})

    # ------------------------------------------------------------ 页面
    def _select_page(self, i: int):
        i = max(0, min(len(self._pages) - 1, i))
        self._current_page = i
        self.inspector.setCurrentIndex(i)
        self.rail_buttons[self._rail_of[i]].setChecked(True)
        if i in self._pages_dirty:
            self._pages_dirty.discard(i)
            self._refresh_one(i)
            self._reselect_page(i)
        page = self._pages[i]
        if i == 1 and not self.viewport.show_bones:
            # 骨骼页必须看得到骨架，否则改数值时视口毫无反馈
            self._apply_display({"show_bones": True})
            self._pages[5].sync_display(self.viewport)
        if i == 5:
            page.sync_display(self.viewport)

    def _refresh_one(self, i: int):
        p = self._pages[i]
        # 刷新会重建内容，滚动位置会被重置到顶部；记住旧值再写回，
        # 否则在大模型里逐项编辑时每次都要重新滚回原处。
        area = p.scroll_area()
        bar = area.verticalScrollBar() if area is not None else None
        offset = bar.value() if bar is not None else 0
        try:
            p.refresh()
        except Exception as e:
            self._set_status("面板刷新失败：%s" % e)
        if bar is not None and offset:
            # 内容高度变化后 setValue 会自动夹到合法范围
            bar.setValue(offset)

    def _refresh_pages(self, active_only: bool = False):
        for i in range(len(self._pages)):
            if active_only and i != self._current_page:
                self._pages_dirty.add(i)
                continue
            self._pages_dirty.discard(i)
            self._refresh_one(i)

    def _reselect_page(self, i: int):
        """页面刚被刷新过，把当前选中的条目重新填回详情区。"""
        kind, index = self.doc.sel_kind, self.doc.sel_index
        if not kind or index < 0:
            return
        if KIND_PAGE.get(kind) != i:
            return
        try:
            self._pages[i].select(kind, index)
        except Exception as e:
            self._set_status("选择失败：%s" % e)

    # ------------------------------------------------------------ 文档
    def _update_title(self):
        m = self.doc.model
        if m:
            name = os.path.basename(self.doc.path or (m.name or "未命名")) or "未命名"
            self.setWindowTitle("%s — %s" % (name, APP_NAME))
            self.titlebar.set_document(name, self.doc.dirty)
            self.phys_label.setText(
                "%s · %d 刚体" % (backend_label(), len(m.rigid)))
        else:
            self.setWindowTitle(APP_NAME)
            self.titlebar.set_document("", False)
            self.phys_label.setText(backend_label())

    def _on_dirty(self, dirty: bool):
        self._update_title()

    def _set_status(self, text: str):
        self.status_label.setText(text)

    # ------------------------------------------------------------ 偏好
    def _start_dir(self) -> str:
        """上次打开/保存的目录；路径已不存在就退回当前工作目录。"""
        path = str(self.config.get("paths/last_dir", "") or "")
        return path if os.path.isdir(path) else os.getcwd()

    def _vpd_dir(self) -> str:
        path = str(self.config.get("paths/last_vpd_dir", "") or "")
        return path if os.path.isdir(path) else self._start_dir()

    def _restore_view_settings(self):
        """把 settings.json 里的亮度/显示开关/物理参数恢复进视口与设置页。"""
        page = self._pages[5]
        page.sync_config(self.config)
        bg = float(self.config.get("view/bg_brightness", 1.0))
        mb = float(self.config.get("view/model_brightness", 1.0))
        self.viewport.set_brightness(bg, mb)
        page.sync_brightness(bg, mb)
        values = {}
        for key in ("show_grid", "show_bones", "show_rigid", "show_joints",
                    "show_texture", "toon", "outline", "wireframe"):
            values[key] = bool(self.config.get("view/" + key, True))
        try:
            self.viewport.set_display(**values)
            for key, on in values.items():
                act = self.display_actions.get(key)
                if act is not None:
                    act.blockSignals(True)
                    act.setChecked(bool(on))
                    act.blockSignals(False)
            page.sync_display(self.viewport)
        except Exception:
            traceback.print_exc()
        try:
            page.gravity.setValue(float(self.config.get("physics/gravity", -9.8)))
            page.iterations.setValue(int(self.config.get("physics/iterations", 10)))
            page.ground.setChecked(bool(self.config.get("physics/ground", True)))
        except Exception:
            traceback.print_exc()

    def open_dialog(self):
        start = self._start_dir()
        path, _ = QFileDialog.getOpenFileName(self, "打开 PMX 模型", start,
                                              "PMX 模型 (*.pmx);;所有文件 (*.*)")
        if path:
            self.open_path(path)

    def open_path(self, path: str):
        if not self._maybe_save():
            return
        self.doc.suppress = True
        try:
            self.doc.load(path)
        except Exception as e:
            QMessageBox.critical(self, "打开失败", "无法读取模型：\n%s" % e)
            self._set_status("打开失败：%s" % e)
            return
        finally:
            self.doc.suppress = False
        self.config.set("paths/last_dir", os.path.dirname(path))
        self._apply_model()
        self._set_status("已打开 %s" % os.path.basename(path))

    # ------------------------------------------------------------ VPD 姿态
    def import_vpd_dialog(self):
        if not self.doc.model or self.viewport.pose is None:
            self._set_status("请先打开 PMX 模型")
            return
        start = self._vpd_dir()
        path, _ = QFileDialog.getOpenFileName(
            self, "导入 VPD 姿态", start,
            "VPD 姿态 (*.vpd);;所有文件 (*.*)")
        if path:
            self.import_vpd_path(path)

    def import_vpd_path(self, path: str) -> bool:
        """解析并应用 VPD；返回是否实际改变了姿态。"""
        if not self.doc.model or self.viewport.pose is None:
            self._set_status("请先打开 PMX 模型")
            return False
        try:
            vpd = load_vpd(path)
        except Exception as e:
            QMessageBox.critical(self, "VPD 导入失败", "无法读取 VPD：\n%s" % e)
            self._set_status("VPD 导入失败：%s" % e)
            return False
        match = match_vpd(self.doc.model, vpd)
        if not match.pairs and not match.morph_pairs:
            QMessageBox.warning(
                self, "VPD 导入失败",
                "没有骨骼或形态名称能与当前模型匹配。\n\n"
                "VPD 骨骼：%d 根，形态：%d 个；"
                "请确认该姿态与当前模型使用同一套命名。"
                % (len(vpd.bones), len(vpd.morphs)))
            self._set_status("VPD 未匹配任何骨骼或形态")
            return False
        if not self._confirm_vpd(path, match):
            return False

        # 物理演算中的姿态会被刚体覆盖，导入前先停下演算。
        if match.pairs and self.viewport.physics.enabled:
            self.set_physics(False)
        # VPD 只改姿态与形态权重，不动 PMX 数据：压轻量姿态条目即可
        self.doc.push_pose_undo("导入 VPD 姿态")
        apply_vpd_pose(self.viewport.pose, match,
                       self.viewport.morph_weights, self.doc.model.morphs)
        self.viewport.mark_dirty()
        self.doc.mark_dirty()
        self.doc.edited.emit("pose")
        self.config.set("paths/last_vpd_dir", os.path.dirname(path))
        text = "已导入 VPD 姿态：%d/%d 根骨骼" % (match.matched, match.total)
        if match.missing:
            text += "，%d 根未匹配" % len(match.missing)
        if match.morph_pairs:
            text += "；%d/%d 个形态" % (match.morph_matched,
                                       match.morph_total)
        self._set_status(text)
        return True

    def _confirm_vpd(self, path: str, match) -> bool:
        def preview(items, limit=40):
            text = "、".join(str(item) for item in items[:limit])
            if len(items) > limit:
                text += " …（共 %d 项）" % len(items)
            return text

        details = []
        if match.missing:
            details.append("未匹配骨骼（%d）：\n%s" % (
                len(match.missing),
                preview([bone.name for bone in match.missing])))
        if match.renamed:
            details.append("按宽松名称匹配的骨骼（%d）：\n%s" % (
                len(match.renamed),
                preview(["%s → %s" % pair for pair in match.renamed])))
        if match.duplicate_vpd:
            details.append("VPD 内重复骨骼名（%d）：\n%s" % (
                len(match.duplicate_vpd), preview(match.duplicate_vpd)))
        if match.duplicate_target:
            details.append("目标模型重名骨骼（%d）：\n%s" % (
                len(match.duplicate_target),
                preview(match.duplicate_target)))
        if match.morph_missing:
            details.append("未匹配形态（%d）：\n%s" % (
                len(match.morph_missing),
                preview([morph.name for morph in match.morph_missing])))
        if match.morph_renamed:
            details.append("按宽松名称匹配的形态（%d）：\n%s" % (
                len(match.morph_renamed),
                preview(["%s → %s" % pair for pair in match.morph_renamed])))

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning
                    if (match.missing or match.morph_missing)
                    else QMessageBox.Information)
        box.setWindowTitle("导入 VPD 姿态")
        box.setText(
            "「%s」包含 %d 根骨骼、%d 个形态，可匹配 %d 根骨骼、%d 个形态。"
            % (os.path.basename(path), match.total, match.morph_total,
               match.matched, match.morph_matched))
        box.setInformativeText(
            "导入会重置当前姿态，并用 VPD 权重替换形态预览；"
            "未匹配项保持初始状态，可用 Ctrl+Z 撤销。")
        if details:
            box.setDetailedText("\n\n".join(details))
        box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Ok)
        box.button(QMessageBox.Ok).setText("应用姿态")
        box.button(QMessageBox.Cancel).setText("取消")
        return box.exec_() == QMessageBox.Ok

    # ------------------------------------------------------------ VPD 导出
    def export_vpd_dialog(self):
        if not self.doc.model or self.viewport.pose is None:
            self._set_status("请先打开 PMX 模型")
            return
        start = self._vpd_dir()
        if self.doc.path:
            base = os.path.splitext(os.path.basename(self.doc.path))[0]
        else:
            base = (self.doc.model.name or "pose").strip() or "pose"
        default = os.path.join(start, base + "_pose.vpd")
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 VPD 姿态", default,
            "VPD 姿态 (*.vpd);;所有文件 (*.*)")
        if path:
            self.export_vpd_path(path)

    def export_vpd_path(self, path: str) -> bool:
        """把当前姿态导出为 VPD；返回是否写出文件。"""
        if not self.doc.model or self.viewport.pose is None:
            self._set_status("请先打开 PMX 模型")
            return False
        if not path.lower().endswith(".vpd"):
            path += ".vpd"
        model_name = os.path.basename(self.doc.path) if self.doc.path else ""
        if not model_name:
            model_name = (self.doc.model.name or "") + ".pmx"
        text, bones, morphs = build_vpd_text(
            self.doc.model, self.viewport.pose,
            self.viewport.morph_weights, model_name=model_name)
        if not bones and not morphs:
            QMessageBox.information(
                self, "导出 VPD 姿态",
                "当前姿态与初始姿态相同，没有可导出的骨骼或形态变化。")
            self._set_status("VPD 导出已取消：姿态无变化")
            return False
        try:
            result = write_vpd_text(path, text, bones, morphs)
        except Exception as e:
            QMessageBox.critical(self, "VPD 导出失败", "无法写入 VPD：\n%s" % e)
            self._set_status("VPD 导出失败：%s" % e)
            return False
        self.config.set("paths/last_vpd_dir", os.path.dirname(path))
        text = "已导出 VPD：%d 根骨骼，%d 个形态" % (result.bones, result.morphs)
        if result.encoding != "cp932":
            text += "（含非 Shift-JIS 名称，已保存为 UTF-8）"
        self._set_status(text)
        return True

    def _apply_model(self):
        self.doc.suppress = True
        try:
            self.viewport.set_model(self.doc.model)
            self.viewport.set_selection("", -1)
            self._refresh_pages()
            self._pages[5].sync_display(self.viewport)
            for key, act in self.display_actions.items():
                act.blockSignals(True)
                act.setChecked(bool(getattr(self.viewport, key)))
                act.blockSignals(False)
        finally:
            self.doc.suppress = False
        self._update_title()

    def _reload_structure(self):
        """结构性变化后重建视口，保留相机与形态预览。

        骨骼/刚体/关节的增删只要不触碰网格本体，就先走 Viewport.rebuild_structure()
        就地重建：省掉网格重传、贴图预热与相机重设；顶点/索引/UV/材质区间变化
        则回落到完整的 set_model()。
        """
        vp = self.viewport
        cam = vp.camera
        state = (np.array(cam.target, copy=True), cam.distance, cam.yaw, cam.pitch)
        weights = dict(vp.morph_weights)
        pose_snap = None
        if vp.pose is not None:
            pose_snap = (vp.pose.base_rot.copy(), vp.pose.base_trans.copy())
        was_physics = bool(vp.physics.enabled)
        kind, index = self.doc.sel_kind, self.doc.sel_index
        self.doc.suppress = True
        try:
            # 撤销/重做会整体替换 Document.model 对象：网格与材质布局没变时，
            # 先让视口接管新对象（只重建 Pose/Deformer），仍可走分项重建；
            # 布局变了（顶点/索引/UV/材质区间）才回落到完整 set_model。
            adopted = True
            if vp.model is not self.doc.model:
                adopted = vp.adopt_model(self.doc.model)
            if adopted and vp.rebuild_structure():
                self._refresh_pages(active_only=True)
                self._pages[5].sync_display(vp)
                if kind:
                    self.doc.select(kind, index)
                else:
                    vp.set_selection("", -1)
                self._update_title()
                return
            vp.set_model(self.doc.model)
            cam2 = vp.camera
            cam2.target = state[0]
            cam2.distance, cam2.yaw, cam2.pitch = state[1], state[2], state[3]
            vp.set_morph_weights(weights)
            # 重建视口会换掉 Pose；姿态撤销依赖紧接着的 edited("reload")，
            # 因此这里恢复旧姿态，骨骼数量变化时由形状检查自动跳过。
            if (pose_snap is not None and vp.pose is not None
                    and pose_snap[0].shape == vp.pose.base_rot.shape):
                vp.pose.base_rot = pose_snap[0]
                vp.pose.base_trans = pose_snap[1]
                vp.pose.apply(vp.morph_weights, self.doc.model.morphs)
                vp.pose.world_update()
                vp.mark_dirty()
            if was_physics:
                vp.set_physics(True)
            self._refresh_pages()
            self._pages[5].sync_display(vp)
            if kind:
                self.doc.select(kind, index)
            else:
                vp.set_selection("", -1)
        finally:
            self.doc.suppress = False
        self._update_title()

    EDIT_STATUS = {
        "reload": "已重新载入模型",
        "structure": "已更新模型结构",
        "physics": "已更新物理设置",
        "physics_live": "已应用物理参数（热更新）",
        "material": "已更新材质",
        "morph": "已更新形态",
        "pose": "姿态已更新",
    }

    def _on_edited(self, kind: str):
        if not self.doc.model or self.doc.suppress:
            return
        self._set_status(self.EDIT_STATUS.get(kind, "已修改：" + str(kind)))
        if kind == "reload" or kind == "structure":
            self._reload_structure()
            return
        if kind == "physics":
            self._pages[4].refresh()
            self.viewport.rebuild_physics()
            self._update_title()
            return
        if kind == "physics_live":
            # 质量/摩擦力直接写进现有 Bullet 世界，避免重建（大模型约 77 ms）
            self.viewport.apply_rigid_params(self.doc.sel_index)
            self._update_title()
            return
        if kind == "material":
            self.viewport.refresh_textures()
            return
        if kind == "morph":
            self.viewport.set_morph_weights(self.viewport.morph_weights)
            return
        self.viewport.mark_dirty()

    def _on_selection(self, kind: str, index: int):
        self.viewport.set_selection(kind, index)
        page = KIND_PAGE.get(kind)
        if page is not None and page != self._current_page:
            self._select_page(page)
        if kind:
            if page is not None and page in self._pages_dirty:
                self._pages_dirty.discard(page)
                self._refresh_one(page)
            p = self._pages[page] if page is not None else None
            if p is not None:
                try:
                    p.select(kind, index)
                except Exception as e:
                    self._set_status("选择失败：%s" % e)
        name = ""
        m = self.doc.model
        if m and index >= 0:
            if kind == "bone" and index < len(m.bones):
                name = m.bones[index].name
            elif kind == "material" and index < len(m.materials):
                name = m.materials[index].name
            elif kind == "morph" and index < len(m.morphs):
                name = m.morphs[index].name
            elif kind == "rigid" and index < len(m.rigid):
                name = m.rigid[index].name
            elif kind == "joint" and index < len(m.joints):
                name = m.joints[index].name
            self.sel_label.setText(("%s · %s" % (KIND_NAMES.get(kind, kind), name))
                                   if name else "")
        else:
            self.sel_label.setText("")

    def save(self):
        if not self.doc.model:
            return
        if not self.doc.path:
            self.save_as()
            return
        try:
            self.doc.save(self.doc.path)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
            return
        self._set_status("已保存 %s" % os.path.basename(self.doc.path))

    def save_as(self):
        if not self.doc.model:
            return
        start = self.doc.path or os.path.join(
            self._start_dir(), "%s.pmx" % (self.doc.model.name or "model"))
        path, _ = QFileDialog.getSaveFileName(self, "另存为 PMX", start,
                                              "PMX 模型 (*.pmx)")
        if not path:
            return
        try:
            self.doc.save(path)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
            return
        self.config.set("paths/last_dir", os.path.dirname(path))
        self._update_title()
        self._set_status("已保存 %s" % os.path.basename(path))

    def close_model(self):
        if not self._maybe_save():
            return
        self.doc.clear()
        self.viewport.clear_model()
        self._refresh_pages()
        self._select_page(0)
        self._update_title()
        self._set_status("模型已关闭")

    def _maybe_save(self) -> bool:
        if not self.doc.model or not self.doc.dirty:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("未保存的修改")
        box.setText("「%s」有未保存的修改。" % (self.doc.model.name or "模型"))
        box.setInformativeText("是否在继续之前保存？")
        box.setStandardButtons(QMessageBox.Save | QMessageBox.Discard |
                               QMessageBox.Cancel)
        box.setDefaultButton(QMessageBox.Save)
        r = box.exec_()
        if r == QMessageBox.Save:
            self.save()
            return not self.doc.dirty
        return r == QMessageBox.Discard

    def undo(self):
        self.doc.undo()
        self._update_title()

    def redo(self):
        self.doc.redo()
        self._update_title()

    # ------------------------------------------------------------ 视图
    def set_physics(self, on: bool):
        """物理演算开关；姿态编辑始终可用，两者可以同时生效。"""
        on = bool(on)
        self.viewport.set_physics(on)
        enabled = bool(self.viewport.physics.enabled)
        for w in (self.physics_switch, self.act_physics):
            if w.isChecked() != enabled:
                w.blockSignals(True)
                w.setChecked(enabled)
                w.blockSignals(False)
        if enabled:
            self._apply_display({"show_rigid": True, "show_joints": True,
                                 "show_bones": True})
            self._pages[5].sync_display(self.viewport)
            self._set_status("物理演算已开启 · 可同时摆姿（左键位移 / 右键旋转）")
        else:
            self._set_status("物理演算已停止")

    def toggle_physics(self, checked: bool = None):
        if checked is None:
            checked = not self.viewport.physics.enabled
        self.set_physics(checked)

    def _toggle_display(self, key: str, on: bool):
        self.viewport.set_display(**{key: on})
        self.config.set("view/" + key, bool(on))
        self._pages[5].sync_display(self.viewport)

    def _apply_display(self, values: dict):
        self.viewport.set_display(**values)
        for key, on in values.items():
            act = self.display_actions.get(key)
            if act is not None:
                act.blockSignals(True)
                act.setChecked(bool(on))
                act.blockSignals(False)

    def _reload_settings(self):
        """重新读磁盘上的 settings.json 并立即应用（手工改文件后免重启）。"""
        cfg = Config.load(force=True)
        self.config = cfg
        want = "light" if str(cfg.get("theme", "dark")).lower() == "light" else "dark"
        self._set_theme(want, announce=False)
        self._restore_view_settings()
        self._set_status("已重新载入设置：%s" % cfg.path)

    def _set_brightness(self, bg: float, model: float):
        self.viewport.set_brightness(bg, model)
        self.config.update({"view/bg_brightness": float(bg),
                            "view/model_brightness": float(model)})
        self._set_status("亮度：背景 %d%% · 模型 %d%%"
                         % (round(bg * 100), round(model * 100)))

    def _apply_physics(self, values: dict):
        if not self.doc.model or self.viewport.pose is None:
            self._set_status("未载入模型，无法应用物理参数")
            return
        self.viewport.apply_physics_settings(**values)
        self.config.update({"physics/" + key: values[key] for key in values})
        self._set_status("物理参数已应用")

    def _set_theme(self, name: str, announce: bool = True):
        """即时切换配色：重建样式表、内联样式、图标与视口底色。"""
        target = ("light" if str(name).lower() in ("light", "亮色", "浅色")
                  else "dark")
        # 先落盘再刷新界面：刷新链路（图标、视口底色）在个别显卡/GL 驱动上
        # 可能抛异常，若放到最后，主题就没存下来——表现为「主题自动保存失效」。
        try:
            self.config.set("theme", target)
        except Exception:
            traceback.print_exc()
        if target == theme.current_name():
            self._pages[5].theme_seg.set_value(target)
            return
        theme.apply_theme(target)
        theme.sync_modules()
        try:
            theme.remap_stylesheets()
            theme.svg_assets()
            theme.refresh_icons()
            QApplication.instance().setStyleSheet(theme.build_qss())
        except Exception:
            traceback.print_exc()
        try:
            self.viewport.refresh_theme()
        except Exception:
            traceback.print_exc()
        self._pages[5].theme_seg.set_value(theme.current_name())
        self.centralWidget().update()
        if announce:
            self._set_status("已切换为%s主题"
                             % ("亮色" if theme.current_name() == "light" else "深色"))

    def _about(self):
        QMessageBox.about(
            self, "关于 %s" % APP_NAME,
            "%s %s\n\n"
            "PMX 2.0 / 2.1 查看与编辑工具，使用 Python + PyQt5 重写。\n"
            "物理：Bullet（开源，自编译 bullet_phys.dll）\n"
            "界面字体：Microsoft YaHei UI，数值：Consolas\n\n"
            "日文名称保留原名，并提供中文对照显示。"
            % (APP_NAME, APP_VERSION))

    # ------------------------------------------------------------ 拖动打开
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            for u in e.mimeData().urls():
                p = u.toLocalFile().lower()
                if p.endswith(".pmx") or (
                        p.endswith(".vpd") and self.doc.model is not None):
                    e.acceptProposedAction()
                    return
        super().dragEnterEvent(e)

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            lower = p.lower()
            if lower.endswith(".pmx"):
                self.open_path(p)
                e.acceptProposedAction()
                return
            if lower.endswith(".vpd") and self.doc.model is not None:
                self.import_vpd_path(p)
                e.acceptProposedAction()
                return
        super().dropEvent(e)

    def closeEvent(self, e):
        if not self._maybe_save():
            e.ignore()
            return
        try:
            self.config.update({
                # 以"屏幕上实际生效的主题"为准落盘：切换过程中的任何异常都不会
                # 让存档停留在上一个主题，下次启动就不会反过来闪一下。
                "theme": theme.current_name(),
                "window/geometry": bytes(self.saveGeometry().toBase64()).decode("ascii"),
                "window/splitter": [int(s) for s in self.splitter.sizes()],
            })
        except Exception:
            pass
        try:
            self.config.save()
        except Exception:
            traceback.print_exc()
        self.viewport.physics.release()
        # 显式释放网格/叠加层缓冲与纹理，避免关窗后显存留在驱动侧
        self.viewport.release_gpu_resources()
        super().closeEvent(e)

    # ------------------------------------------------------------ 无边框缩放
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and not (self.isMaximized() or self.isFullScreen()):
            m = 6
            p = e.pos()
            edges = Qt.Edges()
            if p.x() <= m:
                edges |= Qt.LeftEdge
            elif p.x() >= self.width() - m:
                edges |= Qt.RightEdge
            if p.y() <= m:
                edges |= Qt.TopEdge
            elif p.y() >= self.height() - m:
                edges |= Qt.BottomEdge
            if edges and self.windowHandle() is not None:
                try:
                    self.windowHandle().startSystemResize(edges)
                    return
                except Exception:
                    pass
        super().mousePressEvent(e)

    def showEvent(self, e):
        super().showEvent(e)
        geo = self.config.get("window/geometry", "")
        if geo:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geo.encode("ascii")))
            except Exception:
                pass
        sizes = self.config.get("window/splitter", [])
        if sizes:
            try:
                self.splitter.setSizes([int(s) for s in sizes])
            except Exception:
                pass

KIND_NAMES = {"bone": "骨骼", "material": "材质", "morph": "形态",
              "rigid": "刚体", "joint": "关节"}

# ---------------------------------------------------------------- 启动

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--verify-backend":
        from tools.verify_native_backend import run_cli
        return run_cli(sys.argv[2:], in_process=True, require_out=True)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    saved_theme = Config.load().get("theme", "dark")
    # 界面始终先按深色构建，再切到保存的主题：
    # 切换逻辑依赖深色原始样式作为基准，可保证往返后精确还原。
    theme.apply_theme("dark")
    theme.sync_modules()
    theme.svg_assets()
    app.setStyleSheet(build_qss())
    app.setFont(ui_font(9.0))
    win = MainWindow()
    # 恢复存档主题放在 show() 之前：窗口一旦可见再切主题会先渲染一帧深色
    # 再刷成亮色，肉眼就是「启动深色、随后闪一下变白」。
    want = "light" if str(saved_theme).lower() == "light" else "dark"
    if want != theme.current_name():
        win._set_theme(want, announce=False)
    win.show()
    if len(sys.argv) > 1 and sys.argv[1].lower().endswith(".pmx"):
        win.open_path(sys.argv[1])
    return app.exec_()

if __name__ == "__main__":
    sys.exit(main())
