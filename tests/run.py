# -*- coding: utf-8 -*-
"""驱动主程序：创建窗口、执行测试场景。"""
import os, sys, json, time, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness as H
from harness import log, anomaly, desc, click, pump, shot, STATE

from PyQt5.QtCore import Qt, QPoint, QPointF, QTimer, QRect, QEvent
from PyQt5.QtGui import QColor, QFontMetrics, QMouseEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import (QApplication, QWidget, QAbstractButton, QPushButton,
                             QLineEdit, QComboBox, QCheckBox, QAbstractItemView,
                             QMenu, QMessageBox, QDialog, QLabel, QSplitter,
                             QSpinBox, QDoubleSpinBox, QSlider, QAbstractSpinBox,
                             QStackedWidget, QGroupBox)
from PyQt5.QtGui import QWheelEvent

from pmxeditor import app as appmod
from pmxeditor import theme

APP = None
WIN = None


class Status:
    def __init__(self):
        self.hist = []

    @property
    def text(self):
        try:
            return WIN.status_label.text()
        except Exception:
            return ""

    def note(self):
        t = self.text
        if not self.hist or self.hist[-1] != t:
            self.hist.append(t)
        return t


H.STATUS = STATUS = Status()


class NotifyApp(QApplication):
    """捕获槽函数内异常并记录完整堆栈（PyQt5 默认会 abort 或吞掉）。"""
    def notify(self, recv, ev):
        try:
            return QApplication.notify(self, recv, ev)
        except BaseException:
            H.anomaly("notify-exc", "recv=%r ev=%r\n%s" % (recv, ev, traceback.format_exc()))
            return False


def boot(theme_name="dark", model=None):
    global APP, WIN
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    APP = NotifyApp(sys.argv[:1])
    APP.setApplicationName("PMX 编辑器")
    APP.setStyle("Fusion")
    theme.apply_theme("dark")
    theme.sync_modules()
    theme.svg_assets()
    from pmxeditor.theme import build_qss, ui_font
    APP.setStyleSheet(build_qss())
    APP.setFont(ui_font(9.0))
    WIN = appmod.MainWindow()
    H.APP_WIN = WIN
    WIN.resize(1560, 920)
    WIN.show()
    pump(600)
    if theme_name == "light":
        WIN._set_theme("light", announce=False)
        pump(300)
    if model:
        WIN.open_path(model)
        pump(500)

    # 记录状态栏变化
    try:
        WIN.doc.status.connect(lambda s: STATUS.hist.append(s))
    except Exception:
        pass
    return WIN


# ---------------------------------------------------------------- 异常捕获
def install_hooks():
    def excepthook(t, v, tb):
        txt = "".join(traceback.format_exception(t, v, tb))
        anomaly("exception", txt)
    sys.excepthook = excepthook

    def handler(mode, ctx, msg):
        low = msg.lower()
        interesting = any(k in low for k in (
            "qpainter", "qlayout", "opengl", "shader", "attribute", "buffer",
            "invalid", "error", "context", "premature", "segmentation"))
        if interesting:
            anomaly("qt-warning", msg.strip()[:400])
        else:
            log("qt:", msg.strip()[:200])
    from PyQt5.QtCore import qInstallMessageHandler
    qInstallMessageHandler(handler)
    timer = QTimer()
    timer.timeout.connect(H._auto_modal)
    timer.start(120)
    timer.moveToThread(APP.thread())


# ---------------------------------------------------------------- 控件清单
INTERACTIVE = (QAbstractButton, QComboBox, QAbstractSpinBox, QLineEdit,
               QAbstractItemView, QSlider)


def walk(w, out=None):
    out = [] if out is None else out
    out.append(w)
    for c in w.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
        walk(c, out)
    return out


def leaves(w):
    return [x for x in walk(w) if not x.findChildren(QWidget, options=Qt.FindDirectChildrenOnly)]


def clipped(w):
    """文本是否被裁切。"""
    t = ""
    for attr in ("text", "currentText"):
        f = getattr(w, attr, None)
        if callable(f):
            try:
                v = f()
                if v:
                    t = v
                    break
            except Exception:
                pass
    if not t:
        return ""
    fm = w.fontMetrics()
    avail = w.contentsRect().width()
    ic = 0
    try:
        if w.icon() is not None and not w.icon().isNull():
            ic = w.iconSize().width() + 6
    except Exception:
        pass
    need = fm.horizontalAdvance(t) + ic
    if need > avail + 1:
        return "%s (需要 %dpx / 可用 %dpx)" % (t, need, avail)
    return ""


def overlaps(parent):
    kids = [k for k in parent.findChildren(QWidget, options=Qt.FindDirectChildrenOnly)
            if k.isVisible()]
    bad = []
    for i in range(len(kids)):
        for j in range(i + 1, len(kids)):
            a, b = kids[i], kids[j]
            if a.geometry().intersects(b.geometry()):
                bad.append((desc(a), desc(b), a.geometry().getRect(), b.geometry().getRect()))
    return bad


def inventory(tag=""):
    STATE["step"] = "inventory" + tag
    pages = WIN._pages
    for pi, page in enumerate(pages):
        log("=== 页面 %d %s  (小部件 %d)" % (pi, type(page).__name__, len(walk(page))))
        for w in walk(page):
            if isinstance(w, INTERACTIVE) or w.objectName() in ("Faint", "TitleSmall"):
                log("  %-14s %-58s vis=%d en=%d geo=%s" %
                    (type(w).__name__, desc(w)[:58], w.isVisible(), w.isEnabled(),
                     w.geometry().getRect()))
                c = clipped(w)
                if c:
                    anomaly("text-clipped", "%s: %s" % (desc(w), c))
        for a, b, ga, gb in overlaps(page):
            anomaly("overlap", "%s %s / %s %s" % (a, ga, b, gb))
    # 工具栏/标题栏/状态栏
    for holder, name in ((WIN.titlebar, "TitleBar"), (WIN.menubar, "MenuBar"),
                         (WIN.centralWidget(), "Central")):
        for w in walk(holder):
            if isinstance(w, INTERACTIVE):
                log("%s %-10s %s" % (name, type(w).__name__, desc(w)[:70]))
    log("页面切换按钮:", [b.toolTip() for b in WIN.rail_buttons])
    log("菜单:", [a.text() for a in WIN.menubar.actions()])
    log("物理开关:", WIN.physics_switch.isChecked(), "enabled=", WIN.viewport.physics.enabled)
    log("状态栏:", WIN.status_label.text(), "|", WIN.sel_label.text(), "|", WIN.phys_label.text())
    log("窗口几何:", WIN.geometry().getRect(), "DPR:", WIN.devicePixelRatioF())
    log("splitter:", WIN.splitter.sizes())
    log("viewport:", WIN.viewport.width(), WIN.viewport.height(), "physics=", WIN.viewport.physics.enabled,
        "fps=", getattr(WIN.viewport, "fps", "?"))

# ---------------------------------------------------------------- 场景：清单
def scen_inventory():
    inventory()
    for i in range(6):
        WIN._select_page(i)
        pump(250)
        STATUS.note()
        shot(WIN, "page%d" % i)
        log("切到页面 %d 后状态:" % i, STATUS.text)


# ---------------------------------------------------------------- 场景：逐控件点击
from PyQt5.QtWidgets import (QStyle, QStyleOptionSpinBox, QStyleOptionComboBox,
                             QAbstractScrollArea)

DESTRUCTIVE = ("删除", "移除")


def is_destructive(w):
    tip = ""
    try:
        tip = w.toolTip() or w.text()
    except Exception:
        pass
    return any(k in tip for k in DESTRUCTIVE)


def snapshot():
    d = WIN.doc
    return {"dirty": d.dirty, "undo": len(d._undo), "redo": len(d._redo),
            "sel": (d.sel_kind, d.sel_index),
            "n": (len(d.model.bones), len(d.model.materials), len(d.model.morphs),
                  len(d.model.rigid), len(d.model.joints)) if d.model else None}


def delta(a, b):
    out = []
    if a["dirty"] != b["dirty"]:
        out.append("dirty %s→%s" % (a["dirty"], b["dirty"]))
    if a["undo"] != b["undo"]:
        out.append("undo %d→%d" % (a["undo"], b["undo"]))
    if a["redo"] != b["redo"]:
        out.append("redo %d→%d" % (a["redo"], b["redo"]))
    if a["sel"] != b["sel"]:
        out.append("sel %s→%s" % (a["sel"], b["sel"]))
    if a["n"] != b["n"]:
        out.append("数量 %s→%s" % (a["n"], b["n"]))
    return out


def click_and_report(w, label=""):
    before = snapshot()
    st0 = STATUS.text
    d = click(w, label=label)
    after = snapshot()
    ch = delta(before, after)
    log("   → 状态: %r 变化: %s" % (STATUS.text, ch if ch else "无"))
    if d is not None and d < 0.02 and STATUS.text == st0 and not ch:
        anomaly("no-effect-click", "%s 点击后无像素/状态/数据变化" % desc(w)[:120])
    return d, ch


def combo_all(cb):
    """展开下拉，逐项点击。"""
    log("COMBO", desc(cb)[:80])
    cb.showPopup()
    pump(120)
    view = cb.view()
    n = cb.count()
    for i in range(n):
        idx = cb.model().index(i, 0)
        r = view.visualRect(idx)
        if not r.isValid() or r.isEmpty():
            view.scrollTo(idx, view.ScrollHint.PositionAtCenter)
            pump(60)
            r = view.visualRect(idx)
        before = snapshot()
        st0 = STATUS.text
        QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.NoModifier, r.center())
        pump(120)
        log("   item %d %r → cur=%d 状态: %r 变化: %s"
            % (i, cb.itemText(i), cb.currentIndex(), STATUS.text, delta(before, snapshot()) or "无"))
        cb.showPopup()
        pump(80)
    cb.hidePopup()
    pump(80)


def spin_click(sb):
    """点击上下箭头。"""
    opt = QStyleOptionSpinBox()
    opt.initFrom(sb)
    opt.subControls = QStyle.SC_All
    st = sb.style()
    for sc, nm in ((QStyle.SC_SpinBoxUp, "上"), (QStyle.SC_SpinBoxDown, "下")):
        r = st.subControlRect(QStyle.CC_SpinBox, opt, sc, sb)
        if not r.isValid():
            continue
        before = snapshot()
        QTest.mouseClick(sb, Qt.LeftButton, Qt.NoModifier, r.center())
        pump(110)
        log("   箭头%s %s → %r 变化: %s" % (nm, desc(sb)[:40], sb.value(),
                                       delta(before, snapshot()) or "无"))


def type_edit(le, text="Abc123"):
    click(le)
    pump(60)
    le.selectAll()
    QTest.keyClicks(le, text)
    QTest.keyClick(le, Qt.Key_Return)
    pump(140)
    log("   输入 %r → text=%r 状态: %r" % (text, le.text(), STATUS.text))


def test_view_rows(view, limit=99):
    m = view.model()
    if m is None or m.rowCount() == 0:
        log("   （空列表）", desc(view))
        return
    log("   列表 %s 行数=%d 内容=%s" % (desc(view)[:40], m.rowCount(),
                                      [m.data(m.index(r, 0)) for r in range(min(m.rowCount(), 12))]))
    for r in range(min(m.rowCount(), limit)):
        idx = m.index(r, 0)
        view.scrollTo(idx, view.ScrollHint.PositionAtCenter)
        pump(30)
        rect = view.visualRect(idx)
        if rect.isEmpty():
            anomaly("row-not-visible", "%s 第 %d 行 visualRect 为空" % (desc(view)[:50], r))
            continue
        before = snapshot()
        st0 = STATUS.text
        QTest.mouseClick(view.viewport(), Qt.LeftButton, Qt.NoModifier, rect.center())
        pump(100)
        log("   行 %d %r → 状态: %r 变化: %s"
            % (r, m.data(idx), STATUS.text, delta(before, snapshot()) or "无"))
        if STATUS.text == st0 and not delta(before, snapshot()):
            pass


def scen_clickall():
    model = sys.argv[3] if len(sys.argv) > 3 else None
    for pi in range(6):
        STATE["step"] = "page%d" % pi
        WIN._select_page(pi)
        pump(400)
        page = WIN._pages[pi]
        shot(WIN, "before_page%d" % pi)
        log("### 页面 %d %s" % (pi, type(page).__name__))
        ws = [w for w in walk(page) if isinstance(w, INTERACTIVE) and w.isVisible()]
        log("可见交互控件 %d 个" % len(ws))
        for w in ws:
            if w.objectName() == "qt_spinbox_lineedit":
                continue
            if is_destructive(w):
                log("跳过破坏性控件（稍后单独测试）", desc(w))
                continue
            if isinstance(w, QComboBox):
                combo_all(w)
                continue
            if isinstance(w, QAbstractSpinBox):
                click_and_report(w)
                spin_click(w)
                continue
            if isinstance(w, QLineEdit):
                click_and_report(w)
                type_edit(w)
                continue
            if isinstance(w, QAbstractItemView):
                test_view_rows(w)
                continue
            click_and_report(w)
            if isinstance(w, QCheckBox):
                click(w)
        shot(WIN, "after_page%d" % pi)
    # 破坏性按钮
    STATE["step"] = "destructive"
    for pi in range(6):
        WIN._select_page(pi)
        pump(250)
        page = WIN._pages[pi]
        for w in walk(page):
            if isinstance(w, INTERACTIVE) and w.isVisible() and is_destructive(w):
                log("### 破坏性点击", desc(w))
                click_and_report(w)
    H.dump()


def main_start():
    mode = sys.argv[1] if len(sys.argv) > 1 else "inventory"
    th = sys.argv[2] if len(sys.argv) > 2 else "dark"
    model = sys.argv[3] if len(sys.argv) > 3 else None
    H.patch_dialogs(open_path=model, save_path=os.path.join(H.ROOT, "tests", "out.pmx"))
    H.patch_menus()
    boot(th, model)
    if not mode.startswith("nohook_"):
        install_hooks()
    log("APP STARTED", mode, th, model)
    try:
        globals()["scen_" + mode]()
    except Exception:
        anomaly("scenario-crash", traceback.format_exc())
    H.dump()
    log("DONE anomalies:", len(H.ANOM))
    try:
        WIN.viewport.physics.release()
    except Exception:
        pass
    os._exit(0)

def scen_combo():
    WIN._select_page(1)
    pump(300)
    page = WIN._pages[1]
    from PyQt5.QtWidgets import QComboBox
    cbs = [w for w in walk(page) if isinstance(w, QComboBox) and w.isVisible()]
    log("combos", [desc(c) for c in cbs])
    cb = cbs[0]
    log("current", cb.currentIndex(), cb.currentText())
    cb.showPopup()
    pump(200)
    v = cb.view()
    log("view", type(v).__name__, v.isVisible(), v.geometry().getRect(), "rows", v.model().rowCount(),
        "same model", v.model() is cb.model())
    for i in range(min(5, v.model().rowCount())):
        idx = v.model().index(i, 0)
        r = v.visualRect(idx)
        log("  row", i, v.model().data(idx), r.getRect())
    idx = v.model().index(3, 0)
    r = v.visualRect(idx)
    QTest.mouseClick(v.viewport(), Qt.LeftButton, Qt.NoModifier, r.center())
    pump(200)
    log("after click row3: cur", cb.currentIndex(), cb.currentText(), "popupvisible", v.isVisible(),
        "status", STATUS.text)
    shot(WIN, "combo")


def scen_combo2():
    WIN._select_page(1)
    pump(300)
    page = WIN._pages[1]
    from PyQt5.QtWidgets import QComboBox
    cb = [w for w in walk(page) if isinstance(w, QComboBox) and w.isVisible()][0]
    log("dpr", WIN.devicePixelRatioF(), WIN.windowHandle().devicePixelRatio())
    cb.showPopup()
    pump(250)
    v = cb.view()
    idx = v.model().index(3, 0)
    r = v.visualRect(idx)
    gp = v.viewport().mapToGlobal(r.center())
    log("row3 center local", r.center().x(), r.center().y(), "global", gp.x(), gp.y())
    log("widgetAt(global)", desc(QApplication.widgetAt(gp)))
    log("viewport global rect", v.viewport().mapToGlobal(QPoint(0,0)).x(), v.viewport().mapToGlobal(QPoint(0,0)).y(),
        v.viewport().width(), v.viewport().height())
    log("popup window", type(v.window()).__name__, v.window().geometry().getRect())
    cb.hidePopup()
    pump(100)
    log("--- 试着用 mouseMove+mousePress 到 viewport 相对坐标")
    cb.showPopup()
    pump(200)
    QTest.mouseMove(v.viewport(), r.center())
    pump(80)
    QTest.mouseClick(v.viewport(), Qt.LeftButton, Qt.NoModifier, r.center())
    pump(250)
    log("cur", cb.currentIndex(), cb.currentText(), "status", STATUS.text)

# ---------------------------------------------------------------- 场景：结构化逐控件走查
from PyQt5.QtWidgets import QComboBox, QScrollBar

MODEL_PATH = None


def reload_model():
    WIN.doc.dirty = False
    WIN.doc._undo.clear()
    WIN.open_path(MODEL_PATH)
    pump(220)


def path_of(w, root):
    p = []
    x = w
    while x is not None and x is not root:
        par = x.parentWidget()
        if par is None:
            return None
        p.append(par.findChildren(QWidget, options=Qt.FindDirectChildrenOnly).index(x)
                 if x in par.findChildren(QWidget, options=Qt.FindDirectChildrenOnly) else -1)
        x = par
    return tuple(reversed(p))


def resolve(root, path):
    x = root
    for i in path:
        kids = x.findChildren(QWidget, options=Qt.FindDirectChildrenOnly)
        if i < 0 or i >= len(kids):
            return None
        x = kids[i]
    return x


def scen_walk():
    global MODEL_PATH
    MODEL_PATH = sys.argv[3]
    WIN._select_page(0)
    pump(300)
    for pi in range(6):
        STATE["step"] = "p%d" % pi
        reload_model()
        WIN._select_page(pi)
        pump(350)
        page = WIN._pages[pi]
        log("====== 页面 %d %s" % (pi, type(page).__name__))
        ws = [w for w in walk(page)
              if isinstance(w, INTERACTIVE) and w.isVisible() and w.isEnabled()]
        targets = [(desc(w), path_of(w, page)) for w in ws
                   if not isinstance(w, QScrollBar)]
        log("可见可用交互控件 %d 个" % len(targets))
        for label, path in targets:
            STATE["step"] = "p%d" % pi
            reload_model()
            WIN._select_page(pi)
            pump(180)
            w = resolve(page, path)
            if w is None:
                log("!! 控件在刷新后消失:", label)
                continue
            if not w.isVisible():
                log("!! 控件刷新后不可见:", label)
                continue
            log("--- %s" % label[:110])
            before = snapshot()
            st0 = STATUS.text
            try:
                if isinstance(w, QComboBox):
                    for i in range(min(w.count(), 6)):
                        if i == w.currentIndex():
                            continue
                        w.setCurrentIndex(i)
                        pump(120)
                        log("   选中 %d %r -> 状态 %r 变化 %s"
                            % (i, w.itemText(i), STATUS.text, delta(before, snapshot()) or "无"))
                        before = snapshot()
                elif isinstance(w, QAbstractSpinBox):
                    click_and_report(w)
                    spin_click(w)
                elif isinstance(w, QLineEdit):
                    click_and_report(w)
                    type_edit(w)
                elif isinstance(w, QAbstractItemView):
                    test_view_rows(w)
                else:
                    click_and_report(w)
                    if type(w).__name__ == "Switch":
                        click(w)
            except Exception:
                anomaly("widget-crash", "%s\n%s" % (label[:100], traceback.format_exc()))
            page = WIN._pages[pi]
        shot(WIN, "walk_p%d" % pi)
    H.dump()

# ---------------------------------------------------------------- 场景：核心功能
def repaint_probe(tag=""):
    before = len(H.ANOM)
    WIN.viewport.update()
    pump(160)
    n = len([a for a in H.ANOM if a["kind"] == "exception"])
    log("重绘后异常累计 %d %s" % (n, tag))
    return n


def scen_core():
    global MODEL_PATH
    MODEL_PATH = sys.argv[3]
    m = WIN.doc.model
    log("材质0 specular=%r ambient=%r diffuse=%r"
        % (m.materials[0].specular, m.materials[0].ambient, m.materials[0].diffuse))
    WIN._select_page(2)
    pump(300)
    page = WIN._pages[2]
    log("材质页 visible combos etc")
    n0 = repaint_probe("初始")
    # 1) 点击"高光色"颜色按钮
    log("--- 点击 高光色 ColorButton")
    click(page.specular)
    pump(200)
    log("材质0 specular 现在 = %r (长度 %d)" % (m.materials[0].specular, len(m.materials[0].specular)))
    n1 = repaint_probe("高光色之后")
    log("--- 点击 环境色 ColorButton")
    click(page.ambient)
    pump(200)
    log("材质0 ambient 现在 = %r (长度 %d)" % (m.materials[0].ambient, len(m.materials[0].ambient)))
    n2 = repaint_probe("环境色之后")
    shot(WIN, "core_color")
    # 2) 撤销能否恢复
    log("--- Ctrl+Z 撤销两次")
    QTest.keyClick(WIN, Qt.Key_Z, Qt.ControlModifier)
    pump(300)
    log("撤销后 specular=%r ambient=%r dirty=%s status=%r"
        % (m.materials[0].specular, m.materials[0].ambient, WIN.doc.dirty, STATUS.text))
    n3 = repaint_probe("撤销后")
    # 3) 骨骼树过滤无匹配
    WIN._select_page(1)
    pump(300)
    bp = WIN._pages[1]
    log("--- 骨骼树：清空搜索后行数")
    bp._search.setText("")
    pump(200)
    log("树行数 =", bp.tree.model().rowCount() if bp.tree.model() else None)
    log("--- 输入不存在的名字 'zzzz'")
    bp._search.setText("zzzz")
    pump(250)
    log("树行数 =", bp.tree.model().rowCount() if bp.tree.model() else None)
    shot(WIN, "core_tree_empty")
    log("--- 清空搜索")
    bp._search.setText("")
    pump(250)
    log("树行数 =", bp.tree.model().rowCount() if bp.tree.model() else None)
    # 4) 选中不同骨骼，检查详情刷新
    for i in (0, 2, 5, 3):
        bp.tree.select_bone(i)
        pump(150)
        log("选中 %d → name_edit=%r pos=%r parent=%r status=%r"
            % (i, bp.name_edit.text(), bp.pos_spin.value(), bp.parent_combo.currentText(), STATUS.text))
    # 5) 通过树双击
    idx = bp.tree.model().index(2, 0)
    r = bp.tree.visualRect(idx)
    log("--- 双击骨骼树第 3 行")
    QTest.mouseDClick(bp.tree.viewport(), Qt.LeftButton, Qt.NoModifier, r.center())
    pump(250)
    log("双击后 doc.sel=%s status=%r" % ((WIN.doc.sel_kind, WIN.doc.sel_index), STATUS.text))
    H.dump()


# ---------------------------------------------------------------- 场景：颜色按钮 / 撤销 / 骨骼树
def scen_core2():
    def mat():
        return WIN.doc.model.materials[0]
    WIN._select_page(2)
    pump(300)
    page = WIN._pages[2]
    log("初始 spec=%r amb=%r diff=%r" % (mat().specular, mat().ambient, mat().diffuse))
    log("异常数=%d" % len([a for a in H.ANOM if a["kind"] == "exception"]))
    log("--- 点击 高光色")
    click(page.specular)
    pump(250)
    log("点击后 spec=%r (len %d) 异常数=%d"
        % (mat().specular, len(mat().specular),
           len([a for a in H.ANOM if a["kind"] == "exception"])))
    log("undo栈=%d redo栈=%d" % (len(WIN.doc._undo), len(WIN.doc._redo)))
    log("--- 保存到 tests/bad.pmx")
    try:
        from pmxeditor import pmx as PMX
        PMX.save_pmx(WIN.doc.model, os.path.join(H.ROOT, "tests", "bad.pmx"))
        log("保存完成，大小=%d" % os.path.getsize(os.path.join(H.ROOT, "tests", "bad.pmx")))
        try:
            m2 = PMX.load_pmx(os.path.join(H.ROOT, "tests", "bad.pmx"))
            log("回读成功 材质数=%d spec=%r" % (len(m2.materials), m2.materials[0].specular))
        except Exception as e:
            anomaly("save-reload", "回读保存后的 PMX 失败: %r" % (e,))
    except Exception:
        anomaly("save", traceback.format_exc())
    log("--- Ctrl+Z")
    QTest.keyClick(WIN, Qt.Key_Z, Qt.ControlModifier)
    pump(250)
    log("撤销后 spec=%r amb=%r dirty=%s status=%r"
        % (mat().specular, mat().ambient, WIN.doc.dirty, STATUS.text))
    log("--- Ctrl+Y 重做")
    QTest.keyClick(WIN, Qt.Key_Y, Qt.ControlModifier)
    pump(250)
    log("重做后 spec=%r dirty=%s status=%r" % (mat().specular, WIN.doc.dirty, STATUS.text))
    # 骨骼树
    WIN._select_page(1)
    pump(300)
    bp = WIN._pages[1]
    def rows():
        mdl = bp.tree.model()
        return None if mdl is None else mdl.rowCount()
    log("--- 骨骼树行数(无过滤)=%s" % rows())
    bp.search.setText("zzzz")
    pump(250)
    log("过滤 zzzz 后行数=%s" % rows())
    shot(WIN, "core2_tree_filter")
    bp.search.setText("")
    pump(250)
    log("清空过滤后行数=%s" % rows())
    for i in (0, 2, 5, 3):
        try:
            bp.tree.select_bone(i)
        except Exception:
            bp.tree.setCurrentIndex(bp.tree.model().index(i, 0))
        pump(150)
        log("选中 %d → name=%r pos=%r parent=%r status=%r"
            % (i, bp.name_edit.text(), bp.pos_spin.value(),
               bp.parent_combo.currentText(), STATUS.text))
    idx = bp.tree.model().index(2, 0)
    r = bp.tree.visualRect(idx)
    log("--- 双击骨骼树第 3 行 (rect=%s)" % (r,))
    QTest.mouseDClick(bp.tree.viewport(), Qt.LeftButton, Qt.NoModifier, r.center())
    pump(250)
    log("双击后 sel=%s status=%r" % ((WIN.doc.sel_kind, WIN.doc.sel_index), STATUS.text))
    H.dump()


def scen_nohook_color():
    import sys as _s
    def mark(msg):
        _s.stderr.write("[MARK] %s\n" % msg)
        _s.stderr.flush()
    mark("booted")
    WIN._select_page(2)
    pump(300)
    mark("page2")
    click(WIN._pages[2].specular)
    mark("clicked color")
    pump(600)
    mark("survived")
    _s.stderr.flush()
    H.dump()


# ---------------------------------------------------------------- 场景：菜单 / 标题栏 / 主题
def scen_menu():
    mb = WIN.menubar
    acts = mb.actions()
    log("菜单栏 actions=%d" % len(acts))
    skip = ("退出", "关闭模型")
    for a in acts:
        name = a.text()
        log("=== 菜单 %r" % name)
        r = mb.actionGeometry(a)
        menu = a.menu()
        QTest.mouseClick(mb, Qt.LeftButton, Qt.NoModifier, r.center())
        pump(250)
        if not menu.isVisible():
            anomaly("menu", "点击菜单标题 %r 后未弹出" % name)
            continue
        shot(WIN, "menu_%s" % name)
        items = [x for x in menu.actions() if not x.isSeparator()]
        log("  可见=%s 项数=%d" % (menu.isVisible(), len(items)))
        for it in items:
            log("    项 %r enabled=%s checkable=%s checked=%s shortcut=%r"
                % (it.text(), it.isEnabled(), it.isCheckable(), it.isChecked(),
                   it.shortcut().toString()))
        logs = []
        for it in items:
            if it.text() in skip or not it.isEnabled():
                continue
            if not menu.isVisible():
                QTest.mouseClick(mb, Qt.LeftButton, Qt.NoModifier, r.center())
                pump(200)
            before = snapshot()
            geo = menu.actionGeometry(it)
            log("  → 点击 %r %s" % (it.text(), geo))
            QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier, geo.center())
            pump(320)
            log("     %s | status=%r" % (delta(before, snapshot()), STATUS.text))
            if menu.isVisible():
                menu.close()
                pump(120)
        if menu.isVisible():
            menu.close()
            pump(120)
    # 关闭模型 / 退出 单测
    log("=== 单测 关闭模型")
    m_file = acts[0].menu()
    it = [x for x in m_file.actions() if x.text() == "关闭模型"][0]
    r = mb.actionGeometry(acts[0])
    QTest.mouseClick(mb, Qt.LeftButton, Qt.NoModifier, r.center()); pump(220)
    before = snapshot()
    QTest.mouseClick(m_file, Qt.LeftButton, Qt.NoModifier, m_file.actionGeometry(it).center())
    pump(350)
    log("    %s | status=%r 标题=%r" % (delta(before, snapshot()), STATUS.text, WIN.windowTitle()))
    shot(WIN, "after_close_model")
    log("--- 关闭后访问各页面")
    for i in range(6):
        WIN._select_page(i)
        pump(180)
        log("     页 %d ok" % i)
    H.dump()


# ---------------------------------------------------------------- 场景：视图菜单显示开关
def scen_view():
    vp = WIN.viewport
    keys = ["show_grid", "show_bones", "show_rigid", "show_joints",
            "show_texture", "toon", "outline", "wireframe"]
    mb = WIN.menubar
    va = [a for a in mb.actions() if a.text() == "视图"][0]
    menu = va.menu()
    r = mb.actionGeometry(va)
    for k in keys:
        it = [x for x in menu.actions() if x.text() and x.isCheckable()
              and WIN.display_actions.get(k) is x]
        it = it[0] if it else None
        log("--- 开关 %s action=%r" % (k, it.text() if it else None))
        b_val = getattr(vp, k, "<无此属性>")
        b_chk = it.isChecked() if it else None
        b_img = H.raw(WIN)
        QTest.mouseClick(mb, Qt.LeftButton, Qt.NoModifier, r.center())
        pump(220)
        QTest.mouseClick(menu, Qt.LeftButton, Qt.NoModifier, menu.actionGeometry(it).center())
        pump(420)
        a_val = getattr(vp, k, "<无此属性>")
        a_chk = it.isChecked() if it else None
        dpix = H.pixdiff(WIN, b_img)
        log("    vp.%s: %r → %r | action.checked %r → %r | 画面差异 %.2f%%"
            % (k, b_val, a_val, b_chk, a_chk, dpix))
        if b_val == a_val:
            anomaly("display-toggle", "菜单开关 %s 点击后 viewport.%s 未变化" % (k, k))
        if b_chk == b_val:
            pass
        shot(WIN, "view_%s" % k)
        if menu.isVisible():
            menu.close(); pump(100)
    # 恢复默认
    for k in keys:
        it = WIN.display_actions.get(k)
        if it is not None and it.isChecked() != (k in ("show_grid", "show_texture", "toon", "outline")):
            it.setChecked(k in ("show_grid", "show_texture", "toon", "outline"))
    pump(300)
    log("=== 设置页控件清单")
    WIN._select_page(5)
    pump(300)
    for w in walk(WIN._pages[5]):
        log("   ", desc(w))
    shot(WIN, "page_settings")
    H.dump()


