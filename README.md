# PmxStudio

PMX（MikuMikuDance 模型格式）查看与编辑工具，仓库内包含两套独立实现：

| 版本 | 技术栈 | 入口 | 说明 |
| --- | --- | --- | --- |
| **Python 版** | Python 3.12 + PyQt5 + OpenGL + Bullet（可选 pybind11 加速） | `run.bat` / `main.py` | 功能最全，带 GUI 自动化测试，打包为单文件 exe 发行 |
| **C++ 版** | C++20 + GLFW 3.4 + Dear ImGui + OpenGL 4.6 + Bullet 3.26 | `cpp/build/Release/pmxstudio.exe` | 原生重写，无 Python 依赖，GPU Compute Shader 蒙皮 |

两版共用同一份测试模型 `tests/test_model.pmx` 与同一份 Bullet 源码（`native/bullet_src`），PMX 读写语义由 `tools/parity_check.py` 做跨实现逐字段校验。

## 功能

- **PMX 数据**：2.0 / 2.1 读写，保留编码、索引宽度、顶点权重等原始字段；结构校验与统计。
- **检查器面板**（两版均为十个）：信息、骨骼、表示枠、顶点、材质、面、形态、物理、柔体、设置。
- **姿态与 IK**：FK、付与继承、CCD IK 与逐轴角度限制、骨骼拖动；VPD 姿态导入 / 导出。
- **形态**：顶点 / UV / 材质 / 骨骼 / 组 / 翻转 / 刚体偏移，滑杆预览（不写入文件）。
- **物理**：Bullet 刚体 / 关节 / 柔体，固定 1/60 步进，可边演算边摆姿；重力、迭代次数、地面可调。
- **编辑**：结构增删与索引重映射、撤销 / 重做（整模型快照 + 轻量姿态条目）、拖放打开、主题切换与偏好持久化。
- **渲染**：贴图 / 灰模、线框、卡通光照、模板缓冲描边、地面网格、骨骼 / 刚体 / 关节叠加层与拾取。

## 快速开始

### Python 版（推荐，仓库自带运行时）

```powershell
.\run.bat                        # 启动
.\run.bat "D:\MMD\模型.pmx"      # 直接打开模型
```

`run.bat` 优先使用 `build\python\pythonw.exe`（便携 CPython 3.12，含 PyQt5 / PyOpenGL / NumPy），缺失时回退系统 Python。也可用自有环境：

```powershell
python -m pip install -r requirements.txt
python main.py "模型.pmx"
```

原生加速后端与 Bullet 物理库为可选项：

```powershell
.\build\python\python.exe native\setup_core.py build_ext --inplace   # pmx_core 计算后端
powershell -ExecutionPolicy Bypass -File native\build_core.ps1       # 一键构建
powershell -ExecutionPolicy Bypass -File native\build.ps1            # bullet_phys.dll
```

扩展或 DLL 缺失时自动回退到 NumPy 参考实现，状态栏会显示当前后端。

### C++ 版

需要 CMake ≥ 3.20 与支持 C++20 的编译器（Windows 上为 MSVC 2019/2022）。

```powershell
cmake -S cpp -B cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build cpp/build --config Release

cpp\build\Release\pmxstudio.exe tests\test_model.pmx
cpp\build\Release\pmx_tests.exe            # 无窗口对照测试
```

依赖（GLFW / ImGui / stb_image / Bullet）默认从 gitee 镜像拉取，可用 `-DPMX_DEPS_MIRROR=https://github.com` 切换；CMake 选项与实现细节见 [cpp/README.md](cpp/README.md)。

## 操作

| 操作 | Python 版 | C++ 版 |
| --- | --- | --- |
| 选中骨骼 / 刚体 / 关节 | 左键双击（可重叠循环） | 左键双击（空白处取消） |
| 移动 / 旋转骨骼 | 左键 / 右键拖动已选骨骼 | 同左 |
| 旋转 / 平移 / 缩放视图 | 左键空白 / 右键空白 / 滚轮 | 同左（`Shift`+中键平移） |
| `F` / `R` / `P` | 视图居中 / 重置姿态 / 物理开关 | 同左 |
| `Ctrl+O` / `Ctrl+S` / `Ctrl+Shift+S` | 打开 / 保存 / 另存为 | 同左 |
| `Ctrl+Z` / `Ctrl+Y` / `Ctrl+Shift+Z` | 撤销 / 重做 | 同左 |

物理演算也可以从界面开关：Python 版在工具栏与「视图 → 物理演算」，C++ 版在「设置 → Bullet 物理 → 物理演算」。

## 测试

```powershell
# Python 版 GUI 自动化测试（真实点击驱动，场景定义见 tests/run.py）
$env:PYTHONUTF8="1"
.\build\python\python.exe tests\go.py inventory dark tests\test_model.pmx

# C++ 版对照测试：205 项检查，不创建窗口
cpp\build\Release\pmx_tests.exe

# 跨实现一致性：原始 / Python / C++ 三向逐字段比较
.\build\python\python.exe tools\parity_check.py
.\build\python\python.exe tools\parity_check.py "D:\MMD\模型.pmx"   # 追加真实模型用例
```

已用「残虹」模型（98404 顶点 / 843 骨骼 / 718 刚体 / 930 关节）完成物理与十个面板的截图对比，结果见 [对比测试报告](docs/canhong-parity/index.html)。

## 目录结构

```
PmxStudio/
├─ main.py / run.bat        # Python 版入口
├─ src/pmxeditor/           # Python 版源码：app、panels、viewport、skinning、physics、pmx
├─ native/                  # pybind11 扩展与 Bullet 物理库
├─ cpp/                     # C++ 版：CMake 工程、core / gpu / physics / app、对照测试
├─ tests/                   # 测试模型、GUI 自动化测试、parity 语义比较
├─ tools/                   # parity_check.py 等工具脚本
├─ docs/canhong-parity/     # 残虹模型全量对比测试报告（截图）
└─ build/python/            # 便携 Python 运行时（仓库自带，勿手改）
```

Python 版的模块划分见 `src/pmxeditor/` 下各模块文件头注释；C++ 版的架构、坐标系与实现要点见 [cpp/README.md](cpp/README.md)。

## Code signing policy

**Free code signing provided by [SignPath.io](https://about.signpath.io/), certificate by [SignPath Foundation](https://signpath.org/).**

- Committers and reviewers: [@shuyan-k](https://github.com/shuyan-k)
- Approvers: [@shuyan-k](https://github.com/shuyan-k)

每次发布的 `PmxStudio.exe` 由仓库内 GitHub Actions（`.github/workflows/build.yml`）从当前源码构建后交由 SignPath.io 签名；签名表示该二进制确实由本仓库源码构建。

隐私政策：本程序不会向任何联网系统传输信息，除非用户明确要求。

## 已知限制

- 不实现 VMD 动画（数据、时间轴与播放）。
- Python 版的柔体只读写与编辑，不参与 Bullet 演算；C++ 版支持柔体演算。
- IK 限位按欧拉逐轴钳制（与 MMD 一致），接近 ±90° 时用分支滞回保持连续。
- 文件对话框与中文路径处理当前仅针对 Windows；Linux 需自行准备 OpenGL / 窗口系统开发包。
- 两版界面形态不同（Python 为左侧导航 + 右侧检查器，C++ 为检查器标签栏），部分显示类开关（亮度、材质透贴、GPU 蒙皮）为单侧独有。

## 许可

[GNU General Public License v3.0](LICENSE)。
