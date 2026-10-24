# PMX 编辑器（PmxEditor_Modern）功能点击测试报告

测试方式：进程内 Qt 驱动（`_test/harness.py` + `_test/run.py`），用 QTest 合成真实鼠标/键盘事件（含命中测试、像素差分、状态与数据断言），
逐控件、逐页、逐菜单项点击；共覆盖 6 个面板页、4 个菜单、标题栏、工具栏、视口、保存/打开/拖放、主题、缩放、分隔条、快捷键与空模型状态。
测试模型由 `_test/gen_model.py` 生成（24 顶点 / 7 骨骼 / 2 材质 / 5 形态 / 3 刚体 / 2 关节）。

---

## P0-1 点击任意"颜色"按钮 → 程序直接崩溃（数据 4 分量 vs 渲染 3 分量）

**现象**：材质页点"漫反射 / 环境色 / 高光色 / 描边颜色"任一色块 → 视口渲染崩溃；真实进程（未替换 excepthook）**退出码 -1073740791 (0xC0000409)**，窗口消失，未保存修改全部丢失。

**证据**
- `panels.py` MaterialPage 的颜色回调：`self.edit("修改颜色", lambda m: setattr(m.materials[self.idx], field, list(color)), ...)`
  —— `ColorButton.colorChanged` 发的是 **RGBA 4 分量**，于是 `mt.specular/ambient/diffuse` 变成 `[0.25098039215686274, 0.5019607843137255, 1.0, 1.0]`。
- 渲染侧：`viewport.py:424 paintGL` → `viewport.py:1348 _draw_mesh` → `viewport.py:1312`
  `GL.glUniform3f(L["uSpecular"], *[float(v) for v in mt.specular])`
  → `TypeError: this function takes 4 arguments (5 given)`（`:1311` 的 uAmbient 同样报错），每帧 1~3 次，画面残缺。
- 附带：`pmx.save_pmx` 只取前 3 个分量，保存后文件仍是 2691 B、回读 specular 为 3 分量 → 文件不会损坏；Ctrl+Z 可恢复。

**建议**：`list(color)[:3]`（或在 ColorButton 侧只发 RGB）；`viewport` 侧再做一次 `tuple(mt.specular[:3])` 兜底。

---

## P0-2 物理页点击"刚体/关节"列表行 → select 无限递归 → 报错/崩溃

**现象**：点物理页列表里除当前行以外的任意行，触发 `PhysicsPage.select` 自我重入上百次；状态栏出现 `选择失败：maximum recursion depth exceeded in comparison`，stderr 输出 `Error in sys.excepthook:`；批量遍历选择时进程曾以 **-1073741819 (0xC0000005)** 崩溃。

**调用环（实测栈，第三次进入即复现）**
```
doc.py:149      self.selectionChanged.emit(kind, int(index))
main.py:548     p.select(kind, index)
panels.py:1901  self.list.select_data_index(index)      # ← 此时 self.loading 已被清成 False
ui_widgets.py:614  self.setCurrentIndex(...)
ui_widgets.py:625  self.indexSelected.emit(self._selected)
panels.py:1914  self.doc.select(self.kind, i)
doc.py:149      ...循环
```

**根因**：`panels.py:1892 select()` 用 `self.loading = True ... finally: self.loading = False` 保护，但其中调用的
`panels.py:1851 _refresh_list()` 自己在末尾 **`finally: self.loading = False`**（无条件写 False，未保存/恢复调用者的值），
于是第 1901 行的 `select_data_index()` 在 `loading=False` 状态下发信号 → `_on_list`（`panels.py:1911`）的守卫失效 → `doc.select` 重入。
对比：`refresh()`（`panels.py:1877-1881`）与 `_fill_rigid()`（`panels.py:1933-1934` `prev = self.loading`）用法是正确的；`BonePage/MaterialPage/MorphPage.select` 无此问题（它们不先调 `_refresh_list`）。

