// 结构性编辑（增删骨骼/材质/形态/表示枠/刚体/关节/柔体）与索引重映射。
// 语义对齐 Python 版 src/pmxeditor/doc.py。
#pragma once

#include <vector>

#include "core/pmx.hpp"

namespace pmxdoc {

int add_bone(pmx::Model& m, int parent = -1);
int move_bone(pmx::Model& m, int index, int delta);
int duplicate_bone(pmx::Model& m, int index);
int remove_bone(pmx::Model& m, int index);

int add_material(pmx::Model& m);
int duplicate_material(pmx::Model& m, int index);
int reassign_faces(pmx::Model& m, int src, int start_face, int count_faces, int dst);
int compact_vertices(pmx::Model& m);
int remove_material(pmx::Model& m, int index, bool merge = false);

int add_morph(pmx::Model& m, int type = 1);
int duplicate_morph(pmx::Model& m, int index);
int remove_morph(pmx::Model& m, int index);

int add_frame(pmx::Model& m, int special = 0);
int duplicate_frame(pmx::Model& m, int index);
int remove_frame(pmx::Model& m, int index);
int move_frame(pmx::Model& m, int index, int delta);
bool frame_add_item(pmx::Model& m, int index, int kind, int item);
bool frame_remove_item(pmx::Model& m, int index, int pos);
int frame_move_item(pmx::Model& m, int index, int pos, int delta);

int add_rigid(pmx::Model& m, int bone = -1);
int duplicate_rigid(pmx::Model& m, int index);
int remove_rigid(pmx::Model& m, int index);

int add_joint(pmx::Model& m);
int duplicate_joint(pmx::Model& m, int index);
int remove_joint(pmx::Model& m, int index);

int add_softbody(pmx::Model& m);
int remove_softbody(pmx::Model& m, int index);

// 编辑辅助：重新计算材质 face_count（面区间被改动后调用）。
void recompute_face_counts(pmx::Model& m);
// 按材质序号返回该材质的面区间 [start_face, start_face+count)。
void material_face_range(const pmx::Model& m, int material, int* start_face, int* count);

}  // namespace pmxdoc
