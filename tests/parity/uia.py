# -*- coding: utf-8 -*-
"""抓取原版窗口所有 UIA 元素（文本），供按标签定位控件用。"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PS = os.path.join(HERE, "uia_dump.ps1")
CACHE = os.path.join(HERE, "uia")


def dump(pid, tag):
    os.makedirs(CACHE, exist_ok=True)
    out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                          "-File", PS, str(pid)], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    rows = []
    for ln in out.stdout.splitlines():
        p = ln.split("\t")
        if len(p) < 6:
            continue
        try:
            rows.append({"type": p[0], "name": p[1].replace("\\n", "\n"),
                         "x": int(p[2]), "y": int(p[3]), "w": int(p[4]),
                         "h": int(p[5]), "aid": p[6] if len(p) > 6 else ""})
        except ValueError:
            continue
    json.dump(rows, open(os.path.join(CACHE, tag + ".json"), "w", encoding="utf8"),
              ensure_ascii=False, indent=0)
    return rows


def load(tag):
    p = os.path.join(CACHE, tag + ".json")
    return json.load(open(p, encoding="utf8"))


def find(rows, name, types=("Pane", "Text")):
    return [r for r in rows if r["name"].strip() == name and r["type"] in types]


def after(rows, label, dy=0, maxdx=400):
    """找标签右侧同一行（±dy）的最近输入框中心点。"""
    lb = find(rows, label)
    if not lb:
        return None
    L = lb[0]
    ly = L["y"] + L["h"] // 2
    cands = []
    for r in rows:
        cy = r["y"] + r["h"] // 2
        if abs(cy - ly) > (dy or max(8, L["h"] // 2)):
            continue
        if r["x"] < L["x"] + L["w"] - 4:
            continue
        if r["x"] - (L["x"] + L["w"]) > maxdx:
            continue
        cands.append((r["x"] - (L["x"] + L["w"]), r))
    if not cands:
        return None
    cands.sort(key=lambda t: t[0])
    r = cands[0][1]
    return (r["x"] + r["w"] // 2, r["y"] + r["h"] // 2, r)


def center(r):
    return (r["x"] + r["w"] // 2, r["y"] + r["h"] // 2)