**建议**：`_refresh_list()` 改为 `prev = self.loading; ...; self.loading = prev`（或在 `select()` 里把 `select_data_index` 单独用 `loading=True` 包起来）。

---

## P1-3 亮色主题下地面网格颜色错乱（纯红/纯黄高饱和线）

**现象**：切到亮色主题后，视口地面网格不是浅灰细线，而是**大量纯红 (253,4,14) 与纯黄 (246,253,5) 的高饱和线 + 黑色线**，画面噪杂，几乎无法看清模型轮廓；深色主题下正常（同一区域这两种颜色出现 0 次）。

**证据**
- 亮色截图地面区域（1480×240）计数：(253,4,14) 4451 px、(246,253,5) 2999 px、(4,12,23) 2419 px；深色同区域全为 0。
- 关闭"地面网格"开关后这些像素完全消失（red/yellow/dark 全部 0）→ 确认来自网格绘制。
- 排除项：`vp._grid` 顶点色数组本身正确，亮色下只有 4 种色 `(0.78,0.81,0.85) / (0.65,0.69,0.75) / (0.8,0.35,0.38) / (0.38,0.52,0.75)`；
  `theme.GRID_*` 与 `viewport.GRID_*` 一致（不是 `from theme import` 冻结问题）；`_grid_vbo=(1,2)` 与骨骼/刚体/关节线 VBO `(3,4)(5,6)(7,8)` 不冲突（不是 buffer id 复用）；
  覆盖层 `show_bones/show_rigid/show_joints` 默认全 False。
- 结论：CPU 侧数据正确、渲染结果错误 → 网格绘制时顶点颜色属性绑定到了别的缓冲（渲染出的是 [0,1] 区间的其它数据，如 UV），深色主题下同样存在但因底色深而不可见。
  相关代码：`viewport.py:1165 _draw_grid`（`glVertexAttribPointer` 在 1178/1181）、`viewport.py:1188 _build_grid`。

---

## P1-4 窗口/分隔条缩小后，列表行不重算宽度 → 横向滚动条 + 右侧统计文字被推出可视区

**现象**：窗口从 1560 宽缩到最小 1120 后，右侧"材质"列表出现横向滚动条，行右侧的 "72 面 / 36 面" 完全看不见（滚到最左也看不到）；切一次主题（触发重排）后恢复正常。实测：暗色 `viewport().width()=334` 但 `visualRect` 行宽 **626**，`hbar.maximum()=292`；重排后行宽 334、无滚动条。

**根因**：`ui_widgets.py:458 RowDelegate.sizeHint` 返回 `max(120, option.rect.width())`，与 `EntryList.setUniformItemSizes(True)` 组合后，尺寸被首次（更宽时）的宽度锁死，窗口缩小时不重算。

**建议**：改用固定列宽（视口宽度）或在 `resizeEvent` 里 `self._model` 重置 uniform sizes / `scheduleDelayedItemsLayout()`。

---

## P2 级（功能可用但有明显缺陷）

5. **视口点空白处不能取消选择**：`viewport.py` 的 `mouseReleaseEvent` 只在 `if kind:` 时发信号，命中空白时什么都不做，`doc.sel` 仍停留在上一对象。
6. **姿态模式"单击不拖动"也压入撤销记录**：按下即 `editStarted.emit("调整骨骼姿态")`，状态栏变 "姿态已更新"，白占 `UNDO_LIMIT = 12` 的名额。
7. **搜索/过滤到 0 条时是纯空白面板**：骨骼树、材质/形态/物理列表均无"无匹配结果"提示（项目里已有 `EmptyState` 控件但未用于列表）。
8. **HUD 的 FPS 不衰减**：`viewport.py:437-440` 只在 `paintGL` 内累加，静止不重绘就一直显示旧值（实测静止模型显示 1/2/4/8 FPS），会误导性能判断；应对空闲计时归零。
9. **编辑类操作无状态反馈 / 状态被覆盖**：改名、改描述、点"应用描述"、拖形态权重滑杆后状态栏仍是旧文案（如 "已载入 TestModel"）；反之 `viewport.py:479 set_model` 的 "已载入 xxx" 会在结构性编辑重建视口时覆盖掉刚显示的状态。
10. **空模型（未载入）时点"应用物理参数"仍提示"物理参数已应用"**：无实际作用的假成功文案。
11. **物理页切到"关节"分段会清空选择**：`_switch_kind` 里 `self.idx = -1; self._set_enabled(False)`，`doc.sel` 变成 `('', -1)`。