# ---------------------------------------------------------------- 场景：视口交互
def _mouse_drag(vp, start, end, button, mods, steps=5):
    """直接投递鼠标事件：QTest.mouseMove 走光标路径，在无窗口系统命中的环境里到不了控件。"""
    def send(t, pt, btn, btns):
        ev = QMouseEvent(t, QPointF(pt), QPointF(pt), QPointF(pt), btn, btns, mods)
        if t == QEvent.MouseButtonPress:
            vp.mousePressEvent(ev)
        elif t == QEvent.MouseMove:
            vp.mouseMoveEvent(ev)
        else:
            vp.mouseReleaseEvent(ev)

    send(QEvent.MouseButtonPress, start, button, button)
    for k in range(1, steps):
        pt = QPoint(int(start.x() + (end.x() - start.x()) * k / float(steps)),
                    int(start.y() + (end.y() - start.y()) * k / float(steps)))
        send(QEvent.MouseMove, pt, Qt.NoButton, button)
        pump(40)
    send(QEvent.MouseButtonRelease, end, button, Qt.NoButton)


def scen_vp():
    vp = WIN.viewport
    cam = vp.camera
    W, Hh = vp.width(), vp.height()
    log("视口尺寸=%dx%d 相机 dist=%.3f yaw=%.3f pitch=%.3f target=%s"
        % (W, Hh, cam.distance, cam.yaw, cam.pitch, cam.target))
    # 网格扫描拾取
    hits = {}
    for yy in range(40, Hh - 40, 18):
        for xx in range(20, W - 20, 18):
            k, i = vp.pick(xx, yy)
            if k:
                hits.setdefault(k, []).append((xx, yy, i))
    log("拾取命中: %s" % {k: len(v) for k, v in hits.items()})
    for k, v in hits.items():
        log("   %s 首个=%s 末个=%s" % (k, v[0], v[-1]))
    if not hits:
        anomaly("pick", "视口内任意位置都拾取不到任何对象")
    # 单击骨骼
    if "bone" in hits:
        xx, yy, idx = hits["bone"][len(hits["bone"]) // 2]
        log("--- 单击骨骼 (本地坐标 %d,%d 期望 index=%d)" % (xx, yy, idx))
        QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, QPoint(xx, yy))
        pump(300)
        log("    doc.sel=%s vp.selection_kind=%r 页=%d status=%r"
            % ((WIN.doc.sel_kind, WIN.doc.sel_index), vp.selection_kind,
               WIN.inspector.currentIndex(), STATUS.text))
        log("    vp._hover=%r" % vp._hover)
    # 单击空白（左上角）
    log("--- 单击空白处 (10,10)")
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, QPoint(10, 10))
    pump(250)
    log("    doc.sel=%s" % ((WIN.doc.sel_kind, WIN.doc.sel_index),))
    if WIN.doc.sel_kind:
        anomaly("deselect", "点击视口空白处后选中状态没有清除（%s:%s 仍保持）"
                % (WIN.doc.sel_kind, WIN.doc.sel_index))
    # 滚轮缩放
    d0 = cam.distance
    log("--- 滚轮向下 3 格")
    QTest.mouseMove(vp, QPoint(W // 2, Hh // 2))
    for _ in range(3):
        e = QWheelEvent(QPointF(W / 2, Hh / 2), QPointF(W / 2, Hh / 2),
                        QPoint(0, 0), QPoint(0, -120), Qt.NoButton,
                        Qt.NoModifier, Qt.NoScrollPhase, False)
        APP.sendEvent(vp, e)
        pump(120)
    log("    distance %.4f → %.4f" % (d0, cam.distance))
    # 中键拖动旋转
    y0, p0 = cam.yaw, cam.pitch
    c = QPoint(W // 2, Hh // 2)
    log("--- 中键拖动 (旋转)")
    _mouse_drag(vp, c, c + QPoint(60, 20), Qt.MiddleButton, Qt.NoModifier)
    pump(250)
    log("    yaw %.4f → %.4f  pitch %.4f → %.4f" % (y0, cam.yaw, p0, cam.pitch))
    # Shift+中键 平移
    t0 = [float(v) for v in cam.target]
    log("--- Shift+中键拖动 (平移)")
    _mouse_drag(vp, c, c + QPoint(50, 30), Qt.MiddleButton, Qt.ShiftModifier)
    pump(250)
    log("    target %s → %s" % (t0, [round(float(v), 3) for v in cam.target]))
    # 键盘 F / R
    log("--- 按键 F")
    QTest.keyClick(vp, Qt.Key_F)
    pump(300)
    log("    dist=%.3f target=%s" % (cam.distance, [round(float(v), 3) for v in cam.target]))
    # 姿态编辑：左键拖动 = 位移，右键拖动 = 旋转
    log("=== 姿态编辑（物理关闭）")
    WIN.set_physics(False)
    pump(400)
    rot_before = [list(map(float, r)) for r in vp.pose.base_rot] if vp.pose else None
    trans_before = [list(map(float, r)) for r in vp.pose.base_trans] if vp.pose else None
    n_undo = len(WIN.doc._undo)
    if "bone" in hits:
        hx, hy, idx = [v for v in hits["bone"] if v[2] != 0][0]
        log("--- 右键拖动骨骼旋转 index=%d 本地(%d,%d)" % (idx, hx, hy))
        _mouse_drag(vp, QPoint(hx, hy), QPoint(hx + 40, hy + 15), Qt.RightButton, Qt.NoModifier)
        pump(500)
        log("    undo %d → %d status=%r" % (n_undo, len(WIN.doc._undo), STATUS.text))
        if vp.pose:
            rot_after = [list(map(float, r)) for r in vp.pose.base_rot]
            diff = [i for i in range(len(rot_before)) if rot_before[i] != rot_after[i]]
            log("    旋转变化的骨骼 = %s" % diff)
            if not diff:
                anomaly("pose-rotate", "右键拖动骨骼后没有任何骨骼旋转变化")
        # 左键拖动同一骨骼：应只改位移、不改旋转
        rot_mid = [list(map(float, r)) for r in vp.pose.base_rot]
        log("--- 左键拖动骨骼位移 index=%d" % idx)
        _mouse_drag(vp, QPoint(hx, hy), QPoint(hx - 30, hy - 20), Qt.LeftButton, Qt.NoModifier)
        pump(500)
        log("    status=%r" % STATUS.text)
        if vp.pose:
            rot_after2 = [list(map(float, r)) for r in vp.pose.base_rot]
            rot_diff = [i for i in range(len(rot_mid)) if rot_mid[i] != rot_after2[i]]
            trans_after = [list(map(float, r)) for r in vp.pose.base_trans]
            trans_diff = [i for i in range(len(trans_before))
                          if trans_before[i] != trans_after[i]]
            log("    位移变化的骨骼 = %s，旋转变化的骨骼 = %s"
                % (trans_diff, rot_diff))
            if not trans_diff:
                anomaly("pose-move", "左键拖动骨骼后没有骨骼位移变化")
            if idx in rot_diff:
                # IK 控制器被拖动时解算会转动链上的其他骨骼，但被拖的骨骼本身不该转
                anomaly("pose-move-rot", "左键拖动只应改位移，却改到了被拖骨骼的旋转")
        # 单击不拖：是否产生空撤销
        n_undo2 = len(WIN.doc._undo)
        log("--- 仅单击骨骼（不拖动）")
        QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, QPoint(hx, hy))
        pump(350)
        log("    undo %d → %d status=%r" % (n_undo2, len(WIN.doc._undo), STATUS.text))
        if len(WIN.doc._undo) > n_undo2:
            anomaly("pose-click-undo", "只单击骨骼未拖动，却压入了一条撤销记录")
    shot(WIN, "vp_pose")
    # R 重置
    log("--- 按键 R 重置姿态")
    QTest.keyClick(vp, Qt.Key_R)
    pump(400)
    log("    status=%r" % STATUS.text)
    # 物理演算开关
    log("=== 物理演算开关")
    WIN.set_physics(True)
    if not vp.show_rigid:
        vp.set_display(show_rigid=True)
    pump(600)
    hits = {}
    for yy in range(40, Hh - 40, 18):
        for xx in range(20, W - 20, 18):
            k, i = vp.pick(xx, yy)
            if k == "rigid":
                hits.setdefault("rigid", []).append((xx, yy, i))
    log("    物理模式刚体拾取: %d 处" % len(hits.get("rigid", [])))
    if "rigid" in hits:
        rx, ry, ridx = hits["rigid"][0]
        log("--- 物理模式左键拖动刚体 index=%d" % ridx)
        _mouse_drag(vp, QPoint(rx, ry), QPoint(rx + 50, ry + 10), Qt.LeftButton, Qt.NoModifier)
        pump(600)
        log("    status=%r" % STATUS.text)
    else:
        anomaly("pick-rigid", "物理模式下视口里拾取不到任何刚体（已打开 show_rigid）")
    # 物理开着的同时摆姿：挑一根不受刚体驱动的骨骼，左键拖动应改变它的位移
    driven = {int(rb.bone) for rb in WIN.doc.model.rigid}
    target = None
    for yy in range(40, Hh - 40, 12):
        for xx in range(20, W - 20, 12):
            k, i = vp.pick(xx, yy)
            if k == "bone" and i not in driven:
                target = (xx, yy, i)
                break
        if target:
            break
    if target:
        bx, by, bidx = target
        t0 = vp.pose.base_trans[bidx].copy()
        log("--- 物理演算中左键拖动非物理骨骼 index=%d" % bidx)
        _mouse_drag(vp, QPoint(bx, by), QPoint(bx + 35, by + 20),
                    Qt.LeftButton, Qt.NoModifier)
        pump(400)
        moved = float(__import__("numpy").abs(vp.pose.base_trans[bidx] - t0).max())
        log("    位移变化=%.4f physics=%s status=%r"
            % (moved, vp.physics.enabled, STATUS.text))
        if moved < 1e-4:
            anomaly("phys-pose", "物理演算中拖动骨骼没有改变姿态（%.6f）" % moved)
        if not vp.physics.enabled:
            anomaly("phys-pose-off", "拖动骨骼后物理演算被意外关闭")
    else:
        log("--- 没有找到不受刚体驱动的骨骼，跳过物理+姿态共存检查")
    H.dump()


def _by_tip(page, tip):
    for w in page.findChildren(QPushButton):
        if w.toolTip() == tip and w.isVisible():
            return w
    return None


# ---------------------------------------------------------------- 场景：逐项选择遍历
def scen_sel():
    m = WIN.doc.model
    plan = [("bone", len(m.bones)), ("material", len(m.materials)),
            ("morph", len(m.morphs)), ("rigid", len(m.rigid)),
            ("joint", len(m.joints))]
    for kind, n in plan:
        for i in range(n):
            try:
                WIN.doc.select(kind, i)
                pump(80)
                ok = "ok"
            except Exception:
                ok = "RAISE " + traceback.format_exc().splitlines()[-1]
                anomaly("select-%s-%d" % (kind, i), traceback.format_exc())
            if STATUS.text.startswith("选择失败"):
                anomaly("select-fail-%s-%d" % (kind, i), STATUS.text)
            log("%-8s #%d → sel=%s status=%r %s"
                % (kind, i, (WIN.doc.sel_kind, WIN.doc.sel_index), STATUS.text, ok))
        # 逐行点击列表（真实鼠标）
        page = {"bone": 1, "material": 2, "morph": 3, "rigid": 4, "joint": 4}[kind]
        WIN._select_page(page)
        pump(250)
        pw = WIN._pages[page]
        lv = pw.tree if kind == "bone" else pw.list
        if kind == "bone":
            lv.expandAll()
            pump(120)
        mdl = lv.model()
        cnt = mdl.rowCount()
        log("  [%s] 列表 rowCount=%d" % (kind, cnt))
        for r in range(min(cnt, 6)):
            idx = mdl.index(r, 0)
            rc = lv.visualRect(idx)
            if not rc.isValid():
                log("    row %d rect 无效（不可见）" % r)
                continue
            before = (WIN.doc.sel_kind, WIN.doc.sel_index)
            n_undo = len(WIN.doc._undo)
            try:
                QTest.mouseClick(lv.viewport(), Qt.LeftButton, Qt.NoModifier, rc.center())
                pump(150)
            except Exception:
                anomaly("click-row-%s-%d" % (kind, r), traceback.format_exc())
            log("    单击 row %d %r → %s undo %d→%d status=%r"
                % (r, mdl.data(idx, Qt.DisplayRole), (WIN.doc.sel_kind, WIN.doc.sel_index),
                   n_undo, len(WIN.doc._undo), STATUS.text))
            if STATUS.text.startswith("选择失败"):
                anomaly("click-fail-%s-%d" % (kind, r), STATUS.text)
    log("done")
    H.dump()
# ---------------------------------------------------------------- 场景：刚体选择递归取证
def scen_sel2():
    m = WIN.doc.model
    pp = WIN._pages[4]
    log("rigid=%d joints=%d" % (len(m.rigid), len(m.joints)))
    for i in range(len(m.rigid)):
        try:
            pp.select("rigid", i)
            log("rigid %d OK idx=%d" % (i, pp.idx))
        except RecursionError:
            lines = traceback.format_exc().splitlines()
            frames = [l.strip() for l in lines if l.strip().startswith("File ")]
            log("rigid %d RecursionError frames=%d" % (i, len(frames)))
            log("   head=%s" % frames[:6])
            log("   tail=%s" % frames[-8:])
            anomaly("rigid-recursion-%d" % i, "frames=%d\n%s" % (len(frames), "\n".join(frames[-12:])))
        except Exception:
            anomaly("rigid-select-%d" % i, traceback.format_exc())
    try:
        WIN.doc.select("rigid", 0)
        log("doc.select rigid0 OK status=%r" % STATUS.text)
    except Exception:
        anomaly("doc-select-rigid0", traceback.format_exc())
    log("done")
    H.dump()
# ---------------------------------------------------------------- 场景：select 递归取证
def scen_sel3():
    def wrap(pg, k):
        orig = pg.select
        def f(kind, index):
            log("   -> page%d.select(%r,%d)" % (k, kind, index))
            try:
                return orig(kind, index)
            except BaseException:
                tb = traceback.format_exc().splitlines()
                frames = [l.strip() for l in tb if l.strip().startswith("File ")]
                anomaly("page%d-select" % k, "frames=%d tail=%s" % (len(frames), frames[-14:]))
                raise
        return f
    for k, pg in enumerate(WIN._pages):
        pg.select = wrap(pg, k)
    _orig_status = WIN._set_status
    def _st(msg):
        if msg.startswith("选择失败"):
            import traceback as _tb
            frames = [l.strip() for l in _tb.format_stack()[-6:]]
            log("   !! _set_status(%r) stack=%s" % (msg[:60], frames[-4:]))
        return _orig_status(msg)
    WIN._set_status = _st
    log("pages=%d wrapped" % len(WIN._pages))
    for i in range(len(WIN.doc.model.rigid)):
        n = len(H.ANOM)
        WIN.doc.select("rigid", i)
        pump(120)
        log("doc.select rigid %d → status=%r 新异常=%d" % (i, STATUS.text, len(H.ANOM) - n))
    for i in range(len(WIN.doc.model.joints)):
        n = len(H.ANOM)
        WIN.doc.select("joint", i)
        pump(120)
        log("doc.select joint %d → status=%r 新异常=%d" % (i, STATUS.text, len(H.ANOM) - n))
    for a in H.ANOM[-2:]:
        log("ANOM %s: %s" % (a["kind"], a["detail"][:600]))
    log("done")
    H.dump()
# ---------------------------------------------------------------- 场景：小递归上限取证
def scen_sel4():
    import sys as _s
    pp = WIN._pages[4]
    _s.setrecursionlimit(150)
    try:
        pp.select("rigid", 1)
        log("select ok idx=%d" % pp.idx)
    except RecursionError:
        tb = traceback.format_exc().splitlines()
        frames = [l.strip() for l in tb if l.strip().startswith("File ")]
        log("RecursionError frames=%d" % len(frames))
        for f in frames[-24:]:
            log("   %s" % f)
        anomaly("recursion-small", "\n".join(frames[-24:]))
    _s.setrecursionlimit(1000)
    log("done")
    H.dump()
# ---------------------------------------------------------------- 场景：recursion 栈取证
def scen_sel5():
    import sys as _s
    _orig = WIN._set_status
    def _st(msg):
        if msg.startswith("选择失败"):
            frames = [l.strip() for l in traceback.format_stack()[-16:]]
            log("SET_STATUS %r" % msg[:50])
            for f in frames:
                log("   %s" % f)
        return _orig(msg)
    WIN._set_status = _st
    _s.setrecursionlimit(220)
    WIN.doc.select("rigid", 1)
    _s.setrecursionlimit(1000)
    pump(100)
    WIN._set_status = _orig
    log("done")
    H.dump()
# ---------------------------------------------------------------- 场景：递归环取证（第3层打印栈）
def scen_sel6():
    pp = WIN._pages[4]
    orig = pp.select
    st = {"n": 0}
    def _sel(kind, index, *a, **k):
        st["n"] += 1
        if st["n"] == 3:
            frames = [l.strip() for l in traceback.format_stack()[-18:]]
            log("=== 第3次进入 select 的调用栈 ===")
            for f in frames:
                log("  %s" % f)
            raise RuntimeError("BREAK-RECURSION-PROBE")
        return orig(kind, index, *a, **k)
    pp.select = _sel
    WIN.doc.select("rigid", 1)
    pp.select = orig
    log("select calls=%d sel=%r status=%r" % (st["n"], WIN.doc.sel, WIN.status_label.text()))
    H.dump()
# ---------------------------------------------------------------- 场景：真实点击刚体列表行
def scen_click_rigid():
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    WIN._select_page(4)
    pump(80)
    pp = WIN._pages[4]
    log("kind=%r idx=%r rows=%d current=%d" % (pp.kind, pp.idx, pp.list._model.rowCount(), pp.list.currentIndex().row()))
    r = pp.list.visualRect(pp.list._model.index(1, 0))
    log("row1 rect=%r" % (r,))
    log("clicking row1 ...")
    QTest.mouseClick(pp.list.viewport(), Qt.LeftButton, Qt.NoModifier, r.center())
    pump(120)
    log("after click sel=(%r,%r) status=%r row=%d" % (WIN.doc.sel_kind, WIN.doc.sel_index, WIN.status_label.text(), pp.list.currentIndex().row()))
    QTest.mouseClick(pp.list.viewport(), Qt.LeftButton, Qt.NoModifier, r.center())
    pump(120)
    log("2nd click sel=(%r,%r) status=%r" % (WIN.doc.sel_kind, WIN.doc.sel_index, WIN.status_label.text()))
    H.dump()
# ---------------------------------------------------------------- 场景：最后一轮（右键/快捷键/分隔条/缩放/亮色）
def scen_last():
    from PyQt5.QtCore import Qt, QTimer, QPoint
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication, QMenu
    H.patch_menus()
    # A) 材质列表点击
    WIN._select_page(2)
    pump(80)
    mp = WIN._pages[2]
    log("A material rows=%d cur=%d sel=(%r,%r)" % (mp.list._model.rowCount(), mp.list.currentIndex().row(), WIN.doc.sel_kind, WIN.doc.sel_index))
    r = mp.list.visualRect(mp.list._model.index(1, 0))
    QTest.mouseClick(mp.list.viewport(), Qt.LeftButton, Qt.NoModifier, r.center())
    pump(80)
    log("A after click row1 sel=(%r,%r) idx=%r status=%r" % (WIN.doc.sel_kind, WIN.doc.sel_index, mp.idx, WIN.status_label.text()))
    # B) 右键上下文菜单
    H.MENUS.clear()
    QTest.mouseClick(mp.list.viewport(), Qt.RightButton, Qt.NoModifier, r.center())
    pump(120)
    vis = [w for w in QApplication.topLevelWidgets() if isinstance(w, QMenu) and w.isVisible()]
    log("B rightclick menus_visible=%d captured=%d" % (len(vis), len(H.MENUS)))
    for w in vis:
        w.close()
    # C) 快捷键
    WIN.activateWindow(); pump(50)
    log("C before: dirty=%r undo=%d redo=%d" % (WIN.doc.dirty, WIN.doc.undo_depth() if hasattr(WIN.doc,'undo_depth') else -1, -1))
    QTest.keyClick(WIN, Qt.Key_S, Qt.ControlModifier); pump(120)
    log("C ctrl+S -> title=%r status=%r dirty=%r" % (WIN.windowTitle(), WIN.status_label.text(), WIN.doc.dirty))
    mp.mat_name_edit = getattr(mp, "name_edit", None)
    log("C ctrl+F/F/R keys")
    QTest.keyClick(WIN, Qt.Key_F); pump(60)
    QTest.keyClick(WIN, Qt.Key_R); pump(60)
    log("C after F,R status=%r" % WIN.status_label.text())
    # D) 分隔条拖动
    sp = getattr(WIN, "splitter", None)
    log("D splitter=%r sizes=%r" % (type(sp).__name__ if sp else None, sp.sizes() if sp else None))
    if sp:
        before = sp.sizes()
        sp.moveSplitter(before[0] - 180, 1)
        pump(60)
        log("D after move sizes=%r" % (sp.sizes(),))
        sp.setSizes(before)
        pump(60)
    # E) 缩到最小尺寸
    WIN.resize(1120, 700); pump(150)
    H.shot(WIN, "last_min")
    log("E min size ok=%r win=%r" % (WIN.size(), WIN.minimumSize()))
    # F) 亮色主题截图
    WIN._set_theme("light"); pump(200)
    H.shot(WIN, "last_light")
    log("F light status=%r" % WIN.status_label.text())
    WIN._set_theme("dark"); pump(150)
    # G) Esc / 关闭按钮存在性
    btns = [b for b in WIN.findChildren(type(WIN)) if False]
    log("G done")
    H.dump()
# ---------------------------------------------------------------- 场景：列表行右侧文本是否被裁掉
def scen_rows():
    WIN._select_page(2)
    pump(80)
    mp = WIN._pages[2]
    for th in ("dark", "light", "dark"):
        WIN._set_theme(th); pump(120)
        lst = mp.list
        hb = lst.horizontalScrollBar()
        r0 = lst.visualRect(lst._model.index(0, 0))
        r1 = lst.visualRect(lst._model.index(1, 0))
        log("%s vw=%d row0=%r row1=%r hbar vis=%r max=%r val=%r" % (
            th, lst.viewport().width(), (r0.x(), r0.width()), (r1.x(), r1.width()),
            hb.isVisible(), hb.maximum(), hb.value()))
        log("   row1 data right=%r" % (lst._model.index(1, 0).data(Qt.UserRole + 2) if False else lst._model.index(1, 0).data(0x0102),))
    H.shot(WIN, "rows_dark")
    H.dump()
# ---------------------------------------------------------------- 场景：亮色起始截图
def scen_lightfresh():
    pump(300)
    H.shot(WIN, "light_fresh")
    log("theme done status=%r" % WIN.status_label.text())
    H.dump()
# ---------------------------------------------------------------- 场景：主题常量是否冻结
def scen_themeconst():
    from pmxeditor import theme, viewport
    names = ["GRID_MINOR_RGB", "GRID_MAJOR_RGB", "GRID_X_RGB", "VIEW_BG_RGB",
             "BONE_RGB", "RIGID_STATIC_RGB", "TEXT", "ACCENT", "TEX_MISS_BG"]
    for th in ("light", "dark"):
        WIN._set_theme(th); pump(150)
        log("== theme=%s" % th)
        for n in names:
            log("   %-16s theme=%r viewport=%r %s" % (
                n, getattr(theme, n, "?"), getattr(viewport, n, "?"),
                "SAME" if getattr(theme, n, None) == getattr(viewport, n, None) else "FROZEN!"))
    H.dump()
# ---------------------------------------------------------------- 场景：亮色下关掉辅助线
def scen_lightoff():
    from pmxeditor import app as appmod
    WIN._set_theme("light"); pump(200)
    vp = WIN.viewport
    log("defaults show_bones=%r show_rigid=%r show_joints=%r show_grid=%r wire=%r" % (
        vp.show_bones, vp.show_rigid, vp.show_joints, vp.show_grid, getattr(vp, "wireframe", "?")[0] if isinstance(getattr(vp,"wireframe",0), tuple) else getattr(vp,"wireframe","?")))
    vp.show_bones = False; vp.show_rigid = False; vp.show_joints = False
    vp.update(); pump(200)
    H.shot(WIN, "light_off")
    print("SHOT light_off")
    vp.show_grid = False; vp.update(); pump(200)
    H.shot(WIN, "light_off_nogrid")
    print("SHOT light_off_nogrid")
    H.dump()
# ---------------------------------------------------------------- 场景：网格顶点色内容
def scen_gridcolor():
    import numpy as np
    WIN._set_theme("light"); pump(200)
    vp = WIN.viewport
    verts, colors = vp._grid
    u = np.unique(np.round(colors, 3), axis=0)
    log("light: verts=%r colors=%r unique=%d" % (verts.shape, colors.shape, len(u)))
    for row in u:
        log("   color=%r" % (tuple(round(float(x), 3) for x in row),))
    vbo = vp._grid_vbo
    log("vbo ids=%r" % (vbo,))
    WIN._set_theme("dark"); pump(150)
    verts, colors = vp._grid
    u = np.unique(np.round(colors, 3), axis=0)
    log("dark: unique=%d" % len(u))
    for row in u:
        log("   color=%r" % (tuple(round(float(x), 3) for x in row),))
    log("vbo ids=%r" % (vp._grid_vbo,))
    H.dump()
# ---------------------------------------------------------------- 场景：VBO id 复用检查
def scen_vbo():
    WIN._set_theme("dark"); pump(150)
    vp = WIN.viewport
    log("DARK  grid=%r lines=%r counts=%r" % (vp._grid_vbo, vp._vbo_lines, vp._line_counts))
    WIN._set_theme("light"); pump(250)
    log("LIGHT grid=%r lines=%r counts=%r" % (vp._grid_vbo, vp._vbo_lines, vp._line_counts))
    log("show: bones=%r rigid=%r joints=%r" % (vp.show_bones, vp.show_rigid, vp.show_joints))
    H.dump()
# ---------------------------------------------------------------- 场景：收尾验证
def scen_final():
    from pmxeditor import panels as pn
    from pmxeditor import app as appmod
    from PyQt5.QtCore import QMimeData, QPoint, QUrl
    from PyQt5.QtGui import QDragEnterEvent, QDropEvent
    from PyQt5.QtWidgets import QMessageBox as MB

    def counts():
        m = WIN.doc.model
        return None if m is None else (len(m.bones), len(m.materials), len(m.morphs),
                                       len(m.rigid), len(m.joints))

    # ---- 确认框记录器
    class FakeConfirm(QWidget):
        Accepted = 1
        Rejected = 0
        def __init__(self, title, text, **kw):
            super().__init__()
            H.DIALOGS.append({"kind": "ConfirmDialog", "window": title, "text": text})
        def exec_(self):
            return 1
    pn.ConfirmDialog = FakeConfirm

    # ================= A. 关节/刚体删除取证
    WIN._select_page(4)
    pump(300)
    pp = WIN._pages[4]
    b_add = _by_tip(pp, "新建刚体 / 关节")
    b_del = _by_tip(pp, "删除当前项目")
    log("A0 初始 counts=%s kind=%r seg=%s"
        % (counts(), pp.kind, [w.text() for w in pp.findChildren(QPushButton)
                               if w.objectName() == "Segment"]))
    segj = [w for w in pp.findChildren(QPushButton)
            if w.objectName() == "Segment" and w.text() == "关节"][0]
    click(segj); pump(300)
    log("A1 点『关节』后 kind=%r sel=%s" % (pp.kind, (WIN.doc.sel_kind, WIN.doc.sel_index)))
    log("A2 joints 名称=%s" % [j.name for j in WIN.doc.model.joints])
    click(b_add); pump(300)
    log("A3 新建后 kind=%r counts=%s joints=%s sel=%s"
        % (pp.kind, counts(), [j.name for j in WIN.doc.model.joints],
           (WIN.doc.sel_kind, WIN.doc.sel_index)))
    click(b_del); pump(350)
    log("A4 删除后 kind=%r counts=%s joints=%s"
        % (pp.kind, counts(), [j.name for j in WIN.doc.model.joints]))
    log("A5 对话框记录=%s" % [d for d in H.DIALOGS[-2:]])
    log("A6 撤销栈=%s" % ([u if isinstance(u, str) else getattr(u, "label", str(u))
                          for u in WIN.doc._undo][-4:]))

    # ---- A7 直接调用 _add/_remove 取真实堆栈
    pp.kind = "joint"
    try:
        pp._add()
        log("A7 _add OK counts=%s" % (counts(),))
    except Exception:
        anomaly("joint-add-direct", traceback.format_exc())
    try:
        pp._remove()
        log("A7b _remove OK counts=%s" % (counts(),))
    except Exception:
        anomaly("joint-remove-direct", traceback.format_exc())
    # ================= C. 未保存提示三分支
    class FakeBox(MB):
        NEXT = MB.Discard
        def __init__(self, *a, **k):
            super().__init__()
            H.DIALOGS.append({"kind": "UnsaveBox", "window": "", "text": ""})
        def setWindowTitle(self, t):
            H.DIALOGS[-1]["window"] = t
        def setText(self, t):
            H.DIALOGS[-1]["text"] = t
        def setInformativeText(self, t):
            H.DIALOGS[-1]["extra"] = t
        def setStandardButtons(self, *a):
            pass
        def setDefaultButton(self, *a):
            pass
        def exec_(self):
            return FakeBox.NEXT
    old_box = appmod.QMessageBox
    appmod.QMessageBox = FakeBox
    WIN.doc.mark_dirty()
    FakeBox.NEXT = MB.Discard
    n = len(H.DIALOGS)
    r = WIN._maybe_save()
    log("C1 Discard → 返回 %s 弹窗=%s dirty=%s" % (r, H.DIALOGS[n:], WIN.doc.dirty))
    WIN.doc.mark_dirty()
    FakeBox.NEXT = MB.Cancel
    n = len(H.DIALOGS)
    r = WIN._maybe_save()
    log("C2 Cancel → 返回 %s 弹窗=%s dirty=%s" % (r, H.DIALOGS[n:], WIN.doc.dirty))
    # Cancel 时关闭模型应被阻止
    before = counts()
    WIN.close_model(); pump(200)
    log("C3 dirty+关闭模型(Cancel) counts %s → %s（应不变）status=%r"
        % (before, counts(), STATUS.text))
    FakeBox.NEXT = MB.Save
    WIN.doc.mark_dirty()
    n = len(H.DIALOGS)
    r = WIN._maybe_save()
    log("C4 Save → 返回 %s dirty=%s status=%r" % (r, WIN.doc.dirty, STATUS.text))
    appmod.QMessageBox = old_box
    WIN.doc.dirty = False

    # ================= D. 拖拽打开
    before = counts()
    md = QMimeData()
    md.setUrls([QUrl.fromLocalFile(os.path.join(H.ROOT, "tests", "test_model.pmx"))])
    de = QDragEnterEvent(QPoint(200, 200), Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier)
    WIN.dragEnterEvent(de)
    log("D1 dragEnter accepted=%s" % de.isAccepted())
    dp = QDropEvent(QPoint(200, 200), Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier)
    WIN.dropEvent(dp)
    pump(400)
    log("D2 drop 后 counts %s → %s path=%r name=%r"
        % (before, counts(), WIN.doc.path, WIN.doc.model.name if WIN.doc.model else None))
    md2 = QMimeData()
    md2.setText("hello")
    de2 = QDragEnterEvent(QPoint(200, 200), Qt.CopyAction, md2, Qt.LeftButton, Qt.NoModifier)
    WIN.dragEnterEvent(de2)
    log("D3 非文件拖入 accepted=%s（应 False）" % de2.isAccepted())

    # ================= E. 姿态/形态/双击
    WIN.set_physics(False); pump(300)
    log("E1 模式=%r status=%r undo=%d" % (getattr(WIN, "cur_mode", "?"), STATUS.text, len(WIN.doc._undo)))
    WIN.set_physics(False); pump(200)
    WIN.doc.select("bone", 1); pump(200)
    WIN._select_page(3); pump(300)
    mp = WIN._pages[3]
    sl = [w for w in walk(mp) if isinstance(w, QSlider) and w.isVisible()]
    log("E2 形态滑杆 %d 个 value=%s" % (len(sl), [x.value() for x in sl]))
    if sl:
        s0 = sl[0]
        s0.setValue(100); pump(250)
        log("E3 滑杆设 100 后 value=%d status=%r" % (s0.value(), STATUS.text))
        s0.setValue(0); pump(150)
    # 双击骨骼树行
    WIN._select_page(1); pump(300)
    bp = WIN._pages[1]
    tree = bp.tree
    tree.expandAll(); pump(200)
    mdl = tree.model()
    log("E4 骨骼树 rows(top)=%d expanded rows=%d"
        % (mdl.rowCount(), sum(1 for _ in range(mdl.rowCount()))))
    rc = tree.visualRect(mdl.index(0, 0))
    log("E4b 第一行 rect=%s viewport=%s" % (rc, tree.viewport().rect()))
    n = len(WIN.doc._undo)
    QTest.mouseDClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier, rc.center()); pump(300)
    log("E5 双击骨骼行 sel=%s undo %d→%d status=%r"
        % ((WIN.doc.sel_kind, WIN.doc.sel_index), n, len(WIN.doc._undo), STATUS.text))
    QTest.mouseClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier, rc.center()); pump(250)
    log("E5b 单击骨骼行 sel=%s" % ((WIN.doc.sel_kind, WIN.doc.sel_index),))
    # 双击列表行（材质）
    WIN._select_page(2); pump(300)
    lm = WIN._pages[2].list
    rc2 = lm.visualRect(lm.model().index(0, 0))
    n = len(WIN.doc._undo)
    QTest.mouseDClick(lm.viewport(), Qt.LeftButton, Qt.NoModifier, rc2.center()); pump(300)
    log("E6 双击材质行 sel=%s undo %d→%d status=%r"
        % ((WIN.doc.sel_kind, WIN.doc.sel_index), n, len(WIN.doc._undo), STATUS.text))
    # ================= F. 撤销栈上限
    WIN._select_page(1); pump(250)
    bp = WIN._pages[1]
    for k in range(14):
        bp.name_edit.setText("B%d" % k)
        bp.name_edit.editingFinished.emit()
        pump(60)
    log("F1 连续 14 次改名后 undo 深度=%d（上限 12）dirty=%s" % (len(WIN.doc._undo), WIN.doc.dirty))
    ok = 0
    for k in range(14):
        try:
            WIN.undo(); pump(40); ok += 1
        except Exception:
            anomaly("undo-overflow", traceback.format_exc()); break
    log("F2 撤销 %d 次后 name=%r undo=%d redo=%d status=%r"
        % (ok, WIN.doc.model.bones[WIN.doc.sel_index].name if WIN.doc.sel_index >= 0 else None,
           len(WIN.doc._undo), len(WIN.doc._redo), STATUS.text))
    for k in range(14):
        try:
            WIN.redo(); pump(40)
        except Exception:
            anomaly("redo-overflow", traceback.format_exc()); break
    log("F3 重做后 undo=%d redo=%d name=%r"
        % (len(WIN.doc._undo), len(WIN.doc._redo),
           WIN.doc.model.bones[WIN.doc.sel_index].name if WIN.doc.sel_index >= 0 else None))
    log("done")
    H.dump()

