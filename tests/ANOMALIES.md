# PMX 编辑器（PmxEditor_Modern）功能点击测试与 parity 差异台账

测试方式：进程内 Qt 驱动（`tests/harness.py` + `tests/run.py`），用 QTest 合成真实鼠标/键盘事件（含命中测试、像素差分、状态与数据断言），
逐控件、逐页、逐菜单项点击；共覆盖 8 个检查器页、4 个菜单、标题栏、工具栏、视口、保存/打开/拖放、主题、缩放、分隔条、快捷键与空模型状态（早期点击审计只遍历前 6 页，表示枠/顶点页由 `frame` / `vertex_edit` 场景补充）。
测试模型由 `tests/gen_model.py` 生成（24 顶点 / 7 骨骼 / 2 材质 / 5 形态 / 3 刚体 / 2 关节）。

> 说明：本文跨多轮记录。P0/P2/P3 条目里的 `panels.py` / `main.py` / `viewport.py` 是包拆分前的单文件布局，现分别对应 `src/pmxeditor/panels/`、`src/pmxeditor/app.py`、`src/pmxeditor/viewport/core.py`；文中行号是当时的快照，只作定位线索，代码位置以函数名为准。

---

## P0-1 点击任意"颜色"按钮 → 程序直接崩溃（数据 4 分量 vs 渲染 3 分量）— ✅ 已修复

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

## P0-2 物理页点击"刚体/关节"列表行 → select 无限递归 → 报错/崩溃 — ✅ 已修复

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

## P0-3 物理页点刚体/关节列表行 → 进程崩溃 rc=0xC0000005 — ✅ 已修复

**现象**：`sel` 场景选中全部刚体后真实点击列表行，进程以 0xC0000005 退出；`PYTHONFAULTHANDLER=1` 抓到
`tests/run.py:1081 in scen_sel`（读 `mdl.data(idx)`）。时崩时不崩，取决于堆复用。

**根因**：`PhysicsPage.select()` 每次选中都调用 `_refresh_list()` → `EntryList.set_entries()` →
`QStandardItemModel.clear()`，把列表条目全部删除重建。点击行时这次重建发生在 `QItemSelectionModel.selectionChanged`
的槽里，场景在点击前取得的 `QModelIndex` 于点击后再 `data()` 就解引用了已释放的 `QStandardItem` → 访问冲突。
最小复现：选满 82 个刚体后点击首行，再读旧索引即 100% 崩溃。

**修复**：`panels/physics.py` 记录列表当前展示的类型 `_list_kind`，`select()` 只在类型变化时重建列表；
`tests/run.py` `scen_sel` 改为点击前取行文本。顺带修正 `scen_sel6` 引用了不存在的 `doc.sel`。

**验证**：`sel` rc=0、0 异常；`sel2 / sel6 / click_rigid / verify_p0` 均 0 异常。

---

## P1-3 亮色主题下地面网格颜色错乱（纯红/纯黄高饱和线）— ✅ 已修复

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

## P1-4 窗口/分隔条缩小后，列表行不重算宽度 → 横向滚动条 + 右侧统计文字被推出可视区 — ✅ 已修复

**现象**：窗口从 1560 宽缩到最小 1120 后，右侧"材质"列表出现横向滚动条，行右侧的 "72 面 / 36 面" 完全看不见（滚到最左也看不到）；切一次主题（触发重排）后恢复正常。实测：暗色 `viewport().width()=334` 但 `visualRect` 行宽 **626**，`hbar.maximum()=292`；重排后行宽 334、无滚动条。

**根因**：`ui_widgets.py:458 RowDelegate.sizeHint` 返回 `max(120, option.rect.width())`，与 `EntryList.setUniformItemSizes(True)` 组合后，尺寸被首次（更宽时）的宽度锁死，窗口缩小时不重算。

**建议**：改用固定列宽（视口宽度）或在 `resizeEvent` 里 `self._model` 重置 uniform sizes / `scheduleDelayedItemsLayout()`。

---