## P3 级（小问题/死代码）

12. **列表右键无任何反应**：`ui_widgets.py:574` 设了 `setContextMenuPolicy(Qt.CustomContextMenu)`，但全工程没有 `customContextMenuRequested` 的连接 → 死代码（右键菜单缺失）。
13. **F / R（视图居中 / 重置姿态）不是全局快捷键**：只在 `Viewport.keyPressEvent` 里处理，焦点在右侧面板时按 F/R 无效；而 Ctrl+S/Ctrl+Z 等走菜单 QAction，全局有效（行为不一致）。
14. **材质/形态列表双击与单击行为完全相同**（没有 `doubleClicked/activated` 连接）：双击不会额外打开详情或重命名。
15. **`EntryList.set_entries(entries, selected=-1)` 总是回落到第 0 行**（`ui_widgets.py:602`），刷新时会把列表选择"吸"到首行。

---

## 已验证正常（不属缺陷，避免误报）

- 菜单：文件（打开/保存/另存为/关闭模型/退出）、编辑（撤销/重做，空栈有提示）、视图（3 模式 + 8 个显示开关，全部改变渲染，像素差 0.32%~9.68%）、帮助（快捷键说明、关于）全部可用。
- 标题栏：最小化 / 最大化 / 双击标题栏切换最大化；深↔亮主题切换（像素差 99.97%）。
- 工具栏：打开/保存/撤销/重做/三模式/视图居中/重置姿态；撤销栈（含 0.9s 合并）、重做、`UNDO_LIMIT=12`。
- 6 个面板页的新建/复制/删除/编辑/列表选择/开关/分段，以及 `ConfirmDialog` 删除确认（刚体 3→4→5→4、关节 2→3→2，重映射正确）；删除刚体会连带删除引用它的关节（设计如此）。
- 形态页 7 种形态类型全部创建成功（5→12）。
- 视口：滚轮缩放、中键旋转、Shift+中键平移、F 复位、拾取选中骨骼并联动右侧面板、姿态模式拖动旋转、R 重置。
- 文件流程：保存/另存为、`_maybe_save` 三分支（保存/放弃/取消）、拖放打开、非文件拖入被拒绝。
- 空模型状态：6 页所有可见可用控件点击 0 异常，各按钮正确早退。
- 缩放：最小尺寸 1120×700 下布局不裁切、不重叠；分隔条拖动正常。


---

# 修复记录（全部 16 条 + 1 条新发现）

