# PmxStudio

用 **Python + PyQt5 + OpenGL + Bullet** 重写的 PMX 模型编辑器，目标是在保留 MMD 语义（付与、IK、物理、形态）的前提下，提供一个跨平台、可脚本化、可自动回归测试的 PMX 工具链。

- 纯 Python 界面与渲染，数值热点（蒙皮、层级/付与矩阵、CCD IK、形态累加、物理批处理）由可选的 pybind11 C++ 扩展加速；扩展缺失时自动回退到 NumPy 参考实现，状态栏会显示当前后端。
- 自带真实点击驱动的 GUI 自动化测试（`tests/`），可在无人工干预下遍历全部控件并输出异常清单。
- 仓库自带可移植的 Python 运行时（`build/python`），编译、打包、回归都不依赖宿主机已安装的 Python。

> 当前状态：开发版，已完成真实 PMX 模型（79848 顶点 / 321 骨骼 / 183 刚体）的加载、渲染、编辑、物理与保存往返验收；尚未在无开发工具环境的干净机器上做跨驱动复测。

## 功能概览

| 子系统 | 已支持 | 边界 |
| --- | --- | --- |
| PMX 数据 | 2.0 / 2.1 读写、统计与校验；保留编码、索引宽度与顶点权重原始字段 | 能读写不等于所有类型都能在视口中预览或编辑 |
| 主界面 | 左侧竖排导航（图标 + 名称，当前页高亮）切换十个检查器页：模型信息、骨骼、表示枠、顶点、材质、面、形态、物理、柔体、显示/主题设置；设置页含背景/模型亮度滑杆（显示用，不写入模型）；打开/保存/另存为/拖放/关闭；VPD 姿态导入导出 | 无动作/关键帧编辑，姿态只做静态预览 |
| 骨骼编辑 | 层级、名称、父级、变形层级（0–31，与 PMXEditor 一致）、位置、尾端、顺序上下移、旋转/移动付与、轴固定、IK 参数（目标/循环/单次角度 + **IK 链增删与逐轴角度限制**）；新建/复制/删除/搜索；进入骨骼页自动显示骨架；可选「移动时带动顶点」（按蒙皮权重把位移写进顶点） | 深层树紧凑缩进，长名称可能省略（悬停看完整名称） |
| 表示枠编辑 | 分组名称、特殊枠、项目顺序；加入骨骼/形态、移除、上下移动；枠本身可复制、删除、排序 | 对应 PMXEditor 的「表示枠」，只影响操作面板分组 |
| 顶点编辑 | 按索引定位顶点，改位置/法线/UV/边缩放；蒙皮权重可切 BDEF1/BDEF2/BDEF4/SDEF/QDEF 并逐槽选骨骼、填权重、改 SDEF 的 C/R0/R1；「写入模型」走撤销栈；诊断卡统计各权重类型数量、权重和不足与无主骨骼 | 一次编辑一个顶点，不提供框选与批量刷权重；顶点不参与视口拾取 |
| 材质编辑 | 漫反射/高光/环境色、纹理与球面纹理、Toon、绘制标志、描边、备注；删除时可选择「连同三角面删除」或「并入上一个材质」（保留几何） | 材质形态为近似预览 |
| 面与柔体 | 「面」页按材质查看三角面数，把源材质的一段面移到目标材质末尾（按材质顺序重建扁平索引）；「柔体」页编辑 PMX 2.1 柔体：名称、形状、材质、碰撞组、生成选项、质量/碰撞余量/气动模型、12 项求解参数、锚点与固定点，支持新建与删除 | 柔体只读写与编辑，不参与 Bullet 演算；移动面会改变材质面数，属于结构编辑（可撤销） |
| 形态 | 列表与新建/复制/删除；顶点、骨骼、UV、材质、组、翻转形态预览（组/翻转递归展开）；偏移表可选中任意一条，逐字段改目标索引与数值（材质/骨骼/形态/刚体下拉、向量分量、乘法/加法切换），并可添加/删除偏移 | 冲量、附加 UV 形态不改变视口（前者需物理回放，后者是独立 UV 通道）；添加顶点偏移默认指向 0 号顶点 |
| 姿态与 IK | FK 拖动、IK 控制器拖动、CCD IK、付与继承、蒙皮（BDEF1/2/4，SDEF/QDEF 按 BDEF2 处理）、姿态重置；VPD 导入导出；撤销/重做 | IK 限位按欧拉逐轴钳制（与 MMD 一致），近 ±90° 用分支滞回保持连续；末端残差仍偏大的链会从静止姿态重解一次，取更接近目标的解 |
| 物理 | Bullet 刚体/关节构建与实时步进，骨骼跟随与动态刚体，姿态覆盖与重置 | PMX 2.1 柔体可编辑（参数/锚点/固定点）但不参与演算；重力与迭代次数可热更新，其余参数需重建物理世界 |
| 视口 | 贴图/灰模、线框、卡通光照、描边、地面网格、骨骼/刚体/关节叠加、背景/模型亮度、拾取与 HUD | 整帧性能取决于 GPU、驱动与显示开关 |
| 编辑历史 | 模型编辑撤销/重做（12 步，0.9 s 内同键合并）；姿态拖动/`R` 重置/VPD 导入用轻量姿态条目，不占整模型快照 | 模型快照与姿态条目各有 12 步预算，互不挤占；不是无限历史 |
| 发布 | Nuitka 单文件发行包，内置 `--verify-backend` 数值对拍；构建命令见「打包与发布」，产物不入库（`dist/` 由构建生成，仓库不保留 exe） | 跨驱动（另一块 GPU）复测仍待完成 |

> **只有一个视图**：原先的「浏览 / 姿态 / 物理」三视图已合并，物理演算改成工具栏与「视图 → 物理演算」里的开关（快捷键 `P`），可以**一边演算一边摆姿**——姿态写在骨骼上，物理每步只覆盖受刚体驱动的骨骼。姿态编辑不再需要切模式，也就没有「浏览模式」了。

