# 原版 PmxEditor × 新版 PmxEditor_Modern 同操作一致性验收报告

- 被测对象
  - 原版：`D:\Project\MMD\05_工具\PmxEditor (MMD模型编辑器）\PmxEditor_x64.exe`（中文汉化版，0.2.7.3，x64 + 就地 msvcr120 修复）
  - 新版：`D:\Project\PmxEditor_Modern`（Python + PyQt5 重写；基于 HEAD `54d1942`，含本轮未提交修复）
- 基准模型：`D:\Project\MMD\02_模型库\KARU式Rabbit Hole MIKU.ver 1.5_by_KR-SAM_141b6a51e3ad47ff26d0910dd71e3a71\KARU式Rabbit Hole MIKU.ver 1.6.pmx`
  （116,036 顶点 / 204,919 三角面 / 21 材质 / 168 骨骼 / 22 表情 / 10 贴图 / 82 刚体 / 74 关节 / 0 柔体，PMX 2.0，UTF-16LE）
- 结论速览（**全部修复 + 后续建议 + 单字段补测 + 多模型复跑 + ②剩余三项 + 补齐面/柔体页后**）：**42 项操作（41 项双侧 + M3 单侧）中 36 项保存结果字段级完全一致**；差异 5 项：S1（有意保留）、B7（原版开轴固定时会归一化轴向量）、N1/N2（设计/能力差异）、E5（新版更正确）；M3 仅单侧可比。第二模型 `米娅.pmx` 上复跑 5 项核心操作，全部 0 差异。原报告列出的 8 项差异里有 7 项已修复并复验一致（含 I2 暴露的「新建 IK 默认 loop/angle」），另补上 E4（文字编码）/E5（追加 UV）两个可写入口与 M4/M5/M6/V2/B4/B5/P2/F2/I2/I3 共 10 项，再打通原版 **CSScript（.cx）通道**补上 FA1/N3/N4/SB1/SB2 五项，最后由新增的「面」页与「柔体」页把 FA1/SB2 从能力差异转为双侧 GUI 0 差异。新版在「文件往返保真」上仍优于原版。

## 一、测试方法

同一模型、同一操作序列，两侧**各自用真实 GUI 操作**；GUI 无法编辑或原版无入口的字段，走原版自带 CSScript（`.cx`）通道写入（不用内部 API 改数据）。操作完成后各自「文件 → 另存为」到 `tests/parity/work/<OP>_orig.pmx`（`.cx` 通道为 `_cx.pmx`）与 `<OP>_mod.pmx`，再用自研语义比较器 `tests/parity/pmxsem.py`（1e-5 容差，逐字段覆盖 version/encoding/add_uv/name/comment/textures/顶点数组/索引/材质/骨骼/表情/表示枠/刚体/关节/柔体）比对两个另存文件。

- 原版侧驱动：`tests/parity/origlib.py`（win32 SetCursorPos + mouse_event / SendInput 键鼠、PIL 抓屏）+ `tests/parity/origui.py`（窗口定位、页签切换、索引跳转、另存为、对话框应答）+ `tests/parity/uia.py`（PowerShell UIAutomation 抓取控件矩形以取得点击坐标）。
- 新版侧驱动：`tests/parity/modern.py`（复用仓库 `tests/harness.py`：真实命中测试点击、对话框打桩、截图、日志）+ `tests/parity/side_mod.py`。
- 每个操作都重新加载模型，避免操作之间互相污染；每步留存截图。
- 注意：原版骨骼/材质/顶点等页面的数值是**离开该条目时才回写模型**，脚本里用「切到别的条目再切回」的方式提交（`commit_bone`），否则另存出来是未修改状态。

## 二、文件往返保真（R1，无修改另存）

| 侧 | 另存结果 | 与源文件比对 |
| --- | --- | --- |
| 原版 | 8,437,650 B | **7 字节不同**（偏移 8178795/8178799/8179743/8180019/8180023/8180027/8180853，全在关节/弹簧参数区，1 LSB 级浮点，如 `c222bf5a→c222bf59`、`99453fa6→99453f82`、`3c02dcce→3c04dcce`）；语义完全一致 |
| 新版 | 8,437,650 B | **逐字节完全相同**（md5 与源文件一致） |

→ 新版写入器保真度优于原版（原版会因 float→decimal→float 往返损失末位）。


> **状态（本轮修复后）**：标记为「已修复」的 6 项（E2 / B1 / M1 / M2 / V1 / S2）已在代码里修掉，
> 并用**同一套 GUI 脚本**重跑新版侧后复验为字段级一致；详见第九节。

## 三、操作结果总表

详见 `tests/parity/compare_all.md`（脚本生成，含每项差异的字段级明细）。摘要：

