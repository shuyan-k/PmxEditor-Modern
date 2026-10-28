// 蒙皮：CPU 参考实现（双四元数 BDEF/QDEF）+ GPU 所需打包数据。
#pragma once

#include <array>
#include <cstdint>
#include <vector>

#include "core/math.hpp"
#include "core/pmx.hpp"

namespace pmx {

class SkinDeformer {
public:
    explicit SkinDeformer(const Model& model);

    int n = 0;
    int bone_count = 0;
    std::vector<std::array<int, 4>> bones;
    std::vector<std::array<float, 4>> weights;
    std::vector<uint8_t> types;  // 运行时类型：SDEF(3) 已按 BDEF2(1) 处理
    std::vector<std::array<float, 9>> sdef;
    std::vector<Vec3> rest;

    // base_pos/base_nrm 为形态应用后的静止坐标；world 为骨骼世界矩阵。
    void deform(const std::vector<Vec3>& base_pos, const std::vector<Vec3>& base_nrm,
                const std::vector<Mat4>& world, std::vector<Vec3>& out_pos,
                std::vector<Vec3>& out_nrm) const;

    // 局部重算：只更新 dirty_bones 影响到的顶点，其余沿用 prev。
    void deform_subset(const std::vector<Vec3>& base_pos, const std::vector<Vec3>& base_nrm,
                       const std::vector<Mat4>& world,
                       const std::vector<int>& dirty_bones, std::vector<Vec3>& prev_pos,
                       std::vector<Vec3>& prev_nrm) const;

    const std::vector<int>& dup_vertices() const { return dup_; }

private:
    std::vector<int> dup_;                        // 同一骨骼占用多个权重槽的顶点
    std::vector<std::vector<int>> bone_vertices_;  // 每根骨骼影响的顶点
    void deform_one(const std::vector<Vec3>& base_pos, const std::vector<Vec3>& base_nrm,
                    const std::vector<Mat4>& world, int vi, Vec3& pos, Vec3& nrm) const;
};

}  // namespace pmx
