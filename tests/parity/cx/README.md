# 同操作校验用的 CSScript（.cx）通道

CSScript 是原版 PmxEditor 自带的插件（菜单 `编辑(E) → 插件(P) → CSScript → C#スクリプト`），
可以在编辑器进程内直接读写 `IPXPmx`，因此能覆盖 GUI 无法编辑的字段（如 IK 链）。

## 目录内容

| 文件 | 说明 |
| --- | --- |
| `*.cs` | 各操作的「簡易形式」语句片段，由 `../cxop.py` 粘进脚本窗体执行。例：`op_V1.cs`（顶点0 X=0.5）、`op_I3.cs`（骨骼5 IK 目标/循环/角度/两条 Link） |
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

## 常用 API 参考

- 材质：`m.Name / NameE / Diffuse(V4) / Ambient(V3) / Specular(V3) / Power / BothDraw / Shadow / SelfShadowMap / SelfShadow / VertexColor / Edge / EdgeSize / SphereMode`
- 骨骼：`b.Name / NameE / Position(V3) / Parent / ToBone / ToOffset / Level / IsRotation / IsTranslation / Visible / Controllable / IsIK / IK.Target / IK.LoopCount / IK.Angle / IK.Links[i].Bone / IsLimit / Low / High`
- 表示枠：`node[i].Name / NameE`，以及 `pmx.RootNode`、`pmx.ExpressionNode`
- 顶点：`v.Position / Normal / EdgeScale / UV / UVA1 / Bone1..4 / Weight1..4 / SDEF / QDEF`
- 形变偏移：`o.Vertex = vertex[0]`

完整样例见原版目录 `D:\Project\MMD\05_工具\PmxEditor (MMD模型编辑器）\_plugin\CSScript\SampleScript\`
（S033 顶点、S034 材质/面、S035 骨骼、S036 モーフ、S037 表示枠、S038 刚体、S039 Joint、S042 オブジェクト追加 等）。
