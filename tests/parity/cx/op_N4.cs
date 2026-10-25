// 复制材质0（Skin）：Clone 全部字段与面列表后追加到末尾，命名按新版「复制材质」规则
IPXMaterial src = material[0];
IPXMaterial mt = (IPXMaterial)src.Clone();
mt.Name = src.Name + "_副本";
mt.NameE = (src.NameE == "" ? "material" : src.NameE) + "_copy";
material.Add(mt);