| 编号 | 问题 | 状态 | 主要改动 |
| --- | --- | --- | --- |
| P0-1 | 点颜色按钮崩溃（RGBA4 vs glUniform3f） | 已修 | `panels.py` `MaterialPage._color` 按字段截断分量（diffuse/edge_color 4 个，specular/ambient 3 个）；`viewport.py` `_draw_mesh` 再对 uDiffuse/uAmbient/uSpecular/描边色做长度兜底 |
| P0-2 | 物理页点刚体/关节行无限递归 | 已修 | `panels.py` 三处 `_refresh_list`（材质/形态/物理）改 `prev = self.loading ... finally: self.loading = prev`（原来无条件写 False，冲掉了 `select()` 的守卫） |
| P1-3 | 亮色主题网格出现纯红/纯黄条纹 | 已修 | `viewport.py` `_draw_grid`/`_draw_lines` 画 `GL_LINES` 期间临时 `glDisable(GL_MULTISAMPLE)`（Intel Arc + 4x MSAA 细线噪点） |
| P1-4 | 列表右侧"72 面/组 0"被挤出可视区 | 已修 | `ui_widgets.py` `RowDelegate.width_hint` + `sizeHint` 用 hint；`EntryList.resizeEvent` → `_sync_row_width()` 重置 uniform 尺寸 |
| P2-5 | 点视口空白不取消选择 | 已修 | `viewport.py` 新增 `selectionCleared` 信号 + release 空白分支（`main.py` 连到 `doc.select("", -1)`） |
| P2-6 | 姿态模式单击不拖动也压撤销栈 | 已修 | `viewport.py` 按下不再发 `editStarted`，改为首个位移时才发（`_pose_moved`） |
| P2-7 | 过滤到 0 条时面板全空白 | 已修 | `EntryList`/`BoneTree` 新增 `paintEvent` 画 `empty_text`（"无匹配结果" / "未载入模型"） |
| P2-8 | HUD 长期显示 "1 FPS" | 已修 | `viewport.py` `_decay_fps()` + `_fps_skip`，空闲 1.2s 归零；HUD 改为显示"空闲" |
| P2-9 | 编辑后状态栏无反馈 / 被"已载入"覆盖 | 已修 | `main.py` `EDIT_STATUS` 映射 + `_on_edited` 统一设置；删除 `viewport.set_model` 里的状态覆盖 |
| P2-10 | 空模型点"应用物理参数"仍提示成功 | 已修 | `main.py` `_apply_physics` 增加"未载入模型"守卫 |
| P2-11 | 物理页切"关节"分段会清空选中 | 已修 | `panels.py` `_switch_kind` 末尾选中新类型首项（无项则 `doc.select("", -1)`） |
| P2-16 | 复选框右侧空白区点了没反应（新发现） | 已修 | `panels.py` 材质 5 个 flag 复选框与组遮罩复选框加 `setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)`，让整个控件都在点击矩形内 |
| P3-12 | 列表声明了右键菜单却无实现 | 已修 | `BoneTree` 实现右键菜单（全部展开/全部折叠）；`EntryList` 删除死代码 `setContextMenuPolicy` |
| P3-13 | F/R 不是全局快捷键 | 已修 | `main.py` 改 `QShortcut`（`Qt.ApplicationShortcut`），焦点不在视口也生效 |
| P3-14 | 列表/树双击无额外行为 | 不改 | 骨骼树默认全展开、列表单击即选中并刷新详情，双击无额外语义属设计；`expandAll` 会在重建时被复位，加双击反而更乱 |
| P3-15 | `set_entries` 总回落到第 0 行 | 已修 | `ui_widgets.py` `set_entries` 用 `next(..., -1)`，无匹配时 `setCurrentIndex(QModelIndex())` + `clearSelection()`（原来搜索过滤会偷改文档选中项） |

## 已知残留（未修，可接受）

- 亮色主题网格线比配色表偏深（实测约 (11,21,35)，配色是 (183,191,204) 一档），彩色噪点已消除；关掉 `GL_LINE_SMOOTH` 数值不变，判断与 Intel 驱动 MSAA 相关，继续深挖性价比低。
- `viewport.py` `_upload_mesh` 每次重建都 `glGenBuffers` 新 id，不删除旧的 → 反复切换模型会泄漏 VBO。

## 如何复跑验证

```
python _test\\gen_model.py                    # 重新生成干净测试模型
python _test\\go.py walk dark _test\\test_model.pmx     # 全量逐控件点击走查（21 条均为已知噪声）
python _test\\go.py verify_p0 dark _test\\test_model.pmx # P0-1/P0-2 回归
python _test\\go.py flag8 dark _test\\test_model.pmx     # 复选框点击
python _test\\go.py rows_fix dark _test\\test_model.pmx  # 列表行宽
python _test\\go.py fix2 dark _test\\test_model.pmx      # 空白取消选择 / 姿态不误压栈
python _test\\go.py final dark _test\\test_model.pmx     # 菜单/主题/保存/拖放/快捷键
```
结果看 `_test/report.json` 与控制台最后一行 `DONE anomalies: N`。