## P1-5 复制材质只复制材质行、不复制面索引 → 落盘材质面数之和大于索引总数 — ✅ 已修复

**现象**：材质页「复制材质」后另存，材质数 +1，但新材质的 `face_count` 沿用源材质，而扁平索引列表没有增加对应三角面。以基准模型复制材质0 为例：
`sum(face_count)=733161`、`indices=614757`，差 118404（=材质0 的面索引数）。原版 PmxEditor 的 `IPXMaterial.Clone()` 会连 `Faces` 一起复制，落盘后索引同步增加。

**根因**：`doc.py duplicate_material` 只 `deepcopy` 了 `Material`（含 `face_count`），没有把源材质的索引切片追加到 `model.indices`。

**修复**：复制时先按前面材质的 `face_count` 求和定位源材质索引区间，把该区间（`face_count` 个索引）追加到 `indices` 末尾并同步新材质的计数；新材质排在材质列表末尾，其面区间正好落在追加的数据上。

**验证**：`N4_cx`（原版 `.cx` Clone）vs `N4_mod`（新版复制）**0 差异**；材质 21→22、面 204919→244387、文件同为 8,911,392 B；重载后 `sum(face_count)==indices.size`、`validate_model` 无告警；复制材质 0/1/5 均满足一致性。

---

## P2 级（功能可用但有明显缺陷 — 均已修复）

5. **视口点空白处不能取消选择**：`viewport.py` 的 `mouseReleaseEvent` 只在 `if kind:` 时发信号，命中空白时什么都不做，`doc.sel_kind/sel_index` 仍停留在上一对象。
6. **姿态编辑"单击不拖动"也压入撤销记录**：按下即 `editStarted.emit("调整骨骼姿态")`，状态栏变 "姿态已更新"，白占 `UNDO_LIMIT = 12` 的名额。
7. **搜索/过滤到 0 条时是纯空白面板**：骨骼树、材质/形态/物理列表均无"无匹配结果"提示（项目里已有 `EmptyState` 控件但未用于列表）。
8. **HUD 的 FPS 不衰减**：`viewport.py:437-440` 只在 `paintGL` 内累加，静止不重绘就一直显示旧值（实测静止模型显示 1/2/4/8 FPS），会误导性能判断；应对空闲计时归零。
9. **编辑类操作无状态反馈 / 状态被覆盖**：改名、改描述、点"应用描述"、拖形态权重滑杆后状态栏仍是旧文案（如 "已载入 TestModel"）；反之 `viewport.py:479 set_model` 的 "已载入 xxx" 会在结构性编辑重建视口时覆盖掉刚显示的状态。
10. **空模型（未载入）时点"应用物理参数"仍提示"物理参数已应用"**：无实际作用的假成功文案。
11. **物理页切到"关节"分段会清空选择**：`_switch_kind` 里 `self.idx = -1; self._set_enabled(False)`，`doc.sel_kind/sel_index` 变成 `('', -1)`。

## P3 级（小问题/死代码 — 除 P3-14 外均已修复）

12. **列表右键无任何反应**：`ui_widgets.py:574` 设了 `setContextMenuPolicy(Qt.CustomContextMenu)`，但全工程没有 `customContextMenuRequested` 的连接 → 死代码（右键菜单缺失）。
13. **F / R（视图居中 / 重置姿态）不是全局快捷键**：只在 `Viewport.keyPressEvent` 里处理，焦点在右侧面板时按 F/R 无效；而 Ctrl+S/Ctrl+Z 等走菜单 QAction，全局有效（行为不一致）。
14. **材质/形态列表双击与单击行为完全相同**（没有 `doubleClicked/activated` 连接）：双击不会额外打开详情或重命名。
15. **`EntryList.set_entries(entries, selected=-1)` 总是回落到第 0 行**（`ui_widgets.py:602`），刷新时会把列表选择"吸"到首行。

---

## 已验证正常（不属缺陷，避免误报）

