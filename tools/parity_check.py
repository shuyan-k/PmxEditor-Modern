# -*- coding: utf-8 -*-
"""C++ 版与 Python 版 PMX 读写一致性校验。

流程（每个用例）：
  1) Python 读入原始 PMX 并写回 py.pmx；
  2) C++ 探针（pmx_parity_probe）读入同一原始 PMX 并写回 cpp.pmx；
  3) 用 tests/parity/pmxsem.py 对「原始 → Python」「原始 → C++」「Python → C++」
     做逐字段语义比较；任何差异都视为校验失败。

用法：python tools/parity_check.py [模型路径...]
默认用例：tests/test_model.pmx，以及在此基础上追加 PMX 2.1 柔体的临时模型。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tests", "parity"))

from pmxeditor import pmx  # noqa: E402
import pmxsem  # noqa: E402


def find_probe() -> str:
    names = ("pmx_parity_probe.exe", "pmx_parity_probe")
    for sub in ("build/Release", "build", "build/Debug", "build/RelWithDebInfo"):
        for name in names:
            path = os.path.join(ROOT, "cpp", sub, name)
            if os.path.isfile(path):
                return path
    raise SystemExit("找不到 pmx_parity_probe，请先构建 cpp（cmake --build cpp/build --config Release）")


def make_softbody_case(path: str) -> None:
    """在测试模型上追加一个 PMX 2.1 柔体，覆盖柔体读写路径。"""
    m = pmx.load_pmx(os.path.join(ROOT, "tests", "test_model.pmx"))
    sb = pmx.SoftBody(
        name="测试柔体", name_en="soft", shape=0, material=0, group=2,
        mask=0xFFFF, flags=pmx.SB_BEND_LINK | pmx.SB_CLUSTER, b_link_dist=2,
        cluster_count=8, total_mass=1.5, collision_margin=0.02, aero_model=1,
        config=[0.5, 0.1, 1.0, 0.0, 0.0, 0.0, 0.15, 0.05, 1.0, 1.0, 1.0, 0.0],
        cluster=[0.3, 0.3, 0.3, 1, 1, 1],
        iteration=[0, 1, 0, 1],
        material_params=[1.0, 1.0, 1.0],
        anchors=[(0, 0, 0), (1, 5, 1)],
        pins=[0, 1, 2],
    )
    m.soft_bodies = [sb]
    pmx.save_pmx(m, path)


def run_probe(probe: str, src: str, dst: str) -> None:
    proc = subprocess.run([probe, "roundtrip", src, dst], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit("C++ 探针失败：\n%s\n%s" % (proc.stdout, proc.stderr))


def check_case(probe: str, src: str, py_out: str, cpp_out: str) -> bool:
    print("=" * 72)
    print("用例：%s" % src)
    m = pmx.load_pmx(src)
    pmx.save_pmx(m, py_out)
    run_probe(probe, src, cpp_out)

    ok = True
    for label_a, path_a, label_b, path_b in (
            ("原始", src, "Python", py_out),
            ("原始", src, "C++", cpp_out),
            ("Python", py_out, "C++", cpp_out)):
        res = pmxsem.diff(path_a, path_b, label_a, label_b)
        if res["total"]:
            ok = False
            print("-- %s vs %s：%d 处差异" % (label_a, label_b, res["total"]))
            print(pmxsem.fmt(res, maxlines=30))
        else:
            print("-- %s vs %s：一致" % (label_a, label_b))
    return ok


def main() -> int:
    probe = find_probe()
    print("探针：%s" % probe)
    with tempfile.TemporaryDirectory(prefix="pmx_parity_") as tmp:
        cases = list(sys.argv[1:])
        if not cases:
            cases = [os.path.join(ROOT, "tests", "test_model.pmx")]
            soft = os.path.join(tmp, "soft21.pmx")
            make_softbody_case(soft)
            cases.append(soft)
        ok = True
        for i, src in enumerate(cases):
            py_out = os.path.join(tmp, "py_%d.pmx" % i)
            cpp_out = os.path.join(tmp, "cpp_%d.pmx" % i)
            ok = check_case(probe, src, py_out, cpp_out) and ok
    print("=" * 72)
    print("结论：%s" % ("全部一致" if ok else "存在差异，见上方明细"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