| # | 操作 | 判定 | 关键数据 |
| --- | --- | --- | --- |
| E1 | 模型日文名 → `PARITY_E1` | ✅ 一致 | 两侧均只改 `name` |
| E2 | 注释改三行（中日英混排） | ✅ 一致（已修复） | 修复后两侧都存 **CRLF**（`\r\n`） |
| E3 | 模型英文名 → `PARITY_EN` | ✅ 一致 | 两侧均只改 `name_en` |
| E4 | 文字编码 UTF-16LE → UTF-8 | ✅ 一致（已修复） | 两侧 `encoding` 均 0→1、文件均 8,435,389 B、`pmxsem` **0 差异**（第九节） |
| E5 | 追加UV 数 0 → 2 | ✅ 新版真正落盘（原版 UI 无效） | 新版 `add_uv=2`、`v_add (116036, 8)`、12,150,802 B；原版下拉可设 2 但保存仍写 0 |
| B1 | 骨骼5「上半身」位置 X=1.0 | ✅ 一致（已修复） | 修复后只改 `bones[5].pos[0]`，不再搬动顶点 |
| B2 | 骨骼5 名称 → `PARITY_BONE` | ✅ 一致 | 只改 `bones[5].name` |
| B3 | 骨骼5 变形层级 0→3 | ✅ 一致 | 只改 `bones[5].layer` |
| M1 | 材质0 漫反射 R=0.5 | ✅ 一致（已修复） | 新增 RGBA 精确数值框，两侧都存 0.5 |
| M2 | 材质0 透明度 A=0.5 | ✅ 一致（已修复） | 同上（A=0.5） |
| V1 | 顶点0 位置 X=0.5 | ✅ 一致（已修复） | 只写被改动的分量，Y/Z/法线/权重不再漂移 |
| F1 | 表情0 首个顶点偏移 X=0.1 | ✅ 一致 | `morphs[0].offsets[0].offset[0]`=0.1 |
| P1 | 刚体0 质量 1.0→2.5 | ✅ 一致 | `rigid[0].mass`=2.5 |
| J1 | Joint0 旋转限制 X 下限 −0.5° | ✅ 一致 | 两侧都存 −0.008727 rad（度→弧度换算一致） |
| S1 | 删除骨骼 #100 | ⚠ 有意差异 | 引用重映射一致；子骨骼父级：新版挂到被删骨骼的真正父级 87，原版挂 99 |
| S2 | 删除材质 #20「metal」 | ✅ 一致（已修复） | 两侧顶点 116,036→102,081、面 614,757→538,605、文件同为 7,573,725 B |
| U1 | 骨骼位移后 Ctrl+Z 撤销 | ✅ 一致 | 两侧都完全回滚到基线 |
| N1 | 新建骨骼 | ⚠ 行为差异 | 两侧都 +1 骨骼，但默认值不同（见下） |
| N2 | 新建材质 | ⚠ 能力差异 | 原版 + 号**灰化不可用**（材质数 21）；新版可新建（22） |
| M4 | 材质0 描边大小 1.0→0.5 | ✅ 一致 | 只改 `materials[0].edge_size` |
| M5 | 材质0 关闭「双面描绘」 | ✅ 一致 | `draw_flags` 15→14（清 0x01） |
| M6 | 材质0 开启「描边有效」 | ✅ 一致 | `draw_flags` 15→31（置 0x10） |
| V2 | 顶点0 UV-u 0.5→0.25 | ✅ 一致 | 只改 `v_uv[0,0]`，v 分量与位置/法线/权重全无漂移 |
| B4 | 骨骼5 关闭「显示」 | ✅ 一致 | `bones[5].flags` 27→19（清 0x08） |
| B5 | 骨骼5 关闭「可旋转」 | ✅ 一致 | `bones[5].flags` 27→25（清 0x02） |
| P2 | 刚体0 模式「跟随」→「演算+对齐」 | ✅ 一致 | `rigid[0].mode` 0→2 |
| F2 | 表示枠 Root 追加骨骼 #106「兔耳_2_2.R」 | ✅ 一致 | `frames[0].items` 1→2，两侧都追加 `(0, 106)` |
| I2 | 骨骼5 开启 IK | ✅ 一致（已修复） | `flags` 27→59；`ik={target:-1,loop:0,angle:1.0,links:[]}` 两侧一致（第九节 P3） |
| I3 | 骨骼5 IK：target=bone6、loop=3、angle=10°、Link=bone4/bone5 | ✅ 一致 | 原版侧由 `.cx` 写入（GUI 无 IK 链编辑入口）、新版由 IK 面板 GUI 写入；`flags` 27→59、`ik={target:6,loop:3,angle:0.174533,links:[4,5]}` 两侧 0 差异 |
| V3 | 顶点0 法线 Y 0.706→1.0 | ✅ 一致 | 只改 `v_nrm[0,1]` |
| V4 | 顶点0 UV-v 0.052→0.75 | ✅ 一致 | 只改 `v_uv[0,1]` |
| B6 | 骨骼5 开「旋转付与」+ 付与率 0.5 | ✅ 一致 | `flags` 27→283（+0x100）、`append_ratio` 0→0.5 |
| B7 | 骨骼5 开「轴固定」 | ⚠ 差异 2 处 | `flags` 27→1051 一致；**原版另把 `axis` 归一化为骨骼朝向**（`axis[1]` 0→0.998421、`axis[2]` 1→−0.056169），新版保持 (1,0,0) |
| M7 | 材质0 球面模式 无→乘法 | ✅ 一致 | `materials[0].sphere_mode` 0→1 |
| P3 | 刚体0 形状 球→箱 | ✅ 一致 | `rigid[0].shape` 0→1 |
| P4 | 刚体0 所属组 0→1 | ✅ 一致 | `rigid[0].group` 0→1 |
| FA1 | 面材质重分配：材质0 前 300 面 → 材质1 | ✅ 一致（已补齐「面」页） | 原版 `.cx` 与新版「面」页同语义：`materials[0].face_count` 118404→117504、`materials[1]` 15204→16104、`indices` 按材质顺序重建，两侧 0 差异 |
| N3 | 复制骨骼5「上半身」并追加 | ✅ 一致 | 原版 `.cx` `Clone()` vs 新版「复制当前骨骼」：骨骼 168→169，新骨骼仅 name/name_en 不同，其余字段 0 差异 |
| N4 | 复制材质0「Skin」并追加（连面） | ✅ 一致（已修复） | 材质 21→22、面 204919→244387、文件 8,911,392 B；新版原先只复制 `face_count` 不复制面索引，已修（见第九节） |
| SB1 | PMX 2.1 柔体基座往返另存 | ✅ 一致 | 基座 `SB0_cx.pmx`（1 柔体 / 1 锚点 / 1 固定点）；两侧均 8,437,856 B、0 差异 |
| SB2 | 柔体0 总质量 2.5→3.5、碰撞余量 0.05→0.1 | ✅ 一致（已补齐「柔体」页） | 原版 `.cx` 与新版「柔体」页同语义：`soft[0].total_mass` 2.5→3.5、`collision_margin` 0.05→0.1，其余字段 0 差异 |