### 视口鼠标约定

| 操作 | 行为 |
| --- | --- |
| 左键拖动骨骼 | 位移骨骼（IK 控制器同理，拖动会带动整条链解算） |
| 右键拖动骨骼 | 旋转骨骼（绕视角的上下 / 左右轴） |
| 左键拖动空白处 | 旋转视图（位移小于 3 px 仍算单击） |
| 右键拖动空白处 | 平移视图 |
| 左键单击 / 双击 | 选择骨骼 / 刚体 / 关节（点空白处取消选择；Alt+单击在重叠目标间循环；双击给出操作提示） |
| 滚轮 | 缩放视图 |
| 中键拖动 | 兼容旧习惯：旋转视图；`Shift` + 中键拖动平移 |
| `F` / `R` / `P` | 视图居中 / 重置姿态 / 物理演算开关（全局快捷键，重置可用 Ctrl+Z 撤销） |

骨骼手柄优先于刚体与关节：只有光标附近没有骨骼线段时，显示中的刚体 / 关节才会参与拾取。物理演算开启时拖动刚体仍不施加冲量（只做选择与显示）。

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
PmxStudio/
├─ main.py                  # 启动入口：把 src 加入 sys.path 后调用 pmxeditor.app.main
├─ src/pmxeditor/           # 应用包（全部业务代码）
│  ├─ app.py                # 主窗口、菜单、工具栏、物理开关、文件操作、主题切换
│  ├─ panels/               # 右侧十个检查器页（按页面分模块）
│  │  ├─ base.py            #   PageBase 与共用小工具
│  │  ├─ info/bone/material/face/morph/physics/soft/settings/frame/vertex.py
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
│  └─ parity/               # 与原版 PmxEditor 的同操作语义比对（.cx 通道 / 总表 / 报告）
├─ build/python/            # 便携 CPython 3.10（编译与回归统一使用）
├─ requirements.txt
├─ run.bat
└─ .gitignore
```

## 架构

### 分层与依赖

```
                    src/pmxeditor/app.py（主窗口 / 工具栏 / 文件 / 主题）
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
6. 物理结果通过 `ov_rot/ov_trans` 覆盖，**关闭物理演算时**清除覆盖；开启期间姿态编辑仍然写入 `base_*`，物理只覆盖受刚体驱动的骨骼。
7. 任何姿态/形态/物理变化都要失效 `world_cache` 与 `_dirty`。
8. 界面修改模型必须走 `Document.edit` / `push_undo`，不要直接改 dataclass。
9. 改动骨骼的静止位置/父级/付与/IK 后必须让视口重建 `Pose`/`SkinDeformer`（`Viewport.ensure_pose_current()` 会按 `pose_state()` 签名自动重建）；`doc.undo/redo` 会替换 `Document.model` 对象，界面需按身份判断是否重新 `set_model`。

### 关键数据流

| 场景 | 路径 |
| --- | --- |
| 打开模型 | `app.open_path` → `_maybe_save` → `Document.load`（`pmx.load_pmx`）→ `viewport.set_model` → `_refresh_pages` |
| 面板编辑 | 控件信号 → `PageBase.edit()` → `doc.edit(kind)` → `push_undo` + 修改 + `edited.emit(kind)` → `app._on_edited`（状态栏 + 局部刷新） |
| 结构编辑 | `doc.add_*/duplicate_*/remove_*`（含索引重映射）→ `edited("structure")` → `app._reload_structure()` 重建 Pose/Deformer/网格/物理 |
| 姿态拖动 | `viewport.mousePressEvent`（左键位移 / 右键旋转）→ 增量入队 → `Pose.translate_world` / `rotate_world` → `world_update` → `SkinDeformer.deform` → VBO 更新 → 重绘（首次位移才压撤销栈） |
| 物理演算 | `viewport.set_physics(True)` → `physics.MMDPhysics.step` → 刚体结果回写 `ov_*` → 蒙皮 → 重绘（与姿态编辑互不排斥） |
| 保存 | `app.save` → `pmx.save_pmx`（按内容决定 2.0/2.1 与索引宽度）→ `doc.dirty=False` |
| VPD 导出 | `vpd.build_vpd_text`（只导出偏离初始姿态的骨骼与非零形态）→ CP932 写入 |

## 核心模块

### `pmx.py` — 数据层

`PMXModel` 持有 `v_pos/v_nrm/v_uv/v_add/v_edge/v_bones/v_weights/v_sdef/indices` 等 NumPy 数组与 `materials/bones/morphs/frames/rigid/joints/soft_bodies` 列表；`Bone`/`Material`/`Morph`/`RigidBody`/`Joint`/`SoftBody`/`IK`/`IKLink` 为 dataclass。形态偏移是 dict 列表（`vertex+offset` / `bone+move+rot` / `material+…` / `morph+ratio`）。`save_pmx` 自动决定写入 2.0 还是 2.1 以及各级索引宽度；真实模型 `米娅.pmx` 的保存往返为**字节数一致、顶点/UV 最大差 0**。

### `doc.py` — 文档与撤销

`Document` 暴露 `edited/status/selectionChanged/dirtyChanged` 信号，撤销栈上限 `UNDO_LIMIT = 12`；`push_undo` 在 0.9 s 内对同键操作做合并（coalesce）。撤销条目是 `(label, model, pose, morphs)`：**`model is None` 表示姿态条目**（只存 `Pose` 的 `base_rot/base_trans` 与形态权重，不做整模型深拷贝，约 0.04 ms vs 27 ms），`undo/redo` 见到它只回滚姿态并 `edited.emit("pose")`，不替换 `Document.model`、不触发结构重建。所有会改变索引的结构操作集中在 `add_*/duplicate_*/remove_*`（`remove_bone` 会重映射父级、尾骨、付与、IK、顶点权重、形态、刚体与显示枠；`remove_rigid` 会连带删除引用它的关节）。

