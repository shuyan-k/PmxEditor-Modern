#include "core/skinning.hpp"

#include <algorithm>
#include <cmath>

namespace pmx {
namespace {

inline Quat quat_from_mat(const Mat3& m) { return mat3_to_quat(m); }

inline Quat dq_mul(Quat a, Quat b) { return quat_mul(a, b); }

// d = 0.5 * (0, t) * q
inline Quat dual_part(Quat q, Vec3 t) {
    // Quat 的分量顺序是 (x, y, z, w)，纯四元数必须把 w 放到末位。
    Quat pure(t.x, t.y, t.z, 0.0f);
    Quat out = quat_mul(pure, q);
    return Quat(out.x * 0.5f, out.y * 0.5f, out.z * 0.5f, out.w * 0.5f);
}

inline Vec3 dual_translation(Quat q, Quat d) {
    Quat conj(-q.x, -q.y, -q.z, q.w);  // 双四元数的共轭：向量取反、实部保留
    Quat out = quat_mul(d, conj);
    return {2.0f * out.x, 2.0f * out.y, 2.0f * out.z};
}

inline Vec3 rotate_by_quat(Quat q, Vec3 v) {
    Quat r = quat_mul(quat_mul(q, Quat(v.x, v.y, v.z, 0.0f)), Quat(-q.x, -q.y, -q.z, q.w));
    return {r.x, r.y, r.z};
}

}  // namespace

SkinDeformer::SkinDeformer(const Model& model) {
    n = static_cast<int>(model.vertices.size());
    bone_count = static_cast<int>(model.bones.size());
    bones.resize(static_cast<std::size_t>(n));
    weights.resize(static_cast<std::size_t>(n));
    types.resize(static_cast<std::size_t>(n));
    sdef = model.vertices.sdef;
    rest.reserve(static_cast<std::size_t>(bone_count));
    for (const Bone& b : model.bones) rest.push_back(b.pos);
    bone_vertices_.assign(static_cast<std::size_t>(bone_count), {});

    for (int i = 0; i < n; ++i) {
        const std::size_t k = static_cast<std::size_t>(i);
        types[k] = runtime_weight_type(model.vertices.wtype[k]);
        bones[k] = model.vertices.bones[k];
        weights[k] = model.vertices.weights[k];
        for (auto& b : bones[k])
            if (b < 0 || b >= bone_count) b = 0;
        const int count = types[k] == WT_BDEF1 ? 1 : ((types[k] == WT_BDEF2 || types[k] == WT_SDEF) ? 2 : 4);
        for (int c = 0; c < count; ++c) {
            if (weights[k][static_cast<std::size_t>(c)] > 0.0f)
                bone_vertices_[static_cast<std::size_t>(bones[k][static_cast<std::size_t>(c)])].push_back(i);
        }
        // 同一骨骼占多个槽时按骨骼批量加法会互相覆盖，这些顶点单独整算。
        for (int a = 0; a < 4; ++a) {
            for (int b2 = a + 1; b2 < 4; ++b2) {
                if (b2 < count && bones[k][static_cast<std::size_t>(a)] ==
                                     bones[k][static_cast<std::size_t>(b2)]) {
                    dup_.push_back(i);
                }
            }
        }
    }
    std::sort(dup_.begin(), dup_.end());
    dup_.erase(std::unique(dup_.begin(), dup_.end()), dup_.end());
}

void SkinDeformer::deform_one(const std::vector<Vec3>& base_pos,
                              const std::vector<Vec3>& base_nrm,
                              const std::vector<Mat4>& world, int vi, Vec3& pos,
                              Vec3& nrm) const {
    const std::size_t k = static_cast<std::size_t>(vi);
    const int wt = types[k];
    const int influence = wt == 0 ? 1 : ((wt == 1 || wt == 3) ? 2 : 4);
    const Vec3 p0 = base_pos[k];
    const Vec3 n0 = base_nrm[k];

    Vec3 position;
    Vec3 normal;
    bool resolved = false;

    if (wt == WT_SDEF) {
        const std::array<float, 9>& sd = sdef[k];
        int b0 = bones[k][0];
        int b1 = bones[k][1];
        if (b0 < 0 || b0 >= bone_count) b0 = 0;
        if (b1 < 0 || b1 >= bone_count) b1 = 0;
        float w1 = clampf(weights[k][1], 0.0f, 1.0f);
        float w0 = 1.0f - w1;
        const Vec3 center(sd[0], sd[1], sd[2]);
        const Vec3 c0 = transform_point(world[static_cast<std::size_t>(b0)], center - rest[static_cast<std::size_t>(b0)]);
        const Vec3 c1 = transform_point(world[static_cast<std::size_t>(b1)], center - rest[static_cast<std::size_t>(b1)]);
        const Vec3 pA = transform_point(world[static_cast<std::size_t>(b0)], p0 - rest[static_cast<std::size_t>(b0)]);
        const Vec3 pB = transform_point(world[static_cast<std::size_t>(b1)], p0 - rest[static_cast<std::size_t>(b1)]);
        const Vec3 blended = c0 * w0 + c1 * w1;
        const Vec3 direction = (pA - c0) * w0 + (pB - c1) * w1;
        float dir_len = length(direction);
        float radius = length(p0 - center);
        Vec3 r0(std::fabs(sd[3] - center.x), std::fabs(sd[4] - center.y), std::fabs(sd[5] - center.z));
        Vec3 r1(std::fabs(sd[6] - center.x), std::fabs(sd[7] - center.y), std::fabs(sd[8] - center.z));
        float rmax = std::max({r0.x, r0.y, r0.z});
        float r1max = std::max({r1.x, r1.y, r1.z});
        bool has_r1 = std::fabs(sd[6]) > 1e-6f || std::fabs(sd[7]) > 1e-6f || std::fabs(sd[8]) > 1e-6f;
        Vec3 axes = has_r1 ? r1 : r0;
        float amax = has_r1 ? r1max : rmax;
        if (amax > 1e-6f && dir_len > 1e-6f) {
            const Mat3 R0 = upper3(world[static_cast<std::size_t>(b0)]);
            Vec3 d_rest = p0 - center;
            Vec3 dl_cur = mul(transpose(R0), direction);
            float rest_len = length(d_rest);
            float len_rest = length(d_rest);
            float len_cur = length(dl_cur);
            if (rest_len > 1e-6f && len_rest > 1e-6f && len_cur > 1e-6f) {
                float sum_rest = 0.0f, sum_cur = 0.0f;
                for (int axis = 0; axis < 3; ++axis) {
                    float a = std::fabs(axes[axis]);
                    if (a < 1e-6f) a = amax;
                    float tr = (d_rest[axis] / len_rest) / a;
                    float tc = (dl_cur[axis] / len_cur) / a;
                    sum_rest += tr * tr;
                    sum_cur += tc * tc;
                }
                if (sum_rest > 1e-12f && sum_cur > 1e-12f) {
                    radius = rest_len * std::sqrt(sum_rest / sum_cur);
                    radius = clampf(radius, rest_len * 0.6f, rest_len * 1.4f);
                }
            }
        }
        if (dir_len > 1e-6f && radius > 1e-6f) {
            position = blended + direction * (radius / dir_len);
            resolved = true;
        }
    }

    if (wt <= WT_BDEF4 && influence >= 2 && !resolved) {
        // 双四元数混合：BDEF2/BDEF4/QDEF 共用螺旋插值，避免线性蒙皮在
        // 「大角度弯曲 + 轴向自转」时拧成糖纸。
        Quat qsum(0.0f, 0.0f, 0.0f, 0.0f);
        Quat dsum(0.0f, 0.0f, 0.0f, 0.0f);
        Quat reference;
        bool has_reference = false;
        float weight_sum = 0.0f;
        for (int slot = 0; slot < influence; ++slot) {
            const float w = weights[k][static_cast<std::size_t>(slot)];
            if (w <= 0.0f) continue;
            const int bone = bones[k][static_cast<std::size_t>(slot)];
            const Mat4& M = world[static_cast<std::size_t>(bone)];
            Quat q = quat_from_mat(upper3(M));
            Vec3 t(M.at(0, 3), M.at(1, 3), M.at(2, 3));
            Vec3 translation = t - mul(upper3(M), rest[static_cast<std::size_t>(bone)]);
            Quat d = dual_part(q, translation);
            float sign = 1.0f;
            if (!has_reference) {
                reference = q;
                has_reference = true;
            } else if (quat_dot(q, reference) < 0.0f) {
                sign = -1.0f;
            }
            qsum.x += q.x * w * sign;
            qsum.y += q.y * w * sign;
            qsum.z += q.z * w * sign;
            qsum.w += q.w * w * sign;
            dsum.x += d.x * w * sign;
            dsum.y += d.y * w * sign;
            dsum.z += d.z * w * sign;
            dsum.w += d.w * w * sign;
            weight_sum += w;
        }
        float q_len = std::sqrt(qsum.x * qsum.x + qsum.y * qsum.y + qsum.z * qsum.z + qsum.w * qsum.w);
        if (weight_sum > 1e-6f && q_len > 1e-6f) {
            float inv = 1.0f / q_len;
            qsum = Quat(qsum.x * inv, qsum.y * inv, qsum.z * inv, qsum.w * inv);
            dsum = Quat(dsum.x * inv, dsum.y * inv, dsum.z * inv, dsum.w * inv);
            position = rotate_by_quat(qsum, p0) + dual_translation(qsum, dsum);
            resolved = true;
        }
    }

    for (int slot = 0; slot < influence; ++slot) {
        const int bone = bones[k][static_cast<std::size_t>(slot)];
        const float w = weights[k][static_cast<std::size_t>(slot)];
        const Mat4& M = world[static_cast<std::size_t>(bone)];
        if (!resolved) {
            Vec3 tp = transform_point(M, p0 - rest[static_cast<std::size_t>(bone)]);
            position += tp * w;
        }
        normal += transform_dir(M, n0) * w;
    }

    float nlen = length(normal);
    if (nlen >= 1e-6f) normal = normal / nlen;
    pos = position;
    nrm = normal;
}

void SkinDeformer::deform(const std::vector<Vec3>& base_pos, const std::vector<Vec3>& base_nrm,
                          const std::vector<Mat4>& world, std::vector<Vec3>& out_pos,
                          std::vector<Vec3>& out_nrm) const {
    out_pos.resize(static_cast<std::size_t>(n));
    out_nrm.resize(static_cast<std::size_t>(n));
    for (int i = 0; i < n; ++i) deform_one(base_pos, base_nrm, world, i, out_pos[static_cast<std::size_t>(i)],
                                           out_nrm[static_cast<std::size_t>(i)]);
}

void SkinDeformer::deform_subset(const std::vector<Vec3>& base_pos,
                                 const std::vector<Vec3>& base_nrm,
                                 const std::vector<Mat4>& world,
                                 const std::vector<int>& dirty_bones, std::vector<Vec3>& prev_pos,
                                 std::vector<Vec3>& prev_nrm) const {
    if (static_cast<int>(prev_pos.size()) != n || static_cast<int>(prev_nrm.size()) != n ||
        dirty_bones.size() > bone_vertices_.size() * 3 / 10) {
        deform(base_pos, base_nrm, world, prev_pos, prev_nrm);
        return;
    }
    std::vector<int> affected;
    for (int bone : dirty_bones) {
        if (bone < 0 || bone >= bone_count) continue;
        affected.insert(affected.end(), bone_vertices_[static_cast<std::size_t>(bone)].begin(),
                        bone_vertices_[static_cast<std::size_t>(bone)].end());
    }
    std::sort(affected.begin(), affected.end());
    affected.erase(std::unique(affected.begin(), affected.end()), affected.end());
    if (static_cast<int>(affected.size()) > n * 3 / 10) {
        deform(base_pos, base_nrm, world, prev_pos, prev_nrm);
        return;
    }
    for (int vi : affected) {
        deform_one(base_pos, base_nrm, world, vi, prev_pos[static_cast<std::size_t>(vi)],
                   prev_nrm[static_cast<std::size_t>(vi)]);
    }
}

}  // namespace pmx
