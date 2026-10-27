# PmxStudio C++ 版

`cpp/` 是 PmxStudio 的原生 C++ 重写：不依赖 Python / PyQt5，直接用 C++20 + OpenGL 4.6 实现 PMX 查看与姿态编辑。Python 版独立维护在 `python` 分支；本分支与 `main` 同源，自带全部第三方源码（`cpp/third_party/`），断网也能构建。

主要能力：PMX 2.0/2.1 读写、GPU Compute Shader 蒙皮（BDEF1/2/4、SDEF）、付与继承、CCD IK、形态（顶点/UV/材质/骨骼/组/翻转/刚体）、Bullet 物理与柔体预览、全量检查器编辑与撤销/重做、VPD 姿态导入导出、主题与偏好持久化、骨骼/刚体/关节叠加层与拾取。

---

## 1. 目录结构

```
cpp/
├── CMakeLists.txt          构建入口：pmx_core / pmx_gpu / pmxstudio / pmx_tests
├── build.bat               Windows 一键配置 + 编译
├── setup_linux.sh          Linux 一键装依赖 + 配置 + 编译 + 自测
├── third_party/            自带源码：glfw 3.4 / imgui v1.92.9b / stb / bullet 3.25
├── cmake/Dependencies.cmake 依赖解析（本地 third_party 优先，可选联网兜底）
├── src/
│   ├── core/               与图形无关的纯逻辑，可单测
│   │   ├── pmx.hpp         PMX 数据模型（顶点 SoA、骨骼、材质、形态、刚体、关节、柔体）
│   │   ├── pmx_io.cpp      PMX 二进制读写：编码、索引宽度、各段解析与写出
│   │   ├── model.cpp       纹理路径解析、模型包围盒等派生数据
│   │   ├── math.hpp        Vec3 / Quat / Mat4 与变换工具
│   │   ├── pose.hpp/.cpp   姿态求值：世界矩阵、付与继承、CCD IK、骨骼拖拽
│   │   ├── morph.hpp/.cpp  形态展开（组/翻转）、顶点/UV/材质形态
│   │   ├── skinning.hpp/.cpp CPU 蒙皮参考实现（GPU 结果校验用）
│   │   └── vpd.hpp/.cpp    VPD 解析、应用、文本生成与导出
│   ├── gpu/
│   │   ├── gl_api.hpp/.cpp OpenGL 4.6 函数指针加载器（不用 GLAD）
│   │   ├── shader.hpp/.cpp 着色器编译/链接与 uniform 缓存
│   │   └── renderer.cpp    渲染核心：蒙皮 dispatch、材质、球面贴图、描边、叠加层、拾取
│   ├── physics/
│   │   ├── physics.cpp     Bullet 世界构建、6DOF 弹簧关节、刚体-骨骼绑定、步进
│   │   └── softbody.cpp    柔体（btSoftBody）：节点、锚点、固定点、弯曲/簇、回读
│   └── app/
│       ├── main.cpp        GLFW + ImGui 查看器：窗口、输入、文件对话框、拖放、快捷键
│       ├── viewer.hpp      查看器状态：模型、姿态、选择、撤销栈、编辑入口
│       ├── viewer_edit.cpp 编辑/撤销/重做与运行时重建（Pose / 网格 / 物理）
│       ├── document_ops.*  结构性增删（骨骼/材质/形态/表示枠/刚体/关节/柔体）与索引重映射
│       ├── theme.*         亮/暗主题与 settings.ini 偏好持久化
│       ├── camera.cpp      轨道相机（目标点 + 球面角 + 距离）
│       └── panels/         检查器面板：info / bone / frame / vertex / material /
│                           face / morph / physics / soft / settings
└── tests/
    ├── test_core.cpp       无窗口的对照测试
    └── parity_probe.cpp    PMX 读写探针（供 Python 侧一致性校验调用）
```

---

## 2. 依赖

全部随仓库提供，克隆后无需联网：

