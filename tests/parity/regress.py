# -*- coding: utf-8 -*-
"""回归：跑仓库自带场景，收集 report.json 里的异常。"""
import json, os, shutil, subprocess, sys, time

PY = r".\build\python\python.exe"
MODEL = (r"D:\Project\MMD\02_模型库\KARU式Rabbit Hole MIKU.ver 1.5_by_KR-SAM_"
         r"141b6a51e3ad47ff26d0910dd71e3a71\KARU式Rabbit Hole MIKU.ver 1.6.pmx")
OUT = r"tests\parity\work"
env = dict(os.environ, PYTHONUTF8="1")

for scene in sys.argv[1:]:
    t0 = time.time()
    rep = os.path.join("tests", "report.json")
    if os.path.exists(rep):
        os.remove(rep)
    try:
        p = subprocess.run([PY, r"tests\go.py", scene, "dark", MODEL],
                           capture_output=True, text=True, encoding="utf8", errors="replace",
                           env=env, timeout=260)
    except subprocess.TimeoutExpired:
        print("%-14s TIMEOUT >260s" % scene)
        continue
    dt = time.time() - t0
    data = None
    if os.path.exists(rep):
        with open(rep, encoding="utf8") as f:
            data = json.load(f)
        shutil.copy(rep, os.path.join(OUT, "_rep_%s.json" % scene))
    n = len(data.get("anomalies", [])) if isinstance(data, dict) else -1
    print("%-14s %5.1fs rc=%s anomalies=%s" % (scene, dt, p.returncode, n))
    if isinstance(data, dict):
        for a in data.get("anomalies", [])[:6]:
            print("   ", str(a)[:220])
    if p.returncode not in (0, None):
        print("   stderr:", (p.stderr or "")[-600:])
