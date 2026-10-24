# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, "src")
from pmxeditor import pmx, doc
import pmxsem as P
sys.path.insert(0, r"tests/parity")

MODEL = r"D:\Project\MMD\02_模型库\KARU式Rabbit Hole MIKU.ver 1.5_by_KR-SAM_141b6a51e3ad47ff26d0910dd71e3a71\KARU式Rabbit Hole MIKU.ver 1.6.pmx"

# 1) CRLF
m = pmx.load_pmx(MODEL)
m.comment = "PARITY 注释测试\n第二行 line2\n第三行 TEST"
pmx.save_pmx(m, r"tests\parity\work\_fix_crlf.pmx")
m2 = pmx.load_pmx(r"tests\parity\work\_fix_crlf.pmx")
print("[1] comment repr:", repr(m2.comment))
print("[1] stats:", pmx.model_stats(m2))

# 2) 删材质：真删几何 + 压缩孤立顶点
m = pmx.load_pmx(MODEL)
before = pmx.model_stats(m)
idx = doc.remove_material(m, 20)
after = pmx.model_stats(m)
print("[2] before:", before["vertices"], before["faces"], "after:", after["vertices"], after["faces"], "idx:", idx)
pmx.save_pmx(m, r"tests\parity\work\_fix_s2.pmx")
print("[2] size:", os.path.getsize(r"tests\parity\work\_fix_s2.pmx"))
r = P.diff(r"tests\parity\work\S2_orig.pmx", r"tests\parity\work\_fix_s2.pmx")
print("[2] vs S2_orig:", P.fmt(r, maxlines=12))

# 3) 删骨骼：不再改写无关骨骼的 flags
m = pmx.load_pmx(MODEL)
doc.remove_bone(m, 100)
pmx.save_pmx(m, r"tests\parity\work\_fix_s1.pmx")
r = P.diff(r"tests\parity\work\S1_orig.pmx", r"tests\parity\work\_fix_s1.pmx")
print("[3] vs S1_orig:", P.fmt(r, maxlines=12))