### `skinning.py` — 姿态、付与、IK、蒙皮

`Pose` 保存 `base_rot/base_trans`（编辑源）与 `rot/trans`（生效值）、`eval_order`、`world_cache` 与 `_dirty`。付与继承区分 `BF_INHERIT_ROT` / `BF_INHERIT_MOV` / `BF_LOCAL_APPEND`，按 `eval_order` 求值；IK 为 CCD 实现（逐链刷新末端、世界增量左乘），并以 FK 旋转作为迭代初值；若某条链解完末端残差仍超过 `ik_retry_tolerance`（0.05 模型单位），会把这条链的骨骼旋转清零后单独重解一次，只有残差变小才采用，避免从大角度初值收敛到镜像解（实测米娅帧 136 双膝跨到身体另一侧，修复后右膝 x=-2.78/左膝 x=+2.40，与 MMD 同侧）；蒙皮支持 BDEF1/2/4，**SDEF/QDEF 顶点在蒙皮阶段一律按 BDEF2 处理**（`_sdef_fallback_table()` 把 type 3 映射成 1）：真机膝带实测 SDEF 到关节中心 0.661/0.540、相邻 BDEF2 0.610/0.517，SDEF 会把膝盖顶出 0.05~0.16、侧视有台阶，而 PmxEditor 的膝盖观感就是 BDEF2。SDEF 求值器仍完整保留在原生 `_pmx_core` 与 NumPy 回退两条路径上（语义一致），只作对拍基线——`go.py skin/ellipsoid/sdefr1` 直接调 `native_core.deform` 比对两条路径。它的半轴按逐轴 `|R − C|` 计算：PMX 里 R0/R1 存的是"点"，模型库实测 `R0−C` 与 `R1−C` 恒为 180° 反向、`|R0|` 是骨骼长度量级，直接当半径会把膝带顶点整体外推 0.15；原始 R1 全零时回退 R0，R1==R0 时与只用 R0 的实现逐位一致。`.pmx` 里的 C/R0/R1 原样解析与回写。付与（付与回転/移動）按「源骨骼相对其自身父级」的本地变换求值（与 mmd_tools 的 shadow-bone 语义一致），`膝` 这类 `append_parent == 自身父级` 的反向付与骨骼因此能正常抵消父级旋转；PMX 没有 Roll 字段，`local_x/local_z` 只保存并显示编辑用局部轴，不参与蒙皮。刚体/关节叠加层、视口拾取与「定位选中」使用当前姿态（物理演算时为模拟变换）而不是 PMX 静止坐标。

### `physics.py` — Bullet

用 ctypes 加载 `native/bullet_phys.dll`（C 包装层 `bw_*`）。刚体语义与 MMD 对齐：`跟随骨骼` 为运动学体、`物理演算` 由 Bullet 求解并回写、关节用 `btGeneric6DofSpringConstraint` 保留三轴限位与弹簧、限位 `min > max` 视为自由轴。PMX 2.1 柔体可在「柔体」页编辑，但不参与 Bullet 演算。被标记「物理后变形」(`BF_AFTER_PHYSICS`) 的骨骼不接收刚体覆盖：原生与 NumPy 两条覆盖路径都会跳过它，演算结束后该骨骼保持手工姿态。

### `viewport/` — 渲染与交互

自绘 `QOpenGLWidget`：网格按材质批次上传，绘制顺序为 地面/阴影 → 不透明 → 透明（`MF_DOUBLE_SIDED` 关闭背面剔除）→ 描边 → 叠加层 → HUD。贴图缓存键是 `(贴图路径, 是否球面)`，**编辑材质不会清空缓存**（只有 `initializeGL` 建立新上下文时才清一次）。相机为轨道相机，拾取用屏幕距离启发式（骨骼/刚体/关节，按屏幕距离与深度排序，Alt+单击循环重叠目标），HUD 空闲时显示"空闲"而不是残留 FPS。骨骼页的六个开关在视口里都有实际效果：`BF_VISIBLE` 关掉的骨骼不绘制也不参与拾取；`BF_ENABLED`（可操作）关掉后拾取直接跳过（列表仍可选中，拖动时状态栏提示“不可移动/不可旋转”）；`BF_TRANSLATABLE` 只门控左键位移、`BF_ROTATABLE` 只门控右键旋转（拖动途中改开关立即失效）；`BF_AFTER_PHYSICS`（物理后变形）让刚体不覆盖该骨骼的手工姿态；`BF_LOCAL_APPEND` 走付与链。

### `panels/` / `ui_widgets.py` / `theme.py` — 界面层

`panels/` 的十个页面都继承 `PageBase`（`base.py`）（`edit()/scroll()/select()/refresh()`）。回填数据时必须置 `self.loading = True`（并在 `finally` 里恢复原值，不要无条件写 `False`），否则信号回环会触发编辑与压栈。`ui_widgets.py` 提供自绘控件；`EntryList` 在过滤到 0 行、`BoneTree` 在无匹配时显示占位提示。`theme.py` 负责深/亮两套配色与 SVG 图标，`paths.ASSETS` 指向仓库根 `assets/`。

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

所有可记忆的状态写在仓库根目录的 `settings.json`（不进版本库），启动时自动读取、改动即时写回，不落到模型文件里：

```json
{
  "version": 1,
  "theme": "dark",
  "view": {
    "bg_brightness": 1.0,
    "model_brightness": 1.0,
    "show_grid": true, "show_bones": true, "show_rigid": false,
    "show_joints": false, "show_texture": true, "toon": true,
    "outline": true, "wireframe": false, "show_shadow": true
  },
  "physics": { "gravity": 9.8, "iterations": 10, "ground": true },
  "paths": { "last_dir": "", "last_vpd_dir": "" },
  "window": { "geometry": "<base64>", "splitter": [339, 300] },
  "editor": { "move_bone_vertices": false }
}
```

