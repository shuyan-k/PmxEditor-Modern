# -*- coding: utf-8 -*-
"""新版编辑器的操作执行器：python tests/parity/side_mod.py <OPID> [更多OPID...]"""
import os, sys, json
sys.path.insert(0, r"tests\parity")
import modern as M
import ops_spec as S
from PyQt5.QtWidgets import QLineEdit, QPlainTextEdit, QDoubleSpinBox, QSpinBox, QComboBox
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtTest import QTest
from PyQt5.QtCore import Qt

MODEL = r"D:\Project\MMD\02_模型库\KARU式Rabbit Hole MIKU.ver 1.5_by_KR-SAM_141b6a51e3ad47ff26d0910dd71e3a71\KARU式Rabbit Hole MIKU.ver 1.6.pmx"
WORK = os.path.join(r"tests\parity\work")
SUF = os.environ.get("PARITY_SUF", "")
MODEL = os.environ.get("PARITY_MODEL") or MODEL


def paste_into(w, text):
    w.setFocus()
    M.pump(40)
    if isinstance(w, (QLineEdit, QPlainTextEdit)):
        w.selectAll()
    M.pump(30)
    QGuiApplication.clipboard().setText(text)
    QTest.keyClick(w, Qt.Key_V, Qt.ControlModifier)
    M.pump(120)


def type_spin(sb, val):
    sb.setFocus()
    M.pump(30)
    sb.lineEdit().selectAll()
    QGuiApplication.clipboard().setText(str(val))
    QTest.keyClick(sb.lineEdit(), Qt.Key_V, Qt.ControlModifier)
    M.pump(60)
    QTest.keyClick(sb.lineEdit(), Qt.Key_Return)
    M.pump(150)


def info_edits():
    p = M.page(0)
    return [w for w in M.walk(p) if isinstance(w, QLineEdit) and w.isVisible()]


def op_E1():
    p = M.page(0)
    paste_into(p.name_edit, "PARITY_E1")
    QTest.keyClick(p.name_edit, Qt.Key_Tab)
    M.pump(200)


def op_E2():
    p = M.page(0)
    paste_into(p.comment, "PARITY 注释测试\r\n第二行 line2\r\n第三行 TEST")
    M.click(M.WIN._pages[0].comment_btn)
    M.pump(250)


def op_E3():
    p = M.page(0)
    paste_into(p.name_en_edit, "PARITY_EN")
    QTest.keyClick(p.name_en_edit, Qt.Key_Tab)
    M.pump(200)


def _registry():
    return {k[3:]: v for k, v in list(globals().items()) if k.startswith("op_")}


def main():
    ids = sys.argv[1:] or ["R1"]
    M.boot(MODEL)
    # 结果按 op 累积，避免一次只跑几个 op 时把之前的记录覆盖掉
    res_path = os.path.join(WORK, "_mod_result.json")
    out = {}
    if os.path.exists(res_path):
        try:
            with open(res_path, encoding="utf8") as f:
                out = json.load(f)
        except Exception:
            out = {}
    for oid in ids:
        fn = _registry().get(oid)
        if fn is None:
            out[oid] = {"status": "unsupported", "detail": "新版无该操作入口"}
            continue
        tgt = os.path.join(WORK, "%s%s_mod.pmx" % (oid, SUF))
        try:
            fn()
            M.shot(oid + "_mod")
            ok = M.save_to(tgt)
            out[oid] = {"status": "ok" if ok else "save-failed", "path": tgt,
                        "dirty": bool(getattr(M.WIN.doc, "dirty", None))}
        except Exception as e:
            import traceback
            out[oid] = {"status": "error", "detail": traceback.format_exc()[-600:]}
        # 每个操作后重载原始模型，保证互不污染
        M.WIN.open_path(MODEL)
        M.pump(400)
    json.dump(out, open(res_path, "w", encoding="utf8"),
              ensure_ascii=False, indent=1)
    sys.stdout.flush()
    os._exit(0)



# ---------------------------------------------------------------- 骨骼 B1..B3
def op_B1():
    p = M.page(1)
    type_spin(p.pos_spin.spins[0], "1.0")


def op_B2():
    p = M.page(1)
    paste_into(p.name_edit, "PARITY_BONE")
    QTest.keyClick(p.name_edit, Qt.Key_Tab)
    M.pump(250)


def op_B3():
    p = M.page(1)
    type_spin(p.layer_spin, "3")


