# -*- coding: utf-8 -*-
"""项目路径锚点：资源、原生库与包目录位置集中在此。

同时适配两种布局：
- 源码运行：``<repo>/src/pmxeditor/`` -> ROOT = ``<repo>``
- Nuitka 打包：``<dist>/pmxeditor/``   -> ROOT = ``<dist>``（assets/native 与包同级）
"""
from __future__ import annotations

from pathlib import Path

PKG = Path(__file__).resolve().parent
SRC = PKG.parent
ROOT = SRC.parent


def _locate(name: str) -> Path:
    """优先返回已存在的资源目录，兼顾源码树与打包目录。"""
    for base in (ROOT, SRC, PKG):
        cand = base / name
        if cand.is_dir():
            return cand
    return ROOT / name


ASSETS = _locate("assets")
NATIVE = _locate("native")