| 依赖 | 版本 | 位置 |
| --- | --- | --- |
| GLFW | 3.4 | `third_party/glfw` |
| Dear ImGui | v1.92.9b | `third_party/imgui`（含 glfw / opengl3 后端） |
| stb_image | master | `third_party/stb/stb_image.h` |
| Bullet | 3.25 | `third_party/bullet/src` |

需要系统提供的是编译器、CMake 与图形/窗口系统开发包，见下一节。若想改用联网拉取，可加 `-DPMX_FETCH_DEPS=ON`（默认 `https://gitee.com/mirrors`，可用 `-DPMX_DEPS_MIRROR` 改）。

## 3. 构建与运行

需要 CMake ≥ 3.20 与支持 C++20 的编译器。

**Windows**（MSVC 2019/2022，先装 Visual Studio 的「使用 C++ 的桌面开发」）：

```powershell
cpp\build.bat                                  # 配置 + 编译 Release
cpp\build\Release\pmxstudio.exe tests\test_model.pmx
cpp\build\Release\pmx_tests.exe                # 205 项无窗口测试
```

**Linux**：

```bash
bash cpp/setup_linux.sh                        # apt 安装依赖 + 编译 + 自测
# 或手动：
cmake -S cpp -B cpp/build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build cpp/build -j"$(nproc)"
./cpp/build/pmxstudio tests/test_model.pmx
```

Linux 需要 `build-essential cmake ninja-build libx11-dev libxrandr-dev libxinerama-dev
libxcursor-dev libxi-dev`；中文界面还需要系统装有 Noto CJK 或文泉驿字体（`fonts-noto-cjk`）。
无显示服务（纯 SSH 容器）时只能构建与跑测试，查看器需要 X11。

### CMake 选项

| 选项 | 默认 | 说明 |
| --- | --- | --- |
| `PMX_BUILD_APP` | ON | 构建 GLFW + ImGui 查看器 |
| `PMX_BUILD_TESTS` | ON | 构建 `pmx_tests` 与 `pmx_parity_probe` |
| `PMX_ENABLE_PHYSICS` | ON | 编译 Bullet 物理后端；关闭后物理接口退化为空实现 |
| `PMX_USE_SYSTEM_BULLET` | OFF | 使用系统安装的 Bullet 而非仓库内源码 |
| `PMX_FETCH_DEPS` | OFF | 本地 `third_party` 缺失时联网拉取依赖 |
| `PMX_DEPS_MIRROR` | gitee | `PMX_FETCH_DEPS=ON` 时使用的镜像 |
| `PMX_BULLET_SRC_DIR` | `third_party/bullet/src` | 自带 Bullet 源码位置 |

---

## 4. 操作方式

| 操作 | 行为 |
| --- | --- |
| 「打开 PMX…」/「导入 VPD…」 | 资源管理器文件对话框选择文件 |
| 拖放 `.pmx` / `.vpd` 到窗口 | 同上，可直接替换当前模型 |
| 左键**双击**骨骼 / 刚体 / 关节 / 形态 / 顶点 | 选中（空白处双击取消） |
| 左键拖动已选中的骨骼 | 世界空间位移；拖 IK 控制器会带动整条链解算 |
| 右键拖动已选中的骨骼 | 绕相机轴旋转 |
| 左键拖动空白处 | 旋转视角 |
| 右键拖动空白处 / `Shift` + 中键 | 平移视角 |
| 中键拖动 | 旋转视角 |
| 滚轮 | 缩放 |
| `F` / `R` / `P` | 相机居中 / 重置姿态 / 开关物理演算 |
| `Ctrl+O` | 打开 PMX |
| `Ctrl+S` / `Ctrl+Shift+S` | 保存 / 另存为 |
| `Ctrl+Z` / `Ctrl+Shift+Z` / `Ctrl+Y` | 撤销 / 重做 / 重做 |

未选中骨骼时拖动只改变视角，状态栏会提示先双击选中。

