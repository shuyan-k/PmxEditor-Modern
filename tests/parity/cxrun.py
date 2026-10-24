import sys, os, time
sys.path.insert(0, r"tests/parity")
import win32gui, win32process, win32con, win32clipboard, win32api
import origui as U, origlib as O

LOG = r"D:\Project\PmxEditor_Modern\tests\parity\cx_log.txt"
FORM_POS = (1550, 250, 1550, 1200)
EDITOR_PT = (2000, 700)
RUN_PT = (2888, 1162)


def hwnds(pid=None):
    pid = pid or U.pid()
    out = []
    def cb(h, _):
        if win32gui.IsWindowVisible(h) and win32process.GetWindowThreadProcessId(h)[1] == pid:
            t = win32gui.GetWindowText(h)
            if t:
                out.append((h, t))
        return True
    win32gui.EnumWindows(cb, None)
    return out


def form():
    for h, t in hwnds():
        if t == "CSScript":
            return h
    return None


def open_form():
    h = form()
    if h:
        return h
    e = U.editor()
    O.focus(e)
    time.sleep(0.3)
    O.key("esc")
    time.sleep(0.3)
    O.click(205, 106)
    time.sleep(0.7)
    O.key("p")
    time.sleep(0.9)
    O.key("right")
    time.sleep(0.9)
    O.key("enter")
    time.sleep(2.0)
    h = form()
    if not h:
        raise RuntimeError("CSScript 窗体没有出现")
    O.set_pos(h, *FORM_POS)
    time.sleep(0.6)
    return h


def set_clip(text):
    for _ in range(6):
        try:
            win32clipboard.OpenClipboard()
            break
        except Exception:
            time.sleep(0.2)
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


def run_code(path=None, code=None, wait=6.0, clear_log=True):
    if clear_log and os.path.exists(LOG):
        os.remove(LOG)
    if code is None:
        with open(path, "r", encoding="utf-8-sig") as f:
            code = f.read()
    h = open_form()
    O.focus(h)
    time.sleep(0.4)
    O.click(*EDITOR_PT)
    time.sleep(0.3)
    set_clip(code)
    time.sleep(0.2)
    O.hotkey("ctrl", "a")
    time.sleep(0.2)
    O.hotkey("ctrl", "v")
    time.sleep(0.6)
    O.click(*RUN_PT)
    t0 = time.time()
    while time.time() - t0 < wait:
        time.sleep(0.3)
        if os.path.exists(LOG):
            time.sleep(0.3)
            break
    if not os.path.exists(LOG):
        return None
    with open(LOG, "r", encoding="utf-8-sig") as f:
        return f.read()


if __name__ == "__main__":
    print(run_code(r"tests\parity\cx\01_inventory.cs"))
