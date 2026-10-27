# PmxStudio

PMX（MikuMikuDance 模型格式）查看与编辑工具的原生 C++ 实现：C++20 + GLFW 3.4 + Dear ImGui + OpenGL 4.6 + Bullet 3.25。

Python 版（PyQt5 + OpenGL）独立维护在 [`python` 分支](https://github.com/shuyan-k/PmxStudio/tree/python)。

## 下载即用

仓库自带全部第三方源码（`cpp/third_party/`：GLFW、ImGui、stb_image、Bullet），clone 后**无需联网**即可编译。
只需系统具备编译器与图形开发包：

**Windows**（Visual Studio 2019/2022，勾选「使用 C++ 的桌面开发」+ CMake）：

```powershell
cpp\build.bat
cpp\build\Release\pmxstudio.exe tests\test_model.pmx
```

**Linux**（Debian/Ubuntu 系）：

```bash
bash cpp/setup_linux.sh          # 自动安装依赖 → 编译 → 自测
./cpp/build/pmxstudio tests/test_model.pmx
```

脚本会安装 `build-essential cmake ninja-build libx11-dev libxrandr-dev libxinerama-dev
libxcursor-dev libxi-dev`（中文界面另需 `fonts-noto-cjk`）。查看器需要 X11 显示服务；
纯 SSH 环境可只构建并运行无窗口测试。

## 功能

- **数据**：PMX 2.0 / 2.1 读写，保留编码、索引宽度与全部字段；结构校验与统计。
- **渲染**：GPU Compute Shader 蒙皮（BDEF1/2/4、SDEF）、材质/球面贴图/Toon、模板缓冲描边、地面网格、骨骼/刚体/关节叠加层与拾取。
- **姿态**：FK、付与继承、CCD IK 与逐轴限位、骨骼拖动；VPD 导入 / 导出。
- **形态**：顶点 / UV / 材质 / 骨骼 / 组 / 翻转 / 刚体偏移，滑杆预览。
- **物理**：Bullet 刚体、6DOF 弹簧关节与柔体（btSoftBody），固定 1/60 步进，可边演算边摆姿。
- **编辑**：十个检查器面板（信息 / 骨骼 / 表示枠 / 顶点 / 材质 / 面 / 形态 / 物理 / 柔体 / 设置），结构增删与索引重映射，撤销 / 重做，主题与偏好持久化。

## 操作

| 操作 | 行为 |
| --- | --- |
| 左键双击骨骼 / 刚体 / 关节 | 选中（空白处取消） |
| 左键 / 右键拖动已选骨骼 | 世界空间位移 / 绕相机轴旋转 |
| 左键 / 右键 / 中键拖动空白处 | 旋转 / 平移 / 旋转视角（`Shift`+中键平移） |
| 滚轮 | 缩放 |
| `F` / `R` / `P` | 视图居中 / 重置姿态 / 物理开关 |
| `Ctrl+O` / `Ctrl+S` / `Ctrl+Shift+S` | 打开 / 保存 / 另存为 |
| `Ctrl+Z` / `Ctrl+Shift+Z` / `Ctrl+Y` | 撤销 / 重做 |

## 测试

```bash
./cpp/build/pmx_tests      # 205 项无窗口检查：读写、姿态、蒙皮、物理、VPD
```

`pmx_parity_probe` 提供与 Python 版的逐字段读写比对探针，比对脚本位于 `python` 分支。

## 目录

```
cpp/
├─ CMakeLists.txt          构建入口：pmx_core / pmx_gpu / pmxstudio / pmx_tests
├─ build.bat               Windows 一键构建
├─ setup_linux.sh          Linux 一键装依赖 + 构建 + 自测
├─ third_party/            glfw 3.4、imgui v1.92.9b、stb_image、bullet 3.25（自带）
├─ src/core/               PMX 读写、姿态 / IK、蒙皮、形态、VPD
├─ src/gpu/                GL 加载器、着色器、渲染核心
├─ src/physics/            Bullet 刚体 / 关节 / 柔体
├─ src/app/                GLFW + ImGui 查看器与十个检查器面板
└─ tests/                  无窗口对照测试与一致性探针
tests/test_model.pmx       测试模型（含贴图）
docs/canhong-parity/       「残虹」模型物理与面板对比报告
```

实现细节、坐标系约定、CMake 选项见 [cpp/README.md](cpp/README.md)。

## 已知限制

- 不实现 VMD 动画（数据、时间轴与播放）。
- 文件对话框封装为 Windows 专用；Linux 下通过命令行参数或拖放（X11 文件拖放依赖 GLFW 支持）打开文件。
- IK 限位按欧拉逐轴钳制；接近 ±90° 时用分支滞回保持连续。

## 许可

[GNU General Public License v3.0](LICENSE)。第三方组件许可见各自目录（`cpp/third_party/*/LICENSE*`）。
