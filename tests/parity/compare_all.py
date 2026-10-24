# -*- coding: utf-8 -*-
"""把所有已跑过的操作做一遍「原版 vs 新版」语义比对，输出 Markdown 表格。

用法： python -X utf8 tests/parity/compare_all.py
输出： tests/parity/compare_all.md
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pmxsem as P

W = os.path.join(HERE, "work")
BASE = os.path.join(W, "00_orig.pmx")

DESC = {
    "V3": "顶点0 法线 Y 0.706 → 1.0",
    "V4": "顶点0 UV-v 0.052 → 0.75",
    "B6": "骨骼5 开启「旋转付与」+ 付与率 0.5",
    "B7": "骨骼5 开启「轴固定」",
    "M7": "材质0 球面模式 无 → 乘法",
    "P3": "刚体0 形状 球 → 箱",
    "P4": "刚体0 所属组 0 → 1",
    "E1": "改模型日文名 → PARITY_E1",
    "E2": "改注释为三行文本（含中英文）",
    "E3": "改模型英文名 → PARITY_EN",
    "E4": "文字编码 UTF-16LE → UTF-8",
    "E5": "追加UV 数 0 → 2",
    "B1": "骨骼5「上半身」位置 X = 1.0",
    "B2": "骨骼5 名称 → PARITY_BONE",
    "B3": "骨骼5 变形层级 0 → 3",
    "M1": "材质0 漫反射色 R = 0.5",
    "M2": "材质0 透明度 A = 0.5",
    "M3": "材质0 漫反射色 R 经取色对话框（8 位量化）",
    "V1": "顶点0 位置 X = 0.5",
    "F1": "表情0「ウィンク２」首个顶点偏移 X = 0.1",
    "P1": "刚体0 质量 1.0 → 2.5",
    "J1": "Joint0 旋转限制 X 下限 = -0.5°",
    "S1": "删除骨骼 #100「左小指１」",
    "S2": "删除材质 #20「metal」",
    "U1": "骨骼位移后撤销（Ctrl+Z）",
    "N1": "新建骨骼",
    "N2": "新建材质",
    "M4": "材质0 描边大小 1.0 → 0.5",
    "M5": "材质0 关闭「双面描绘」",
    "M6": "材质0 开启「描边有效」",
    "V2": "顶点0 UV-u 0.5 → 0.25",
    "B4": "骨骼5 关闭「显示」",
    "B5": "骨骼5 关闭「可旋转」",
    "P2": "刚体0 模式 跟随 → 演算+对齐",
    "F2": "表示枠 Root 追加骨骼 #106「兔耳_2_2.R」",
    "I2": "骨骼5 开启 IK",
    "I3": "骨骼5 IK 目标/循环/角度 + 追加两条链（bone4、bone5）",
}
ORDER = ["E1", "E2", "E3", "E4", "E5", "B1", "B2", "B3", "M1", "M2",
         "V1", "F1", "P1", "J1", "S1", "S2", "U1", "N1", "N2", "M3",
         "M4", "M5", "M6", "V2", "B4", "B5", "P2", "F2", "I2", "I3",
         "V3", "V4", "B6", "B7", "M7", "P3", "P4"]

# 某些操作的「原版侧」不是 GUI 另存，而是踩 CSScript（.cx）通道另存
PAIR = {"I3": ("I3_cx.pmx", "I3_mod.pmx")}


def main():
    NOTE = {
        "E5": "（新版真正落盘，原版 UI 无效）",
        "S1": "（有意：新骨骼挂到原父 87，原版挂到前一根 99）",
        "N1": "（设计差异：默认名/父级/位置/flags）",
        "N2": "（原版 + 号灰化，无法新建材质）",
        "I3": "（原版侧经 CSScript .cx 通道写入，GUI 无法编辑 IK 链）",
        "B7": "（原版开启轴固定时把轴向量归一化为骨骼朝向，新版保持原值）",
    }
    rows = []
    detail = []
    for op in ORDER:
        fa, fb = PAIR.get(op, (op + "_orig.pmx", op + "_mod.pmx"))
        po = os.path.join(W, fa)
        pm = os.path.join(W, fb)
        if not os.path.exists(po) or not os.path.exists(pm):
            rows.append("| %s | %s | 未双侧完成 | — | — |" % (op, DESC[op]))
            continue
        r = P.diff(po, pm)
        sa, sb = r["stats_a"], r["stats_b"]
        sd = ""
        if sa != sb:
            keys = [k for k in sa if sa[k] != sb[k]]
            sd = "；".join("%s %s→%s" % (k, sa[k], sb[k]) for k in keys)
        if r["total"] == 0:
            verdict = "**一致**"
            sec = "—"
        else:
            verdict = "差异 %d 处" % r["total"]
            sec = "、".join("%s(%d)" % (k, len(v)) for k, v in r["sections"].items()) if isinstance(list(r["sections"].values())[0], list) else "、".join(r["sections"])
        note = NOTE.get(op, "")
        rows.append("| %s | %s | %s%s | %s | %s |" % (op, DESC[op], verdict, note, sec, sd or "—"))
        if r["total"]:
            detail.append("### %s %s\n\n```\n%s\n```\n" % (op, DESC[op], P.fmt(r, 8)))

    out = ["# 原版 PmxEditor vs 新版 PmxEditor_Modern — 同操作语义比对总表", "",
           "基准模型：`KARU式Rabbit Hole MIKU.ver 1.6.pmx`（116036 顶点 / 204919 面 / 21 材质 / 168 骨骼 / 22 表情 / 10 贴图 / 82 刚体 / 74 关节）", "",
           "比对方式：两侧各自操作后「另存为」，再用 `pmxsem` 按 1e-5 容差逐字段比对两个另存文件。原版侧通常用真实鼠标键盘（GUI），I3（IK 链）等 GUI 无法编辑的字段改由 `tests/parity/cxop.py` 驱动原版自带 CSScript 插件（`.cx`）写入，落盘仍走 PmxEditor 自身的另存。", "",
           "| 操作 | 说明 | 判定 | 差异段（处数） | 统计变化 |", "| --- | --- | --- | --- | --- |"]
    out += rows
    out += ["", "## 差异明细", ""]
    out += detail
    text = "\n".join(out)
    open(os.path.join(HERE, "compare_all.md"), "w", encoding="utf8").write(text)
    print(text[:4000])


if __name__ == "__main__":
    main()
