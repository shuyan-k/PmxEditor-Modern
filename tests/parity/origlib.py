# -*- coding: utf-8 -*-
"""原版 PmxEditor（WinForms/Direct3D）窗口与输入自动化小工具。"""
import ctypes, time, subprocess, os
from ctypes import wintypes
import win32gui, win32api, win32con, win32process, win32clipboard

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.SetProcessDPIAware()  # 本进程使用物理像素坐标（截图也是物理像素）

ORIG_DIR = r"D:\Project\MMD\05_工具\PmxEditor (MMD模型编辑器）"
ORIG_EXE = os.path.join(ORIG_DIR, "PmxEditor_x64.exe")


def find_windows(title_sub=None, pid=None):
    out = []
    def cb(h, p):
        if not win32gui.IsWindowVisible(h):
            return True
        t = win32gui.GetWindowText(h)
        _, wpid = win32process.GetWindowThreadProcessId(h)
        if pid is not None and wpid != pid:
            return True
        if title_sub is not None and title_sub not in t:
            return True
        out.append((h, wpid, t, win32gui.GetWindowRect(h)))
        return True
    win32gui.EnumWindows(cb, None)
    return out


def children(hwnd, depth=0, out=None):
    out = [] if out is None else out
    try:
        kids = win32gui.EnumChildWindows(hwnd, lambda h, p: out.append((h, depth)) or True, None)
    except Exception:
        pass
    return out


def tree(hwnd, maxdepth=6):
    res = []
    def walk(h, d):
        if d > maxdepth:
            return
        try:
            cls = win32gui.GetClassName(h)
            txt = win32gui.GetWindowText(h)
            rc = win32gui.GetWindowRect(h)
            vis = win32gui.IsWindowVisible(h)
            en = win32gui.IsWindowEnabled(h)
        except Exception:
            return
        res.append(("  " * d) + f"[{h:#x}] {cls.split('.')[0]}:{cls.split('.')[1] if '.' in cls else ''} '{txt}' {rc} vis={int(vis)} en={int(en)}")
        def cb(k, p):
            walk(k, d + 1)
            return True
        try:
            win32gui.EnumChildWindows(h, cb, None)
        except Exception:
            pass
    walk(hwnd, 0)
    return res


def rect(hwnd):
    return win32gui.GetWindowRect(hwnd)


def center(hwnd):
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    return ((l + r) // 2, (t + b) // 2)


def set_pos(hwnd, x, y, w, h):
    win32gui.SetWindowPos(hwnd, win32con.HWND_TOP, x, y, w, h,
                          win32con.SWP_SHOWWINDOW | win32con.SWP_NOACTIVATE)


def focus(hwnd):
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    except Exception:
        pass
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        # 前台锁定时用 AttachThreadInput 兜底
        fg = win32gui.GetForegroundWindow()
        tid = win32process.GetWindowThreadProcessId(fg)[0]
        cur = win32api.GetCurrentThreadId()
        user32.AttachThreadInput(tid, cur, True)
        try:
            win32gui.SetForegroundWindow(hwnd)
        finally:
            user32.AttachThreadInput(tid, cur, False)
    time.sleep(0.1)


# ---------- 输入 ----------
def click(x, y, button="left", double=False, delay=0.05):
    win32api.SetCursorPos((int(x), int(y)))
    time.sleep(0.03)
    down = win32con.MOUSEEVENTF_LEFTDOWN if button == "left" else win32con.MOUSEEVENTF_RIGHTDOWN
    up = win32con.MOUSEEVENTF_LEFTUP if button == "left" else win32con.MOUSEEVENTF_RIGHTUP
    n = 2 if double else 1
    for _ in range(n):
        win32api.mouse_event(down, 0, 0, 0, 0)
        time.sleep(0.02)
        win32api.mouse_event(up, 0, 0, 0, 0)
        time.sleep(delay)


def click_hwnd(hwnd, button="left", double=False):
    x, y = center(hwnd)
    click(x, y, button=button, double=double)


def drag(x1, y1, x2, y2, button="left", steps=12, settle=0.15):
    win32api.SetCursorPos((int(x1), int(y1)))
    time.sleep(0.05)
    down = win32con.MOUSEEVENTF_LEFTDOWN if button == "left" else win32con.MOUSEEVENTF_RIGHTDOWN
    up = win32con.MOUSEEVENTF_LEFTUP if button == "left" else win32con.MOUSEEVENTF_RIGHTUP
    win32api.mouse_event(down, 0, 0, 0, 0)
    for i in range(1, steps + 1):
        win32api.SetCursorPos((int(x1 + (x2 - x1) * i / steps), int(y1 + (y2 - y1) * i / steps)))
        time.sleep(0.02)
    time.sleep(0.03)
    win32api.mouse_event(up, 0, 0, 0, 0)
    time.sleep(settle)


def wheel(x, y, notches):
    win32api.SetCursorPos((int(x), int(y)))
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, int(notches * 120), 0)
    time.sleep(0.15)