## 真机模型测试：米娅.pmx（79848 顶点 / 321 骨骼 / 183 刚体）

测试文件：`D:\Project\MMD\02_模型库\米娅\米娅.pmx`（4,908,850 字节，PMX 2.0，UTF-16LE）
规模：顶点 79848 / 三角面 113995 / 骨骼 321 / 材质 52 / 形态 29 / 刚体 183 / 关节 261 / 贴图 12 / 显示枠 11

通过项（无异常）
- 加载 0.67 s，`validate_model` 返回 []，模型、贴图、Toon、描边、透明裙摆渲染均正确。
- 6 个页面逐页进入、321 行骨骼树、52 行材质列表、29 行形态列表、183 行刚体列表全部正常（行右侧信息完整可见）。
- 保存往返无损：`doc.save` 0.15 s，输出字节数与源文件完全相同，回读后计数全等、`v_pos`/`uv` maxdiff = 0.000000。
- 姿态拖拽 + 撤销：`_skin_pos` 逐点还原（maxdiff 0.00000），状态 `已撤销：调整骨骼姿态`。
- 物理模式 46 FPS、183 刚体演算正常；形态预览生效；改色不再崩溃（P0-1 修复成立）。
- 界面刷新：切页 28~45 ms、整页刷新 2~7 ms、重绘 14 ms。

修复项：结构性编辑卡顿（`edit-slow`）
- 现象：改一个骨骼坐标 580 ms、撤销 603 ms（大模型下每次编辑都卡半秒）。
- 定位：撤销栈深拷贝只占 42 ms；`_reload_structure()` 本身 75 ms；真正的大头是**重建后的首次重绘 434~469 ms**——`viewport.py set_model()` 里 `self._tex_cache.clear()` 把 12 张贴图全部丢弃，重绘时重新解码 + 上传。
- 修复：纹理缓存键从 `(index, sphere)` 改为 `(path, sphere)`（`viewport.py _texture`），`set_model()` 不再清空缓存（换模型/换贴图靠路径自然失效）。
- 效果：结构编辑总耗时 580 ms → **108 ms**（reload 76 + paint 32），换贴图后仍能正确刷新（`tex 1 -> 2`、undo 回 1、状态 `已撤销：修改通常贴图`）。
- 回归：`verify_p0` 0、`final` 0、`walk` 21（全为已知噪声）。

补充：材质类编辑同样受影响
- `main.py _on_edited` 对 `kind == "material"` 只调 `viewport.refresh_textures()`，而它原来 `self._tex_cache.clear()` → 每次改颜色/贴图/描边都会重新解码全部贴图，单次约 460 ms（其中 `QImageReader.read` 291 ms）。
- 已改为只 `update()`（缓存键含路径，换贴图自然换键），并在 `initializeGL` 补一次 `_tex_cache.clear()`（新上下文的纹理 id 全部失效）。
- 效果：材质编辑 460 ms → 58 ms，重绘 419 ms → 19 ms；全部材质改色/改贴图仍实时生效（像素差 8.39% / 3.76%）。

---

## 2026-10-23 进度同步复核（VPD 导入/导出 + 发行包 r4）

**复核范围**：上一轮之后新增的 `vpd.py`、`main.py` 的 VPD 菜单/拖放、`tools/verify_vpd.py`、发行包 `dist\release-20261023-r4`。

