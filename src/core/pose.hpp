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

// 物理回写目标：刚体驱动出的骨骼世界矩阵。
struct BoneOverride {
    Mat4 world;
    // 只反馈旋转、位移沿用动画（PMX 刚体 mode 2「物理+骨骼对齐」）。
    bool keep_translation = false;
};

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
    // 每个 IK 骨骼的开关（来自 VMD 的「表示枠 / IK」帧）。关闭时这条 IK 链不参与
    // 求解，骨骼直接按动作里的关节轨道驱动（MMD 就是这么处理足 IK 开关的）。
    std::unordered_map<int, bool> ik_enabled;
    void set_ik_enabled(int bone, bool enabled);

    // 求解不收敛时把链接骨骼清成静止姿态重解的「重试」不是 MMD 的做法，而且会把
    // 动作写进骨骼的旋转整个抹掉（膝/踝被清成 0 后会朝错误方向起解，表现为反折）。
    bool ik_reset_links = false;
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

    // 物理回写：target 为 bone → 刚体驱动出的骨骼世界矩阵。按 eval_order 求值一遍，
    // 目标骨骼用该矩阵换算成本地量并写入覆盖，其余骨骼照常按动画局部量与付与继承
    // 求值。求值后 rot / trans / world() 已包含物理结果。
    void apply_physics_world(const std::unordered_map<int, BoneOverride>& target,
                             const MorphWeights* morph_weights = nullptr);

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
    // 求单根骨骼的世界矩阵：rot / trans 叠加付与继承后与父级世界矩阵相乘。
    // W 为已按 eval_order 求值好的世界矩阵数组（父级必须已就绪）。
    Mat4 local_matrix(int bone, const std::vector<Mat4>& W) const;
    int solve_ik_core(int max_loops, const std::unordered_set<int>* only);
    // 足 IK：按余弦定理先把膝弯到目标所需夹角，避免 CCD 从接近伸直的低条件数
    // 位形慢慢爬（每轮 0.002 rad）。之后 CCD 再做收尾。
    bool prebend_knee(const Chain& chain, const IK& ik);
    int retry_stuck_chains(int max_loops, const std::unordered_set<int>* only);
};

}  // namespace pmx
