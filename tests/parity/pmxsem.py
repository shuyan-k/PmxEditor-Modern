# -*- coding: utf-8 -*-
"""PMX 语义比较：把两份 pmx 解析成规范结构并逐字段求差（用于两个编辑器的同操作结果对比）。"""
import os, sys, json
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "src"))
from pmxeditor import pmx  # noqa: E402
import dataclasses

TOL = 1e-5


def load(path):
    return pmx.load_pmx(path)


def _ser(v):
    if isinstance(v, np.ndarray):
        return v
    if dataclasses.is_dataclass(v):
        d = {f.name: _ser(getattr(v, f.name)) for f in dataclasses.fields(v)}
        d["__type"] = type(v).__name__
        return d
    if isinstance(v, (list, tuple)):
        return [_ser(x) for x in v]
    return v


def dump(path):
    m = load(path)
    return {
        "version": m.version, "encoding": m.encoding, "add_uv": m.add_uv,
        "name": m.name, "name_en": m.name_en, "comment": m.comment, "comment_en": m.comment_en,
        "textures": list(m.textures),
        "v_pos": m.v_pos.copy(), "v_nrm": m.v_nrm.copy(), "v_uv": m.v_uv.copy(),
        "v_add": m.v_add.copy(), "v_edge": m.v_edge.copy(), "v_wtype": m.v_wtype.copy(),
        "v_bones": m.v_bones.copy(), "v_weights": m.v_weights.copy(), "v_sdef": m.v_sdef.copy(),
        "indices": m.indices.copy(),
        "materials": [_ser(x) for x in m.materials],
        "bones": [_ser(x) for x in m.bones],
        "morphs": [_ser(x) for x in m.morphs],
        "frames": [_ser(x) for x in m.frames],
        "rigid": [_ser(x) for x in m.rigid],
        "joints": [_ser(x) for x in m.joints],
        "soft": [_ser(x) for x in m.soft_bodies],
        "stats": pmx.model_stats(m),
    }


def _eq(a, b):
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        a = np.asarray(a); b = np.asarray(b)
        if a.shape != b.shape:
            return False
        if a.dtype.kind in "fc" or b.dtype.kind in "fc":
            return bool(np.allclose(a, b, atol=TOL, rtol=0))
        return bool(np.array_equal(a, b))
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) <= TOL
        except Exception:
            return a == b
    if isinstance(a, (int, str, bool)) or isinstance(b, (int, str, bool)):
        return a == b
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            return False
        return all(_eq(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_eq(x, y) for x, y in zip(a, b))
    return a == b


def _walk(a, b, path, out, limit=12):
    if len(out) >= limit:
        return
    if _eq(a, b):
        return
    if isinstance(a, dict) and isinstance(b, dict) and set(a) == set(b):
        for k in a:
            if not _eq(a[k], b[k]):
                _walk(a[k], b[k], path + "." + str(k), out, limit)
        return
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            if not _eq(x, y):
                _walk(x, y, "%s[%d]" % (path, i), out, limit)
        return
    out.append((path, _brief(a), _brief(b)))


def _scalar(x):
    if isinstance(x, float):
        return round(x, 6)
    return x


def _brief(v):
    """把差异值压成短文本；任何序列都比较前 4 项并截断，避免深递归。"""
    if isinstance(v, np.ndarray):
        flat = v.ravel()
        head = [_scalar(x) for x in flat[:4].tolist()]
        tail = "" if flat.size <= 4 else "…(%d)" % flat.size
        return "arr%s=%s%s" % (list(v.shape), head, tail)
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, (list, tuple)):
        head = [_brief(x) for x in list(v)[:4]]
        tail = "" if len(v) <= 4 else "…(%d)" % len(v)
        return "[" + ", ".join(json.dumps(x, ensure_ascii=False) for x in head) + "]" + tail
    if isinstance(v, dict):
        s = json.dumps({k: _brief(x) for k, x in list(v.items())[:6]}, ensure_ascii=False)
        return s if len(s) < 90 else s[:87] + "..."
    if isinstance(v, str) and len(v) > 60:
        return repr(v[:57] + "...")
    return v


def diff(pa, pb, label_a="A", label_b="B", limit=12):
    da, db = dump(pa), dump(pb)
    res = {"%s" % label_a: pa, label_b: pb, "stats_a": da["stats"], "stats_b": db["stats"],
           "sections": {}, "total": 0}
    for key in da:
        if key == "stats":
            continue
        out = []
        _walk(da[key], db[key], key, out, limit)
        if out:
            res["sections"][key] = out
            res["total"] += len(out)
    return res


def fmt(res, maxlines=40):
    lines = ["stats A=%s" % res["stats_a"], "stats B=%s" % res["stats_b"]]
    if not res["sections"]:
        lines.append("== 语义完全一致 ==")
        return "\n".join(lines)
    n = 0
    for k, items in res["sections"].items():
        lines.append("● %s (%d 处)" % (k, len(items)))
        for p, a, b in items:
            lines.append("   %-42s A=%s  B=%s" % (p, a, b))
            n += 1
            if n >= maxlines:
                lines.append("   ...")
                return "\n".join(lines)
    return "\n".join(lines)


if __name__ == "__main__":
    r = diff(sys.argv[1], sys.argv[2])
    print(fmt(r))