| 键 | 含义 |
| --- | --- |
| `theme` | 深色 / 亮色主题，首帧即按它构建（不再"先深色再闪一下"） |
| `view.*` | 视口显示开关与亮度（`bg_brightness` / `model_brightness`，1.0 为默认） |
| `physics.*` | 重力、迭代次数、地面开关 |
| `paths.*` | 打开模型、导入导出 VPD 时记住的目录 |
| `window.*` | 窗口位置大小（base64）与左右分栏比例 |
| `editor.move_bone_vertices` | 骨骼页「移动时带动顶点」开关 |

- 写文件是先写 `.tmp` 再 `os.replace` 的原子替换；文件损坏时会自动备份成 `settings.json.bak` 并回落到默认值（设置页「配置文件」卡片会显示错误）。
- 想恢复出厂状态：关掉程序，删掉 `settings.json`。
- 用环境变量 `PMXE_CONFIG=<路径>` 可以指定另一份配置（便携模式 / 多套环境）。
- 设置为根目录写不进去时（只读安装位置）自动退到 `%APPDATA%/PmxEditorModern/settings.json`。
- 旧版的注册表配置（`HKCU\Software\PmxEditorModern\editor`）在首次启动、且 `settings.json` 不存在时会被一次性搬迁过来；之后以文件为准，注册表不再读写。

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
| `sel` | 全量选中 + 逐行真实点击（物理页列表重建与悬空索引回归，需真实模型） |
| `flag8` | 材质绘制标志复选框的点击命中与模型写回 |
| `rows_fix` | 列表行宽随视口重算（右侧信息不被裁掉） |
| `fix2` | 点视口空白取消选择、单击骨骼不压撤销栈 |
| `fps` | HUD FPS 空闲衰减 |
| `tree2` / `empty` | 骨骼树右键菜单、空列表占位提示 |
| `sync` | VPD 导入/导出全流程（需真实模型） |
| `themesync` | 主题切换后视口/控件的颜色常量是否跟着变（深<->亮双向） |
| `theme_persist` | 切换主题后配置文件存档、分段控件、视口底色是否一起更新（再切回） |
| `opt` | 网格 VBO 复用（三次重建 id 不变）、页面刷新保留滚动、贴图预热产出、关闭时释放 GL 资源 |
| `optb` | 量化贴图预热收益（有/无预热的 `set_model` + 首帧耗时） |
| `undo` | 快照快速深拷贝提速、快照与在线模型隔离、撤销后另存字节一致 |
| `undo2` | `deepcopy` 各字段耗时分布 |
| `rest` | 改骨骼位置/尾端/父级后 Pose 与蒙皮静止位置是否跟着重建、撤销是否复原 |
| `vp` | 视口拾取、左键选择、中键/右键拖动、F/R 快捷键、姿态拖动、物理刚体拾取（拖动类交互直接投递 QMouseEvent，因为 `QTest.mouseMove` 走光标路径、在本环境到不了控件） |
| `bright` | 设置页亮度滑杆传到视口（背景清屏色、模型漫反射倍率）、写入配置文件、恢复默认、视口像素确实变化、背景提亮后网格与 HUD 翻深色 |
| `mouse` | 左键拖动旋转/右键拖动平移/空白单击取消选择；「移动时带动顶点」开关不写配置文件、新实例默认关闭 |
| `config` | 配置文件：不存在时新建、写入即落盘、重载、手工写成字符串时的类型纠正、损坏时备份并回落默认、主题切换同时写内存与磁盘 |
| `skin` | SDEF 球面半径保持、QDEF 同矩阵等价刚体、NumPy 回退与原生一致（合成夹具） |
| `frame` | 表示枠增删改与项目排序、IK 链增删、角度限制写入与往返读写 |
| `morph_edit` | 形态偏移的目标/数值编辑、添加与删除、材质乘法/加法切换、往返读写 |
| `vertex_edit` | 顶点索引定位、位置/UV 写回、权重类型切换与落盘往返 |
| `ellipsoid` | SDEF 椭球：半轴取逐轴 \|R−C\|（PMX 里 R0/R1 存的是点）、静止回到球面半径、双骨骼混合时按 R0 各向异性伸缩、回退与原生一致 |
| `sdefr1` | SDEF 的 R1：原始值全零才回退 R0（C 非零时不能看 \|R1−C\|）、R1==R0 与旧实现一致、R1 生效改变半径、静止姿态不受影响 |
| `struct3`/`struct4` | 追加骨骼不再重建 Deformer/物理；页面懒刷新只刷当前页并在切页时补刷 |
| `physlive` | 质量/摩擦力热更新不重建世界、运动学刚体被跳过 |
| `physlazy` | 结构编辑后物理世界保持待建、开启物理演算才构建、撤销后接管模型对象 |
| `ikclamp` | IK 限位：奇点附近欧拉分支保持连续、顶到限位后不再抖动、native 与回退结果一致 |
| `hover` | 骨骼悬停名称牌命中与空白处清除 |
| `optim` | 组/翻转形态递归展开、附加 UV 不被当成容器、物理参数热更新、Alt 循环拾取 |
| `undobudget` | 模型快照与姿态条目各 12 步预算、互不挤占 |
| `restmove` | 进入骨骼页是否自动显示骨架；「移动时带动顶点」开/关时顶点位移与撤销还原 |
| `flagguard` | 骨骼页六个开关：不可操作=不可拾取/不可拖动、可移动管左键位移、可旋转管右键旋转、显示=关不拾取、物理后变形=刚体不覆盖手工姿态（合成模型 + Bullet 夹具） |
| `poseundo` | 姿态拖动压的是轻量条目（0.04 ms vs 整模型 27 ms）、撤销不换模型对象、`R` 重置可撤销、与模型编辑按顺序混排 |
| `struct` | 结构编辑走分项重建：不重传网格、不动相机、不重预热贴图 |
| `struct2` | 同一结构编辑「分项 vs 全量」耗时对比 |
| `dform` | 向量化 `SkinDeformer` 与旧逐顶点实现逐项比对 |
| `final` | 菜单/物理开关/分隔条/主题/关闭模型等收尾回归 |

