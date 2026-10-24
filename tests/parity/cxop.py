import sys, os, time
sys.path.insert(0, r"tests/parity")
import win32gui
import origui as U, origlib as O, cxrun, pmxsem as P

WORK = r"D:\Project\PmxEditor_Modern\tests\parity\work"
CX = r"D:\Project\PmxEditor_Modern\tests\parity\cx"
TAIL = ("connect.Pmx.Update(pmx);\n"
        "connect.Form.UpdateList(UpdateObject.All);\n"
        "connect.View.PMDView.UpdateModel();\n"
        "connect.View.PMDView.UpdateView();\n"
        'System.IO.File.WriteAllText(@"D:\\Project\\PmxEditor_Modern\\tests\\parity\\cx_log.txt",'
        ' "done", System.Text.Encoding.UTF8);')


def body(op):
    with open(os.path.join(CX, "op_%s.cs" % op), "r", encoding="utf-8-sig") as f:
        return f.read()


def run(op, save=True):
    cxrun.RUN_PT = (2974, 1250)
    cxrun.EDITOR_PT = (2300, 700)
    for _ in range(3):
        if U.dialog_windows():
            U.answer_dialog()
            time.sleep(0.4)
    U.open_model()
    time.sleep(0.8)
    out = cxrun.run_code(code=body(op) + "\n" + TAIL + "\n")
    if out is None:
        raise RuntimeError("脚本没有执行完（编译或运行失败）")
    if not save:
        return out
    h = cxrun.form()
    if h:
        win32gui.ShowWindow(h, 6)
    time.sleep(0.4)
    O.focus(U.editor())
    time.sleep(0.6)
    path = os.path.join(WORK, "%s_cx.pmx" % op)
    ok, why = U.save_as(path)
    if not ok:
        raise RuntimeError("另存失败: %s" % (why,))
    return "%s (%.0f B)" % (why, os.path.getsize(path))


if __name__ == "__main__":
    for op in sys.argv[1:]:
        print("[%s] %s" % (op, run(op)))
        a = os.path.join(WORK, "%s_orig.pmx" % op)
        b = os.path.join(WORK, "%s_cx.pmx" % op)
        if os.path.exists(a) and os.path.exists(b):
            print(P.fmt(P.diff(a, b)))
