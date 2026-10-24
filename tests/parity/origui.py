# -*- coding: utf-8 -*-
"""原版 PmxEditor 的 ui 层封装（只使用跨进程安全的消息，绝不下发带指针的消息）。"""
import sys, time, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import origlib as O
import win32gui, win32api, win32con, win32process

MODEL = r"D:\Project\MMD\02_模型库\KARU式Rabbit Hole MIKU.ver 1.5_by_KR-SAM_141b6a51e3ad47ff26d0910dd71e3a71\KARU式Rabbit Hole MIKU.ver 1.6.pmx"
WORK = r"D:\Project\PmxEditor_Modern\tests\parity\work"
SHOTS = r"D:\Project\PmxEditor_Modern\tests\parity\shots"
for d in (WORK, SHOTS):
    os.makedirs(d, exist_ok=True)


def pid():
    for h, p, t, rc in O.find_windows():
        if t.startswith("Pmx") and "Harness" not in t:
            return p
    return None


def _wins():
    p = pid()
    return O.find_windows(pid=p) if p else []


def editor():
    for h, p, t, rc in _wins():
        if not win32gui.GetClassName(h).startswith("WindowsForms10.Window"):
            continue
        if "View" in t or "CSScript" in t or "エラー" in t or "插件" in t:
            continue
        if ("編" in t) or ("编" in t) or t.strip() == "Pmx":
            return h
    return None


def view():
    for h, p, t, rc in _wins():
        if t.startswith("PmxView"):
            return h
    return None


def alive():
    return editor() is not None


def start():
    if alive():
        return True
    import subprocess
    subprocess.Popen([O.ORIG_EXE], cwd=O.ORIG_DIR)
    for _ in range(60):
        time.sleep(0.5)
        if alive():
            time.sleep(2.0)
            layout()
            return True
    return False


def layout():
    e, v = editor(), view()
    if e:
        O.set_pos(e, 20, 20, 1400, 1300)
    if v:
        O.set_pos(v, 1440, 20, 820, 820)
    time.sleep(0.6)


def kids(h):
    out = []
    win32gui.EnumChildWindows(h, lambda k, p: out.append(k) or True, None)
    return out


def controls(root=None, visible_only=False):
    root = root or editor()
    res = []
    for h in kids(root):
        try:
            cls = win32gui.GetClassName(h)
            txt = win32gui.GetWindowText(h)
            rc = win32gui.GetWindowRect(h)
            vis = win32gui.IsWindowVisible(h)
        except Exception:
            continue
        if visible_only and not vis:
            continue
        res.append({"hwnd": h, "cls": cls.split(".")[0] if not cls.startswith("WindowsForms") else cls.split(".")[1],
                    "text": txt, "rect": rc, "vis": bool(vis)})
    return res


def open_model(path=MODEL, tries=4):
    """Ctrl+O 打开模型；对话框没弹出时重试（原版偶发不响应）。"""
    base = os.path.basename(path)[:8]
    for _k in range(tries):
        e = editor()
        O.focus(e)
        time.sleep(0.35)
        O.key("esc")
        time.sleep(0.15)
        O.hotkey("ctrl", "o")
        dlg = None
        for _ in range(25):
            time.sleep(0.2)
            hits = O.find_windows("打开")
            if hits:
                dlg = hits[0][0]
                break
            if dialog_windows():          # 「是否保存修改」之类，先答否
                answer_dialog()
        if dlg is None:
            continue
        ks = kids(dlg)
        edt = [h for h in ks if win32gui.GetClassName(h) == "Edit"]
        btn = [h for h in ks if win32gui.GetClassName(h) == "Button"
               and "打开" in win32gui.GetWindowText(h)]
        if not edt or not btn:
            continue
        win32api.SendMessage(edt[0], win32con.WM_SETTEXT, 0, path)
        time.sleep(0.25)
        win32api.SendMessage(btn[0], win32con.BM_CLICK, 0, 0)
        for i in range(60):
            time.sleep(0.5)
            if not O.find_windows("打开") and base in win32gui.GetWindowText(editor()):
                break
        time.sleep(2.2)
        return i * 0.5
    raise RuntimeError("打开模型对话框未出现（%d 次尝试）" % tries)


def tabctl():
    for h in kids(editor()):
        if "SysTabControl32" in win32gui.GetClassName(h):
            return h
    return None


def pages():
    t = tabctl()
    res = []
    for h in kids(t):
        if win32gui.GetClassName(h).startswith("WindowsForms10.Window"):
            txt = win32gui.GetWindowText(h)
            if txt:
                res.append((txt, h, win32gui.IsWindowVisible(h), win32gui.GetWindowRect(h)))
    return res


def visible_page():
    for txt, h, vis, rc in pages():
        if vis:
            return txt, h, rc
    return None, None, None


def tab_scan(y=140, x0=40, x1=1000, step=8):
    """返回 [(x, 页面名)] 的变化点。"""
    e = editor()
    O.focus(e)
    seen, prev = [], None
    for x in range(x0, x1, step):
        O.click(x, y)
        time.sleep(0.30)
        t = visible_page()[0]
        if t != prev:
            seen.append((x, t))
            prev = t
    return seen


