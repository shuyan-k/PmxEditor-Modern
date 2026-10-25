# 原版 PmxEditor vs 新版 PmxEditor_Modern — 同操作语义比对总表

基准模型：`KARU式Rabbit Hole MIKU.ver 1.6.pmx`（116036 顶点 / 204919 面 / 21 材质 / 168 骨骼 / 22 表情 / 10 贴图 / 82 刚体 / 74 关节）。柔体两项（SB1/SB2）的基座为 `SB0_cx.pmx`：由原版 .cx 在基准模型上追加 1 个柔体后另存，PMX 2.1。

比对方式：两侧各自操作后「另存为」，再用 `pmxsem` 按 1e-5 容差逐字段比对两个另存文件。原版侧通常用真实鼠标键盘（GUI）；I3（IK 链）、FA1（面材质重分配）、N3/N4（复制骨骼/材质）、SB2（柔体参数）等原版无 GUI 入口或难以自动化的操作，改由 `tests/parity/cxop.py` 驱动原版自带 CSScript 插件（`.cx`）写入，落盘仍走 PmxEditor 自身的另存；其中 FA1 与 SB2 的新版侧已改为「面」页 / 「柔体」页的真实 GUI 操作。

**共 42 项：36 项一致、5 项差异、1 项未双侧完成。**

| 操作 | 说明 | 判定 | 差异段（处数） | 统计变化 |
| --- | --- | --- | --- | --- |
| E1 | 改模型日文名 → PARITY_E1 | **一致** | — | — |
| E2 | 改注释为三行文本（含中英文） | **一致** | — | — |
| E3 | 改模型英文名 → PARITY_EN | **一致** | — | — |
| E4 | 文字编码 UTF-16LE → UTF-8 | **一致** | — | — |
| E5 | 追加UV 数 0 → 2 | 差异 2 处（新版真正落盘，原版 UI 无效） | add_uv(1)、v_add(1) | — |
| B1 | 骨骼5「上半身」位置 X = 1.0 | **一致** | — | — |
| B2 | 骨骼5 名称 → PARITY_BONE | **一致** | — | — |
| B3 | 骨骼5 变形层级 0 → 3 | **一致** | — | — |
| M1 | 材质0 漫反射色 R = 0.5 | **一致** | — | — |
| M2 | 材质0 透明度 A = 0.5 | **一致** | — | — |
| V1 | 顶点0 位置 X = 0.5 | **一致** | — | — |
| F1 | 表情0「ウィンク２」首个顶点偏移 X = 0.1 | **一致** | — | — |
| P1 | 刚体0 质量 1.0 → 2.5 | **一致** | — | — |
| J1 | Joint0 旋转限制 X 下限 = -0.5° | **一致** | — | — |
| S1 | 删除骨骼 #100「左小指１」 | 差异 2 处（有意：新骨骼挂到原父 87，原版挂到前一根 99） | v_bones(1)、bones(1) | — |
| S2 | 删除材质 #20「metal」 | **一致** | — | — |
| U1 | 骨骼位移后撤销（Ctrl+Z） | **一致** | — | — |
| N1 | 新建骨骼 | 差异 5 处（设计差异：默认名/父级/位置/flags） | bones(5) | — |
| N2 | 新建材质 | 差异 1 处（原版 + 号灰化，无法新建材质） | materials(1) | materials 21→22 |
| M3 | 材质0 漫反射色 R 经取色对话框（8 位量化） | 未双侧完成 | — | — |
| M4 | 材质0 描边大小 1.0 → 0.5 | **一致** | — | — |
| M5 | 材质0 关闭「双面描绘」 | **一致** | — | — |
| M6 | 材质0 开启「描边有效」 | **一致** | — | — |
| V2 | 顶点0 UV-u 0.5 → 0.25 | **一致** | — | — |
| B4 | 骨骼5 关闭「显示」 | **一致** | — | — |
| B5 | 骨骼5 关闭「可旋转」 | **一致** | — | — |
| P2 | 刚体0 模式 跟随 → 演算+对齐 | **一致** | — | — |
| F2 | 表示枠 Root 追加骨骼 #106「兔耳_2_2.R」 | **一致** | — | — |
| I2 | 骨骼5 开启 IK | **一致** | — | — |
| I3 | 骨骼5 IK 目标/循环/角度 + 追加两条链（bone4、bone5） | **一致**（原版侧经 CSScript .cx 通道写入，GUI 无法编辑 IK 链） | — | — |
| V3 | 顶点0 法线 Y 0.706 → 1.0 | **一致** | — | — |
| V4 | 顶点0 UV-v 0.052 → 0.75 | **一致** | — | — |
| B6 | 骨骼5 开启「旋转付与」+ 付与率 0.5 | **一致** | — | — |
| B7 | 骨骼5 开启「轴固定」 | 差异 2 处（原版开启轴固定时把轴向量归一化为骨骼朝向，新版保持原值） | bones(2) | — |
| M7 | 材质0 球面模式 无 → 乘法 | **一致** | — | — |
| P3 | 刚体0 形状 球 → 箱 | **一致** | — | — |
| P4 | 刚体0 所属组 0 → 1 | **一致** | — | — |
| FA1 | 面材质重分配：材质0 前 300 个面 → 材质1 | **一致**（新版已补齐「面」页并走真实 GUI；原版侧经 .cx 定义同一语义） | — | — |
| N3 | 复制骨骼5「上半身」并追加 | **一致**（原版无复制入口；原版侧用 .cx Clone 同一命名规则） | — | — |
| N4 | 复制材质0「Skin」并追加（连面一起复制） | **一致**（原版无复制入口；原版侧 Clone 连面一起复制） | — | — |
| SB1 | PMX 2.1 柔体基座往返另存（1 柔体 / 1 锚点 / 1 固定点） | **一致**（基座 SB0_cx.pmx 由原版 .cx 生成，PMX 2.1） | — | — |
| SB2 | 柔体0 总质量 2.5 → 3.5、碰撞余量 0.05 → 0.1 | **一致**（新版已补齐「柔体」页并走真实 GUI；原版侧经 .cx 定义同一语义） | — | — |