def scen_verify_p0():
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    H.STATE["step"] = "verify"
    log("=== P0-1 color buttons ===")
    WIN._select_page(2)
    pump(100)
    mp = WIN._pages[2]
    log("material rows=%d idx=%d" % (mp.list._model.rowCount(), mp.idx))
    for w, fld in ((mp.diffuse, "diffuse"), (mp.specular, "specular"),
                   (mp.ambient, "ambient"), (mp.edge_color, "edge_color")):
        n0 = len(H.ANOM)
        H.click(w)
        pump(80)
        mt = WIN.doc.model.materials[mp.idx]
        v = getattr(mt, fld)
        log("click %-11s -> %r len=%d anom+%d" % (fld, v, len(v), len(H.ANOM) - n0))
        H.raw(WIN)
    mt = WIN.doc.model.materials[mp.idx]
    log("after all: diff=%r spec=%r amb=%r edge=%r" % (mt.diffuse, mt.specular, mt.ambient, mt.edge_color))
    WIN.doc.undo(); pump(60)
    mt = WIN.doc.model.materials[mp.idx]
    log("undo -> spec=%r amb=%r" % (mt.specular, mt.ambient))
    WIN.doc.redo(); pump(60)
    mt = WIN.doc.model.materials[mp.idx]
    log("redo -> edge=%r" % (mt.edge_color,))
    log("=== P0-2 physics select recursion ===")
    WIN._select_page(4)
    pump(120)
    pp = WIN._pages[4]
    log("kind=%r rows=%d cur=%d" % (pp.kind, pp.list._model.rowCount(), pp.list.currentIndex().row()))
    for idx in (1, 2, 0, 1):
        n0 = len(H.ANOM)
        try:
            WIN.doc.select("rigid", idx)
        except Exception as e:
            log("select rigid %d raised %r" % (idx, e))
        pump(80)
        log("select rigid %d -> sel=(%r,%r) anom+%d" % (idx, WIN.doc.sel_kind, WIN.doc.sel_index, len(H.ANOM) - n0))
    n0 = len(H.ANOM)
    WIN.doc.select("joint", 0); pump(80)
    log("select joint 0 -> sel=(%r,%r) anom+%d" % (WIN.doc.sel_kind, WIN.doc.sel_index, len(H.ANOM) - n0))
    nj = len(WIN.doc.model.joints)
    n0 = len(H.ANOM)
    WIN.doc.select("joint", nj - 1); pump(80)
    log("select joint %d -> sel=(%r,%r) anom+%d" % (nj - 1, WIN.doc.sel_kind, WIN.doc.sel_index, len(H.ANOM) - n0))
    WIN.doc.select("rigid", 0); pump(80)
    r = pp.list.visualRect(pp.list._model.index(1, 0))
    n0 = len(H.ANOM)
    QTest.mouseClick(pp.list.viewport(), Qt.LeftButton, Qt.NoModifier, r.center())
    pump(200)
    log("real click row1 -> sel=(%r,%r) row=%d anom+%d" % (WIN.doc.sel_kind, WIN.doc.sel_index, pp.list.currentIndex().row(), len(H.ANOM) - n0))
    # 连续切换页 + 选择
    for i in range(6):
        WIN._select_page(i); pump(40)
    log("TOTAL ANOM=%d" % len(H.ANOM))
    for a in H.ANOM:
        log("ANOM[%s] %s: %s" % (a["step"], a["kind"], a["detail"][:300]))
    H.dump()