## 四、问题清单与处理状态（按优先级）

### P1-1 移动骨骼时会带动权重顶点（B1） — ✅ 已修复（见第九节）
- 现象：把骨骼5 X 从 0 改到 1.0 后，新版另有 14,602 个顶点被按权重位移（如顶点 554 权重 0.125 → X 0.1879→0.3131，恰为 0.125×1.0），`v_pos` 最大变化 0.859；原版 PmxEditor 移动骨骼**不动任何顶点**。
- 影响：用户只想摆骨骼，网格却被永久改写并随文件保存，且与原版结果不可互换。
- 代码：`src/pmxeditor/panels/bone.py:66 self.move_verts_sw = Switch(False)`、`:520 _move_verts_toggled()`、`:541 self.edit("移动骨骼并带动顶点" if move else "移动骨骼", apply, ...)`。
- 建议：默认关闭「移动时带动顶点」，或与原版对齐（原版无此默认行为）；若保留，需在标题/提示上明确告警。

### P1-2 删除材质的语义与原版不同（S2） — ✅ 已修复（见第九节）
- 现象：删除材质 #20（`metal`，76,152 面）后
  - 原版：连同其独占顶点一起删除 → 顶点 116,036→102,081（−13,955）、面 614,757→538,605（−76,152），文件 8,437,650→7,573,725 B。
  - 新版：几何全部保留，76,152 个面被并入上一个材质 → `materials[19].face_count` 5,520→81,672，顶点/面数不变，文件 8,437,554 B。
- 影响：模型体积、渲染结果（整片金属区改用 `coin` 的贴图/材质）与原版不一致，属于**破坏性差异**。
- 代码：`src/pmxeditor/doc.py:385`（删除材质，`merge=True` 时把三角面并入上一个材质）+ `src/pmxeditor/panels/material.py:439` 调用点。
- 建议：删除前提供选择「删除该材质使用的顶点/面」与「仅删材质并并入相邻材质」，默认对齐原版行为。

### P1-3 注释换行被写成 LF（E2） — ✅ 已修复（见第九节）
- 现象：多行注释存盘后为 `\n`，原版为 `\r\n`；PMX 注释是原样字节，跨编辑器查看时换行丢失/错乱。
- 代码：`src/pmxeditor/panels/info.py:119 v = self.comment.toPlainText()`（QPlainTextEdit 已把行尾统一成 `\n`）→ `src/pmxeditor/pmx.py:416 m.comment = r.text()`。
- 建议：写入时按 `\r\n` 规范化（或保留原文行尾风格）：`v.replace("\r\n", "\n").replace("\n", "\r\n")`。

### P1-4 颜色只有 8 位精度（M1/M2） — ✅ 已修复（见第九节）
- 现象：输入 0.5 只能得到 0.501961（128/255），原版可存任意浮点 0.5。
- 代码：`src/pmxeditor/panels/material.py:57 self.diffuse = ColorButton([1,1,1,1])`（`ui_widgets.py:185 ColorButton` 内部 `QColor.fromRgbF`，8 位通道）；`material.py:66 / _color()`。
- 建议：给漫反射/反射/环境/轮廓色各配 4 个浮点数值框（或颜色对话框旁提供数值输入），至少让 `diffuse[3]`（透明度）可输入浮点。

### P2-1 顶点编辑后的浮点漂移（V1） — ✅ 已修复（见第九节）
- 编辑顶点0 X=0.5 后，该顶点 Y 16.80584→16.805799、法线 3e-6→0、权重 0.53826→0.5383（≤4.0e-5）。原版只有 X 变。
- 说明：疑似 `src/pmxeditor/panels/vertex.py:_apply` 走了一次 float32 重算/归一化。影响小（视觉不可见），但会让「保存前后 diff 干净」的期望落空。

### P2-2 删骨骼时规范化 tail 标记位（S1） — ✅ 已修复（S1 为部分修复，见第九节）
- `src/pmxeditor/doc.py:318-322`：
  `if b.flags & BF_TAIL_INDEX: b.tail_bone = _remap(...); if b.tail_bone < 0: b.flags &= ~BF_TAIL_INDEX; b.tail_offset = [0,0,0]`
- 结果：源模型里 9 个「标记为骨骼索引但 tail_bone=-1」的骨骼被清位（flags 271→270、283→282、267→266），原版原样保留。方向上新版更规范（-1 索引本身非法），但属于**未被要求的连带修改**。