# ================= 覆盖版（骨骼 5「上半身」，先搜索再点行）=================
def select_bone(idx, keyword=""):
    p = M.page(1)
    paste_into(p.search, keyword)
    M.pump(300)
    it = p.tree._items.get(idx)
    if it is None and keyword:
        paste_into(p.search, "")
        M.pump(300)
        it = p.tree._items.get(idx)
    if it is None:
        raise RuntimeError("骨骼 %d 不在过滤结果中（keyword=%r）" % (idx, keyword))
    ti = it.index()
    p.tree.scrollTo(ti)
    M.pump(150)
    r = p.tree.visualRect(ti)
    M.click(p.tree.viewport(), pos=r.center())
    M.pump(250)
    return p.hint_label.text()


def op_B1():
    select_bone(5, "上半身")
    p = M.page(1)
    type_spin(p.pos_spin.spins[0], "1.0")


def op_B2():
    select_bone(5, "上半身")
    p = M.page(1)
    paste_into(p.name_edit, "PARITY_BONE")
    QTest.keyClick(p.name_edit, Qt.Key_Tab)
    M.pump(250)


def op_B3():
    select_bone(5, "上半身")
    p = M.page(1)
    type_spin(p.layer_spin, "3")




# ---------------------------------------------------------------- 其余操作（真实点击）
def tool(p, tip):
    for w in M.walk(p):
        try:
            if tip in (w.toolTip() or ""):
                return w
        except Exception:
            pass
    return None


def row_click(entry_list, row):
    idx = entry_list.model().index(row, 0)
    entry_list.scrollTo(idx)
    M.pump(120)
    r = entry_list.visualRect(idx)
    M.click(entry_list.viewport(), pos=r.center())
    M.pump(250)


def click_text(root, text):
    for w in M.walk(root):
        try:
            if getattr(w, "text", None) and w.text() == text and w.isVisible():
                M.click(w)
                M.pump(200)
                return w
        except Exception:
            pass
    return None


def op_V1():
    p = M.page(7)
    type_spin(p.index_spin, "0")
    M.pump(200)
    type_spin(p.pos_spin.spins[0], "0.5")
    if p.apply_btn.isEnabled():
        M.click(p.apply_btn)
    M.pump(250)


def op_P1():
    p = M.page(4)
    click_text(p, "刚体")
    M.pump(200)
    row_click(p.list, 0)
    type_spin(p.rb_mass, "2.5")


def op_J1():
    p = M.page(4)
    click_text(p, "关节")
    M.pump(250)
    row_click(p.list, 0)
    type_spin(p.jt_min_rot.spins[0], "-0.5")


def op_F1():
    p = M.page(3)
    row_click(p.list, 0)
    p.offset_table.selectRow(0)
    M.pump(250)
    dbl = [w for w in M.walk(p.off_host)
           if w.isVisible() and w.metaObject().className() == "QDoubleSpinBox"]
    if not dbl:
        raise RuntimeError("形态偏移编辑器没有可编辑数值")
    type_spin(dbl[0], "0.1")


def _precise_color(idx_spin, value):
    """在材质色的精确数值框里键入数值（对应原版直接输入 0.5 的操作）。"""
    p = M.page(2)
    row_click(p.list, 0)
    type_spin(p.diffuse_spins.spins[idx_spin], value)


def op_M1():
    _precise_color(0, "0.5")


def op_M2():
    # 透明度 A：漫反射 RGBA 的第四格
    p = M.page(2)
    row_click(p.list, 0)
    type_spin(p.diffuse_spins.spins[3], "0.5")


def op_M3():
    """取色对话框路径：用户在 Qt 颜色对话框里选 R=128（8 位精度）。"""
    p = M.page(2)
    row_click(p.list, 0)
    from PyQt5.QtGui import QColor
    from PyQt5.QtWidgets import QColorDialog
    QColorDialog.getColor = staticmethod(lambda *a, **k: QColor(128, 255, 255, 255))
    M.click(p.diffuse)


def op_S1():
    p = M.page(1)
    select_bone(100, "")
    b = tool(p, "删除当前骨骼")
    if b is None:
        raise RuntimeError("找不到删除骨骼工具按钮")
    M.click(b)
    M.pump(500)


