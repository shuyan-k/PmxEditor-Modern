# -*- coding: utf-8 -*-
"""新版（PmxEditor_Modern, PyQt5）的测试驱动封装：复用 tests/run.py 的 boot + 真实控件点击。"""
import os, sys, json, time

ROOT = r"D:\Project\PmxEditor_Modern"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

import run as R            # noqa: E402
from harness import log, anomaly, pump, click, desc, items  # noqa: E402
from PyQt5.QtWidgets import (QAbstractButton, QLineEdit, QComboBox, QLabel,
                             QSpinBox, QDoubleSpinBox, QListWidget,
                             QTableWidget, QAbstractItemView)  # noqa: E402
from PyQt5.QtCore import Qt  # noqa: E402

WIN = None
PAGE_NAMES = ["信息", "骨骼", "材质", "形态", "物理", "显示设置", "表示枠", "顶点"]


def boot(model=None, theme="dark", size=(1560, 1000)):
    global WIN
    R.H.patch_dialogs(open_path=model)
    R.H.patch_menus()
    WIN = R.boot(theme, model)
    R.install_hooks()
    WIN.resize(*size)
    pump(300)
    WIN.activateWindow()
    return WIN


def page(i):
    WIN._select_page(i)
    pump(250)
    return WIN._pages[i]


def save_to(path):
    R.H.patch_dialogs(save_path=path)
    WIN.save_as()
    pump(400)
    return os.path.exists(path)


def shot(name):
    return R.H.shot(WIN, "parity_" + name)


def walk(w):
    return R.walk(w)


def btn(root, text, exact=True):
    for w in walk(root):
        if isinstance(w, QAbstractButton) and w.isVisible():
            t = w.text().replace("&", "")
            if (t == text) if exact else (text in t):
                return w
    return None


def lbl(root, text, fuzzy=True):
    for w in walk(root):
        if isinstance(w, QLabel) and w.isVisible() and text in w.text():
            return w
    return None


def edit_near(root, label_text):
    """返回与某标签同一行（垂直中心最近）的 QLineEdit。"""
    lb = lbl(root, label_text)
    if lb is None:
        return None
    y = lb.mapToGlobal(lb.rect().center()).y()
    best, bd = None, 1e9
    for w in walk(root):
        if isinstance(w, QLineEdit) and w.isVisible():
            wy = w.mapToGlobal(w.rect().center()).y()
            d = abs(wy - y)
            if d < bd:
                best, bd = w, d
    return best if bd < 30 else None


def spin_near(root, label_text):
    lb = lbl(root, label_text)
    if lb is None:
        return []
    y = lb.mapToGlobal(lb.rect().center()).y()
    out = []
    for w in walk(root):
        if isinstance(w, (QSpinBox, QDoubleSpinBox)) and w.isVisible():
            if abs(w.mapToGlobal(w.rect().center()).y() - y) < 30:
                out.append(w)
    return out


def set_spin(sb, val, commit=True):
    sb.setFocus()
    pump(20)
    sb.selectAll() if hasattr(sb, "selectAll") else None
    sb.lineEdit().selectAll()
    sb.lineEdit().clear()
    from PyQt5.QtTest import QTest
    QTest.keyClicks(sb.lineEdit(), str(val))
    pump(30)
    if commit:
        QTest.keyClick(sb.lineEdit(), Qt.Key_Return)
    pump(80)


def lists_of(root):
    return [w for w in walk(root) if isinstance(w, (QListWidget, QTableWidget)) and w.isVisible()]
