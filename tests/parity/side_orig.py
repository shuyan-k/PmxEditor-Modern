# -*- coding: utf-8 -*-
"""原版 PmxEditor 的操作执行器（真实鼠标键盘）：python tests/parity/side_orig.py <OPID> [...]"""
import os, sys, time, json
sys.path.insert(0, r"tests/parity")
import origui as U, origlib as O
import win32gui, win32api, win32con

MODEL = r"D:\Project\MMD\02_模型库\KARU式Rabbit Hole MIKU.ver 1.5_by_KR-SAM_141b6a51e3ad47ff26d0910dd71e3a71\KARU式Rabbit Hole MIKU.ver 1.6.pmx"
WORK = U.WORK
SUF = os.environ.get("PARITY_SUF", "")
MODEL = os.environ.get("PARITY_MODEL") or MODEL


def info_ctrls():
    U.click_tab("信息")
    time.sleep(0.5)
    page = [p for p in U.pages() if p[2]][0][1]
    cs = U.controls(page, True)
    ed = [c for c in cs if c["cls"].upper() == "EDIT"]
    cb = [c for c in cs if c["cls"].upper() == "COMBOBOX"]
    btn = [c for c in cs if c["cls"].upper() == "BUTTON"]
    name_ed = min(ed, key=lambda c: c["rect"][1])
    comment_ed = max(ed, key=lambda c: c["rect"][3])
    return {"ed": ed, "name": name_ed, "comment": comment_ed, "cb": cb, "btn": btn}


def set_text(ctrl, text, verify=True):
    x, y = U.rcenter(ctrl["rect"])
    O.click(x, y)
    time.sleep(0.25)
    O.hotkey("ctrl", "a")
    time.sleep(0.15)
    O.type_text(text)
    time.sleep(0.35)
    O.key("tab")
    time.sleep(0.45)
    got = U.get_text(ctrl["hwnd"])
    return got


def op_E1():
    c = info_ctrls()
    return set_text(c["name"], "PARITY_E1")


def op_E2():
    c = info_ctrls()
    return set_text(c["comment"], "PARITY 注释测试\r\n第二行 line2\r\n第三行 TEST")


def btn_by_text(cs, txt):
    for b in cs:
        if txt in b["text"]:
            return b
    return None


def op_E3():
    c = info_ctrls()
    b = btn_by_text(c["btn"], "英")
    x, y = U.rcenter(b["rect"])
    O.click(x, y)
    time.sleep(0.8)
    c = info_ctrls()
    before = U.get_text(c["name"]["hwnd"])
    got = set_text(c["name"], "PARITY_EN")
    return {"before": before, "after": got}


def _registry():
    return {k[3:]: v for k, v in list(globals().items()) if k.startswith("op_")}


def main():
    ids = sys.argv[1:] or ["R1"]
    # 结果按 op 累积，避免一次只跑几个 op 时把之前的记录覆盖掉
    res_path = os.path.join(WORK, "_orig_result.json")
    out = {}
    if os.path.exists(res_path):
        try:
            with open(res_path, encoding="utf8") as f:
                out = json.load(f)
        except Exception:
            out = {}
    if not U.alive():
        U.start()
    for oid in ids:
        U.layout()
        U.open_model(MODEL)
        time.sleep(2.6)
        fn = _registry().get(oid)
        tgt = os.path.join(WORK, "%s%s_orig.pmx" % (oid, SUF))
        if fn is None:
            out[oid] = {"status": "unsupported"}
            continue
        try:
            detail = fn()
            U.shot(oid + "_orig")
            ok, note = U.save_as(tgt)
            out[oid] = {"status": "ok" if ok else "save-failed", "path": tgt,
                        "note": note, "detail": str(detail)[:200]}
        except Exception:
            import traceback
            out[oid] = {"status": "error", "detail": traceback.format_exc()[-800:]}
            U.shot(oid + "_orig_err")
    json.dump(out, open(res_path, "w", encoding="utf8"),
              ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1)[:1500])



# ---------------------------------------------------------------- 骨骼/B1..B3
BONE_NAME = (774, 218)
BONE_POS_X = (654, 271)
BONE_LAYER = (1250, 216)