VK = {"ctrl": win32con.VK_CONTROL, "shift": win32con.VK_SHIFT, "alt": win32con.VK_MENU,
      "enter": win32con.VK_RETURN, "esc": win32con.VK_ESCAPE, "tab": win32con.VK_TAB,
      "del": win32con.VK_DELETE, "home": win32con.VK_HOME, "end": win32con.VK_END,
      "left": win32con.VK_LEFT, "right": win32con.VK_RIGHT, "up": win32con.VK_UP, "down": win32con.VK_DOWN,
      "f5": win32con.VK_F5, "space": win32con.VK_SPACE}


def key(name):
    vk = VK.get(name.lower())
    if vk is None:
        vk = ord(name.upper())
    win32api.keybd_event(vk, 0, 0, 0)
    time.sleep(0.02)
    win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.08)


def hotkey(*names):
    vks = [VK.get(n.lower(), ord(n.upper()) if len(n) == 1 else 0) for n in names]
    for vk in vks:
        win32api.keybd_event(vk, 0, 0, 0)
        time.sleep(0.02)
    for vk in reversed(vks):
        win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
        time.sleep(0.02)
    time.sleep(0.12)


def type_text(text):
    """通过剪贴板输入（支持中文/日文）。"""
    for ch in (win32clipboard.CF_UNICODETEXT,):
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, ch)
        finally:
            win32clipboard.CloseClipboard()
    time.sleep(0.05)
    hotkey("ctrl", "v")


def send_text_ctrl(hwnd, text):
    win32api.SendMessage(hwnd, win32con.WM_SETTEXT, 0, text)


def bm_click(hwnd):
    win32api.SendMessage(hwnd, win32con.BM_CLICK, 0, 0)


# ---------- 截图 ----------
def shot(path, box=None):
    """box 为物理像素 (l,t,r,b)，None 则全屏。"""
    from PIL import ImageGrab
    im = ImageGrab.grab(bbox=box, all_screens=True) if box else ImageGrab.grab(all_screens=True)
    im.save(path)
    return im


def win_box(hwnd):
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    return (l, t, r, b)


def shot_window(hwnd, path):
    """把窗口置前，截其屏幕区域。"""
    focus(hwnd)
    time.sleep(0.25)
    l, t, r, b = win32gui.GetWindowRect(hwnd)
    return shot(path, (l, t, r, b))


def launch_orig():
    p = subprocess.Popen([ORIG_EXE], cwd=ORIG_DIR)
    for _ in range(60):
        time.sleep(0.5)
        if find_windows("Pmx", pid=p.pid):
            break
    time.sleep(2.0)
    return p


def close_orig(proc):
    for h, wpid, t, rc in find_windows(pid=proc.pid):
        try:
            win32api.PostMessage(h, win32con.WM_CLOSE, 0, 0)
        except Exception:
            pass
    time.sleep(1.0)
    try:
        proc.terminate()
    except Exception:
        pass