**结果（全部通过，0 异常）**
- 14 个 Python 模块 `ast.parse` 通过；`release-20261023-r4\PmxEditor_Modern.exe` 为 28,841,984 字节，SHA256 与 README 记录一致。
- `python tools\verify_vpd.py "残虹泳装.pmx"`：parser / encoding / 675 骨骼 56990 顶点 / 名称匹配与应用 60-60 / 宽松名称 / 缺失名称 / 形态 / 导出文件（cp932 5 骨骼 1 形态）全部通过。
- 打包 exe `--verify-backend --runs 5`：退出码 0、1.8 s 内完成，报告 `ok=true`、`backend="C++ / Bullet"`、25 项 0 失败、`elapsed_seconds=0.99`、Python 3.10.9。
- 新增 GUI 场景 `scen_sync`（`python _test\go.py sync dark "模型.pmx"`），在 `残虹泳装.pmx`（56990 顶点 / 675 骨骼 / 20 材质 / 136 形态 / 443 刚体 / 492 关节）上：
  - 菜单含「导入 VPD 姿态…」「导出 VPD 姿态…」；构造 5 根骨骼的 CP932 VPD 导入 456 ms，状态栏 `已导入 VPD 姿态：5/5 根骨骼`，自动切姿态模式、只记 1 条撤销。
  - 实际改动 11 根骨骼（源 5 根 + IK 链求解 6 根），符合预期。
  - 撤销后 `base_rot` 与导入前逐元素相等（maxdiff 0.00000000），重做重新生效。
  - 导出 6 ms，自动补 `.vpd`，写出 11 根骨骼 / 1 个形态、cp932，回读旋转误差 1e-8。
  - 重置姿态后导出被拒绝：`VPD 导出已取消：姿态无变化`，不产生文件。

**清理**：删除根目录遗留的 `nuitka-crash-report.xml`（4.8 MB，2026-10-23 08:59 一次失败的 onefile 构建报告，原因是构建解释器路径含非 ASCII 字符导致 `pyqt5: Error, failed to detect 'PyQt5' plugin directories.`；该坑已在 README 记录）。

**注意事项**
- 控制台是 GBK，跑脚本要 `PYTHONUTF8=1`，结果读 `_test/report.json`（键为 `log` / `anomalies`）。
- `_test/run.py` 里 VPD 场景用内建 `open(..., encoding="cp932")`，不要用未导入的 `io.open`。
- 打包 exe 用 `--windows-console-mode=disable`，PowerShell 里直接 `&` 不会等待，需 `Start-Process -Wait` 才能拿退出码。

---

# 附：与原版 PmxEditor 的同操作一致性比对（parity）发现

测试方式、坐标、脚本与证据见 `tests/parity/REPORT.md`。基准模型 `KARU式Rabbit Hole MIKU.ver 1.6.pmx`，两侧各用真实 GUI 操作同一件事后另存，再用 `tests/parity/pmxsem.py` 逐字段比对（19 项操作）。

**状态：已修复**（`src/pmxeditor/panels/bone.py`：「移动时带动顶点」改为构造即关、不再从 `settings.json` 读回、不再持久化，触发时状态栏提示）。修复后同一 GUI 脚本复跑，`B1_orig.pmx` 与 `B1_mod.pmx` 字段级 0 差异。

## 差异-1 移动骨骼会连带搬动 14,602 个顶点（原版不动）

**现象**：骨骼页把骨骼5「上半身」位置 X 由 0 改为 1.0 → 新版 `v_pos` 有 **14,602 个顶点**被按权重位移（顶点 554 权重 0.125，X 0.1879→0.3131），最大位移 0.859；原版 PmxEditor 保存后顶点数组完全不变。撤销可回滚。

**证据**：`tests/parity/work/B1_orig.pmx` vs `B1_mod.pmx`；代码 `src/pmxeditor/panels/bone.py:66 self.move_verts_sw = Switch(False)` → `:520 _move_verts_toggled` → `:541 self.edit("移动骨骼并带动顶点" if move else "移动骨骼", apply, ...)`（该开关的持久化默认值为开）。