def set_field(xy, text, tab=True):
    O.click(xy[0], xy[1])
    time.sleep(0.3)
    O.hotkey("ctrl", "a")
    time.sleep(0.15)
    O.type_text(text)
    time.sleep(0.35)
    if tab:
        O.key("tab")
    time.sleep(0.5)


def op_B1():
    U.click_tab("骨骼")
    time.sleep(0.6)
    set_field(BONE_POS_X, "1.0")


def op_B2():
    U.click_tab("骨骼")
    time.sleep(0.6)
    set_field(BONE_NAME, "PARITY_BONE")


def op_B3():
    U.click_tab("骨骼")
    time.sleep(0.6)
    set_field(BONE_LAYER, "3")


# ---------------------------------------------------------------- 信息页下拉
def combo_index(hwnd):
    return win32api.SendMessage(hwnd, 0x147, 0, 0), win32api.SendMessage(hwnd, 0x146, 0, 0)


def combo_select(cb, index):
    x, y = U.rcenter(cb["rect"])
    O.click(x, y)
    time.sleep(0.5)
    O.key("home")
    time.sleep(0.2)
    for _ in range(index):
        O.key("down")
        time.sleep(0.15)
    O.key("tab")
    time.sleep(0.6)
    return combo_index(cb["hwnd"])


def op_E4():
    c = info_ctrls()
    utf8 = c["cb"][0]
    return combo_select(utf8, 1)


def op_E5():
    c = info_ctrls()
    uv = c["cb"][1]
    return combo_select(uv, 2)


# ================= 覆盖版（骨骼改用 5「上半身」，提交方式 Enter）=================
def set_field(xy, text, tab=True):
    O.click(xy[0], xy[1])
    time.sleep(0.3)
    O.hotkey("ctrl", "a")
    time.sleep(0.12)
    O.type_text(text)
    time.sleep(0.35)
    O.key("enter")
    time.sleep(0.6)
    if tab:
        O.key("tab")
        time.sleep(0.2)


def select_bone(idx):
    U.click_tab("骨骼")
    time.sleep(0.6)
    O.click(129, 211)
    time.sleep(0.25)
    O.hotkey("ctrl", "a")
    time.sleep(0.12)
    O.type_text(str(idx))
    O.key("enter")
    time.sleep(0.7)


def op_B1():
    select_bone(5)
    set_field(BONE_POS_X, "1.0")


def op_B2():
    select_bone(5)
    set_field(BONE_NAME, "PARITY_BONE")


def op_B3():
    select_bone(5)
    set_field(BONE_LAYER, "3")

def commit_bone(idx):
    """PmxEditor 的骨骼字段在离开该骨骼时才写回模型：切到别的骨骼再切回来。"""
    other = (idx + 20) % 168
    select_bone(other)
    time.sleep(0.3)
    select_bone(idx)


def op_B1():
    select_bone(5)
    set_field(BONE_POS_X, "1.0")
    commit_bone(5)


def op_B2():
    select_bone(5)
    set_field(BONE_NAME, "PARITY_BONE")
    commit_bone(5)


def op_B3():
    select_bone(5)
    set_field(BONE_LAYER, "3")
    commit_bone(5)


# ---------------------------------------------------------------- 材质 M1/M2
MAT_R = (774, 309)
MAT_A = (1289, 309)
MAT_INDEX = (104, 209)


def select_mat(i):
    O.click(MAT_INDEX[0], MAT_INDEX[1])
    time.sleep(0.25)
    O.hotkey("ctrl", "a")
    time.sleep(0.12)
    O.type_text(str(i))
    O.key("enter")
    time.sleep(0.7)


def op_M1():
    U.click_tab("材质")
    time.sleep(0.7)
    select_mat(0)
    set_field(MAT_R, "0.5")
    select_mat(1)
    select_mat(0)


def op_M2():
    U.click_tab("材质")
    time.sleep(0.7)
    select_mat(0)
    set_field(MAT_A, "0.5")
    select_mat(1)
    select_mat(0)