- 菜单：文件（打开/保存/另存为/关闭模型/退出）、编辑（撤销/重做，空栈有提示）、视图（物理演算开关 + 8 个显示开关，全部改变渲染，像素差 0.32%~9.68%）、帮助（快捷键说明、关于）全部可用。
- 标题栏：最小化 / 最大化 / 双击标题栏切换最大化；深↔亮主题切换（像素差 99.97%）。
- 工具栏：打开/保存/撤销/重做/物理演算开关/视图居中/重置姿态；撤销栈（含 0.9s 合并）、重做、`UNDO_LIMIT=12`。
- 十个检查器页的新建/复制/删除/编辑/列表选择/开关/分段（冒烟清单覆盖前六页，表示枠/顶点/面/柔体页由 `frame` / `vertex_edit` / `face_edit` / `softbody_edit` 场景覆盖），以及 `ConfirmDialog` 删除确认（刚体 3→4→5→4、关节 2→3→2，重映射正确）；删除刚体会连带删除引用它的关节（设计如此）。复制材质的落盘完整性见 P1-5（已修）。
- 形态页 7 种形态类型全部创建成功（5→12）。
- 视口：滚轮缩放、中键旋转、Shift+中键平移、F 复位、拾取选中骨骼并联动右侧面板、左键拖动位移 / 右键拖动旋转、R 重置。
- 文件流程：保存/另存为、`_maybe_save` 三分支（保存/放弃/取消）、拖放打开、非文件拖入被拒绝。
- 空模型状态：各检查器页可见可用控件点击 0 异常，各按钮正确早退。
- 缩放：最小尺寸 1120×700 下布局不裁切、不重叠；分隔条拖动正常。


---

# 修复记录（全部 16 条 + 3 条新发现）

| 编号 | 问题 | 状态 | 主要改动 |
| --- | --- | --- | --- |
| P0-1 | 点颜色按钮崩溃（RGBA4 vs glUniform3f） | 已修 | `panels.py` `MaterialPage._color` 按字段截断分量（diffuse/edge_color 4 个，specular/ambient 3 个）；`viewport.py` `_draw_mesh` 再对 uDiffuse/uAmbient/uSpecular/描边色做长度兜底 |
| P0-2 | 物理页点刚体/关节行无限递归 | 已修 | `panels.py` 三处 `_refresh_list`（材质/形态/物理）改 `prev = self.loading ... finally: self.loading = prev`（原来无条件写 False，冲掉了 `select()` 的守卫） |
| P0-3 | 物理页点列表行后进程崩溃 rc=0xC0000005 | 已修 | `panels/physics.py` `PhysicsPage.select()` 只在 `_list_kind` 变化时 `_refresh_list()`（不再每次选中都清空重建列表）；`tests/run.py` `scen_sel` 点击前取行文本、`scen_sel6` 修正 `doc.sel` |
| P1-3 | 亮色主题网格出现纯红/纯黄条纹 | 已修 | `viewport.py` `_draw_grid`/`_draw_lines` 画 `GL_LINES` 期间临时 `glDisable(GL_MULTISAMPLE)`（Intel Arc + 4x MSAA 细线噪点） |
| P1-4 | 列表右侧"72 面/组 0"被挤出可视区 | 已修 | `ui_widgets.py` `RowDelegate.width_hint` + `sizeHint` 用 hint；`EntryList.resizeEvent` → `_sync_row_width()` 重置 uniform 尺寸 |
| P1-5 | 复制材质不复制面索引（落盘材质面数之和 > 索引总数） | 已修 | `doc.py` `duplicate_material` 追加源材质的 `face_count` 个索引到 `indices` 末尾并同步计数；`N4_cx` vs `N4_mod` 0 差异 |
| P2-5 | 点视口空白不取消选择 | 已修 | `viewport.py` 新增 `selectionCleared` 信号 + release 空白分支（`main.py` 连到 `doc.select("", -1)`） |
| P2-6 | 姿态编辑单击不拖动也压撤销栈 | 已修 | `viewport.py` 按下不再发 `editStarted`，改为首个位移时才发（`_pose_moved`） |
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

## 如何复跑验证