def click_tab(name, table=None):
    table = table or json.load(open(os.path.join(os.path.dirname(__file__), "tabs.json"), "r", encoding="utf8"))
    for x, t in table:
        if t == name:
            O.click(x, 140)
            time.sleep(0.4)
            return True
    return False


def shot(name, window="editor"):
    h = editor() if window == "editor" else view()
    O.focus(h)
    time.sleep(0.3)
    O.shot(os.path.join(SHOTS, name + ".png"), O.win_box(h))
    return os.path.join(SHOTS, name + ".png")


FILE_MENU = {"新建制作": (160, 147), "打开": (160, 188), "另存为": (160, 245), "保存": (160, 288),
             "保存时处理": (160, 325), "载入": (160, 365), "导出": (160, 405),
             "锚点数据自动载入/保存": (160, 453), "打开其他窗口": (160, 493),
             "关于文件夹": (160, 533), "文本(CSV)变换": (160, 573),
             "验证PMX数据的状态": (160, 613)}


def get_text(hwnd, n=8192):
    """跨进程安全读取控件文本（WM_GETTEXT 由系统封送）。"""
    import ctypes
    buf = ctypes.create_unicode_buffer(n)
    win32api.SendMessage(hwnd, win32con.WM_GETTEXT, n, buf)
    return buf.value


def menu_file(item="另存为", pause=1.0):
    e = editor()
    O.focus(e)
    time.sleep(0.3)
    O.click(56, 106)
    time.sleep(pause)
    x, y = FILE_MENU[item]
    O.click(x, y)
    time.sleep(1.4)


def save_as(path, timeout=40):
    """文件→另存为→填路径→保存。返回 (成功, 说明)。"""
    if os.path.exists(path):
        os.remove(path)
    # 关掉可能残留的「只有一个确定按钮」的另存为提示窗
    for h, p, t, rc in O.find_windows(pid=pid()):
        if "另存" in t:
            b = [k for k in kids(h) if win32gui.GetClassName(k) == "Button"]
            if b and not any(win32gui.GetClassName(k) == "Edit" for k in kids(h)):
                win32api.SendMessage(b[0], win32con.BM_CLICK, 0, 0)
                time.sleep(0.4)
    menu_file("另存为")
    wins = O.find_windows("另存为")
    if not wins:
        return False, "另存为对话框未出现"
    dlg = None
    for h, p, t, rc in wins:
        ks = kids(h)
        if any(win32gui.GetClassName(k) == "Edit" for k in ks):
            dlg = h
            break
    if dlg is None:
        return False, "找不到文件名输入框"
    ks = kids(dlg)
    edt = [h for h in ks if win32gui.GetClassName(h) == "Edit"]
    win32api.SendMessage(edt[0], win32con.WM_SETTEXT, 0, path)
    time.sleep(0.3)
    btns = [h for h in ks if win32gui.GetClassName(h) == "Button" and "保存" in win32gui.GetWindowText(h)]
    if not btns:
        return False, "找不到保存按钮"
    win32api.SendMessage(btns[0], win32con.BM_CLICK, 0, 0)
    for i in range(int(timeout * 2)):
        time.sleep(0.5)
        extra = [(win32gui.GetClassName(h), win32gui.GetWindowText(h)) for h, p, t, rc in O.find_windows(pid=pid())]
        names = [t for c, t in extra]
        if any("覆盖" in t or "确认" in t for t in names):
            h = [h for h, p, t, rc in O.find_windows(pid=pid()) if "覆盖" in t or "确认" in t][0]
            bs = [k for k in kids(h) if win32gui.GetClassName(k) == "Button"]
            if bs:
                win32api.SendMessage(bs[0], win32con.BM_CLICK, 0, 0)
            continue
        if any("保存" in t or "选项" in t for t in names):
            h = [h for h, p, t, rc in O.find_windows(pid=pid()) if "保存" in t or "选项" in t][0]
            if h != editor():
                bs = [k for k in kids(h) if win32gui.GetClassName(k) == "Button"]
                if bs:
                    win32api.SendMessage(bs[-1], win32con.BM_CLICK, 0, 0)
                continue
        if os.path.exists(path) and os.path.getsize(path) > 1000:
            time.sleep(0.8)
            return True, "ok %.1fs" % (i * 0.5)
    return os.path.exists(path), "超时"

def rcenter(rect):
    l, t, r, b = rect
    return ((l + r) // 2, (t + b) // 2)

# ---------------------------------------------------------------- 对话框处理
def dialog_windows():
    return [h for h, _p, _t, _r in O.find_windows(pid=pid())
            if win32gui.GetClassName(h) == "#32770"]


def dialog_buttons(h):
    return [(c["hwnd"], c["text"], c["rect"]) for c in controls(h, visible_only=True)
            if c["cls"] in ("Button",)]


def answer_dialog(words=("否", "いいえ", "取消", "キャンセル", "OK", "确定")):
    """点掉原版弹出的确认框（如「是否保存修改」选否）。"""
    for h in dialog_windows():
        for hwnd, txt, rc in dialog_buttons(h):
            for w in words:
                if w in txt:
                    win32api.SendMessage(hwnd, win32con.BM_CLICK, 0, 0)
                    time.sleep(0.5)
                    return txt
    return None