# ---------------------------------------------------------------- 顶点/刚体/Joint/表情/删除/撤销
VERT_POS_X = (714, 263)
VERT_INDEX = (118, 209)
RIGID_MASS = (1021, 645)
JOINT_MINROT_X = (660, 579)
MORPH_OFF1 = (981, 535)
BTN_X = (354, 1268)


def jump_index(pos, i):
    O.click(pos[0], pos[1])
    time.sleep(0.25)
    O.hotkey("ctrl", "a")
    time.sleep(0.12)
    O.type_text(str(i))
    O.key("enter")
    time.sleep(0.7)


def drop_dialog():
    """若有模态确认框，按 Enter 取默认按钮。"""
    time.sleep(0.8)
    wins = O.find_windows(pid=U.pid())
    titles = [t for _h, _p, t, _r in wins]
    if any(("編集" not in t and "View" not in t) for t in titles):
        O.key("enter")
        time.sleep(0.6)


def op_V1():
    U.click_tab("顶点")
    time.sleep(0.8)
    jump_index(VERT_INDEX, 0)
    set_field(VERT_POS_X, "0.5")


def op_P1():
    U.click_tab("刚体")
    time.sleep(0.8)
    jump_index((104, 209), 0)
    set_field(RIGID_MASS, "2.5")
    jump_index((104, 209), 1)
    jump_index((104, 209), 0)


def op_J1():
    U.click_tab("Joint")
    time.sleep(0.8)
    jump_index((104, 209), 0)
    set_field(JOINT_MINROT_X, "-0.5")
    jump_index((104, 209), 1)
    jump_index((104, 209), 0)


def op_F1():
    U.click_tab("表情")
    time.sleep(0.8)
    jump_index((104, 209), 0)
    set_field(MORPH_OFF1, "0.1")


def op_S1():
    U.click_tab("骨骼")
    time.sleep(0.8)
    jump_index((129, 211), 100)
    O.click(BTN_X[0], BTN_X[1])
    drop_dialog()


def op_S2():
    U.click_tab("材质")
    time.sleep(0.8)
    jump_index((104, 209), 20)
    O.click(BTN_X[0], BTN_X[1])
    drop_dialog()


def op_U1():
    U.click_tab("骨骼")
    time.sleep(0.8)
    select_bone(5)
    set_field(BONE_POS_X, "1.0")
    commit_bone(5)
    O.hotkey("ctrl", "z")
    time.sleep(1.0)



# ---------------- N1/N2：新建骨骼 / 新建材质（点底部 + 号）
PLUS = (302, 1268)
def op_N1():
    U.click_tab("骨骼")
    U.time.sleep(0.5)
    jump_index((129, 211), 0)
    O.click(*PLUS); U.time.sleep(1.0)
    drop_dialog()


def op_N2():
    U.click_tab("材质")
    U.time.sleep(0.5)
    jump_index(MAT_INDEX, 0)
    O.click(*PLUS); U.time.sleep(1.0)
    drop_dialog()

# ---------------- 追加场景（报告第八节后续建议）：描边尺寸 / 描绘开关 / 顶点 UV / 骨骼性能开关
MAT_EDGE_SIZE = (1287, 483)
MAT_DOUBLE = (568, 486)
VERT_UV_U = (716, 419)
BONE_SW_ROT = (1037, 276)
BONE_SW_VIS = (1261, 276)


def op_M4():
    U.click_tab("材质")
    time.sleep(0.7)
    select_mat(0)
    set_field(MAT_EDGE_SIZE, "0.5")
    select_mat(1)
    select_mat(0)


def op_M5():
    U.click_tab("材质")
    time.sleep(0.7)
    select_mat(0)
    O.click(MAT_DOUBLE[0], MAT_DOUBLE[1])
    time.sleep(0.6)
    select_mat(1)
    select_mat(0)


def op_V2():
    U.click_tab("顶点")
    time.sleep(0.8)
    jump_index(VERT_INDEX, 0)
    set_field(VERT_UV_U, "0.25")


def op_B4():
    select_bone(5)
    O.click(BONE_SW_VIS[0], BONE_SW_VIS[1])
    time.sleep(0.6)
    commit_bone(5)


def op_B5():
    select_bone(5)
    O.click(BONE_SW_ROT[0], BONE_SW_ROT[1])
    time.sleep(0.6)
    commit_bone(5)


