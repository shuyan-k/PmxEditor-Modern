# -*- coding: utf-8 -*-
"""Peek helper: `python tests/peek.py grep <file> <regex>` or `... cat <file> <a> <b>`."""
import io, re, sys

def main():
    mode, path = sys.argv[1], sys.argv[2]
    lines = io.open(path, encoding="utf-8", errors="replace").read().splitlines()
    if mode == "grep":
        pat = re.compile(sys.argv[3])
        for i, ln in enumerate(lines, 1):
            if pat.search(ln):
                print("%5d| %s" % (i, ln))
    else:
        a, b = int(sys.argv[3]), int(sys.argv[4])
        for i in range(a, min(b, len(lines)) + 1):
            print("%5d| %s" % (i, lines[i - 1]))

main()
