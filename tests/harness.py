# -*- coding: utf-8 -*-
"""自动化点击测试驱动：真实 QTest 点击 + 截图 + 异常/状态记录。"""
import os, sys, json, time, traceback, hashlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.chdir(ROOT)

from pmxeditor import native_backend  # noqa: F401  必须在 Qt 之前

from PyQt5.QtCore import Qt, QPoint, QTimer, QEvent, QRect
from PyQt5.QtGui import QColor, QFontMetrics, QGuiApplication
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import (QApplication, QWidget, QAbstractButton, QPushButton,
                             QLineEdit, QComboBox, QCheckBox, QAbstractItemView,
                             QMenu, QMessageBox, QFileDialog, QColorDialog,
                             QDialog, QSpinBox, QDoubleSpinBox, QSlider,
                             QAbstractSpinBox, QLabel)

from pmxeditor import app as appmod
from pmxeditor import theme

LOG = []
ANOM = []
STATE = {"step": "boot"}


def log(*a):
    s = " ".join(str(x) for x in a)
    LOG.append("[%s] %s" % (STATE["step"], s))
    print(s)
    sys.stdout.flush()


def anomaly(kind, detail):
    ANOM.append({"step": STATE["step"], "kind": kind, "detail": detail})
    print("!! ANOMALY [%s] %s: %s" % (STATE["step"], kind, detail))
    sys.stdout.flush()


