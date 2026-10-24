# -*- coding: utf-8 -*-
"""右侧检查器：模型信息、骨骼、表示枠、材质、形态、物理与显示设置。

按页面拆成子模块，公共基类与工具在 base.py；对外仍暴露
PANEL_NAMES / PageBase / InfoPage / BonePage / FramePage / MaterialPage /
MorphPage / PhysicsPage / SettingsPage。
"""
from .base import PANEL_NAMES, PageBase
from .info import InfoPage
from .bone import BonePage
from .frame import FramePage
from .vertex import VertexPage
from .material import MaterialPage
from .morph import MorphPage
from .physics import PhysicsPage
from .settings import SettingsPage

__all__ = ["PANEL_NAMES", "PageBase", "InfoPage", "BonePage", "FramePage", "VertexPage",
           "MaterialPage", "MorphPage", "PhysicsPage", "SettingsPage"]
