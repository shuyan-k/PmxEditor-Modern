# -*- coding: utf-8 -*-
"""3D 视口子包：相机、着色器、几何工具、HUD 与 Viewport。

对外仍暴露 Viewport / OrbitCamera 与全部颜色常量（主题切换时
theme.sync_modules() 会按名字覆盖这里的常量）。
"""
from ..theme import (ACCENT, BONE_RGB, GRID_MAJOR_RGB, GRID_MINOR_RGB,
                     GRID_X_RGB, GRID_Z_RGB, GROUP_COLORS, RIGID_STATIC_RGB,
                     TEX_MISS_BG, TEX_MISS_CELL, TEXT, TEXT_DIM, TEXT_FAINT,
                     VIEW_BG_RGB)
from .camera import OrbitCamera
from .core import Viewport

# 颜色常量是刻意的重导出：theme.sync_modules() 按名字覆盖这里的属性。
__all__ = [
    "Viewport", "OrbitCamera",
    "ACCENT", "BONE_RGB", "GRID_MAJOR_RGB", "GRID_MINOR_RGB", "GRID_X_RGB",
    "GRID_Z_RGB", "GROUP_COLORS", "RIGID_STATIC_RGB", "TEX_MISS_BG",
    "TEX_MISS_CELL", "TEXT", "TEXT_DIM", "TEXT_FAINT", "VIEW_BG_RGB",
]