# ---------------- 追加场景（第二批）：刚体模式切换 / 表示枠追加骨骼
RIGID_MODE_ALIGN = (1115, 292)
RIGID_INDEX = (104, 209)
FRAME_INDEX = (108, 257)
FRAME_BONE_COMBO = (1133, 534)
FRAME_BONE_ADD = (1333, 537)


def op_P2():
    U.click_tab("刚体")
    time.sleep(0.8)
    jump_index(RIGID_INDEX, 0)
    O.click(RIGID_MODE_ALIGN[0], RIGID_MODE_ALIGN[1])
    time.sleep(0.8)
    drop_dialog()
    jump_index(RIGID_INDEX, 1)
    jump_index(RIGID_INDEX, 0)


def op_F2():
    U.click_tab("显示枠")
    time.sleep(0.8)
    jump_index(FRAME_INDEX, 0)
    page = [p for p in U.pages() if p[2]][0][1]
    cs = [c for c in U.controls(page, True)
          if c["cls"].upper() == "COMBOBOX" and c["rect"][1] > 480]
    cs.sort(key=lambda c: c["rect"][1])
    combo_select(cs[0], 3)
    O.click(FRAME_BONE_ADD[0], FRAME_BONE_ADD[1])
    time.sleep(0.8)
    drop_dialog()


# ---------------- 追加场景（第三批）：描边有效 / IK 开关
MAT_EDGE_ON = (1006, 486)
BONE_SW_IK = (1191, 276)


def op_M6():
    U.click_tab("材质")
    time.sleep(0.7)
    select_mat(0)
    O.click(MAT_EDGE_ON[0], MAT_EDGE_ON[1])
    time.sleep(0.6)
    select_mat(1)
    select_mat(0)


def op_I2():
    select_bone(5)
    O.click(BONE_SW_IK[0], BONE_SW_IK[1])
    time.sleep(0.8)
    drop_dialog()
    commit_bone(5)


def pick_xy(pos, n):
    O.click(pos[0], pos[1])
    time.sleep(0.4)
    O.key("home")
    time.sleep(0.2)
    for _ in range(n):
        O.key("down")
        time.sleep(0.15)
    O.key("tab")
    time.sleep(0.3)


def op_V3():
    U.click_tab("顶点")
    time.sleep(0.5)
    jump_index(VERT_INDEX, 0)
    set_field((900, 319), "1.0")


def op_V4():
    U.click_tab("顶点")
    time.sleep(0.5)
    jump_index(VERT_INDEX, 0)
    set_field((902, 419), "0.75")


def set_field_enter(xy, text):
    O.click(xy[0], xy[1])
    time.sleep(0.25)
    O.hotkey("ctrl", "a")
    time.sleep(0.2)
    O.type_text(text)
    time.sleep(0.3)
    O.key("enter")
    time.sleep(0.4)


def op_B6():
    U.click_tab("骨骼")
    time.sleep(0.5)
    select_bone(5)
    O.click(603, 530)
    time.sleep(0.5)
    set_field_enter((883, 535), "0.5")
    commit_bone(5)


def op_B7():
    U.click_tab("骨骼")
    time.sleep(0.5)
    select_bone(5)
    O.click(910, 645)
    time.sleep(0.6)
    commit_bone(5)


def op_M7():
    U.click_tab("材质")
    time.sleep(0.5)
    select_mat(0)
    pick_xy((1052, 687), 1)
    select_mat(1)
    select_mat(0)


def op_P3():
    U.click_tab("刚体")
    time.sleep(0.5)
    jump_index(RIGID_INDEX, 0)
    O.click(611, 398)
    time.sleep(0.4)


def op_P4():
    U.click_tab("刚体")
    time.sleep(0.5)
    jump_index(RIGID_INDEX, 0)
    pick_xy((669, 500), 1)


# ---------------- PMX 2.1 柔体基座：只做原样另存（基座由 cxop.py SB0 生成）
def op_SB1():
    return "PMX 2.1 柔体基座原样另存（1 柔体 / 1 锚点 / 1 固定点）"


if __name__ == "__main__":
    main()