`skin` / `ellipsoid` / `sdefr1` 直接调用 `native_core.deform` 对拍求值器；视口蒙皮按「SDEF/QDEF 一律当 BDEF2」处理（见「已知限制」）。

其余场景（`core*`、`sel*`、`grid_*`、`real*`、`flag2–flag7`、`combo*`、`bgprobe`、`optc`、`dbg2` 等）是当时的取证探针，保留在 `tests/run.py` 中便于复现历史问题，不在常规回归里执行。

结果统一写入 `tests/report.json`（键 `log` / `anomalies`），截图在 `tests/shots/`。测试夹具 `tests/test_model.pmx` 由 `tests/gen_model.py` 生成；该脚本依赖 Pillow（便携运行时未安装，需用系统 Python 3.10 运行）。

像素验证有两个坑：

1. `win.grab()` 抓 `QOpenGLWidget` 可能拿到**上一帧**，比较前必须 `viewport.repaint()` 再 `pump()`。
2. 遍历列表项前先 `list.scrollTo(index)`，否则 `visualRect().center()` 可能落在详情区控件上，误报"点击被拦截"。

### 与原版 PmxEditor 的同操作比对（`tests/parity/`）

同一项操作在原版与新版本里各做一遍并另存，再用 `pmxsem` 按 1e-5 容差逐字段比对。GUI 无法编辑或原版无入口的字段走原版自带 CSScript（`.cx`）通道写入，落盘仍由 PmxEditor 完成。

```powershell
# 汇总总表（当前 42 项：34 一致 / 7 差异 / 1 单侧）
.\build\python\python.exe tests\parity\compare_all.py

# 跑一组功能场景并收集异常
.\build\python\python.exe tests\parity\regress.py sel sel2 click_rigid
```

原版侧执行器 `side_orig.py` / `cxop.py` 依赖 pywin32 与原版编辑器窗口，需用系统 Python；新版侧 `side_mod.py` 用仓库便携运行时。字段级结果见 `tests/parity/compare_all.md`，方法、差异根因与修复记录见 `tests/parity/REPORT.md`。

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
6. 姿态编辑：左键拖动位移、右键拖动旋转、IK 控制器拖动、付与、`R` 重置；撤销后姿态逐点还原。骨骼页关掉“可操作/可移动/可旋转/显示”后对应操作确实失效（`go.py flagguard`）。
7. 物理演算：开关切换无报错，关闭后姿态恢复；开启时仍能拖动骨骼（被刚体驱动的骨骼会被物理覆盖）。
8. 撤销/重做：结构编辑与字段编辑各一次。
9. 保存后重新打开：计数全等，顶点/UV 最大差为 0。
10. 真实模型（`米娅.pmx` 级别）改骨骼坐标应在 **100 ms** 以内（贴图缓存命中、结构分项重建）。
11. `tools\verify_vpd.py` 通过，并用真实 VPD 检查导入、未匹配报告、撤销与零变化拒绝导出。
12. 有原版 PmxEditor 环境时跑 `tests\parity\compare_all.py`，确认总表没有新增差异（当前 42 项 / 34 一致）。

## 性能

### 实测数据（真实模型：79848 顶点 / 321 骨骼 / 52 材质 / 183 刚体 / 261 关节）

| 项目 | 数值 |
| --- | --- |
| 加载 / 保存 / 回读 | 0.67 s / 0.15 s / 0.16 s（保存后字节数与源文件一致） |
| 静态重绘一帧 | 9.5 ms（约 105 FPS） |
| 物理演算 | 45.9 FPS（183 刚体 + 8 万顶点） |
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
$env:PYTHONPATH = "$PWD\src"   # 让 Nuitka 找到 src 下的 pmxeditor 包，否则报 failed to locate module 'pmxeditor._pmx_core'
.\build\python\python.exe -m nuitka --standalone --onefile --enable-plugin=pyqt5 `
  --windows-console-mode=disable --msvc=latest --assume-yes-for-downloads `
  --output-dir=dist\release --output-filename=PmxStudio.exe `
  --include-data-dir=assets=assets `
  --include-data-files=native/bullet_phys.dll=native/bullet_phys.dll `
  --include-data-files=src/pmxeditor/_pmx_core.cp310-win_amd64.pyd=pmxeditor/_pmx_core.cp310-win_amd64.pyd `
  --include-module=pmxeditor._pmx_core --include-module=tools.verify_native_backend `
  --include-module=OpenGL.GL --include-package=OpenGL.arrays --include-package=OpenGL.platform `
  --company-name="PmxStudio" --product-name="PmxStudio" `
  --file-version=1.0.0.0 --product-version=1.0.0.0 main.py
```

要点：

- 只打包实际用到的 OpenGL 子模块，`--include-package=OpenGL` 会把全部扩展塞进去。
- 数据文件映射按包内布局写：`assets` 与 `native` 落在发行根目录，`_pmx_core*.pyd` 落在 `pmxeditor/` 内（`paths.py` 的 `_locate()` 会自动找到它们）。
- 通过 PowerShell 传参时带空格的参数必须整体加引号（如 `'--company-name="My App Name"'`），否则 Nuitka 报 `specify only one positional argument`。
- **onefile 每次启动都会把运行时解压到 `%TEMP%`**。若解压目录不可用（策略受限、残留被强杀进程占用的 `onefile_*`、路径异常），exe 会立即退出且不显示窗口，退出码 2。排查顺序：清理 `%TEMP%\onefile_*` → 把 `TEMP`/`TMP` 指向普通可写目录 → 用 `--onefile-tempdir-spec` 固定解压目录重建；冒烟脚本结束时按进程名清理子进程，否则解压目录会被长期占用。
- 构建产物不入库：`dist/` 是构建时生成的输出目录（已在 `.gitignore` 里），仓库不保留 exe。发布前用上面的命令重新生成，再按下列方式验收：
  - 隔离环境（`PATH` 只留 `C:\Windows\System32` 等系统目录、私有 `TEMP`）启动 → 窗口正常、模型与贴图正常、骨骼叠加正常、stderr 为空；
  - `PmxStudio.exe --verify-backend --runs 1 --out dist\be.json 模型.pmx` → 退出码 0、`ok=true`、26 项检查全过、包内 `pmxeditor\_pmx_core.pyd` 被正确加载。