**建议**：默认关闭，或与原版对齐；至少首次触发时提示「将同时移动 N 个顶点」。

**状态：已修复**（`src/pmxeditor/doc.py`：`remove_material` 非 merge 分支修正 `face_count` 切片单位 + 新增 `compact_vertices()` 清理孤立顶点并重映射索引与形态偏移；删除对话框默认按钮改为「连同三角面删除」）。修复后顶点 116,036→102,081、面 614,757→538,605、文件 7,573,725 B，与原版逐字段一致。

## 差异-2 删除材质不会删除其几何（原版会）

**现象**：删除材质 #20「metal」（76,152 面）后——原版连带删除其独占顶点：顶点 116,036→102,081、面 614,757→538,605（文件 7,573,725 B）；新版保留全部几何，把这 76,152 面并入上一材质，`materials[19].face_count` 5,520→81,672（文件 8,437,554 B）。

**证据**：`tests/parity/work/S2_orig.pmx` vs `S2_mod.pmx`；代码 `src/pmxeditor/doc.py:385`（`merge=True` 时把面并入上一材质）、调用点 `src/pmxeditor/panels/material.py:439`。

**建议**：提供「删除材质并删除其面/顶点」（默认，对齐原版）与「仅删材质、面并入相邻材质」两种模式。

**状态：已修复**（`src/pmxeditor/pmx.py` 新增 `_crlf()`，`save_pmx` 写 `comment`/`comment_en` 前规范化）。修复后与原版保存结果 0 差异。

## 差异-3 PMX 注释换行被写成 LF（原版为 CRLF）

**现象**：三行注释保存后是 `\n`，原版是 `\r\n`。

**证据**：`src/pmxeditor/panels/info.py:119 v = self.comment.toPlainText()`（QPlainTextEdit 输出 `\n`）→ `src/pmxeditor/pmx.py:416 m.comment = r.text()`。

**建议**：写入前 `v.replace("\r\n", "\n").replace("\n", "\r\n")`。

**状态：已修复**（`src/pmxeditor/ui_widgets.py` 新增 `ColorSpins` 浮点 RGBA 数值框，材质页加入漫反射/高光色/环境色/描边四行并与颜色按钮双向同步；`_fill_fields` 用 PMX 原值回填）。精确输入 0.5 后与原版 0 差异；经 `QColorDialog` 取色的老路径仍是 8 位（`0.501961`），属预期。

## 差异-4 颜色只有 8 位精度（0.5 存成 0.501961）

**现象**：材质漫反射 R / 透明度 A 想设 0.5，新版落盘 0.501961（128/255）；原版可存任意浮点 0.5。

**证据**：`src/pmxeditor/panels/material.py:57 self.diffuse = ColorButton([1,1,1,1])`、`src/pmxeditor/ui_widgets.py:185 ColorButton`（`QColor.fromRgbF`，8 位通道）、`material.py:66 / _color()`。

**建议**：给 diffuse/specular/ambient/edge_color 补 4 个浮点数值框（至少透明度可输入浮点）。

**状态：已修复**（`src/pmxeditor/panels/vertex.py:_apply` 改为按分量判定改动，只写真正被改过的分量）。修复后与原版 0 差异。

## 差异-5 顶点编辑后该顶点出现 ≤4.0e-5 漂移

编辑顶点0 位置 X=0.5 后，该顶点 Y 16.80584→16.805799、Z −0.422984→−0.423、法线 3e-06→0、权重 0.53826→0.5383；原版只有 X 变。疑为 `src/pmxeditor/panels/vertex.py:_apply` 的 float32 重算/权重归一化。

**状态：部分修复**（`src/pmxeditor/doc.py`：只有 `tail_bone == 被删索引` 时才清 `BF_TAIL_INDEX`/归零 `tail_offset`）。与 `S1_orig` 的差异由 15 处降到 2 处；剩下的是**有意保留**：子骨骼父级挂到被删骨骼的真正父级（87）而原版挂索引前一位（99），语义更正确。