### P2-3 新建骨骼的默认值不同（N1） — 有意保留
| 字段 | 原版 | 新版 |
| --- | --- | --- |
| name | `新規ボーン1` | `新建骨骼` |
| name_en | 空 | `new_bone` |
| 父骨骼 | −1（无） | 0（当前选中骨骼） |
| 位置 | (0, 0, 0) | (0.0, 1.0157, 0)（父骨骼位置 +Y1） |
| flags | 26 | 30 |

新版是「作为当前骨骼的子级」的显式设计，但与原名/原坐标不一致，会影响「同操作同结果」的验收口径，建议至少在报告中标注为**有意的功能增强**。

### P2-4 开启「轴固定」时的轴向量处理（B7） — 未修（已知差异）

- 现象：两侧 `bones[5].flags` 都 27→1051（置 `BF_FIXED_AXIS`），但**原版在开启轴固定的瞬间会把 `axis` 归一化为骨骼朝向**（`axis` 由 (1,0,0) 变为 (1, 0.998421, −0.056169)），新版保持原值 (1,0,0)。
- 影响：只有「轴固定」骨骼在 PMX 里的轴向冗余数据不同，不影响物理/姿态；属低危一致性差异，本轮未改（改则需推断原版归一化算法）。
- 现场：`work/B7_orig.pmx` vs `work/B7_mod.pmx`（`pmxsem` 2 处）。

### 能力差异（非缺陷，但需记录）
- E5 追加UV：新版已提供 0–4 下拉并真正落盘；原版可设但 PMX 2.0 不落盘 → 记为「新版更正确」的有意差异。
- N2 新建材质：原版材质页 + 号灰化（不支持），新版支持 → 新版功能更多。
- ~~FA1 面页材质重分配：新版无「面」页~~ → 已补齐「面」页（`panels/face.py`），原版 `.cx` 语义与新版 GUI 0 差异。
- ~~SB2 柔体参数编辑：新版无柔体编辑入口~~ → 已补齐「柔体」页（`panels/soft.py`），原版 `.cx` 语义与新版 GUI 0 差异。

## 五、判定为一致的项（可直接作为回归基线）

E1、E3、B2、B3、F1、P1、J1、U1 以及 R1 往返保真：两侧保存结果字段级完全一致（U1 撤销后与基线 0 差异）。

上一轮小结：修复后新增一致项 **E2、B1、M1、M2、V1、S2、E4**（第九节有逐条复核数据），即 20 项双侧操作里 **15 项字段级一致**、1 项有意差异（S1）、2 项设计差异（N1/N2）、1 项新版更正确（E5），另有 M3 只有单侧。

截至本轮（42 项操作）：**36 项字段级完全一致**；差异 5 项 = S1（有意）、B7、N1/N2（设计差异）、E5（新版更正确），M3 仅单侧可比。

## 六、截图对比证据

`tests/parity/pairs/<OP>_pair.png`：左侧原版、右侧新版，同操作后的界面状态（28 张，含 E4/E5：E4 两侧「文字编码」都是 UTF-8；E5 新版「附加 UV」下拉为 2，原版下拉同样停在 2 但保存仍写 0）。FA1/N3/N4/SB1/SB2 没有配对拼图，截图见 `tests/parity/shots/` 与 `tests/shots/`（FA1/SB2 新版侧已改为「面」页 / 「柔体」页截图）。

## 七、复现步骤

```powershell
cd D:\Project\PmxEditor_Modern
# 1) 启动原版（保持窗口在 (20,20)，PmxView 在 (1440,20)）
python -X utf8 -c "import sys;sys.path.insert(0,r'tests/parity');import origui as U;U.start()"
# 2) 原版侧跑操作（每个 op 会重新加载模型、截图、另存）
python -X utf8 tests/parity/side_orig.py E1 E2 B1 M1 S2
# 3) 新版侧跑同样的操作
.\build\python\python.exe tests\parity\side_mod.py E1 E2 B1 M1 S2
# 4) 语义比对总表
python -X utf8 tests/parity/compare_all.py     # → tests/parity/compare_all.md
# 5) 单次对比
python -X utf8 -c "import sys;sys.path.insert(0,r'tests/parity');import pmxsem as P;print(P.fmt(P.diff(r'tests/parity/work/B1_orig.pmx', r'tests/parity/work/B1_mod.pmx')))"
```

工具文件：`tests/parity/{origlib,origui,uia,modern,pmxsem,side_orig,side_mod,cxrun,cxop,compare_all,make_pairs,regress}.py`、`cx/*.cs`（原版 CSScript 片段）、`uia/*.json`（各页控件坐标快照）、`work/*.pmx`（42 项操作的另存结果，含 `SB0_cx.pmx` 柔体基座）、`shots/*_orig.png`、`pairs/*_pair.png`。

## 八、后续建议落实情况

上一版报告把「表示枠增删、面页材质重分配、IK 链编辑、复制骨骼/材质、物理类型切换、PMX 2.1、贴图替换、VPD 载入、视口交互」列为未覆盖。通过同一框架（`side_orig.py` / `side_mod.py` 追加 `op_XX`，两侧操作 → 另存 → `pmxsem` 比对）累计补了 **15 项**操作；其中前 10 项中 9 项两侧都用真实 GUI、I3 原版侧走 CSScript `.cx`，后 5 项见下方「②剩余三项」，全部串行跑通：