```
python tests\\gen_model.py                     # 重新生成干净测试模型
python tests\\go.py walk dark tests\\test_model.pmx      # 全量逐控件点击走查（噪声条数随点击顺序浮动）
python tests\\go.py verify_p0 dark tests\\test_model.pmx  # P0-1/P0-2 回归
python tests\\go.py flag8 dark tests\\test_model.pmx      # 复选框点击
python tests\\go.py rows_fix dark tests\\test_model.pmx   # 列表行宽
python tests\\go.py fix2 dark tests\\test_model.pmx       # 空白取消选择 / 姿态不误压栈
python tests\\go.py final dark tests\\test_model.pmx      # 菜单/主题/保存/拖放/快捷键
python tests\\go.py sel dark <真实模型.pmx>               # P0-3：全量选中 + 逐行点击
```
结果看 `tests/report.json` 与控制台最后一行 `DONE anomalies: N`。


## 真机模型测试：米娅.pmx（79848 顶点 / 321 骨骼 / 183 刚体）

> 本节记录于包拆分前（2026-10-23），文中的 `viewport.py` / `main.py` 现分别位于 `src/pmxeditor/viewport/core.py` 与 `src/pmxeditor/app.py`；耗时数据保留作历史基线。

测试文件：`D:\Project\MMD\02_模型库\米娅\米娅.pmx`（4,908,850 字节，PMX 2.0，UTF-16LE）
规模：顶点 79848 / 三角面 113995 / 骨骼 321 / 材质 52 / 形态 29 / 刚体 183 / 关节 261 / 贴图 12 / 显示枠 11

通过项（无异常）
- 加载 0.67 s，`validate_model` 返回 []，模型、贴图、Toon、描边、透明裙摆渲染均正确。
- 检查器页逐页进入（该轮实测覆盖前 6 页）、321 行骨骼树、52 行材质列表、29 行形态列表、183 行刚体列表全部正常（行右侧信息完整可见）。
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

# 附：与原版 PmxEditor 的同操作一致性比对（parity）发现

测试方式、坐标、脚本与证据见 `tests/parity/REPORT.md`。基准模型 `KARU式Rabbit Hole MIKU.ver 1.6.pmx`，两侧各用真实 GUI 或原版 `.cx` 通道操作同一件事后另存，再用 `tests/parity/pmxsem.py` 逐字段比对。当前共 42 项（34 一致 / 7 差异 / 1 单侧），完整总表见 `tests/parity/compare_all.md`；本节保留早期差异的根因记录。

## 差异-1 移动骨骼会连带搬动 14,602 个顶点（原版不动）

**现象**：骨骼页把骨骼5「上半身」位置 X 由 0 改为 1.0 → 新版 `v_pos` 有 **14,602 个顶点**被按权重位移（顶点 554 权重 0.125，X 0.1879→0.3131），最大位移 0.859；原版 PmxEditor 保存后顶点数组完全不变。撤销可回滚。

**证据**：`tests/parity/work/B1_orig.pmx` vs `B1_mod.pmx`；代码 `src/pmxeditor/panels/bone.py` 的 `_move_verts_toggled` / `edit(...)`（修复前该开关的持久化默认值为开）。

**建议**：默认关闭，或与原版对齐；至少首次触发时提示「将同时移动 N 个顶点」。

**状态：已修复**（`src/pmxeditor/panels/bone.py`：「移动时带动顶点」改为构造即关、不再从 `settings.json` 读回、不再持久化，触发时状态栏提示）。修复后同一 GUI 脚本复跑，`B1_orig.pmx` 与 `B1_mod.pmx` 字段级 0 差异。

## 差异-2 删除材质不会删除其几何（原版会）

**现象**：删除材质 #20「metal」（76,152 面）后——原版连带删除其独占顶点：顶点 116,036→102,081、面 614,757→538,605（文件 7,573,725 B）；新版保留全部几何，把这 76,152 面并入上一材质，`materials[19].face_count` 5,520→81,672（文件 8,437,554 B）。

