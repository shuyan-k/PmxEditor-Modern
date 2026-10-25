// 柔体0 参数修改：总质量 2.5 → 3.5，碰撞余量 0.05 → 0.1
// 原版可经 SoftBody 页/CSScript 编辑；新版没有柔体编辑入口，属能力差异。
IPXSoftBody s = sbody[0];
s.TotalMass = 3.5f;
s.Margin = 0.1f;