### 面板

- **信息**：统计概览、显示名称与描述、文件路径/版本/编码/索引宽度/附加 UV、结构校验
- **骨骼**：名称搜索、父级/位置/尾/标志/付与/IK 详情、增删复制与索引重映射
- **表示枠**：特殊/普通枠、条目增删与顺序调整
- **顶点**：位置/法线/UV/附加 UV/权重（BDEF1/2/4、SDEF）编辑
- **材质**：漫反射、高光、环境色、描边、球面/Toon、纹理、面数、标志与增删
- **面**：三角形列表、顶点索引编辑与增删
- **形态**：顶点/UV/材质/骨骼/组/翻转/刚体偏移编辑，类型切换，滑杆预览（不写入文件）
- **物理**：刚体（形状/质量/摩擦/衰减/组/碰撞掩码）与关节（6DOF 限制/弹簧）编辑
- **柔体**：PMX 2.1 柔体参数、锚点与固定点编辑
- **设置**：显示开关、叠加层不透明度、重力/迭代/地面、深浅主题、配置文件路径、快捷键

---

## 5. 实现要点

### 坐标系与绕序
MMD 使用左手坐标系，PMX 面片在 OpenGL 右手系视图中是**顺时针朝外**。渲染网格时使用 `glFrontFace(GL_CW)`，网格绘制结束后恢复 `GL_CCW`，否则背面剔除会把可见面剔掉、描边壳会把模型涂黑。

### 描边
倒置壳描边必须在主网格**之后**绘制：网格先写好深度，外壳只在外轮廓露出。绘制时 `glCullFace(GL_FRONT)`、`glDepthMask(GL_FALSE)` 并混合，结束后恢复。顺序颠倒会让整个可见面变成描边色。

仅靠深度裁剪对**单层布料**不够：外扩后的壳可能落在表面之前，把整片衣服涂成描边色。因此与 Python 版一致，先关闭颜色写入、用 `GL_LEQUAL` 把当前材质已覆盖的像素写进模板（值 1），再用 `GL_NOTEQUAL 1` 绘制外壳，只保留轮廓外侧。窗口创建时显式请求 8 位模板缓冲。

### GPU 蒙皮
Compute Shader（GLSL 460）按 64 顶点一组 dispatch，SSBO 绑定 0~4：骨骼蒙皮矩阵、骨骼静止坐标、输入顶点（每顶点 8 个 `vec4`，权重与索引打包）、输出位置、输出法线。支持 BDEF1/2/4 与 SDEF；CPU 侧 [skinning.cpp](src/core/skinning.cpp) 保留同一套语义，用于 `PMX_GPU_CHECK=1` 时的逐顶点对比。

### 叠加层
骨骼画八面体，刚体按形状画盒/球/胶囊，关节画小球。叠加层绘制前关闭深度测试（与 Python 版一致），保证模型内部的骨骼/刚体可见；刚体按 `group % 16` 分组着色，`mode == 0` 的静态刚体压暗。

### 物理
Bullet 固定 1/60 步进。刚体旋转按 PMX 的 YXZ 顺序组四元数，关节框架分解为等价欧拉角。运动学刚体（`mode == 0`）不启用 `DISABLE_DEACTIVATION`：初始 `ISLAND_SLEEPING`，仅在位移超过阈值时临时 `ACTIVE_TAG`，避免物理岛永远无法休眠。刚体与骨骼通过静止矩阵偏移绑定。

回写姿态时必须按 `pose.eval_order` **逐骨累积世界矩阵**（与 Python 版 `physics_step` 同构）：父骨世界矩阵要用本帧已回写后的结果。若改用帧开始前缓存的世界矩阵，袖 / 裙 / 发这类多级链每深一层都会重复叠加一次父级位移，误差逐帧放大，布料会被拉成巨大的面片。