**证据**：`tests/parity/work/S2_orig.pmx` vs `S2_mod.pmx`；代码 `src/pmxeditor/doc.py:385`（`merge=True` 时把面并入上一材质）、调用点 `src/pmxeditor/panels/material.py:439`。

**建议**：提供「删除材质并删除其面/顶点」（默认，对齐原版）与「仅删材质、面并入相邻材质」两种模式。

**状态：已修复**（`src/pmxeditor/doc.py`：`remove_material` 非 merge 分支修正 `face_count` 切片单位 + 新增 `compact_vertices()` 清理孤立顶点并重映射索引与形态偏移；删除对话框默认按钮改为「连同三角面删除」）。修复后顶点 116,036→102,081、面 614,757→538,605、文件 7,573,725 B，与原版逐字段一致。

## 差异-3 PMX 注释换行被写成 LF（原版为 CRLF）

**现象**：三行注释保存后是 `\n`，原版是 `\r\n`。

**证据**：`src/pmxeditor/panels/info.py:119 v = self.comment.toPlainText()`（QPlainTextEdit 输出 `\n`）→ `src/pmxeditor/pmx.py:416 m.comment = r.text()`。

**建议**：写入前 `v.replace("\r\n", "\n").replace("\n", "\r\n")`。

**状态：已修复**（`src/pmxeditor/pmx.py` 新增 `_crlf()`，`save_pmx` 写 `comment`/`comment_en` 前规范化）。修复后与原版保存结果 0 差异。

## 差异-4 颜色只有 8 位精度（0.5 存成 0.501961）

**现象**：材质漫反射 R / 透明度 A 想设 0.5，新版落盘 0.501961（128/255）；原版可存任意浮点 0.5。

**证据**：`src/pmxeditor/panels/material.py:57 self.diffuse = ColorButton([1,1,1,1])`、`src/pmxeditor/ui_widgets.py:185 ColorButton`（`QColor.fromRgbF`，8 位通道）、`material.py:66 / _color()`。

**建议**：给 diffuse/specular/ambient/edge_color 补 4 个浮点数值框（至少透明度可输入浮点）。

**状态：已修复**（`src/pmxeditor/ui_widgets.py` 新增 `ColorSpins` 浮点 RGBA 数值框，材质页加入漫反射/高光色/环境色/描边四行并与颜色按钮双向同步；`_fill_fields` 用 PMX 原值回填）。精确输入 0.5 后与原版 0 差异；经 `QColorDialog` 取色的老路径仍是 8 位（`0.501961`），属预期。

## 差异-5 顶点编辑后该顶点出现 ≤4.0e-5 漂移

编辑顶点0 位置 X=0.5 后，该顶点 Y 16.80584→16.805799、Z −0.422984→−0.423、法线 3e-06→0、权重 0.53826→0.5383；原版只有 X 变。疑为 `src/pmxeditor/panels/vertex.py:_apply` 的 float32 重算/权重归一化。

**状态：已修复**（`src/pmxeditor/panels/vertex.py:_apply` 改为按分量判定改动，只写真正被改过的分量）。修复后与原版 0 差异。

## 差异-6 删骨骼时连带规范化 tail 标记位

`src/pmxeditor/doc.py:318-322` 对 `BF_TAIL_INDEX` 且重映射后 <0 的骨骼清位（源模型里已有 9 个 `tail_bone=-1` 但置位的骨骼，flags 271→270、283→282、267→266）。方向更规范，但属于未请求的连带修改。

**状态：部分修复**（`src/pmxeditor/doc.py`：只有 `tail_bone == 被删索引` 时才清 `BF_TAIL_INDEX`/归零 `tail_offset`）。与 `S1_orig` 的差异由 15 处降到 2 处；剩下的是**有意保留**：子骨骼父级挂到被删骨骼的真正父级（87）而原版挂索引前一位（99），语义更正确。

## 差异-7 新建骨骼默认值与原版不同