- 上一次完整构建验收针对 `448af3c`（移除 VMD 与 SDEF 降级开关之前）；当前源码改动后需重新构建并复测。

发布前检查：exe 复制到无关目录可独立启动、状态栏显示 `C++ / Bullet`、模型/贴图/物理库正常、VPD 导入导出回读一致、界面无缺字错位、记录对应源码版本。

## 已知限制与技术债

| 优先级 | 问题 | 影响 | 建议 |
| --- | --- | --- | --- |
| 低 | IK 限位用欧拉角钳制 | 已用「分支滞回 + 增量钳制」消除 ±90° 处的轴跳变，但仍是欧拉逐轴语义（与 MMD 一致，刻意不改锥形约束） | 保持 |
| 决定 | SDEF/QDEF 顶点一律按 BDEF2 蒙皮 | 膝带实测：SDEF 到关节中心 0.661/0.540，相邻 BDEF2 带 0.610/0.517——SDEF 把膝盖顶出去 0.05~0.16，侧视有台阶，而 PmxEditor 的膝盖观感就是 BDEF2。视图因此不再提供降级开关，蒙皮阶段直接把 type 3 当 1；`.pmx` 里的 C/R0/R1 仍原样解析与回写，只保留求值代码作对拍基线（`go.py skin/ellipsoid/sdefr1` 直接调 `native_core.deform`） |
| 低 | 冲量/附加 UV 形态不影响视口 | 冲量需物理回放、附加 UV 是材质不采样的独立通道 | 需要时再接物理回放/自定义着色 |
| 低 | 骨骼位置编辑的顶点跟随需手动开启 | 关闭「移动时带动顶点」时只有骨骼线与关节移动（静止位置语义下 `world @ (v - rest)` 自动抵消）；开关不持久化，每次启动默认关闭 | 保持默认关闭（原版移动骨骼不搬顶点）；确有需要时手动开启 |
| 低 | 物理热更新覆盖重力/迭代次数/质量/摩擦力 | 弹性与运动学刚体的质量改动仍会被忽略 | 面板补弹性入口、运动学刚体走整体重建 |
| 低 | 删除骨骼仍走完整重建 | 米娅（321 骨骼）删除骨骼约 65 ms：删骨骼会重排 `v_bones` 索引并连带重映射刚体/关节，只能整次 `set_model` | 若出现真实卡顿再评估索引压缩 |
| 低 | 亮色主题地面网格线偏深 | Intel 4x MSAA 细线光栅化导致明度偏离配色表（彩色噪点已修） | 跨驱动复测后考虑改用四边形描边 |
| 低 | 骨骼拾取仍是屏幕距离启发式 | 已改为按投影长度自适应的像素半径并加悬停名称牌，但极密集区域仍需多次 Alt+单击循环 | 改为几何射线-线段求交与命中测试 |
| 低 | 软体只读写不模拟 | PMX 2.1 软体无物理效果 | 接入 Bullet 软体或在界面标注 |
| 低 | 无多选 / 对称编辑 / 权重绘制 | 批量操作与权重刷取仍缺 | 按路线图补充 |
| 低 | `viewport/core.py` 仍是单文件（约 2.2k 行） | 渲染、拾取、HUD 仍耦合在同一个类里 | 继续拆 mixin 前先把回归场景按渲染/交互分组 |
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

1. 顶点权重绘制与左右对称权重镜像。
2. 跨模型 VPD 批量验收与骨骼映射表。
3. 视需要把渲染几何准备迁到原生层（当前实测不需要）。

## 更新记录

