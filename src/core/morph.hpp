// 形态：组/翻转递归展开、顶点/UV/骨骼/材质偏移应用。
#pragma once

#include <unordered_map>
#include <vector>

#include "core/pmx.hpp"
#include "core/pose.hpp"

namespace pmx {

constexpr int MORPH_FLIP = 9;

// 把组形态(0)与翻转形态(9)展开成实际生效的形态权重。
std::unordered_map<int, float> resolve_morph_weights(const Model& model,
                                                     const MorphWeights& weights);

// 返回应用顶点(1)/UV(3)形态后的坐标；没有对应形态时返回原数组引用。
struct VertexMorphResult {
    const std::vector<Vec3>* pos = nullptr;
    const std::vector<Vec2>* uv = nullptr;
    std::vector<Vec3> pos_storage;
    std::vector<Vec2> uv_storage;
};
VertexMorphResult apply_vertex_morphs(const Model& model, const MorphWeights& weights);

// 材质形态的乘算/加算校正（calc=0 乘算，calc=1 加算）。
struct MaterialColor {
    Vec4 mul{1.0f, 1.0f, 1.0f, 1.0f};
    Vec4 add{};
};
std::unordered_map<int, MaterialColor> material_morph_colors(const Model& model,
                                                             const MorphWeights& weights);

}  // namespace pmx