## 差异-6 删骨骼时连带规范化 tail 标记位

`src/pmxeditor/doc.py:318-322` 对 `BF_TAIL_INDEX` 且重映射后 <0 的骨骼清位（源模型里已有 9 个 `tail_bone=-1` 但置位的骨骼，flags 271→270、283→282、267→266）。方向更规范，但属于未请求的连带修改。

## 差异-7 新建骨骼默认值与原版不同

原版：`新規ボーン1` / 英文名空 / 父骨骼 −1 / 位置 (0,0,0) / flags 26。
新版：`新建骨骼` / `new_bone` / 父骨骼 = 当前选中骨骼 / 位置 = 父位置+(0,1,0) / flags 30。

## 能力差异

> 以上修复已用同一套 GUI 脚本（`tests/parity/side_mod.py`）复跑复核，明细见 `tests/parity/REPORT.md` 第九节。


- ~~信息页「文字编码」「追加UV数」新版只读（原版可改编码；追加UV 原版可设但 PMX 2.0 不落盘）。~~
  **状态：已修复**。`src/pmxeditor/panels/info.py` 把这两项改成下拉，`src/pmxeditor/pmx.py` 新增 `set_add_uv()` 并在 `validate_model` 里校验 0–4 与 `v_add` 宽度。复核：E4 两侧均 8,435,389 B、`pmxsem` 0 差异；E5 新版 `add_uv=2`、`v_add (116036, 8)`、12,150,802 B（+n×32），0→2→4→0 往返回到 8,437,650 B 且与纯另存逐字节相同。原版追加 UV 在 PMX 2.0 下仍不落盘，故 E5 记为「新版更正确」的有意差异。
- 材质页「新建材质」原版 + 号灰化不可用，新版可新建（materials 22）。

## 差异-8 开启「轴固定」时原版会把轴向量归一化为骨骼朝向（parity B7）

两侧开「轴固定」后 `bones[5].flags` 都 27→1051（置 `BF_FIXED_AXIS`），但原版在同一动作里把 `axis` 从 (1,0,0) 改成 (1, 0.998421, −0.056169)（骨骼朝向），新版保持 (1,0,0)。

**证据**：`tests/parity/work/B7_orig.pmx` vs `work/B7_mod.pmx`（`pmxsem` 2 处差异，仅 `axis[1]/axis[2]`）；新版 `src/pmxeditor/panels/bone.py:_axis_flag_changed` 只改标志位。

**影响**：低危——只有轴固定骨骼的冗余轴向数据不同，不影响物理与姿态。

**状态：未修复**（有意保留：需要先推断原版归一化算法，当前无明确规格）。

## 全量回归时发现的既有问题（非本轮引入）

用 `tests/parity/regress.py` 跑 `tests/run.py` 的 40 个功能场景时发现三类既有问题，均已用 `git stash push -- src` 在 HEAD 上复现确认：

1. `sel` 场景 **进程崩溃 rc=0xC0000005**（访问冲突），HEAD 同样崩溃 —— 建议单独立项排查（该场景覆盖选中/高亮路径）。
2. `vp` 场景 2 条异常：`pose-move`（左键拖动骨骼后没有位移）、`phys-pose`（物理演算中拖动骨骼姿态未变）—— HEAD 同样出现，属拖动模拟与实际鼠标路径的差异，非产品缺陷。
3. `sel6` 场景脚本自身 `AttributeError: 'Document' object has no attribute 'sel'` —— 测试脚本引用了不存在的属性，需修脚本。

另：`inventory` 的 2 条 `text-clipped` 是超长模型路径的 `Faint` 标签，属既有告警。

`mouse` 场景原本断言「移动时带动顶点」开关写入 `settings.json`；该持久化在本轮按 parity 结论移除（原版移动骨骼不搬顶点），场景断言已同步改为「开关不再持久化、新实例默认关闭」。