def scen_grid_gl():
    import numpy as np
    import OpenGL.GL as GL
    from PyQt5.QtCore import Qt
    H.STATE["step"] = "grid"
    WIN._set_theme("light"); pump(250)
    WIN.grab(); pump(120)
    vp = WIN.viewport
    vp.makeCurrent()
    log("vbo grid=%r mesh=%r lines=%r" % (vp._grid_vbo, vp._mesh.get("pos"), vp._vbo_lines))
    n = int(vp._grid[1].nbytes)
    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vp._grid_vbo[1])
    raw = GL.glGetBufferSubData(GL.GL_ARRAY_BUFFER, 0, n)
    gpu = np.frombuffer(raw, dtype=np.float32)
    log("gpu color head %s" % (np.round(gpu[:12], 4).tolist(),))
    log("cpu color head %s" % (np.round(vp._grid[1].ravel()[:12], 4).tolist(),))
    log("gpu color uniq %s" % (sorted(set(map(tuple, np.round(gpu.reshape(-1, 3), 3).tolist())))[:6],))
    log("attrib aColor loc=%r aPos=%r" % (GL.glGetAttribLocation(vp._prog_line, "aColor"),
                                          GL.glGetAttribLocation(vp._prog_line, "aPos")))
    grid_n = len(vp._grid[0])
    seen = []
    orig = GL.glDrawArrays

    def patched(mode, first, count):
        if mode == GL.GL_LINES and count == grid_n:
            buf1 = GL.glGetVertexAttribiv(1, GL.GL_VERTEX_ATTRIB_ARRAY_BUFFER_BINDING)[0]
            buf0 = GL.glGetVertexAttribiv(0, GL.GL_VERTEX_ATTRIB_ARRAY_BUFFER_BINDING)[0]
            sz1 = GL.glGetVertexAttribiv(1, GL.GL_VERTEX_ATTRIB_ARRAY_SIZE)[0]
            ty1 = GL.glGetVertexAttribiv(1, GL.GL_VERTEX_ATTRIB_ARRAY_TYPE)[0]
            st1 = GL.glGetVertexAttribiv(1, GL.GL_VERTEX_ATTRIB_ARRAY_STRIDE)[0]
            en1 = GL.glGetVertexAttribiv(1, GL.GL_VERTEX_ATTRIB_ARRAY_ENABLED)[0]
            seen.append((buf0, buf1, sz1, ty1, st1, en1, count))
        return orig(mode, first, count)

    GL.glDrawArrays = patched
    try:
        WIN.grab(); pump(120)
    finally:
        GL.glDrawArrays = orig
    log("grid draws seen: %r" % (seen[:4],))
    # 取像素
    img = WIN.viewport.grab().toImage()
    W, Hh = img.width(), img.height()
    from collections import Counter
    cnt = Counter()
    for y in range(int(Hh * 0.45), int(Hh * 0.72), 2):
        for x in range(0, int(W * 0.45), 2):
            c = img.pixelColor(x, y)
            if (c.red(), c.green(), c.blue()) == (255, 255, 255):
                continue
            cnt[(c.red() // 32 * 32, c.green() // 32 * 32, c.blue() // 32 * 32)] += 1
    log("top colors %r" % (cnt.most_common(8),))
    H.dump()



def scen_grid_clean():
    from collections import Counter
    H.STATE["step"] = "gridclean"
    WIN._set_theme("light"); pump(200)
    WIN.close_model(); pump(200)
    vp = WIN.viewport
    H.shot(WIN, "gridclean_model_off")
    img = vp.grab().toImage()

    def count(tag):
        cnt = Counter()
        for y in range(0, img.height(), 2):
            for x in range(0, img.width(), 2):
                c = img.pixelColor(x, y)
                key = (c.red() // 32 * 32, c.green() // 32 * 32, c.blue() // 32 * 32)
                cnt[key] += 1
        red = sum(v for k, v in cnt.items() if k[0] >= 192 and k[1] < 64 and k[2] < 64)
        yel = sum(v for k, v in cnt.items() if k[0] >= 192 and k[1] >= 192 and k[2] < 96)
        log("%s size=%dx%d red=%d yellow=%d top=%r" % (tag, img.width(), img.height(), red, yel, cnt.most_common(6)))

    count("grid_on")
    vp.show_grid = False
    vp.update(); pump(200)
    img = vp.grab().toImage()
    count("grid_off")
    vp.show_grid = True
    vp.update(); pump(200)
    img = vp.grab().toImage()
    count("grid_back")
    H.dump()

def scen_grid_const():
    import numpy as np
    import OpenGL.GL as GL
    from collections import Counter
    from PyQt5.QtCore import Qt
    H.STATE["step"] = "gridconst"
    WIN._set_theme("light"); pump(200)
    WIN.close_model(); pump(200)
    vp = WIN.viewport

    def stats(tag):
        img = vp.grab().toImage()
        cnt = Counter()
        for y in range(0, img.height(), 2):
            for x in range(0, img.width(), 2):
                c = img.pixelColor(x, y)
                cnt[(c.red() // 32 * 32, c.green() // 32 * 32, c.blue() // 32 * 32)] += 1
        red = sum(v for k, v in cnt.items() if k[0] >= 192 and k[1] < 64 and k[2] < 64)
        yel = sum(v for k, v in cnt.items() if k[0] >= 192 and k[1] >= 192 and k[2] < 96)
        log("%-14s red=%d yellow=%d top=%r" % (tag, red, yel, cnt.most_common(5)))

    stats("baseline")
    verts, colors = vp._grid
    vp.makeCurrent()
    flat = np.full_like(colors, 0.5)
    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vp._grid_vbo[1])
    GL.glBufferSubData(GL.GL_ARRAY_BUFFER, 0, flat.nbytes, flat)
    vp.doneCurrent()
    vp.update(); pump(250)
    stats("const0.5")
    # 恢复
    vp.makeCurrent()
    GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vp._grid_vbo[1])
    GL.glBufferSubData(GL.GL_ARRAY_BUFFER, 0, colors.nbytes, colors)
    vp.doneCurrent()
    vp.update(); pump(250)
    stats("restored")
    H.dump()

def scen_grid_calls():
    import numpy as np
    import OpenGL.GL as GL
    H.STATE["step"] = "gridcalls"
    WIN._set_theme("light"); pump(200)
    WIN.close_model(); pump(200)
    vp = WIN.viewport
    calls = []
    state = {"prog": 0}
    ou, oa, oe = GL.glUseProgram, GL.glDrawArrays, GL.glDrawElements

    def use(p):
        state["prog"] = p
        return ou(p)

    def da(mode, first, count):
        calls.append(("A", state["prog"], mode, first, count))
        return oa(mode, first, count)

    def de(mode, count, typ, idx):
        calls.append(("E", state["prog"], mode, count))
        return oe(mode, count, typ, idx)

    GL.glUseProgram, GL.glDrawArrays, GL.glDrawElements = use, da, de
    try:
        vp.makeCurrent()
        vp.update()
        vp.grab(); pump(120)
    finally:
        GL.glUseProgram, GL.glDrawArrays, GL.glDrawElements = ou, oa, oe
    log("prog_line=%r prog_mesh=%r" % (vp._prog_line, vp._prog_mesh))
    log("calls=%d" % len(calls))
    for c in calls[:20]:
        log("  %r" % (c,))
    GLB = {0x0000: "POINTS", 0x0001: "LINES", 0x0004: "TRIANGLES", 0x0005: "TRIANGLE_STRIP"}
    for c in calls:
        log("   %s prog=%r %s count=%s" % (c[0], c[1], GLB.get(c[2], c[2]), c[-1]))
    H.dump()

def scen_grid_fb():
    import numpy as np
    import OpenGL.GL as GL
    from collections import Counter
    H.STATE["step"] = "gridfb"
    WIN._set_theme("light"); pump(200)
    WIN.close_model(); pump(200)
    vp = WIN.viewport

    def stats(tag, img):
        cnt = Counter()
        for y in range(0, img.height(), 2):
            for x in range(0, img.width(), 2):
                c = img.pixelColor(x, y)
                cnt[(c.red() // 32 * 32, c.green() // 32 * 32, c.blue() // 32 * 32)] += 1
        red = sum(v for k, v in cnt.items() if k[0] >= 192 and k[1] < 64 and k[2] < 64)
        yel = sum(v for k, v in cnt.items() if k[0] >= 192 and k[1] >= 192 and k[2] < 96)
        log("%-16s %dx%d red=%d yellow=%d top=%r" % (tag, img.width(), img.height(), red, yel, cnt.most_common(4)))

    stats("widget.grab", vp.grab().toImage())
    stats("grabFramebuffer", vp.grabFramebuffer())
    stats("window.grab", WIN.grab().toImage())
    # 在 draw 时读取颜色缓冲
    buf = {}
    oa = GL.glDrawArrays

    def da(mode, first, count):
        if count == len(vp._grid[0]):
            b = GL.glGetVertexAttribiv(1, GL.GL_VERTEX_ATTRIB_ARRAY_BUFFER_BINDING)[0]
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, b)
            raw = GL.glGetBufferSubData(GL.GL_ARRAY_BUFFER, 0, count * 12)
            arr = np.frombuffer(raw, np.float32).reshape(-1, 3)
            buf["id"] = b
            buf["uniq"] = sorted(set(map(tuple, np.round(arr, 3).tolist())))
        return oa(mode, first, count)

    GL.glDrawArrays = da
    try:
        vp.makeCurrent(); vp.update(); vp.grabFramebuffer()
    finally:
        GL.glDrawArrays = oa
    log("at-draw buffer id=%r uniq=%r" % (buf.get("id"), buf.get("uniq")))
    log("dpr=%r" % (vp.devicePixelRatioF(),))
    H.dump()

def scen_grid_green():
    import numpy as np
    import OpenGL.GL as GL
    from collections import Counter
    import viewport as V
    H.STATE["step"] = "gridgreen"
    WIN._set_theme("light"); pump(200)
    WIN.close_model(); pump(200)
    vp = WIN.viewport

    def stats(tag):
        img = vp.grabFramebuffer()
        cnt = Counter()
        for y in range(0, img.height(), 2):
            for x in range(0, img.width(), 2):
                c = img.pixelColor(x, y)
                cnt[(c.red() // 32 * 32, c.green() // 32 * 32, c.blue() // 32 * 32)] += 1
        red = sum(v for k, v in cnt.items() if k[0] >= 192 and k[1] < 64 and k[2] < 64)
        grn = sum(v for k, v in cnt.items() if k[1] >= 160 and k[0] < 96 and k[2] < 96)
        log("%-10s red=%d green=%d top=%r" % (tag, red, grn, cnt.most_common(4)))

    stats("palette")
    vp.makeCurrent()
    fs = "#version 120\nuniform float uAlpha;\nvoid main(){ gl_FragColor = vec4(0.0, 1.0, 0.0, uAlpha); }"
    old = vp._prog_line
    vp._prog_line = V._compile(V.LINE_VS, fs, {"aPos": 0, "aColor": 1})
    vp._loc["line"] = {k: GL.glGetUniformLocation(vp._prog_line, k) for k in ("uMVP", "uAlpha")}
    vp.doneCurrent()
    vp.update(); pump(250)
    stats("greenFS")
    vp.makeCurrent()
    GL.glDeleteProgram(vp._prog_line)
    vp._prog_line = old
    vp._loc["line"] = {k: GL.glGetUniformLocation(old, k) for k in ("uMVP", "uAlpha")}
    vp.doneCurrent()
    vp.update(); pump(250)
    stats("restored")
    H.dump()

def scen_grid_state():
    import numpy as np
    import OpenGL.GL as GL
    from collections import Counter
    H.STATE["step"] = "gridstate"
    WIN._set_theme("light"); pump(200)
    WIN.close_model(); pump(200)
    vp = WIN.viewport

    def stats(tag):
        img = vp.grabFramebuffer()
        cnt = Counter()
        for y in range(0, img.height(), 2):
            for x in range(0, img.width(), 2):
                c = img.pixelColor(x, y)
                cnt[(c.red() // 32 * 32, c.green() // 32 * 32, c.blue() // 32 * 32)] += 1
        red = sum(v for k, v in cnt.items() if k[0] >= 192 and k[1] < 64 and k[2] < 64)
        yel = sum(v for k, v in cnt.items() if k[0] >= 192 and k[1] >= 192 and k[2] < 96)
        log("%-22s red=%d yellow=%d top=%r" % (tag, red, yel, cnt.most_common(4)))

    stats("baseline")
    orig = vp._draw_grid

    def no_smooth(mvp):
        GL.glDisable(GL.GL_LINE_SMOOTH)
        GL.glDisable(GL.GL_MULTISAMPLE)
        try:
            return orig(mvp)
        finally:
            GL.glEnable(GL.GL_LINE_SMOOTH)
            GL.glEnable(GL.GL_MULTISAMPLE)

    vp._draw_grid = no_smooth
    vp.update(); pump(250)
    stats("no linesmooth/msaa")

    def no_blend(mvp):
        GL.glDisable(GL.GL_BLEND)
        try:
            return orig(mvp)
        finally:
            GL.glEnable(GL.GL_BLEND)
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)

    vp._draw_grid = no_blend
    vp.update(); pump(250)
    stats("no blend")

    def depth_off(mvp):
        GL.glDisable(GL.GL_DEPTH_TEST)
        try:
            return orig(mvp)
        finally:
            GL.glEnable(GL.GL_DEPTH_TEST)

    vp._draw_grid = depth_off
    vp.update(); pump(250)
    stats("no depth test")
    vp._draw_grid = orig
    vp.update(); pump(250)
    stats("restored")
    H.dump()

def scen_grid_state2():
    import numpy as np
    import OpenGL.GL as GL
    from collections import Counter
    H.STATE["step"] = "gridstate2"
    WIN._set_theme("light"); pump(200)
    WIN.close_model(); pump(200)
    vp = WIN.viewport
    vp.makeCurrent()
    log("VENDOR=%r" % (GL.glGetString(GL.GL_VENDOR),))
    log("RENDERER=%r" % (GL.glGetString(GL.GL_RENDERER),))
    log("VERSION=%r" % (GL.glGetString(GL.GL_VERSION),))
    log("SAMPLES=%r" % (GL.glGetIntegerv(GL.GL_SAMPLES),))
    vp.doneCurrent()

    def stats(tag, shot=False):
        img = vp.grabFramebuffer()
        cnt = Counter()
        for y in range(0, img.height(), 2):
            for x in range(0, img.width(), 2):
                c = img.pixelColor(x, y)
                cnt[(c.red() // 32 * 32, c.green() // 32 * 32, c.blue() // 32 * 32)] += 1
        red = sum(v for k, v in cnt.items() if k[0] >= 192 and k[1] < 64 and k[2] < 64)
        yel = sum(v for k, v in cnt.items() if k[0] >= 192 and k[1] >= 192 and k[2] < 96)
        log("%-20s red=%d yellow=%d top=%r" % (tag, red, yel, cnt.most_common(4)))
        if shot:
            img.save("tests/shots/gs2_%s.png" % tag.replace("/", "_"))

    stats("baseline", True)
    orig = vp._draw_grid

    def only_nosmooth(mvp):
        GL.glDisable(GL.GL_LINE_SMOOTH)
        try:
            return orig(mvp)
        finally:
            GL.glEnable(GL.GL_LINE_SMOOTH)

    vp._draw_grid = only_nosmooth
    vp.update(); pump(250)
    stats("no linesmooth", True)

    def only_nomsaa(mvp):
        GL.glDisable(GL.GL_MULTISAMPLE)
        try:
            return orig(mvp)
        finally:
            GL.glEnable(GL.GL_MULTISAMPLE)

    vp._draw_grid = only_nomsaa
    vp.update(); pump(250)
    stats("no msaa", True)
    vp._draw_grid = orig
    vp.update(); pump(250)
    stats("restored")

    # 宽度 2 像素是否也复现
    def wide(mvp):
        o = GL.glLineWidth
        GL.glDisable(GL.GL_LINE_SMOOTH)
        try:
            return orig(mvp)
        finally:
            GL.glEnable(GL.GL_LINE_SMOOTH)

    H.dump()

def scen_grid_green2():
    import numpy as np
    import OpenGL.GL as GL
    from collections import Counter
    H.STATE["step"] = "gridgreen2"
    WIN._set_theme("light"); pump(200)
    WIN.close_model(); pump(200)
    vp = WIN.viewport
    info = {}
    oa = GL.glDrawArrays

    def stats(tag):
        img = vp.grabFramebuffer()
        cnt = Counter()
        for y in range(int(img.height() * 0.35), img.height(), 2):
            for x in range(0, int(img.width() * 0.8), 2):
                c = img.pixelColor(x, y)
                cnt[(c.red() // 32 * 32, c.green() // 32 * 32, c.blue() // 32 * 32)] += 1
        log("%-12s top=%r" % (tag, cnt.most_common(5)))

    def da(mode, first, count):
        if mode == GL.GL_LINES and count == len(vp._grid[0]):
            b = GL.glGetVertexAttribiv(1, GL.GL_VERTEX_ATTRIB_ARRAY_BUFFER_BINDING)[0]
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, b)
            raw = GL.glGetBufferSubData(GL.GL_ARRAY_BUFFER, 0, count * 12)
            arr = np.frombuffer(raw, np.float32).reshape(-1, 3)
            info["before"] = sorted(set(map(tuple, np.round(arr, 2).tolist())))
            green = np.tile(np.array([0.0, 1.0, 0.0], np.float32), (count, 1))
            GL.glBufferSubData(GL.GL_ARRAY_BUFFER, 0, green.nbytes, green)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
            info["overwrote"] = True
        return oa(mode, first, count)

    stats("baseline")
    GL.glDrawArrays = da
    try:
        vp.update(); pump(250)
        vp.grabFramebuffer()
    finally:
        GL.glDrawArrays = oa
    log("before=%r overwrote=%r" % (info.get("before"), info.get("overwrote")))
    stats("green-bound")
    H.dump()

def scen_grid_final():
    import numpy as np
    import OpenGL.GL as GL
    from collections import Counter
    H.STATE["step"] = "gridfinal"
    WIN._set_theme("light"); pump(200)
    WIN.close_model(); pump(200)
    vp = WIN.viewport

    def stats(tag):
        img = vp.grabFramebuffer()
        c = Counter()
        for y in range(int(img.height() * 0.62), int(img.height() * 0.92)):
            for x in range(0, int(img.width() * 0.7)):
                c[img.pixelColor(x, y).getRgb()[:3]] += 1
        log("%-18s %r" % (tag, c.most_common(4)))

    stats("current(msaa off)")
    orig = vp._draw_grid

    def both(mvp):
        GL.glDisable(GL.GL_LINE_SMOOTH)
        try:
            return orig(mvp)
        finally:
            GL.glEnable(GL.GL_LINE_SMOOTH)

    vp._draw_grid = both
    vp.update(); pump(250)
    stats("+nosmooth")
    vp._draw_grid = orig

    # 检查预期色：0.75*a + 0.25*bg
    for name, c in (("minor", (0.78, 0.81, 0.85)), ("major", (0.65, 0.69, 0.75)),
                    ("X", (0.80, 0.35, 0.38)), ("Z", (0.38, 0.52, 0.75))):
        bg = (0.913, 0.929, 0.953)
        log("expect %-6s %r" % (name, [int(round((0.75 * c[i] + 0.25 * bg[i]) * 255)) for i in range(3)]))
    H.dump()

def scen_rows_fix():
    H.STATE["step"] = "rowsfix"
    if not WIN.doc.model:
        WIN.open_path(MODEL_PATH); pump(300)
    WIN._select_page(2); pump(300)
    mp = WIN._pages[2]
    lst = mp.list

    def probe(tag):
        w = lst.viewport().width()
        r = lst.visualRect(lst.model().index(0, 0))
        log("%-10s vw=%d roww=%d hbar=%s max=%d hint=%d" % (
            tag, w, r.width(), lst.horizontalScrollBar().isVisible(),
            lst.horizontalScrollBar().maximum(), lst.itemDelegate().width_hint))

    probe("1560")
    WIN.resize(1120, 700); pump(500)
    probe("1120")
    H.shot(WIN, "rowsfix_1120")
    WIN.resize(1560, 920); pump(500)
    probe("back")

    # 其它列表页也过一遍
    WIN._select_page(3); pump(250)
    lst = WIN._pages[3].list
    probe("morph")
    WIN._select_page(4); pump(250)
    lst = WIN._pages[4].list
    probe("rigid")
    H.shot(WIN, "rowsfix_phys")
    H.dump()


# ---------------------------------------------------------------- 场景：修复项回归
def scen_fix2():
    H.STATE["step"] = "fix2"
    WIN._select_page(1); pump(300)
    vp = WIN.viewport
    # 1) 点空白处取消选择
    WIN.doc.select("bone", 0); pump(200)
    QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, QPoint(8, 8))
    pump(250)
    log("deselect: sel=%s" % ((WIN.doc.sel_kind, WIN.doc.sel_index),))
    if WIN.doc.sel_kind:
        anomaly("deselect", "点视口空白处后选择未清除")
    # 2) 姿态模式仅单击不产生撤销
    WIN.set_physics(False); pump(300)
    hits = []
    for yy in range(60, vp.height() - 60, 14):
        for xx in range(30, vp.width() - 30, 14):
            k, i = vp.pick(xx, yy)
            if k == "bone":
                hits.append((xx, yy, i))
    log("bone hits=%d" % len(hits))
    if hits:
        hx, hy, idx = hits[len(hits) // 2]
        n0 = len(WIN.doc._undo)
        QTest.mouseClick(vp, Qt.LeftButton, Qt.NoModifier, QPoint(hx, hy))
        pump(350)
        n1 = len(WIN.doc._undo)
        log("pose click: undo %d -> %d status=%r" % (n0, n1, STATUS.text))
        if n1 > n0:
            anomaly("pose-click-undo", "只单击未拖动却压入撤销记录")
        if "姿态已更新" in STATUS.text:
            anomaly("pose-click-status", "只单击却提示姿态已更新")
    WIN.set_physics(False); pump(200)
    H.dump()


def scen_flag():
    H.STATE["step"] = "flag"
    WIN._select_page(2); pump(300)
    mp = WIN._pages[2]
    WIN.doc.select("material", 0); pump(300)
    mt = WIN.doc.model.materials[0]
    log("idx=%s mt=%r flags0=%s" % (mp.idx, getattr(mt, "name", None), mt.draw_flags))
    cb = mp.flags["ground"]
    log("cb visible=%s enabled=%s checked=%s" % (cb.isVisible(), cb.isEnabled(), cb.isChecked()))
    n0 = len(WIN.doc._undo); f0 = mt.draw_flags
    H.click(cb); pump(300)
    mt2 = WIN.doc.model.materials[0]
    log("after click: flags %s -> %s undo %d -> %d dirty=%s" % (f0, mt2.draw_flags, n0, len(WIN.doc._undo), WIN.doc.dirty))
    if mt2.draw_flags == f0:
        anomaly("flag-noop", "材质页取消勾选「地面阴影」后 draw_flags 未变化")
    H.shot(WIN, "flag_ground")
    H.dump()


def scen_flag2():
    H.STATE["step"] = "flag2"
    WIN._select_page(2); pump(300)
    mp = WIN._pages[2]
    WIN.doc.select("material", 0); pump(400)
    log("loading=%s idx=%s mt=%r" % (mp.loading, mp.idx, mp._material().name if mp._material() else None))
    cb = mp.flags["ground"]
    log("checked=%s" % cb.isChecked())
    cb.setChecked(False); pump(250)
    mt = WIN.doc.model.materials[0]
    log("setChecked(False) -> flags=%s undo=%d status=%r" % (mt.draw_flags, len(WIN.doc._undo), STATUS.text))
    mp.loading = False
    cb.setChecked(True); pump(250)
    mt = WIN.doc.model.materials[0]
    log("force loading=False, setChecked(True) -> flags=%s undo=%d status=%r" % (mt.draw_flags, len(WIN.doc._undo), STATUS.text))
    H.dump()


def scen_flag3():
    H.STATE["step"] = "flag3"
    WIN._select_page(2); pump(300)
    mp = WIN._pages[2]
    WIN.doc.select("material", 0); pump(400)
    for key in ("double", "ground", "edge"):
        cb = mp.flags[key]
        cb.setChecked(True); pump(120)
        gp = cb.mapToGlobal(cb.rect().center())
        hit = QApplication.widgetAt(gp)
        log("%s: geom=%s global=%s hit=%r checked=%s" % (key, cb.rect().getRect(), (gp.x(), gp.y()), desc(hit) if hit else None, cb.isChecked()))
    cb = mp.flags["ground"]
    f0 = WIN.doc.model.materials[0].draw_flags
    QTest.mouseClick(cb, Qt.LeftButton, Qt.NoModifier, cb.rect().center()); pump(300)
    log("qtest click -> checked=%s flags %s -> %s undo=%d" % (cb.isChecked(), f0, WIN.doc.model.materials[0].draw_flags, len(WIN.doc._undo)))
    H.dump()


def scen_flag4():
    H.STATE["step"] = "flag4"
    WIN._select_page(2); pump(300)
    mp = WIN._pages[2]
    WIN.doc.select("material", 0); pump(400)
    cb = mp.flags["ground"]
    log("before: checked=%s loading=%s geom=%s" % (cb.isChecked(), mp.loading, cb.rect().getRect()))
    d = H.click(cb); pump(250)
    log("H.click d=%.2f -> checked=%s loading=%s flags=%s undo=%d" % (d, cb.isChecked(), mp.loading, WIN.doc.model.materials[0].draw_flags, len(WIN.doc._undo)))
    H.shot(WIN, "flag4")
    H.dump()


def scen_flag5():
    H.STATE["step"] = "flag5"
    WIN._select_page(2); pump(300)
    mp = WIN._pages[2]
    WIN.doc.select("material", 0); pump(400)
    from PyQt5.QtWidgets import QScrollArea
    sa = mp.detail.parentWidget()
    while sa is not None and not isinstance(sa, QScrollArea):
        sa = sa.parentWidget()
    sb = sa.verticalScrollBar()
    log("scroll range %d..%d page=%d" % (sb.minimum(), sb.maximum(), sb.pageStep()))
    sb.setValue(sb.maximum()); pump(250)
    cb = mp.flags["ground"]
    gp = cb.mapToGlobal(cb.rect().center())
    log("after scroll: global=%s win=%s hit=%r checked=%s" % ((gp.x(), gp.y()), WIN.geometry().getRect(), desc(QApplication.widgetAt(gp)) if QApplication.widgetAt(gp) else None, cb.isChecked()))
    H.click(cb); pump(250)
    log("clicked -> checked=%s flags=%s undo=%d status=%r" % (cb.isChecked(), WIN.doc.model.materials[0].draw_flags, len(WIN.doc._undo), STATUS.text))
    H.shot(WIN, "flag5")
    H.dump()


def scen_flag6():
    H.STATE["step"] = "flag6"
    WIN._select_page(2); pump(300)
    mp = WIN._pages[2]
    WIN.doc.select("material", 0); pump(400)
    cb = mp.flags["ground"]
    seen = []

    from PyQt5.QtCore import QObject as _QO

    class F(_QO):
        def eventFilter(self, o, e):
            seen.append((e.type(), type(o).__name__))
            return False
    f = F()
    cb.installEventFilter(f)
    QTest.mouseClick(cb, Qt.LeftButton, Qt.NoModifier, cb.rect().center()); pump(200)
    log("qtest: checked=%s events=%s" % (cb.isChecked(), seen[:8]))
    seen.clear()
    cb.click(); pump(200)
    log("click(): checked=%s events=%s" % (cb.isChecked(), seen[:8]))
    log("attrs: enabled=%s visible=%s wa_transparent=%s hit=%s" % (
        cb.isEnabled(), cb.isVisible(), cb.testAttribute(Qt.WA_TransparentForMouseEvents),
        cb.hitButton(cb.rect().center())))
    H.dump()


def scen_flag7():
    H.STATE["step"] = "flag7"
    WIN._select_page(2); pump(300)
    mp = WIN._pages[2]
    WIN.doc.select("material", 0); pump(400)
    from PyQt5.QtWidgets import QStyle, QSizePolicy, QStyleOptionButton
    def clickrect(cb):
        opt = QStyleOptionButton()
        cb.initStyleOption(opt)
        return cb.style().subElementRect(QStyle.SE_CheckBoxClickRect, opt, cb)
    for key in ("double", "ground", "shadow", "map", "edge"):
        cb = mp.flags[key]
        cr = clickrect(cb)
        log("%s w=%d clickRect=%s center=%s hit=%s" % (key, cb.width(), cr.getRect(), cb.rect().center(), cb.hitButton(cb.rect().center())))
    cb = mp.flags["ground"]
    cb.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
    cb.updateGeometry(); mp.detail.layout().activate(); pump(250)
    log("after Maximum: w=%d clickRect=%s hit=%s" % (cb.width(), clickrect(cb).getRect(), cb.hitButton(cb.rect().center())))
    f0 = WIN.doc.model.materials[0].draw_flags
    QTest.mouseClick(cb, Qt.LeftButton, Qt.NoModifier, cb.rect().center()); pump(250)
    log("click -> checked=%s flags %s -> %s undo=%d status=%r" % (cb.isChecked(), f0, WIN.doc.model.materials[0].draw_flags, len(WIN.doc._undo), STATUS.text))
    H.dump()


def scen_flag8():
    H.STATE["step"] = "flag8"
    WIN._select_page(2); pump(300)
    mp = WIN._pages[2]
    WIN.doc.select("material", 0); pump(400)
    from PyQt5.QtWidgets import QStyle, QStyleOptionButton
    for key in ("double", "ground", "shadow", "map", "edge"):
        cb = mp.flags[key]
        opt = QStyleOptionButton(); cb.initStyleOption(opt)
        cr = cb.style().subElementRect(QStyle.SE_CheckBoxClickRect, opt, cb)
        f0 = WIN.doc.model.materials[0].draw_flags
        before = cb.isChecked()
        H.click(cb); pump(200)
        f1 = WIN.doc.model.materials[0].draw_flags
        log("%-6s w=%d clickRect=%d center=%d hit=%s checked %s->%s flags %d->%d"
            % (key, cb.width(), cr.width(), cb.rect().center().x(), cb.hitButton(cb.rect().center()), before, cb.isChecked(), f0, f1))
        if f0 == f1:
            anomaly("flag-click", "勾选「%s」后 draw_flags 未变化" % key)
    H.shot(WIN, "flag8")
    H.dump()


def scen_tree2():
    H.STATE["step"] = "tree2"
    WIN._select_page(1); pump(400)
    bp = WIN._pages[1]
    tree = bp.tree
    log("rows=%d" % tree._model.rowCount())
    root = tree._model.index(0, 0)
    log("expanded0=%s" % tree.isExpanded(root))
    tree.doubleClicked.emit(root); pump(200)
    log("after dbl emit: expanded0=%s" % tree.isExpanded(root))
    tree.doubleClicked.emit(root); pump(200)
    log("after 2nd: expanded0=%s" % tree.isExpanded(root))
    QTest.mouseDClick(tree.viewport(), Qt.LeftButton, Qt.NoModifier,
                      tree.visualRect(root).center()); pump(250)
    log("after real dclick: expanded0=%s" % tree.isExpanded(root))
    n = len(H.MENUS)
    tree.customContextMenuRequested.emit(tree.visualRect(root).center()); pump(250)
    log("menus %d -> %d last=%r" % (n, len(H.MENUS), H.MENUS[-1] if H.MENUS else None))
    H.dump()


def scen_empty():
    H.STATE["step"] = "empty"
    WIN._select_page(1); pump(300)
    bp = WIN._pages[1]
    bp.search.setText("zzz"); bp.search.changed.emit("zzz"); pump(300)
    H.shot(WIN, "empty_tree")
    WIN._select_page(2); pump(300)
    mp = WIN._pages[2]
    mp.search.setText("zzz"); mp.search.changed.emit("zzz"); pump(300)
    H.shot(WIN, "empty_list")
    WIN.close_model(); pump(400)
    WIN._select_page(1); pump(300)
    H.shot(WIN, "empty_nomodel")
    log("tree rows=%d text=%r" % (bp.tree._model.rowCount(), bp.tree.empty_text))
    log("list rows=%d text=%r" % (mp.list._model.rowCount(), mp.list.empty_text))
    H.dump()


def scen_fps():
    H.STATE["step"] = "fps"
    vp = WIN.viewport
    vp.update(); pump(200)
    log("busy fps=%.2f" % vp._fps)
    pump(4500)
    log("idle4.5s fps=%.2f skip=%s" % (vp._fps, vp._fps_skip))
    H.shot(WIN, "fps_idle")
    if vp._fps > 0.5:
        anomaly("fps-idle", "空闲 4.5 秒后 HUD 仍显示 %.1f FPS" % vp._fps)
    H.dump()


def scen_real():
    H.STATE["step"] = "real"
    m = WIN.doc.model
    log("verts=%d indices=%d tris=%d bones=%d mats=%d morphs=%d rigid=%d joints=%d tex=%d frames=%d" % (
        len(m.v_pos), len(m.indices), len(m.indices)//3, len(m.bones), len(m.materials),
        len(m.morphs), len(m.rigid), len(m.joints), len(m.textures), len(m.frames)))
    log("name=%r comment=%r version=%s enc=%s" % (m.name, m.comment[:40], m.version, m.encoding))
    log("status=%r title=%r" % (WIN.status_label.text(), WIN.windowTitle()))
    from pmxeditor import pmx as _pmx
    log("validate=%r" % (_pmx.validate_model(m),))
    log("cb=%d fps=%.1f" % (WIN.doc._undo.__len__(), WIN.viewport._fps))
    H.shot(WIN, "real_boot")
    t0 = time.time()
    WIN.doc.load(sys.argv[3])
    pump(300)
    log("reload to open: %.2fs" % (time.time() - t0))
    H.shot(WIN, "real_boot2")
    H.dump()


def scen_real2():
    H.STATE["step"] = "real2"
    doc, vp = WIN.doc, WIN.viewport
    log("pages=%d" % len(WIN._pages))
    for i in range(6):
        WIN._select_page(i)
        pump(350)
        H.shot(WIN, "real_p%d" % i)
    # 骨骼树
    WIN._select_page(1); pump(300)
    bp = WIN._pages[1]
    rows = bp.tree.model().rowCount() if bp.tree.model() else -1
    log("bone tree top rows=%s" % rows)
    bp.tree.expandAll(); pump(200)
    log("after expandAll rows=%s" % (bp.tree.model().rowCount() if bp.tree.model() else -1))
    # 材质列表
    WIN._select_page(2); pump(300)
    mp = WIN._pages[2]
    log("material list rows=%d idx=%s" % (mp.list.model().rowCount(), mp.idx))
    H.click(mp.list.viewport(), pos=mp.list.visualRect(mp.list.model().index(5, 0)).center())
    pump(200)
    log("after click row5 sel=%s idx=%s" % ((doc.sel_kind, doc.sel_index), mp.idx))
    H.shot(WIN, "real_mat5")
    # 形态列表
    WIN._select_page(3); pump(300)
    mop = WIN._pages[3]
    log("morph list rows=%d" % mop.list.model().rowCount())
    for r in (0, 1, 2, 5, 10):
        if mop.list.model().rowCount() > r:
            H.click(mop.list.viewport(), pos=mop.list.visualRect(mop.list.model().index(r, 0)).center())
            pump(120)
    log("morph sel=%s" % ((doc.sel_kind, doc.sel_index),))
    H.shot(WIN, "real_morph")
    # 物理页
    WIN._select_page(4); pump(300)
    pp = WIN._pages[4]
    log("rigid list rows=%d joints=%d" % (pp.list.model().rowCount(), len(doc.model.joints)))
    H.shot(WIN, "real_phys")
    # 视口拾取
    WIN._select_page(0); pump(200)
    c = vp.rect().center()
    hit = None
    for dx in range(-40, 41, 8):
        r = vp.pick(c.x() + dx, c.y())
        if r: hit = (dx, r); break
    log("pick center -> %r" % (hit,))
    H.dump()


def scen_real3():
    H.STATE["step"] = "real3"
    import numpy as np
    doc, vp = WIN.doc, WIN.viewport
    m = doc.model
    from pmxeditor import pmx
    out = os.path.join(H.ROOT, "tests", "miya_out.pmx")
    try:
        t0 = time.time(); doc.save(out); dt = time.time() - t0
        log("save %.2fs -> %d bytes (src %d)" % (dt, os.path.getsize(out), os.path.getsize(sys.argv[3])))
    except Exception:
        anomaly("save", traceback.format_exc())
    try:
        t0 = time.time(); m2 = pmx.load_pmx(out); dt = time.time() - t0
        log("reload %.2fs" % dt)
        for k in ("v_pos", "indices", "bones", "materials", "morphs", "rigid", "joints", "textures", "frames"):
            a, b = getattr(m, k), getattr(m2, k)
            log("  %-10s %6d -> %6d %s" % (k, len(a), len(b), "OK" if len(a) == len(b) else "DIFF"))
        log("  validate=%r" % (pmx.validate_model(m2),))
        a = np.array(m.v_pos, dtype="f4"); b = np.array(m2.v_pos, dtype="f4")
        log("  v_pos maxdiff=%.6f  uv maxdiff=%.6f" % (float(np.abs(a - b).max()),
            float(np.abs(np.array(m.v_uv, dtype="f4") - np.array(m2.v_uv, dtype="f4")).max())))
    except Exception:
        anomaly("roundtrip", traceback.format_exc())
    # 帧耗时
    try:
        for _ in range(2):
            vp.repaint()
        n = 12
        t0 = time.perf_counter()
        for _ in range(n):
            vp.repaint()
        ms = (time.perf_counter() - t0) / n * 1000
        log("frame avg %.1f ms (%.1f fps)" % (ms, 1000.0 / ms))
        if ms > 100:
            anomaly("perf", "79848 顶点模型单帧 %.0f ms" % ms)
    except Exception:
        anomaly("perf", traceback.format_exc())
    # 形态预览
    try:
        WIN._select_page(3); pump(250)
        mop = WIN._pages[3]
        lst = mop.list
        hit = 0
        for r in range(min(lst.model().rowCount(), 12)):
            idx = lst.model().index(r, 0)
            lst.scrollTo(idx)
            pump(80)
            H.click(lst.viewport(), pos=lst.visualRect(idx).center())
            pump(120)
            if (doc.sel_kind, doc.sel_index) == ("morph", r):
                hit += 1
        log("morph click hit %d/12 sel=%s" % (hit, (doc.sel_kind, doc.sel_index)))
        H.shot(WIN, "real_morph2")
    except Exception:
        anomaly("morph", traceback.format_exc())
    H.dump()


def scen_real4():
    H.STATE["step"] = "real4"
    doc, vp = WIN.doc, WIN.viewport
    # 1) 形态预览滑杆
    try:
        WIN._select_page(3); pump(250)
        mop = WIN._pages[3]
        lst = mop.list
        idx = lst.model().index(0, 0); lst.scrollTo(idx); pump(80)
        H.click(lst.viewport(), pos=lst.visualRect(idx).center()); pump(150)
        log("morph idx=%s name=%r w=%s" % (mop.idx, doc.model.morphs[mop.idx].name, mop.weight.value()))
        before = H.raw(WIN)
        mop.weight.setValue(100); pump(250)
        d1 = H.pixdiff(WIN, before)
        log("weight=100 -> pix %.2f%% status=%r" % (d1, WIN.status_label.text()))
        H.shot(WIN, "real_morph_prev")
        if d1 < 0.05:
            anomaly("morph-preview", "形态预览拉到 100%% 后画面只变了 %.2f%%" % d1)
        mop.weight.setValue(0); pump(200)
        log("weight=0 -> pix %.2f%%" % H.pixdiff(WIN, before))
    except Exception:
        anomaly("morph", traceback.format_exc())
    # 2) 姿态模式拖骨骼
    try:
        WIN.set_physics(False); pump(300)
        c = vp.rect().center()
        hit = None
        for dx in range(-200, 201, 10):
            for dy in (-150, -80, 0, 60):
                r = vp.pick(c.x() + dx, c.y() + dy)
                if r and r[0] == "bone":
                    hit = (c.x() + dx, c.y() + dy, r); break
            if hit: break
        log("pose pick -> %r" % (hit,))
        if hit:
            before = H.raw(WIN)
            u0 = len(doc._undo)
            t0 = time.perf_counter()
            QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, QPoint(hit[0], hit[1]))
            for k in range(1, 9):
                QTest.mouseMove(vp, QPoint(hit[0] + k * 4, hit[1]))
                pump(20)
            QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, QPoint(hit[0] + 32, hit[1]))
            pump(200)
            ms = (time.perf_counter() - t0) * 1000
            d = H.pixdiff(WIN, before)
            log("pose drag %.0fms pix %.2f%% undo %d->%d status=%r" % (ms, d, u0, len(doc._undo), WIN.status_label.text()))
            H.shot(WIN, "real_pose")
            if d < 0.05:
                anomaly("pose-drag", "拖动骨骼后画面只变了 %.2f%%" % d)
            t0 = time.time(); WIN.doc.undo(); pump(300)
            log("undo %.2fs -> pose restored? pix %.2f%%" % (time.time() - t0, H.pixdiff(WIN, before)))
    except Exception:
        anomaly("pose", traceback.format_exc())
    # 3) 物理模式
    try:
        t0 = time.time(); WIN.set_physics(True); pump(500)
        log("physics mode in %.2fs enabled=%s" % (time.time() - t0, vp.physics.enabled))
        p0 = [tuple(round(v, 3) for v in b.position) for b in []] 
        n0 = vp.physics.frame if hasattr(vp.physics, "frame") else -1
        pump(1500)
        log("after 1.5s physics status=%r" % WIN.status_label.text())
        vp.repaint()
        log("physics fps=%.1f" % vp._fps)
        H.shot(WIN, "real_physics")
        WIN.set_physics(False); pump(300)
    except Exception:
        anomaly("physics", traceback.format_exc())
    H.dump()


def scen_real5():
    H.STATE["step"] = "real5"
    import numpy as np
    doc, vp = WIN.doc, WIN.viewport
    WIN.set_physics(False); pump(300)
    c = vp.rect().center()
    hit = None
    for dx in range(-200, 201, 10):
        for dy in (-150, -80, 0, 60):
            r = vp.pick(c.x() + dx, c.y() + dy)
            if r and r[0] == "bone":
                hit = (c.x() + dx, c.y() + dy, r); break
        if hit: break
    log("pick=%r" % (hit,))
    r0 = vp.pose.base_rot.copy(); t0 = vp.pose.base_trans.copy()
    log("rot0 nonzero=%d" % int((np.abs(r0 - np.array([0, 0, 0, 1], "f4")).sum(1) > 1e-6).sum()))
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, QPoint(hit[0], hit[1]))
    for k in range(1, 9):
        QTest.mouseMove(vp, QPoint(hit[0] + k * 4, hit[1] + k))
        pump(20)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, QPoint(hit[0] + 32, hit[1] + 8))
    pump(250)
    r1 = vp.pose.base_rot.copy()
    log("after drag maxdiff=%.4f undo=%d" % (float(np.abs(r1 - r0).max()), len(doc._undo)))
    pix_after = H.raw(WIN)
    doc.undo(); pump(400)
    r2 = vp.pose.base_rot.copy()
    log("after undo maxdiff_vs_orig=%.4f  maxdiff_vs_drag=%.4f  undo=%d redo=%d" % (
        float(np.abs(r2 - r0).max()), float(np.abs(r2 - r1).max()), len(doc._undo), len(doc._redo)))
    log("pix undo vs drag = %.2f%%" % H.pixdiff(WIN, pix_after))
    H.shot(WIN, "real_undo_pose")
    # 再试一次：undo 后重新 select 同一骨骼，看面板数值是否回到原值
    log("sel=%s status=%r" % ((doc.sel_kind, doc.sel_index), WIN.status_label.text()))
    H.dump()


def scen_real6():
    H.STATE["step"] = "real6"
    import numpy as np
    doc, vp = WIN.doc, WIN.viewport
    WIN.set_physics(False); pump(400)
    c = vp.rect().center()
    hit = None
    for dx in range(-200, 201, 10):
        for dy in (-150, -80, 0, 60):
            r = vp.pick(c.x() + dx, c.y() + dy)
            if r and r[0] == "bone":
                hit = (c.x() + dx, c.y() + dy, r); break
        if hit: break
    b = hit[2][1]
    log("bone=%d" % b)
    A = H.raw(WIN)
    rot0 = vp.pose.rot.copy()
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, QPoint(hit[0], hit[1]))
    for k in range(1, 13):
        QTest.mouseMove(vp, QPoint(hit[0] + k * 6, hit[1] + k))
        pump(15)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, QPoint(hit[0] + 72, hit[1] + 12))
    pump(400)
    B = H.raw(WIN)
    rot1 = vp.pose.rot.copy()
    log("drag: rot[%d]=%s  rotdiff=%.4f  ov=%d" % (b, np.round(rot1[b], 3), float(np.abs(rot1 - rot0).max()), len(vp.pose.ov_rot)))
    log("pix A->B = %.2f%%" % H.pixdiff(WIN, A))
    doc.undo(); pump(500)
    C = H.raw(WIN)
    rot2 = vp.pose.rot.copy()
    log("undo: rot[%d]=%s rotdiff_vs_orig=%.4f" % (b, np.round(rot2[b], 3), float(np.abs(rot2 - rot0).max())))
    log("pix B->C = %.2f%%   A->C = %.2f%%" % (H.pixdiff(WIN, B), H.pixdiff(WIN, A)))
    log("dirty: %s pose_dirty=%s force_full=%s" % (vp._dirty, vp._pose_dirty, vp._skin_force_full))
    H.shot(WIN, "real_undo_c")
    H.dump()


def scen_real7():
    H.STATE["step"] = "real7"
    import numpy as np
    doc, vp = WIN.doc, WIN.viewport
    WIN.set_physics(False); pump(400)
    c = vp.rect().center()
    hit = None
    for dx in range(-200, 201, 10):
        for dy in (-150, -80, 0, 60):
            r = vp.pick(c.x() + dx, c.y() + dy)
            if r and r[0] == "bone":
                hit = (c.x() + dx, c.y() + dy, r); break
        if hit: break
    A = vp._skin_pos.copy()
    QTest.mousePress(vp, Qt.LeftButton, Qt.NoModifier, QPoint(hit[0], hit[1]))
    for k in range(1, 13):
        QTest.mouseMove(vp, QPoint(hit[0] + k * 6, hit[1] + k))
        pump(15)
    QTest.mouseRelease(vp, Qt.LeftButton, Qt.NoModifier, QPoint(hit[0] + 72, hit[1] + 12))
    pump(400)
    B = vp._skin_pos.copy()
    log("drag skin maxdiff=%.4f" % float(np.abs(B - A).max()))
    doc.undo(); pump(500)
    C = vp._skin_pos.copy()
    log("undo skin: vs_A=%.5f vs_B=%.5f" % (float(np.abs(C - A).max()), float(np.abs(C - B).max())))
    log("pose.rot vs A? rot restored all-zero=%s" % bool((np.abs(vp.pose.rot - np.array([0,0,0,1],'f4')).sum(1) > 1e-6).sum() == 0))
    # 强制改成 browse 再回 pose，看画面是否恢复
    WIN.set_physics(False); pump(300)
    WIN.set_physics(False); pump(300)
    D = vp._skin_pos.copy()
    log("mode roundtrip skin vs_A=%.5f" % float(np.abs(D - A).max()))
    log("pix now vs A = %.2f%%" % H.pixdiff(WIN, A and H.raw(WIN)))
    H.dump()


def scen_real8():
    H.STATE["step"] = "real8"
    import numpy as np
    doc, vp = WIN.doc, WIN.viewport
    m = doc.model
    # 1) 编辑骨骼：改名 + 改位置，测耗时
    WIN._select_page(1); pump(300)
    bp = WIN._pages[1]
    doc.select("bone", 11); pump(200)
    log("bone11=%r pos=%s" % (m.bones[11].name, np.round(m.bones[11].pos, 3)))
    old = m.bones[11].pos[0]
    t0 = time.perf_counter()
    bp.pos_spin.spins[0].setValue(old + 0.5); pump(200)
    dt = (time.perf_counter() - t0) * 1000
    log("pos edit %.0fms -> %s undo=%d dirty=%s status=%r" % (
        dt, np.round(doc.model.bones[11].pos, 3), len(doc._undo), doc.dirty, WIN.status_label.text()))
    if dt > 400:
        anomaly("edit-slow", "改一个骨骼坐标耗时 %.0f ms（撤销栈深拷贝 8 万顶点模型）" % dt)
    t0 = time.perf_counter(); doc.undo(); pump(200)
    log("undo %.0fms -> %s" % ((time.perf_counter() - t0) * 1000, np.round(doc.model.bones[11].pos, 3)))
    # 2) 材质改色（P0-1 真机回归）
    WIN._select_page(2); pump(250)
    mp = WIN._pages[2]
    doc.select("material", 0); pump(200)
    before = list(doc.model.materials[0].diffuse)
    H.click(mp.diffuse)
    pump(300)
    after = list(doc.model.materials[0].diffuse)
    log("diffuse %r -> %r len=%d anom=%d" % (before[:3], after[:4], len(after), len(H.ANOM)))
    vp.repaint(); pump(100)
    log("viewport alive after color change: %s" % bool(vp._mesh))
    doc.undo(); pump(200)
    log("diffuse after undo=%r" % (list(doc.model.materials[0].diffuse)[:4],))
    # 3) 贴图缓存
    try:
        log("tex cache=%d textures=%d" % (len(vp._tex_cache), len(m.textures)))
        missing = [t for t in m.textures if not os.path.exists(os.path.join(os.path.dirname(m.path), t.replace("\\", "/")))]
        log("missing texture files=%r" % (missing[:5],))
    except Exception:
        anomaly("texture", traceback.format_exc())
    H.dump()


def scen_real9():
    H.STATE["step"] = "real9"
    import copy, numpy as np
    doc = WIN.doc
    m = doc.model
    for k in ("v_pos", "v_nrm", "v_uv", "v_edge", "v_bones", "v_weights", "indices"):
        a = getattr(m, k)
        log("%-8s type=%s len=%d" % (k, type(a).__name__, len(a)))
    t0 = time.perf_counter(); c = copy.deepcopy(m); dt = time.perf_counter() - t0
    log("deepcopy whole model %.0f ms" % (dt * 1000))
    for k in ("v_pos", "indices", "materials", "bones", "morphs", "rigid", "joints"):
        a = getattr(m, k)
        t0 = time.perf_counter(); copy.deepcopy(a); d1 = (time.perf_counter() - t0) * 1000
        log("  copy %-10s %7.1f ms (%s)" % (k, d1, type(a).__name__))
    t0 = time.perf_counter(); doc.push_undo("probe"); dt = time.perf_counter() - t0
    log("push_undo %.0f ms (undo=%d)" % (dt * 1000, len(doc._undo)))
    H.dump()


def scen_real10():
    H.STATE["step"] = "real10"
    doc, vp = WIN.doc, WIN.viewport
    t0 = time.perf_counter(); WIN._reload_structure(); pump(50)
    log("_reload_structure %.0f ms" % ((time.perf_counter() - t0) * 1000))
    t0 = time.perf_counter(); vp.rebuild_physics(); pump(50)
    log("rebuild_physics %.0f ms" % ((time.perf_counter() - t0) * 1000))
    for i in (1, 2, 3, 4, 5):
        t0 = time.perf_counter(); WIN._select_page(i); pump(20)
        log("select page %d: %.0f ms" % (i, (time.perf_counter() - t0) * 1000))
    t0 = time.perf_counter(); WIN._pages[1].refresh(); log("bone page refresh %.0f ms" % ((time.perf_counter() - t0) * 1000))
    t0 = time.perf_counter(); WIN._pages[2].refresh(); log("material page refresh %.0f ms" % ((time.perf_counter() - t0) * 1000))
    t0 = time.perf_counter(); WIN._pages[3].refresh(); log("morph page refresh %.0f ms" % ((time.perf_counter() - t0) * 1000))
    t0 = time.perf_counter(); WIN._pages[4].refresh(); log("physics page refresh %.0f ms" % ((time.perf_counter() - t0) * 1000))
    t0 = time.perf_counter(); WIN._refresh_pages(); log("_refresh_pages all %.0f ms" % ((time.perf_counter() - t0) * 1000))
    # 显示开关的像素与耗时
    vp.show_bones = True; t0 = time.perf_counter(); vp.repaint(); ms1 = (time.perf_counter() - t0) * 1000
    vp.show_rigid = True; t0 = time.perf_counter(); vp.repaint(); ms2 = (time.perf_counter() - t0) * 1000
    vp.show_joints = True; t0 = time.perf_counter(); vp.repaint(); ms3 = (time.perf_counter() - t0) * 1000
    log("repaint base %.1f ms  +rigid %.1f  +joints %.1f" % (ms1, ms2, ms3))
    vp.show_bones = vp.show_rigid = vp.show_joints = False
    H.shot(WIN, "real_p5")
    H.dump()


def scen_real11():
    H.STATE["step"] = "real11"
    import cProfile, pstats, io
    pr = cProfile.Profile()
    pr.enable(); WIN._reload_structure(); pr.disable()
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
    ps.print_stats(22)
    for line in s.getvalue().splitlines():
        if line.strip() and not line.startswith("   Ordered") and "ncalls" not in line:
            log("P| " + line[:150])
    H.dump()


def scen_real12():
    H.STATE["step"] = "real12"
    doc, vp = WIN.doc, WIN.viewport
    for i in range(3):
        t0 = time.perf_counter(); WIN._reload_structure()
        log("reload #%d alone: %.0f ms" % (i, (time.perf_counter() - t0) * 1000))
        t0 = time.perf_counter(); pump(120)
        log("   pump120 after: %.0f ms" % ((time.perf_counter() - t0) * 1000))
    bp = WIN._pages[1]
    WIN._select_page(1)
    old = float(doc.model.bones[11].position[1])
    for i in range(3):
        t0 = time.perf_counter()
        bp.pos_spin.spins[1].setValue(old + 0.1)
        t1 = time.perf_counter()
        pump(150)
        t2 = time.perf_counter()
        log("edit#%d setValue %.0f ms pump %.0f ms  total %.0f" % (i, (t1 - t0) * 1000, (t2 - t1) * 1000, (t2 - t0) * 1000))
        doc.undo(); pump(150)
    t0 = time.perf_counter(); doc.undo(); t1 = time.perf_counter()
    log("undo alone: %.0f ms" % ((t1 - t0) * 1000))
    H.dump()


def scen_real13():
    H.STATE["step"] = "real13"
    doc, vp = WIN.doc, WIN.viewport
    for i in range(3):
        t0 = time.perf_counter(); WIN._reload_structure()
        t1 = time.perf_counter(); vp.repaint()
        log("reload %-2d: %.0f ms  first paint: %.0f ms" % (i, (t1 - t0) * 1000, (time.perf_counter() - t1) * 1000))
    vp.repaint()
    log("tex_cache entries=%d" % len(vp._tex_cache))
    H.shot(WIN, "real_texcache")
    # 换贴图后必须刷新（缓存键含路径）
    mp = WIN._pages[2]; WIN._select_page(2)
    m = doc.model
    log("mat0 tex=%d mat1 tex=%d" % (m.materials[0].texture, m.materials[1].texture))
    old = m.materials[0].texture
    cb = mp.tex_combo
    n = cb.count()
    cb.setCurrentIndex((old + 1) % n); pump(120)
    vp.repaint()
    log("after combo: mat0 tex=%s cache=%d" % (str(doc.model.materials[0].texture), len(vp._tex_cache)))
    H.shot(WIN, "real_texswap")
    H.dump()


def scen_real14():
    H.STATE["step"] = "real14"
    doc, vp = WIN.doc, WIN.viewport
    WIN._select_page(2)
    mp = WIN._pages[2]
    mp.doc.select("material", 0); pump(60)
    cb = mp.tex_combo
    log("idx=%s count=%d cur=%d data=%s" % (mp.idx, cb.count(), cb.currentIndex(), cb.currentData()))
    for i in range(min(4, cb.count())):
        log("  item[%d]=%s data=%s" % (i, cb.itemText(i), cb.itemData(i)))
    before = doc.model.materials[0].texture
    cb.setCurrentIndex(2); pump(120)
    log("mat0 tex %s -> %s  status=%s" % (before, doc.model.materials[0].texture, WIN.status_label.text()))
    vp.repaint()
    log("cache=%d" % len(vp._tex_cache))
    H.shot(WIN, "real_texswap")
    H.dump()


def scen_real15():
    H.STATE["step"] = "real15"
    doc, vp = WIN.doc, WIN.viewport
    WIN._select_page(2)
    mp = WIN._pages[2]
    mp.doc.select("material", 1); pump(80)
    before = H.raw(WIN)
    log("mat1 name=%s tex=%s cur=%d" % (doc.model.materials[1].name, doc.model.materials[1].texture, mp.tex_combo.currentIndex()))
    mp.tex_combo.setCurrentIndex(mp.tex_combo.currentIndex() + 1); pump(120); vp.repaint(); pump(60)
    log("tex now=%s  pixdiff=%.2f%%" % (doc.model.materials[1].texture, H.pixdiff(WIN, before)))
    doc.undo(); pump(150); vp.repaint(); pump(60)
    log("after undo tex=%s  pixdiff=%.2f%%  status=%s" % (doc.model.materials[1].texture,
        H.pixdiff(WIN, before), WIN.status_label.text()))
    t0 = time.perf_counter(); WIN._reload_structure(); t1 = time.perf_counter()
    vp.repaint(); t2 = time.perf_counter()
    log("edit path: reload %.0f + paint %.0f = %.0f ms" % ((t1-t0)*1000, (t2-t1)*1000, (t2-t0)*1000))
    H.dump()


def scen_real16():
    H.STATE["step"] = "real16"
    doc, vp = WIN.doc, WIN.viewport
    WIN._select_page(2)
    mp = WIN._pages[2]
    mp.doc.select("material", 1); pump(60)
    cb = mp.tex_combo
    for i in range(2):
        t0 = time.perf_counter()
        cb.setCurrentIndex(cb.currentIndex() + 1)
        t1 = time.perf_counter(); vp.repaint(); t2 = time.perf_counter()
        log("edit#%d: emit %.0f ms + paint %.0f = %.0f ms" % (i, (t1-t0)*1000, (t2-t1)*1000, (t2-t0)*1000))
        t0 = time.perf_counter(); doc.undo(); t1 = time.perf_counter(); vp.repaint(); t2 = time.perf_counter()
        log("   undo: %.0f + paint %.0f = %.0f ms" % ((t1-t0)*1000, (t2-t1)*1000, (t2-t0)*1000))
    H.dump()


def scen_real17():
    H.STATE["step"] = "real17"
    doc, vp = WIN.doc, WIN.viewport
    WIN._select_page(2)
    mp = WIN._pages[2]
    mp.doc.select("material", 1); pump(60)
    cb = mp.tex_combo
    log("cache=%d" % len(vp._tex_cache))
    for data, tag in ((0, "已缓存"), (5, "未缓存"), (5, "已缓存"), (0, "已缓存")):
        i = cb.findData(data)
        t0 = time.perf_counter(); cb.setCurrentIndex(i); t1 = time.perf_counter()
        vp.repaint(); t2 = time.perf_counter()
        log("-> tex %d (%s): %.0f ms" % (data, tag, (t2 - t1) * 1000))
    H.dump()


def scen_real18():
    H.STATE["step"] = "real18"
    import cProfile, pstats, io
    doc, vp = WIN.doc, WIN.viewport
    WIN._select_page(2)
    mp = WIN._pages[2]
    mp.doc.select("material", 1); pump(60)
    cb = mp.tex_combo
    cb.setCurrentIndex(cb.findData(0)); vp.repaint()
    t0 = time.perf_counter()
    cb.setCurrentIndex(cb.findData(5)); vp.repaint()
    log("repeat switch %.0f ms" % ((time.perf_counter() - t0) * 1000))
    pr = cProfile.Profile()
    cb.setCurrentIndex(cb.findData(0))
    pr.enable(); vp.repaint(); pr.disable()
    s = io.StringIO(); pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(14)
    for line in s.getvalue().splitlines():
        if line.strip() and "ncalls" not in line and not line.startswith("   Ordered") and not line.startswith("         List"):
            log("P| " + line[:140])
    H.dump()


def scen_real19():
    H.STATE["step"] = "real19"
    doc, vp = WIN.doc, WIN.viewport
    WIN._select_page(2)
    mp = WIN._pages[2]
    mp.doc.select("material", 1); pump(80)
    cb = mp.tex_combo
    A = H.raw(WIN)
    log("start tex=%s cache=%d" % (doc.model.materials[1].texture, len(vp._tex_cache)))
    for d in (11, 6):
        t0 = time.perf_counter(); cb.setCurrentIndex(cb.findData(d)); vp.repaint()
        log("-> tex %d: %.0f ms  pixdiff vs A = %.2f%%" % (d, (time.perf_counter() - t0) * 1000, H.pixdiff(WIN, A)))
        H.shot(WIN, "real_tex%d" % d)
        doc.undo(); vp.repaint()
        log("   undo: pixdiff vs A = %.2f%%  tex=%s cache=%d" % (H.pixdiff(WIN, A), doc.model.materials[1].texture, len(vp._tex_cache)))
    t0 = time.perf_counter(); WIN._reload_structure(); vp.repaint()
    log("structure reload+paint %.0f ms  tex=%s cache=%d" % ((time.perf_counter() - t0) * 1000, doc.model.materials[1].texture, len(vp._tex_cache)))
    log("final pixdiff vs A = %.2f%%" % H.pixdiff(WIN, A))
    H.dump()


def scen_real20():
    H.STATE["step"] = "real20"
    doc, vp = WIN.doc, WIN.viewport
    WIN._select_page(2)
    mp = WIN._pages[2]
    mp.doc.select("material", 1); pump(80)
    cb = mp.tex_combo
    A = H.raw(WIN)
    base = doc.model.materials[1].texture
    best = (0, -1)
    for d in range(12):
        if d == base:
            continue
        cb.setCurrentIndex(cb.findData(d)); vp.repaint()
        pd = H.pixdiff(WIN, A)
        log("tex %2d %-14s pixdiff %.2f%%" % (d, doc.model.resolve_texture(d).split("\\")[-1], pd))
        if pd > best[0]:
            best = (pd, d); H.shot(WIN, "real_best_tex")
        doc.undo(); vp.repaint()
        if abs(H.pixdiff(WIN, A)) > 0.5:
            log("!! undo failed to restore: %.2f%%" % H.pixdiff(WIN, A))
    log("max diff tex=%s (%.2f%%)" % (best[1], best[0]))
    log("final restore diff %.2f%%" % H.pixdiff(WIN, A))
    H.dump()


def scen_real21():
    H.STATE["step"] = "real21"
    doc, vp = WIN.doc, WIN.viewport
    WIN._select_page(2)
    mp = WIN._pages[2]
    mp.doc.select("material", 1); pump(150)
    cb = mp.tex_combo
    H.shot(WIN, "t_base")
    cb.setCurrentIndex(cb.findData(0)); pump(250); H.shot(WIN, "t_swap")
    doc.undo(); pump(250); H.shot(WIN, "t_back")
    cb.setCurrentIndex(cb.findData(0)); pump(250); H.shot(WIN, "t_swap2")
    log("tex now=%s" % doc.model.materials[1].texture)
    H.dump()


def scen_real22():
    H.STATE["step"] = "real22"
    doc, vp = WIN.doc, WIN.viewport
    WIN._select_page(2)
    mp = WIN._pages[2]
    mp.doc.select("material", 0); pump(100)
    H.shot(WIN, "c_base")
    doc.model.materials[0].diffuse = [1.0, 0.0, 0.0, 1.0]
    vp.repaint(); pump(200)
    H.shot(WIN, "c_red")
    doc.model.materials[0].diffuse = [1.0, 1.0, 1.0, 1.0]
    vp.repaint(); pump(200)
    mp.doc.select("material", 1); pump(100)
    H.shot(WIN, "c_base2")
    doc.model.materials[1].texture = 2
    vp.repaint(); pump(200)
    H.shot(WIN, "c_tex2")
    log("done")
    H.dump()


def scen_real23():
    H.STATE["step"] = "real23"
    doc, vp = WIN.doc, WIN.viewport
    vp.repaint(); pump(150)
    H.shot(WIN, "all_base")
    for mt in doc.model.materials:
        mt.diffuse = [1.0, 0.0, 0.0, 1.0]
    vp.repaint(); pump(300)
    H.shot(WIN, "all_red")
    log("painted")
    H.dump()


def scen_real24():
    H.STATE["step"] = "real24"
    doc, vp = WIN.doc, WIN.viewport
    vp.repaint(); pump(150); H.shot(WIN, "m_base")
    mt = doc.model.materials[1]
    log("mat1 %s tex=%s diff=%s faces=%s" % (mt.name, mt.texture, mt.diffuse[:3], mt.face_count))
    mt.diffuse = [1.0, 0.0, 0.0, 1.0]
    vp.repaint(); pump(250); H.shot(WIN, "m_red")
    mt.diffuse = [0.8, 0.8, 0.8, 1.0]
    mt.texture = 2
    vp.repaint(); pump(250); H.shot(WIN, "m_tex2")
    log("tex now=%s path=%s" % (mt.texture, doc.model.resolve_texture(2)))
    H.dump()


def scen_real25():
    H.STATE["step"] = "real25"
    doc, vp = WIN.doc, WIN.viewport
    vp.repaint(); pump(120)
    base = H.raw(WIN)
    mats = doc.model.materials
    for i, mt in enumerate(mats):
        old = list(mt.diffuse)
        mt.diffuse = [1.0, 0.0, 0.0, 1.0]
        vp.repaint()
        log("%2d %-10s faces=%-5d diff=%.2f%%" % (i, mt.name, mt.face_count, H.pixdiff(WIN, base)))
        mt.diffuse = old
    vp.repaint()
    H.dump()


def scen_real26():
    H.STATE["step"] = "real26"
    doc, vp = WIN.doc, WIN.viewport
    vp.repaint(); pump(120); H.shot(WIN, "x_base")
    base = H.raw(WIN)
    for mt in doc.model.materials:
        mt.texture = 2
    vp.repaint(); pump(150); H.shot(WIN, "x_tex2")
    log("all materials -> tex 2: diff %.2f%%" % H.pixdiff(WIN, base))
    for mt in doc.model.materials:
        mt.texture = 0
    vp.repaint(); pump(150)
    log("all -> tex 0: diff %.2f%%" % H.pixdiff(WIN, base))
    log("cache=%d" % len(vp._tex_cache))
    H.dump()



def scen_sync():
    """2026-10-23 进度同步：VPD 导入/导出 + 状态记录。"""
    H.STATE["step"] = "sync"
    import numpy as np
    from pmxeditor import vpd as vpdmod
    from PyQt5.QtWidgets import QMessageBox as MB

    doc, vp = WIN.doc, WIN.viewport
    m = doc.model
    log("model: %d verts / %d bones / %d mats / %d morphs / %d rigid / %d joints"
        % (m.n_vertices, m.n_bones, len(m.materials), len(m.morphs),
           len(m.rigid), len(m.joints)))

    texts = []
    for a in WIN.menubar.actions():
        menu = a.menu()
        if menu is not None:
            texts += [x.text() for x in menu.actions()]
    log("VPD menu items: %s" % [t for t in texts if "VPD" in t])

    orig_exec = MB.exec_
    def fake_exec(self):
        H.DIALOGS.append({"kind": "QMessageBox.exec_", "window": self.windowTitle(),
                          "text": self.text()[:120]})
        return MB.Ok
    MB.exec_ = fake_exec

    names, seen = [], set()
    for b in m.bones:
        n = (b.name or "").strip()
        if n and n not in seen:
            seen.add(n)
            names.append(n)
        if len(names) >= 5:
            break
    lines = ["Vocaloid Pose Data file ( sync.pmx )", ""]
    for i, n in enumerate(names):
        lines += ["Bone%d{%s" % (i, n), "-1",
                  "%.6f,%.6f,%.6f" % (0.01 * i, 0.0, 0.0),
                  "0.000000,0.382683,0.000000,0.923880", "}", ""]
    path = os.path.join(H.ROOT, "tests", "sync_pose.vpd")
    with open(path, "w", encoding="cp932", newline="") as f:
        f.write("\r\n".join(lines))
    log("vpd written: %d bones -> %s" % (len(names), path))

    before = vp.pose.base_rot.copy()
    undo0 = len(doc._undo)
    t0 = time.time()
    ok = WIN.import_vpd_path(path)
    dt = (time.time() - t0) * 1000.0
    log("import ok=%s %.0f ms status=%r physics=%s dirty=%s undo %d->%d"
        % (ok, dt, WIN.status_label.text(),
           vp.physics.enabled, doc.dirty, undo0, len(doc._undo)))
    matched = [i for i in range(m.n_bones)
               if not np.allclose(vp.pose.base_rot[i], before[i])]
    log("bones changed: %d %s" % (len(matched), matched[:8]))
    if not ok or len(matched) < len(names):
        anomaly("vpd-import", "ok=%s changed=%d expect=%d" % (ok, len(matched), len(names)))
    if len(doc._undo) != undo0 + 1:
        anomaly("vpd-import", "undo stack %d -> %d" % (undo0, len(doc._undo)))

    doc.undo()
    pump(150)
    rest = float(np.abs(vp.pose.base_rot - before).max())
    log("undo restores pose: maxdiff=%.8f undo=%d redo=%d"
        % (rest, len(doc._undo), len(doc._redo)))
    if rest > 1e-6:
        anomaly("vpd-undo", "maxdiff=%.6f" % rest)
    doc.redo()
    pump(150)
    again = [i for i in range(m.n_bones)
             if not np.allclose(vp.pose.base_rot[i], before[i])]
    log("redo re-applies: changed=%d" % len(again))

    out_noext = os.path.join(H.ROOT, "tests", "sync_out")
    dirty_before = doc.dirty
    t0 = time.time()
    ok_out = WIN.export_vpd_path(out_noext)
    dt = (time.time() - t0) * 1000.0
    out = out_noext + ".vpd"
    log("export ok=%s %.0f ms exists=%s status=%r dirty %s->%s"
        % (ok_out, dt, os.path.exists(out), WIN.status_label.text(),
           dirty_before, doc.dirty))
    if ok_out and os.path.exists(out):
        back = vpdmod.load_vpd(out)
        log("export file: %d bones %d morphs enc=%s"
            % (len(back.bones), len(back.morphs), back.encoding))
        idx = matched[0] if matched else 0
        bname = (m.bones[idx].name or "").strip()
        entry = [b for b in back.bones if (b.name or "").strip() == bname]
        if entry:
            d = float(np.abs(np.array(entry[0].rot) - vp.pose.base_rot[idx]).max())
            log("  roundtrip maxdiff(%s)=%.8f" % (bname, d))
            if d > 1e-5:
                anomaly("vpd-export", "rot maxdiff=%.6f" % d)
        else:
            anomaly("vpd-export", "exported file missing bone %r" % bname)
    else:
        anomaly("vpd-export", "ok=%s exists=%s" % (ok_out, os.path.exists(out)))

    vp.reset_pose()
    pump(120)
    zero = os.path.join(H.ROOT, "tests", "sync_zero")
    ok_zero = WIN.export_vpd_path(zero)
    log("zero-change export ok=%s exists=%s status=%r"
        % (ok_zero, os.path.exists(zero + ".vpd"), WIN.status_label.text()))
    if ok_zero or os.path.exists(zero + ".vpd"):
        anomaly("vpd-export", "zero-change wrote file")

    MB.exec_ = orig_exec
    H.shot(WIN, "sync_vpd")


# ---------------------------------------------------------------- 场景：主题同步
def scen_themesync():
    from pmxeditor import theme as TH
    from pmxeditor import viewport as VP
    from pmxeditor import ui_widgets as UW
    subs = [m for n, m in list(sys.modules.items())
            if n.startswith("pmxeditor.panels.") and hasattr(m, "TEXT")]
    log("=== 亮色启动")
    log("   theme.VIEW_BG_RGB=%r" % (TH.VIEW_BG_RGB,))
    log("   viewport.VIEW_BG_RGB=%r" % (VP.VIEW_BG_RGB,))
    log("   ui_widgets.TEXT=%r panels 子模块(带 TEXT)=%d" % (UW.TEXT, len(subs)))
    from pmxeditor.viewport import core as VC
    log("   viewport.core.VIEW_BG_RGB=%r" % (VC.VIEW_BG_RGB,))
    for m in subs:
        if tuple(m.TEXT) != tuple(TH.TEXT):
            anomaly("theme-sync", "%s 的 TEXT 没跟上主题：%r" % (m.__name__, m.TEXT))
    if tuple(VP.VIEW_BG_RGB) != tuple(TH.VIEW_BG_RGB):
        anomaly("theme-sync", "viewport 的 VIEW_BG_RGB 没跟上主题：%r vs %r"
                % (VP.VIEW_BG_RGB, TH.VIEW_BG_RGB))
    if tuple(UW.TEXT) != tuple(TH.TEXT):
        anomaly("theme-sync", "ui_widgets.TEXT 没跟上主题")
    if tuple(VC.VIEW_BG_RGB) != tuple(TH.VIEW_BG_RGB):
        anomaly("theme-sync", "viewport.core 的 VIEW_BG_RGB 没跟上主题")
    WIN.viewport.repaint()
    pump(250)
    shot(WIN, "themesync_light")
    log("=== 切深色")
    WIN._set_theme("dark", announce=False)
    WIN.viewport.repaint()
    pump(250)
    log("   theme.VIEW_BG_RGB=%r viewport=%r" % (TH.VIEW_BG_RGB, VP.VIEW_BG_RGB))
    if tuple(VP.VIEW_BG_RGB) != tuple(TH.VIEW_BG_RGB):
        anomaly("theme-sync", "切回深色后 viewport 常量不同步")
    shot(WIN, "themesync_dark")
    log("=== 再切亮色")
    WIN._set_theme("light", announce=False)
    WIN.viewport.repaint()
    pump(250)
    log("   theme.VIEW_BG_RGB=%r viewport=%r" % (TH.VIEW_BG_RGB, VP.VIEW_BG_RGB))
    shot(WIN, "themesync_light2")
    H.dump()


# ---------------------------------------------------------------- 场景：主题视觉取样
def scen_themeshot():
    """亮/深两套主题下各拍一张物理模式截图，用于人工比对配色。"""
    WIN.set_physics(True)
    WIN._select_page(5)
    WIN.viewport.repaint()
    pump(400)
    from pmxeditor import theme as TH
    shot(WIN, "themeshot_%s" % TH.current_name())
    log("theme = %s" % TH.current_name())
    H.dump()


# ---------------------------------------------------------------- 场景：三项优化验证
def scen_opt():
    vp = WIN.viewport
    log("=== 1) 网格 VBO 复用")
    ids0 = dict(vp._mesh_ids)
    for i in range(3):
        vp.set_model(WIN.doc.model)
        pump(120)
    ids1 = dict(vp._mesh_ids)
    log("   ids 初值=%s 三次重建后=%s" % (ids0, ids1))
    if ids0 and ids1 != ids0:
        anomaly("vbo-reuse", "结构重建后网格缓冲 id 发生变化，说明仍在重复创建：%s -> %s"
                % (ids0, ids1))
    log("   网格 VBO 数量=%d（固定 4 个即无累积）" % len(ids1))
    if len(ids1) > 4:
        anomaly("vbo-leak", "网格缓冲 id 数量= %d，超过 4 个说明有泄漏" % len(ids1))

    log("=== 2) 页面滚动位置保持")
    WIN._select_page(1)
    pump(150)
    area = WIN._pages[1].scroll_area()
    bar = area.verticalScrollBar()
    log("   骨骼页滚动范围 0..%d viewport=%d" % (bar.maximum(), area.viewport().height()))
    target = min(120, bar.maximum())
    bar.setValue(target)
    before = bar.value()
    WIN._refresh_pages()
    pump(150)
    after = bar.value()
    log("   刷新前=%d 刷新后=%d" % (before, after))
    if before and after != before:
        anomaly("scroll-reset", "面板刷新后滚动位置被重置：%d -> %d" % (before, after))

    log("=== 3) 贴图后台预热")
    thread = getattr(vp, "_tex_warm", None)
    if thread is not None:
        thread.join(timeout=10)
    cached = len(vp._tex_pixels)
    log("   预热完成像素条目=%d 贴图数=%d 线程存活=%s"
        % (cached, len(vp.model.textures) if getattr(vp, "model", None) else -1,
           bool(thread and thread.is_alive())))
    log("   _tex_cache 纹理数=%d" % len(vp._tex_cache))
    if vp.model and len(vp.model.textures) and cached < min(3, len(vp.model.textures)):
        anomaly("tex-prewarm", "后台预热线程没有产出像素缓存（%d 条）" % cached)

    log("=== 4) 关闭时释放 GL 资源")
    try:
        vp.release_gpu_resources()
        log("   release ok mesh_ids=%s tex_cache=%s"
            % (vp._mesh_ids, vp._tex_cache))
    except Exception as e:
        anomaly("gpu-release", "release_gpu_resources 抛异常：%r" % (e,))
    H.dump()


# ---------------------------------------------------------------- 场景：预热收益量化
def scen_optb():
    import time
    vp = WIN.viewport
    model = WIN.doc.model
    n = len(model.textures)

    # A) 有预热：等后台线程解码完，再重建 + 首帧
    if vp._tex_warm is not None:
        vp._tex_warm.join(timeout=20)
    log("预热像素条目=%d" % len(vp._tex_pixels))
    t0 = time.perf_counter()
    vp.set_model(model)
    vp.repaint()
    warm = (time.perf_counter() - t0) * 1000.0
    log("A 预热就绪后 set_model+首帧 = %.1f ms" % warm)

    # B) 关闭预热与像素缓存：模拟旧行为（paint 里同步解码全部贴图）
    vp._tex_pixels.clear()
    vp._tex_cache.clear()
    real = vp._prewarm_textures
    vp._prewarm_textures = lambda: None
    try:
        t0 = time.perf_counter()
        vp.set_model(model)
        vp.repaint()
        cold = (time.perf_counter() - t0) * 1000.0
    finally:
        vp._prewarm_textures = real
    log("B 同步解码全部贴图 = %.1f ms（贴图 %d 张）" % (cold, n))

    # C) 后台预热自身耗时（不进 UI 线程）
    vp._tex_pixels.clear()
    vp._tex_cache.clear()
    t0 = time.perf_counter()
    for i in range(n):
        vp._decode_texture(model.resolve_texture(i))
    decode = (time.perf_counter() - t0) * 1000.0
    log("C 后台解码 12 张耗时 = %.1f ms（在 daemon 线程里，不阻塞界面）" % decode)
    log("结论：首帧从 %.1f ms 降到 %.1f ms（%.1fx）" % (cold, warm, cold / max(warm, 0.01)))
    H.dump()


def scen_dbg2():
    from PyQt5.QtWidgets import QApplication, QScrollArea
    WIN._select_page(2)
    pump(150)
    mp = WIN._pages[2]
    area = mp.scroll_area()
    bar = area.verticalScrollBar()
    log("page2 area=%r bar=%d/%d" % (area is not None, bar.value(), bar.maximum()))
    for name in ("diffuse", "specular", "ambient", "edge_color"):
        b = getattr(mp, name, None)
        if b is None:
            log("  %s 缺失" % name); continue
        g = b.mapToGlobal(b.rect().center())
        hit = QApplication.widgetAt(g)
        log("  %-10s pos=%s size=%s global=%s hit=%s"
            % (name, b.pos(), b.size(), g, desc(hit) if hit else None))
    from PyQt5.QtCore import QPoint
    log("win=%s visible=%s active=%s" % (WIN.geometry(), WIN.isVisible(), WIN.isActiveWindow()))
    log("page2 visible=%s area visible=%s diffuse visible=%s"
        % (mp.isVisible(), area.isVisible(), mp.diffuse.isVisible()))
    for pt in ((700, 100), (1400, 200), (1404, 571)):
        w = QApplication.widgetAt(QPoint(*pt))
        tl = QApplication.topLevelAt(QPoint(*pt))
        ch = WIN.childAt(WIN.mapFromGlobal(QPoint(*pt)))
        log("  %s widgetAt=%s topLevelAt=%s childAt=%s"
            % (pt, desc(w) if w else None, desc(tl) if tl else None, desc(ch) if ch else None))
    area.ensureWidgetVisible(mp.edge_color)
    pump(80)
    b = mp.edge_color
    log("ensure 后 bar=%d edge global=%s hit=%s" % (bar.value(), b.mapToGlobal(b.rect().center()),
        desc(QApplication.widgetAt(b.mapToGlobal(b.rect().center()))) if QApplication.widgetAt(b.mapToGlobal(b.rect().center())) else None))
    shot(WIN, "dbg2")
    H.dump()


def scen_optc():
    """量化结构重建各阶段耗时。"""
    import time
    from pmxeditor import skinning as SK
    vp = WIN.viewport
    model = WIN.doc.model
    log(" bones=%d verts=%d rigid=%d joints=%d"
        % (len(model.bones), model.n_vertices, len(model.rigid), len(model.joints)))
    t0 = time.perf_counter(); pose = SK.Pose(model); t1 = time.perf_counter()
    log(" Pose(model)        = %.1f ms" % ((t1 - t0) * 1000))
    t0 = time.perf_counter(); dfm = SK.SkinDeformer(model); t1 = time.perf_counter()
    log(" SkinDeformer(model)= %.1f ms" % ((t1 - t0) * 1000))
    t0 = time.perf_counter(); vp._prepare_bone_cache(); t1 = time.perf_counter()
    log(" _prepare_bone_cache= %.1f ms" % ((t1 - t0) * 1000))
    t0 = time.perf_counter(); vp.physics.build(model); t1 = time.perf_counter()
    log(" physics.build      = %.1f ms" % ((t1 - t0) * 1000))
    t0 = time.perf_counter(); vp._upload_mesh(); t1 = time.perf_counter()
    log(" _upload_mesh       = %.1f ms" % ((t1 - t0) * 1000))
    t0 = time.perf_counter(); vp._invalidate_all_geometry(); t1 = time.perf_counter()
    log(" _invalidate_geom   = %.1f ms" % ((t1 - t0) * 1000))
    H.dump()


def scen_dform():
    """向量化后的 SkinDeformer 与旧逐顶点实现逐项比对，并计时。"""
    import time
    import numpy as np
    from pmxeditor import skinning as SK

    def reference(model):
        n = model.n_vertices
        nb = len(model.bones)
        bones, wtype, weights = model.v_bones, model.v_wtype, model.v_weights
        counts = np.where(wtype == 0, 1, np.where((wtype == 1) | (wtype == 3), 2, 4))
        total = int(counts.sum())
        eb = np.empty(total, np.int32)
        ev = np.empty(total, np.int32)
        ew = np.empty(total, np.float32)
        k = 0
        for vi in range(n):
            for j in range(int(counts[vi])):
                b = int(bones[vi, j])
                if b < 0 or b >= nb:
                    b = 0
                eb[k] = b
                ev[k] = vi
                ew[k] = float(weights[vi, j])
                k += 1
        order = np.argsort(eb, kind="stable")
        eb, ev, ew = eb[order], ev[order], ew[order]
        cb = np.bincount(eb, minlength=nb)
        starts = np.zeros(nb, np.int64)
        if nb > 1:
            starts[1:] = np.cumsum(cb)[:-1]
        return eb, ev, ew, np.stack([starts, cb], 1), total

    model = WIN.doc.model
    t0 = time.perf_counter(); ref = reference(model); t1 = time.perf_counter()
    log(" 参考实现（逐顶点循环）= %.1f ms" % ((t1 - t0) * 1000))
    t0 = time.perf_counter(); d = SK.SkinDeformer(model); t1 = time.perf_counter()
    log(" 新实现（向量化）      = %.1f ms" % ((t1 - t0) * 1000))
    eb, ev, ew, off, total = ref
    ok = (np.array_equal(d.entries_bone, eb) and np.array_equal(d.entries_vi, ev)
          and np.array_equal(d.entries_w, ew) and np.array_equal(d.offsets, off)
          and d.total == total)
    log(" 逐项一致=%s total=%d/%d entries=%d" % (ok, d.total, total, len(d.entries_bone)))
    if not ok:
        anomaly("deformer-mismatch", "向量化入口与参考实现不一致")
    H.dump()


def scen_struct():
    """结构编辑分项重建：最小重建是否生效、耗时与一致性。"""
    import time
    from pmxeditor import doc as DOC
    vp = WIN.viewport
    doc = WIN.doc
    model = doc.model
    nb0 = len(model.bones)
    rig0 = len(model.rigid)
    vbo0 = dict(vp._mesh_ids)
    tex0 = len(vp._tex_pixels)
    cam0 = (tuple(vp.camera.target), vp.camera.distance)
    pose0 = vp.pose.base_rot.copy()
    doc.select("bone", 0)

    t0 = time.perf_counter()
    doc.edit("新建骨骼", lambda m: DOC.add_bone(m, -1), "structure")
    pump(30)
    t_add = (time.perf_counter() - t0) * 1000.0
    log(" 新建骨骼 %.1f ms bones %d -> %d" % (t_add, nb0, len(doc.model.bones)))
    if len(doc.model.bones) != nb0 + 1:
        anomaly("struct-add", "骨骼数量未增加：%d" % len(doc.model.bones))
    if dict(vp._mesh_ids) != vbo0:
        anomaly("struct-reupload", "最小重建居然重传了网格：%s -> %s" % (vbo0, vp._mesh_ids))
    if tuple(vp.camera.target) != cam0[0] or vp.camera.distance != cam0[1]:
        anomaly("struct-camera", "最小重建改动了相机：%s -> %s" % (cam0, (tuple(vp.camera.target), vp.camera.distance)))
    if vp.pose.base_rot.shape[0] != nb0 + 1:
        anomaly("struct-pose", "Pose 未随骨骼数量更新")
    if len(vp._tex_pixels) != tex0:
        anomaly("struct-tex", "最小重建重新预热了贴图")

    # 撤销应回到原始状态（走 reload 分支的全量重建）
    t0 = time.perf_counter()
    doc.undo()
    pump(30)
    log(" 撤销 %.1f ms bones=%d" % ((time.perf_counter() - t0) * 1000.0, len(doc.model.bones)))
    if len(doc.model.bones) != nb0:
        anomaly("struct-undo", "撤销后骨骼数量=%d（期望 %d）" % (len(doc.model.bones), nb0))

    # 关节类编辑：不应重建 Pose/Deformer
    pose_id = id(vp.pose)
    t0 = time.perf_counter()
    doc.edit("新建关节", lambda m: DOC.add_joint(m), "structure")
    pump(30)
    log(" 新建关节 %.1f ms joints=%d pose 复用=%s"
        % ((time.perf_counter() - t0) * 1000.0, len(doc.model.joints), id(vp.pose) == pose_id))
    if id(vp.pose) != pose_id:
        anomaly("struct-pose-rebuild", "只改关节却重建了 Pose")
    if len(doc.model.joints) <= 0:
        anomaly("struct-joint", "关节未创建")
    doc.undo()
    pump(20)
    if tuple(vp.camera.target) != cam0[0]:
        anomaly("struct-camera2", "关节撤销后相机被改动")
    log(" 结束 bones=%d rigid=%d" % (len(doc.model.bones), len(doc.model.rigid)))
    H.dump()


def scen_struct2():
    """最小重建 vs 全量重建：同一结构编辑的耗时对比（各 3 次取中位）。"""
    import time
    from pmxeditor import doc as DOC
    vp = WIN.viewport
    doc = WIN.doc

    def once():
        t0 = time.perf_counter()
        doc.edit("新建骨骼", lambda m: DOC.add_bone(m, -1), "structure")
        a = (time.perf_counter() - t0) * 1000.0
        t0 = time.perf_counter()
        doc.undo()
        u = (time.perf_counter() - t0) * 1000.0
        return a, u

    def batch(tag):
        adds, undos = [], []
        for _ in range(3):
            a, u = once()
            adds.append(a)
            undos.append(u)
        adds.sort(); undos.sort()
        log(" %-4s 新建骨骼中位=%.1f ms 撤销中位=%.1f ms（adds=%s undos=%s）"
            % (tag, adds[1], undos[1],
               ",".join("%.0f" % v for v in adds), ",".join("%.0f" % v for v in undos)))
        return adds[1], undos[1]

    fast_add, fast_undo = batch("最小")
    real = vp.rebuild_structure
    vp.rebuild_structure = lambda: False
    try:
        full_add, full_undo = batch("全量")
    finally:
        vp.rebuild_structure = real
    log(" 提升：新建骨骼 %.1f -> %.1f ms（%.2fx），撤销 %.1f -> %.1f ms（%.2fx）"
        % (full_add, fast_add, full_add / max(fast_add, 0.01),
           full_undo, fast_undo, full_undo / max(fast_undo, 0.01)))
    if fast_add >= full_add:
        anomaly("struct-nospeedup", "最小重建未带来提升：%.1f vs %.1f ms" % (fast_add, full_add))
    H.dump()


def scen_undo():
    """撤销快照成本与正确性：deepcopy 耗时、快照隔离、撤销后文件字节一致。"""
    import copy
    import time
    from pathlib import Path as _P
    from pmxeditor import pmx as PMX
    doc = WIN.doc
    model = doc.model

    def best(fn, n=3):
        vals = []
        for _ in range(n):
            t0 = time.perf_counter()
            fn()
            vals.append((time.perf_counter() - t0) * 1000.0)
        vals.sort()
        return vals[1], vals

    fast_ms, fast_all = best(lambda: copy.deepcopy(model))
    orig = PMX._FastCopy.__deepcopy__
    PMX._FastCopy.__deepcopy__ = None      # 让 deepcopy 回落到通用 __reduce_ex__ 路径
    try:
        slow_ms, slow_all = best(lambda: copy.deepcopy(model))
    finally:
        PMX._FastCopy.__deepcopy__ = orig
    log(" deepcopy(model) 通用 %.1f ms -> 快速 %.1f ms（%.1fx）%s"
        % (slow_ms, fast_ms, slow_ms / max(fast_ms, 0.01),
           "".join(" %.0f" % v for v in fast_all)))
    if fast_ms >= slow_ms:
        anomaly("copy-nospeedup", "快速深拷贝未加速：%.1f vs %.1f ms" % (fast_ms, slow_ms))

    # 快照隔离：修改在线形态偏移，快照不得跟着变
    snap = copy.deepcopy(model)
    mo = model.morphs[0]
    if mo.offsets and isinstance(mo.offsets[0], dict):
        key = "offset" if "offset" in mo.offsets[0] else None
        snap_val = copy.deepcopy(snap.morphs[0].offsets[0])
        if key and isinstance(mo.offsets[0][key], list) and mo.offsets[0][key]:
            mo.offsets[0][key][0] += 5.0
            if snap.morphs[0].offsets[0][key][0] == mo.offsets[0][key][0]:
                anomaly("snapshot-alias", "快照与在线模型共享了偏移列表")
            mo.offsets[0][key][0] -= 5.0
        mo.offsets[0]["__probe__"] = 1
        if "__probe__" in snap.morphs[0].offsets[0]:
            anomaly("snapshot-alias-dict", "快照与在线模型共享了偏移字典")
        del mo.offsets[0]["__probe__"]
        if snap.morphs[0].offsets[0] != snap_val:
            anomaly("snapshot-content", "快照内容被在线修改污染")
    else:
        log(" 首个形态没有偏移项，跳过隔离检查")

    # 隔离检查通过后，撤销后保存的字节应与编辑前完全一致
    a = str(_P("tests/undo_a.pmx"))
    b = str(_P("tests/undo_b.pmx"))
    PMX.save_pmx(model, a)
    doc.edit("改形态名", lambda m: setattr(m.morphs[0], "name", "改名探针"), "morph")
    doc.edit("改材质名", lambda m: setattr(m.materials[0], "name", "材质探针"), "material")
    doc.undo()
    doc.undo()
    pump(30)
    PMX.save_pmx(doc.model, b)
    da = _P(a).read_bytes()
    db = _P(b).read_bytes()
    log(" 撤销后字节 %d / %d 一致=%s" % (len(da), len(db), da == db))
    if da != db:
        anomaly("undo-bytes", "撤销后保存的字节与编辑前不一致（%d vs %d）" % (len(da), len(db)))
    if doc.model.morphs[0].name == "改名探针" or doc.model.materials[0].name == "材质探针":
        anomaly("undo-state", "撤销未恢复名称")
    for q in (a, b):
        _P(q).unlink(missing_ok=True)
    log(" 结束 morphs=%d materials=%d" % (len(doc.model.morphs), len(doc.model.materials)))
    H.dump()


def scen_undo2():
    """deepcopy 各字段耗时分布，找出快照剩余大头。"""
    import copy
    import time
    doc = WIN.doc
    model = doc.model
    names = [f for f in model.__dict__ if not f.startswith("_")]
    rows = []
    for f in names:
        val = model.__dict__[f]
        t0 = time.perf_counter()
        copy.deepcopy(val)
        rows.append((((time.perf_counter() - t0) * 1000.0), f, len(val) if hasattr(val, "__len__") else 0))
    rows.sort(reverse=True)
    for ms, f, n in rows[:12]:
        log("  %-12s %7.1f ms  n=%s" % (f, ms, n))
    log("  合计 %.1f ms" % sum(r[0] for r in rows))
    H.dump()


def scen_rest():
    """骨骼位置/尾端/父级等静止姿态字段改了，视口是否真的跟着变。"""
    doc = WIN.doc
    vp = WIN.viewport
    WIN._select_page(1)
    pump(150)
    bp = WIN._pages[1]
    i = -1
    for k, b in enumerate(doc.model.bones):
        if (b.flags & 0x0008) and not (b.flags & 0x0001):
            i = k
            break
    if i < 0:
        i = 3
    log("tail-offset bone idx=%d flags=0x%x" % (i, doc.model.bones[i].flags))
    doc.select("bone", i)
    pump(150)
    log("bone %d name=%s pos=%s tail=%s" % (i, doc.model.bones[i].name,
        [round(float(v), 4) for v in doc.model.bones[i].pos],
        [round(float(v), 4) for v in doc.model.bones[i].tail_offset]))
    rest0 = vp.pose.rest_off[i].copy()
    dpos0 = vp.deformer.rest_pos[i].copy()
    before = H.raw(WIN)

    # 1) 面板改位置 Y +0.5
    cur = [float(v) for v in doc.model.bones[i].pos]
    bp.pos_spin.spins[1].setValue(cur[1] + 0.5)
    pump(200)
    log("位置写入后 model.pos=%s" % ([round(float(v), 4) for v in doc.model.bones[i].pos],))
    vp.repaint()
    pump(120)
    rest1 = vp.pose.rest_off[i].copy()
    dpos1 = vp.deformer.rest_pos[i].copy()
    moved_pose = float(abs(rest1 - rest0).max())
    moved_def = float(abs(dpos1 - dpos0).max())
    pct = H.pixdiff(WIN, before)
    log("位置编辑: pose.rest_off delta=%.4f deformer.rest_pos delta=%.4f pix=%.2f%%"
        % (moved_pose, moved_def, pct))
    if moved_pose < 0.4:
        anomaly("bone-pos-stale", "改骨骼位置后 Pose.rest_off 没变（%.4f）" % moved_pose)
    if moved_def < 0.4:
        anomaly("bone-pos-stale", "改骨骼位置后 SkinDeformer.rest_pos 没变（%.4f）" % moved_def)
    if pct < 0.02:
        anomaly("bone-pos-no-pixels", "改骨骼位置后画面几乎没变（%.2f%%）" % pct)
    shot(WIN, "rest_pos")

    # 2) 尾端偏移：骨骼线长度要变
    rows = [int(v) for v in vp._bone_static["indices"]]
    row = rows.index(i) if i in rows else 0
    t0 = vp._bone_static["tail_offsets"][row].copy()
    tc = [float(v) for v in doc.model.bones[i].tail_offset]
    bp.tail_spin.spins[1].setValue(tc[1] - 0.5)
    pump(200)
    t1 = vp._bone_static["tail_offsets"][row].copy()
    log("尾端写入后 model.tail=%s row=%d" % (
        [round(float(v), 4) for v in doc.model.bones[i].tail_offset], row))
    moved_tail = float(abs(t1 - t0).max())
    log("尾端编辑: tail_offsets delta=%.4f" % moved_tail)
    if moved_tail < 0.4:
        anomaly("bone-tail-stale", "改尾端偏移后骨骼线数据没变（%.4f）" % moved_tail)

    # 3) 父级：Pose.parent 要更新（挑一根有父级的骨骼）
    j = i
    for k, b in enumerate(doc.model.bones):
        if 0 <= b.parent < len(doc.model.bones) and b.parent != k:
            j = k
            break
    old_parent = int(doc.model.bones[j].parent)
    doc.edit("改父级", lambda m: setattr(m.bones[j], "parent", 0), "bone")
    vp.mark_dirty()
    pump(120)
    log("父级编辑: bone %d %d -> pose.parent=%d" % (j, old_parent, int(vp.pose.parent[j])))
    if int(vp.pose.parent[j]) != 0:
        anomaly("bone-parent-stale", "改父级后 Pose.parent 仍是 %d" % int(vp.pose.parent[j]))

    # 4) 撤销回退
    for _ in range(12):
        if not doc._undo:
            break
        doc.undo()
    pump(200)
    vp.repaint()
    pump(120)
    back = float(abs(vp.deformer.rest_pos[i] - dpos0).max())
    log("三次撤销后 rest_pos 相对初始 %.5f" % back)
    if back > 1e-4:
        anomaly("undo-rest-mismatch", "撤销后静止位置没恢复（%.5f）" % back)

    # 5) 有蒙皮权重的骨骼：位移后画面应有明显变化
    import numpy as _np
    vb = _np.asarray(doc.model.v_bones)
    vw = _np.asarray(doc.model.v_weights)
    counts = _np.bincount(vb.ravel(), weights=(vw.ravel() > 0.3).astype(_np.float64),
                          minlength=len(doc.model.bones))
    w = int(counts.argmax())
    doc.select("bone", w)
    pump(150)
    before5 = H.raw(WIN)
    cw = [float(v) for v in doc.model.bones[w].pos]
    log("权重骨骼 idx=%d verts=%d pos=%s" % (w, int(counts[w]), [round(v, 3) for v in cw]))
    bp.pos_spin.spins[2].setValue(cw[2] + 0.3)
    pump(200)
    vp.repaint()
    pump(150)
    pct5 = H.pixdiff(WIN, before5)
    log("权重骨骼位移: pix=%.2f%% pos=%s" % (
        pct5, [round(float(v), 3) for v in doc.model.bones[w].pos]))
    if pct5 < 0.05:
        anomaly("bone-pos-no-skin", "移动有权重的骨骼后画面几乎没变（%.2f%%）" % pct5)
    shot(WIN, "rest_weighted")
    doc.undo()
    pump(250)
    vp.repaint()
    pump(150)
    log("撤销后 pix vs 位移前 = %.2f%%" % H.pixdiff(WIN, before5))
    H.dump()

scen_restx = scen_rest



def scen_restmove():
    """骨骼页：进入即显示骨架；可选的「移动时带动顶点」。"""
    import numpy as _np
    WIN.resize(1560, 920)
    APP.processEvents()
    vp = WIN.viewport
    doc = WIN.doc
    vp.set_display(show_bones=False)
    WIN._select_page(4)
    pump(120)
    WIN._select_page(1)
    pump(200)
    log("进入骨骼页后 show_bones = %s" % vp.show_bones)
    if not vp.show_bones:
        anomaly("bone-page-no-skeleton", "进入骨骼页没有自动打开骨骼显示")

    bp = WIN._pages[1]
    vb = _np.asarray(doc.model.v_bones)
    vw = _np.asarray(doc.model.v_weights)
    counts = _np.bincount(vb.ravel(), weights=(vw.ravel() > 0.3).astype(_np.float64),
                          minlength=len(doc.model.bones))
    w = int(counts.argmax())
    doc.select("bone", w)
    pump(200)
    base = doc.model.v_pos.copy()
    z = float(doc.model.bones[w].pos[2])

    # 1) 开关关闭：只动骨骼，顶点不变
    bp.move_verts_sw.setChecked(False)
    bp.pos_spin.spins[2].setValue(z + 0.3)
    pump(250)
    d0 = float(_np.abs(doc.model.v_pos - base).max())
    log("开关关闭: 顶点最大位移=%.5f bone z=%.3f" % (d0, float(doc.model.bones[w].pos[2])))
    if d0 > 1e-6:
        anomaly("move-verts-off-leak", "关闭开关仍改动了顶点（%.5f）" % d0)
    doc.undo()
    pump(250)

    # 2) 开关打开：顶点按权重跟随
    bp.move_verts_sw.setChecked(True)
    before = H.raw(WIN)
    bp.pos_spin.spins[2].setValue(z + 0.3)
    pump(250)
    vp.repaint()
    pump(150)
    d1 = float(_np.abs(doc.model.v_pos - base).max())
    moved = int((_np.abs(doc.model.v_pos - base).max(axis=1) > 1e-6).sum())
    pct = H.pixdiff(WIN, before)
    log("开关打开: 顶点最大位移=%.5f 受影响=%d 像素差=%.2f%%" % (d1, moved, pct))
    if abs(d1 - 0.3) > 0.02:
        anomaly("move-verts-delta", "顶点位移 %.5f 与 0.3 不符" % d1)
    if moved <= 0:
        anomaly("move-verts-none", "打开开关后没有顶点跟随")
    if pct < 0.05:
        anomaly("move-verts-invisible", "顶点已移动但画面几乎没变（%.2f%%）" % pct)
    shot(WIN, "restmove_on")

    # 3) 撤销：顶点与骨骼都回到原样
    doc.undo()
    pump(250)
    d2 = float(_np.abs(doc.model.v_pos - base).max())
    log("撤销后: 顶点最大位移=%.6f bone z=%.3f" % (d2, float(doc.model.bones[w].pos[2])))
    if d2 > 1e-6:
        anomaly("move-verts-undo", "撤销后顶点没复原（%.6f）" % d2)
    H.dump()


def scen_mouse():
    """视角操作：左键拖动旋转、右键拖动平移、左键单击选择；骨骼页开关持久化。"""
    from PyQt5.QtCore import QEvent, QPointF, QSettings, Qt
    from PyQt5.QtGui import QMouseEvent
    from pmxeditor import panels as pn

    WIN.resize(1560, 920)
    APP.processEvents()
    vp = WIN.viewport
    doc = WIN.doc

    def send(t, x, y, btn, buttons):
        ev = QMouseEvent(t, QPointF(x, y), QPointF(x, y), QPointF(x, y),
                         btn, buttons, Qt.NoModifier)
        if t == QEvent.MouseButtonPress:
            vp.mousePressEvent(ev)
        elif t == QEvent.MouseMove:
            vp.mouseMoveEvent(ev)
        else:
            vp.mouseReleaseEvent(ev)

    # 1) 左键拖动 = 旋转
    doc.select("bone", 3)
    pump(100)
    yaw0 = vp.camera.yaw
    pitch0 = vp.camera.pitch
    send(QEvent.MouseButtonPress, 40, 40, Qt.LeftButton, Qt.LeftButton)
    send(QEvent.MouseMove, 140, 100, Qt.NoButton, Qt.LeftButton)
    send(QEvent.MouseButtonRelease, 140, 100, Qt.LeftButton, Qt.NoButton)
    pump(80)
    log("左键拖动: yaw %.4f -> %.4f, pitch %.4f -> %.4f, sel=%s"
        % (yaw0, vp.camera.yaw, pitch0, vp.camera.pitch,
           (doc.sel_kind, doc.sel_index)))
    if abs(vp.camera.yaw - yaw0) < 1e-6:
        anomaly("left-drag-orbit", "左键拖动没有旋转视角")
    if doc.sel_kind != "bone":
        anomaly("left-drag-deselect", "左键拖动把选择清掉了（%s）" % (doc.sel_kind,))

    # 2) 右键拖动 = 平移
    t0 = vp.camera.target.copy()
    send(QEvent.MouseButtonPress, 40, 40, Qt.RightButton, Qt.RightButton)
    send(QEvent.MouseMove, 120, 80, Qt.NoButton, Qt.RightButton)
    send(QEvent.MouseButtonRelease, 120, 80, Qt.RightButton, Qt.NoButton)
    pump(80)
    dt = float(((vp.camera.target - t0) ** 2).sum() ** 0.5)
    log("右键拖动: target 位移=%.4f" % dt)
    if dt < 1e-4:
        anomaly("right-drag-pan", "右键拖动没有平移视角")

    # 3) 左键单击（不移动）= 选择，空白处取消选择
    send(QEvent.MouseButtonPress, 6, 6, Qt.LeftButton, Qt.LeftButton)
    send(QEvent.MouseButtonRelease, 6, 6, Qt.LeftButton, Qt.NoButton)
    pump(80)
    log("左键单击空白: sel=%s" % ((doc.sel_kind, doc.sel_index),))
    if doc.sel_kind != "":
        anomaly("click-blank", "左键单击空白没有取消选择")

    # 4) 「移动时带动顶点」开关持久化
    bp = WIN._pages[1]
    st = QSettings("PmxEditorModern", "editor")
    prev = st.value("editor/move_bone_vertices", False, type=bool)
    bp.move_verts_sw.setChecked(True)
    pump(60)
    got = st.value("editor/move_bone_vertices", False, type=bool)
    bp2 = pn.BonePage(doc)
    log("开关持久化: 写入=%s 新实例=%s" % (got, bp2.move_verts_sw.isChecked()))
    if not got or not bp2.move_verts_sw.isChecked():
        anomaly("move-verts-persist", "开关状态没有持久化")
    bp2.deleteLater()
    bp.move_verts_sw.setChecked(bool(prev))
    st.sync()
    H.dump()


def scen_bright():
    """设置页亮度：背景/模型倍率是否真的作用到视口，并持久化。"""
    from PyQt5.QtCore import QSettings
    WIN.resize(1560, 920)
    WIN._select_page(5)
    pump(300)
    sp = WIN._pages[5]
    vp = WIN.viewport
    st = QSettings("PmxEditorModern", "editor")
    prev_bg = st.value("view/bg_brightness", 1.0, type=float)
    prev_mb = st.value("view/model_brightness", 1.0, type=float)
    log("初始: bg_slider=%d model_slider=%d vp.bg=%.2f vp.model=%.2f"
        % (sp.bg_slider.value(), sp.model_slider.value(),
           vp.bg_brightness, vp.model_brightness))
    if abs(sp.bg_slider.value() / 100.0 - prev_bg) > 0.01 or \
            abs(sp.model_slider.value() / 100.0 - prev_mb) > 0.01:
        anomaly("bright-restore", "启动时滑杆没有回填上次保存的亮度（%d/%d vs %.2f/%.2f）"
                % (sp.bg_slider.value(), sp.model_slider.value(), prev_bg, prev_mb))
    sp.bg_slider.setValue(100)
    sp.model_slider.setValue(100)
    vp.repaint(); pump(120)

    vp.repaint(); pump(120)
    base = H.raw(WIN)

    # 背景 200%（提亮走"向白插值"，应能看到明显的浅灰底）
    bg0 = vp.grabFramebuffer().pixelColor(int(vp.width() * 0.82),
                                         int(vp.height() * 0.12))
    sp.bg_slider.setValue(200)
    vp.repaint(); pump(160)
    bg1 = vp.grabFramebuffer().pixelColor(int(vp.width() * 0.82),
                                         int(vp.height() * 0.12))
    log("背景像素: %s -> %s"
        % ((bg0.red(), bg0.green(), bg0.blue()),
           (bg1.red(), bg1.green(), bg1.blue())))
    if abs(bg1.red() - bg0.red()) < 20:
        anomaly("bright-bg-pixel", "调背景亮度后视口像素几乎没变（%d -> %d）"
                % (bg0.red(), bg1.red()))
    bgc = vp._bg_color()
    if not vp._grid_dark:
        anomaly("bright-gridtone", "背景提亮到 200%% 后网格/HUD 没有翻成深色")
    log("背景 200%%: vp.bg=%.2f 清屏色=%s 状态=%r"
        % (vp.bg_brightness, tuple(round(c, 3) for c in bgc), STATUS.text))
    if abs(vp.bg_brightness - 2.0) > 1e-6:
        anomaly("bright-bg-prop", "背景亮度没有传到视口（%.3f）" % vp.bg_brightness)
    if abs(st.value("view/bg_brightness", 1.0, type=float) - 2.0) > 1e-6:
        anomaly("bright-bg-save", "背景亮度没有持久化")
    log("    像素差=%.2f%%" % H.pixdiff(WIN, base))
    shot(WIN, "bright_bg")

    # 模型 50%
    sp.model_slider.setValue(50)
    vp.repaint(); pump(160)
    log("模型 50%%: vp.model=%.2f 标签=%r 状态=%r"
        % (vp.model_brightness, sp.model_value.text(), STATUS.text))
    if abs(vp.model_brightness - 0.5) > 1e-6:
        anomaly("bright-model-prop", "模型亮度没有传到视口（%.3f）" % vp.model_brightness)
    shot(WIN, "bright_model")

    # 恢复默认
    sp.bg_slider.setValue(100)
    sp.model_slider.setValue(100)
    vp.repaint(); pump(160)
    log("恢复默认: vp.bg=%.2f vp.model=%.2f 像素差=%.2f%%"
        % (vp.bg_brightness, vp.model_brightness, H.pixdiff(WIN, base)))

    # 还原用户原设置
    sp.bg_slider.setValue(int(round(prev_bg * 100)))
    sp.model_slider.setValue(int(round(prev_mb * 100)))
    st.sync()
    H.dump()


def scen_bgprobe():
    """读取视口像素，确认背景亮度真的改变了清屏色（不是只改了属性）。"""
    vp = WIN.viewport
    WIN._select_page(5)
    pump(200)
    for b in (0.2, 0.5, 1.0, 1.6, 2.5):
        vp.set_brightness(bg=b)
        vp.repaint()
        pump(160)
        img = vp.grabFramebuffer()
        c = img.pixelColor(int(vp.width() * 0.82), int(vp.height() * 0.12))
        d = img.pixelColor(int(vp.width() * 0.05), int(vp.height() * 0.5))
        log("bg=%.1f 属性=%s 像素(右上)=%s 像素(左中)=%s 清屏色=%s"
            % (b, round(vp.bg_brightness, 2),
               (c.red(), c.green(), c.blue()), (d.red(), d.green(), d.blue()),
               tuple(round(x, 3) for x in vp._bg_color())))
    vp.set_brightness(bg=1.0)
    H.dump()

def scen_brightshot():
    """亮度设置的真机视觉验收：背景 200%、模型 160%。"""
    win = WIN
    vp = win.viewport
    sp = win._pages[5]
    win._select_page(5)
    pump(150)
    sp.bg_slider.setValue(200)
    vp.repaint(); pump(200)
    shot(win, "bright_bg200")
    sp.bg_slider.setValue(100)
    sp.model_slider.setValue(160)
    vp.repaint(); pump(200)
    shot(win, "bright_model160")
    sp.model_slider.setValue(100)
    vp.repaint(); pump(200)
    log("bg=%s model=%s" % (vp.bg_brightness, vp.model_brightness))

def scen_optim():
    """验证「已知限制与技术债」三项优化：组/翻转形态展开、物理参数热更新、
    骨骼拾取 Alt 循环。"""
    import time
    win = WIN
    vp = win.viewport
    m = win.doc.model
    log("morphs=%d" % len(m.morphs))

    # ---- 1) 组形态 / 翻转形态递归展开 ----
    group = next((i for i, mo in enumerate(m.morphs) if mo.type == 0), -1)
    flip = next((i for i, mo in enumerate(m.morphs) if mo.type == 9), -1)
    add_uv = next((i for i, mo in enumerate(m.morphs) if mo.type == 4), -1)
    log("group_morph=%d flip_morph=%d add_uv=%d" % (group, flip, add_uv))
    if add_uv >= 0:
        vp.set_morph_weights({add_uv: 1.0})
        got = dict(vp.morph_weights)
        log("附加UV形态 #%d w=1.0 -> %s（应保留自身）"
            % (add_uv, sorted(got.items())))
        if abs(got.get(add_uv, 0.0) - 1.0) > 1e-4:
            anomaly("morph-adduv", "附加 UV 形态被当成组/翻转容器：%s"
                    % sorted(got.items()))
        vp.set_morph_weights({})
    if group >= 0:
        vp.set_morph_weights({group: 1.0})
        expanded = dict(vp.morph_weights)
        log("组形态展开: 引用=%s -> 生效=%s"
            % ([(o.get("morph"), o.get("ratio")) for o in m.morphs[group].offsets],
               sorted(expanded.items())))
        if group in expanded:
            anomaly("morph-group", "组形态自身还在生效权重里（没被展开）")
        if not expanded:
            anomaly("morph-group", "组形态展开后没有任何子形态生效")
        for ti, w in expanded.items():
            if m.morphs[ti].type in (0, 9):
                anomaly("morph-group", "展开结果里仍残留组/翻转形态 #%d" % ti)
    else:
        log("模型没有组形态，跳过展开用例")
    if flip >= 0:
        vp.set_morph_weights({flip: 0.25})
        got = dict(vp.morph_weights)
        refs = [(o.get("morph"), o.get("ratio")) for o in m.morphs[flip].offsets]
        log("翻转形态 w=0.25 引用=%s -> 生效=%s" % (refs, sorted(got.items())))
        for ti, r in refs:
            want = (1.0 - 0.25) * float(r)
            if abs(got.get(ti, 0.0) - want) > 1e-4:
                anomaly("morph-flip", "#%d 期望 %.4f 实际 %.4f"
                        % (ti, want, got.get(ti, 0.0)))
    # 合成翻转形态与嵌套组形态，验证 (1-w) 语义与递归（不改模型，临时追加）
    from pmxeditor.pmx import Morph as _Morph
    base = 0 if len(m.morphs) > 0 else -1
    added = []
    if base >= 0:
        n0 = len(m.morphs)
        f = _Morph(name="__flip__", name_en="__flip__", type=9, panel=0,
                   offsets=[{"morph": base, "ratio": 1.0}])
        g2 = _Morph(name="__grp2__", name_en="__grp2__", type=0, panel=0,
                    offsets=[{"morph": n0, "ratio": 0.5}])
        m.morphs.append(f)
        m.morphs.append(g2)
        added = [n0, n0 + 1]
        vp.set_morph_weights({added[0]: 0.25})
        got = dict(vp.morph_weights)
        log("合成翻转 w=0.25 -> %s（期望 #%d=0.75）" % (sorted(got.items()), base))
        if abs(got.get(base, 0.0) - 0.75) > 1e-4:
            anomaly("morph-flip", "翻转形态权重应为 1-w=0.75，实际 %.4f"
                    % got.get(base, 0.0))
        vp.set_morph_weights({added[1]: 1.0})
        got = dict(vp.morph_weights)
        log("嵌套组 #%d -> %s（期望 #%d=0.5）"
            % (added[1], sorted(got.items()), base))
        if abs(got.get(base, 0.0) - 0.5) > 1e-4:
            anomaly("morph-nested", "嵌套组展开权重应为 0.5，实际 %.4f"
                    % got.get(base, 0.0))
        if added[0] in got or added[1] in got:
            anomaly("morph-nested", "组/翻转形态不应留在生效权重里：%s"
                    % sorted(got.items()))
        # 自引用不能死循环
        cyc = _Morph(name="__cyc__", name_en="__cyc__", type=0, panel=0,
                     offsets=[{"morph": len(m.morphs), "ratio": 1.0}])
        m.morphs.append(cyc)
        vp.set_morph_weights({len(m.morphs) - 1: 1.0})
        log("自引用组形态未死循环，结果=%s（应为空）"
            % sorted(vp.morph_weights.items()))
        if vp.morph_weights:
            anomaly("morph-cycle", "自引用组形态仍留在生效权重里：%s"
                    % sorted(vp.morph_weights.items()))
        added.append(len(m.morphs) - 1)
        for _ in range(len(added)):
            m.morphs.pop()
    vp.set_morph_weights({})

    # ---- 2) 物理参数热更新 ----
    if vp.physics._ready:
        world_before = vp.physics.world
        t0 = time.time()
        vp.apply_physics_settings(gravity=-20.0, iterations=12)
        hot_ms = (time.time() - t0) * 1000
        same = vp.physics.world is world_before
        log("热更新: %.1f ms world 未重建=%s gravity=%.1f iterations=%d"
            % (hot_ms, same, vp.physics.gravity, vp.physics.iterations))
        if not same:
            anomaly("phys-hot", "改重力重建了物理世界（不是热更新）")
        if abs(vp.physics.gravity + 20.0) > 1e-6:
            anomaly("phys-hot", "重力没写进物理世界（%.2f）" % vp.physics.gravity)
        t0 = time.time()
        vp.rebuild_physics()
        full_ms = (time.time() - t0) * 1000
        log("对比 rebuild_physics: %.1f ms（热更新 %.1f ms）" % (full_ms, hot_ms))
        vp.apply_physics_settings(gravity=-9.8, iterations=10)
    else:
        log("物理不可用，跳过热更新用例")

    # ---- 3) 拾取候选与 Alt 循环 ----
    best_pt = None
    for gy in range(120, vp.height() - 60, 40):
        for gx in range(40, vp.width() - 40, 40):
            c = vp._pick_candidates(gx, gy)
            if len(c) >= 2:
                best_pt = (gx, gy, c)
                break
        if best_pt:
            break
    if not best_pt:
        log("没找到重叠骨骼点，Alt 循环用例退化")
    else:
        gx, gy, cands = best_pt
        log("重叠点 (%d,%d) 候选=%s" % (gx, gy,
              [(c[2], c[3], round(c[0], 1)) for c in cands]))
        picks = []
        for _ in range(len(cands) + 1):
            picks.append(vp.pick(gx, gy, cycle=True))
        log("Alt 循环: %s" % (picks,))
        if len({p[1] for p in picks}) < 2:
            anomaly("pick-cycle", "Alt 循环没有切换到其它候选：%s" % (picks,))
        one = vp.pick(gx, gy)
        if one not in picks:
            anomaly("pick-best", "非循环拾取结果不在候选里：%s" % (one,))
        if vp.pick(gx, gy, cycle=True) == one and len(cands) > 1:
            pass

def scen_undobudget():
    """撤销栈分类预算：模型快照与姿态条目各 12 步，互不挤占。"""
    win = WIN
    doc = win.doc
    if doc.model is None:
        anomaly("undobudget", "没有模型")
        return
    doc._undo.clear()
    doc._redo.clear()
    for i in range(14):
        doc.edit("m%d" % i, lambda m, i=i: setattr(m, "comment", "c%d" % i))
    models = len([it for it in doc._undo if it[1] is not None])
    poses = len([it for it in doc._undo if it[1] is None])
    log("14 次模型编辑后 模型条目=%d 姿态条目=%d" % (models, poses))
    if models != 12:
        anomaly("undobudget", "模型条目应被裁到 12，实际 %d" % models)
    for i in range(5):
        doc.push_pose_undo("p%d" % i)
    models = len([it for it in doc._undo if it[1] is not None])
    poses = len([it for it in doc._undo if it[1] is None])
    log("再加 5 条姿态后 模型条目=%d 姿态条目=%d" % (models, poses))
    if models != 12:
        anomaly("undobudget", "姿态条目挤掉了模型快照：模型条目=%d" % models)
    if poses != 5:
        anomaly("undobudget", "姿态条目应为 5，实际 %d" % poses)
    for i in range(14, 17):
        doc.edit("m%d" % i, lambda m, i=i: setattr(m, "comment", "c%d" % i))
    models = len([it for it in doc._undo if it[1] is not None])
    poses = len([it for it in doc._undo if it[1] is None])
    log("再 3 次模型编辑后 模型条目=%d 姿态条目=%d" % (models, poses))
    if models != 12 or poses != 5:
        anomaly("undobudget", "分类预算失衡：模型=%d 姿态=%d" % (models, poses))
    n = len(doc._undo)
    for _ in range(n):
        if not doc.undo():
            anomaly("undobudget", "撤销提前中断，剩余 %d 条" % len(doc._undo))
            break
    log("连续撤销 %d 次后剩余=%d" % (n, len(doc._undo)))


def scen_poseundo():
    """姿态类撤销：轻量条目、不换模型、R 重置可撤销、与模型编辑混排。"""
    import time as _time
    from pmxeditor import pmx as _pmx
    WIN.set_physics(False)
    vp = WIN.viewport
    doc = WIN.doc
    m = doc.model
    if doc.sel_kind != "bone":
        doc.select("bone", 5)
    APP.processEvents()

    def find_bone_pixel():
        for yy in range(40, vp.height() - 40, 12):
            for xx in range(40, vp.width() - 40, 12):
                r = vp.pick(xx, yy)
                if r and r[0] == "bone":
                    return xx, yy, r
        return None

    hit = find_bone_pixel()
    log("骨骼像素: %s" % (hit,))
    if not hit:
        anomaly("poseundo", "视口里找不到骨骼像素，无法测姿态撤销")
        return
    xx, yy, before_sel = hit
    doc.select(before_sel[0], before_sel[1])
    APP.processEvents()

    rot0 = doc.pose_capture()[1].copy() if doc.pose_capture else None
    model0 = doc.model
    undo0 = len(doc._undo)
    dirty0 = doc.dirty

    t0 = _time.perf_counter()
    _mouse_drag(vp, QPoint(xx, yy), QPoint(xx + 70, yy + 30), Qt.LeftButton, Qt.NoModifier)
    dt = (_time.perf_counter() - t0) * 1000.0
    APP.processEvents()
    undo1 = len(doc._undo)
    entry = doc._undo[-1] if doc._undo else None
    log("姿态拖动 %.1f ms undo %d -> %d 条目标签=%r 模型快照=%s"
        % (dt, undo0, undo1, entry[0] if entry else None,
           "无" if entry and entry[1] is None else "有"))
    if undo1 != undo0 + 1:
        anomaly("poseundo", "姿态拖动应压 1 条撤销记录，实际 %d -> %d"
                % (undo0, undo1))
    if entry is not None and entry[1] is not None:
        anomaly("poseundo", "姿态条目不应深拷贝模型（应存 model=None）")
    # dt 里包含 5 次 pump(40)，不用于比较；这里直接量一次「压姿态条目」的开销
    import copy as _copy
    saved_entry = doc._undo.pop()
    t0 = _time.perf_counter()
    _copy.deepcopy(m)
    deep_ms = (_time.perf_counter() - t0) * 1000.0
    t0 = _time.perf_counter()
    doc.push_pose_undo("测试姿态")
    pose_ms = (_time.perf_counter() - t0) * 1000.0
    doc._undo.pop()
    doc._undo.append(saved_entry)
    log("对照：整模型 deepcopy %.1f ms / 压姿态条目 %.2f ms（含拖动 %.1f ms）"
        % (deep_ms, pose_ms, dt))
    if pose_ms > deep_ms * 0.5:
        anomaly("poseundo", "姿态条目 %.2f ms 应远低于整模型快照 %.2f ms"
                % (pose_ms, deep_ms))

    rot1 = doc.pose_capture()[1].copy()
    ok = doc.undo()
    APP.processEvents()
    rot2 = doc.pose_capture()[1].copy()
    import numpy as _np
    d_undo = float(_np.abs(rot2 - rot0).max())
    d_drag = float(_np.abs(rot1 - rot0).max())
    log("撤销: ok=%s 拖动位移=%.4f 撤销后残留=%.6f 模型对象未变=%s status=%r"
        % (ok, d_drag, d_undo, doc.model is model0, WIN.status_label.text()))
    if not ok or d_drag < 1e-4:
        anomaly("poseundo", "姿态拖动没有改变姿态（位移 %.6f）" % d_drag)
    if d_undo > 1e-4:
        anomaly("poseundo", "撤销后姿态未复原，残留 %.6f" % d_undo)
    if doc.model is not model0:
        anomaly("poseundo", "姿态撤销不应替换模型对象")

    doc.redo()
    APP.processEvents()
    rot3 = doc.pose_capture()[1].copy()
    d_redo = float(_np.abs(rot3 - rot1).max())
    log("重做: 与拖动后差值=%.6f" % d_redo)
    if d_redo > 1e-4:
        anomaly("poseundo", "重做未回到拖动后的姿态，差值 %.6f" % d_redo)
    doc.undo()
    APP.processEvents()

    pre_reset = doc.pose_capture()[1].copy()
    n0 = len(doc._undo)
    vp.reset_pose()
    APP.processEvents()
    n1 = len(doc._undo)
    label = doc._undo[-1][0] if doc._undo else None
    log("R 重置: undo %d -> %d 标签=%r" % (n0, n1, label))
    if n1 != n0 + 1 or label != "重置姿态":
        anomaly("poseundo", "R 重置应压一条「重置姿态」撤销记录，实际 %d -> %d %r"
                % (n0, n1, label))
    doc.undo()
    APP.processEvents()
    back = doc.pose_capture()[1].copy()
    d_reset = float(_np.abs(back - pre_reset).max())
    log("R 重置撤销: 与重置前差值=%.6f" % d_reset)
    if d_reset > 1e-4:
        anomaly("poseundo", "撤销重置未回到重置前姿态，差值 %.6f" % d_reset)

    # 与模型编辑混排：先改骨骼坐标（模型条目），再拖姿态（姿态条目）
    WIN.set_physics(False)
    WIN._select_page(1)
    APP.processEvents()
    bp = WIN._pages[1]
    n0 = len(doc._undo)
    bp.pos_spin.spins[1].setValue(bp.pos_spin.spins[1].value() + 0.2)
    APP.processEvents()
    WIN.set_physics(False)
    APP.processEvents()
    again = find_bone_pixel()          # 骨骼刚被移动过，重新扫描命中点
    if again:
        xx, yy = again[0], again[1]
    _mouse_drag(vp, QPoint(xx, yy), QPoint(xx + 50, yy - 20), Qt.LeftButton, Qt.NoModifier)
    APP.processEvents()
    n1 = len(doc._undo)
    kinds = [("pose" if e[1] is None else "model") for e in doc._undo[-2:]]
    log("混排: undo %d -> %d 末两条=%s" % (n0, n1, kinds))
    if kinds != ["model", "pose"]:
        anomaly("poseundo", "混排顺序应为 [model, pose]，实际 %s" % kinds)
    doc.undo()
    APP.processEvents()
    still_model = doc.model is not None
    doc.undo()
    APP.processEvents()
    log("连续两次撤销后 sel=%r status=%r 模型对象有效=%s dirty=%s"
        % ((doc.sel_kind, doc.sel_index), WIN.status_label.text(),
           still_model, doc.dirty))
    shot(WIN, "poseundo")
    doc.undo()
    doc.undo()
    APP.processEvents()
    log("清理: undo 深度=%d" % len(doc._undo))
    del dirty0


def scen_skin():
    """SDEF 球面插值 / QDEF 双四元数的数值验证（合成夹具，不依赖模型文件）。"""
    import types
    import numpy as _np
    from pmxeditor import skinning as SK
    log("== skin: SDEF / QDEF ==")

    def rz(deg):
        r = _np.radians(deg)
        c, s = _np.cos(r), _np.sin(r)
        m = _np.eye(4, dtype=_np.float32)
        m[0, 0], m[0, 1], m[1, 0], m[1, 1] = c, -s, s, c
        return m

    # ---- SDEF：骨骼 0 静止，骨骼 1 绕 C 点转 90 度，50/50 混合
    m0 = _np.eye(4, dtype=_np.float32)
    m1 = rz(90.0)
    m1[:3, 3] = _np.array([1.0, 0.0, 0.0], _np.float32)
    world = _np.stack([m0, m1])
    rest = _np.array([[0, 0, 0], [1, 0, 0]], dtype=_np.float32)
    base = _np.array([[1.5, 0, 0]], dtype=_np.float32)
    sdef = _np.zeros((1, 9), dtype=_np.float32)
    sdef[0, 0:3] = [1.0, 0.0, 0.0]
    model = types.SimpleNamespace(
        v_pos=base, v_nrm=_np.array([[0, 0, 1]], dtype=_np.float32),
        v_bones=_np.array([[0, 1, 0, 0]], dtype=_np.int32),
        v_weights=_np.array([[0.5, 0.5, 0, 0]], dtype=_np.float32),
        v_wtype=_np.array([3], dtype=_np.uint8), v_sdef=sdef)
    nrm = _np.array([[0, 0, 1]], dtype=_np.float32)
    native = SK.native_core
    out_n, _ = native.deform(base, nrm, model.v_bones, model.v_weights,
                             model.v_wtype, rest, world, sdef)
    radius = float(_np.linalg.norm(out_n[0] - _np.array([1.0, 0, 0])))
    log("sdef: pos=%s 半径=%.4f (期望 0.5)" % (_np.round(out_n[0], 4), radius))
    if abs(radius - 0.5) > 1e-3:
        anomaly("sdef-radius", "SDEF 顶点到 C 的距离应为静止半径 0.5，实际 %.4f" % radius)
    linear = 0.5 * (m0[:3, :3] @ base[0] + m0[:3, 3]) + 0.5 * (
        m1[:3, :3] @ (base[0] - rest[1]) + m1[:3, 3])
    if float(_np.linalg.norm(linear - out_n[0])) < 1e-3:
        anomaly("sdef-equal-linear", "SDEF 结果与线性混合相同，说明分支没生效")

    # ---- QDEF：四根骨骼同矩阵时必须与 BDEF4 完全一致
    mq = rz(37.0)
    mq[:3, 3] = _np.array([0.3, -0.2, 0.5], _np.float32)
    world4 = _np.stack([mq] * 4)
    rest4 = _np.zeros((4, 3), dtype=_np.float32)
    base4 = _np.array([[0.7, 1.1, -0.4]], dtype=_np.float32)
    sdef4 = _np.zeros((1, 9), dtype=_np.float32)
    model4 = types.SimpleNamespace(
        v_pos=base4, v_nrm=nrm,
        v_bones=_np.array([[0, 1, 2, 3]], dtype=_np.int32),
        v_weights=_np.array([[0.25, 0.25, 0.25, 0.25]], dtype=_np.float32),
        v_wtype=_np.array([4], dtype=_np.uint8), v_sdef=sdef4)
    out4, _ = native.deform(base4, nrm, model4.v_bones, model4.v_weights,
                            model4.v_wtype, rest4, world4, sdef4)
    expect = mq[:3, :3] @ base4[0] + mq[:3, 3]
    err = float(_np.linalg.norm(out4[0] - expect))
    log("qdef: pos=%s 期望=%s 误差=%.6f" % (_np.round(out4[0], 4),
                                            _np.round(expect, 4), err))
    if err > 1e-4:
        anomaly("qdef-rigid", "同矩阵 QDEF 混合应与刚体变换一致，误差 %.6f" % err)

    # ---- Python 回退实现与原生实现一致
    fake = types.SimpleNamespace(model=model, rest_pos=rest)
    back = SK.SkinDeformer._special_blend(fake, base, world,
                                          _np.zeros_like(base))
    d = float(_np.linalg.norm(back[0] - out_n[0]))
    log("fallback: sdef 差=%.6f" % d)
    if d > 1e-4:
        anomaly("sdef-fallback", "回退实现与原生结果差 %.6f" % d)
    fake4 = types.SimpleNamespace(model=model4, rest_pos=rest4)
    back4 = SK.SkinDeformer._special_blend(fake4, base4, world4,
                                           _np.zeros_like(base4))
    d4 = float(_np.linalg.norm(back4[0] - out4[0]))
    log("fallback: qdef 差=%.6f" % d4)
    if d4 > 1e-4:
        anomaly("qdef-fallback", "回退实现与原生结果差 %.6f" % d4)



def scen_ellipsoid():
    """P2-a：SDEF 椭球半轴（R0）。

    公式 radius = |v - C| * ell(u_rest) / ell(u_cur)，ell(u) = 1/sqrt(sum((u_i/a_i)^2))：
    静止姿态下 u_cur 与 u_rest 同向，半径退回球面半径 |v - C|；
    只有两根骨骼旋转不同、方向被混合偏转时，R0 的各向异性才改变半径。
    """
    import types
    import numpy as _np
    from pmxeditor import skinning as SK

    log("== SDEF ellipsoid ==")
    nrm = _np.array([[0, 0, 1]], dtype=_np.float32)
    rest = _np.zeros((2, 3), dtype=_np.float32)

    def run(r0, rot1_deg, base_pt, center=None):
        base = _np.array([base_pt], dtype=_np.float32)
        world = _np.stack([_np.eye(4, dtype=_np.float32)] * 2)
        if rot1_deg:
            a = _np.deg2rad(rot1_deg)
            world[1] = _np.array([[ _np.cos(a), -_np.sin(a), 0, 0],
                                  [ _np.sin(a),  _np.cos(a), 0, 0],
                                  [0, 0, 1, 0], [0, 0, 0, 1]], dtype=_np.float32)
        sd = _np.zeros((1, 9), dtype=_np.float32)
        if center is not None:
            sd[0, 0:3] = center
        sd[0, 3:6] = r0
        model = types.SimpleNamespace(
            v_pos=base, v_nrm=nrm,
            v_bones=_np.array([[0, 1, 0, 0]], dtype=_np.int32),
            v_weights=_np.array([[0.5, 0.5, 0, 0]], dtype=_np.float32),
            v_wtype=_np.array([3], dtype=_np.uint8), v_sdef=sd)
        out, _ = SK.native_core.deform(base, nrm, model.v_bones,
                                       model.v_weights, model.v_wtype,
                                       rest, world, sd)
        fake = types.SimpleNamespace(model=model, rest_pos=rest)
        back = SK.SkinDeformer._special_blend(fake, base, world,
                                              _np.zeros_like(base))
        radius = float(_np.linalg.norm(out[0]))
        if center is not None:
            # C 非零时，球心本身也被两根骨骼混到别处：半径要相对混合中心量，
            # 否则量到的是世界原点、与 C=0 用例不可比。
            c0 = _np.asarray(center, dtype=_np.float32)
            cblend = 0.5 * (c0 + world[1][:3, :3] @ c0 + world[1][:3, 3])
            radius = float(_np.linalg.norm(out[0] - cblend))
        return (radius, float(_np.linalg.norm(back[0] - out[0])))

    r_rest, d_rest = run([0.5, 0.5, 0.5], 0.0, [1.5, 0.0, 0.0])
    log(" 静止（各向同性 r0=0.5）: 半径=%.4f (期望 1.5000 球面) 回退差=%.6f"
        % (r_rest, d_rest))
    if abs(r_rest - 1.5) > 1e-3:
        anomaly("sdef-rest", "静止姿态应保持球面半径 1.5，实际 %.4f" % r_rest)

    r_iso, d_iso = run([0.5, 0.5, 0.5], 60.0, [1.5, 0.0, 0.0])
    log(" 双骨骼 60 度（各向同性）: 半径=%.4f (期望 1.5000) 回退差=%.6f"
        % (r_iso, d_iso))
    if abs(r_iso - 1.5) > 1e-3:
        anomaly("sdef-iso", "各向同性椭球应保持球面半径，实际 %.4f" % r_iso)

    r_narrow, d_narrow = run([1.0, 0.5, 0.5], 60.0, [1.5, 0.0, 0.0])
    r_wide, d_wide = run([1.0, 2.0, 2.0], 60.0, [1.5, 0.0, 0.0])
    log(" 双骨骼 60 度（Y 窄轴 0.5）: 半径=%.4f (期望 1.1339) 回退差=%.6f"
        % (r_narrow, d_narrow))
    log(" 双骨骼 60 度（Y 宽轴 2.0）: 半径=%.4f (期望 1.6641) 回退差=%.6f"
        % (r_wide, d_wide))
    if abs(r_narrow - 1.1339) > 2e-3:
        anomaly("sdef-axis-narrow", "Y 窄轴时半径应为 1.1339，实际 %.4f" % r_narrow)
    if abs(r_wide - 1.6641) > 2e-3:
        anomaly("sdef-axis-wide", "Y 宽轴时半径应为 1.6641，实际 %.4f" % r_wide)
    if not r_wide > r_narrow:
        anomaly("sdef-monotone", "半轴变长应让半径变大（窄 %.4f / 宽 %.4f）"
                % (r_narrow, r_wide))

    if max(d_rest, d_iso, d_narrow, d_wide) > 1e-4:
        anomaly("sdef-ell-fallback", "Python 回退与原生椭球半径不一致")

    # R0/R1 在 PMX 里存的是「点」：C 非零时半轴应是 |R-C|。把它写成
    # C 平移后的同一组点，半径必须与 C=0 完全一致。
    r_c0, d_c0 = run([0.5, 0.5, 0.5], 60.0, [1.5, 0.0, 0.0])
    # 顶点也跟着 C 一起平移，保证 |v-C| 仍是 1.5，才能与 C=0 逐位对照。
    r_shift, d_shift = run([2.5, 3.5, 4.5], 60.0, [3.5, 3.0, 4.0],
                           center=[2.0, 3.0, 4.0])
    log(" R0/R1 取 |R-C|（C 平移）: 半径=%.4f（对照 %.4f）回退差=%.6f"
        % (r_shift, r_c0, d_shift))
    if abs(r_shift - r_c0) > 1e-4:
        anomaly("sdef-axes-point",
                "R0/R1 应按 |R-C| 取半轴：C=0 时 %.4f、C 平移后 %.4f"
                % (r_c0, r_shift))
    if d_shift > 1e-4:
        anomaly("sdef-axes-point-fb", "C 平移用例的回退与原生不一致")
    H.dump()


def scen_sdefr1():
    """SDEF 的 R1（形变后的椭球半轴）。

    语义：静止方向与当前方向都用同一组半轴度量（R1 优先，全零回退 R0），
    静止时比值恒为 1，所以 R1 不会挪动静止姿态；R1 与 R0 相等时与旧实现
    逐位一致。
    """
    import types
    import numpy as _np
    from pmxeditor import skinning as SK

    log("== SDEF R1 ==")
    nrm = _np.array([[0, 0, 1]], dtype=_np.float32)
    rest = _np.zeros((2, 3), dtype=_np.float32)

    def make_world(deg):
        world = _np.stack([_np.eye(4, dtype=_np.float32)] * 2)
        if deg:
            a = _np.deg2rad(deg)
            world[1] = _np.array([[ _np.cos(a), -_np.sin(a), 0, 0],
                                  [ _np.sin(a),  _np.cos(a), 0, 0],
                                  [0, 0, 1, 0], [0, 0, 0, 1]], dtype=_np.float32)
        return world

    def run(r0, r1, deg, base_pt=(1.5, 0.0, 0.0)):
        base = _np.array([base_pt], dtype=_np.float32)
        world = make_world(deg)
        sd = _np.zeros((1, 9), dtype=_np.float32)
        sd[0, 3:6] = _np.asarray(r0, dtype=_np.float32)
        sd[0, 6:9] = _np.asarray(r1, dtype=_np.float32)
        model = types.SimpleNamespace(
            v_pos=base, v_nrm=nrm,
            v_bones=_np.array([[0, 1, 0, 0]], dtype=_np.int32),
            v_weights=_np.array([[0.5, 0.5, 0, 0]], dtype=_np.float32),
            v_wtype=_np.array([3], dtype=_np.uint8), v_sdef=sd)
        out, _ = SK.native_core.deform(base, nrm, model.v_bones,
                                       model.v_weights, model.v_wtype,
                                       rest, world, sd)
        fake = types.SimpleNamespace(model=model, rest_pos=rest)
        back = SK.SkinDeformer._special_blend(fake, base, world,
                                              _np.zeros_like(base))
        diff = float(_np.linalg.norm(back[0] - out[0]))
        return float(_np.linalg.norm(out[0])), diff, out[0]

    iso, iso_fb, _ = run([1.0, 1.0, 1.0], [0, 0, 0], 60.0)
    log(" R0 各向同性、R1=0（回退 R0）: 半径=%.4f 回退差=%.6f" % (iso, iso_fb))
    if abs(iso - 1.5) > 2e-3:
        anomaly("sdefr1-iso", "各向同性半轴应保持球面半径 1.5，实际 %.4f" % iso)

    r1_only, r1_fb, _ = run([1.0, 1.0, 1.0], [1.0, 2.0, 0.5], 60.0)
    log(" R1=[1,2,0.5] 生效: 半径=%.4f (期望 1.6642) 回退差=%.6f"
        % (r1_only, r1_fb))
    if abs(r1_only - 1.6642) > 3e-3:
        anomaly("sdefr1-active",
                "R1 应改变半径到 1.6642，实际 %.4f" % r1_only)
    if abs(r1_only - iso) < 1e-3:
        anomaly("sdefr1-ignored", "R1 未参与计算（与各向同性结果相同）")

    fb_r0, fb_r0_fb, _ = run([1.0, 2.0, 0.5], [0, 0, 0], 60.0)
    log(" R0=[1,2,0.5]、R1=0（旧数据）: 半径=%.4f 回退差=%.6f"
        % (fb_r0, fb_r0_fb))
    if abs(fb_r0 - 1.6642) > 3e-3:
        anomaly("sdefr1-compat", "R1 全零应回退 R0，实际 %.4f" % fb_r0)

    same, same_fb, _ = run([1.0, 2.0, 0.5], [1.0, 2.0, 0.5], 60.0)
    log(" R1==R0: 半径=%.4f 回退差=%.6f" % (same, same_fb))
    if abs(same - fb_r0) > 1e-4:
        anomaly("sdefr1-identical", "R1==R0 时应与旧实现一致")

    at_rest, rest_fb, _ = run([1.0, 1.0, 1.0], [1.0, 2.0, 0.5], 0.0)
    log(" 静止姿态（R1=[1,2,0.5]）: 半径=%.4f (期望 1.5000) 回退差=%.6f"
        % (at_rest, rest_fb))
    if abs(at_rest - 1.5) > 1e-3:
        anomaly("sdefr1-rest", "R1 不应挪动静止姿态，实际 %.4f" % at_rest)
    if max(iso_fb, r1_fb, fb_r0_fb, same_fb, rest_fb) > 1e-4:
        anomaly("sdefr1-fallback", "Python 回退与原生 R1 半径不一致")
    H.dump()


def scen_ikclamp():
    """IK 限位：欧拉分支连续 + 顶到限位后不再来回抖（native 与回退两条路径）。"""
    from pmxeditor import skinning as SK
    from pmxeditor import pmx as PMX
    import math as _m
    import numpy as _np
    # 1) 奇点附近的等价解选择
    q = SK.euler_to_quat(0.3, 2.0, 0.2)          # 俯仰 2.0 rad 超过 90 度
    prev = (0.3, 2.0, 0.2)
    canon = SK.quat_to_euler(q)
    stable = SK.quat_to_euler_stable(q, prev)
    log(" 奇点: 默认解=%s 稳定解=%s 与上一轮距离 %.3f -> %.3f"
        % (["%.3f" % v for v in canon], ["%.3f" % v for v in stable],
           SK.euler_distance(canon, prev), SK.euler_distance(stable, prev)))
    if SK.euler_distance(stable, prev) > 1e-6:
        anomaly("ik-branch", "稳定解没有保持上一轮的分支")
    if SK.euler_distance(canon, prev) < 1.0:
        anomaly("ik-branch-test", "构造的用例没有触发分支翻转，测试无效")

    m = WIN.doc.model
    ikbone = next((i for i, b in enumerate(m.bones)
                   if (b.flags & PMX.BF_IK) and b.ik and b.ik.links), -1)
    if ikbone < 0:
        anomaly("ik-clamp", "夹具里没有 IK 骨骼")
        H.dump()
        return
    link = m.bones[ikbone].ik.links[0]

    def run(tag):
        # 把 IK 控制器整体推离末端，逼 CCD 一路顶到限位
        pose = SK.Pose(m)
        pose.reset()
        pose.base_trans[ikbone] = _np.array([0.0, 2.2, 0.0], dtype=_np.float32)
        pose._invalidate_world()
        prev_e = None
        worst = 0.0
        outs = 0
        moved = 0.0
        for _ in range(16):
            pose.solve_ik(1)
            cur = SK.quat_to_euler(pose.rot[link.bone])
            if prev_e is not None:
                worst = max(worst, _m.sqrt(SK.euler_distance(cur, prev_e)))
            prev_e = cur
            moved = max(moved, float(_np.abs(pose.rot[link.bone] - SK.IDENTITY_Q).max()))
            if any(abs(cur[k]) > float(link.hi[k]) + 1e-4 for k in range(3)):
                outs += 1
        log(" 限位[%s]: 钳制次数=%d 单轮最大跳变=%.3f rad 越界=%d 旋转量=%.3f 末态=%s"
            % (tag, pose.ik_clamp_hits, worst, outs, moved,
               ["%.3f" % v for v in prev_e]))
        if outs:
            anomaly("ik-clamp", "%s 钳制后仍有角度越过限制（%d 次）" % (tag, outs))
        if worst > 0.6:
            anomaly("ik-jump", "%s 限位处欧拉角单轮跳变过大：%.3f rad" % (tag, worst))
        if moved < 1e-3:
            anomaly("ik-clamp-test", "%s 没有产生旋转，用例无效" % tag)
        return pose, prev_e

    link.limited = True
    link.lo = [-0.35, -0.35, -0.35]
    link.hi = [0.35, 0.35, 0.35]
    native = SK.native_core
    res = {}
    if native is not None:
        res["native"] = run("native")
    SK.native_core = None
    try:
        res["python"] = run("python")
    finally:
        SK.native_core = native
    if res["python"][0].ik_clamp_hits <= 0:
        anomaly("ik-clamp-test", "Python 回退路径没有触发钳制")
    if len(res) == 2:
        d = _m.sqrt(SK.euler_distance(res["native"][1], res["python"][1]))
        log(" native 与回退末态差=%.6f rad" % d)
        if d > 1e-3:
            anomaly("ik-native-mismatch", "native 与回退的限位结果不一致：%.6f" % d)
    link.limited = False
    shot(WIN, "ikclamp")
    H.dump()


def scen_physlazy():
    """结构编辑后不立即构建物理世界；进物理模式才构建。"""
    vp = WIN.viewport
    doc = WIN.doc
    if vp.physics is None or not doc.model.rigid:
        anomaly("physlazy", "物理对象或刚体缺失")
        return
    log("初始: ready=%s pending=%s" % (vp.physics._ready, vp._phys_pending))
    if vp.physics._ready:
        anomaly("physlazy", "载入后不该已经构建物理世界")
    # 结构编辑（新建骨骼）
    t0 = time.time()
    WIN._select_page(1)
    WIN._pages[1]._add()
    pump(120)
    dt = (time.time() - t0) * 1000.0
    log("新建骨骼 %.1f ms: ready=%s pending=%s"
        % (dt, vp.physics._ready, vp._phys_pending))
    if vp.physics._ready:
        anomaly("physlazy", "结构编辑后不该立即构建物理世界")
    if not vp._phys_pending:
        anomaly("physlazy", "结构编辑后应置待建标记")
    # 进物理模式 -> 立刻构建
    t0 = time.time()
    vp.set_physics(True)
    pump(80)
    log("进物理模式 %.1f ms: ready=%s pending=%s"
        % ((time.time() - t0) * 1000.0, vp.physics._ready, vp._phys_pending))
    if not vp.physics._ready:
        anomaly("physlazy", "物理模式应构建物理世界")
    # 撤销（adopt_model 接管新对象，物理惰性）
    WIN.set_physics(False)
    n0 = len(doc.model.bones)
    t0 = time.time()
    doc.undo()
    pump(120)
    log("撤销 %.1f ms: bones %d->%d 接管=%s"
        % ((time.time() - t0) * 1000.0, n0, len(doc.model.bones),
           vp.model is doc.model))
    if vp.model is not doc.model:
        anomaly("physlazy", "撤销后视口未接管新模型对象")
    if vp.physics.enabled:
        anomaly("physlazy", "浏览模式下物理不该在演算")
    shot(WIN, "physlazy")
    H.dump()


def scen_physlive():
    """P1-b：质量/摩擦力热更新——世界不重建，静态刚体被跳过。"""
    vp, doc = WIN.viewport, WIN.doc
    m = doc.model
    pp = WIN._pages[4]
    WIN._select_page(4)
    vp.set_physics(True)          # 物理惰性构建：进物理模式后才建世界
    pump(80)
    ph = vp.physics
    if not ph._ready:
        anomaly("physlive-ready", "物理世界未就绪，无法验证热更新")
        H.dump()
        return
    world = id(ph.world)
    dyn = next((i for i, rb in enumerate(m.rigid) if int(rb.mode) != 0), -1)
    kin = next((i for i, rb in enumerate(m.rigid) if int(rb.mode) == 0), -1)
    log(" 刚体 %d 个（动态首个=%d 运动学首个=%d）" % (len(m.rigid), dyn, kin))
    if dyn < 0:
        anomaly("physlive-dyn", "模型里没有动态刚体")
        H.dump()
        return

    doc.select("rigid", dyn)
    pump(60)
    before = float(m.rigid[dyn].mass)
    pp.rb_mass.setValue(before * 2.0 if before > 0 else 2.0)
    pump(60)
    after = float(WIN.doc.model.rigid[dyn].mass)
    rebuilt = id(vp.physics.world) != world
    log(" 质量 %.3f -> %.3f 世界重建=%s 状态=%r"
        % (before, after, rebuilt, STATUS.text))
    if rebuilt:
        anomaly("physlive-rebuild", "改质量不应重建物理世界")
    if abs(after - before) < 1e-6:
        anomaly("physlive-mass", "质量没有写回模型")

    # 静态/运动学刚体应被 bw_set_body_mass 跳过（返回 False 但不抛异常）
    if kin >= 0:
        ok = vp.physics.set_body_params(kin, mass=1.0)
        log(" 运动学刚体 idx=%d 热更新返回=%s" % (kin, ok))
        if ok:
            anomaly("physlive-kinematic", "运动学刚体不应接受质量热更新")

    doc.undo()
    pump(60)
    log(" 撤销后质量=%.3f 世界重建=%s" % (float(WIN.doc.model.rigid[dyn].mass),
                                          id(vp.physics.world) != world))
    H.dump()


def scen_struct3():
    """P0-a：追加骨骼不应重建 Deformer/物理，删骨骼必须重建，并给出耗时。"""
    import time
    from pmxeditor import doc as DOC
    vp, doc = WIN.viewport, WIN.doc
    m = doc.model
    log("bones=%d rigid=%d joints=%d" % (len(m.bones), len(m.rigid), len(m.joints)))

    def snap():
        return (id(vp.deformer), id(vp.pose), id(vp.physics.world))

    s0 = snap()
    t0 = time.perf_counter()
    doc.edit("新建骨骼", lambda mm: DOC.add_bone(mm, -1), "structure")
    add_ms = (time.perf_counter() - t0) * 1000.0
    pump(60)
    s1 = snap()
    log(" 追加骨骼: %.1f ms deformer重建=%s pose重建=%s physics重建=%s bones=%d"
        % (add_ms, s1[0] != s0[0], s1[1] != s0[1], s1[2] != s0[2], len(doc.model.bones)))
    if s1[0] != s0[0]:
        anomaly("struct-deformer", "追加骨骼不应重建 SkinDeformer（没有顶点引用新骨骼）")
    if s1[2] != s0[2]:
        anomaly("struct-physics", "追加骨骼不应重建物理世界（刚体索引未变）")

    t0 = time.perf_counter()
    doc.undo()
    undo_ms = (time.perf_counter() - t0) * 1000.0
    pump(60)
    s2 = snap()
    log(" 撤销追加: %.1f ms deformer重建=%s physics重建=%s bones=%d"
        % (undo_ms, s2[0] != s1[0], s2[2] != s1[2], len(doc.model.bones)))

    t0 = time.perf_counter()
    doc.edit("删除骨骼", lambda mm: DOC.remove_bone(mm, 3), "structure")
    del_ms = (time.perf_counter() - t0) * 1000.0
    pump(60)
    s3 = snap()
    log(" 删除骨骼: %.1f ms deformer重建=%s pose重建=%s physics重建=%s bones=%d"
        % (del_ms, s3[0] != s2[0], s3[1] != s2[1], s3[2] != s2[2], len(doc.model.bones)))
    if s3[0] == s2[0]:
        anomaly("struct-deformer-del", "删骨骼后 SkinDeformer 必须重建（顶点索引会重排）")
    doc.undo()
    pump(60)
    log(" 复原 bones=%d" % len(doc.model.bones))
    H.dump()


def scen_struct4():
    """P0-b：结构编辑后只刷当前页，其余页切过去再刷，且内容必须是最新的。"""
    from pmxeditor import doc as DOC
    vp, doc, win = WIN.viewport, WIN.doc, WIN
    win._select_page(0)
    pump(60)
    n0 = len(doc.model.bones)
    t0 = time.perf_counter()
    doc.edit("新建骨骼", lambda m: DOC.add_bone(m, -1), "structure")
    ms = (time.perf_counter() - t0) * 1000.0
    pump(60)
    dirty = sorted(win._pages_dirty)
    log(" 编辑后 %.1f ms 脏页=%s 当前页=%d" % (ms, dirty, win._current_page))
    if 0 in dirty:
        anomaly("lazy-current", "当前页不应被标记为脏")
    if not dirty:
        anomaly("lazy-dirty", "其它页面应被标记为脏")

    win._select_page(1)
    pump(80)
    bp = win._pages[1]
    rows = bp.tree.model().rowCount() if bp.tree.model() is not None else -1
    log(" 切到骨骼页：脏页=%s 树顶层行数=%d 骨骼数=%d" % (sorted(win._pages_dirty), rows, len(doc.model.bones)))
    if 1 in win._pages_dirty:
        anomaly("lazy-clear", "切换到该页后应清除脏标记")

    win._select_page(2)
    pump(80)
    mp = win._pages[2]
    log(" 切到材质页：列表行数=%d 材质数=%d" % (mp.list.model().rowCount(), len(doc.model.materials)))
    if mp.list.model().rowCount() != len(doc.model.materials):
        anomaly("lazy-material", "材质页刷新后行数与模型不一致")

    win._select_page(4)
    pump(80)
    pp = win._pages[4]
    log(" 切到物理页：刚体行数=%d 模型刚体=%d" % (pp.list.model().rowCount(), len(doc.model.rigid)))
    if pp.list.model().rowCount() != len(doc.model.rigid):
        anomaly("lazy-physics", "物理页刷新后行数与模型不一致")

    doc.undo()
    pump(80)
    log(" 撤销后 bones=%d（原 %d）" % (len(doc.model.bones), n0))
    if len(doc.model.bones) != n0:
        anomaly("lazy-undo", "撤销未恢复骨骼数")
    H.dump()


def scen_hover():
    """P1-a：射线-胶囊式拾取 + 悬停名称牌。"""
    vp = WIN.viewport
    m = WIN.doc.model
    WIN.set_physics(False)
    pump(80)

    def find_pixel():
        for gy in range(60, vp.height() - 60, 17):
            for gx in range(60, vp.width() - 60, 17):
                kind, index = vp.pick(gx, gy)
                if kind == "bone":
                    return gx, gy, index
        return None

    hit = find_pixel()
    if hit is None:
        anomaly("hover-pick", "扫描全屏未命中任何骨骼")
        H.dump()
        return
    gx, gy, index = hit
    log(" 命中骨骼 idx=%d 于 (%d,%d)" % (index, gx, gy))

    # 悬停：直接投递鼠标移动
    from PyQt5.QtGui import QMouseEvent
    ev = QMouseEvent(QEvent.MouseMove, QPointF(gx, gy), QPointF(gx, gy),
                     Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    vp.mouseMoveEvent(ev)
    vp.repaint()
    pump(60)
    log(" 悬停键=%r 名称=%r 光标=%s" % (vp._hover, vp._hover_text(), vp.cursor().shape()))
    if not vp._hover_text():
        anomaly("hover-text", "悬停命中骨骼但名称牌为空")
    shot(WIN, "hover_tip")

    # 空旷处悬停：名称牌应消失
    ev2 = QMouseEvent(QEvent.MouseMove, QPointF(8, 8), QPointF(8, 8),
                      Qt.NoButton, Qt.NoButton, Qt.NoModifier)
    vp._hover_tick = 0.0
    vp.mouseMoveEvent(ev2)
    log(" 空白悬停键=%r" % vp._hover)
    if vp._hover:
        anomaly("hover-clear", "移出骨骼后悬停状态未清除")
    H.dump()


def scen_flagguard():
    """骨骼标志：可操作/可移动/可旋转在视口里必须真的挡住；物理后变形不被刚体覆盖。"""
    from PyQt5.QtCore import QEvent, QPointF, Qt
    from PyQt5.QtGui import QMouseEvent
    from pmxeditor import skinning as _sk
    from pmxeditor.physics import MMDPhysics
    from pmxeditor.pmx import (BF_AFTER_PHYSICS, BF_ENABLED, BF_ROTATABLE,
                               BF_TRANSLATABLE, BF_VISIBLE)
    np = __import__("numpy")

    path = sys.argv[3] if len(sys.argv) > 3 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "test_model.pmx")
    WIN.open_path(path)
    pump(320)
    doc, vp = WIN.doc, WIN.viewport
    m = doc.model
    if m is None:
        anomaly("flag-model", "模型没有载入")
        H.dump()
        return

    def set_flag(index, flag, on):
        def fn(model):
            b = model.bones[index]
            b.flags = (b.flags | flag) if on else (b.flags & ~flag)
        doc.edit("修改骨骼标志", fn, "bone")
        pump(80)

    def screen_of(index):
        w = vp.pose.world()
        return vp.camera.project(w[index][:3, 3], vp.width(), vp.height())

    def send(kind, x, y, btn, buttons):
        ev = QMouseEvent(kind, QPointF(x, y), QPointF(x, y), QPointF(x, y),
                         btn, buttons, Qt.NoModifier)
        if kind == QEvent.MouseButtonPress:
            vp.mousePressEvent(ev)
        elif kind == QEvent.MouseMove:
            vp.mouseMoveEvent(ev)
        else:
            vp.mouseReleaseEvent(ev)

    idx = -1
    for i, b in enumerate(m.bones):
        need = BF_ROTATABLE | BF_TRANSLATABLE | BF_ENABLED
        if b.ik is None and (b.flags & need) == need:
            idx = i
            break
    if idx < 0:
        anomaly("flag-bone", "找不到可用的测试骨骼")
        H.dump()
        return
    log("测试骨骼 #%d %s flags=0x%04x" % (idx, m.bones[idx].name, m.bones[idx].flags))

    if not screen_of(idx):
        anomaly("flag-screen", "骨骼不在视口内")
        H.dump()
        return
    px, py = 0, 0
    cam0 = (vp.camera.yaw, vp.camera.pitch, vp.camera.target.copy(),
            vp.camera.distance)

    def at():
        """按下前重算屏幕坐标：空白处拖动会转视角，坐标会失效。"""
        q = screen_of(idx) or (0, 0)
        return int(q[0]), int(q[1])

    def restore_cam():
        vp.camera.yaw, vp.camera.pitch = cam0[0], cam0[1]
        vp.camera.target = cam0[2].copy()
        vp.camera.distance = cam0[3]
        vp.update()
        pump(40)

    # 1) 可操作的骨骼能被拾取
    px, py = at()
    kind, hit = vp.pick(px, py)
    log("可操作=开: pick=%s/%d" % (kind, hit))
    if not (kind == "bone" and hit == idx):
        anomaly("flag-pick-on", "可操作骨骼没被拾取到（%s/%d）" % (kind, hit))

    # 2) 关掉可操作 -> 视口里点不到
    set_flag(idx, BF_ENABLED, False)
    px, py = at()
    kind, hit = vp.pick(px, py)
    log("可操作=关: pick=%s/%d" % (kind, hit))
    if kind == "bone" and hit == idx:
        anomaly("flag-operable", "不可操作的骨骼仍能在视口里拾取")
    # 关掉可操作的骨骼也不能被拖动
    trans0 = vp.pose.base_trans.copy()
    send(QEvent.MouseButtonPress, px, py, Qt.LeftButton, Qt.LeftButton)
    send(QEvent.MouseMove, px + 40, py + 20, Qt.NoButton, Qt.LeftButton)
    send(QEvent.MouseButtonRelease, px + 40, py + 20, Qt.LeftButton, Qt.NoButton)
    pump(80)
    if np.any(vp.pose.base_trans != trans0):
        anomaly("flag-operable-move", "不可操作的骨骼仍被拖动了")
    restore_cam()
    set_flag(idx, BF_ENABLED, True)

    # 3) 可移动=开时左键拖动确实位移（对照组）
    restore_cam()
    px, py = at()
    trans0 = vp.pose.base_trans[idx].copy()
    send(QEvent.MouseButtonPress, px, py, Qt.LeftButton, Qt.LeftButton)
    send(QEvent.MouseMove, px + 40, py + 10, Qt.NoButton, Qt.LeftButton)
    send(QEvent.MouseButtonRelease, px + 40, py + 10, Qt.LeftButton, Qt.NoButton)
    pump(120)
    moved = float(np.abs(vp.pose.base_trans[idx] - trans0).sum())
    log("可移动=开: 位移量=%.5f" % moved)
    if moved < 1e-5:
        anomaly("flag-move-on", "可移动骨骼左键拖动没有位移（%.6f）" % moved)

    # 4) 关掉可移动 -> 左键拖动不动
    restore_cam()
    set_flag(idx, BF_TRANSLATABLE, False)
    px, py = at()
    trans1 = vp.pose.base_trans.copy()
    send(QEvent.MouseButtonPress, px, py, Qt.LeftButton, Qt.LeftButton)
    send(QEvent.MouseMove, px + 40, py + 10, Qt.NoButton, Qt.LeftButton)
    send(QEvent.MouseButtonRelease, px + 40, py + 10, Qt.LeftButton, Qt.NoButton)
    pump(80)
    if np.any(vp.pose.base_trans != trans1):
        anomaly("flag-translatable", "不可移动的骨骼仍被左键拖动了")
    set_flag(idx, BF_TRANSLATABLE, True)

    # 5) 可旋转=开时右键拖动确实旋转（对照组）
    restore_cam()
    px, py = at()
    rot0 = vp.pose.base_rot[idx].copy()
    send(QEvent.MouseButtonPress, px, py, Qt.RightButton, Qt.RightButton)
    send(QEvent.MouseMove, px + 40, py + 20, Qt.NoButton, Qt.RightButton)
    send(QEvent.MouseButtonRelease, px + 40, py + 20, Qt.RightButton, Qt.NoButton)
    pump(120)
    turned = float(np.abs(vp.pose.base_rot[idx] - rot0).sum())
    log("可旋转=开: 旋转量=%.5f" % turned)
    if turned < 1e-5:
        anomaly("flag-rotate-on", "可旋转骨骼右键拖动没有旋转（%.6f）" % turned)

    # 6) 关掉可旋转 -> 右键拖动不转
    set_flag(idx, BF_ROTATABLE, False)
    px, py = at()
    rot1 = vp.pose.base_rot.copy()
    send(QEvent.MouseButtonPress, px, py, Qt.RightButton, Qt.RightButton)
    send(QEvent.MouseMove, px + 40, py + 20, Qt.NoButton, Qt.RightButton)
    send(QEvent.MouseButtonRelease, px + 40, py + 20, Qt.RightButton, Qt.NoButton)
    pump(80)
    if np.any(vp.pose.base_rot != rot1):
        anomaly("flag-rotatable", "不可旋转的骨骼仍被右键拖转了")
    set_flag(idx, BF_ROTATABLE, True)

    # 7) 显示=False 的骨骼也不该被拾取
    restore_cam()
    set_flag(idx, BF_VISIBLE, False)
    px, py = at()
    kind, hit = vp.pick(px, py)
    log("显示=关: pick=%s/%d" % (kind, hit))
    if kind == "bone" and hit == idx:
        anomaly("flag-visible", "隐藏的骨骼仍能被拾取")
    set_flag(idx, BF_VISIBLE, True)

    # 8) 物理后变形：刚体不再覆盖该骨骼，取消后恢复覆盖
    phys = MMDPhysics()
    if not phys.build(m):
        log("物理不可用（%s），跳过物理后变形检查" % phys.error)
        H.dump()
        return
    phys.enabled = True
    driven = []
    for bi, bone in enumerate(phys.bone_of_body):
        if bone >= 0 and phys.modes[bi] != 0 and bone not in driven:
            driven.append(bone)
    log("刚体驱动的骨骼 %d 根: %s" % (len(driven), driven[:6]))
    if not driven:
        log("没有动态刚体绑定的骨骼，跳过物理后变形检查")
        phys.release()
        H.dump()
        return

    def overridden(bone_index):
        pose = _sk.Pose(m)
        pose.apply({}, m.morphs)
        for _ in range(4):
            phys.step(pose, 1.0 / 60.0, {}, m.morphs)
            pose.apply({}, m.morphs)
        return bone_index in pose.ov_rot

    target = driven[0]
    had = overridden(target)
    log("骨骼 #%d 默认被刚体覆盖=%r" % (target, had))
    set_flag(target, BF_AFTER_PHYSICS, True)
    after = overridden(target)
    log("骨骼 #%d 物理后变形=开 被刚体覆盖=%r" % (target, after))
    if had and after:
        anomaly("flag-after-physics", "物理后变形的骨骼仍被刚体覆盖")
    set_flag(target, BF_AFTER_PHYSICS, False)
    back = overridden(target)
    log("骨骼 #%d 物理后变形=关 被刚体覆盖=%r" % (target, back))
    if had and not back:
        anomaly("flag-after-physics-off", "取消物理后变形后刚体没有恢复覆盖")
    phys.release()

    WIN._select_page(1)
    pump(180)
    H.shot(WIN, "flagguard")
    H.dump()


def scen_frame():
    """表示枠与 IK 链的可编辑性（数据 + 面板两条路径）。"""
    import math

    win = WIN
    doc = win.doc
    m = doc.model
    if not m:
        anomaly("frame-nomodel", "没有模型")
        dump()
        return
    win._select_page(6)
    pump(120)
    page = win._pages[6]
    n0 = len(m.frames)
    page._add()
    pump(40)
    n1 = len(m.frames)
    if n1 != n0 + 1:
        anomaly("frame-add", "表示枠数量 %d -> %d" % (n0, n1))
        dump()
        return
    doc.select("frame", n1 - 1)
    page.select("frame", n1 - 1)
    page.name_edit.setText("测试枠")
    page._name_changed()
    pump(30)
    if m.frames[n1 - 1].name != "测试枠":
        anomaly("frame-name", "名字 = %r" % (m.frames[n1 - 1].name,))
    page._add_bone_item()
    page._add_bone_item()
    pump(40)
    items = list(m.frames[n1 - 1].items)
    if len(items) != 2 or items[0][0] != 0:
        anomaly("frame-items", "项目 = %r" % (items,))
    else:
        page._move_item(1)
        pump(30)
        swapped = list(m.frames[n1 - 1].items)
        if swapped[0] != items[1] or swapped[1] != items[0]:
            anomaly("frame-item-move", "顺序 = %r" % (swapped,))
        page._remove_item()
        pump(30)
        if len(m.frames[n1 - 1].items) != 1:
            anomaly("frame-item-remove", "剩余 %d" % len(m.frames[n1 - 1].items))
    if m.morphs:
        page._add_morph_item()
        pump(30)
        kinds = [it[0] for it in m.frames[n1 - 1].items]
        if 1 not in kinds:
            anomaly("frame-morph-item", "项目 = %r" % (kinds,))
    if n1 - 1 > 0:
        page._move_frame(-1)
        pump(30)
        if m.frames[n1 - 2].name != "测试枠":
            anomaly("frame-move", "位置不对")
    idx = [i for i, f in enumerate(m.frames) if f.name == "测试枠"]
    if idx:
        page.select("frame", idx[0])
        page._remove()
        pump(80)
        if len(m.frames) != n0:
            anomaly("frame-remove", "数量 %d != %d" % (len(m.frames), n0))
    shot(win, "frame_page")

    bp = win._pages[1]
    win._select_page(1)
    pump(60)
    target = None
    for i, b in enumerate(m.bones):
        if b.ik is not None:
            target = i
            break
    if target is None:
        target = 0
    bp.select("bone", target)
    pump(40)
    bp.ik_sw.setChecked(True)
    pump(80)
    b = m.bones[target]
    if b.ik is None:
        anomaly("ik-enable", "IK 没有建立")
        dump()
        return
    k0 = len(b.ik.links)
    if bp.ik_link_combo.count():
        bp.ik_link_combo.setCurrentIndex(0)
        bp._ik_link_add()
        pump(80)
        b = m.bones[target]
        if len(b.ik.links) != k0 + 1:
            anomaly("ik-link-add", "链接 %d -> %d" % (k0, len(b.ik.links)))
        else:
            bp.ik_links.setCurrentRow(len(b.ik.links) - 1)
            pump(40)
            bp.link_limit_sw.setChecked(True)
            pump(60)
            b = m.bones[target]
            if not b.ik.links[-1].limited:
                anomaly("ik-link-limit", "limited 未写入")
            bp.link_lo.spins[0].setValue(-30.0)
            bp.link_lo.spins[1].setValue(-10.0)
            pump(80)
            b = m.bones[target]
            if abs(b.ik.links[-1].lo[0] - math.radians(-30.0)) > 1e-4:
                anomaly("ik-link-range", "lo = %r" % (b.ik.links[-1].lo,))
            bp._ik_link_del()
            pump(80)
            b = m.bones[target]
            if len(b.ik.links) != k0:
                anomaly("ik-link-del", "剩余 %d" % len(b.ik.links))
    shot(win, "ik_chain")

    # 往返读写
    path = os.path.join(H.ROOT, "tests", "frame_rt.pmx")
    from pmxeditor.pmx import load_pmx as _pmx_load, save_pmx as _pmx_save
    _pmx_save(m, path)
    back = _pmx_load(path)
    if len(back.frames) != len(m.frames):
        anomaly("frame-roundtrip", "枠 %d != %d" % (len(back.frames), len(m.frames)))
    bi = back.bones[target].ik
    if (bi is None) != (m.bones[target].ik is None):
        anomaly("ik-roundtrip", "IK 状态不一致")
    log("[frame] 表示枠 / IK 链编辑通过：frames=%d links=%d"
        % (len(m.frames), len(m.bones[target].ik.links) if m.bones[target].ik else 0))


def scen_morph_edit():
    """形态偏移编辑：目标/数值、添加/删除、往返。"""
    win = WIN
    doc = win.doc
    m = doc.model
    if not m:
        anomaly("medit-nomodel", "没有模型")
        dump()
        return
    page = win._pages[3]
    win._select_page(3)
    pump(80)

    def pick(t):
        for i, mo in enumerate(m.morphs):
            if mo.type == t:
                return i
        return -1

    vi = pick(1)
    if vi < 0:
        log("[morph-edit] 没有顶点形态，跳过顶点部分")
    else:
        page.select("morph", vi)
        page.refresh()
        pump(60)
        if not m.morphs[vi].offsets:
            page._add_offset()
            pump(80)
            if len(m.morphs[vi].offsets) != 1:
                anomaly("medit-add", "偏移 %d" % len(m.morphs[vi].offsets))
        page.offset_table.setCurrentCell(0, 0)
        pump(40)
        spins = page._off_widgets.get("offset")
        if not spins:
            anomaly("medit-form", "编辑器缺少 offset 字段")
        else:
            spins[0].setValue(0.25)
            spins[0].editingFinished.emit()
            pump(80)
            val = m.morphs[vi].offsets[0].get("offset")
            if abs(float(val[0]) - 0.25) > 1e-5:
                anomaly("medit-value", "offset[0] = %r" % (val,))
        n0 = len(m.morphs[vi].offsets)
        page._add_offset()
        pump(80)
        if len(m.morphs[vi].offsets) != n0 + 1:
            anomaly("medit-add2", "偏移 %d != %d" % (len(m.morphs[vi].offsets), n0 + 1))
        page.offset_table.setCurrentCell(len(m.morphs[vi].offsets) - 1, 0)
        pump(30)
        page._del_offset()
        pump(80)
        if len(m.morphs[vi].offsets) != n0:
            anomaly("medit-del", "偏移 %d != %d" % (len(m.morphs[vi].offsets), n0))

    mi = pick(8)
    if mi >= 0 and m.morphs[mi].offsets:
        page.select("morph", mi)
        page.refresh()
        pump(60)
        page.offset_table.setCurrentCell(0, 0)
        pump(40)
        spins = page._off_widgets.get("diffuse")
        if not spins:
            anomaly("medit-mat-form", "材质偏移缺少 diffuse")
        else:
            spins[0].setValue(0.75)
            spins[0].editingFinished.emit()
            pump(80)
            d = m.morphs[mi].offsets[0].get("diffuse")
            if abs(float(d[0]) - 0.75) > 1e-5:
                anomaly("medit-mat-value", "diffuse = %r" % (d,))
        combo = page._off_widgets.get("calc")
        if combo is not None:
            combo.setCurrentIndex(1)
            pump(80)
            if int(m.morphs[mi].offsets[0].get("calc", 0)) != 1:
                anomaly("medit-calc", "calc = %r" % (m.morphs[mi].offsets[0].get("calc"),))
    shot(win, "morph_edit")

    path = os.path.join(H.ROOT, "tests", "morph_rt.pmx")
    from pmxeditor.pmx import load_pmx as _pmx_load, save_pmx as _pmx_save
    count = len(m.morphs)
    _pmx_save(m, path)
    back = _pmx_load(path)
    if len(back.morphs) != count:
        anomaly("medit-roundtrip", "%d != %d" % (len(back.morphs), count))
    log("[morph-edit] 形态偏移编辑通过：morphs=%d" % count)
