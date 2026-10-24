import io, sys

def sub(path, old, new, count=1):
    with io.open(path, encoding="utf-8") as f:
        s = f.read()
    n = s.count(old)
    if n != count:
        raise SystemExit("MISMATCH %s: found %d expected %d\n---\n%s" % (path, n, count, old[:300]))
    s = s.replace(old, new)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(s)
    print("patched", path, count)