- **2026-10-25 修复膝部鼓包（付与参考系）与物理叠加层跟随**：膝部鼓包的根因不在 Roll/坐标系，而在「非ローカル付与」取了**目标骨骼父级**的世界旋转。`膝` 这类骨骼的 `append_parent` 就是自己的父级，这样算出的相对旋转恒为单位阵，反向付与率 −0.75 完全失效（小腿弯 60° 时 `膝` 也转 60°，正确值应为 15°），膝周大片权重给到 `膝` 的顶点因此被过度拧转。改为按源骨骼**自身父级**求本地旋转（与 Blender `mmd_tools` 的 shadow-bone 语义一致），Python 与 `native/pmx_core.cpp` 同步修改并重建原生后端；新增回归场景 `append`（60° 弯曲时 `膝` 世界角 = 15.00°，native/NumPy 差 0）。另外，刚体/关节叠加层、视口拾取与「定位选中」现在使用**当前姿态/物理变换**而不是 PMX 静止坐标，整体移动或摆姿后标记不再留在原地；`bone = -1` 的无骨骼刚体（本模型的 8 个胸部物理体及其关节）按「子树最大的根骨骼」的整体增量跟随，不会掉队。
- **2026-10-25 补齐「面」与「柔体」两个检查器页**：原版 PmxEditor 有「面」页（按材质把三角面重新分配）和 SoftBody 编辑，新版此前只能读写、不能编辑，属平铺比对里的两项能力差异（FA1/SB2）。新增 `panels/face.py`：材质列表显示三角面数，选源材质 / 起始面 / 数量 / 目标材质后「移动这些面」，`doc.reassign_faces()` 按材质顺序切分并重建扁平 `indices`，走结构编辑撤销栈；新增 `panels/soft.py`：柔体列表 + 新建/删除，编辑名称、形状、材质、所属组、16 位碰撞组、生成选项、质量/碰撞余量/气动模型、config/cluster/iteration/material_params 全部参数，以及锚点与固定点的增删。`PAGES` 增至 10 页（`RAIL_ORDER` 把「面」放在材质后、「柔体」放在物理后），`theme.make_icon` 新增两枚图标。比对复核：`FA1_cx` vs `FA1_mod`、`SB2_cx` vs `SB2_mod` 均 **0 差异**，总表变为 **42 项 = 36 一致 / 5 差异 / 1 单侧**；新增回归场景 `face_edit` / `softbody_edit`，`regress.py` 复核 anomalies=0。
- **2026-10-25 同操作比对补完 ② 剩余三项**：新增面页材质重分配（FA1）、复制骨骼/材质（N3/N4）、PMX 2.1 柔体（SB1/SB2）共 5 条比对，总表 42 项 = 34 一致 / 7 差异 / 1 单侧（其中 FA1/SB2 的两项能力差异已由上一行补齐）。原版侧经 CSScript（`.cx`）定义语义，新增 `op_FA1/op_N3/op_N4/op_SB0/op_SB2` 样例与 `PARITY_MODEL/SUF` 支持；`SB0_cx.pmx` 由原版追加 1 个柔体后另存，作为 SB1/SB2 基座。副产物：`duplicate_material` 只复制 `face_count` 不复制面索引（材质面数之和大于索引总数），已修为连面一起复制，N4 两侧 0 差异。
- **2026-10-25 修复 `sel` 场景崩溃（0xC0000005）**：根因是物理页 `select()` 每次选中都重建列表，点击行时 `QStandardItemModel.clear()` 发生在 `selectionChanged` 槽里，场景持有的 `QModelIndex` 变成悬空指针。现在 `PhysicsPage` 记录 `_list_kind`，只在刚体/关节类型变化时重建；`scen_sel` 改为点击前取行文本，`scen_sel6` 改用 `sel_kind/sel_index`。`sel` 复跑 0 异常、42.7s，相关 sel/click_rigid/verify_p0 场景均通过。
- **2026-10-25 左侧导航带上名称**：导航栏原来只有图标，八个页面里「表示枠」和「顶点」共用同一个网格图标，新加的页面也容易认错。现在左侧栏加宽成 118 px 的竖排列表，每项是「图标 + 名称」、选中项用强调色高亮，图标重画了两枚——「表示枠」是带分栏的方框、「顶点」是带顶点的三角面，与列表里的文字一一对应；其余六枚沿用原图标。`PAGES` 表的第二列因此改为 `frame` / `vertex`，`theme.make_icon` 增加对应两种形状，主题切换时图标与文字一起重新着色。
- **2026-10-25 设置改用配置文件**：亮色主题仍然存不住，根因是设置的生命周期散在 `QSettings` 与各处刷新里（写注册表时机、注册表被系统/清理工具重置、`_set_theme` 早退等），排查成本高且无法被版本库/用户直接审视。现在所有设置集中到仓库根目录的 `settings.json`（`src/pmxeditor/config.py`），启动时用 `Config.load()` 一次读入并驱动窗口构建，改动即时写回，写入走 `*.tmp` + `os.replace` 原子替换；文件损坏时自动备份 `settings.json.bak` 并回落默认值（设置页「配置文件」卡片显示路径与错误）。支持 `PMXE_CONFIG` 环境变量指定另一份配置，根目录不可写时退到 `%APPDATA%/PmxEditorModern/settings.json`；首次启动且文件不存在时，把旧注册表里的主题、目录、亮度、窗口几何一次性搬迁过来，之后不再读注册表。设置页新增「配置文件」卡片（打开所在文件夹 / 重新载入文件），`_set_theme`、`_set_brightness`、`_toggle_display`、`_apply_physics`、`closeEvent` 统一写 `Config`，`_reload_settings()` 重新载入后同步主题与显示开关。`.gitignore` 忽略三份配置文件。新增回归场景 `config`（新建/落盘/重载/类型纠正/损坏恢复/主题双写），`main_start()` 在场景前后快照并还原设置，避免测试污染真实偏好；`theme_persist`、`bright`、`mouse` 同步改读配置文件。真机双进程验证：点「亮色」后关闭，重启首帧即亮色（`current=light seg=light stored=light`），不再出现「先深色再闪一下」。
- **2026-10-25 主题保存加固**：`_set_theme` 过去把「写 QSettings」放在刷新链路的最后，图标重建 / 视口底色刷新一旦抛异常（个别显卡与 GL 驱动上会遇到），主题就没落盘，表现为「下次启动主题又变回去了」。现在先 `setValue` + `sync()` 落盘，再做配色、图标、样式表与视口刷新，刷新步骤各自 `try/except` 不阻断；切到当前主题时也会同步一次存档与分段控件，避免状态漂移。`main()` 的启动恢复改成「目标主题 vs 当前主题」比较（亮色/深色同一条路径），**并且恢复动作放在 `show()` 之前**——存档为亮色时以前是窗口先可见再切主题，肉眼看到的就是「启动先是深色、随后闪一下变白」；`closeEvent` 写几何、分隔条与**当前生效主题**后 `sync()`，保证存档不会停留在上一个主题。新增回归场景 `theme_persist`：切换后存档、控件、视口底色三处必须一起变，再切回原主题。

