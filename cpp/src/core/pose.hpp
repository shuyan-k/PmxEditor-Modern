// 姿态求值：世界矩阵合成（含付与继承）、CCD IK、骨骼拖拽，语义对齐 native/pmx_core.cpp。
#pragma once

#include <array>
#include <cstdint>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>

#include "core/math.hpp"
#include "core/pmx.hpp"

namespace pmx {

using MorphWeights = std::vector<std::pair<int, float>>;

class Pose {
public:
    explicit Pose(const Model& model);

    int n = 0;
    std::vector<int> parent;
    std::vector<Vec3> rest_off;
    std::vector<Vec3> rest_pos;
    std::vector<std::vector<int>> children;
    std::vector<int> eval_order;
    std::vector<std::vector<int>> subtrees;
    std::vector<std::vector<int>> append_users;

    std::vector<Quat> base_rot;
    std::vector<Vec3> base_trans;
    std::vector<Quat> rot;
    std::vector<Vec3> trans;

    std::unordered_map<int, Quat> ov_rot;
    std::unordered_map<int, Vec3> ov_trans;

    bool ik_reset_links = true;
    float ik_retry_tolerance = 0.05f;
    int ik_clamp_hits = 0;

    void reset();
    // morph_weights 需先经 resolve_morph_weights 展开（组/翻转形态）。
    void apply(const MorphWeights* morph_weights = nullptr);
    void world_update();

    const std::vector<Mat4>& world();
    void invalidate_world();

    void rotate_local(int bone, Quat dq);
    void rotate_world(int bone, Vec3 axis, float angle);
    void translate_world(int bone, Vec3 delta);
    void clear_overrides();

    int solve_ik(int max_loops = 0, const std::unordered_set<int>* only = nullptr);

    std::unordered_set<int> active_ik_indices(int changed_bone) const;
    std::unordered_set<int> changed_subtrees(const std::unordered_set<int>& changed) const;

private:
    const Model& model_;
    std::vector<Mat4> world_;
    bool dirty_ = true;
    std::unordered_map<int, std::array<float, 3>> ik_euler_;

    struct Chain {
        int ik_bone = -1;
        int start = 0;
        int count = 0;
    };
    std::vector<Chain> chains_;
    std::vector<int> link_bones_;
    std::vector<uint8_t> link_limited_;
    std::vector<IKLink> link_limits_;
    std::vector<uint16_t> flags_;
    std::vector<int> append_parent_;

    void compute_world();
    int solve_ik_core(int max_loops, const std::unordered_set<int>* only);
    int retry_stuck_chains(int max_loops, const std::unordered_set<int>* only);
};

}  // namespace pmx