def dump(path=None):
    path = path or os.path.join(ROOT, "tests", "report.json")
    with open(path, "w", encoding="utf8") as f:
        json.dump({"log": LOG, "anomalies": ANOM}, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- 拦截对话框
DIALOGS = []


def _rec(kind, w, extra=""):
    rec = {"kind": kind, "window": getattr(w, "windowTitle", lambda: "")() if w is not None else "",
           "text": "", "extra": extra}
    for attr in ("text", "informativeText", "message"):
        f = getattr(w, attr, None)
        if callable(f):
            try:
                v = f()
                if v:
                    rec[attr] = v
            except Exception:
                pass
    DIALOGS.append(rec)
    log("DIALOG(%s) %s" % (kind, json.dumps(rec, ensure_ascii=False)))
    return rec


MENUS = []


def _menu_exec(menu, *a, **k):
    try:
        items = [{"text": x.text(), "enabled": x.isEnabled(), "check": x.isCheckable()}
                 for x in menu.actions() if not x.isSeparator()]
        MENUS.append({"title": menu.title(), "items": items})
    except Exception:
        pass
    try:
        menu.close()
    except Exception:
        pass
    return None


def patch_dialogs(open_path=None, save_path=None):
    QFileDialog.getOpenFileName = staticmethod(
        lambda *a, **k: (_rec("getOpenFileName", a[0] if a else None, str(a[1:])), (open_path or "", ""))[1])
    QFileDialog.getSaveFileName = staticmethod(
        lambda *a, **k: (_rec("getSaveFileName", a[0] if a else None, str(a[1:])), (save_path or "", ""))[1])
    QColorDialog.getColor = staticmethod(
        lambda *a, **k: (_rec("getColor", a[0] if a else None), QColor("#4080ff"))[1])
    QMessageBox.critical = staticmethod(lambda *a, **k: (_rec("critical", a[0] if a else None, str(a[2:3])), QMessageBox.Ok)[1])
    QMessageBox.warning = staticmethod(lambda *a, **k: (_rec("warning", a[0] if a else None, str(a[2:3])), QMessageBox.Ok)[1])
    QMessageBox.information = staticmethod(lambda *a, **k: (_rec("information", a[0] if a else None, str(a[2:3])), QMessageBox.Ok)[1])
    QMessageBox.about = staticmethod(lambda *a, **k: (_rec("about", a[0] if a else None, str(a[2:3])), None)[1])
    try:
        from pmxeditor import ui_widgets
        _orig_exec = ui_widgets.ConfirmDialog.exec_

        def _exec(self):
            rec = _rec("ConfirmDialog", self, "")
            for attr in ("message", "_message"):
                v = getattr(self, attr, None)
                if isinstance(v, str):
                    rec["msg"] = v
            for lb in self.findChildren(QLabel):
                if lb.text():
                    rec.setdefault("labels", []).append(lb.text())
            return QDialog.Accepted
        ui_widgets.ConfirmDialog.exec_ = _exec
    except Exception as e:
        log("patch ConfirmDialog failed", e)


def _auto_modal():
    """兜底：自动关闭任何真正弹出的模态对话框。"""
    w = QApplication.activeModalWidget()
    if w is None:
        return
    _rec("modal:" + type(w).__name__, w)
    try:
        w.reject()
    except Exception:
        try:
            w.close()
        except Exception:
            pass


# ---------------------------------------------------------------- 工具

def desc(w):
    if w is None:
        return "<None>"
    cls = type(w).__name__
    obj = w.objectName()
    bits = [cls]
    if obj:
        bits.append("#" + obj)
    for attr, tag in (("text", "text"), ("placeholderText", "ph"), ("toolTip", "tip")):
        f = getattr(w, attr, None)
        if callable(f):
            try:
                v = f()
            except Exception:
                v = ""
            if v:
                bits.append(tag + "=" + str(v).replace("\n", "\\n")[:60])
    if isinstance(w, QComboBox):
        bits.append("items=[%s]" % ",".join(w.itemText(i) for i in range(w.count())))
        bits.append("cur=" + str(w.currentIndex()))
    return " ".join(bits)


def items(view):
    m = view.model()
    if m is None:
        return []
    out = []
    for r in range(m.rowCount()):
        idx = m.index(r, 0)
        out.append(m.data(idx))
    return out


def shot(win, name):
    p = os.path.join(ROOT, "tests", "shots", name + ".png")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    win.grab().save(p)
    return p


def sig(win):
    img = win.grab().toImage()
    b = img.bits()
    b.setsize(img.byteCount())
    return hashlib.md5(bytes(b)).hexdigest()


def pixdiff(win, before_bytes):
    img = win.grab().toImage()
    b = img.bits()
    b.setsize(img.byteCount())
    a = before_bytes
    c = bytes(b)
    n = min(len(a), len(c))
    if n == 0:
        return 0
    step = 4 * 7
    d = 0
    tot = 0
    for i in range(0, n, step):
        tot += 1
        if a[i] != c[i]:
            d += 1
    return round(100.0 * d / max(tot, 1), 2)


def raw(win):
    img = win.grab().toImage()
    b = img.bits()
    b.setsize(img.byteCount())
    return bytes(b)


def pump(ms=40):
    QTest.qWait(ms)


def ensure_visible(w):
    from PyQt5.QtWidgets import QScrollArea
    p = w.parentWidget()
    while p is not None:
        if isinstance(p, QScrollArea):
            p.ensureWidgetVisible(w, 24, 24)
            QTest.qWait(30)
            return
        p = p.parentWidget()


def hit_test(gp):
    """屏幕坐标命中测试。

    优先 QApplication.widgetAt；某些进程里窗口没被登记到桌面（widgetAt
    恒返回 None，例如便携运行时下的无边框窗口），此时回退到主窗口自己的
    childAt(mapFromGlobal(...))，两者语义一致且不依赖窗口系统。
    """
    hit = QApplication.widgetAt(gp)
    if hit is not None:
        return hit
    win = APP_WIN
    if win is None:
        return None
    local = win.mapFromGlobal(gp)
    if not win.rect().contains(local):
        return None
    return win.childAt(local)


def click(w, dbl=False, button=Qt.LeftButton, pos=None, label=None):
    """真实点击（经窗口命中测试），返回像素变化百分比。"""
    if w is None:
        anomaly("click-none", "目标控件不存在")
        return None
    if not w.isVisible():
        log("SKIP (不可见)", desc(w))
        return None
    if not w.isEnabled():
        anomaly("click-disabled", "%s 处于禁用状态" % desc(w))
        return None
    ensure_visible(w)
    p = pos or w.rect().center()
    gp = w.mapToGlobal(p)
    hit = hit_test(gp)
    if hit is None:
        anomaly("click-outside", "%s 中心 %s 处没有控件（可能被滚动区裁掉，控件矩形 %s）"
                % (desc(w), gp, w.rect().getRect()))
        return None
    if hit is not w and not w.isAncestorOf(hit):
        anomaly("click-intercept", "%s 的中心点被 %s 覆盖" % (desc(w), desc(hit)))
        w = hit
        p = w.mapFromGlobal(gp)
    before = raw(APP_WIN)
    if dbl:
        QTest.mouseDClick(w, button, Qt.NoModifier, p)
    else:
        QTest.mouseClick(w, button, Qt.NoModifier, p)
    pump(90)
    d = pixdiff(APP_WIN, before)
    log("CLICK%s %s%s -> pix %.2f%% | status: %s"
        % ("x2" if dbl else "", desc(w), ("" if not label else " [" + label + "]"), d,
           STATUS.text))
    return d


def rclick(w, pos=None):
    p = pos or w.rect().center()
    before = raw(APP_WIN)
    QTest.mouseClick(w, Qt.RightButton, Qt.NoModifier, p)
    pump(90)
    d = pixdiff(APP_WIN, before)
    log("RCLICK %s → 变化 %.2f%% | 状态: %s" % (desc(w), d, STATUS.text))
    return d


def patch_menus():
    from PyQt5.QtWidgets import QMenu
    QMenu.exec_ = _menu_exec
    QMenu.exec = _menu_exec
    H_MENUS = MENUS
