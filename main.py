# -*- coding: utf-8 -*-
"""PMX 编辑器启动入口：把 src 加入搜索路径后交给 pmxeditor.app。"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
for _path in (os.path.join(ROOT, "src"), ROOT):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from pmxeditor.app import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
