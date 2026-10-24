# PmxEditor Modern

用 **Python + PyQt5 + OpenGL + Bullet** 重写的 PMX 模型编辑器，目标是在保留 MMD 语义（付与、IK、物理、形态）的前提下，提供一个跨平台、可脚本化、可自动回归测试的 PMX 工具链。

- 纯 Python 界面与渲染，数值热点（蒙皮、层级/付与矩阵、CCD IK、形态累加、物理批处理）由可选的 pybind11 C++ 扩展加速；扩展缺失时自动回退到 NumPy 参考实现，状态栏会显示当前后端。
- 自带真实点击驱动的 GUI 自动化测试（`tests/`），可在无人工干预下遍历全部控件并输出异常清单。
- 仓库自带可移植的 Python 运行时（`build/python`），编译、打包、回归都不依赖宿主机已安装的 Python。

> 当前状态：开发版，已完成真实 PMX 模型（79848 顶点 / 321 骨骼 / 183 刚体）的加载、渲染、编辑、物理与保存往返验收；尚未在无开发工具环境的干净机器上做跨驱动复测。

## 功能概览

| 子系统 | 已支持 | 边界 |
| --- | --- | --- |
| PMX 数据 | 2.0 / 2.1 读写、统计与校验；保留编码、索引宽度与顶点权重原始字段 | 能读写不等于所有类型都能在视口中预览或编辑 |
| 主界面 | 模型信息、骨骼、材质、形态、物理、显示/主题设置六个检查器页；设置页含背景/模型亮度滑杆（显示用，不写入模型）；打开/保存/另存为/拖放/关闭；VPD 姿态导入导出 | 无动作/关键帧编辑，姿态只做静态预览 |
| 骨骼编辑 | 层级、名称、父级、变形层级、位置、尾端、旋转/移动付与、轴固定、IK 参数；新建/复制/删除/搜索；进入骨骼页自动显示骨架；可选「移动时带动顶点」（按蒙皮权重把位移写进顶点） | 深层树紧凑缩进，长名称可能省略（悬停看完整名称） |
| 材质编辑 | 漫反射/高光/环境色、纹理与球面纹理、Toon、绘制标志、描边、备注 | 材质形态为近似预览 |
| 形态 | 列表与新建/复制/删除；顶点、骨骼、UV、材质、组、翻转形态预览（组/翻转递归展开） | 冲量、附加 UV 形态不改变视口（前者需物理回放，后者是独立 UV 通道） |
| 姿态与 IK | FK 拖动、IK 控制器拖动、CCD IK、付与继承、蒙皮（BDEF1/2/4，SDEF/QDEF 按 BDEF2 处理）、姿态重置；VPD 导入导出；撤销/重做 | IK 限位按欧拉逐轴钳制（与 MMD 一致），近 ±90° 用分支滞回保持连续；末端残差仍偏大的链会从静止姿态重解一次，取更接近目标的解 |
| 物理 | Bullet 刚体/关节构建与实时步进，骨骼跟随与动态刚体，姿态覆盖与重置 | PMX 2.1 软体只读写不演算；重力与迭代次数可热更新，其余参数需重建物理世界 |
| 视口 | 贴图/灰模、线框、卡通光照、描边、地面网格、骨骼/刚体/关节叠加、背景/模型亮度、拾取与 HUD | 整帧性能取决于 GPU、驱动与显示开关 |
| 编辑历史 | 模型编辑撤销/重做（12 步，0.9 s 内同键合并）；姿态拖动/`R` 重置/VPD 导入用轻量姿态条目，不占整模型快照 | 模型快照与姿态条目各有 12 步预算，互不挤占；不是无限历史 |
| 发布 | Nuitka 单文件发行包，内置 `--verify-backend` 数值对拍；构建命令见「打包与发布」，产物不入库（`dist/` 由构建生成，仓库不保留 exe） | 跨驱动（另一块 GPU）复测仍待完成 |

### 视口鼠标约定

| 操作 | 行为 |
| --- | --- |
| 左键拖动 | 旋转视图（浏览模式下拖动即旋转，位移小于 3 px 仍算单击） |
| 右键拖动 | 平移视图 |
| 左键单击 | 选择骨骼 / 刚体 / 关节（点空白处取消选择；Alt+单击在重叠目标间循环） |
| 姿态模式左键拖动骨骼 | 旋转骨骼；拖动 IK 控制器移动目标（骨骼优先于视角旋转） |
| 滚轮 | 缩放视图 |
| 中键拖动 | 兼容旧习惯：旋转视图；`Shift` + 中键拖动平移 |
| `F` / `R` | 视图居中 / 重置姿态（全局快捷键，重置可用 Ctrl+Z 撤销） |

物理模式下左键拖动刚体不施加冲量（当前只做选择）。

## 快速开始

### 方式一：仓库自带运行时（推荐，无需安装 Python）

```powershell
.\run.bat                       # 双击或用命令启动
.\run.bat "D:\MMD\模型.pmx"     # 直接打开模型
```