| 操作 | 覆盖的场景 | 判定与关键数据 |
| --- | --- | --- |
| M4 | 材质描边大小 | ✅ 一致，`edge_size` 1.0→0.5 |
| M5 | 材质「双面描绘」开关 | ✅ 一致，`draw_flags` 15→14 |
| M6 | 材质「描边有效」开关 | ✅ 一致，`draw_flags` 15→31 |
| V2 | 顶点 UV 编辑 | ✅ 一致，只改 `v_uv[0,0]`，v 分量/位置/法线/权重零漂移 |
| B4 | 骨骼「显示」位 | ✅ 一致，`flags` 27→19 |
| B5 | 骨骼「可旋转」位 | ✅ 一致，`flags` 27→25 |
| P2 | 刚体模式（物理类型）切换 | ✅ 一致，`rigid[0].mode` 0→2 |
| F2 | 表示枠追加骨骼项 | ✅ 一致，`frames[0].items` 1→2，两侧都追加 `(0, 106)` |
| I2 | 骨骼开启 IK | ✅ 一致（修 P3 后），`flags` 27→59、`ik={target:-1,loop:0,angle:1.0,links:[]}` |
| I3 | IK 链编辑（target/loop/角度/两条 Link） | ✅ 一致，`ik={target:6,loop:3,angle:0.174533,links:[bone4,bone5]}`；原版侧经 `.cx`，新版侧经 IK 面板 + 「添加链接」按钮 |

副产物：I2 首次比对暴露出新版「开启 IK」时用了 dataclass 默认的 `loop=40 / angle=0.5`，而 PmxEditor 写入 `loop=0 / angle=1.0` —— 已按第九节 P3 修正。

#### ②剩余三项（面页 / 复制对象 / PMX 2.1 柔体）

新增 5 条比对（原版侧全部经 `.cx` 定义语义，落盘仍由 PmxEditor 完成）：

| 操作 | 覆盖的场景 | 判定与关键数据 |
| --- | --- | --- |
| FA1 | 面页材质重分配：材质0 前 300 面 → 材质1 | ✅ 一致（新版「面」页 GUI）：`m0 118404→117504`、`m1 15204→16104`、`indices` 按材质顺序重建 |
| N3 | 复制骨骼5 | ✅ 一致：`.cx Clone()` 与新版「复制当前骨骼」0 差异（仅 name/name_en 按同一规则变化） |
| N4 | 复制材质0 | ✅ 一致（修 `duplicate_material` 后）：材质 21→22、面 204919→244387、8,911,392 B |
| SB1 | PMX 2.1 柔体基座往返 | ✅ 一致：`SB0_cx.pmx`（1 柔体/1 锚点/1 固定点）两侧 0 差异、同尺寸 |
| SB2 | 柔体参数编辑 | ✅ 一致（新版「柔体」页 GUI）：`total_mass 2.5→3.5`、`collision_margin 0.05→0.1` |

副产物：N4 首次比对暴露 `duplicate_material` 只复制 `face_count`、不复制面索引（材质面数之和 733,161 > 索引 614,757）→ 已修（见第九节）。

### 仍未覆盖（含原因）

- ~~**面页材质重分配**~~：已用 `.cx` 覆盖（FA1），新版随后补齐「面」页，现为双侧 GUI 0 差异。
- ~~**IK 链编辑（改 target / 增删 link）**~~：已用 CSScript `.cx` 通道覆盖（I3）。
- ~~**复制骨骼 / 复制材质**~~：已用 `.cx Clone()` 覆盖（N3/N4），并修掉 N4 暴露的材质面索引不一致。
- ~~**PMX 2.1 特性（柔体）**~~：已构造 `SB0_cx.pmx` 基座并覆盖往返（SB1）与参数编辑（SB2）；新版随后补齐「柔体」页，现为双侧 GUI 0 差异；QDEF 仍未覆盖。
- **贴图替换 / VPD 载入**：都经由系统文件对话框，落盘只有路径字符串（VPD 的姿态不进 PMX），`pmxsem` 无法判定对错，需目视。
- **视口交互**（旋转/缩放/线框/骨骼拾取）：纯视觉行为，不产生文件差异，建议单独做视觉回归。


### CSScript（.cx）通道：绕开 GUI 限制的可编程入口

原版 PmxEditor 自带 `_plugin\CSScript`（菜单 `编辑(E) → 插件(P) → CSScript → C#スクリプト`），可在进程内直接读写 `IPXPmx`。本轮把它接成了测试通道：

| 文件 | 作用 |
| --- | --- |
| `tests/parity/cxrun.py` | 打开/复用 CSScript 窗体（键盘导航 `编辑(E)→p→右→回车`），把脚本体粘进「簡易形式」页，点「実行」，轮询 `tests/parity/cx_log.txt` 取结果 |
| `tests/parity/cxop.py` | 单个操作的完整流程：重载模型 → 跑 `.cx` 片段 → 最小化脚本窗体 → 回编辑器「另存为」`work\<OP>_cx.pmx` → `pmxsem` 比对 |
| `tests/parity/cx/*.cs` | 各操作的「簡易形式」语句片段（如 `op_V1.cs`、`op_I3.cs`） |
| `tests/parity/cx/parity_template.cx` | 可直接在 GUI 里「スクリプト読み込み」的完整 `.cx` 模板（内含读模型概况 + 写日志的示例） |

使用要点（踩过的坑）：

