// 面页材质重分配：材质0 的前 300 个面移到材质1（追加到材质1 面列表末尾）
// 原版 GUI「面」页可完成同样的事；新版没有「面」页，属能力差异。
IPXMaterial m0 = material[0];
IPXMaterial m1 = material[1];
int move = 300;
if (m0.Faces.Count < move) move = m0.Faces.Count;
for (int i = 0; i < move; i++) {
    IPXFace f = m0.Faces[0];
    m0.Faces.RemoveAt(0);
    m1.Faces.Add(f);
}