原版：`新規ボーン1` / 英文名空 / 父骨骼 −1 / 位置 (0,0,0) / flags 26。
新版：`新建骨骼` / `new_bone` / 父骨骼 = 当前选中骨骼 / 位置 = 父位置+(0,1,0) / flags 30。

**状态：不改**（有意保留：默认父级/位置/flags 是功能增强，见 `REPORT.md` 第十节 N1）。

## 能力差异

> 以上修复已用同一套 GUI 脚本（`tests/parity/side_mod.py`）复跑复核，明细见 `tests/parity/REPORT.md` 第九节。


- ~~信息页「文字编码」「追加UV数」新版只读（原版可改编码；追加UV 原版可设但 PMX 2.0 不落盘）。~~
  **状态：已修复**。`src/pmxeditor/panels/info.py` 把这两项改成下拉，`src/pmxeditor/pmx.py` 新增 `set_add_uv()` 并在 `validate_model` 里校验 0–4 与 `v_add` 宽度。复核：E4 两侧均 8,435,389 B、`pmxsem` 0 差异；E5 新版 `add_uv=2`、`v_add (116036, 8)`、12,150,802 B（+n×32），0→2→4→0 往返回到 8,437,650 B 且与纯另存逐字节相同。原版追加 UV 在 PMX 2.0 下仍不落盘，故 E5 记为「新版更正确」的有意差异。
- 材质页「新建材质」原版 + 号灰化不可用，新版可新建（materials 22）。
- ~~面页材质重分配：新版无「面」页，属能力差异；原版语义见 `FA1_cx.pmx`（总表 FA1，3 处差异）。~~
  **状态：已补齐**。新增 `src/pmxeditor/panels/face.py`（「面」页）与 `src/pmxeditor/doc.py: reassign_faces()`：按材质切分扁平 `indices`，把源材质一段面移到目标材质末尾后重新拼接。复核 `FA1_cx` vs `FA1_mod` **0 差异**（m0 118404→117504、m1 15204→16104，总索引不变）。
- ~~柔体参数编辑：新版只读写不提供编辑入口，属能力差异；`SB1` 证明 PMX 2.1 柔体（含锚点/固定点）可原样往返。~~
  **状态：已补齐**。新增 `src/pmxeditor/panels/soft.py`（「柔体」页）与 `doc.py: add_softbody()/remove_softbody()`，覆盖名称/形状/材质/碰撞组/生成选项/质量/气动模型/求解参数/锚点/固定点；`SB2_cx` vs `SB2_mod` **0 差异**。

另：N3（复制骨骼）、N4（复制材质）、SB1（柔体往返）已与原版 `.cx`/GUI 对照 **0 差异**，详见 `tests/parity/compare_all.md`。

## 膝部鼓包：非ローカル付与的参考系错误（已修复）

**现象**：弯曲小腿/旋转腿部时，膝周网格出现明显鼓包与拧转；同一姿态在原版 PmxEditor 中正常。

**根因**：`Pose._world_rows`（NumPy）与 `native/pmx_core.cpp: compute_world_rows` 的非ローカル付与，把源骨骼的世界旋转换算到**目标骨骼父级**空间。`膝` 这类反向付与骨骼的 `append_parent` 就是自己的父级，`W[target_parent]⁻¹ @ W[source]` 恒为单位旋转，付与率 −0.75 完全失效：左ひざ弯 60° 时 `膝` 世界角本应为 `60 × (1−0.75) = 15°`，实际仍是 60°；膝周大量顶点权重给到 `膝`，因此被过度拧转。

**修复**：非ローカル付与改为取源骨骼**相对其自身父级**的本地旋转（与 Blender `mmd_tools` 的 shadow-bone 语义一致）；`world_subset` 的 need 集合补上源父级，避免局部更新时源父级矩阵缺失。Python 与 C++ 同步修改并重建 `_pmx_core`。

**验证**：新增 `tests/run.py: scen_append`——60° 弯曲时 `膝` 世界角 **15.00°**（旧实现 60°），native/NumPy 世界矩阵差 **0**；全量回归 **43 个功能场景**全部 rc=0、anomalies=0（`poseundo` 仍为已记录的既有失败，与本次改动无关）。膝部 60° 弯曲截图（`tests/shots/parity_knee_fix_60.png`）目视无鼓包。