`run.bat` 优先使用 `build\python\pythonw.exe`，缺失时才回退到系统的 `pythonw.exe`。`build\python` 是 `tools\make_portable_python.ps1` 生成的便携 CPython 3.10（含 PyQt5 / PyOpenGL / NumPy / pybind11），重建方式见 [开发与构建](#开发与构建)。

### 方式二：自有 Python 环境

```powershell
python -m pip install -r requirements.txt
python main.py "测试模型.pmx"
```

要求 64 位 CPython 3.10（原生扩展按 cp310 编译），依赖见 `requirements.txt`：PyQt5 5.15.11、PyOpenGL 3.1.10、NumPy 1.23.1、pybind11 >= 2.11, < 4。

## 目录结构

```
PmxEditor_Modern/
├─ main.py                  # 启动入口：把 src 加入 sys.path 后调用 pmxeditor.app.main
├─ src/pmxeditor/           # 应用包（全部业务代码）
│  ├─ app.py                # 主窗口、菜单、模式、文件操作、主题切换
│  ├─ panels/               # 右侧六个检查器页（按页面分模块）
│  │  ├─ base.py            #   PageBase 与共用小工具
│  │  ├─ info/bone/material/morph/physics/settings.py
│  │  └─ __init__.py        #   重导出各页面类
│  ├─ viewport/             # OpenGL 视口（按职责分模块）
│  │  ├─ core.py            #   Viewport：渲染、拾取、拖拽、姿态与物理预览
│  │  ├─ camera.py          #   OrbitCamera
│  │  ├─ shaders.py         #   着色器源码与编译
│  │  ├─ geom.py            #   几何小工具
│  │  ├─ hud.py             #   HUD 覆盖层
│  │  └─ __init__.py        #   重导出 Viewport / 颜色常量
│  ├─ ui_widgets.py         # 自绘控件（Card/Section/Switch/Segmented/EntryList/BoneTree…）
│  ├─ theme.py              # 配色、字体、样式表、矢量图标
│  ├─ doc.py                # 文档模型：撤销栈、选中项、结构编辑原语
│  ├─ pmx.py                # PMX 2.0/2.1 读写与数据结构
│  ├─ skinning.py           # Pose、层级/付与、CCD IK、蒙皮、形态
│  ├─ physics.py            # Bullet 封装（ctypes）
│  ├─ vpd.py                # VPD 姿态解析、匹配与导出
│  ├─ gl_names.py           # 日文骨骼/材质/形态名的中文对照
│  ├─ native_backend.py     # 加载 _pmx_core 扩展并报告后端状态
│  ├─ paths.py              # 资源/原生库路径锚点
│  └─ _pmx_core.cp310-win_amd64.pyd   # pybind11 计算后端（构建产物）
├─ assets/                  # 图标等静态资源
├─ native/                  # Bullet 与 pybind11 后端源码及构建脚本
│  ├─ pmx_core.cpp          # C++ 计算后端源码
│  ├─ bullet_wrap.cpp       # Bullet C 包装层
│  ├─ setup_core.py         # 构建 _pmx_core（setuptools + pybind11）
│  ├─ build_core.ps1        # 一键构建计算后端
│  ├─ build.ps1             # 一键构建 bullet_phys.dll
│  ├─ obj/                  # cl.exe 的中间文件与导入库（不入库）
│  └─ bullet_phys.dll       # 物理库（构建产物）
├─ tools/                   # 命令行工具（数值对拍、VPD 校验、性能基准、便携 Python）
├─ tests/                   # GUI 自动化测试（真实点击驱动）+ 测试模型
├─ build/python/            # 便携 CPython 3.10（编译与回归统一使用）
├─ requirements.txt
├─ run.bat
└─ .gitignore
```

## 架构

### 分层与依赖

```
                    src/pmxeditor/app.py（主窗口 / 模式 / 文件 / 主题）
                   /        |            |             \
          panels/      ui_widgets.py    theme.py      viewport/
              |              |              |               |
            doc.py           |              |          physics.py
              |              |              |               |
            pmx.py <--------------------- skinning.py <----+
```

- `pmx.py` 只依赖标准库与 NumPy，不依赖 Qt。
- `skinning.py` 只依赖 NumPy 与 `pmx.py` 的常量，不依赖 Qt。
- `physics.py` 依赖 `skinning.py` 与 ctypes，不依赖 Qt。
- `vpd.py` 依赖 NumPy 与 `skinning.py` 的 `IDENTITY_Q`，不依赖 Qt；解析与匹配结果由 `app.py` 负责应用。
- `viewport/` / `panels/` / `app.py` 属于界面层，可以依赖下层全部模块。
- **下层不得反向导入界面层**，避免循环依赖。
- 包内一律使用相对导入（`from .pmx import ...`）；只有 `main.py` 负责把 `src` 放进 `sys.path`。

### 关键不变量（修改前必读）

1. `base_*` 是编辑源，`rot/trans` 是生效值；拖拽后必须 `world_update()`。
2. IK 求解必须同时写 `base_rot` 与 `rot`，否则迭代会在旧姿态上重复。
3. 世界空间增量旋转必须**左乘**局部旋转。
4. CCD 每条链修正后必须立即刷新末端位置。
5. `world()` 依赖 `eval_order`，付与来源必须先于当前骨骼求值。
6. 物理结果通过 `ov_rot/ov_trans` 覆盖，退出物理模式要清除覆盖。
7. 任何姿态/形态/物理变化都要失效 `world_cache` 与 `_dirty`。
8. 界面修改模型必须走 `Document.edit` / `push_undo`，不要直接改 dataclass。
9. 改动骨骼的静止位置/父级/付与/IK 后必须让视口重建 `Pose`/`SkinDeformer`（`Viewport.ensure_pose_current()` 会按 `pose_state()` 签名自动重建）；`doc.undo/redo` 会替换 `Document.model` 对象，界面需按身份判断是否重新 `set_model`。

### 关键数据流

| 场景 | 路径 |
| --- | --- |
| 打开模型 | `app.open_path` → `_maybe_save` → `Document.load`（`pmx.load_pmx`）→ `viewport.set_model` → `_refresh_pages` |
| 面板编辑 | 控件信号 → `PageBase.edit()` → `doc.edit(kind)` → `push_undo` + 修改 + `edited.emit(kind)` → `app._on_edited`（状态栏 + 局部刷新） |
| 结构编辑 | `doc.add_*/duplicate_*/remove_*`（含索引重映射）→ `edited("structure")` → `app._reload_structure()` 重建 Pose/Deformer/网格/物理 |
| 姿态拖动 | `viewport.mouseMoveEvent` → `Pose.rotate_world` → `world_update` → `SkinDeformer.deform` → VBO 更新 → 重绘（首次位移才压撤销栈） |
| 物理模式 | `viewport.set_mode("physics")` → `physics.MMDPhysics.step` → 刚体结果回写 `ov_*` → 蒙皮 → 重绘 |
| 保存 | `app.save` → `pmx.save_pmx`（按内容决定 2.0/2.1 与索引宽度）→ `doc.dirty=False` |
| VPD 导出 | `vpd.build_vpd_text`（只导出偏离初始姿态的骨骼与非零形态）→ CP932 写入 |

## 核心模块

### `pmx.py` — 数据层

`PMXModel` 持有 `v_pos/v_nrm/v_uv/v_add/v_edge/v_bones/v_weights/v_sdef/indices` 等 NumPy 数组与 `materials/bones/morphs/frames/rigid/joints/soft_bodies` 列表；`Bone`/`Material`/`Morph`/`RigidBody`/`Joint`/`SoftBody`/`IK`/`IKLink` 为 dataclass。形态偏移是 dict 列表（`vertex+offset` / `bone+move+rot` / `material+…` / `morph+ratio`）。`save_pmx` 自动决定写入 2.0 还是 2.1 以及各级索引宽度；真实模型 `米娅.pmx` 的保存往返为**字节数一致、顶点/UV 最大差 0**。

### `doc.py` — 文档与撤销

`Document` 暴露 `edited/status/selectionChanged/dirtyChanged` 信号，撤销栈上限 `UNDO_LIMIT = 12`；`push_undo` 在 0.9 s 内对同键操作做合并（coalesce）。撤销条目是 `(label, model, pose, morphs)`：**`model is None` 表示姿态条目**（只存 `Pose` 的 `base_rot/base_trans` 与形态权重，不做整模型深拷贝，约 0.04 ms vs 27 ms），`undo/redo` 见到它只回滚姿态并 `edited.emit("pose")`，不替换 `Document.model`、不触发结构重建。所有会改变索引的结构操作集中在 `add_*/duplicate_*/remove_*`（`remove_bone` 会重映射父级、尾骨、付与、IK、顶点权重、形态、刚体与显示枠；`remove_rigid` 会连带删除引用它的关节）。

### `skinning.py` — 姿态、付与、IK、蒙皮

`Pose` 保存 `base_rot/base_trans`（编辑源）与 `rot/trans`（生效值）、`eval_order`、`world_cache` 与 `_dirty`。付与继承区分 `BF_INHERIT_ROT` / `BF_INHERIT_MOV` / `BF_LOCAL_APPEND`，按 `eval_order` 求值；IK 为 CCD 实现（逐链刷新末端、世界增量左乘），并以 FK 旋转作为迭代初值；若某条链解完末端残差仍超过 `ik_retry_tolerance`（0.05 模型单位），会把这条链的骨骼旋转清零后单独重解一次，只有残差变小才采用，避免从大角度初值收敛到镜像解（实测米娅帧 136 双膝跨到身体另一侧，修复后右膝 x=-2.78/左膝 x=+2.40，与 MMD 同侧）；蒙皮支持 BDEF1/2/4，**SDEF/QDEF 顶点在蒙皮阶段一律按 BDEF2 处理**（`_sdef_fallback_table()` 把 type 3 映射成 1）：真机膝带实测 SDEF 到关节中心 0.661/0.540、相邻 BDEF2 0.610/0.517，SDEF 会把膝盖顶出 0.05~0.16、侧视有台阶，而 PmxEditor 的膝盖观感就是 BDEF2。SDEF 求值器仍完整保留在原生 `_pmx_core` 与 NumPy 回退两条路径上（语义一致），只作对拍基线——`go.py skin/ellipsoid/sdefr1` 直接调 `native_core.deform` 比对两条路径。它的半轴按逐轴 `|R − C|` 计算：PMX 里 R0/R1 存的是"点"，模型库实测 `R0−C` 与 `R1−C` 恒为 180° 反向、`|R0|` 是骨骼长度量级，直接当半径会把膝带顶点整体外推 0.15；原始 R1 全零时回退 R0，R1==R0 时与只用 R0 的实现逐位一致。`.pmx` 里的 C/R0/R1 原样解析与回写。

### `physics.py` — Bullet

用 ctypes 加载 `native/bullet_phys.dll`（C 包装层 `bw_*`）。刚体语义与 MMD 对齐：`跟随骨骼` 为运动学体、`物理演算` 由 Bullet 求解并回写、关节用 `btGeneric6DofSpringConstraint` 保留三轴限位与弹簧、限位 `min > max` 视为自由轴。PMX 2.1 软体只读写不演算。

### `viewport/` — 渲染与交互

自绘 `QOpenGLWidget`：网格按材质批次上传，绘制顺序为 地面/阴影 → 不透明 → 透明（`MF_DOUBLE_SIDED` 关闭背面剔除）→ 描边 → 叠加层 → HUD。贴图缓存键是 `(贴图路径, 是否球面)`，**编辑材质不会清空缓存**（只有 `initializeGL` 建立新上下文时才清一次）。相机为轨道相机，拾取用屏幕距离启发式（骨骼/刚体/关节，按屏幕距离与深度排序，Alt+单击循环重叠目标），HUD 空闲时显示"空闲"而不是残留 FPS。

### `panels/` / `ui_widgets.py` / `theme.py` — 界面层

`panels/` 的六个页面都继承 `PageBase`（`base.py`）（`edit()/scroll()/select()/refresh()`）。回填数据时必须置 `self.loading = True`（并在 `finally` 里恢复原值，不要无条件写 `False`），否则信号回环会触发编辑与压栈。`ui_widgets.py` 提供自绘控件；`EntryList` 在过滤到 0 行、`BoneTree` 在无匹配时显示占位提示。`theme.py` 负责深/亮两套配色与 SVG 图标，`paths.ASSETS` 指向仓库根 `assets/`。

## 原生计算后端

C++ 后端（`native/pmx_core.cpp`，pybind11）以 NumPy buffer 直接访问连续的模型/姿态数组，覆盖蒙皮、层级与付与矩阵、CCD IK、顶点/UV/骨骼形态稀疏累加与物理批处理；Python 仍负责模型/UI/姿态状态与缓存、视口几何准备与渲染。扩展缺失时自动回退到 NumPy 参考实现，状态栏显示 `C++ / Bullet` 或 `NumPy 回退 · 需构建 C++ 后端`。

**Windows 上必须先导入 `native_backend`、再导入 PyQt5**：MSVC 扩展若在 Qt DLL 加载后才初始化会触发访问冲突。

```powershell
# 只构建计算后端（需要 pybind11 + VS2022 C++ 工具链）
.\build\python\python.exe native\setup_core.py build_ext --inplace
# 或者一键脚本
powershell -ExecutionPolicy Bypass -File native\build_core.ps1

# 构建 Bullet 物理库（需要 VS2022 BuildTools + Windows SDK）
powershell -ExecutionPolicy Bypass -File native\build.ps1
```

数值对拍（Python 参考实现 vs C++ 后端，含物理世界与输出缓冲）：

```powershell
.\build\python\python.exe tools\verify_native_backend.py "模型.pmx" --in-process --runs 3
```

## VPD 姿态导入与导出

- 支持标准 VPD（两行块）与旧式父索引块；名称按「日文名 → 英文名 → 中文译名」宽松匹配，未匹配的骨骼保持初始姿态、形态保持当前预览。
- 导入只写 `Pose`，不改模型数据；导入与随后的姿态调整都进撤销栈。
- 导出只包含**偏离初始姿态**的骨骼与非零形态，因此"摆好姿势 → 导出 → 再导入"可以复现姿态，但不会导出一份与初始姿态相同的空文件（零变化时直接拒绝并提示）。
- 文件编码按 CP932 写入、读取时回退 UTF-8；默认文件名 `<模型名>_pose.vpd`。
- IK 求解过的链骨骼会一并导出，因此导出的骨骼数可能多于 VPD 中的骨骼数。
- 校验工具：`.\build\python\python.exe tools\verify_vpd.py "模型.pmx"`（覆盖解析、编码、匹配、应用、导出与回读）。

## 开发与构建

### 便携 Python 运行时

`build/python` 是精简的 CPython 3.10.9（约 210 MB，含 PyQt5 / PyOpenGL / NumPy / pybind11 / setuptools / pip，已剔除测试套件、tkinter、翻译与 `.pyi/.pdb`）。重建：

```powershell
powershell -ExecutionPolicy Bypass -File tools\make_portable_python.ps1 -Source "C:\Python310\python.exe"
```

源码解释器必须是 **3.10**（原生扩展是 cp310），且路径应保持纯 ASCII —— 构建解释器装在含中文的路径下时，Qt 会把插件路径编码成 `05_??`，Nuitka 报 `failed to detect PyQt5 plugin directories`。

### 代码约定

- 界面文本、状态栏、提示、注释统一使用中文；模块顶部保留职责说明 docstring。
- 数值计算统一 `numpy.float32`，索引 `int32/int64`；避免在逐顶点循环里做 Python 运算。
- 矩阵为列向量约定（平移在第 4 列），四元数顺序 `(x, y, z, w)`。
- PMX 的旋转/角度在数据层是**度数**，进入姿态与物理前转弧度。
- 姿态不是 PMX 数据：所有姿态结果只写 `Pose`，保存时不得写入模型。
- 模型字段的可编辑修改必须经 `Document.edit()` / `push_undo()`，否则撤销栈与脏标记会失配。
- 新增/删除骨骼、材质、刚体等会改变索引的操作，重映射逻辑放在 `doc.py`，面板只调用。
- 界面回填数据时置 `self.loading = True`，并用 `prev = self.loading` / `finally: self.loading = prev` 的写法（无条件写 `False` 会破坏外层守卫，物理页曾因此无限递归）。
- 不要绕过 `world_update()` 直接读 `base_*` 之后的 `rot`。
- 编辑路径不要整体清空贴图缓存，也不要在字段编辑时走全量结构重建。

### 本地设置

所有可记忆的状态都写在 `QSettings("PmxEditorModern", "editor")`，不落到模型文件里：

| 键 | 含义 |
| --- | --- |
| `theme` | 深色 / 亮色主题 |
| `geometry` / `splitter` | 窗口位置大小与左右分栏比例 |
| `view/bg_brightness` / `view/model_brightness` | 视口背景与模型亮度（1.0 为默认） |
| `editor/move_bone_vertices` | 骨骼页「移动时带动顶点」开关 |
| `last_dir` / `last_vpd_dir` | 打开模型、导入导出 VPD 时记住的目录 |

想恢复出厂状态可以删掉这段注册表配置（`HKCU\Software\PmxEditorModern\editor`）。

## 测试与验证

### GUI 自动化测试（`tests/`）

`tests/harness.py` 提供真实点击驱动：`QApplication.widgetAt` 命中测试（被遮挡时自动改点遮挡者并记异常；窗口未登记到桌面时回退到 `WIN.childAt(mapFromGlobal())`）、`QTest.mouseClick/mouseDClick`、滚动区 `ensureWidgetVisible`、窗口截图与像素差分、对话框打桩（文件/颜色/消息框）、槽内异常收集与 `tests/report.json` 输出。`tests/run.py` 是场景集合，`tests/go.py` 是入口：

```powershell
$env:PYTHONUTF8="1"     # 控制台是 GBK 时必须设置，否则中文日志抛 UnicodeEncodeError
.\build\python\python.exe tests\go.py <场景> dark tests\test_model.pmx
```

常用场景：

| 场景 | 覆盖内容 |
| --- | --- |
| `inventory` | 窗口/管理器/菜单/页面/控件清单与实际几何，冒烟 |
| `walk` | 逐页遍历所有可见可用控件（单击/双击/输入/逐行点击/开关），输出异常清单 |
| `verify_p0` | 回归：颜色按钮不崩溃、物理页 `doc.select("rigid", i>0)` 不递归 |
| `flag8` | 材质绘制标志复选框的点击命中与模型写回 |
| `rows_fix` | 列表行宽随视口重算（右侧信息不被裁掉） |
| `fix2` | 点视口空白取消选择、姿态模式单击不压撤销栈 |
| `fps` | HUD FPS 空闲衰减 |
| `tree2` / `empty` | 骨骼树右键菜单、空列表占位提示 |
| `sync` | VPD 导入/导出全流程（需真实模型） |
| `themesync` | 主题切换后视口/控件的颜色常量是否跟着变（深<->亮双向） |
| `opt` | 网格 VBO 复用（三次重建 id 不变）、页面刷新保留滚动、贴图预热产出、关闭时释放 GL 资源 |
| `optb` | 量化贴图预热收益（有/无预热的 `set_model` + 首帧耗时） |
| `undo` | 快照快速深拷贝提速、快照与在线模型隔离、撤销后另存字节一致 |
| `undo2` | `deepcopy` 各字段耗时分布 |
| `rest` | 改骨骼位置/尾端/父级后 Pose 与蒙皮静止位置是否跟着重建、撤销是否复原 |
| `vp` | 视口拾取、左键选择、中键/右键拖动、F/R 快捷键、姿态拖动、物理刚体拾取（拖动类交互直接投递 QMouseEvent，因为 `QTest.mouseMove` 走光标路径、在本环境到不了控件） |
| `bright` | 设置页亮度滑杆传到视口（背景清屏色、模型漫反射倍率）、写入 QSettings、恢复默认、视口像素确实变化、背景提亮后网格与 HUD 翻深色 |
| `mouse` | 左键拖动旋转/右键拖动平移/空白单击取消选择；「移动时带动顶点」开关持久化 |
| `skin` | SDEF 球面半径保持、QDEF 同矩阵等价刚体、NumPy 回退与原生一致（合成夹具） |
| `ellipsoid` | SDEF 椭球：半轴取逐轴 \|R−C\|（PMX 里 R0/R1 存的是点）、静止回到球面半径、双骨骼混合时按 R0 各向异性伸缩、回退与原生一致 |
| `sdefr1` | SDEF 的 R1：原始值全零才回退 R0（C 非零时不能看 \|R1−C\|）、R1==R0 与旧实现一致、R1 生效改变半径、静止姿态不受影响 |
| `struct3`/`struct4` | 追加骨骼不再重建 Deformer/物理；页面懒刷新只刷当前页并在切页时补刷 |
| `physlive` | 质量/摩擦力热更新不重建世界、运动学刚体被跳过 |
| `physlazy` | 结构编辑后物理世界保持待建、进物理模式才构建、撤销后接管模型对象 |
| `ikclamp` | IK 限位：奇点附近欧拉分支保持连续、顶到限位后不再抖动、native 与回退结果一致 |
| `hover` | 骨骼悬停名称牌命中与空白处清除 |
| `optim` | 组/翻转形态递归展开、附加 UV 不被当成容器、物理参数热更新、Alt 循环拾取 |
| `undobudget` | 模型快照与姿态条目各 12 步预算、互不挤占 |
| `restmove` | 进入骨骼页是否自动显示骨架；「移动时带动顶点」开/关时顶点位移与撤销还原 |
| `poseundo` | 姿态拖动压的是轻量条目（0.04 ms vs 整模型 27 ms）、撤销不换模型对象、`R` 重置可撤销、与模型编辑按顺序混排 |
| `struct` | 结构编辑走分项重建：不重传网格、不动相机、不重预热贴图 |
| `struct2` | 同一结构编辑「分项 vs 全量」耗时对比 |
| `dform` | 向量化 `SkinDeformer` 与旧逐顶点实现逐项比对 |
| `final` | 菜单/模式/分隔条/主题/关闭模型等收尾回归 |

其余场景（`core*`、`sel*`、`grid_*`、`real*`、`flag2–flag7`、`combo*`、`bgprobe`、`optc`、`dbg2` 等）是当时的取证探针，保留在 `tests/run.py` 中便于复现历史问题，不在常规回归里执行。

结果统一写入 `tests/report.json`（键 `log` / `anomalies`），截图在 `tests/shots/`。测试夹具 `tests/test_model.pmx` 由 `tests/gen_model.py` 生成；该脚本依赖 Pillow（便携运行时未安装，需用系统 Python 3.10 运行）。

像素验证有两个坑：

1. `win.grab()` 抓 `QOpenGLWidget` 可能拿到**上一帧**，比较前必须 `viewport.repaint()` 再 `pump()`。
2. 遍历列表项前先 `list.scrollTo(index)`，否则 `visualRect().center()` 可能落在详情区控件上，误报"点击被拦截"。

### 数值与工具校验

```powershell
# C++ 后端 vs NumPy 参考实现（蒙皮/层级/付与/IK/形态/物理世界，26 项）
.\build\python\python.exe tools\verify_native_backend.py "模型.pmx" --in-process --runs 3

# VPD 解析、编码、匹配、应用、导出与回读
.\build\python\python.exe tools\verify_vpd.py "模型.pmx"

# 性能基准
.\build\python\python.exe tools\bench_perf.py --help
```

### 回归清单

改完姿态/渲染/物理/界面后建议执行：

1. `.\build\python\python.exe -m compileall -q src tools tests main.py` 语法检查。
2. `.\build\python\python.exe tests\go.py inventory dark tests\test_model.pmx`：窗口正常、0 异常。
3. `.\build\python\python.exe tests\go.py verify_p0 dark tests\test_model.pmx`：颜色按钮与物理页选择不崩溃。
4. `.\build\python\python.exe tests\go.py walk dark tests\test_model.pmx`：异常应只剩已知噪声（spinbox 内部行编辑、滚动箭头、已选中的分段、被 patch 的菜单、harness 自身遍历表头的崩溃），条数随点击顺序在 20~36 之间浮动。
5. 加载真实模型：顶点/骨骼/刚体/关节数量与参考一致，贴图、描边、线框、灰模正常。
6. 姿态模式：FK 旋转、IK 拖动、付与、`R` 重置；撤销后姿态逐点还原。
7. 物理模式：进入/退出无报错，退出后姿态恢复。
8. 撤销/重做：结构编辑与字段编辑各一次。
9. 保存后重新打开：计数全等，顶点/UV 最大差为 0。
10. 真实模型（`米娅.pmx` 级别）改骨骼坐标应在 **100 ms** 以内（贴图缓存命中、结构分项重建）。
11. `tools\verify_vpd.py` 通过，并用真实 VPD 检查导入、未匹配报告、撤销与零变化拒绝导出。

## 性能

### 实测数据（真实模型：79848 顶点 / 321 骨骼 / 52 材质 / 183 刚体 / 261 关节）

| 项目 | 数值 |
| --- | --- |
| 加载 / 保存 / 回读 | 0.67 s / 0.15 s / 0.16 s（保存后字节数与源文件一致） |
| 静态重绘一帧 | 9.5 ms（约 105 FPS） |
| 物理模式 | 45.9 FPS（183 刚体 + 8 万顶点） |
| 切换页面 | 28–45 ms（首次含懒构建）；单页 `refresh()` 2–7 ms |
| 结构类编辑（追加骨骼 / 删除骨骼 / 改骨骼坐标） | 约 15 ms（旧版 580 ms；分项重建 75 ms；物理惰性+接管模型 19 ms） |
| 材质类编辑（改色/换贴图） | 约 58 ms（旧版 460 ms，其中重绘 419 ms） |
| 整模型深拷贝 / 压一次撤销栈 | 18 ms / 18 ms（快速深拷贝前为 44 ms；形态偏移 dict 列表仍是最大项） |

### 已落地的优化

- 贴图缓存键改为 `(贴图路径, 是否球面)`，`set_model` 与 `refresh_textures` 不再整体清空缓存 —— 旧版每次结构/材质编辑都会重新解码 12 张贴图（单次约 290 ms）。
- 网格与叠加层使用各自 VBO，叠加层开关不再触发整网格重建。
- 线条绘制期间临时关闭 MSAA，修复 Intel 驱动在 4x MSAA 下细线出现纯红/纯黄噪点的问题。
- HUD FPS 在空闲 1.2 s 后归零并显示"空闲"，不再残留旧值。
- **网格 VBO 复用**：网格缓冲按名字长期持有（`Viewport._buffer()`），结构重建不再每次 `glGenBuffers` 四个新缓冲；实测连续三次重建后 id 恒为 `mesh.pos/nrm/uv/idx` 四个，显存不再随编辑次数线性增长。
- **贴图后台预热**：`set_model` 后由 daemon 线程解码全部贴图到 CPU 侧像素缓存，渲染时直接上传。结构重建"`set_model` + 首帧"从 **542 ms 降到 110 ms（4.9×）**，后台解码 452 ms 完全不占 UI 线程。
- **页面刷新保留滚动位置**：`_refresh_pages()` 刷新前后保存/恢复各页滚动条位置，逐项编辑时不会被弹回顶部。
- **关窗释放 GL 资源**：`Viewport.release_gpu_resources()` 删除网格/叠加层/网格线缓冲与纹理，`closeEvent` 中与物理库一起释放。
- **字段编辑不走全量重建**：`bone`/`material`/`morph` 类编辑只 `mark_dirty()` 重绘，只有 `reload`/`structure` 才 `_reload_structure()`。
- **骨骼权重表向量化**：`SkinDeformer` 的「顶点→权重槽」展开由双重 Python 循环改为 `np.repeat` + `np.cumsum` 向量化，大模型（79848 顶点 / 10.6 万条蒙皮项）构造 **33.2 ms → 7.5 ms（4.4 倍）**，与旧实现逐项 `array_equal` 一致。
- **撤销快照快速深拷贝**：`pmx._FastCopy` 按字段类型手写复制规则（数组 `copy()`、列表逐项、嵌套 dataclass 递归），绕开通用 `deepcopy` 的 `__reduce_ex__` 协议；大模型整模型快照 **44 ms → 18 ms（2.4 倍）→ 12.8 ms**（形态偏移改为专用快路径），撤销一次结构编辑 81 → 46 → **34.8 ms**。撤销后另存文件的字节与编辑前完全一致。
- **结构重建分项**：`_reload_structure()` 先由 `Viewport.rebuild_structure()` 判断能否就地重建 —— 只增删骨骼/刚体/关节时复用网格 VBO、贴图像素缓存与相机，仅重建 Pose/Deformer/物理；顶点/索引/UV/材质区间变化才回落到完整 `set_model()`。大模型「新建骨骼」**130.7 → 75.2 ms（1.74 倍）**、撤销 **126.3 → 80.7 ms（1.57 倍）**。

### 后续优化方向

1. **姿态交互**：静态叠加层缓存、骨骼线向量化、鼠标事件合并、增量蒙皮均已落地（见上）；只有在实测仍超 20 ms/帧时才考虑 GPU 蒙皮或原生内核。
2. **结构编辑剩余开销**：一次结构编辑约 15 ms（物理世界已改惰性构建、页面已改懒刷新），大头是首帧重绘（83k 顶点 + 描边第二遍 + 4×MSAA，约 10–15 ms）与 `Pose`/`SkinDeformer` 重建；撤销约 35 ms，因为撤销后首帧同样要重绘。下一步可做物理世界增量更新，或把形态偏移换成 ndarray 以继续压缩撤销快照（当前 12.8 ms）。
3. GPU/Vulkan 渲染路线的评估结论是**暂不迁移**：当前瓶颈在 CPU 侧几何准备，先按分项计时数据推进。

## 打包与发布

使用 Nuitka 4.3.1 onefile，构建解释器取 `build\python`（纯 ASCII 路径）：

```powershell
.\build\python\python.exe -m nuitka --standalone --onefile --enable-plugin=pyqt5 `
  --windows-console-mode=disable --msvc=latest --assume-yes-for-downloads `
  --output-dir=dist\release --output-filename=PmxEditor_Modern.exe `
  --include-data-dir=assets=assets `
  --include-data-files=native/bullet_phys.dll=native/bullet_phys.dll `
  --include-data-files=src/pmxeditor/_pmx_core.cp310-win_amd64.pyd=pmxeditor/_pmx_core.cp310-win_amd64.pyd `
  --include-module=pmxeditor._pmx_core --include-module=tools.verify_native_backend `
  --include-module=OpenGL.GL --include-package=OpenGL.arrays --include-package=OpenGL.platform `
  --company-name="PmxEditor Modern" --product-name="PmxEditor Modern" `
  --file-version=1.0.0.0 --product-version=1.0.0.0 main.py
```

要点：

- 只打包实际用到的 OpenGL 子模块，`--include-package=OpenGL` 会把全部扩展塞进去。
- 数据文件映射按包内布局写：`assets` 与 `native` 落在发行根目录，`_pmx_core*.pyd` 落在 `pmxeditor/` 内（`paths.py` 的 `_locate()` 会自动找到它们）。
- 通过 PowerShell 传参时带空格的参数必须整体加引号（`'--company-name="PmxEditor Modern"'`），否则 Nuitka 报 `specify only one positional argument`。
- **onefile 每次启动都会把运行时解压到 `%TEMP%`**。若解压目录不可用（策略受限、残留被强杀进程占用的 `onefile_*`、路径异常），exe 会立即退出且不显示窗口，退出码 2。排查顺序：清理 `%TEMP%\onefile_*` → 把 `TEMP`/`TMP` 指向普通可写目录 → 用 `--onefile-tempdir-spec` 固定解压目录重建；冒烟脚本结束时按进程名清理子进程，否则解压目录会被长期占用。
- 构建产物不入库：`dist/` 是构建时生成的输出目录（已在 `.gitignore` 里），仓库不保留 exe。发布前用上面的命令重新生成，再按下列方式验收：
  - 隔离环境（`PATH` 只留 `C:\Windows\System32` 等系统目录、私有 `TEMP`）启动 → 窗口正常、模型与贴图正常、骨骼叠加正常、stderr 为空；
  - `PmxEditor_Modern.exe --verify-backend --runs 1 --out dist\be.json 模型.pmx` → 退出码 0、`ok=true`、26 项检查全过、包内 `pmxeditor\_pmx_core.pyd` 被正确加载。
- 上一次完整构建验收针对 `448af3c`（移除 VMD 与 SDEF 降级开关之前）；当前源码改动后需重新构建并复测。

发布前检查：exe 复制到无关目录可独立启动、状态栏显示 `C++ / Bullet`、模型/贴图/物理库正常、VPD 导入导出回读一致、界面无缺字错位、记录对应源码版本。

## 已知限制与技术债

| 优先级 | 问题 | 影响 | 建议 |
| --- | --- | --- | --- |
| 低 | IK 限位用欧拉角钳制 | 已用「分支滞回 + 增量钳制」消除 ±90° 处的轴跳变，但仍是欧拉逐轴语义（与 MMD 一致，刻意不改锥形约束） | 保持 |
| 决定 | SDEF/QDEF 顶点一律按 BDEF2 蒙皮 | 膝带实测：SDEF 到关节中心 0.661/0.540，相邻 BDEF2 带 0.610/0.517——SDEF 把膝盖顶出去 0.05~0.16，侧视有台阶，而 PmxEditor 的膝盖观感就是 BDEF2。视图因此不再提供降级开关，蒙皮阶段直接把 type 3 当 1；`.pmx` 里的 C/R0/R1 仍原样解析与回写，只保留求值代码作对拍基线（`go.py skin/ellipsoid/sdefr1` 直接调 `native_core.deform`） |
| 低 | 冲量/附加 UV 形态不影响视口 | 冲量需物理回放、附加 UV 是材质不采样的独立通道 | 需要时再接物理回放/自定义着色 |
| 低 | 骨骼位置编辑的顶点跟随需手动开启 | 关闭「移动时带动顶点」时只有骨骼线与关节移动（静止位置语义下 `world @ (v - rest)` 自动抵消）；开关按全局设置记忆，不区分模型 | 若确有必要可改为默认开启，或按模型记忆 |
| 低 | 物理热更新覆盖重力/迭代次数/质量/摩擦力 | 弹性与运动学刚体的质量改动仍会被忽略 | 面板补弹性入口、运动学刚体走整体重建 |
| 低 | 删除骨骼仍走完整重建 | 米娅（321 骨骼）删除骨骼约 65 ms：删骨骼会重排 `v_bones` 索引并连带重映射刚体/关节，只能整次 `set_model` | 若出现真实卡顿再评估索引压缩 |
| 低 | 亮色主题地面网格线偏深 | Intel 4x MSAA 细线光栅化导致明度偏离配色表（彩色噪点已修） | 跨驱动复测后考虑改用四边形描边 |
| 低 | 骨骼拾取仍是屏幕距离启发式 | 已改为按投影长度自适应的像素半径并加悬停名称牌，但极密集区域仍需多次 Alt+单击循环 | 改为几何射线-线段求交与命中测试 |
| 低 | 软体只读写不模拟 | PMX 2.1 软体无物理效果 | 接入 Bullet 软体或在界面标注 |
| 低 | 无显示框 / 顶点权重 UV 编辑 | 功能缺口 | 按路线图补充 |
| 低 | `viewport/core.py` 仍是单文件（约 1.9k 行） | 渲染、拾取、HUD 仍耦合在同一个类里 | 继续拆 mixin 前先把回归场景按渲染/交互分组 |
| 低 | 发行包尚未在无开发工具环境与其它 GPU 驱动上验收 | 目标机 DLL 搜索路径与 VC 运行库仍需确认 | 在目标环境执行发布检查清单 |
| 低 | `tests/` 需要交互桌面 | CI 上需虚拟显示器（如 Xvfb / 远程会话）才能跑 GUI 场景 | 增加无头模式或用 Qt offscreen 平台跑纯逻辑场景 |

## 路线图

**短期**

1. 目录重构后的首次打包与发布检查（含 `--verify-backend` 对拍）。
2. 冲量形态的物理回放与附加 UV 通道显示。
3. 跨驱动复测亮色网格与 MSAA 细线；修正网格明度。

**中期**

1. 把大模型结构编辑压到 20 ms 以内（分项重建 + 页面懒刷新已完成，当前约 21–39 ms，剩余开销在物理重建与首帧重绘）。
2. 多选与对称操作。
3. 用几何射线拾取替换屏幕距离启发式。
4. 彻底区分「跟随骨骼 / 物理演算」，并把参数热更新扩展到全部字段。

**长期**

1. 显示框编辑、顶点/权重/UV 编辑。
2. 顶点权重绘制与左右对称权重镜像。
3. 跨模型 VPD 批量验收与骨骼映射表。
4. 视需要把渲染几何准备迁到原生层（当前实测不需要）。

## 更新记录

- **2026-10-25 仓库清理与 README 复核**：删掉 `build/` 下的 Nuitka 中间件与旧构建日志（保留 `build/python` 便携运行时）、`dist/` 里三份过期发行包（r4/r5/r6 共约 1.2 GB，均已落后于当前源码）、`tests/` 的临时诊断产物（`_probe_out*.txt`、`blender*.log/npz`、`out.pmx`、`report.json`、`sync_*.vpd`、`shots/` 截图）与各处 `__pycache__`，合计约 1.38 GB；`native/obj/`（Bullet 导入库）与 `src/pmxeditor/_pmx_core*.pyd` 保留，以免下次构建退化。README 同步：功能表的发布行不再声称仓库内有与源码一致的 exe（`dist/` 改为构建时生成）、SDEF 段落改写为「蒙皮一律按 BDEF2、求值器只作对拍基线」并按现状补充 `_sdef_fallback_table()`、删除「视图 → SDEF 降级」与 `SDEF_AS_BDEF2` 的残留描述、目录树去掉 `dist/`、路线图里过时的「SDEF 半轴插值」换成权重绘制。
- **2026-10-25 移除 VMD 播放、SDEF 改按 BDEF2**：动作播放属于动画软件的职责，模型编辑器只保留静态姿态（VPD 导入导出）。删掉 `vmd.py`、`timeline.py`、底部时间轴控件、`Viewport.apply_bone_tracks()`、文件菜单的「载入动作/关闭动作」、`tools/compare_blender.py`/`blender_dump.py` 与 8 个 VMD 场景（`vmd`/`vmdreal`/`vmdprobe`/`vmdphys`/`vmdcheck`/`vmdbad`/`vmdsdef`/`knee`），`tests/run.py` 因此少约 430 行。同时把 SDEF 从「可选降级」改成「一律按 BDEF2」（`skinning._sdef_fallback_table()` 固定把 type 3 映射成 1），视图菜单里的降级开关与 QSettings `view/sdef_as_bdef2` 一并删除：半轴口径修正后 SDEF 膝带仍比 BDEF2 外推 0.05~0.16，侧视有台阶，而 PmxEditor 的膝盖观感就是 BDEF2。`.pmx` 里 SDEF 的 C/R0/R1 仍原样解析与回写，`skin`/`ellipsoid`/`sdefr1` 三个场景继续直接调用 `native_core.deform` 对拍两条求值路径。
- **2026-10-25 SDEF 半轴口径修正（膝盖突起）**：PMX 里 SDEF 的 `C/R0/R1` 存的都是"点"——模型库实测 `R0−C` 与 `R1−C` 恒为 180° 反向、`|R0|` 是骨骼长度量级（米娅 6.9、阿涵 14.6），只有逐轴 `|R−C|`（0.1~0.3）才是可信半轴。`native/pmx_core.cpp` 与 `skinning._special_blend()` 改为 `a_i = |R_i − C|`，并用**原始** R1 是否全零决定回退（C 非零时 `|0−C|` 不为零，不能看平移后的半轴）。效果：真机米娅帧 136 膝带 57 个 SDEF 顶点到关节中心 0.755/0.608 → **0.661/0.540**，与相邻 BDEF2（0.610/0.517）接上，侧视横向硬棱消失；`bdef2 vs sdef` 膝带最大差 0.209 → **0.164**。顺带让 HEAD 的「视图 → SDEF 降级为 BDEF2」开关真正生效（`skinning._sdef_fallback_table()` + `SkinDeformer.wtype_table()`，此前 deform 路径从不读这个开关）。新增 `go.py knee`（膝带权重类型、半轴口径、两种混合模式的侧视对照与数值），`ellipsoid` 增补「C 平移后半径不变」用例（该开关与 `knee` 场景已在下一条移除）。`verify_native_backend` 测试模型 26 项全过；米娅仅剩既有的 `IK rotations 0.0394` 差异（与蒙皮无关）；skin/dform/ellipsoid/sdefr1/final 场景 0 异常（`ikclamp` 的 0.2036 为既有差异，HEAD 同样复现）。
- 2026-10-25 IK 坏解重试：链上 FK 旋转仍作初值，但末端残差偏大的链会从静止姿态重解并择优选解，修正大角度动作下双腿交叉到身体另一侧的问题（`scen_ikclamp` 回归通过；VMD 播放随后已移除，该修复对 VPD 姿态同样有效）。

- **2026-10-25 VMD 动作预览（随后移除）**：新增 `vmd.py`（Vocaloid Motion Data 0002 解析、骨骼/形态轨道、线性与球面线性插值）、`timeline.py`（播放/暂停/循环/拖动定位）与 `Viewport.apply_bone_tracks()`；菜单新增「载入动作（VMD）…」「关闭动作」；载入时自动开物理演算避免物理骨骼穿插；场景 `vmd`/`vmdreal`。真实动作验收：`残虹摇摇乐.vmd` 290 帧、107 条骨骼轨道全部匹配。

- **2026-10-24 SDEF R1 椭球半轴**：SDEF 分支不再只读 `R0`——`native/pmx_core.cpp` 取 `r1 = sd + 6`，只要 `R1` 非全零就用它作为椭球半轴（全零回退 `R0`），静止方向与当前方向都用同一组半轴度量，因此静止姿态逐位还原、`R1==R0` 时与旧实现完全一致；`skinning._special_blend()` 同步（回退路径与原生差 0.000000）。新增 `go.py sdefr1`（全零回退、R1==R0 一致、R1 生效 1.5000 → 1.6641、静止 1.5000 不变）。真机米娅 326 个 SDEF 顶点在屈膝 90° 时，R1 相对「只用 R0」改变 53 个顶点、最大 0.0344；`verify_native_backend` 米娅 25 项、测试模型 26 项仍全过。
- **2026-10-24 IK 限位分支滞回 + 增量钳制**：`skinning` 新增 `euler_alt()`/`euler_distance()`/`quat_to_euler_stable()`，钳制时按上一轮角度在两组等价解里选最近的一支（消除俯仰 ±90° 的轴跳变），并记录每根受限骨骼的上一轮角度；钳制结果与上一轮完全相同时直接 `continue`（顶在限位上不再累计、不再抖动）。`native/pmx_core.cpp` 同步实现 `euler_alternative`/`euler_distance`/`quaternion_euler_stable` 与 `prev_euler`/`has_prev` 状态，重新编译 `_pmx_core`。新增 `go.py ikclamp`（奇点分支连续性、限位内不越界、native 与回退末态差 0.000000 rad）。
- **2026-10-24 形态快照快路径**：`Morph.__deepcopy__` 不再走通用 `_copy_value`，直接复制外层列表与每个偏移字典的平坦列表（保持快照隔离），整模型快照 17.9 → **12.8 ms**，撤销结构编辑 40.6 → **34.8 ms**。
- **2026-10-24 物理惰性构建 + 撤销复用分项重建**：`Viewport` 新增 `ensure_physics()`（唯一构建入口，物理模式/演算/参数热更新时按需构建）与 `adopt_model()`（网格与材质布局等价时接管撤销/重做换来的新模型对象，只重建 `Pose`/`SkinDeformer` 与缓存）；`rebuild_physics()` 改为「作废旧世界 + 置待建标记」，正在演算时才立刻重建；`app._reload_structure()` 先尝试 `adopt_model()` 再走 `rebuild_structure()`。米娅（321 骨骼 / 79848 顶点）实测：追加骨骼 60.5 → **18.9 ms**，撤销 65.7 → **40.6 ms**，载入后不再预先构建 183 刚体 + 261 关节的物理世界。新增 `go.py physlazy` 断言「结构编辑后 `physics._ready is False`、进物理模式后为 True、撤销后 `vp.model is doc.model`」。

- **2026-10-24 已知限制四项推进**：①分项重建去过度重建——`rebuild_structure()` 不再因为「骨骼数变化」就重建 `SkinDeformer` 与物理世界，改为比对静止位置前缀、`v_bones/v_weights` 身份与刚体/关节引用签名（追加骨骼 66.2 → 38.8 ms，删除骨骼仍走完整重建）；②页面懒刷新——`_refresh_pages(active_only=True)` 只刷当前页，其余记入 `_pages_dirty`，切页/选中时补刷（编辑耗时降到约 21 ms）；③骨骼拾取改为屏幕像素半径自适应（`min(16, max(6, 0.4*段长))`）+ 悬停名称牌；④物理质量/摩擦力热更新——`bullet_phys` 新增 `bw_set_body_mass/friction/restitution`，静态与运动学刚体跳过并在状态栏提示；⑤SDEF 椭球——半径改为「静止距离 x 椭球伸缩比」，静止姿态严格等于球面半径，双骨骼混合偏转时按 `R0` 各向异性伸缩（回退路径逐行对齐，`verify_native_backend` 米娅 25 项、测试模型 26 项全过）。顺带修掉 `panels/bone.py` 里残留的 `from .pmx import IK`（包拆分后会让「启用 IK」抛 `ModuleNotFoundError`）与 SDEF 权重槽重复导致 NumPy 回退少算一半权重的 bug。
- **2026-10-23 README 整合**：按当前代码逐节复核，删掉已失效的条目（「姿态没有独立撤销栈」已由轻量姿态条目解决）、修正过期数字（结构编辑 110→66–75 ms、撤销 81→46 ms、便携运行时 218→210 MB）、标明 `dist/release-20261023-r4` 是重构前的构建（该目录已在 2026-10-25 清理中删除）、补记 `gen_model.py` 依赖 Pillow 与历史探针场景的去留。
- **2026-10-23 SDEF/QDEF 精确变形**：蒙皮从「SDEF 当 BDEF2、QDEF 当 BDEF4」升级为真实现——`native/pmx_core.cpp` 的 `deform_vertices()` 增加 `sdef` 入参，SDEF 分支用两根骨骼的变换后的 C 点混合中心、沿混合方向按静止半径重新定位（`pos = c + normalize(d)*|v-C|`），QDEF 分支用双四元数混合（按首个非零权重骨骼做符号对齐，再对旋转与平移分别混合，避免关节反向扭转）；`deform`/`deform_subset` 包装与 `skinning.py` 的两个原生调用点都补上 `v_sdef`，NumPy 回退路径新增 `_special_blend()` 保持同一语义；`native/setup_core.py` 增加 `/utf-8` 并给 `pmx_core.cpp` 加 BOM（否则中文注释在 GBK 解释下会把下一行吞进注释）。真机米娅 326 个 SDEF 顶点在屈膝 90° 时与线性混合最大差 0.158、半径误差 0.0000（线性混合最大缩 0.158）；新增 `tests/go.py skin` 场景（球面半径保持、QDEF 同矩阵等价刚体、回退与原生一致），`tools/verify_native_backend.py` 仍 26 项全过。
- **2026-10-23 大文件拆分**：`panels.py`（2498 行）拆成 `panels/` 包——`base.py`（`PageBase` 与共用小工具）+ `info/bone/material/morph/physics/settings.py`，`__init__.py` 只做重导出，导入语句由脚本按 AST 实际引用裁剪生成；`viewport.py`（2194 行）拆成 `viewport/` 包——`core.py`（`Viewport`）、`camera.py`（`OrbitCamera`）、`shaders.py`（着色器源与编译）、`geom.py`（几何小工具）、`hud.py`（HUD 覆盖层）。`theme.sync_modules()` 增加包前缀匹配，让 `pmxeditor.panels.*` / `pmxeditor.viewport.*` 的颜色常量也能跟随主题；拆分后全部回归场景（含真机模型）为 0 异常。
- **2026-10-23 姿态轻量撤销**：`Document.push_pose_undo()` 只存姿态（`base_rot/base_trans` 拷贝）与形态权重，不深拷贝整个模型（大模型 27 ms → 0.04 ms）；撤销条目里 `model=None` 表示姿态条目，`undo/redo` 只回滚姿态并 `edited.emit("pose")`，不替换 `Document.model`、不触发结构重建；`R` 重置姿态与 VPD 导入也改走这条路径，因此现在都能单独撤销；新增 `tests/go.py poseundo` 场景（条目类型、撤销不换模型、重置可撤销、与模型编辑混排顺序）。
- **2026-10-23 翻转形态类型修复**：`skinning.resolve_morph_weights()` 原把翻转当成 PMX 类型 4（实际 4~7 是附加 UV1~4，翻转是 9），导致真模型的翻转形态不生效、附加 UV 形态被当容器丢弃；改为常量 `MORPH_FLIP = 9`，`tests/gen_model.py` 补了 type 9 翻转与 type 4 附加 UV 形态，`go.py optim` 增加真实文件用例。
- **2026-10-23 撤销栈分类预算**：`doc.py` 新增 `POSE_UNDO_LIMIT` 与 `_trim()`，模型快照与姿态条目分别保留 12 步（此前共用一个上限，连续拖姿态会挤掉模型快照）；`go.py undobudget` 验证 14 次模型编辑加 5 条姿态后仍为 12/5 且 17 次撤销全部成功。
- **2026-10-23 已知限制推进**：①形态预览新增组/翻转形态递归展开——`skinning.resolve_morph_weights()` 对 type 0 取 `w*ratio`、type 9（翻转）取 `(1-w)*ratio`（此前误写成 type 4，已修），深度上限 8 并用 `seen` 防自引用，未能展开的组/翻转形态直接丢弃（避免残留到生效权重里）；②物理参数热更新——`physics.set_params()` 直接调 `bw_set_gravity`/`bw_set_iterations`，保留当前姿态、不重建世界（实测 0 ms，重建需 16~20 ms）；③骨骼拾取改为候选集 + 深度排序，按住 `Alt` 单击在重叠目标间循环（HUD 提示已同步）；新增 `tests/go.py optim` 场景（合成翻转/嵌套组/自引用组、热更新前后世界对象、Alt 循环回环）。
- **2026-10-23 亮度设置**：设置页新增「亮度」卡片——背景 20%–300%、模型 20%–220%，即时生效、写入 `QSettings`（`view/bg_brightness`、`view/model_brightness`），带「恢复默认」；只影响显示，不改模型数据。背景 <100% 向黑压缩、>100% 向白插值（纯乘法在深色底上几乎看不出差别）；模型亮度是材质漫反射/环境色的倍率。背景提亮后，地面网格线与 HUD 文字会自动翻成深色（`_bg_luma()` > 0.55 判定），否则浅底上的浅线/白字看不见。首版背景滑杆无效，真因是 `paintGL` 沿用 `initializeGL`/`refresh_theme` 设过的清屏色、从不重新 `glClearColor`，已在每帧清屏前按当前亮度重设；同时把 HUD 文字与网格线的颜色改为随背景明暗自适应。
- **2026-10-23 视角操作与开关记忆**：视口操作改为通用 3D 习惯——左键拖动旋转、右键拖动平移、滚轮缩放，左键单击仍是选择（位移 ≤3 px 才判定为单击，骨骼页姿态拖动优先）；「移动时带动顶点」开关写入 `QSettings`（`editor/move_bone_vertices`），重启后保持；新增 `tests/go.py mouse` 场景（左右键拖动、空白单击、开关持久化）。同时修掉 `F`/`R` 与「视图」菜单 QAction 冲突导致的 `Ambiguous shortcut overload`（删掉重复的 QShortcut，快捷键统一由菜单 QAction 提供）。
- **2026-10-23 骨骼编辑反馈修复**：`Pose`/`SkinDeformer` 在构造时把骨骼位置等快照成数组，改动 `pos`/父级/付与/IK 后视口完全不刷新（渲染停在旧快照）——新增 `Viewport.pose_state()` 签名比对与 `ensure_pose_current()` 按需重建；`doc.undo/redo` 会整体替换 `Document.model` 而视口仍握旧对象，`_reload_structure()` 增加身份检查并回退到完整 `set_model`；撤销/重做后未清 coalesce 标记，导致紧接着的同字段编辑被吞掉且无法撤销，已修复；新增「移动时带动顶点」开关（`pmx.shift_bone_vertices()` 按权重写回 `v_pos`）与「进入骨骼页自动显示骨架」；新增 `tests/go.py rest|restmove` 场景。
- **2026-10-23 撤销快照提速**：`pmx` 的模型/骨骼/材质/形态/刚体/关节新增 `_FastCopy.__deepcopy__`，整模型快照 44 → 18 ms；新增 `tests/go.py undo|undo2` 场景（快照隔离、撤销后字节一致、逐字段耗时分布）。
- **2026-10-23 结构重建分项**：`_reload_structure()` 增加 `Viewport.structure_state()` / `rebuild_structure()` 快路径（骨骼/刚体/关节增删不再重传网格、不重设相机、不重预热贴图），`SkinDeformer` 权重展开向量化（33.2 → 7.5 ms）；新增 `tests/go.py struct|struct2|dform` 场景。
- **2026-10-23 性能收尾**：网格 VBO 改为按名复用（不再每次 `glGenBuffers` 四个新缓冲）、贴图改为后台线程预热（结构重建 `set_model` + 首帧 542 ms → 110 ms）、`_refresh_pages()` 保留滚动位置、`closeEvent` 释放全部 GL 资源；新增 `tests/go.py opt|optb` 场景；测试 harness 的命中测试在 `QApplication.widgetAt` 失效时回退到 `WIN.childAt(mapFromGlobal())`。
- **2026-10-23 主题同步修复**：`theme.sync_modules()` 原来按裸模块名（`main`/`panels`/`viewport`…）在 `sys.modules` 里查找，重构为包结构后全部查不到，导致切到亮色主题时面板变亮、而视口背景/网格/文字颜色仍停在深色。改为按末段模块名匹配（兼容 `pmxeditor.xxx` 与 `__main__`），并新增 `tests/go.py themesync` 回归场景。
- **2026-10-23 目录重构**：业务代码迁入 `src/pmxeditor` 包、全部改为相对导入；新增 `paths.py` 统一资源/原生库定位；测试脚本改为 `tests/` 与 `pmxeditor.*` 导入；新增 `build/python` 便携运行时与 `tools/make_portable_python.ps1`；删除 19 处无引用代码（约 130 行）与未使用导入；四篇文档合并进本 README。
- **2026-10-23 VPD**：新增 `vpd.py` 与 `tools/verify_vpd.py`，支持标准/旧式 VPD 的导入导出、宽松名称匹配与零变化拒绝。
- **2026-10-22 性能修复**：贴图缓存键改为 `(路径, 球面标志)`，结构编辑 580→110 ms、材质编辑 460→58 ms、编辑后首帧 419→19 ms。
- **2026-10-22 交互审计**：自动化点击测试发现并修复 16 项问题，其中两条致命——点击任意颜色按钮会让程序崩溃（RGBA 四分量写入三 uniform，`TypeError` 触发 qFatal）；物理页选中刚体/关节会无限递归直到栈溢出崩溃（`_refresh_list` 无条件把 `loading` 写回 `False`）。其余包括 Intel MSAA 细线彩色噪点、列表行宽锁死裁掉右侧信息、宽复选框只有左侧可点、点空白不取消选择、姿态单击空压撤销栈、FPS 不衰减、空列表无提示、编辑类操作无状态反馈、`F`/`R` 非全局快捷键等。

## 贡献

- 提交前请至少跑通「回归清单」中的 `inventory`、`verify_p0`、`walk` 三个场景与 `compileall`。
- 新增/修改姿态、付与、IK、蒙皮代码前，先读本 README 的「关键不变量」。
- 临时诊断脚本请放进 `tools/` 并纳入版本管理，不要留在系统临时目录。

## 许可

本项目以 **GNU General Public License v3.0** 发布，全文见 [LICENSE](LICENSE)。

你可以自由使用、修改与再分发；分发衍生作品时须同样以 GPL-3.0 授权并提供完整源码。

PMX 格式、MikuMikuDance 及相关名称归各自权利人所有；本仓库不包含 MMD 本体或其素材。