- 只能用「簡易形式」粘**语句片段**；把完整 class 粘进「一般形式」会被自动头包进 `Run()` 里 → `CS0116 / CS1022 / CS0542` 编译错误。
- 自动头已定义 `host/builder/connect/view/pmx/header/info/vertex/material/bone/morph/node/body/joint/sbody` 与 `bdx`（构造器）。
- **自动尾未启用**：改完字段必须显式调用
  `connect.Pmx.Update(pmx); connect.Form.UpdateList(UpdateObject.All); connect.View.PMDView.UpdateModel(); connect.View.PMDView.UpdateView();`
  否则改动不写回编辑器（另存出来仍是旧值）。`cxop.py` 的 `TAIL` 已内置这四行。
- 未载入模型时访问 `vertex[0]` 会抛 `ArgumentOutOfRangeException`，脚本报「スクリプトの実行に失敗しました」。
- 另存必须用**绝对路径**（相对路径按模型所在目录解析，会弹「路径不存在」）。

等价性验证：同一操作分别用 GUI（`work\V1_orig.pmx`）与 `.cx`（`work\V1_cx.pmx`）在原版里做「顶点0 X=0.5」，两者 `pmxsem` **0 差异**；IK 链（I3）则由 `.cx` 定义「原版语义」，新版 GUI 结果与之 **0 差异**。

## 九、修复记录与修复后复核

用户「开修」后按报告第四节逐条落地，当轮改动集中在 6 个源文件（后续 N4 修复另加 `src/pmxeditor/doc.py`）；每项修完都用**同一套两侧 GUI 脚本**（`side_orig.py` / `side_mod.py`）重跑并 `pmxsem` 复验。

| 编号 | 改动位置 | 做法 | 复核结果 |
| --- | --- | --- | --- |
| P1-3（E2） | `src/pmxeditor/pmx.py` | 新增 `_crlf()`，`save_pmx` 写 `comment` / `comment_en` 前统一把换行规范成 CRLF | `E2_orig` vs `E2_mod` **0 差异**，回读 `'PARITY 注释测试\r\n第二行 line2\r\n第三行 TEST'` |
| P1-1（B1） | `src/pmxeditor/panels/bone.py` | 「移动时带动顶点」不再从 `Config` 读回（构造即关），`_move_verts_toggled` 不再持久化，改为状态栏提示；tooltip 说明原版不动顶点 | `B1_orig` vs `B1_mod` **0 差异**（`bones[5].pos=[1.0, 12.8, −0.5666]`，`v_pos` 完全不变） |
| P1-4（M1/M2） | `src/pmxeditor/ui_widgets.py`、`panels/material.py` | 新增 `ColorSpins`（RGBA 浮点数值框，3 位小数），与颜色按钮双向同步；材质页加「漫反射 RGBA / 高光色 RGB / 环境色 RGB / 描边 RGBA」四行，`_fill_fields` 用 PMX 原值填写以免被量化 | `M1`/`M2` 与 `_orig` **0 差异**（`diffuse=[0.5,1,1,1]` / `[1,1,1,0.5]`）；取色对话框路径（M3）仍是 8 位 `0.501961`，属预期 |
| P2-1（V1） | `src/pmxeditor/panels/vertex.py` | `_apply` 按分量判定「是否真的被改过」（位置/法线 4 位、UV/描边 5 位），只写改动分量 | `V1_orig` vs `V1_mod` **0 差异** |
| P1-2（S2） | `src/pmxeditor/doc.py`、`panels/material.py` | `remove_material` 非 merge 分支修正切片（`face_count` 是**索引数**，原来误乘 3 导致越界、什么都没删）并调用新增的 `compact_vertices()` 清理孤立顶点、重映射 `indices` 与形态偏移顶点索引；删除对话框默认按钮改为「连同三角面删除」；面数显示 `/3` | `S2_orig` vs `S2_mod` **0 差异**：顶点 116,036→102,081、面 614,757→538,605、文件 7,573,725 B（与原版同尺寸），`validate_model` 无告警，往返字节一致 |
| P2-2（S1） | `src/pmxeditor/doc.py` | 只有 `tail_bone == 被删索引` 时才清 `BF_TAIL_INDEX` / 归零 `tail_offset`；父骨骼处理改为「等于被删索引→挂被删骨骼的父级」 | 与 `S1_orig` 由 15 处降到 **2 处**：`bones[100].parent` A=99 / B=87、`v_bones` 1 个元素。**有意保留**：把子骨骼挂到被删骨骼真正的父级（87「左小指」）比原版挂到索引前一位（99「左薬指３」）语义更正确，删除对话框也是这么承诺的 |

| E4 文字编码 | `src/pmxeditor/panels/info.py`、`src/pmxeditor/pmx.py` | 信息页把只读编码标签换成下拉（UTF-16LE / UTF-8），选择后走 `self.edit("切换文字编码", ...)`；保存时 `_Writer.text` 按新编码整体重写；`validate_model` 不告警 | `E4_orig` vs `E4_mod` **0 差异**，两侧均 8,435,389 B，UTF-8 下中日文名/注释完好 |
| E5 追加UV | `src/pmxeditor/pmx.py`（新增 `set_add_uv`）、`src/pmxeditor/panels/info.py` | 新增 0–4 下拉；`set_add_uv` 按需补齐/截断每个顶点的 4×N 个浮点并同步 `add_uv`，`validate_model` 校验宽度一致 | 新版 `add_uv=2`、`v_add (116036, 8)`、12,150,802 B（+3,713,152 = n×32）；0→2→4→0 回到 8,437,650 B 且与 `00_mod.pmx` 逐字节相同；原版侧仍写 0 → 记为「新版更正确」 |
| P3（I2） | `src/pmxeditor/panels/bone.py` | 开启 IK 时显式使用 PmxEditor 同款初值 `IK(target=-1, loop=0, angle=1.0, links=[])`（原为 dataclass 默认 `loop=40 / angle=0.5`） | `I2_orig` vs `I2_mod` **0 差异** |
| N4（复制材质） | `src/pmxeditor/doc.py` | `duplicate_material` 复制材质时，把源材质 `face_count` 个索引追加到 `indices` 末尾并同步 `face_count`（原来只复制计数不复制面，导致材质面数之和大于索引总数） | `N4_cx` vs `N4_mod` **0 差异**：材质 21→22、面 204919→244387、8,911,392 B；重载后 `sum(face_count)==614757+118404`，新材质面索引与源材质逐项相同 |