def op_S2():
    from PyQt5.QtWidgets import QMessageBox

    def _exec(self):
        # 模拟用户点「连同三角面删除」（真正的几何删除，与原版 PmxEditor 一致）
        for btn in self.buttons():
            if "连同三角面删除" in btn.text():
                btn.click()
                return 0
        for btn in self.buttons():
            if "取消" in btn.text():
                btn.click()
                return 0
        return 0

    old_exec = QMessageBox.exec_
    QMessageBox.exec_ = _exec
    try:
        p = M.page(2)
        row_click(p.list, 20)
        b = tool(p, "删除材质")
        if b is None:
            raise RuntimeError("找不到删除材质工具按钮")
        M.click(b)
        M.pump(500)
    finally:
        QMessageBox.exec_ = old_exec


def op_U1():
    p = M.page(1)
    select_bone(5, "上半身")
    type_spin(p.pos_spin.spins[0], "1.0")
    M.pump(250)
    QTest.keyClick(M.WIN, Qt.Key_Z, Qt.ControlModifier)
    M.pump(400)


# ---------------- N1/N2：新建骨骼 / 新建材质
def op_N1():
    p = M.page(1)
    select_bone(0, "操作中心")
    b = tool(p, "新建骨骼")
    if b is None:
        raise RuntimeError("找不到新建骨骼按钮")
    M.click(b)
    M.pump(500)


def op_N2():
    p = M.page(2)
    row_click(p.list, 0)
    b = tool(p, "新建材质")
    if b is None:
        raise RuntimeError("找不到新建材质按钮")
    M.click(b)
    M.pump(500)

# ---------------- E4/E5：文字编码 / 追加 UV 数（信息页下拉）
def _combo_pick(combo, want: int):
    combo.setFocus()
    M.pump(120)
    idx = combo.currentIndex()
    while idx < want:
        QTest.keyClick(combo, Qt.Key_Down)
        M.pump(80)
        idx = combo.currentIndex()
    while idx > want:
        QTest.keyClick(combo, Qt.Key_Up)
        M.pump(80)
        idx = combo.currentIndex()
    if combo.currentIndex() != want:
        raise RuntimeError("下拉未选到目标项：当前 %d 期望 %d" % (combo.currentIndex(), want))
    M.pump(200)


def op_E4():
    p = M.page(0)
    _combo_pick(p.encoding_combo, 1)      # UTF-16LE -> UTF-8


def op_E5():
    p = M.page(0)
    _combo_pick(p.uv_combo, 2)            # 追加 UV 数 0 -> 2


# ---------------- 追加场景（报告第八节后续建议）
def op_M4():
    p = M.page(2)
    row_click(p.list, 0)
    type_spin(p.edge_size, "0.5")


def op_M5():
    p = M.page(2)
    row_click(p.list, 0)
    M.click(p.flags["double"])
    M.pump(250)


def op_V2():
    p = M.page(7)
    type_spin(p.index_spin, "0")
    M.pump(200)
    type_spin(p.uv_spin.spins[0], "0.25")
    if p.apply_btn.isEnabled():
        M.click(p.apply_btn)
    M.pump(250)


def op_B4():
    p = M.page(1)
    select_bone(5)
    M.click(p.switches["vis"])
    M.pump(250)


def op_B5():
    p = M.page(1)
    select_bone(5)
    M.click(p.switches["rot"])
    M.pump(250)


# ---------------- 追加场景（第二批）
def op_P2():
    p = M.page(4)
    click_text(p, "刚体")
    M.pump(200)
    row_click(p.list, 0)
    click_text(p, "演算+对齐")
    M.pump(300)


def op_F2():
    p = M.page(6)
    row_click(p.list, 0)
    # 原版骨骼下拉按显示顺序排序（第 4 项 = 骨骼 106），新版按骨骼索引排序：取同一根骨骼
    p.bone_combo.setCurrentIndex(105)
    M.pump(150)
    M.click(p.bone_button)
    M.pump(300)


# ---------------- 追加场景（第三批）
def op_M6():
    p = M.page(2)
    row_click(p.list, 0)
    M.click(p.flags["edge"])
    M.pump(250)


def op_I2():
    p = M.page(1)
    select_bone(5)
    M.click(p.ik_sw)
    M.pump(300)



def pick_data(combo, data):
    for i in range(combo.count()):
        if combo.itemData(i) == data:
            combo.setCurrentIndex(i)
            return True
    return False