- **2026-10-25 对齐 PMXEditor 的五处小差异**：① 删除材质时可选择「并入上一个材质」——只把面计数归给上一个材质、`indices` 不动（`remove_material(..., merge=True)`），几何得以保留；② 变形层级范围收紧到 0–31；③ 骨骼列表支持上移/下移（`doc.move_bone` 交换列表项并重映射父骨、尾端骨、付与父、IK 目标与链接、顶点权重、形态骨骼偏移、刚体与表示枠引用）；④ 新建骨骼落在父骨尾端（尾端骨或 `tail_offset`，退化时朝上 1.0），不再写死 `+1.0`；⑤ 顶点页/材质页与骨骼顺序联动的引用都会跟着重映射。新增回归场景 `small_fixes`，`struct3`/`struct4`/`undo`/`skin`/`final`/`vp`/`view`/`menu` 均 0 异常。**尚未实现**：PMX 2.1 的「外部親」——需要在解析层增加外部親表并在求值器里解析跨模型父级，属于独立特性，留待后续。

- **2026-10-25 顶点页**：新增右侧「顶点」页（`panels/vertex.py`），可按索引定位并编辑位置、法线、UV、边缩放；蒙皮部分可切换权重类型（BDEF1/BDEF2/BDEF4/SDEF/QDEF），逐槽选择骨骼与权重，SDEF 额外给出中心 C 与 R0/R1；「写入模型」经 `Document.edit` 写入（可撤销），「诊断」用 NumPy 汇总各权重类型数量、权重和不足与无主骨骼。导航顺序变为信息/骨骼/表示枠/顶点/材质/形态/物理/设置（`RAIL_ORDER = (0, 1, 6, 7, 2, 3, 4, 5)`）。新增回归场景 `vertex_edit`（含往返读写），在测试模型与米娅.pmx 上均 0 异常。

- **2026-10-25 形态偏移可编辑**：形态页的「偏移数据」从只读表格变成可选中编辑：选中任意一条偏移后，下方按形态类型生成字段（组/翻转：目标形态 + 比例；顶点：顶点索引 + XYZ；骨骼：骨骼 + 移动 + 旋转四元数；UV：顶点索引 + 四分量；材质：材质/全部、乘法或加法、漫反射/高光/环境/描边色/描边大小/纹理/球面/Toon 各分量；冲量：刚体 + 局部开关 + 速度/扭矩），下拉与数值都直接写回模型（可撤销，数值框在失焦或回车后提交，避免拖动时反复压栈），另有「添加偏移」「删除偏移」两个按钮。新增回归场景 `morph_edit`，在 `tests/test_model.pmx` 与米娅.pmx 上均 0 异常。

- **2026-10-25 表示枠页与 IK 链编辑**：新增右侧「表示枠」页（`panels/frame.py`），支持新建/复制/删除/排序分组，把骨骼或形态加进分组、移除、上下移动，分组名/英文名/特殊枠可改；`doc.py` 增加 `add_frame`/`duplicate_frame`/`remove_frame`/`move_frame`/`frame_add_item`/`frame_remove_item`/`frame_move_item`。骨骼页的 IK 链从一行只读文字升级为可编辑列表：「添加链接」「移除」按钮，以及每根链接的「角度限制」开关和 XYZ 最小/最大角（UI 用度，模型里存弧度，与 PMX 一致）。新页追加在 `PAGES` 末尾以保持既有页索引不变，导航顺序由 `RAIL_ORDER` 决定（信息/骨骼/表示枠/材质/形态/物理/设置）。新增回归场景 `frame`（含 `.pmx` 往返读写），`vp`/`view`/`menu`/`skin`/`poseundo`/`undo`/`struct3`/`struct4`/`final` 均 0 异常。

- **2026-10-25 骨骼页六个开关在视口里真正生效**：此前只有“显示”被画笔与拾取读取，“可操作/可移动/可旋转/物理后变形”在视口里都是空转（用户报告：未开“可移动”的骨骼照样能拖）。`viewport/core.py` 的 `_pick_candidates()` 改为同时要求 `BF_VISIBLE` 与 `BF_ENABLED`；新增 `bone_drag_block(index, mode)`（“不可操作/不可移动/不可旋转”）并由 `_begin_bone_drag()` 与 `_flush_pose_updates()` 双重把关，被挡时状态栏提示、光标保持箭头；`physics.py` 的两条覆盖路径都跳过 `BF_AFTER_PHYSICS` 的骨骼（“物理后变形”= 物理算完再用手工姿态）。新增 `go.py flagguard` 覆盖六个开关（含 Bullet 夹具验证物理后变形）；没有引入 `Pose.refresh_flags()` 之类的死代码——`pose_state()` 已包含 `b.flags`，改标志会重建 Pose。
- **2026-10-25 合并三视图、物理改为开关、位移/旋转解耦**：删掉「浏览 / 姿态 / 物理」三选一——`Viewport` 去掉 `mode` 字段与 `set_mode()`，只保留 `set_physics(bool)`；工具栏在原 Segmented 的位置放一个 `Switch`（「物理演算」），「视图」菜单同一开关（快捷键 `P`），两者按 `physics.enabled` 双向同步。姿态编辑不再受模式门控：左键拖动骨骼 = 位移、右键拖动骨骼 = 旋转（空白处仍是左拖动视角 / 右拖平移 / 中键旋转 / Shift+中键平移），双击骨骼给出「左键位移 · 右键旋转」提示；IK 控制器被拖动时解算仍会带动整条链。物理与姿态可以同时生效，受刚体驱动的骨骼每步被 `ov_*` 覆盖，其余骨骼保持手摆结果；为让「一边演算一边摆姿」看得见，开启演算时自动打开骨骼/刚体/关节叠加。`_pick_candidates()` 改为骨骼优先、刚体/关节仅在光标附近没有骨骼线段时兜底（`show_rigid`/`show_joints` 打开才参与）；`Viewport` 删除 `self.mode = "browse"` 与 set_model/clear_model 里的模式复位。撤销标签拆成「移动骨骼」「旋转骨骼」，`app.POSE_EDIT_LABELS` 保证它们仍走轻量姿态条目（不克隆整模型）；VPD 导入前若在演算则先停演算，`_reload_structure()` 按 `physics.enabled` 恢复。HUD 徽标改为「摆姿 / 物理演算」，`F/R/P` 快捷键与设置页快捷键表同步。
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
