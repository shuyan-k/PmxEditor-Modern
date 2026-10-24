# -*- coding: utf-8 -*-
"""加载可选的 pybind11 计算后端，并提供明确的回退状态。"""
from __future__ import annotations

import os

from . import paths


_native_dir = paths.NATIVE
_dll_directory = None
if _native_dir.is_dir() and hasattr(os, "add_dll_directory"):
    _dll_directory = os.add_dll_directory(str(_native_dir))

try:
    from . import _pmx_core as core
except ImportError as exc:
    core = None
    load_error = exc
else:
    load_error = None


def is_available() -> bool:
    return core is not None


def backend_label() -> str:
    return "C++ / Bullet" if is_available() else "NumPy 回退 · 需构建 C++ 后端"


def unavailable_reason() -> str:
    return str(load_error) if load_error is not None else ""
