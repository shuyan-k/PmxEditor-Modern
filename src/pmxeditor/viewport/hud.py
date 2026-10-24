"""视口左上角 HUD 覆盖层。"""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QWidget


# ---------------------------------------------------------------- HUD 层

class _HudOverlay(QWidget):
    """视口文字层。

    独立子控件用 raster 引擎绘制，避免 QOpenGLWidget 的 GL 画家在混合
    GL 状态时出现汉字缺笔、字距错位等问题。
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.NoFocus)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        self.parentWidget()._paint_hud(p)
        p.end()
