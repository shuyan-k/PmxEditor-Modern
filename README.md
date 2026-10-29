<p align="center">
  <img src="assets/icon.png" width="128" height="128" alt="PmxStudio 图标">
</p>

<h1 align="center">PmxStudio</h1>

<p align="center">
  <a href="https://github.com/shuyan-k/PmxStudio/actions/workflows/build.yml"><img src="https://github.com/shuyan-k/PmxStudio/actions/workflows/build.yml/badge.svg?branch=main" alt="build"></a>
</p>

PMX（MikuMikuDance 模型格式）查看与编辑工具的原生 C++ 实现：C++20 + GLFW 3.4 + Dear ImGui + OpenGL 4.6 + Bullet 3.25。不依赖 Python / PyQt5，Windows 下产物为单文件 exe。第三方源码全部随仓库提供，克隆后**断网也能构建**。

Python 版（PyQt5 + OpenGL）独立维护在 [`python` 分支](https://github.com/shuyan-k/PmxStudio/tree/python)。

## 功能

- **数据**：PMX 2.0 / 2.1 读写，保留编码、索引宽度与全部字段；结构校验与统计。
- **渲染**：GPU Compute Shader 蒙皮（BDEF1/2/4、SDEF）、材质 / 球面贴图 / Toon、模板缓冲描边、地面网格、骨骼 / 刚体 / 关节叠加层与拾取。
- **姿态**：FK、付与继承、CCD IK 与逐轴限位、骨骼拖动；VPD 导入 / 导出。
- **动作**：VMD 导入与播放（30 fps 时间轴、逐轴贝塞尔缓动、形态轨道）、循环 / 变速 / 拖帧，单帧导出 VMD。
- **形态**：顶点 / UV / 材质 / 骨骼 / 组 / 翻转 / 刚体偏移，滑杆预览。
- **物理**：Bullet 刚体、6DOF 弹簧关节与柔体（`btSoftBody`），固定 1/120 步进、每帧最多 10 个子步，可边演算边摆姿。
- **编辑**：编辑模式十个检查器面板（信息 / 骨骼 / 表示枠 / 顶点 / 材质 / 面 / 形态 / 物理 / 柔体 / 设置），结构增删与索引重映射，撤销 / 重做，主题与偏好持久化；退出时有未保存修改会先弹确认框。

## 快速开始

需要 CMake ≥ 3.20 与支持 C++20 的编译器。

### Windows

安装 Visual Studio 2019/2022（勾选「使用 C++ 的桌面开发」）与 CMake：

```powershell
build.bat
pmxstudio.exe tests\test_model.pmx
build\Release\pmx_tests.exe
```

`pmxstudio.exe` 直接生成在仓库根目录，构建完即可双击运行；测试程序仍在 `build\Release\`。默认使用 MSVC 静态 CRT（`/MT`），`pmxstudio.exe` 可单文件分发；以 GUI 子系统链接，启动不弹控制台窗口。

### Linux

Debian / Ubuntu 系可一键安装依赖、编译并自测：

```bash
bash setup_linux.sh
./build/pmxstudio tests/test_model.pmx
```

或手动构建：

```bash
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build -j"$(nproc)"
./build/pmx_tests
./build/pmxstudio tests/test_model.pmx
```

需要 `build-essential cmake ninja-build libx11-dev libxrandr-dev libxinerama-dev libxcursor-dev libxi-dev`；中文界面另需 Noto CJK 或文泉驿字体（`fonts-noto-cjk`）。查看器依赖 X11 显示服务，纯 SSH 环境只能构建并运行无窗口测试。

## 操作

| 操作 | 行为 |
| --- | --- |
| 「文件」菜单 / 工具栏「打开 PMX…」 | 资源管理器文件对话框选择模型；VPD / VMD 导入（仅预览模式）、VPD / VMD 导出与「导出全部骨骼」（仅编辑模式）在「文件」菜单 |
| 拖放 `.pmx` / `.vpd` / `.vmd` 到窗口 | 同上，可直接替换当前模型 / 姿态 / 动作；VPD / VMD 需在预览模式下拖入 |
| 左键**双击**骨骼 / 刚体 / 关节 | 选中，并自动切到「骨骼」/「物理」面板、把列表滚到对应行（空白处双击取消）；叠加层整体隐藏时，只临时显示并高亮选中的这一项 |
| 双击落点有多个重叠对象 | 在鼠标旁弹出候选框列出全部可选项，点选后提交（`Esc` 或点击空白处取消） |
| 左键拖动已选中的骨骼 | 预览模式下世界空间位移；拖 IK 控制器会带动整条链解算 |
| 右键拖动已选中的骨骼 | 预览模式下绕相机轴旋转；骨骼原点（head）保持不动，只改变末端朝向 |
| 左键拖动空白处 | 旋转视角 |
| 右键拖动空白处 / `Shift` + 中键 | 平移视角 |
| 中键拖动 | 旋转视角 |
| 滚轮 | 缩放 |
| `F` / `R` / `P` | 相机居中 / 重置姿态 / 开关物理演算 |
| `Ctrl+M` | 切换编辑 / 预览模式 |
| `Ctrl+O` | 打开 PMX |
| `Ctrl+S` / `Ctrl+Shift+S` | 保存 / 另存为（仅编辑模式） |
| `Ctrl+Z` / `Ctrl+Shift+Z` / `Ctrl+Y` | 撤销 / 重做（预览模式只撤销摆姿条目） |
| 窗口关闭按钮 / `Alt+F4` / 菜单「退出」 | 模型有未保存修改时先弹确认框：保存并退出 / 不保存退出 / 取消 |

未选中骨骼时拖动只改变视角，状态栏会提示先双击选中；编辑模式不响应骨骼拖动，摆姿请切到预览模式。

### 编辑 / 预览模式

标题栏左侧的「编辑 | 预览」按钮（或 `Ctrl+M`）切换当前视图模式，参考 PmxEditor 的编辑 / 预览分工：

- **编辑模式**：完整检查器（信息 / 骨骼 / 表示枠 / 顶点 / 材质 / 面 / 形态 / 物理 / 柔体 / 设置），可修改模型、撤销重做与保存；视图只显示模型原始姿态——不叠加 VMD 动作、不跑 IK 求解、不演算物理，VPD / VMD 导入入口在菜单里置灰（拖入会提示先切到预览模式）。
- **预览模式**：相当于 PmxEditor 的 TransformView——右键旋转、左键位移都只影响当前姿态，不落盘。检查器只剩「动作 / 物理 / 形态 / 设置」四个控制标签，菜单里的保存 / 另存为 / 导出 VPD / 导出 VMD 置灰，撤销只能撤销摆姿条目（数据修改需切回编辑模式撤销）。物理开关与参数、VMD 播放、形态滑杆、显示开关照常可用。

进入预览时按当前动作帧重新落姿态，物理以该帧为初始姿态复位，之后才允许播放动作 / 演算 / 摆姿；切回编辑时暂停动作、清零形态权重并 `reset()` 姿态，物理回写与临时摆姿都不会残留到数据视图。两种模式共用同一个撤销栈。

模型数据有未保存修改时，点窗口关闭按钮、`Alt+F4` 或菜单「退出」会先弹出确认框（保存并退出 / 不保存退出 / 取消）；`Ctrl+S` 与菜单「保存」走同一个入口，没有文件路径时自动弹出保存对话框。

### 检查器面板

以下标签只在编辑模式中出现：

- **信息**：统计概览、显示名称与描述、文件路径 / 版本 / 编码 / 索引宽度 / 附加 UV、结构校验。
- **骨骼**：名称搜索、父级 / 位置 / 尾 / 标志 / 付与 / IK 详情、增删复制与索引重映射。
- **表示枠**：特殊 / 普通枠、条目增删与顺序调整。
- **顶点**：位置 / 法线 / UV / 附加 UV / 权重（BDEF1/2/4、SDEF）编辑。
- **材质**：漫反射、高光、环境色、描边、球面 / Toon、纹理、面数、标志与增删。
- **面**：三角形列表、顶点索引编辑与增删。
- **形态**：顶点 / UV / 材质 / 骨骼 / 组 / 翻转 / 刚体偏移编辑，类型切换，滑杆预览（不写入文件）。
- **物理**：刚体（形状 / 质量 / 摩擦 / 衰减 / 组 / 碰撞掩码）与关节（6DOF 限制 / 弹簧）编辑。
- **柔体**：PMX 2.1 柔体参数、锚点与固定点编辑。
- **设置**：叠加层不透明度、重力 / 迭代 / 地面、配置文件路径、快捷键。显示开关、物理开关与深浅主题统一在顶部「视图」菜单。

预览模式只有四个控制标签：

- **动作**：VMD 导入 / 清除、播放 / 暂停 / 循环 / 变速、帧滑杆与匹配统计（未匹配轨道逐条列出）。播放中手动拖动骨骼只取消该骨骼的动作，其余骨骼继续受动作驱动。
- **物理**：物理演算开关、重置 / 清速度、重力 / 迭代 / 地面。编辑模式下物理不参与求值，刚体与关节的字段编辑见上。
- **形态**：形态滑杆，只影响当前预览姿态，不写入文件。
- **设置**：同编辑模式的设置面板。

## 目录结构

```
.
├─ CMakeLists.txt            构建入口：pmx_core / pmx_gpu / pmxstudio / pmx_tests
├─ cmake/Dependencies.cmake  依赖解析（本地 third_party 优先，可选联网兜底）
├─ build.bat                 Windows 一键配置 + 编译
├─ setup_linux.sh            Linux 一键装依赖 + 配置 + 编译 + 自测
├─ src/
│  ├─ core/                  与图形无关的纯逻辑，可单测
│  │  ├─ pmx.hpp             PMX 数据模型（顶点 SoA、骨骼、材质、形态、刚体、关节、柔体）
│  │  ├─ pmx_io.cpp          PMX 二进制读写：编码、索引宽度、各段解析与写出
│  │  ├─ model.cpp           纹理路径解析、模型包围盒等派生数据
│  │  ├─ math.hpp            Vec3 / Quat / Mat4 与变换工具
│  │  ├─ pose.hpp/.cpp       姿态求值：世界矩阵、付与继承、CCD IK、骨骼拖拽
│  │  ├─ morph.hpp/.cpp      形态展开（组 / 翻转）、顶点 / UV / 材质形态
│  │  ├─ skinning.hpp/.cpp   CPU 蒙皮参考实现（GPU 结果校验用）
│  │  ├─ vpd.hpp/.cpp        VPD 解析、应用、文本生成与导出
│  │  ├─ vmd.hpp/.cpp        VMD 解析、轨道绑定、逐帧采样与单帧导出
│  │  ├─ text_codec.hpp      名称编码：CP932 ↔ UTF-8 与宽松匹配键
│  │  ├─ fs.hpp              路径编码辅助（UTF-8 ↔ 宽字符）
│  │  └─ utf8_args.hpp/.cpp  Windows 宽字符命令行 → UTF-8 参数
│  ├─ gpu/
│  │  ├─ gl_api.hpp/.cpp     OpenGL 4.6 函数指针加载器（不用 GLAD）
│  │  ├─ shader.hpp/.cpp     着色器编译 / 链接与 uniform 缓存
│  │  └─ renderer.cpp        渲染核心：蒙皮 dispatch、材质、球面贴图、描边、叠加层、拾取
│  ├─ physics/
│  │  ├─ physics.cpp         Bullet 世界构建、6DOF 弹簧关节、刚体-骨骼绑定、步进
│  │  └─ softbody.cpp        柔体（btSoftBody）：节点、锚点、固定点、弯曲 / 簇、回读
│  └─ app/
│     ├─ main.cpp            GLFW + ImGui 查看器：窗口、输入、文件对话框、拖放、快捷键
│     ├─ viewer.hpp          查看器状态：模型、姿态、选择、撤销栈、编辑入口
│     ├─ viewer_edit.cpp     编辑 / 撤销 / 重做与运行时重建（Pose / 网格 / 物理）
│     ├─ document_ops.*      结构性增删与索引重映射
│     ├─ theme.*             亮 / 暗主题与 settings.ini 偏好持久化
│     ├─ camera.cpp          轨道相机（目标点 + 球面角 + 距离）
│     └─ panels/             检查器面板：info / bone / frame / vertex / material /
│                            face / morph / motion / physics / soft / settings
├─ assets/                   应用图标（icon.png / icon.ico / icon.rc）
├─ tests/
│  ├─ test_core.cpp          无窗口的对照测试
│  ├─ parity_probe.cpp       PMX 读写探针（供 Python 侧一致性校验调用）
│  ├─ test_model.pmx         测试模型（含贴图）
│  └─ tex_body.png / sph.png 测试贴图
└─ third_party/              自带源码：GLFW 3.4 / Dear ImGui v1.92.9b / stb / Bullet 3.25
```

## 依赖

| 依赖 | 版本 | 位置 |
| --- | --- | --- |
| GLFW | 3.4 | `third_party/glfw` |
| Dear ImGui | v1.92.9b | `third_party/imgui`（含 glfw / opengl3 后端） |
| stb_image | master | `third_party/stb/stb_image.h` |
| Bullet | 3.25 | `third_party/bullet/src` |

若本地副本缺失，可加 `-DPMX_FETCH_DEPS=ON` 从镜像联网拉取（默认 `https://gitee.com/mirrors`，可用 `-DPMX_DEPS_MIRROR` 修改）。

## CMake 选项

| 选项 | 默认 | 说明 |
| --- | --- | --- |
| `PMX_BUILD_APP` | ON | 构建 GLFW + ImGui 查看器 |
| `PMX_BUILD_TESTS` | ON | 构建 `pmx_tests` 与 `pmx_parity_probe` |
| `PMX_ENABLE_PHYSICS` | ON | 编译 Bullet 物理后端；关闭后物理接口退化为空实现 |
| `PMX_STATIC_RUNTIME` | ON | MSVC 静态 CRT（`/MT`），产物为不依赖 VC 运行时 DLL 的单文件 exe |
| `PMX_USE_SYSTEM_BULLET` | OFF | 使用系统安装的 Bullet 而非仓库内源码 |
| `PMX_FETCH_DEPS` | OFF | 本地 `third_party` 缺失时联网拉取依赖 |
| `PMX_DEPS_MIRROR` | gitee | `PMX_FETCH_DEPS=ON` 时使用的镜像 |
| `PMX_BULLET_SRC_DIR` | `third_party/bullet/src` | 自带 Bullet 源码位置 |

## 测试

`pmx_tests` 共 237 项检查，不创建窗口：

```powershell
build\Release\pmx_tests.exe      # Windows
```

```bash
./build/pmx_tests                # Linux
```

覆盖范围：

1. PMX 读写 round-trip（顶点 / 骨骼 / 材质 / 形态 / 刚体 / 关节 / 柔体各字段）。
2. 姿态求值：层级、付与继承、IK 收敛与限位。
3. CPU 蒙皮：BDEF 与 SDEF 结果对照。
4. 物理：世界构建、刚体静止位、柔体锚点、步进稳定性。
5. VPD：文本生成、内存 / 磁盘回读、应用、静止姿态不导出、全量导出。
6. VMD：单帧导出与磁盘回读、轨道绑定、关键帧采样（位移 / 旋转 / 形态）、未匹配名称、全量导出。

其他调试手段：

- `PMX_GPU_CHECK=1` 启动，首次 GPU 蒙皮后打印与 CPU 参考实现的最大偏差与非法分量顶点数。
- `pmx_parity_probe` 提供与 Python 版逐字段读写比对探针；比对脚本 `tools/parity_check.py` 位于 `python` 分支。

## 实现说明

### 坐标系与绕序

MMD 使用左手坐标系，PMX 面片在 OpenGL 右手系视图中是**顺时针朝外**。渲染网格时使用 `glFrontFace(GL_CW)`，网格绘制结束后恢复 `GL_CCW`，否则背面剔除会把可见面剔掉、描边壳会把模型涂黑。

### 卡通着色（Toon）

主网格着色器按 MMD 的 Toon 流程组织，三段效果叠加：

- **Toon 光照**：优先采样 ramp 贴图。材质为共享 toon 时（`toon_shared == 1`）使用内置的 `toon01..toon10`（程序化生成的竖直灰度渐变，低编号接近硬边两色、高编号更柔和），材质自带 toon 贴图时直接用该贴图；两者都以 `N·L`（0..1）作为贴图 v 坐标，与 MMD 的排布一致。贴图缺失时退回解析式两段阈值。
- **球面贴图**：按**相机空间**法线的 XY 采样（`mat3(uView) * N`），对应 MMD 的 Multiply / Add / 混合三种 `sphere_mode`；相机空间保证高光随视角滑动，世界空间法线做不到这一点。
- **边缘光**：`smoothstep(0.6, 1.0, 1 - N·V)` 乘本体色叠加，强度由「设置 → 卡通着色 → 边缘光」控制，默认 0.18，设 0 即回到 MMD 原版观感。

### 描边

倒置壳描边必须在主网格**之后**绘制：网格先写好深度，外壳只在外轮廓露出。绘制时 `glCullFace(GL_FRONT)`、`glDepthMask(GL_FALSE)` 并混合，结束后恢复。顺序颠倒会让整个可见面变成描边色。

描边外扩在**视空间**完成，偏移量与深度成正比（`uWidth * -z / proj[1][1]`），因此投影后线宽以像素计恒定：相机拉远不会消失、拉近也不会变成粗黑边。

仅靠深度裁剪对**单层布料**不够：外扩后的壳可能落在表面之前，把整片衣服涂成描边色。因此先关闭颜色写入、用 `GL_LEQUAL` 把当前材质已覆盖的像素写进模板（值 1），再用 `GL_NOTEQUAL 1` 绘制外壳，只保留轮廓外侧。窗口创建时显式请求 8 位模板缓冲。

半透明材质（`diffuse.w < 1`）最后绘制并关闭深度写入；绘制前按面区间中心到相机的距离**从远到近**排序，中心随区间首顶点的最大权重骨骼蒙皮变换，避免固定材质顺序在转动视角后出现前后颠倒。

### GPU 蒙皮

Compute Shader（GLSL 460）按 64 顶点一组 dispatch，SSBO 绑定 0~4：骨骼蒙皮矩阵、骨骼静止坐标、输入顶点（每顶点 8 个 `vec4`，权重与索引打包）、输出位置、输出法线。支持 BDEF1/2/4 与 SDEF；CPU 侧 [skinning.cpp](src/core/skinning.cpp) 保留同一套语义，用于 `PMX_GPU_CHECK=1` 时的逐顶点对比。

### 叠加层

骨骼画八面体，刚体按形状画盒 / 球 / 胶囊，关节画小球。叠加层绘制前关闭深度测试，保证模型内部的骨骼 / 刚体可见；刚体按 `group % 16` 分组着色，`mode == 0` 的静态刚体压暗。

### 物理

物理参数与步进对齐 MMD（参考 saba 的 `MMDPhysics`，MMD 兼容度最高的开源实现）：界面里的重力 -9.8 在物理世界放大 10 倍使用；固定步长 1/120、每帧最多 10 个子步；所有刚体 `DISABLE_DEACTIVATION` 且休眠阈值压到 0.01 / 0.1°（默认 0.8 / 1.0 会让布片在约束生效前就睡着并冻结在半空）；`additionalDamping` 全部打开；关节限位与弹簧系数原样写入，不启用的轴不 enableSpring，阻尼与平衡点用 Bullet 默认值；相连刚体之间不关闭碰撞；不做速度钳制。刚体旋转按 PMX 的 YXZ 顺序组四元数，关节框架按 ZYX 分解成等价欧拉角，刚体与骨骼通过静止矩阵偏移绑定。

碰撞过滤按 PMX 语义换算：文件里的组号是 1..16，掩码存的是「非衝突グループ」（bit=1 表示**不**与该组碰撞），读入时统一转成 0 基组号并把掩码反转，与 Bullet 的 `filterGroup / filterMask` 一致；写出时反向还原。若直接把原始 u16 当掩码用，袖 / 裙链会与胸腔、手腕互相穿透，被接触冲量顶到头顶。地面不属于任何组，按全组位加入世界。

物理刚体的世界矩阵只是「目标」，`Pose::apply_physics_world` 会按 `eval_order` 一次求值：先把目标换算成相对父级的本地量写进覆盖，再由 `compute_world` 统一叠加付与继承。早期版本自己在 `Physics::step` 里手写了一份求值循环，漏掉了付与继承，袖链的每根骨骼都会被父级「捩」骨继承出来的位移整体平移掉（实测偏差 2.3 个单位，布料被拉成扇面）。

#### 已知问题：三轴全零角限位会被 Bullet 当成锁定

部分模型（例如 `残虹.pmx`）的袖 / 发长链，每节关节的三轴角限位都写成 `0..0`。Bullet 的 `btRotationalLimitMotor::isLimited()` 只在 `lo > hi` 时返回自由，`lo == hi == 0` 会被当作「锁定在静止位」，于是几十节的链被焊成一根刚性长棍、随肘部整体翻转——抬手臂时整条袖子会拱过头顶。「重置物理」只是按当前姿态重摆刚体并清速度，链仍然焊着，所以复位后照样飞上去。

这不是渲染或数据解析的问题（已用独立解析器逐字节核对该模型：930 个关节中有 441 个三轴全零，袖链 65 节、发链、臂饰、腰布几乎全部如此；裙撑则有真实限位）。PmxEditor 里看着正常，是因为 PmxView 始终只画静止姿态、不叠加物理（见下方「与 PmxEditor 的分工对照」）。

曾试过把「三轴全零且无角弹簧」的关节（该模型 362 个）放宽到 X / Z ±π、Y ±π/2：无头实验里袖子确实垂下且长时间稳定，但整模型一起放开后物理观感严重变差——胸、腰、裙饰这类靠「多约束」锁定的辅助关节被一起放开，整体变得软塌。因此该改动已回退，当前仍按文件原样写入限位。若要再做，需要更精细的判定（例如只处理连续多节的链、或排除与主限位关节冗余的辅助关节），或做成逐关节开关。

### 柔体

柔体与刚体共享同一个 `btSoftRigidDynamicsWorld`：按材质的面片把模型顶点拆成柔体节点，锚点用节点相对刚体的局部坐标 `appendAnchor`（禁用刚体-柔体碰撞避免贴面抖动），固定点把节点质量设为 0。材质刚度（LST/AST/VST）、`config` / `cluster`、V/P/D/C 迭代次数与气动模型都从 PMX 2.1 字段直接映射；弯曲链接、簇、随机化按 `flags` 的 0x01/0x02/0x04 位生成。复位时先按当前姿态（含顶点形态）蒙皮得到初始坐标再重建，避免柔体从静止姿态「弹」回。

### 撤销 / 重做

两条独立栈：整模型快照（12 步，另受 256 MiB 内存预算约束，超预算时从最旧的快照开始丢弃，但至少保留 2 条）用于结构性编辑，轻量姿态条目（12 步）用于骨骼拖动 / 形态滑杆。同一 `coalesce` 键在 0.9 秒内连续操作合并为一条，拖动不会产生上百条记录。结构变化后 `clamp_selection` 修正选中索引，`refresh_after_edit` 按 `kind`（bone / material / morph / physics / physics_live / soft / structure / model）重建 Pose、网格与物理世界，并尽量保留姿态、形态权重、相机与选择。

### 与 PmxEditor 的分工对照

PmxEditor（`F:\MyProject\MMD\05_工具\PmxEditor`）把「改数据」和「试姿态」拆成三块独立屏幕，而不是一个窗口切两种模式：

| 屏幕 | 角色 | 画的是什么 |
| --- | --- | --- |
| Pmx 编辑 | 数据表编辑器 | 模型原始数据（顶点 / 面 / 材质 / 骨骼 / 形态 / 刚体 / 关节 / 柔体 / 表示枠） |
| PmxView | 模型视图 + 直接编辑视口 | **始终**画模型的初始数据（rest 姿态），不叠加 VMD / 物理 |
| TransformView | 变换视图（PmxView 的子窗口，工具栏 `T`） | 画**变形后**的状态，用来试骨骼 / 形态 / 物理 / VMD |

所以它的「预览」= TransformView，「编辑」= Pmx 编辑 + PmxView 的直接编辑。

**PmxView 直接编辑**：左上模式导航 `1 选择／基础编辑`、`2 权重/UV 绘制`、`3 刀刃`、`4 高级编辑（添加对象）`；选择目标 `顶 / 面 / 骨 / 刚 / J`；范围 `・ □ δ ○ △ Φ ×`（δ 为自由曲线/套索）；子窗口按需挂载（显示设置、选择对象、VMD、TransformView 等）。相机：右键拖动旋转、轮拖平移、滚轮推拉、右键双击复位、`Ctrl+右键双击` 设旋转中心、小键盘切视角，Ctrl/Shift 把步长调成 1/10 或 10 倍。

**TransformView 摆姿**：
- 单击骨骼选中并显示手柄；**只有不拖动才进入常规手柄操作**，一旦拖动就按「以手柄为中心」处理：骨骼本身可动则移到光标，不可动则旋转父级让骨骼对准光标。
- 拖手柄 = 沿手柄轴移动/旋转，`Shift` 反向补偿父级（例如抬肩而不改手臂朝向）；`Ctrl+点击` 穿透选中同一位置后面的骨骼；Shift/Ctrl 控制步长。
- IK 逐骨骼开关，另有 `IK 链接的连续变换`（默认每帧从初始状态重算）、`跳过物理 IK 系列`、`忽略局部轴`、SDEF 缩放等开关。
- **动作与手动摆姿互不打断**：一次变换只取消**被操作骨骼**的运动，其它骨骼继续受 VMD 控制；把某部分「初始化」后它又重新受动作驱动。动作循环播放，只能初始化帧位置、不能跳帧；`从当前运动获取` 可把当前帧固定成姿势。
- 物理 `开/关` 会初始化物理状态；`重新计算骨骼对齐`、`关节锁内部计算` 默认开启（相当于 MMD 的修正），关掉才是原始 Bullet 行为。
- TransformView 的变换不落盘，要写回数据得用 `保存为当前形状` / `使用当前变形状态更新模型几何` / `添加具有当前变换状态的骨骼变形`；另有 VPD 复制粘贴、把当前形状作为 1F 动作加进 VMD 列表。

**骨骼位置语义**（与我们的 `Bone::pos` 一致）：
- 位置是**模型空间绝对坐标**，父骨骼只决定层级，不把坐标变成相对值。
- 「表示先(＞) + 相对偏移」只决定 PmxView 里骨骼末端画在哪，**不影响真实位置**。
- 「变形顺序（层级）+ 后物理」决定求值顺序：layer 小的先算，后物理骨骼在物理解算之后。
- 「轴限位 / 局部轴」只限定手动操作时的轴，**不限制内部变形**。
- 「付与」：局部付与用源骨骼的当前局部变换，非局部付与用世界增量（含 IK、形态产生的量），付与率 `-1.0` 就是常见的抵消骨骼（如 `左肩C`）。
- TransformView 的 `移动/旋转 XYZ` 是相对静止姿态的局部变换量，视口看到的是叠加了付与/IK/物理之后的世界位置。

**与当前 PmxStudio 的差异**（供后续调整参考）：

| 维度 | PmxEditor | PmxStudio 现状 |
| --- | --- | --- |
| 视图 | rest 视图与变形视图分开 | 单一视口：编辑模式只画原始姿态（不叠动作 / IK / 物理），预览模式才显示变形结果 |
| 模式 | 两个独立窗口，无互斥开关 | 编辑 / 预览互斥，切换时复位姿态与形态，预览隐藏编辑面板 |
| 摆骨骼 | TransformView 里可自由拖（临时变换不落盘） | 仅预览模式可拖，编辑模式只改数据 |
| 手动 vs 动作 | 只取消被操作骨骼的运动 | 只取消被操作骨骼的动作，其余骨骼继续受动作驱动 |
| IK | 逐骨骼开关 + 连续变换 + 跳过物理 IK | 仅 VMD 表示枠里的 IK 开关；手动旋转时自动临时关闭会被牵动的 IK 链 |
| 撤销 | 变换状态单独一条链 | 姿态拖动与模型编辑共用撤销栈 |

### 偏好持久化


主题、显示开关、叠加层不透明度、重力 / 迭代 / 地面等写入 `%APPDATA%/PmxStudioCpp/settings.ini`（UTF-8 key=value）。启动时先读偏好再加载模型，`last_model` 只在没有命令行参数时生效；退出时保存。

### 分辨率与 DPI 适配

UI 缩放因子由 `glfwGetWindowContentScale` 与 framebuffer/window 比例推导（`content_scale / fb_ratio`，钳制在 1–3），macOS 上该比值恒为 1。样式与所有面板内的固定像素尺寸统一乘以 [ui_scale.hpp](src/app/ui_scale.hpp) 的 `pmxui::scale()`，`FontScaleDpi` 让 ImGui 1.92 的动态字体按缩放后的字号重新光栅化，高 DPI 下不会出现位图拉伸发虚。

初始窗口按 1440×900 逻辑尺寸乘缩放因子，并限制在显示器工作区 92% 以内后居中，最小尺寸 760×500。界面顶部是「文件 / 视图 / 帮助」菜单栏，底部是显示状态消息与 FPS、网格/骨骼统计的状态栏；检查器默认 580 宽并填满两者之间的可用高度，再用 `SetNextWindowSizeConstraints` 约束在视口内。主循环每帧检测跨显示器拖动或系统缩放变化，变化后重新应用主题。布局不写 `imgui.ini`（`IniFilename = nullptr`），避免旧 DPI 下保存的像素尺寸在新分辨率下把控件挤坏。

部分 Linux 桌面不提供 `Xft.dpi`，自动推导会得到 1.0；可用 `PMX_UI_SCALE=2 ./pmxstudio` 强制缩放。

### 路径与编码

所有路径字符串在内部统一使用 UTF-8；文件访问经 [fs.hpp](src/core/fs.hpp) 转成宽字符 `std::filesystem::path` 再打开。Windows 上 `std::ifstream(const char*)`、`std::filesystem::path(const std::string&)` 与 `stbi_load()` 都按系统 ANSI 代码页解释，中文 / 日文目录会直接打不开；纹理改为按 UTF-8 路径读入内存后走 `stbi_load_from_memory`。命令行参数同样会被 CRT 按 ANSI 代码页解码，启动时用 `GetCommandLineW` + `CommandLineToArgvW`（[utf8_args.cpp](src/core/utf8_args.cpp)）重新解析成 UTF-8。

### VPD 导出

默认只导出与静止姿态不同的骨骼和非零形态权重，可切换为全量。旋转先归一化，数值 6 位小数并把近零值归零。文件优先写 Shift-JIS（CP932），名称包含 CP932 无法表示的字符时自动退回 UTF-8；读取时按 UTF-8 严格校验自动识别编码。

### VMD 动作

VMD 以 30 fps 计时，播放时按 `dt * 30 * 速度` 推进帧号，循环用 `fmod` 回到起点，`dt` 上限 0.1 秒避免卡顿后跳帧。每个骨骼 / 形态名称聚成一条轨道，关键帧按帧号排序后二分查找，首帧之前与末帧之后都钳制在端点值。

骨骼关键帧末尾的 64 字节是 4×4 插值表：行是 X1 / Y1 / X2 / Y2，列是 X / Y / Z / 旋转。每个轴对称取 `x1 = ip[a]`、`y1 = ip[4+a]`、`x2 = ip[8+a]`、`y2 = ip[12+a]`，除以 127 得到三次贝塞尔控制点；位移三轴各用一条曲线，旋转对四元数做 slerp，形态权重线性插值。曲线退化为直线时直接返回 `t`，省去迭代。导出默认写 MMD 的 20 / 20 / 107 / 107 缓动值。

求值时先 `pose.reset()`，把轨道写入 `base_rot` / `base_trans`，再交给 `apply()` 叠加骨骼形态，随后照常走 IK 与 `world()`，与 VPD 的写入方式一致。轨道按「先精确匹配名称与英文名，再忽略空格 / 下划线并小写」的顺序查找；未匹配的名称收集到绑定结果里，在「动作」面板逐条列出。播放不写撤销栈；拖动骨骼只取消被拖骨骼的动作，其余骨骼继续按动作播放，避免下一帧把手改的姿态整体覆盖。

## 已知限制

- VMD 相机 / 灯光 / 阴影轨道只统计数量，不参与播放；**表示枠 / IK 帧参与播放**：按帧取最近的开关状态，关掉的 IK 链不再求解，骨骼改由动作轨道直接驱动（MMD 的足 IK 开关就是这么工作的）；导出只写当前单帧的骨骼与形态。
- 文件对话框封装为 Windows 专用；Linux 下通过命令行参数或拖放打开文件。
- IK 限位按欧拉逐轴钳制；接近 ±90° 时用分支滞回保持连续。

## 许可

[GNU General Public License v3.0](LICENSE)。第三方组件许可见各自目录（[third_party](third_party) 下的 `LICENSE*`）。
