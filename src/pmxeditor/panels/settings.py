"""显示与物理设置页。"""
from __future__ import annotations

# -*- coding: utf-8 -*-
from PyQt5.QtCore import Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QGridLayout, QHBoxLayout, QSlider, QSpinBox, QVBoxLayout, QWidget)
from ..theme import mono_font
from .. import theme
from ..ui_widgets import (Form, Segmented, Switch, label, make_spin, text_button)
from .base import PageBase

# ================================================================= 设置

class SettingsPage(PageBase):
    displayChanged = pyqtSignal(dict)
    brightnessChanged = pyqtSignal(float, float)
    physicsApply = pyqtSignal(dict)
    themeChanged = pyqtSignal(str)
    configReloaded = pyqtSignal()

    def __init__(self, doc, parent=None):
        super().__init__(doc, "设置", "显示与物理", parent)
        scroll = self.scroll(QWidget())
        body = scroll.widget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 2, 4)
        bl.setSpacing(8)

        card, sec = self._card("视图显示")
        self.display_switches = {}
        items = (("show_grid", "地面网格"), ("show_bones", "骨骼"),
                 ("show_rigid", "刚体"), ("show_joints", "关节"),
                 ("show_texture", "材质贴图"), ("toon", "卡通光照"),
                 ("outline", "描边"), ("wireframe", "线框"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        for i, (key, txt) in enumerate(items):
            sw = Switch(key in ("show_grid", "show_bones", "show_rigid",
                                "show_joints", "show_texture", "toon", "outline"))
            sw.toggled.connect(lambda on, k=key: self._display(k, on))
            self.display_switches[key] = sw
            grid.addWidget(sw, i // 2, (i % 2) * 2)
            grid.addWidget(label(txt, "Muted"), i // 2, (i % 2) * 2 + 1)
        sec.add_layout(grid)
        bl.addWidget(card)

        card, sec = self._card("亮度", "只影响显示，不写入模型")
        self.bg_slider, self.bg_value = self._brightness_row(sec, "背景", 20, 300, 100)
        self.model_slider, self.model_value = self._brightness_row(sec, "模型", 20, 220, 100)
        self.bg_slider.valueChanged.connect(self._brightness)
        self.model_slider.valueChanged.connect(self._brightness)
        reset = text_button("恢复默认", "Ghost", "refresh")
        reset.clicked.connect(self._reset_brightness)
        sec.add(reset)
        sec.add(label("背景：视口底色明度；模型：材质漫反射/环境色倍率。", "Faint", True))
        bl.addWidget(card)

        card, sec = self._card("叠加层不透明度", "骨骼 / 刚体 / 关节实体")
        self.bone_opacity, self.bone_opacity_value = self._brightness_row(
            sec, "骨骼", 0, 100, 16)
        self.rigid_opacity, self.rigid_opacity_value = self._brightness_row(
            sec, "刚体", 0, 100, 22)
        self.joint_opacity, self.joint_opacity_value = self._brightness_row(
            sec, "关节", 0, 100, 33)
        for slider in (self.bone_opacity, self.rigid_opacity, self.joint_opacity):
            slider.valueChanged.connect(self._opacity)
        sec.add(label("0% 完全隐藏实体，100% 完全不透明。", "Faint", True))
        bl.addWidget(card)

        card, sec = self._card("Bullet 物理", "实时预览参数")
        form = Form(64)
        self.gravity = make_spin(2, -100.0, 100.0, 0.5)
        self.gravity.setValue(-9.8)
        self.iterations = QSpinBox()
        self.iterations.setRange(1, 60)
        self.iterations.setValue(10)
        self.iterations.setButtonSymbols(QSpinBox.NoButtons)
        self.ground = Switch(True)
        row = QHBoxLayout()
        row.addWidget(self.ground)
        row.addWidget(label("显示地面", "Muted"))
        row.addStretch(1)
        form.add("重力", self.gravity)
        form.add("迭代次数", self.iterations)
        form.add_full(row)
        sec.add(form)
        apply_btn = text_button("应用物理参数", "Primary", "play")
        apply_btn.clicked.connect(self._apply_physics)
        sec.add(apply_btn)
        bl.addWidget(card)

        card, sec = self._card("界面主题", "即时生效")
        self.theme_seg = Segmented([("dark", "深色"), ("light", "亮色")])
        self.theme_seg.set_value(theme.current_name())
        self.theme_seg.changed.connect(self.themeChanged.emit)
        sec.add(self.theme_seg)
        sec.add(label("亮色主题适合明亮环境，选择会自动保存。", "Faint", True))
        bl.addWidget(card)

        card, sec = self._card("配置文件", "所有偏好都存在这个 JSON 文件里")
        self.config_path = label("—", "Faint", True)
        self.config_path.setWordWrap(True)
        sec.add(self.config_path)
        row = QHBoxLayout()
        row.setSpacing(8)
        open_btn = text_button("打开所在文件夹", "Ghost", "open")
        open_btn.clicked.connect(self._open_config_dir)
        reload_btn = text_button("重新载入文件", "Ghost", "restore")
        reload_btn.clicked.connect(self._reload_config)
        row.addWidget(open_btn)
        row.addWidget(reload_btn)
        row.addStretch(1)
        sec.add_layout(row)
        sec.add(label("主题、亮度、显示开关、物理参数、上次目录与窗口位置都在这里；"
                      "删掉文件即恢复默认。", "Faint", True))
        bl.addWidget(card)

        card, sec = self._card("界面")
        notes = [
            "字体：Microsoft YaHei UI（中文）+ Consolas（数值）",
            "名称显示：保留日文原名，并显示中文对照",
            "物理引擎：Bullet（开源，自编译 bullet_phys.dll）",
            "撤销上限：12 步，可撤销结构编辑与姿态",
        ]
        for n in notes:
            sec.add(label("· " + n, "Faint", True))
        bl.addWidget(card)

        card, sec = self._card("快捷键")
        keys = [("Ctrl+O", "打开模型"), ("Ctrl+S", "保存"), ("Ctrl+Shift+S", "另存为"),
                ("Ctrl+Z", "撤销"), ("Ctrl+Y", "重做"), ("F", "视图全部"),
                ("R", "重置姿态"), ("P", "物理演算开关"),
                ("双击", "选择骨骼/刚体/关节"),
                ("左键拖动骨骼", "位移（先选中）"),
                ("右键拖动骨骼", "旋转（先选中）"),
                ("中键拖动", "旋转视图"), ("Shift+中键拖动", "平移视图"),
                ("滚轮", "缩放")]
        form = Form(90)
        for k, v in keys:
            lb = label(k, "Accent")
            lb.setFont(mono_font(8.6))
            form.add(k, label(v, "Muted"))
        sec.add(form)
        bl.addWidget(card)
        bl.addStretch(1)
        self.root.addWidget(scroll, 1)

    def sync_config(self, cfg):
        self._config = cfg
        extra = "（%s）" % cfg.error if cfg.error else ""
        self.config_path.setText(str(cfg.path) + extra)

    def _open_config_dir(self):
        cfg = getattr(self, "_config", None)
        if cfg is None:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(cfg.path.parent)))

    def _reload_config(self):
        self.configReloaded.emit()

    def _brightness_row(self, sec, text, lo, hi, default):
        row = QHBoxLayout()
        lb = label(text, "Muted")
        lb.setFixedWidth(32)
        row.addWidget(lb)
        sl = QSlider(Qt.Horizontal)
        sl.setRange(lo, hi)
        sl.setValue(default)
        val = label("%d%%" % default, "Accent")
        val.setFixedWidth(44)
        val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(sl, 1)
        row.addWidget(val)
        sec.add_layout(row)
        return sl, val

    def _brightness(self):
        self.bg_value.setText("%d%%" % self.bg_slider.value())
        self.model_value.setText("%d%%" % self.model_slider.value())
        if self.loading:
            return
        self.brightnessChanged.emit(self.bg_slider.value() / 100.0,
                                    self.model_slider.value() / 100.0)

    def _reset_brightness(self):
        self.bg_slider.setValue(100)
        self.model_slider.setValue(100)

    def sync_brightness(self, bg: float, model: float):
        self.loading = True
        try:
            self.bg_slider.setValue(int(round(bg * 100)))
            self.model_slider.setValue(int(round(model * 100)))
        finally:
            self.loading = False
        self.bg_value.setText("%d%%" % self.bg_slider.value())
        self.model_value.setText("%d%%" % self.model_slider.value())

    def _opacity(self):
        self.bone_opacity_value.setText("%d%%" % self.bone_opacity.value())
        self.rigid_opacity_value.setText("%d%%" % self.rigid_opacity.value())
        self.joint_opacity_value.setText("%d%%" % self.joint_opacity.value())
        if self.loading:
            return
        self.displayChanged.emit({
            "bone_opacity": self.bone_opacity.value() / 100.0,
            "rigid_opacity": self.rigid_opacity.value() / 100.0,
            "joint_opacity": self.joint_opacity.value() / 100.0,
        })

    def _display(self, key: str, on: bool):
        if self.loading:
            return
        self.displayChanged.emit({key: on})

    def _apply_physics(self):
        self.physicsApply.emit({
            "gravity": float(self.gravity.value()),
            "iterations": int(self.iterations.value()),
            "ground": bool(self.ground.isChecked()),
        })

    def sync_display(self, viewport):
        self.loading = True
        try:
            for key, sw in self.display_switches.items():
                sw.setChecked(bool(getattr(viewport, key, False)))
            for key, slider, value in (
                    ("bone_opacity", self.bone_opacity, self.bone_opacity_value),
                    ("rigid_opacity", self.rigid_opacity, self.rigid_opacity_value),
                    ("joint_opacity", self.joint_opacity, self.joint_opacity_value)):
                pct = int(round(float(getattr(viewport, key, 0.0)) * 100))
                slider.setValue(pct)
                value.setText("%d%%" % pct)
        finally:
            self.loading = False