附带的单元级验证（`tests/parity/verify_fixes.py` 等）：CRLF 往返、删材质 20 后统计与原版逐字段一致、删骨骼 100 后 `frames`/`rigid` 引用与基线一致、`validate_model` 全部无告警、保存→重载→保存字节一致。

回归：`tests/parity/regress.py` 用 `tests/go.py` 跑了 12 个既有场景（undo / vertex_edit / morph_edit / struct / struct2-4 / small_fixes / frame / undo2 / skin / restmove）**全部 anomalies=0**；`inventory` 仅 2 条长路径 `text-clipped`；`poseundo` 报「姿态拖动应压 1 条撤销记录，实际 0」——已用 `git stash` 在改动前的 HEAD 上复现同样失败，**属既有问题**，与本次修复无关。

## 十、仍未对齐 / 不在本次范围

- **N1 新建骨骼**：命名与默认父级/坐标为有意的功能增强（原版 `新規ボーン1` 且父级 −1），未改。
- **N2 新建材质**：原版 + 号灰化，新版支持新建 —— 新版能力更强，未改。
- **E5 追加UV**：原版下拉可设为 2 但保存仍写 0（PMX 2.0 下无效），新版会真正写入 4×N 浮点/顶点 —— 有意差异，新版更符合 PMX 规范。
- **M3 取色对话框**：`QColorDialog` 本体就是 8 位，这条路必然量化；需要精确值请用新增的浮点数值框。
- 仍未覆盖：贴图替换 / VPD 载入 / 视口交互 / QDEF，原因见第八节末尾。
- 新增 B7：原版开轴固定会归一化轴向量，新版不归一化（见第四节 P2-4），保留为已知差异。
- ~~新增 FA1 / SB2：新版无「面」页、无柔体编辑入口，属能力差异（见第四节），未实现新功能。~~
  **已补齐**：新增「面」页与「柔体」页，FA1/SB2 由能力差异转为 0 差异（见 11.4）。


## 十一、多模型复跑与全量回归（补充复跑）

### 11.1 第二模型复跑

- 模型：`D:\Project\MMD\02_模型库\米娅\米娅.pmx`（4,908,850 B / 79,848 顶点 / 113,995 面 / 52 材质 / 321 骨骼 / 29 形态 / 12 贴图 / 183 刚体 / 261 关节）。
- 驱动方式：`PARITY_MODEL=<模型> PARITY_SUF=_M2`，两侧执行器同名环境变量切换模型与产物后缀。
- 结果：V1（顶点0 位置 X）、M1（材质0 漫反射 R）、B2（骨骼5 名称）、P1（刚体0 质量）、J1（Joint0 旋转下限）**5 项全部 0 差异**。
- 附注：`side_mod.select_bone()` 已加兜底——按关键字过滤不到目标骨骼时自动清空搜索框重取（米娅的骨骼 5 不叫「上半身」）。

### 11.2 全量回归

- `tests/run.py` 共 **114 个场景**（`def scen_*`）。本轮用 `tests/parity/regress.py` 逐个 subprocess 跑其中 **40 个功能场景**：

| 场景 | 结果 | 说明 |
| --- | --- | --- |
| 其余功能场景（修复前 36 个） | anomalies=0 | menu / view / sel2–sel5 / click_rigid / rows / tree2 / empty / struct / struct2 / struct3 / struct4 / undo / undo2 / rest / restmove / mouse / hover / flagguard / frame / morph_edit / vertex_edit / skin / ellipsoid / sdefr1 / ikclamp / physlazy / physlive / optim / undobudget / small_fixes / theme_probe / theme_persist / config / sync / final / fps |
| inventory | anomalies=2 | 超长模型路径的 `Faint` 标签 `text-clipped`（既有问题，与本轮无关） |
| vp | anomalies=2 | `pose-move`、`phys-pose`：模拟拖动未产生位移 —— **在 HEAD 上同样复现**，非本轮引入 |
| sel | 0（已修） | P0-3：选中时重建列表导致悬空 `QModelIndex` → 访问冲突；修复后 rc=0、42.7s（详见 `ANOMALIES.md`） |
| sel6 | 0（已修） | 场景脚本引用不存在的 `doc.sel` → 改用 `sel_kind/sel_index` |
| mouse | 0（已修） | P1-1 取消 `editor/move_bone_vertices` 持久化后该场景原断言失效 → 已改为「开关不再写 settings.json、新实例默认关闭」，并清掉本机 `settings.json` 的遗留键 |

`sel`、`sel6` 修复后复跑均为 0 异常 → 当前 **38/40 场景 0 异常**；`inventory` 的 2 条 `text-clipped` 与 `vp` 的 2 条拖动差异为既有告警/既有行为。

