// 复制骨骼5（上半身）：Clone 全部字段后追加到末尾，命名按新版「复制骨骼」规则
IPXBone src = bone[5];
IPXBone b = (IPXBone)src.Clone();
b.Name = src.Name + "_副本";
b.NameE = (src.NameE == "" ? "bone" : src.NameE) + "_copy";
bone.Add(b);