## 差异明细

### E5 追加UV 数 0 → 2

```
stats A={'vertices': 116036, 'faces': 204919, 'materials': 21, 'bones': 168, 'morphs': 22, 'textures': 10, 'rigid': 82, 'joints': 74, 'soft': 0}
stats B={'vertices': 116036, 'faces': 204919, 'materials': 21, 'bones': 168, 'morphs': 22, 'textures': 10, 'rigid': 82, 'joints': 74, 'soft': 0}
● add_uv (1 处)
   add_uv                                     A=0  B=2
● v_add (1 处)
   v_add                                      A=arr[116036, 0]=[]  B=arr[116036, 8]=[0.0, 0.0, 0.0, 0.0]…(928288)
```

### S1 删除骨骼 #100「左小指１」

```
stats A={'vertices': 116036, 'faces': 204919, 'materials': 21, 'bones': 167, 'morphs': 22, 'textures': 10, 'rigid': 82, 'joints': 74, 'soft': 0}
stats B={'vertices': 116036, 'faces': 204919, 'materials': 21, 'bones': 167, 'morphs': 22, 'textures': 10, 'rigid': 82, 'joints': 74, 'soft': 0}
● v_bones (1 处)
   v_bones                                    A=arr[116036, 4]=[7, 8, 0, 0]…(464144)  B=arr[116036, 4]=[7, 8, 0, 0]…(464144)
● bones (1 处)
   bones[100].parent                          A=99  B=87
```

### N1 新建骨骼

```
stats A={'vertices': 116036, 'faces': 204919, 'materials': 21, 'bones': 169, 'morphs': 22, 'textures': 10, 'rigid': 82, 'joints': 74, 'soft': 0}
stats B={'vertices': 116036, 'faces': 204919, 'materials': 21, 'bones': 169, 'morphs': 22, 'textures': 10, 'rigid': 82, 'joints': 74, 'soft': 0}
● bones (5 处)
   bones[168].name                            A=新規ボーン1  B=新建骨骼
   bones[168].name_en                         A=  B=new_bone
   bones[168].pos[1]                          A=0.0  B=1.015735
   bones[168].parent                          A=-1  B=0
   bones[168].flags                           A=26  B=30
```

### N2 新建材质

```
stats A={'vertices': 116036, 'faces': 204919, 'materials': 21, 'bones': 168, 'morphs': 22, 'textures': 10, 'rigid': 82, 'joints': 74, 'soft': 0}
stats B={'vertices': 116036, 'faces': 204919, 'materials': 22, 'bones': 168, 'morphs': 22, 'textures': 10, 'rigid': 82, 'joints': 74, 'soft': 0}
● materials (1 处)
   materials                                  A=["{\"name\": \"Skin\", \"name_en\": \"\", \"diffuse\": \"[1.0, 1.0, 1.0, 1.0]\", \"specular\": \"[0.0, 0...", "{\"name\": \"Face\", \"name_en\": \"\", \"diffuse\": \"[1.0, 1.0, 1.0, 1.0]\", \"specular\": \"[0.0, 0...", "{\"name\": \"eye White\", \"name_en\": \"\", \"diffuse\": \"[1.0, 1.0, 1.0, 1.0]\", \"specular\": \"[0...", "{\"name\": \"eye socket\", \"name_en\": \"\", \"diffuse\": \"[1.0, 1.0, 1.0, 1.0]\", \"specular\": \"[..."]…(21)  B=["{\"name\": \"Skin\", \"name_en\": \"\", \"diffuse\": \"[1.0, 1.0, 1.0, 1.0]\", \"specular\": \"[0.0, 0...", "{\"name\": \"Face\", \"name_en\": \"\", \"diffuse\": \"[1.0, 1.0, 1.0, 1.0]\", \"specular\": \"[0.0, 0...", "{\"name\": \"eye White\", \"name_en\": \"\", \"diffuse\": \"[1.0, 1.0, 1.0, 1.0]\", \"specular\": \"[0...", "{\"name\": \"eye socket\", \"name_en\": \"\", \"diffuse\": \"[1.0, 1.0, 1.0, 1.0]\", \"specular\": \"[..."]…(22)
```

### B7 骨骼5 开启「轴固定」

```
stats A={'vertices': 116036, 'faces': 204919, 'materials': 21, 'bones': 168, 'morphs': 22, 'textures': 10, 'rigid': 82, 'joints': 74, 'soft': 0}
stats B={'vertices': 116036, 'faces': 204919, 'materials': 21, 'bones': 168, 'morphs': 22, 'textures': 10, 'rigid': 82, 'joints': 74, 'soft': 0}
● bones (2 处)
   bones[5].axis[1]                           A=0.998421  B=0.0
   bones[5].axis[2]                           A=-0.056169  B=1.0
```
