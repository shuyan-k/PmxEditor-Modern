#include "core/pose.hpp"

#include <algorithm>
#include <cmath>
#include <queue>

namespace pmx {
namespace {

// Python/原生实现都用 float 比较；保持一致以免对拍出现 1e-7 级抖动。
inline bool same_quat(Quat a, Quat b) {
    return a.x == b.x && a.y == b.y && a.z == b.z && a.w == b.w;
}
inline bool same_vec(Vec3 a, Vec3 b) { return a.x == b.x && a.y == b.y && a.z == b.z; }

}  // namespace

Pose::Pose(const Model& model) : model_(model) {
    n = static_cast<int>(model.bones.size());
    parent.assign(n, -1);
    rest_off.resize(n);
    rest_pos.resize(n);
    children.assign(n, {});
    subtrees.resize(n);
    append_users.assign(n, {});
    flags_.resize(n);
    append_parent_.resize(n);

    for (int i = 0; i < n; ++i) {
        const Bone& b = model.bones[static_cast<std::size_t>(i)];
        rest_pos[i] = b.pos;
        flags_[i] = b.flags;
        append_parent_[i] = b.append_parent;
        if (b.parent >= 0 && b.parent < n && b.parent != i) {
            parent[i] = b.parent;
            rest_off[i] = b.pos - model.bones[static_cast<std::size_t>(b.parent)].pos;
            children[static_cast<std::size_t>(b.parent)].push_back(i);
        } else {
            rest_off[i] = b.pos;
        }
        if ((b.flags & (BF_INHERIT_ROT | BF_INHERIT_MOV)) && b.append_parent >= 0 &&
            b.append_parent < n && b.append_parent != i) {
            append_users[static_cast<std::size_t>(b.append_parent)].push_back(i);
        }
    }

    // 拓扑序（父先于子）
    {
        std::vector<uint8_t> seen(static_cast<std::size_t>(n), 0);
        std::vector<int> stack;
        for (int root = 0; root < n; ++root) {
            if (parent[static_cast<std::size_t>(root)] >= 0) continue;
            stack.push_back(root);
            while (!stack.empty()) {
                int i = stack.back();
                stack.pop_back();
                if (seen[static_cast<std::size_t>(i)]) continue;
                seen[static_cast<std::size_t>(i)] = 1;
                for (auto it = children[static_cast<std::size_t>(i)].rbegin();
                     it != children[static_cast<std::size_t>(i)].rend(); ++it)
                    stack.push_back(*it);
            }
        }
    }

    // 子树集合
    for (int i = 0; i < n; ++i) {
        std::vector<int> stack{i};
        while (!stack.empty()) {
            int j = stack.back();
            stack.pop_back();
            subtrees[static_cast<std::size_t>(i)].push_back(j);
            for (int c : children[static_cast<std::size_t>(j)]) stack.push_back(c);
        }
    }

    // 求值顺序：父骨骼与付与来源必须先于当前骨骼（Kahn）。
    {
        std::vector<std::vector<int>> users(static_cast<std::size_t>(n));
        std::vector<int> indeg(static_cast<std::size_t>(n), 0);
        std::vector<int> deps;
        for (int i = 0; i < n; ++i) {
            deps.clear();
            if (parent[static_cast<std::size_t>(i)] >= 0)
                deps.push_back(parent[static_cast<std::size_t>(i)]);
            const Bone& b = model.bones[static_cast<std::size_t>(i)];
            if ((b.flags & (BF_INHERIT_ROT | BF_INHERIT_MOV)) && b.append_parent >= 0 &&
                b.append_parent < n && b.append_parent != i &&
                b.append_parent != parent[static_cast<std::size_t>(i)]) {
                deps.push_back(b.append_parent);
            }
            indeg[static_cast<std::size_t>(i)] = static_cast<int>(deps.size());
            for (int d : deps) users[static_cast<std::size_t>(d)].push_back(i);
        }
        std::queue<int> q;
        for (int i = 0; i < n; ++i)
            if (indeg[static_cast<std::size_t>(i)] == 0) q.push(i);
        eval_order.reserve(static_cast<std::size_t>(n));
        while (!q.empty()) {
            int i = q.front();
            q.pop();
            eval_order.push_back(i);
            for (int u : users[static_cast<std::size_t>(i)]) {
                if (--indeg[static_cast<std::size_t>(u)] == 0) q.push(u);
            }
        }
        if (static_cast<int>(eval_order.size()) < n) {
            std::vector<uint8_t> seen(static_cast<std::size_t>(n), 0);
            for (int i : eval_order) seen[static_cast<std::size_t>(i)] = 1;
            for (int i = 0; i < n; ++i)
                if (!seen[static_cast<std::size_t>(i)]) eval_order.push_back(i);
        }
    }

    // IK 链（链接扁平存放，索引与文件顺序一致）
    for (int i = 0; i < n; ++i) {
        const Bone& b = model.bones[static_cast<std::size_t>(i)];
        if (!(b.flags & BF_IK) || !b.ik) continue;
        if (b.ik->target < 0 || b.ik->target >= n) continue;
        Chain chain;
        chain.ik_bone = i;
        chain.start = static_cast<int>(link_bones_.size());
        for (const IKLink& link : b.ik->links) {
            if (link.bone < 0 || link.bone >= n) continue;
            link_bones_.push_back(link.bone);
            link_limited_.push_back(link.limited ? 1 : 0);
            link_limits_.push_back(link);
        }
        chain.count = static_cast<int>(link_bones_.size()) - chain.start;
        if (chain.count > 0) chains_.push_back(chain);
    }

    base_rot.assign(static_cast<std::size_t>(n), identity_quat());
    base_trans.assign(static_cast<std::size_t>(n), Vec3{});
    rot = base_rot;
    trans = base_trans;
    world_.resize(static_cast<std::size_t>(n));
}

void Pose::reset() {
    base_rot.assign(static_cast<std::size_t>(n), identity_quat());
    base_trans.assign(static_cast<std::size_t>(n), Vec3{});
    ov_rot.clear();
    ov_trans.clear();
    ik_euler_.clear();
    ik_enabled.clear();
    ik_clamp_hits = 0;
    rot = base_rot;
    trans = base_trans;
    dirty_ = true;
    apply();
}

void Pose::apply(const MorphWeights* morph_weights) {
    std::vector<Quat> new_rot = base_rot;
    std::vector<Vec3> new_trans = base_trans;
    if (morph_weights) {
        for (const auto& [mi, weight] : *morph_weights) {
            if (weight == 0.0f || mi < 0 || mi >= static_cast<int>(model_.morphs.size()))
                continue;
            const Morph& mo = model_.morphs[static_cast<std::size_t>(mi)];
            if (mo.type != 2) continue;
            for (const MorphOffset& off : mo.offsets) {
                if (off.bone < 0 || off.bone >= n) continue;
                Quat dq = euler_to_quat(off.rot.x, off.rot.y, off.rot.z);
                new_rot[static_cast<std::size_t>(off.bone)] =
                    normalize(quat_mul(new_rot[static_cast<std::size_t>(off.bone)], dq));
                new_trans[static_cast<std::size_t>(off.bone)] += off.move * weight;
            }
        }
    }
    for (const auto& [bi, q] : ov_rot)
        if (bi >= 0 && bi < n) new_rot[static_cast<std::size_t>(bi)] = q;
    for (const auto& [bi, t] : ov_trans)
        if (bi >= 0 && bi < n) new_trans[static_cast<std::size_t>(bi)] = t;

    bool changed = false;
    for (int i = 0; i < n; ++i) {
        if (!same_quat(new_rot[static_cast<std::size_t>(i)], rot[static_cast<std::size_t>(i)]) ||
            !same_vec(new_trans[static_cast<std::size_t>(i)], trans[static_cast<std::size_t>(i)])) {
            changed = true;
            break;
        }
    }
    rot.swap(new_rot);
    trans.swap(new_trans);
    if (changed) dirty_ = true;
}

void Pose::world_update() {
    rot = base_rot;
    trans = base_trans;
    dirty_ = true;
}

void Pose::invalidate_world() { dirty_ = true; }

const std::vector<Mat4>& Pose::world() {
    if (dirty_) compute_world();
    return world_;
}

Mat4 Pose::local_matrix(int bone, const std::vector<Mat4>& W) const {
    static const Mat4 kIdentity = identity4();
    const std::size_t i = static_cast<std::size_t>(bone);
    const int p = parent[i];
    const Mat4& Wp = p >= 0 ? W[static_cast<std::size_t>(p)] : kIdentity;
    Quat q = rot[i];
    Vec3 t_local = rest_off[i] + trans[i];

    const std::uint16_t flags = flags_[i];
    const int src = append_parent_[i];
    if ((flags & (BF_INHERIT_ROT | BF_INHERIT_MOV)) && src >= 0 && src < n && src != bone) {
        const float ratio = model_.bones[i].append_ratio;
        if (ratio != 0.0f) {
            if (flags & BF_INHERIT_ROT) {
                Quat q_src;
                if (flags & BF_LOCAL_APPEND) {
                    q_src = rot[static_cast<std::size_t>(src)];
                } else {
                    const int p_src = parent[static_cast<std::size_t>(src)];
                    const Mat4& Wp_src = p_src >= 0 ? W[static_cast<std::size_t>(p_src)]
                                                    : kIdentity;
                    Mat3 rel = mul(transpose(upper3(Wp_src)),
                                   upper3(W[static_cast<std::size_t>(src)]));
                    q_src = mat3_to_quat(rel);
                }
                q = normalize(quat_mul(slerp_quat(identity_quat(), q_src, ratio), q));
            }
            if (flags & BF_INHERIT_MOV) {
                Vec3 d;
                if (flags & BF_LOCAL_APPEND) {
                    d = trans[static_cast<std::size_t>(src)] * ratio;
                } else {
                    Vec3 d_world = Vec3(W[static_cast<std::size_t>(src)].at(0, 3),
                                        W[static_cast<std::size_t>(src)].at(1, 3),
                                        W[static_cast<std::size_t>(src)].at(2, 3)) -
                                   model_.bones[static_cast<std::size_t>(src)].pos;
                    d = mul(transpose(upper3(Wp)), d_world) * ratio;
                }
                t_local += d;
            }
        }
    }

    return mul(Wp, from_quat_pos(q, t_local));
}

void Pose::compute_world() {
    std::vector<Mat4> W(static_cast<std::size_t>(n));
    for (int bone : eval_order) W[static_cast<std::size_t>(bone)] = local_matrix(bone, W);
    world_.swap(W);
    dirty_ = false;
}

void Pose::apply_physics_world(const std::unordered_map<int, BoneOverride>& target,
                               const MorphWeights* morph_weights) {
    static const Mat4 kIdentity = identity4();
    // 先得到「纯动画」的局部量（rot / trans），物理覆盖在其上计算。
    ov_rot.clear();
    ov_trans.clear();
    apply(morph_weights);

    std::vector<Mat4> W(static_cast<std::size_t>(n));
    for (int bone : eval_order) {
        const std::size_t b = static_cast<std::size_t>(bone);
        const auto it = target.find(bone);
        if (it == target.end()) {
            W[b] = local_matrix(bone, W);
            continue;
        }
        const int p = parent[b];
        const Mat4& Wp = p >= 0 ? W[static_cast<std::size_t>(p)] : kIdentity;
        const Mat4 local = mul(inverse_rigid(Wp), it->second.world);
        const Quat q = mat3_to_quat(upper3(local));
        const Vec3 t = it->second.keep_translation
                           ? trans[b]
                           : Vec3(local.at(0, 3), local.at(1, 3), local.at(2, 3)) - rest_off[b];
        ov_rot[bone] = q;
        ov_trans[bone] = t;
        rot[b] = q;
        trans[b] = t;
        W[b] = mul(Wp, from_quat_pos(q, rest_off[b] + t));
    }
    world_.swap(W);
    dirty_ = false;
}

void Pose::rotate_local(int bone, Quat dq) {
    if (bone < 0 || bone >= n) return;
    const Quat next =
        normalize(quat_mul(base_rot[static_cast<std::size_t>(bone)], dq));
    base_rot[static_cast<std::size_t>(bone)] = next;
    rot[static_cast<std::size_t>(bone)] = next;
    dirty_ = true;
}

void Pose::rotate_world(int bone, Vec3 axis, float angle) {
    if (bone < 0 || bone >= n || std::fabs(angle) < 1e-9f) return;
    const auto& W = world();
    const int p = parent[static_cast<std::size_t>(bone)];
    Mat3 Rp = p >= 0 ? upper3(W[static_cast<std::size_t>(p)]) : Mat3{};
    Quat dq = axis_angle_quat(axis, angle);
    Mat3 dR = quat_to_mat3(dq);
    Mat3 localR = mul(transpose(Rp), mul(dR, Rp));
    const Quat next = normalize(quat_mul(mat3_to_quat(localR),
                                         base_rot[static_cast<std::size_t>(bone)]));
    base_rot[static_cast<std::size_t>(bone)] = next;
    rot[static_cast<std::size_t>(bone)] = next;
    dirty_ = true;
}

void Pose::translate_world(int bone, Vec3 delta) {
    if (bone < 0 || bone >= n) return;
    const auto& W = world();
    const int p = parent[static_cast<std::size_t>(bone)];
    Mat3 Rp = p >= 0 ? upper3(W[static_cast<std::size_t>(p)]) : Mat3{};
    const Vec3 local = mul(transpose(Rp), delta);
    base_trans[static_cast<std::size_t>(bone)] += local;
    trans[static_cast<std::size_t>(bone)] = base_trans[static_cast<std::size_t>(bone)];
    dirty_ = true;
}

void Pose::clear_overrides() {
    ov_rot.clear();
    ov_trans.clear();
    dirty_ = true;
}

void Pose::set_ik_enabled(int bone, bool enabled) {
    if (bone < 0 || bone >= n) return;
    ik_enabled[bone] = enabled;
}

std::unordered_set<int> Pose::changed_subtrees(const std::unordered_set<int>& changed) const {
    std::unordered_set<int> dirty;
    std::vector<int> stack(changed.begin(), changed.end());
    while (!stack.empty()) {
        int bone = stack.back();
        stack.pop_back();
        if (bone < 0 || bone >= n || dirty.count(bone)) continue;
        for (int affected : subtrees[static_cast<std::size_t>(bone)]) {
            if (dirty.insert(affected).second)
                stack.insert(stack.end(), append_users[static_cast<std::size_t>(affected)].begin(),
                             append_users[static_cast<std::size_t>(affected)].end());
        }
    }
    return dirty;
}

std::unordered_set<int> Pose::active_ik_indices(int changed_bone) const {
    std::unordered_set<int> active;
    if (changed_bone < 0 || changed_bone >= n) return active;
    std::unordered_set<int> dirty = changed_subtrees({changed_bone});
    struct IkInfo {
        int index;
        const IK* ik;
    };
    std::vector<IkInfo> ik_bones;
    for (int i = 0; i < n; ++i) {
        const Bone& b = model_.bones[static_cast<std::size_t>(i)];
        if ((b.flags & BF_IK) && b.ik) ik_bones.push_back({i, &*b.ik});
    }
    while (true) {
        bool added = false;
        for (const IkInfo& info : ik_bones) {
            if (active.count(info.index)) continue;
            bool hit = info.index == changed_bone || dirty.count(info.index) ||
                       dirty.count(info.ik->target);
            if (!hit) {
                for (const IKLink& link : info.ik->links)
                    if (dirty.count(link.bone)) { hit = true; break; }
            }
            if (!hit) continue;
            active.insert(info.index);
            auto sub = changed_subtrees({info.index});
            dirty.insert(sub.begin(), sub.end());
            std::unordered_set<int> link_set;
            for (const IKLink& link : info.ik->links)
                if (link.bone >= 0 && link.bone < n) link_set.insert(link.bone);
            if (!link_set.empty()) {
                auto sub2 = changed_subtrees(link_set);
                dirty.insert(sub2.begin(), sub2.end());
            }
            added = true;
        }
        if (!added) return active;
    }
}

int Pose::solve_ik(int max_loops, const std::unordered_set<int>* only) {
    int solved = solve_ik_core(max_loops, only);
    if (ik_reset_links) solved += retry_stuck_chains(max_loops, only);
    if (solved > 0) apply();
    return solved;
}

int Pose::solve_ik_core(int max_loops, const std::unordered_set<int>* only) {
    int solved = 0;
    ik_euler_.clear();

    for (const Chain& chain : chains_) {
        if (only && !only->count(chain.ik_bone)) continue;
        const auto en = ik_enabled.find(chain.ik_bone);
        if (en != ik_enabled.end() && !en->second) continue;
        const IK& ik = *model_.bones[static_cast<std::size_t>(chain.ik_bone)].ik;
        const int target = ik.target;

        // 足 IK 这类「大腿 + 单侧铰链膝」两骨骼链：先把膝弯到目标所需的夹角，再交给
        // CCD 收尾。CCD 从接近伸直的位形出发时每轮只有 0.002 rad，40 轮也弯不到位；
        // 预先弯膝后增量条件数正常，几轮即可收敛。
        if (prebend_knee(chain, ik)) ++solved;

        const auto& W = world();
        const Vec3 goal(W[static_cast<std::size_t>(chain.ik_bone)].at(0, 3),
                        W[static_cast<std::size_t>(chain.ik_bone)].at(1, 3),
                        W[static_cast<std::size_t>(chain.ik_bone)].at(2, 3));
        int iterations = std::max(1, std::min(ik.loop, 200));
        if (max_loops > 0) iterations = std::min(iterations, max_loops);

        for (int iteration = 0; iteration < iterations; ++iteration) {
            world();
            Vec3 eff(W[static_cast<std::size_t>(target)].at(0, 3),
                     W[static_cast<std::size_t>(target)].at(1, 3),
                     W[static_cast<std::size_t>(target)].at(2, 3));
            auto distance = [&]() { return length(goal - eff); };
            if (distance() < 1e-3f) break;
            bool moved = false;

            // 从根（大腿）往靶侧（膝）遍历：先摆大腿再弯膝。反过来先弯膝时，
            // 单侧限位会把膝的增量钳到接近伸直，等大腿再摆回来时膝已经顶在限位上，
            // 腿就卡在 20° 左右弯不下去。
            for (int oi = 0; oi < chain.count; ++oi) {
                const int li = chain.start + (chain.count - 1 - oi);
                const int link_bone = link_bones_[static_cast<std::size_t>(li)];
                world();
                Vec3 pivot(W[static_cast<std::size_t>(link_bone)].at(0, 3),
                           W[static_cast<std::size_t>(link_bone)].at(1, 3),
                           W[static_cast<std::size_t>(link_bone)].at(2, 3));
                Vec3 v1 = eff - pivot;
                Vec3 v2 = goal - pivot;
                float n1 = length(v1), n2 = length(v2);
                if (n1 < 1e-6f || n2 < 1e-6f) continue;
                float cosine = clampf(dot(v1, v2) / (n1 * n2), -1.0f, 1.0f);
                double angle = std::acos(static_cast<double>(cosine));
                if (angle < 1e-4) continue;
                angle = std::min(angle, static_cast<double>(std::max(0.01f, ik.angle)));
                Vec3 axis = cross(v1, v2);
                if (length(axis) < 1e-8f) continue;

                const int p = parent[static_cast<std::size_t>(link_bone)];
                Mat3 Rp = p >= 0 ? upper3(W[static_cast<std::size_t>(p)]) : Mat3{};
                Mat3 dR = quat_to_mat3(axis_angle_quat(axis, static_cast<float>(angle)));
                Mat3 localR = mul(transpose(Rp), mul(dR, Rp));
                Mat3 current = quat_to_mat3(rot[static_cast<std::size_t>(link_bone)]);
                Mat3 new_local = mul(localR, current);
                Quat next_rotation = mat3_to_quat(new_local);

                if (link_limited_[static_cast<std::size_t>(li)]) {
                    const IKLink& limit = link_limits_[static_cast<std::size_t>(li)];
                    bool has_prev = ik_euler_.count(link_bone) != 0;
                    float rx, ry, rz;
                    if (has_prev) {
                        const auto& prev = ik_euler_[link_bone];
                        quat_to_euler_stable(next_rotation, true, prev[0], prev[1], prev[2], rx,
                                             ry, rz);
                    } else {
                        quat_to_euler_stable(next_rotation, false, 0, 0, 0, rx, ry, rz);
                    }
                    // MMD 逐轴钳制：X → Y → Z，每钳完一轴立刻重建四元数再分解下一轴。
                    // 一次性钳三个轴在单侧区间（如膝盖 X ∈ [-π, -0.5°]）会落到错误的
                    // 等价解，膝盖就会反折。
                    bool clipped = false;
                    for (int axis = 0; axis < 3; ++axis) {
                        float nx, ny, nz;
                        quat_to_euler_stable(next_rotation, true, rx, ry, rz, nx, ny, nz);
                        rx = nx;
                        ry = ny;
                        rz = nz;
                        const float v = axis == 0 ? rx : (axis == 1 ? ry : rz);
                        const float lo = axis == 0 ? limit.lo.x : (axis == 1 ? limit.lo.y : limit.lo.z);
                        const float hi = axis == 0 ? limit.hi.x : (axis == 1 ? limit.hi.y : limit.hi.z);
                        const float c = std::min(std::max(v, lo), hi);
                        if (c == v) continue;
                        clipped = true;
                        if (axis == 0) rx = c;
                        else if (axis == 1) ry = c;
                        else rz = c;
                        next_rotation = euler_to_quat(rx, ry, rz);
                    }
                    if (clipped) {
                        if (has_prev) {
                            const auto& prev = ik_euler_[link_bone];
                            if (euler_distance(rx, ry, rz, prev[0], prev[1], prev[2]) < 1e-6f) {
                                // 该轴已经顶在限制上，继续累计只会抖动，舍弃本轮旋转。
                                continue;
                            }
                        }
                        ++ik_clamp_hits;
                    }
                    ik_euler_[link_bone] = {rx, ry, rz};
                }

                base_rot[static_cast<std::size_t>(link_bone)] = next_rotation;
                rot[static_cast<std::size_t>(link_bone)] = next_rotation;
                dirty_ = true;
                moved = true;
                world();
                eff = Vec3(W[static_cast<std::size_t>(target)].at(0, 3),
                           W[static_cast<std::size_t>(target)].at(1, 3),
                           W[static_cast<std::size_t>(target)].at(2, 3));
                if (distance() < 1e-3f) break;
            }
            if (!moved) break;
        }
        ++solved;
    }
    if (solved > 0) dirty_ = true;
    return solved;
}

bool Pose::prebend_knee(const Chain& chain, const IK& ik) {
    if (chain.count != 2) return false;
    const std::size_t base = static_cast<std::size_t>(chain.start);
    const int knee = link_bones_[base];
    const int root = link_bones_[base + 1];
    const int target = ik.target;
    if (knee < 0 || root < 0 || target < 0) return false;
    if (!link_limited_[base] || link_limited_[base + 1]) return false;
    if (parent[static_cast<std::size_t>(knee)] != root ||
        parent[static_cast<std::size_t>(target)] != knee)
        return false;
    const IKLink& lim = link_limits_[base];
    if (std::fabs(lim.lo.y) > 1e-4f || std::fabs(lim.hi.y) > 1e-4f ||
        std::fabs(lim.lo.z) > 1e-4f || std::fabs(lim.hi.z) > 1e-4f)
        return false;

    const auto& W = world();
    auto pos = [&](int b) {
        return Vec3(W[static_cast<std::size_t>(b)].at(0, 3), W[static_cast<std::size_t>(b)].at(1, 3),
                    W[static_cast<std::size_t>(b)].at(2, 3));
    };
    const Vec3 H = pos(root), K = pos(knee), E = pos(target), G = pos(chain.ik_bone);
    const float L1 = length(K - H), L2 = length(E - K);
    const float d0 = length(G - H);
    if (L1 < 1e-3f || L2 < 1e-3f || d0 < 1e-4f) return false;
    const float d = clampf(d0, std::fabs(L1 - L2) + 1e-3f, L1 + L2 - 1e-3f);
    // 余弦定理给出的膝关节夹角：链长 L1/L2、髋到目标 d。伸直时夹角为 π。
    const float interior =
        std::acos(clampf((L1 * L1 + L2 * L2 - d * d) / (2.0f * L1 * L2), -1.0f, 1.0f));
    const float bend = kPi - interior;
    // 本来就接近伸直（夹角几乎为 0）时不需要预先弯膝，交给 CCD 微调即可；
    // 这里只处理「CCD 从低条件数位形出发弯不到目标」的情况。
    if (bend < 0.05f) return false;
    // 单侧限位（膝盖只能朝一侧弯）决定符号；区间跨过 0 时按较近的一侧。
    const float sign = lim.hi.x <= 0.0f ? -1.0f : (lim.lo.x >= 0.0f ? 1.0f : 0.0f);
    if (sign == 0.0f) return false;
    float rx, ry, rz;
    quat_to_euler(rot[static_cast<std::size_t>(knee)], rx, ry, rz);
    const float tx = clampf(sign * bend, lim.lo.x, lim.hi.x);
    if (std::fabs(tx - rx) < 1e-4f) return false;
    rot[static_cast<std::size_t>(knee)] =
        base_rot[static_cast<std::size_t>(knee)] =
            euler_to_quat(tx, clampf(ry, lim.lo.y, lim.hi.y), clampf(rz, lim.lo.z, lim.hi.z));
    dirty_ = true;
    return true;
}

int Pose::retry_stuck_chains(int max_loops, const std::unordered_set<int>* only) {
    int retried = 0;
    const Quat ident = identity_quat();
    for (const Chain& chain : chains_) {
        if (only && !only->count(chain.ik_bone)) continue;
        const IK& ik = *model_.bones[static_cast<std::size_t>(chain.ik_bone)].ik;
        const int target = ik.target;
        const auto& W = world();
        Vec3 goal(W[static_cast<std::size_t>(chain.ik_bone)].at(0, 3),
                  W[static_cast<std::size_t>(chain.ik_bone)].at(1, 3),
                  W[static_cast<std::size_t>(chain.ik_bone)].at(2, 3));
        Vec3 eff(W[static_cast<std::size_t>(target)].at(0, 3),
                 W[static_cast<std::size_t>(target)].at(1, 3),
                 W[static_cast<std::size_t>(target)].at(2, 3));
        if (length(goal - eff) <= ik_retry_tolerance) continue;

        bool all_identity = true;
        for (int li = chain.start; li < chain.start + chain.count; ++li) {
            const Quat& q = rot[static_cast<std::size_t>(link_bones_[static_cast<std::size_t>(li)])];
            if (std::fabs(q.x) >= 1e-6f || std::fabs(q.y) >= 1e-6f || std::fabs(q.z) >= 1e-6f) {
                all_identity = false;
                break;
            }
        }
        if (all_identity) continue;

        std::vector<Quat> prev_rot;
        std::vector<Quat> prev_base;
        prev_rot.reserve(static_cast<std::size_t>(chain.count));
        prev_base.reserve(static_cast<std::size_t>(chain.count));
        for (int li = chain.start; li < chain.start + chain.count; ++li) {
            const int bone = link_bones_[static_cast<std::size_t>(li)];
            prev_rot.push_back(rot[static_cast<std::size_t>(bone)]);
            prev_base.push_back(base_rot[static_cast<std::size_t>(bone)]);
            rot[static_cast<std::size_t>(bone)] = ident;
            base_rot[static_cast<std::size_t>(bone)] = ident;
        }
        dirty_ = true;

        // 用静止姿态重跑一次该链的 CCD。
        const std::unordered_set<int> selected{chain.ik_bone};
        solve_ik_core(max_loops, &selected);

        world();
        Vec3 new_eff(W[static_cast<std::size_t>(target)].at(0, 3),
                     W[static_cast<std::size_t>(target)].at(1, 3),
                     W[static_cast<std::size_t>(target)].at(2, 3));
        if (length(goal - new_eff) >= length(goal - eff) - 1e-3f) {
            for (int li = chain.start; li < chain.start + chain.count; ++li) {
                const int bone = link_bones_[static_cast<std::size_t>(li)];
                rot[static_cast<std::size_t>(bone)] =
                    prev_rot[static_cast<std::size_t>(li - chain.start)];
                base_rot[static_cast<std::size_t>(bone)] =
                    prev_base[static_cast<std::size_t>(li - chain.start)];
            }
            dirty_ = true;
            continue;
        }
        ++retried;
    }
    return retried;
}

}  // namespace pmx