def op_I3():
    p = M.page(1)
    select_bone(5)
    M.click(p.ik_sw)
    M.pump(60)
    pick_data(p.ik_target, 6)
    M.pump(60)
    type_spin(p.ik_loop, "3")
    M.pump(60)
    type_spin(p.ik_angle, "10")
    M.pump(60)
    pick_data(p.ik_link_combo, 4)
    click_text(p, "添加链接")
    M.pump(60)
    pick_data(p.ik_link_combo, 5)
    click_text(p, "添加链接")
    M.pump(60)
    ok = p.ik_links.count() == 2
    return {"ok": ok, "rows": p.ik_links.count(), "detail": "IK 目标 bone6 loop3 angle10 links bone4,bone5"}


def op_V3():
    p = M.page(7)
    type_spin(p.index_spin, "0")
    M.pump(60)
    type_spin(p.nrm_spin.spins[1], "1.0")
    M.pump(60)
    M.click(p.apply_btn)


def op_V4():
    p = M.page(7)
    type_spin(p.index_spin, "0")
    M.pump(60)
    type_spin(p.uv_spin.spins[1], "0.75")
    M.pump(60)
    M.click(p.apply_btn)


def op_B6():
    p = M.page(1)
    select_bone(5)
    M.click(p.inherit_rot)
    M.pump(80)
    type_spin(p.inherit_ratio, "0.5")
    M.pump(80)
    return {"ok": True, "detail": "付与率 0.5"}


def op_B7():
    p = M.page(1)
    select_bone(5)
    M.click(p.fixed_sw)
    M.pump(80)
    return {"ok": True, "detail": "轴固定 开"}


def op_M7():
    p = M.page(2)
    row_click(p.list, 0)
    M.pump(80)
    M.click(p.sphere_seg.buttons["1"])
    M.pump(80)
    return {"ok": p.sphere_seg.value() == "1", "detail": "球面模式 → 乘法"}


def op_P3():
    p = M.page(4)
    click_text(p, "刚体")
    row_click(p.list, 0)
    M.pump(80)
    click_text(p, "箱")
    M.pump(80)
    return {"ok": True, "detail": "刚体0 形状 → 箱"}


def op_P4():
    p = M.page(4)
    click_text(p, "刚体")
    row_click(p.list, 0)
    type_spin(p.rb_group, "1")
    M.pump(80)
    return {"ok": True, "detail": "刚体0 所属组 → 1"}


# ---------------- 复制骨骼/材质（原版无入口，用 .cx Clone 定义同一语义）
def op_N3():
    select_bone(5, "上半身")
    p = M.page(1)
    b = tool(p, "复制当前骨骼")
    if b is None:
        raise RuntimeError("找不到复制骨骼按钮")
    M.click(b)
    M.pump(400)
    return {"ok": True, "detail": "复制骨骼5 并追加"}


def op_N4():
    p = M.page(2)
    row_click(p.list, 0)
    b = tool(p, "复制材质")
    if b is None:
        raise RuntimeError("找不到复制材质按钮")
    M.click(b)
    M.pump(400)
    return {"ok": True, "detail": "复制材质0 并追加（含面）"}


# ---------------- 面页 / 柔体：新版对应入口（「面」页与「柔体」页）
def op_FA1():
    p = M.page(8)
    row_click(p.list, 0)
    pick_data(p.src_combo, 0)
    M.pump(120)
    type_spin(p.start_spin, "0")
    type_spin(p.count_spin, "300")
    pick_data(p.dst_combo, 1)
    M.pump(150)
    if not p.move_btn.isEnabled():
        raise RuntimeError("「移动这些面」按钮未启用")
    M.click(p.move_btn)
    M.pump(800)
    return {"ok": True, "detail": "材质0 前 300 面 → 材质1 末尾"}


def op_SB1():
    return {"ok": True, "detail": "PMX 2.1 柔体基座原样另存"}


def op_SB2():
    p = M.page(9)
    row_click(p.list, 0)
    M.pump(120)
    type_spin(p.mass_spin, "3.5")
    type_spin(p.margin_spin, "0.1")
    M.pump(300)
    s = M.WIN.doc.model.soft_bodies[0]
    if abs(float(s.total_mass) - 3.5) > 1e-5 or abs(float(s.collision_margin) - 0.1) > 1e-5:
        raise RuntimeError("柔体参数未写入：mass=%r margin=%r"
                           % (s.total_mass, s.collision_margin))
    return {"ok": True, "detail": "柔体0 总质量 3.5、碰撞余量 0.1"}


if __name__ == "__main__":
    main()
