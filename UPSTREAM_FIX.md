# 上游修复说明（PmxStudio 便携运行时）

同步日期：2026-10-26　基准：`main` @ `289e15a`

## 1. 缺陷：`.gitignore` 规则未锚定，便携运行时缺失模块

`.gitignore` 中的 `_t*.py` 没有前导 `/`，Git 会把它匹配到**任意目录**下的所有 `_t` 开头 Python 文件，而 `build/python`（LFS 入库的便携 CPython 3.12.10）里恰好有大量这类文件。结果：

- 任何 `git clone` 得到的 `build\python\python.exe` 都无法 `import numpy`（`numpy/_core/_type_aliases.py` 缺失）；
- `OpenGL/raw/*/_types.py` 缺失，`import OpenGL.GL` 失败；
- `importlib/metadata/_text.py` 缺失，`pip` 与 `importlib.metadata` 不可用。

本地实测报错：

```
ModuleNotFoundError: No module named 'numpy._core._type_aliases'
ModuleNotFoundError: No module named 'importlib.metadata._text'
```

## 2. 上游需要的修改

1. `.gitignore` 第 64 行改为根目录锚定：

```diff
-_t*.py
+/_t*.py
```

2. 重新生成便携运行时并提交被漏掉的文件（推荐用 `tools/make_portable_python.ps1` 从干净的 CPython 3.12.10 重建，避免手工补文件与版本不一致）。
3. 建议 CI 增加一道门禁：用 `build/python` 跑一次 `import numpy, OpenGL.GL, PyQt5.QtWidgets`，或直接跑 `tests/go.py inventory`，防止同类遗漏再次进入发布包。

## 3. 本地已补回的文件（21 个）

包内文件（按 `requirements.txt` 对应版本 wheel 取回）：

```
build/python/Lib/site-packages/numpy/_core/_type_aliases.py
build/python/Lib/site-packages/numpy/lib/_twodim_base_impl.py
build/python/Lib/site-packages/numpy/lib/_type_check_impl.py
build/python/Lib/site-packages/OpenGL/raw/EGL/_types.py
build/python/Lib/site-packages/OpenGL/raw/GL/_types.py
build/python/Lib/site-packages/OpenGL/raw/GLES1/_types.py
build/python/Lib/site-packages/OpenGL/raw/GLES2/_types.py
build/python/Lib/site-packages/OpenGL/raw/GLES3/_types.py
build/python/Lib/site-packages/OpenGL/raw/GLX/_types.py
build/python/Lib/site-packages/OpenGL/raw/osmesa/_types.py
build/python/Lib/site-packages/OpenGL/raw/WGL/_types.py
build/python/Lib/site-packages/pip/_vendor/packaging/_tokenizer.py
build/python/Lib/site-packages/pip/_vendor/rich/_timer.py
build/python/Lib/site-packages/pip/_vendor/tomli/_types.py
build/python/Lib/site-packages/setuptools/_vendor/importlib_metadata/_text.py
build/python/Lib/site-packages/setuptools/_vendor/importlib_metadata/_typing.py
build/python/Lib/site-packages/setuptools/_vendor/packaging/_tokenizer.py
build/python/Lib/site-packages/setuptools/_vendor/tomli/_types.py
```

stdlib 文件（本机取自已安装的 Python 3.10，逻辑兼容；上游应从 3.12.10 重建拷回）：

```
build/python/Lib/_threading_local.py
build/python/Lib/importlib/metadata/_text.py
build/python/Lib/zoneinfo/_tzpath.py
```

## 4. 修复后验证

| 检查 | 结果 |
| --- | --- |
| `build\python\python.exe --version` | 3.12.10 |
| `import numpy / OpenGL.GL / PyQt5.QtWidgets / importlib.metadata` | 通过（NumPy 2.2.6，Qt 5.15.2） |
| `native\bullet_phys.dll` 加载 | 通过 |
| `tools\verify_native_backend.py tests\test_model.pmx --in-process --runs 1` | 26/26 通过 |
| 原生后端状态 | `available=True`，`C++ / Bullet` |

GUI 冒烟（`tests/go.py inventory`）未执行，需要弹窗环境。

## 5. 其他已修正项

- `README.md` 的同操作比对总数：`34 一致 / 7 差异 / 1 单侧` → `36 一致 / 5 差异 / 1 单侧`（第 366、405 行），与 `tests/parity/compare_all.md` 一致。
- `APP_VERSION = "1.0"` 与打包元数据 `1.0.1.0` 不一致，建议统一（本次未改）。
