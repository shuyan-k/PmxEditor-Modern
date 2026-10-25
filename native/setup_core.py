# -*- coding: utf-8 -*-
"""构建 pybind11 原生计算后端。

用法（仓库根目录）：
    build\\python\\python.exe native\\setup_core.py build_ext --inplace
产物 _pmx_core.cp312-win_amd64.pyd 落在 src/pmxeditor/ 下。
"""
from pathlib import Path

import pybind11
from setuptools import Extension, setup

NATIVE = Path(__file__).resolve().parent
REPO = NATIVE.parent
PKG = REPO / "src" / "pmxeditor"

setup(
    name="pmxeditor-native-core",
    version="0.1.0",
    packages=["pmxeditor"],
    package_dir={"pmxeditor": str(PKG)},
    ext_modules=[
        Extension(
            "pmxeditor._pmx_core",
            sources=[str(NATIVE / "pmx_core.cpp")],
            include_dirs=[pybind11.get_include()],
            library_dirs=[str(NATIVE), str(NATIVE / "obj")],
            libraries=["bullet_phys"],
            language="c++",
            extra_compile_args=["/O2", "/EHsc", "/std:c++17", "/utf-8"],
            extra_link_args=["/OPT:REF", "/OPT:ICF"],
        )
    ],
)