**Roll / 坐标系排查结论**：PMX 没有 Roll 字段，`local_x/local_z` 只是可选的编辑用局部轴，PMX/MMD 蒙皮不使用它们；渲染链路没有 Z 翻转，世界矩阵直接由 PMX 坐标与四元数累加。该模型权重全为 BDEF1/2/4（无 SDEF/QDEF），BDEF2/4 的 DQS 已有「参考骨骼符号对齐」，不存在 `q1·q2<0` 的长路径问题。因此本次鼓包与 Roll、坐标系翻转、DQS 符号均无关。附带对拍：膝 60°/90° 弯曲时 DQS 与 LBS 的边长伸缩接近；髋 90° 旋转时 DQS 的 p95 径向膨胀 1.21 vs LBS 1.16，属既有的 DQS 取舍，不是本次鼓包的主因。

## 刚体/关节叠加层停留在静止坐标（已修复）

**现象**：整体移动或摆姿后，刚体十字/关节坐标轴标记留在 PMX 静止位置，与模型分离。

**修复**：`Viewport._rigid_current_matrix` / `_joint_current_matrix` 统一返回当前变换——物理演算中取 Bullet 模拟变换，否则取「静止矩阵 × 所属骨骼的姿态增量」；关节跟随第一个刚体。**`bone = -1` 的无骨骼刚体**（本模型的 `右胸_後/回転/前/前後`、`左胸_後/回転/前/前後` 共 8 个，以及引用它们的关节）取「子树最大的根骨骼」（`全ての親`）的整体姿态增量，保证整体平移/旋转时一起走。`_build_rigid_lines`、`_build_joint_lines`、视口拾取、`frame_selected` 全部改用该矩阵；姿态变化时按显示开关重建叠加层。


## 差异-8 开启「轴固定」时原版会把轴向量归一化为骨骼朝向（parity B7）

两侧开「轴固定」后 `bones[5].flags` 都 27→1051（置 `BF_FIXED_AXIS`），但原版在同一动作里把 `axis` 从 (1,0,0) 改成 (1, 0.998421, −0.056169)（骨骼朝向），新版保持 (1,0,0)。

**证据**：`tests/parity/work/B7_orig.pmx` vs `work/B7_mod.pmx`（`pmxsem` 2 处差异，仅 `axis[1]/axis[2]`）；新版 `src/pmxeditor/panels/bone.py:_axis_flag_changed` 只改标志位。

**影响**：低危——只有轴固定骨骼的冗余轴向数据不同，不影响物理与姿态。

**状态：未修复**（有意保留：需要先推断原版归一化算法，当前无明确规格）。

## 全量回归时发现的既有问题（非本轮引入）

用 `tests/parity/regress.py` 跑 `tests/run.py` 的 40 个功能场景时发现三类既有问题，均已用 `git stash push -- src` 在 HEAD 上复现确认：

1. ~~`sel` 场景 **进程崩溃 rc=0xC0000005**（访问冲突）~~ —— 已定位并修复（见 P0-3：选中时重建列表导致悬空 QModelIndex）。
2. `vp` 场景 2 条异常：`pose-move`（左键拖动骨骼后没有位移）、`phys-pose`（物理演算中拖动骨骼姿态未变）—— HEAD 同样出现，属拖动模拟与实际鼠标路径的差异，非产品缺陷。
3. ~~`sel6` 场景脚本自身 `AttributeError: 'Document' object has no attribute 'sel'`~~ —— 已修（改用 `sel_kind/sel_index`）。

另：`inventory` 的 2 条 `text-clipped` 是超长模型路径的 `Faint` 标签，属既有告警。

`mouse` 场景原本断言「移动时带动顶点」开关写入 `settings.json`；该持久化在本轮按 parity 结论移除（原版移动骨骼不搬顶点），场景断言已同步改为「开关不再持久化、新实例默认关闭」。
