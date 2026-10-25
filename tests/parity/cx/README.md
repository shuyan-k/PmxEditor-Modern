# 同操作校验用的 CSScript（.cx）通道

CSScript 是原版 PmxEditor 自带的插件（菜单 `编辑(E) → 插件(P) → CSScript → C#スクリプト`），
可以在编辑器进程内直接读写 `IPXPmx`，因此能覆盖 GUI 无法编辑的字段（如 IK 链）。

## 目录内容

| 文件 | 说明 |
| --- | --- |
| `*.cs` | 各操作的「簡易形式」语句片段，由 `../cxop.py` 粘进脚本窗体执行。例：`op_V1.cs`（顶点0 X=0.5）、`op_I3.cs`（骨骼5 IK 目标/循环/角度/两条 Link） |
| `op_FA1.cs` | 面页材质重分配：材质0 前 300 个面移入材质1（`Faces.RemoveAt` → `Faces.Add`） |
| `op_N3.cs` / `op_N4.cs` | 复制骨骼 / 复制材质：`(IPXBone|IPXMaterial)src.Clone()` 后追加，命名对齐新版 |
| `op_SB0.cs` | SoftBody 写入样例：追加 PMX 2.1 柔体（含锚点与固定点），用来生成 SB1/SB2 基座 |
| `op_SB2.cs` | SoftBody 参数编辑：总质量、碰撞余量 |
| `parity_template.cx` | 完整 `.cx` 文件：以原版自带 `S033_頂点の編集.cx` 为骨架，**仅替换 `<CodeText>`**（XML 解析校验通过，`ScriptType=CS2`、`CompilerVersion=4`）；可直接在 GUI 里用 `ファイル → スクリプト読み込み` 打开后点 `実行`，内容是「读模型概况 + 写日志」示例，也是自写脚本的最小骨架 |

## 写法约束（踩过的坑）

1. 只能在「簡易形式」页粘**语句片段**；完整 class 不要粘进「一般形式」——本插件的自动头会被插到 `Run()` 内部，导致 `CS0116 / CS1022 / CS0542`。
2. 自动头已定义以下变量，可直接使用：
   `host / builder / bd / bdx / connect / view / pmx / header / info / vertex / material / bone / morph / node / body / joint / sbody`
   其中 `bdx` 是构造器：`bdx.Vertex() / Material() / Bone() / IKLink() / Node() / Body() / Joint() / SoftBody()` 等。
3. **自动尾未启用**：改完字段必须显式写回，否则另存仍是旧值：

   ```csharp
   connect.Pmx.Update(pmx);
   connect.Form.UpdateList(UpdateObject.All);
   connect.View.PMDView.UpdateModel();
   connect.View.PMDView.UpdateView();
   ```

   `cxop.py` 的 `TAIL` 已内置这四行。
4. 数值用 float 字面量（`1.0f`），角度用 `Q.D2R(度)` 转弧度。
5. 未载入模型时访问 `vertex[0]` 会抛 `ArgumentOutOfRangeException`，表现为「スクリプトの実行に失敗しました」。
6. 结果回传给 Python：脚本自己 `System.IO.File.WriteAllText(@"...\cx_log.txt", ...)`。
7. `cxop.py` 依赖 pywin32 与原版编辑器窗口，必须用**系统 Python** 运行；仓库便携运行时（`build/python`）不含 pywin32。

## 常用 API 参考

- 材质：`m.Name / NameE / Diffuse(V4) / Ambient(V3) / Specular(V3) / Power / BothDraw / Shadow / SelfShadowMap / SelfShadow / VertexColor / Edge / EdgeSize / SphereMode`
- 面：`m.Faces`（`IList<IPXFace>`，每项 `Vertex1/2/3`）；重分配就是把 face 从源材质 `RemoveAt` 后 `Add` 到目标材质
- 骨骼：`b.Name / NameE / Position(V3) / Parent / ToBone / ToOffset / Level / IsRotation / IsTranslation / Visible / Controllable / IsIK / IK.Target / IK.LoopCount / IK.Angle / IK.Links[i].Bone / IsLimit / Low / High`
- 复制对象：`IPXBone / IPXMaterial / IPXFace / IPXSoftBody` 均实现 `ICloneable`，`(IPXBone)x.Clone()` 可整体复制
- 柔体（PMX 2.1）：`s.Name / NameE / Shape(SoftBodyShape) / Material(材质引用) / Group / PassGroup[16] / GenerateBendingLinks / GenerateClusters / RandomizeConstraints / BendingLinkDistance / ClusterCount / TotalMass / Margin / AeroModel / VCF..AHR / SRHR_CL..SS_SPLT_CL / V_IT..C_IT / LST,AST,VST / Anchors / Pins`
  - 锚点：`var a = bdx.SoftBodyAnchor(); a.Body = body[0]; a.Vertex = vertex[5]; a.Near = true; s.Anchors.Add(a);`
  - 固定点：`s.Pins.Add(vertex[0]);`
- 表示枠：`node[i].Name / NameE`，以及 `pmx.RootNode`、`pmx.ExpressionNode`
- 顶点：`v.Position / Normal / EdgeScale / UV / UVA1 / Bone1..4 / Weight1..4 / SDEF / QDEF`
- 形变偏移：`o.Vertex = vertex[0]`

## 柔体基座的生成与复用

```powershell
# 1) 在基准模型上追加 1 个柔体并另存 → work\SB0_cx.pmx（PMX 2.1）
$env:PARITY_MODEL=""; python tests\parity\cxop.py SB0

# 2) 以基座为模型做柔体参数编辑 → work\SB2_cx.pmx
$env:PARITY_MODEL="D:\Project\PmxEditor_Modern\tests\parity\work\SB0_cx.pmx"
python tests\parity\cxop.py SB2
```

`cxop.py` 也支持 `PARITY_SUF`，输出文件名为 `<OP><SUF>_cx.pmx`。

完整样例见原版目录 `D:\Project\MMD\05_工具\PmxEditor (MMD模型编辑器）\_plugin\CSScript\SampleScript\`
（S033 顶点、S034 材质/面、S035 骨骼、S036 モーフ、S037 表示枠、S038 刚体、S039 Joint、S042 オブジェクト追加 等）。