- 未跑的重场景：`clickall`（> 260 s 超时，全界面暴力点击，与本次改动无关）；`flag2`–`flag8`、`real*`、`grid_*` 等历史调试场景（开发期一次性探针）。
- 当轮改动量：`git diff --stat` → 7 个 src 文件 + `tests/run.py`，+270/−30 量级。

### 11.3 本轮补充（P0-3 崩溃修复 + ②剩余三项）

- `sel` 场景 **0xC0000005** 已定位并修复（`PhysicsPage.select` 每次选中都重建列表 → 场景持有的 `QModelIndex` 悬空）：`sel` rc=0、**0 异常**、42.7s；`sel2 / sel6 / click_rigid / verify_p0 / final / rows_fix / physlazy / physlive / struct4 / sel5` 均 0 异常（详见 `ANOMALIES.md` P0-3）。
- ② 剩余三项新增 **FA1 / N3 / N4 / SB1 / SB2** 五条比对：N3/N4/SB1 **0 差异**，FA1/SB2 为能力差异；N4 暴露的 `duplicate_material` 材质面索引不一致已修复。
- 修复后回归：`struct`、`real3` 0 异常；`walk` 为逐控件慢场景，260s 窗口内未跑完（非崩溃，覆盖由上一轮 40 场景 + 本次定向场景兜底）。

### 11.4 补充新版缺失功能（FA1 / SB2 转为一致）

新增两个检查器页，把此前的两项能力差异做成真实 GUI 功能：

| 功能 | 代码 | 说明 | 复核 |
| --- | --- | --- | --- |
| 「面」页 | `src/pmxeditor/panels/face.py`、`doc.py: reassign_faces()` | 材质列表显示三角面数；选择源材质、起始面、数量与目标材质后「移动这些面」，按材质顺序重建扁平 `indices`，可撤销 | `side_mod.py: op_FA1` 走真实 GUI；`FA1_cx` vs `FA1_mod` **0 差异**（m0 118404→117504、m1 15204→16104、总索引不变） |
| 「柔体」页 | `src/pmxeditor/panels/soft.py`、`doc.py: add_softbody()/remove_softbody()` | 柔体列表 + 新建/删除；名称、形状、材质、所属组、16 位碰撞组、生成选项（弯曲链接/簇/随机化）、质量/碰撞余量/气动模型、12 项 config、6 项 cluster、4 项 iteration、3 项 material_params、锚点与固定点 | `side_mod.py: op_SB2` 走真实 GUI；`SB2_cx` vs `SB2_mod` **0 差异**（仅 `total_mass`、`collision_margin`） |

- 应用接线：`app.py` 的 `PAGES` 追加 `face`(8) / `soft`(9)，`RAIL_ORDER=(0,1,6,7,2,8,3,4,9,5)`，`KIND_PAGE["soft"]=9`，`EDIT_STATUS["soft"]`；`theme.py` 新增 `face` / `soft` 图标；`doc._clamp_selection` 支持 `soft`。
- 同步更新：`tests/parity/compare_all.py` 的 NOTE 与说明、`compare_all.md`（**42 项：36 一致 / 5 差异 / 1 单侧**）、`ANOMALIES.md`、`README.md`（页数 8→10）。
- 新增回归场景：`tests/run.py: scen_face_edit`（数据层顺序断言 + GUI 移动 + 撤销 + 往返）与 `scen_softbody_edit`（新建/字段/锚点/固定点/PMX 2.1 往返/删除撤销）。
- 全量回归：`tests/parity/regress.py` 跑了 41 个功能场景（含 `face_edit`、`softbody_edit`，以及 menu/view/sel2–5/struct1–4/undo/undo2/frame/morph_edit/vertex_edit/skin/ellipsoid/sdefr1/ikclamp/physlazy/physlive/optim/undobudget/small_fixes/theme_*/config/sync/final/fps 等），**全部 rc=0、anomalies=0**。

### 11.5 膝部鼓包修复（付与参考系）

- **根因**：非ローカル付与把源骨骼的世界旋转投影到**目标骨骼父级**。`膝` 的 `append_parent` 等于自身父级，相对旋转恒为单位阵，付与率 −0.75 失效（小腿 60° 时 `膝` 仍转 60°，应为 15°），膝周大量权重给到 `膝` 的顶点被过度拧转。
- **修复**：改用源骨骼**自身父级**求本地旋转（与 `mmd_tools` shadow-bone 语义一致）；`Pose.world_subset` 补源父级；`native/pmx_core.cpp` 同步修改并重建 `_pmx_core`。
- **验证**：新增 `tests/run.py: scen_append`，60° 时 `膝` 世界角 = **15.00°**、native/NumPy 差 **0**；新增 `scen_overlay_pose` 校验刚体/关节叠加层与拾取使用当前姿态矩阵。全量回归 **43 个功能场景**（原 41 + append + overlay_pose）**全部 rc=0、anomalies=0**；`poseundo` 仍为已记录的既有失败（与本次改动无关）。膝部 60° 弯曲截图见 `tests/shots/parity_knee_fix_60.png`。
- **Roll/坐标系排查**：PMX 无 Roll 字段，`local_x/local_z` 不参与蒙皮；渲染无 Z 翻转；本模型无 SDEF/QDEF，DQS 已做符号对齐——鼓包与这三者无关。
- 另修：刚体/关节叠加层与拾取改用当前姿态/物理变换，不再停留在 PMX 静止坐标；`bone = -1` 的 8 个胸部物理体改按「子树最大的根骨骼」整体增量跟随（见 `ANOMALIES.md`）。

<br />