### 柔体
柔体与刚体共享同一个 `btSoftRigidDynamicsWorld`：按材质的面片把模型顶点拆成柔体节点，锚点用节点相对刚体的局部坐标 `appendAnchor`（禁用刚体-柔体碰撞避免贴面抖动），固定点把节点质量设为 0。材质刚度（LST/AST/VST）、`config`/`cluster`、V/P/D/C 迭代次数与气动模型都从 PMX 2.1 字段直接映射；弯曲链接、簇、随机化按 `flags` 的 0x01/0x02/0x04 位生成。复位时先按当前姿态（含顶点形态）蒙皮得到初始坐标再重建，避免柔体从静止姿态「弹」回。

### 撤销 / 重做
两条独立栈：整模型快照（12 步）用于结构性编辑，轻量姿态条目（12 步）用于骨骼拖动/形态滑杆。同一 `coalesce` 键在 0.9 秒内连续操作合并为一条，拖动不会产生上百条记录。结构变化后 `clamp_selection` 修正选中索引，`refresh_after_edit` 按 `kind`（bone/material/morph/physics/physics_live/soft/structure/model）重建 Pose、网格与物理世界，并尽量保留姿态、形态权重、相机与选择。

### 偏好持久化
主题、显示开关、叠加层不透明度、重力/迭代/地面等写入 `%APPDATA%/PmxStudioCpp/settings.ini`（UTF-8 key=value）。启动时先读偏好再加载模型，`last_model` 只在没有命令行参数时生效；退出时保存。

### 路径与编码
所有路径字符串在内部统一使用 UTF-8；文件访问经 [fs.hpp](src/core/fs.hpp) 转成宽字符 `std::filesystem::path` 再打开。Windows 上 `std::ifstream(const char*)`、`std::filesystem::path(const std::string&)` 与 `stbi_load()` 都按系统 ANSI 代码页解释，中文/日文目录会直接打不开；纹理改为按 UTF-8 路径读入内存后走 `stbi_load_from_memory`。

### VPD 导出
默认只导出与静止姿态不同的骨骼和非零形态权重，可切换为全量。旋转先归一化，数值 6 位小数并把近零值归零。文件优先写 Shift-JIS（CP932），名称包含 CP932 无法表示的字符时自动退回 UTF-8；读取时按 UTF-8 严格校验自动识别编码。

---

## 6. 测试

`cpp/build/Release/pmx_tests.exe` 共 205 项检查，不创建窗口：

1. PMX 读写 round-trip（顶点/骨骼/材质/形态/刚体/关节/柔体各字段）
2. 姿态求值：层级、付与继承、IK 收敛与限位
3. CPU 蒙皮：BDEF 与 SDEF 结果对照
4. 物理：世界构建、刚体静止位、柔体锚点、步进稳定性
5. VPD：文本生成、内存/磁盘回读、应用、静止姿态不导出、全量导出

### 与 Python 版的一致性校验

跨实现比对脚本（`tools/parity_check.py` + `tests/parity/pmxsem.py`）位于 `python` 分支：该脚本用
`tests/test_model.pmx` 与追加柔体后的 PMX 2.1 用例，分别让 Python 版与 C++ 探针
`pmx_parity_probe roundtrip` 读入再写出，再做逐字段语义比较。本分支只保留探针本身，
需要回归时把两个分支分别检出后运行脚本即可。

其他调试手段：`PMX_GPU_CHECK=1` 启动，首次 GPU 蒙皮后打印与 CPU 参考实现的最大偏差与非法分量顶点数。

---

## 7. 与 Python 版的差距

已对齐：渲染外观、叠加层配色/尺寸、双击选中约定、姿态拖动、形态滑杆、物理面板、VPD 导入导出、PMX 保存、全部检查器面板（信息/骨骼/表示枠/顶点/材质/面/形态/物理/柔体/设置）、结构性增删与索引重映射、整模型快照撤销/重做、柔体物理、主题切换与配置持久化。

尚未移植：

- VMD 动画（数据、时间轴与播放；按当前需求不实现）
