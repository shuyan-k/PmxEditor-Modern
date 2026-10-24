#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <initializer_list>
#include <stdexcept>
#include <string>
#include <utility>

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

struct BWWorld;

extern "C" {
__declspec(dllimport) void bw_set_body(
    BWWorld*, int, const float*, const float*);
__declspec(dllimport) void bw_get_body(
    BWWorld*, int, float*, float*);
__declspec(dllimport) void bw_step(BWWorld*, float, int);
}

namespace py = pybind11;

template <typename T>
using Array = py::array_t<T, py::array::c_style>;

void require_shape(const py::buffer_info& info, const char* name,
                   std::initializer_list<py::ssize_t> shape) {
    if (info.ndim != static_cast<py::ssize_t>(shape.size())) {
        throw py::value_error(std::string(name) + " has an invalid rank");
    }
    std::size_t axis = 0;
    for (const auto expected : shape) {
        if (expected >= 0 && info.shape[axis] != expected) {
            throw py::value_error(std::string(name) + " has an invalid shape");
        }
        ++axis;
    }
}

inline void transform_point(const float* matrix, const float* point,
                            const float* rest, float* out, bool translate) {
    for (int row = 0; row < 3; ++row) {
        float value = translate ? matrix[row * 4 + 3] : 0.0f;
        for (int col = 0; col < 3; ++col) {
            value += matrix[row * 4 + col] *
                (point[col] - (rest ? rest[col] : 0.0f));
        }
        out[row] += value;
    }
}

inline void quat_from_matrix(const float* m, float* q) {
    // 行主序 4x4：m[row * 4 + col]
    const float trace = m[0] + m[5] + m[10];
    if (trace > 0.0f) {
        const float s = std::sqrt(trace + 1.0f) * 2.0f;
        q[0] = 0.25f * s;
        q[1] = (m[9] - m[6]) / s;
        q[2] = (m[2] - m[8]) / s;
        q[3] = (m[4] - m[1]) / s;
    } else if (m[0] > m[5] && m[0] > m[10]) {
        const float s = std::sqrt(1.0f + m[0] - m[5] - m[10]) * 2.0f;
        q[0] = (m[9] - m[6]) / s;
        q[1] = 0.25f * s;
        q[2] = (m[1] + m[4]) / s;
        q[3] = (m[2] + m[8]) / s;
    } else if (m[5] > m[10]) {
        const float s = std::sqrt(1.0f + m[5] - m[0] - m[10]) * 2.0f;
        q[0] = (m[2] - m[8]) / s;
        q[1] = (m[1] + m[4]) / s;
        q[2] = 0.25f * s;
        q[3] = (m[6] + m[9]) / s;
    } else {
        const float s = std::sqrt(1.0f + m[10] - m[0] - m[5]) * 2.0f;
        q[0] = (m[4] - m[1]) / s;
        q[1] = (m[2] + m[8]) / s;
        q[2] = (m[6] + m[9]) / s;
        q[3] = 0.25f * s;
    }
    const float len = std::sqrt(q[0] * q[0] + q[1] * q[1] +
                                q[2] * q[2] + q[3] * q[3]);
    if (len > 1e-8f) {
        const float inv = 1.0f / len;
        for (int i = 0; i < 4; ++i) q[i] *= inv;
    }
}

// 四元数乘法（w 在前），与 NumPy 参考实现保持一致。
inline void quat_mul(const float* a, const float* b, float* out) {
    out[0] = a[0] * b[0] - a[1] * b[1] - a[2] * b[2] - a[3] * b[3];
    out[1] = a[0] * b[1] + a[1] * b[0] + a[2] * b[3] - a[3] * b[2];
    out[2] = a[0] * b[2] - a[1] * b[3] + a[2] * b[0] + a[3] * b[1];
    out[3] = a[0] * b[3] + a[1] * b[2] - a[2] * b[1] + a[3] * b[0];
}

// 把 (旋转 q, 平移 t) 转成双四元数：d = 0.5 * (0, t) * q
inline void dual_from_quat(const float* q, const float* t, float* d) {
    const float pure[4] = {0.0f, t[0], t[1], t[2]};
    float out[4];
    quat_mul(pure, q, out);
    for (int i = 0; i < 4; ++i) d[i] = 0.5f * out[i];
}

inline void dual_translation(const float* q, const float* d, float* t) {
    const float conj[4] = {q[0], -q[1], -q[2], -q[3]};
    float out[4];
    quat_mul(d, conj, out);
    for (int i = 0; i < 3; ++i) t[i] = 2.0f * out[i + 1];
}

inline void rotate_by_quat(const float* q, const float* v, float* out) {
    const float tx = 2.0f * (q[2] * v[2] - q[3] * v[1]);
    const float ty = 2.0f * (q[3] * v[0] - q[1] * v[2]);
    const float tz = 2.0f * (q[1] * v[1] - q[2] * v[0]);
    out[0] = v[0] + q[0] * tx + q[2] * tz - q[3] * ty;
    out[1] = v[1] + q[0] * ty + q[3] * tx - q[1] * tz;
    out[2] = v[2] + q[0] * tz + q[1] * ty - q[2] * tx;
}

// 与 transform_point 相同，但直接写出结果：W * (p - rest) + t
inline void transform_delta(const float* matrix, const float* point,
                            const float* rest, float* out) {
    for (int row = 0; row < 3; ++row) {
        float value = matrix[row * 4 + 3];
        for (int col = 0; col < 3; ++col) {
            value += matrix[row * 4 + col] * (point[col] - rest[col]);
        }
        out[row] = value;
    }
}

void deform_vertices(
    const float* base_pos, const float* base_nrm, const std::int32_t* bones,
    const float* weights, const std::uint8_t* weight_types,
    const float* rest_pos, const float* world, const std::int32_t* indices,
    py::ssize_t count, py::ssize_t vertex_count, py::ssize_t bone_count,
    float* out_pos, float* out_nrm, const float* sdef) {
    for (py::ssize_t item = 0; item < count; ++item) {
        const auto vi = indices ? indices[item] : static_cast<std::int32_t>(item);
        if (vi < 0 || vi >= vertex_count) {
            throw std::out_of_range("vertex index is out of range");
        }

        const int weight_type = weight_types[vi];
        const int influence_count = weight_type == 0
            ? 1
            : ((weight_type == 1 || weight_type == 3) ? 2 : 4);
        std::array<int, 4> slots = {0, 1, 2, 3};
        std::stable_sort(slots.begin(), slots.begin() + influence_count,
            [bones, vi, bone_count](int a, int b) {
                auto bone_a = bones[vi * 4 + a];
                auto bone_b = bones[vi * 4 + b];
                if (bone_a < 0 || bone_a >= bone_count) bone_a = 0;
                if (bone_b < 0 || bone_b >= bone_count) bone_b = 0;
                return bone_a < bone_b;
            });

        float normal[3] = {};
        float position[3] = {};
        bool resolved = false;

        // SDEF：中心 C 随两根骨骼变换后混合，顶点偏移方向混合后按静止半径外推，
        // 这样弯曲时顶点落在球面上，而不是像线性混合那样沿弦线收缩（R0/R1 暂未使用）。
        if (weight_type == 3 && sdef != nullptr) {
            const float* sd = sdef + vi * 9;
            int b0 = bones[vi * 4 + 0];
            int b1 = bones[vi * 4 + 1];
            if (b0 < 0 || b0 >= bone_count) b0 = 0;
            if (b1 < 0 || b1 >= bone_count) b1 = 0;
            float w1 = weights[vi * 4 + 1];
            if (w1 < 0.0f) w1 = 0.0f;
            if (w1 > 1.0f) w1 = 1.0f;
            const float w0 = 1.0f - w1;
            const float center[3] = {sd[0], sd[1], sd[2]};
            float c0[3], c1[3], p0[3], p1[3];
            transform_delta(world + b0 * 16, center, rest_pos + b0 * 3, c0);
            transform_delta(world + b1 * 16, center, rest_pos + b1 * 3, c1);
            transform_delta(world + b0 * 16, base_pos + vi * 3,
                            rest_pos + b0 * 3, p0);
            transform_delta(world + b1 * 16, base_pos + vi * 3,
                            rest_pos + b1 * 3, p1);
            float blended_c[3];
            float direction[3];
            for (int axis = 0; axis < 3; ++axis) {
                blended_c[axis] = c0[axis] * w0 + c1[axis] * w1;
                direction[axis] = (p0[axis] - c0[axis]) * w0 +
                                  (p1[axis] - c1[axis]) * w1;
            }
            const float dir_len = std::sqrt(
                direction[0] * direction[0] + direction[1] * direction[1] +
                direction[2] * direction[2]);
            float radius = std::sqrt(
                (base_pos[vi * 3 + 0] - center[0]) *
                    (base_pos[vi * 3 + 0] - center[0]) +
                (base_pos[vi * 3 + 1] - center[1]) *
                    (base_pos[vi * 3 + 1] - center[1]) +
                (base_pos[vi * 3 + 2] - center[2]) *
                    (base_pos[vi * 3 + 2] - center[2]));
            // R0/R1 在 PMX 文件里存的是「点」而不是半径向量：模型库里实测
            // R0-C 与 R1-C 恒为 180° 反向、|R0| 达到骨骼长度量级（10+），
            // 只有逐轴 |R-C| 才是可信的半轴（0.1~0.3）。静止姿态必须还原
            // 静止位置，所以半径取"静止距离 x 椭球伸缩比"：
            //   radius = |v - C| * ell(u_cur) / ell(u_rest)
            // 其中 ell(u) = 1/sqrt(sum((u_i/a_i)^2))，a_i = |R-C|。全零时保持球面半径。
            const float r0[3] = {std::fabs(sd[3] - center[0]),
                                 std::fabs(sd[4] - center[1]),
                                 std::fabs(sd[5] - center[2])};
            const float r1[3] = {std::fabs(sd[6] - center[0]),
                                 std::fabs(sd[7] - center[1]),
                                 std::fabs(sd[8] - center[2])};
            const float rmax = std::max(r0[0], std::max(r0[1], r0[2]));
            const float r1max = std::max(r1[0], std::max(r1[1], r1[2]));
            // R1 是形变后的椭球半轴。静止姿态必须逐位还原，因此静止方向与
            // 当前方向都用同一组半轴比较（R1 优先，全零时回退 R0），未变形
            // 时比值恒为 1；R1 与 R0 相等时与原实现完全一致。
            // 是否给了 R1 要看原始值：R1 全零表示"没有 R1"，但 C 非零时
            // |0-C| 不为零，不能用平移后的半轴来判定。
            const bool has_r1 = std::fabs(sd[6]) > 1e-6f ||
                                std::fabs(sd[7]) > 1e-6f ||
                                std::fabs(sd[8]) > 1e-6f;
            const float* axes = has_r1 ? r1 : r0;
            const float amax = has_r1 ? r1max : rmax;
            if (amax > 1e-6f && dir_len > 1e-6f) {
                const float* W0 = world + b0 * 16;
                const float d_rest[3] = {base_pos[vi * 3 + 0] - center[0],
                                         base_pos[vi * 3 + 1] - center[1],
                                         base_pos[vi * 3 + 2] - center[2]};
                float dl_rest[3];
                float dl_cur[3];
                for (int col = 0; col < 3; ++col) {
                    // 静止方向直接用模型空间偏移（R0/R1 也是模型空间半轴），
                    // 方向只用旋转部分转回骨骼 0 的本地坐标系做比较；
                    // 若两者都乘 W0，静止与弯曲时比值恒为 1，R0 就失去意义。
                    dl_rest[col] = d_rest[col];
                    dl_cur[col] = W0[0 * 4 + col] * direction[0] +
                                  W0[1 * 4 + col] * direction[1] +
                                  W0[2 * 4 + col] * direction[2];
                }
                const float rest_len = std::sqrt(d_rest[0] * d_rest[0] +
                                                 d_rest[1] * d_rest[1] +
                                                 d_rest[2] * d_rest[2]);
                const float len_rest = std::sqrt(dl_rest[0] * dl_rest[0] +
                                                 dl_rest[1] * dl_rest[1] +
                                                 dl_rest[2] * dl_rest[2]);
                const float len_cur = std::sqrt(dl_cur[0] * dl_cur[0] +
                                                dl_cur[1] * dl_cur[1] +
                                                dl_cur[2] * dl_cur[2]);
                if (rest_len > 1e-6f && len_rest > 1e-6f && len_cur > 1e-6f) {
                    float sum_rest = 0.0f;
                    float sum_cur = 0.0f;
                    for (int axis = 0; axis < 3; ++axis) {
                        float a = std::fabs(axes[axis]);
                        if (a < 1e-6f) a = amax;  // 退化轴用最大半轴兜底
                        const float tr = (dl_rest[axis] / len_rest) / a;
                        const float tc = (dl_cur[axis] / len_cur) / a;
                        sum_rest += tr * tr;
                        sum_cur += tc * tc;
                    }
                    if (sum_rest > 1e-12f && sum_cur > 1e-12f) {
                        radius = rest_len * std::sqrt(sum_rest / sum_cur);
                        // 椭球比在极端弯曲时会给出离谱半径（实测到 4.8 单位），把修正量
                        // 夹在 [0.6, 1.4] 倍静止半径内，保证不会撕裂网格。
                        if (radius < rest_len * 0.6f) radius = rest_len * 0.6f;
                        else if (radius > rest_len * 1.4f) radius = rest_len * 1.4f;
                    }
                }
            }
            if (dir_len > 1e-6f && radius > 1e-6f) {
                const float scale = radius / dir_len;
                for (int axis = 0; axis < 3; ++axis) {
                    position[axis] = blended_c[axis] + direction[axis] * scale;
                }
                resolved = true;
            }
        }

        // 双四元数混合（DQS）：BDEF2/BDEF4 与 QDEF 共用同一套螺旋插值，
        // 避免线性混合在「关节大角度弯曲 + 轴向自转」时的"糖纸"式扭曲
        // （实测米娅帧 136 膝盖弯 49°、大腿自转 88°，线性蒙皮在接缝处拧成螺旋）。
        if (weight_type <= 2 && influence_count >= 2 && !resolved) {
            float qsum[4] = {0.0f, 0.0f, 0.0f, 0.0f};
            float dsum[4] = {0.0f, 0.0f, 0.0f, 0.0f};
            float reference[4] = {0.0f, 0.0f, 0.0f, 0.0f};
            bool has_reference = false;
            float weight_sum = 0.0f;
            for (int ordered = 0; ordered < influence_count; ++ordered) {
                const int slot = slots[ordered];
                const float weight = weights[vi * 4 + slot];
                if (weight <= 0.0f) continue;
                int bone = bones[vi * 4 + slot];
                if (bone < 0 || bone >= bone_count) bone = 0;
                const float* matrix = world + bone * 16;
                const float* rest = rest_pos + bone * 3;
                float q[4];
                quat_from_matrix(matrix, q);
                float translation[3];
                // 增量形式：t_i - R_i * rest_i
                for (int row = 0; row < 3; ++row) {
                    translation[row] = matrix[row * 4 + 3];
                    for (int col = 0; col < 3; ++col) {
                        translation[row] -=
                            matrix[row * 4 + col] * rest[col];
                    }
                }
                float d[4];
                dual_from_quat(q, translation, d);
                float sign = 1.0f;
                if (!has_reference) {
                    for (int i = 0; i < 4; ++i) reference[i] = q[i];
                    has_reference = true;
                } else {
                    float dot = q[0] * reference[0] + q[1] * reference[1] +
                                q[2] * reference[2] + q[3] * reference[3];
                    if (dot < 0.0f) sign = -1.0f;
                }
                for (int i = 0; i < 4; ++i) {
                    qsum[i] += q[i] * weight * sign;
                    dsum[i] += d[i] * weight * sign;
                }
                weight_sum += weight;
            }
            const float q_len = std::sqrt(
                qsum[0] * qsum[0] + qsum[1] * qsum[1] +
                qsum[2] * qsum[2] + qsum[3] * qsum[3]);
            if (weight_sum > 1e-6f && q_len > 1e-6f) {
                const float inv = 1.0f / q_len;
                for (int i = 0; i < 4; ++i) {
                    qsum[i] *= inv;
                    dsum[i] *= inv;
                }
                float translated[3];
                rotate_by_quat(qsum, base_pos + vi * 3, position);
                dual_translation(qsum, dsum, translated);
                for (int axis = 0; axis < 3; ++axis) {
                    position[axis] += translated[axis];
                }
                resolved = true;
            }
        }

        for (int ordered_slot = 0; ordered_slot < influence_count;
             ++ordered_slot) {
            const int slot = slots[ordered_slot];
            auto bone = bones[vi * 4 + slot];
            if (bone < 0 || bone >= bone_count) bone = 0;
            const float weight = weights[vi * 4 + slot];
            const float* matrix = world + bone * 16;
            const float* rest = rest_pos + bone * 3;
            if (!resolved) {
                float transformed_pos[3] = {};
                transform_point(matrix, base_pos + vi * 3, rest,
                                transformed_pos, true);
                for (int axis = 0; axis < 3; ++axis) {
                    position[axis] += transformed_pos[axis] * weight;
                }
            }
            float transformed_nrm[3] = {};
            transform_point(matrix, base_nrm + vi * 3, nullptr,
                            transformed_nrm, false);
            for (int axis = 0; axis < 3; ++axis) {
                normal[axis] += transformed_nrm[axis] * weight;
            }
        }

        const float normal_length = std::sqrt(
            normal[0] * normal[0] + normal[1] * normal[1] +
            normal[2] * normal[2]);
        if (normal_length >= 1e-6f) {
            const float inverse_length = 1.0f / normal_length;
            for (float& component : normal) component *= inverse_length;
        }
        for (int axis = 0; axis < 3; ++axis) {
            out_pos[vi * 3 + axis] = position[axis];
            out_nrm[vi * 3 + axis] = normal[axis];
        }
    }
}


py::tuple deform(
    Array<float> base_pos, Array<float> base_nrm, Array<std::int32_t> bones,
    Array<float> weights, Array<std::uint8_t> weight_types,
    Array<float> rest_pos, Array<float> world, Array<float> sdef) {
    const auto pos_info = base_pos.request();
    const auto nrm_info = base_nrm.request();
    const auto bones_info = bones.request();
    const auto weights_info = weights.request();
    const auto type_info = weight_types.request();
    const auto rest_info = rest_pos.request();
    const auto world_info = world.request();
    const auto sdef_info = sdef.request();
    const auto vertex_count = pos_info.shape[0];
    const auto bone_count = rest_info.shape[0];
    require_shape(nrm_info, "base_nrm", {vertex_count, 3});
    require_shape(bones_info, "bones", {vertex_count, 4});
    require_shape(weights_info, "weights", {vertex_count, 4});
    require_shape(type_info, "weight_types", {vertex_count});
    require_shape(rest_info, "rest_pos", {-1, 3});
    require_shape(world_info, "world", {bone_count, 4, 4});
    require_shape(sdef_info, "sdef", {vertex_count, 9});
    require_shape(pos_info, "base_pos", {-1, 3});

    py::array_t<float> out_pos({vertex_count, py::ssize_t(3)});
    py::array_t<float> out_nrm({vertex_count, py::ssize_t(3)});
    auto out_pos_info = out_pos.request();
    auto out_nrm_info = out_nrm.request();
    const auto* bone_ptr = bones.data();
    const auto* weight_ptr = weights.data();
    const auto* type_ptr = weight_types.data();
    const auto* pos_ptr = base_pos.data();
    const auto* nrm_ptr = base_nrm.data();
    const auto* rest_ptr = rest_pos.data();
    const auto* world_ptr = world.data();
    auto* pos_out_ptr = static_cast<float*>(out_pos_info.ptr);
    auto* nrm_out_ptr = static_cast<float*>(out_nrm_info.ptr);
    {
        py::gil_scoped_release release;
        deform_vertices(pos_ptr, nrm_ptr, bone_ptr, weight_ptr, type_ptr,
                        rest_ptr, world_ptr, nullptr, vertex_count,
                        vertex_count, bone_count, pos_out_ptr, nrm_out_ptr,
                        sdef.data());
    }
    return py::make_tuple(std::move(out_pos), std::move(out_nrm));
}

py::tuple deform_subset(
    Array<float> base_pos, Array<float> base_nrm, Array<std::int32_t> bones,
    Array<float> weights, Array<std::uint8_t> weight_types,
    Array<float> rest_pos, Array<float> world, Array<std::int32_t> indices,
    Array<float> previous_pos, Array<float> previous_nrm, Array<float> sdef) {
    const auto pos_info = base_pos.request();
    const auto nrm_info = base_nrm.request();
    const auto bones_info = bones.request();
    const auto weights_info = weights.request();
    const auto type_info = weight_types.request();
    const auto rest_info = rest_pos.request();
    const auto world_info = world.request();
    const auto sdef_info = sdef.request();
    const auto indices_info = indices.request();
    const auto previous_pos_info = previous_pos.request();
    const auto previous_nrm_info = previous_nrm.request();
    const auto vertex_count = pos_info.shape[0];
    const auto bone_count = rest_info.shape[0];
    require_shape(nrm_info, "base_nrm", {vertex_count, 3});
    require_shape(bones_info, "bones", {vertex_count, 4});
    require_shape(weights_info, "weights", {vertex_count, 4});
    require_shape(type_info, "weight_types", {vertex_count});
    require_shape(rest_info, "rest_pos", {-1, 3});
    require_shape(world_info, "world", {bone_count, 4, 4});
    require_shape(sdef_info, "sdef", {vertex_count, 9});
    require_shape(pos_info, "base_pos", {-1, 3});
    require_shape(indices_info, "indices", {-1});
    require_shape(previous_pos_info, "previous_pos", {vertex_count, 3});
    require_shape(previous_nrm_info, "previous_nrm", {vertex_count, 3});

    py::array_t<float> out_pos({vertex_count, py::ssize_t(3)});
    py::array_t<float> out_nrm({vertex_count, py::ssize_t(3)});
    std::copy_n(previous_pos.data(), vertex_count * 3, out_pos.mutable_data());
    std::copy_n(previous_nrm.data(), vertex_count * 3, out_nrm.mutable_data());
    const auto* index_ptr = indices.data();
    const auto* bone_ptr = bones.data();
    const auto* weight_ptr = weights.data();
    const auto* type_ptr = weight_types.data();
    const auto* pos_ptr = base_pos.data();
    const auto* nrm_ptr = base_nrm.data();
    const auto* rest_ptr = rest_pos.data();
    const auto* world_ptr = world.data();
    auto* pos_out_ptr = out_pos.mutable_data();
    auto* nrm_out_ptr = out_nrm.mutable_data();
    {
        py::gil_scoped_release release;
        deform_vertices(pos_ptr, nrm_ptr, bone_ptr, weight_ptr, type_ptr,
                        rest_ptr, world_ptr, index_ptr, indices_info.shape[0],
                        vertex_count, bone_count, pos_out_ptr, nrm_out_ptr,
                        sdef.data());
    }
    return py::make_tuple(std::move(out_pos), std::move(out_nrm));
}

std::array<float, 4> euler_quaternion(float x, float y, float z);
std::array<float, 4> multiply_quaternion(const float* a, const float* b);

py::tuple apply_vertex_morphs(
    Array<float> base_positions, Array<float> base_uv,
    Array<std::int32_t> morph_indices, Array<float> morph_weights,
    Array<std::int32_t> position_starts,
    Array<std::int32_t> position_vertices, Array<float> position_offsets,
    Array<std::int32_t> uv_starts, Array<std::int32_t> uv_vertices,
    Array<float> uv_offsets) {
    const auto position_info = base_positions.request();
    const auto uv_info = base_uv.request();
    const auto index_info = morph_indices.request();
    const auto weight_info = morph_weights.request();
    const auto position_starts_info = position_starts.request();
    const auto position_vertices_info = position_vertices.request();
    const auto position_offsets_info = position_offsets.request();
    const auto uv_starts_info = uv_starts.request();
    const auto uv_vertices_info = uv_vertices.request();
    const auto uv_offsets_info = uv_offsets.request();
    const auto morph_count = position_starts_info.shape[0] - 1;
    const auto vertex_count = position_info.shape[0];
    require_shape(position_info, "base_positions", {-1, 3});
    require_shape(uv_info, "base_uv", {vertex_count, 2});
    require_shape(index_info, "morph_indices", {-1});
    require_shape(weight_info, "morph_weights", {index_info.shape[0]});
    require_shape(position_starts_info, "position_starts", {morph_count + 1});
    require_shape(position_vertices_info, "position_vertices", {-1});
    require_shape(position_offsets_info, "position_offsets",
                  {position_vertices_info.shape[0], 3});
    require_shape(uv_starts_info, "uv_starts", {morph_count + 1});
    require_shape(uv_vertices_info, "uv_vertices", {-1});
    require_shape(uv_offsets_info, "uv_offsets",
                  {uv_vertices_info.shape[0], 2});

    bool has_position = false;
    bool has_uv = false;
    for (py::ssize_t i = 0; i < index_info.shape[0]; ++i) {
        const int morph = morph_indices.data()[i];
        if (morph < 0 || morph >= morph_count || morph_weights.data()[i] == 0) {
            continue;
        }
        has_position |= position_starts.data()[morph + 1] >
                        position_starts.data()[morph];
        has_uv |= uv_starts.data()[morph + 1] > uv_starts.data()[morph];
    }
    if (!has_position && !has_uv) {
        return py::make_tuple(base_positions, base_uv);
    }

    py::array_t<float> out_positions = has_position
        ? py::array_t<float>({vertex_count, py::ssize_t(3)})
        : py::array_t<float>();
    py::array_t<float> out_uv = has_uv
        ? py::array_t<float>({vertex_count, py::ssize_t(2)})
        : py::array_t<float>();
    if (has_position) {
        std::copy_n(base_positions.data(), vertex_count * 3,
                    out_positions.mutable_data());
    }
    if (has_uv) {
        std::copy_n(base_uv.data(), vertex_count * 2, out_uv.mutable_data());
    }
    auto* output_positions = has_position ? out_positions.mutable_data() : nullptr;
    auto* output_uv = has_uv ? out_uv.mutable_data() : nullptr;
    const auto* active_indices = morph_indices.data();
    const auto* active_weights = morph_weights.data();
    const auto* position_start_ptr = position_starts.data();
    const auto* position_vertex_ptr = position_vertices.data();
    const auto* position_offset_ptr = position_offsets.data();
    const auto* uv_start_ptr = uv_starts.data();
    const auto* uv_vertex_ptr = uv_vertices.data();
    const auto* uv_offset_ptr = uv_offsets.data();
    {
        py::gil_scoped_release release;
        for (py::ssize_t active = 0; active < index_info.shape[0]; ++active) {
            const int morph = active_indices[active];
            const float weight = active_weights[active];
            if (morph < 0 || morph >= morph_count || weight == 0) continue;
            if (has_position) {
                const int start = position_start_ptr[morph];
                const int end = position_start_ptr[morph + 1];
                for (int offset = start; offset < end; ++offset) {
                    const int vertex = position_vertex_ptr[offset];
                    if (vertex < 0 || vertex >= vertex_count) continue;
                    for (int axis = 0; axis < 3; ++axis) {
                        output_positions[vertex * 3 + axis] +=
                            position_offset_ptr[offset * 3 + axis] * weight;
                    }
                }
            }
            if (has_uv) {
                const int start = uv_start_ptr[morph];
                const int end = uv_start_ptr[morph + 1];
                for (int offset = start; offset < end; ++offset) {
                    const int vertex = uv_vertex_ptr[offset];
                    if (vertex < 0 || vertex >= vertex_count) continue;
                    for (int axis = 0; axis < 2; ++axis) {
                        output_uv[vertex * 2 + axis] +=
                            uv_offset_ptr[offset * 2 + axis] * weight;
                    }
                }
            }
        }
    }
    py::object positions_result = has_position
        ? py::object(std::move(out_positions)) : py::object(base_positions);
    py::object uv_result = has_uv
        ? py::object(std::move(out_uv)) : py::object(base_uv);
    return py::make_tuple(std::move(positions_result), std::move(uv_result));
}

py::tuple apply_bone_morphs(
    Array<float> base_rotations, Array<float> base_translations,
    Array<std::int32_t> morph_indices, Array<float> morph_weights,
    Array<std::int32_t> morph_starts, Array<std::int32_t> morph_bones,
    Array<float> morph_rotations, Array<float> morph_translations) {
    const auto rotation_info = base_rotations.request();
    const auto translation_info = base_translations.request();
    const auto index_info = morph_indices.request();
    const auto weight_info = morph_weights.request();
    const auto starts_info = morph_starts.request();
    const auto bones_info = morph_bones.request();
    const auto morph_rotation_info = morph_rotations.request();
    const auto morph_translation_info = morph_translations.request();
    const auto bone_count = rotation_info.shape[0];
    const auto morph_count = starts_info.shape[0] - 1;
    require_shape(rotation_info, "base_rotations", {bone_count, 4});
    require_shape(translation_info, "base_translations", {bone_count, 3});
    require_shape(index_info, "morph_indices", {-1});
    require_shape(weight_info, "morph_weights", {index_info.shape[0]});
    require_shape(starts_info, "morph_starts", {morph_count + 1});
    require_shape(bones_info, "morph_bones", {-1});
    require_shape(morph_rotation_info, "morph_rotations",
                  {bones_info.shape[0], 3});
    require_shape(morph_translation_info, "morph_translations",
                  {bones_info.shape[0], 3});
    py::array_t<float> rotations({bone_count, py::ssize_t(4)});
    py::array_t<float> translations({bone_count, py::ssize_t(3)});
    std::copy_n(base_rotations.data(), bone_count * 4, rotations.mutable_data());
    std::copy_n(base_translations.data(), bone_count * 3,
                translations.mutable_data());
    auto* output_rotations = rotations.mutable_data();
    auto* output_translations = translations.mutable_data();
    const auto* active_indices = morph_indices.data();
    const auto* active_weights = morph_weights.data();
    const auto* starts = morph_starts.data();
    const auto* bones = morph_bones.data();
    const auto* offsets_rotations = morph_rotations.data();
    const auto* offsets_translations = morph_translations.data();
    {
        py::gil_scoped_release release;
        for (py::ssize_t active = 0; active < index_info.shape[0]; ++active) {
            const int morph = active_indices[active];
            const float weight = active_weights[active];
            if (morph < 0 || morph >= morph_count || weight == 0) continue;
            for (int offset = starts[morph];
                 offset < starts[morph + 1]; ++offset) {
                const int bone = bones[offset];
                if (bone < 0 || bone >= bone_count) continue;
                const float angles[3] = {
                    offsets_rotations[offset * 3],
                    offsets_rotations[offset * 3 + 1],
                    offsets_rotations[offset * 3 + 2]};
                auto delta = euler_quaternion(
                    angles[0], angles[1], angles[2]);
                std::array<float, 4> current = {
                    output_rotations[bone * 4],
                    output_rotations[bone * 4 + 1],
                    output_rotations[bone * 4 + 2],
                    output_rotations[bone * 4 + 3]};
                const auto combined = multiply_quaternion(
                    current.data(), delta.data());
                std::copy(combined.begin(), combined.end(),
                          output_rotations + bone * 4);
                for (int axis = 0; axis < 3; ++axis) {
                    output_translations[bone * 3 + axis] +=
                        offsets_translations[offset * 3 + axis] * weight;
                }
            }
        }
    }
    return py::make_tuple(std::move(rotations), std::move(translations));
}

std::array<float, 9> quaternion_matrix(const float* q) {
    const double x = q[0], y = q[1], z = q[2], w = q[3];
    const double norm = x * x + y * y + z * z + w * w;
    if (norm < 1e-12) return {1, 0, 0, 0, 1, 0, 0, 0, 1};
    const double s = 2.0 / norm;
    const double xx = x * x * s, yy = y * y * s, zz = z * z * s;
    const double xy = x * y * s, xz = x * z * s, yz = y * z * s;
    const double wx = w * x * s, wy = w * y * s, wz = w * z * s;
    return {
        static_cast<float>(1 - (yy + zz)), static_cast<float>(xy - wz),
        static_cast<float>(xz + wy), static_cast<float>(xy + wz),
        static_cast<float>(1 - (xx + zz)), static_cast<float>(yz - wx),
        static_cast<float>(xz - wy), static_cast<float>(yz + wx),
        static_cast<float>(1 - (xx + yy))};
}

std::array<float, 16> body_transform(const float* position,
                                     const float* rotation) {
    const auto r = quaternion_matrix(rotation);
    return {r[0], r[1], r[2], position[0],
            r[3], r[4], r[5], position[1],
            r[6], r[7], r[8], position[2],
            0, 0, 0, 1};
}

void multiply4(const float* a, const float* b, float* out) {
    for (int row = 0; row < 4; ++row) {
        for (int col = 0; col < 4; ++col) {
            float value = 0.0f;
            for (int k = 0; k < 4; ++k) {
                value += a[row * 4 + k] * b[k * 4 + col];
            }
            out[row * 4 + col] = value;
        }
    }
}

std::array<float, 16> inverse_rigid(const float* matrix) {
    return {matrix[0], matrix[4], matrix[8], 0,
            matrix[1], matrix[5], matrix[9], 0,
            matrix[2], matrix[6], matrix[10], 0,
            0, 0, 0, 1};
}

void set_inverse_translation(float* inverse, const float* matrix) {
    for (int row = 0; row < 3; ++row) {
        inverse[row * 4 + 3] = -(
            inverse[row * 4] * matrix[3] +
            inverse[row * 4 + 1] * matrix[7] +
            inverse[row * 4 + 2] * matrix[11]);
    }
}

std::array<float, 4> matrix_quaternion(const float* matrix) {
    const double m00 = matrix[0], m01 = matrix[1], m02 = matrix[2];
    const double m10 = matrix[4], m11 = matrix[5], m12 = matrix[6];
    const double m20 = matrix[8], m21 = matrix[9], m22 = matrix[10];
    double x, y, z, w;
    const double trace = m00 + m11 + m22;
    if (trace > 0.0) {
        const double s = std::sqrt(trace + 1.0) * 2.0;
        w = 0.25 * s;
        x = (m21 - m12) / s;
        y = (m02 - m20) / s;
        z = (m10 - m01) / s;
    } else if (m00 > m11 && m00 > m22) {
        const double s = std::sqrt(1.0 + m00 - m11 - m22) * 2.0;
        w = (m21 - m12) / s;
        x = 0.25 * s;
        y = (m01 + m10) / s;
        z = (m02 + m20) / s;
    } else if (m11 > m22) {
        const double s = std::sqrt(1.0 + m11 - m00 - m22) * 2.0;
        w = (m02 - m20) / s;
        x = (m01 + m10) / s;
        y = 0.25 * s;
        z = (m12 + m21) / s;
    } else {
        const double s = std::sqrt(1.0 + m22 - m00 - m11) * 2.0;
        w = (m10 - m01) / s;
        x = (m02 + m20) / s;
        y = (m12 + m21) / s;
        z = 0.25 * s;
    }
    const double norm = std::sqrt(x * x + y * y + z * z + w * w);
    if (norm > 1e-12) {
        x /= norm;
        y /= norm;
        z /= norm;
        w /= norm;
    }
    return {static_cast<float>(x), static_cast<float>(y),
            static_cast<float>(z), static_cast<float>(w)};
}

std::array<float, 4> normalize_quaternion(const std::array<float, 4>& q) {
    const double length = std::sqrt(
        static_cast<double>(q[0]) * q[0] +
        static_cast<double>(q[1]) * q[1] +
        static_cast<double>(q[2]) * q[2] +
        static_cast<double>(q[3]) * q[3]);
    if (length < 1e-8) return {0, 0, 0, 1};
    return {static_cast<float>(q[0] / length),
            static_cast<float>(q[1] / length),
            static_cast<float>(q[2] / length),
            static_cast<float>(q[3] / length)};
}

std::array<float, 4> multiply_quaternion(const float* a, const float* b) {
    return normalize_quaternion({
        a[3] * b[0] + a[0] * b[3] + a[1] * b[2] - a[2] * b[1],
        a[3] * b[1] - a[0] * b[2] + a[1] * b[3] + a[2] * b[0],
        a[3] * b[2] + a[0] * b[1] - a[1] * b[0] + a[2] * b[3],
        a[3] * b[3] - a[0] * b[0] - a[1] * b[1] - a[2] * b[2]});
}

std::array<float, 4> slerp_quaternion(const float* a, const float* b,
                                     float amount) {
    std::array<float, 4> qa = normalize_quaternion({a[0], a[1], a[2], a[3]});
    std::array<float, 4> qb = normalize_quaternion({b[0], b[1], b[2], b[3]});
    double dot = qa[0] * qb[0] + qa[1] * qb[1] +
        qa[2] * qb[2] + qa[3] * qb[3];
    if (dot < 0.0) {
        for (auto& value : qb) value = -value;
        dot = -dot;
    }
    dot = std::min(1.0, std::max(-1.0, dot));
    if (dot > 0.9995) {
        std::array<float, 4> result{};
        for (int i = 0; i < 4; ++i) {
            result[i] = static_cast<float>(qa[i] * (1.0 - amount) +
                                           qb[i] * amount);
        }
        return normalize_quaternion(result);
    }
    const double theta = std::acos(dot);
    const double sine = std::sin(theta);
    const double left = std::sin((1.0 - amount) * theta) / sine;
    const double right = std::sin(amount * theta) / sine;
    std::array<float, 4> result{};
    for (int i = 0; i < 4; ++i) {
        result[i] = static_cast<float>(qa[i] * left + qb[i] * right);
    }
    return normalize_quaternion(result);
}

std::array<float, 4> axis_angle_quaternion(const float* axis, double angle) {
    const double length = std::sqrt(
        static_cast<double>(axis[0]) * axis[0] +
        static_cast<double>(axis[1]) * axis[1] +
        static_cast<double>(axis[2]) * axis[2]);
    if (length < 1e-8) return {0, 0, 0, 1};
    const double sine = std::sin(angle * 0.5) / length;
    return {static_cast<float>(axis[0] * sine),
            static_cast<float>(axis[1] * sine),
            static_cast<float>(axis[2] * sine),
            static_cast<float>(std::cos(angle * 0.5))};
}

std::array<float, 3> quaternion_euler(const float* q) {
    const auto r = quaternion_matrix(q);
    const double sine_pitch = 2.0 * (q[3] * q[1] - q[2] * q[0]);
    return {
        static_cast<float>(std::atan2(
            2.0 * (q[3] * q[0] + q[1] * q[2]),
            1.0 - 2.0 * (q[0] * q[0] + q[1] * q[1]))),
        static_cast<float>(std::asin(std::max(-1.0, std::min(1.0,
                                                            sine_pitch)))),
        static_cast<float>(std::atan2(r[3], r[0]))};
}

std::array<float, 4> euler_quaternion(float x, float y, float z) {
    const float ax[3] = {1, 0, 0};
    const float ay[3] = {0, 1, 0};
    const float az[3] = {0, 0, 1};
    const auto qx = axis_angle_quaternion(ax, x);
    const auto qy = axis_angle_quaternion(ay, y);
    const auto qz = axis_angle_quaternion(az, z);
    const auto yx = multiply_quaternion(qy.data(), qx.data());
    return multiply_quaternion(qz.data(), yx.data());
}


std::array<float, 3> euler_alternative(const std::array<float, 3>& e) {
    auto wrap = [](float a) {
        a = static_cast<float>(std::fmod(a + 3.14159265358979f, 6.28318530717959f));
        if (a < 0.0f) a += 6.28318530717959f;
        return a - 3.14159265358979f;
    };
    return {wrap(e[0] + 3.14159265358979f),
            wrap(3.14159265358979f - e[1]),
            wrap(e[2] + 3.14159265358979f)};
}

float euler_distance(const std::array<float, 3>& a,
                     const std::array<float, 3>& b) {
    float total = 0.0f;
    for (int i = 0; i < 3; ++i) {
        float d = a[i] - b[i];
        d = static_cast<float>(std::fmod(d + 3.14159265358979f, 6.28318530717959f));
        if (d < 0.0f) d += 6.28318530717959f;
        d -= 3.14159265358979f;
        total += d * d;
    }
    return total;
}

std::array<float, 3> quaternion_euler_stable(
    const float* q, const std::array<float, 3>* prev) {
    const auto euler = quaternion_euler(q);
    if (prev == nullptr) return euler;
    const auto alt = euler_alternative(euler);
    if (euler_distance(alt, *prev) < euler_distance(euler, *prev)) return alt;
    return euler;
}

void compute_world_rows(
    py::ssize_t bone_count, const std::uint32_t* flags,
    const std::int32_t* append_parents, const float* append_ratios,
    const std::int32_t* parents, const float* rest_offsets,
    const float* rest_positions, const float* rotations,
    const float* translations, const std::int32_t* order,
    const std::uint8_t* need, float* world) {
    const float identity[16] = {
        1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1};
    for (py::ssize_t order_index = 0; order_index < bone_count;
         ++order_index) {
        const int bone = order[order_index];
        if (bone < 0 || bone >= bone_count || !need[bone]) continue;
        const int parent = parents[bone];
        const float* parent_world = parent >= 0 && parent < bone_count
            ? world + parent * 16 : identity;
        std::array<float, 4> rotation = {
            rotations[bone * 4], rotations[bone * 4 + 1],
            rotations[bone * 4 + 2], rotations[bone * 4 + 3]};
        float local_translation[3] = {
            rest_offsets[bone * 3] + translations[bone * 3],
            rest_offsets[bone * 3 + 1] + translations[bone * 3 + 1],
            rest_offsets[bone * 3 + 2] + translations[bone * 3 + 2]};
        const int source = append_parents[bone];
        const float ratio = append_ratios[bone];
        if ((flags[bone] & ((1u << 8) | (1u << 9))) != 0 &&
            source >= 0 && source < bone_count && source != bone &&
            ratio != 0.0f) {
            if (flags[bone] & (1u << 8)) {
                std::array<float, 4> source_rotation{};
                if (flags[bone] & (1u << 7)) {
                    std::copy_n(rotations + source * 4, 4,
                                source_rotation.begin());
                } else {
                    float relative[16] = {};
                    for (int row = 0; row < 3; ++row) {
                        for (int col = 0; col < 3; ++col) {
                            for (int k = 0; k < 3; ++k) {
                                relative[row * 4 + col] +=
                                    parent_world[k * 4 + row] *
                                    world[source * 16 + k * 4 + col];
                            }
                        }
                    }
                    source_rotation = matrix_quaternion(relative);
                }
                const float identity_rotation[4] = {0, 0, 0, 1};
                const auto inherited = slerp_quaternion(
                    identity_rotation, source_rotation.data(), ratio);
                rotation = multiply_quaternion(inherited.data(),
                                               rotation.data());
            }
            if (flags[bone] & (1u << 9)) {
                float delta[3] = {};
                if (flags[bone] & (1u << 7)) {
                    for (int axis = 0; axis < 3; ++axis) {
                        delta[axis] = translations[source * 3 + axis] * ratio;
                    }
                } else {
                    const float world_delta[3] = {
                        world[source * 16 + 3] - rest_positions[source * 3],
                        world[source * 16 + 7] - rest_positions[source * 3 + 1],
                        world[source * 16 + 11] - rest_positions[source * 3 + 2]};
                    for (int axis = 0; axis < 3; ++axis) {
                        for (int k = 0; k < 3; ++k) {
                            delta[axis] += parent_world[k * 4 + axis] *
                                           world_delta[k] * ratio;
                        }
                    }
                }
                for (int axis = 0; axis < 3; ++axis) {
                    local_translation[axis] += delta[axis];
                }
            }
        }
        const auto local_rotation = quaternion_matrix(rotation.data());
        const float local[16] = {
            local_rotation[0], local_rotation[1], local_rotation[2],
            local_translation[0],
            local_rotation[3], local_rotation[4], local_rotation[5],
            local_translation[1],
            local_rotation[6], local_rotation[7], local_rotation[8],
            local_translation[2],
            0, 0, 0, 1};
        multiply4(parent_world, local, world + bone * 16);
    }
}

void world_rows(
    Array<std::uint32_t> flags, Array<std::int32_t> append_parents,
    Array<float> append_ratios, Array<std::int32_t> parents,
    Array<float> rest_offsets, Array<float> rest_positions,
    Array<float> rotations, Array<float> translations,
    Array<std::int32_t> order, Array<std::uint8_t> need,
    Array<float> world) {
    const auto count = parents.request().shape[0];
    const auto flags_info = flags.request();
    const auto append_parent_info = append_parents.request();
    const auto append_ratio_info = append_ratios.request();
    const auto parent_info = parents.request();
    const auto rest_info = rest_offsets.request();
    const auto rest_position_info = rest_positions.request();
    const auto rotation_info = rotations.request();
    const auto translation_info = translations.request();
    const auto order_info = order.request();
    const auto need_info = need.request();
    const auto world_info = world.request(true);
    require_shape(flags_info, "flags", {count});
    require_shape(append_parent_info, "append_parents", {count});
    require_shape(append_ratio_info, "append_ratios", {count});
    require_shape(parent_info, "parents", {count});
    require_shape(rest_info, "rest_offsets", {count, 3});
    require_shape(rest_position_info, "rest_positions", {count, 3});
    require_shape(rotation_info, "rotations", {count, 4});
    require_shape(translation_info, "translations", {count, 3});
    require_shape(order_info, "order", {count});
    require_shape(need_info, "need", {count});
    require_shape(world_info, "world", {count, 4, 4});
    {
        py::gil_scoped_release release;
        compute_world_rows(
            count, flags.data(), append_parents.data(), append_ratios.data(),
            parents.data(), rest_offsets.data(), rest_positions.data(),
            rotations.data(), translations.data(), order.data(), need.data(),
            world.mutable_data());
    }
}

int solve_ik(
    Array<std::uint32_t> flags, Array<std::int32_t> append_parents,
    Array<float> append_ratios, Array<std::int32_t> parents,
    Array<float> rest_offsets, Array<float> rest_positions,
    Array<std::int32_t> order, Array<std::int32_t> ik_targets,
    Array<std::int32_t> ik_loops, Array<float> ik_angles,
    Array<std::int32_t> link_offsets, Array<std::int32_t> link_bones,
    Array<std::uint8_t> link_limited, Array<float> link_limits,
    Array<std::uint8_t> selected, int max_loops, Array<float> rotations,
    Array<float> translations, Array<float> base_rotations,
    Array<std::uint8_t> changed_bones) {
    const auto bone_count = parents.request().shape[0];
    const auto flags_info = flags.request();
    const auto append_parent_info = append_parents.request();
    const auto append_ratio_info = append_ratios.request();
    const auto parent_info = parents.request();
    const auto rest_info = rest_offsets.request();
    const auto rest_position_info = rest_positions.request();
    const auto order_info = order.request();
    const auto target_info = ik_targets.request();
    const auto loops_info = ik_loops.request();
    const auto angles_info = ik_angles.request();
    const auto offsets_info = link_offsets.request();
    const auto links_info = link_bones.request();
    const auto limited_info = link_limited.request();
    const auto limits_info = link_limits.request();
    const auto selected_info = selected.request();
    const auto rotation_info = rotations.request(true);
    const auto translation_info = translations.request();
    const auto base_rotation_info = base_rotations.request(true);
    const auto changed_info = changed_bones.request(true);
    require_shape(flags_info, "flags", {bone_count});
    require_shape(append_parent_info, "append_parents", {bone_count});
    require_shape(append_ratio_info, "append_ratios", {bone_count});
    require_shape(parent_info, "parents", {bone_count});
    require_shape(rest_info, "rest_offsets", {bone_count, 3});
    require_shape(rest_position_info, "rest_positions", {bone_count, 3});
    require_shape(order_info, "order", {bone_count});
    require_shape(target_info, "ik_targets", {bone_count});
    require_shape(loops_info, "ik_loops", {bone_count});
    require_shape(angles_info, "ik_angles", {bone_count});
    require_shape(offsets_info, "link_offsets", {bone_count + 1});
    require_shape(links_info, "link_bones", {-1});
    require_shape(limited_info, "link_limited", {links_info.shape[0]});
    require_shape(limits_info, "link_limits", {links_info.shape[0], 2, 3});
    require_shape(selected_info, "selected", {bone_count});
    require_shape(rotation_info, "rotations", {bone_count, 4});
    require_shape(translation_info, "translations", {bone_count, 3});
    require_shape(base_rotation_info, "base_rotations", {bone_count, 4});
    require_shape(changed_info, "changed_bones", {bone_count});

    auto* rotation_ptr = rotations.mutable_data();
    auto* base_rotation_ptr = base_rotations.mutable_data();
    auto* changed_ptr = changed_bones.mutable_data();
    const auto* selected_ptr = selected.data();
    const auto* target_ptr = ik_targets.data();
    const auto* loop_ptr = ik_loops.data();
    const auto* angle_ptr = ik_angles.data();
    const auto* link_offset_ptr = link_offsets.data();
    const auto* link_ptr = link_bones.data();
    const auto* limited_ptr = link_limited.data();
    const auto* limit_ptr = link_limits.data();
    int solved = 0;
    const py::ssize_t link_count = link_bones.shape(0);
    std::vector<std::array<float, 3>> prev_euler(
        static_cast<std::size_t>(link_count), {0.0f, 0.0f, 0.0f});
    std::vector<std::uint8_t> has_prev(static_cast<std::size_t>(link_count), 0);
    {
        py::gil_scoped_release release;
        std::fill_n(changed_ptr, bone_count, std::uint8_t(0));
        std::vector<std::uint8_t> all_bones(bone_count, 1);
        std::vector<float> world(static_cast<std::size_t>(bone_count) * 16);
        for (py::ssize_t ik_bone = 0; ik_bone < bone_count; ++ik_bone) {
            if (!selected_ptr[ik_bone] || !(flags.data()[ik_bone] & (1u << 5))) {
                continue;
            }
            const int target = target_ptr[ik_bone];
            if (target < 0 || target >= bone_count) continue;
            const int link_start = link_offset_ptr[ik_bone];
            const int link_end = link_offset_ptr[ik_bone + 1];
            if (link_start < 0 || link_end <= link_start ||
                link_end > links_info.shape[0]) continue;

            compute_world_rows(
                bone_count, flags.data(), append_parents.data(),
                append_ratios.data(), parents.data(), rest_offsets.data(),
                rest_positions.data(), rotation_ptr, translations.data(),
                order.data(), all_bones.data(), world.data());
            const float goal[3] = {
                world[ik_bone * 16 + 3], world[ik_bone * 16 + 7],
                world[ik_bone * 16 + 11]};
            int iterations = std::max(1, std::min(ik_loops.data()[ik_bone], 200));
            if (max_loops > 0) iterations = std::min(iterations, max_loops);
            for (int iteration = 0; iteration < iterations; ++iteration) {
                compute_world_rows(
                    bone_count, flags.data(), append_parents.data(),
                    append_ratios.data(), parents.data(), rest_offsets.data(),
                    rest_positions.data(), rotation_ptr, translations.data(),
                    order.data(), all_bones.data(), world.data());
                float effector[3] = {world[target * 16 + 3],
                                     world[target * 16 + 7],
                                     world[target * 16 + 11]};
                auto distance_to_goal = [&]() {
                    const float x = goal[0] - effector[0];
                    const float y = goal[1] - effector[1];
                    const float z = goal[2] - effector[2];
                    return std::sqrt(x * x + y * y + z * z);
                };
                if (distance_to_goal() < 1e-3) break;
                bool moved = false;
                for (int link_index = link_end - 1;
                     link_index >= link_start; --link_index) {
                    compute_world_rows(
                        bone_count, flags.data(), append_parents.data(),
                        append_ratios.data(), parents.data(), rest_offsets.data(),
                        rest_positions.data(), rotation_ptr, translations.data(),
                        order.data(), all_bones.data(), world.data());
                    const int link_bone = link_ptr[link_index];
                    if (link_bone < 0 || link_bone >= bone_count) continue;
                    const float pivot[3] = {
                        world[link_bone * 16 + 3],
                        world[link_bone * 16 + 7],
                        world[link_bone * 16 + 11]};
                    const float v1[3] = {effector[0] - pivot[0],
                                          effector[1] - pivot[1],
                                          effector[2] - pivot[2]};
                    const float v2[3] = {goal[0] - pivot[0],
                                          goal[1] - pivot[1],
                                          goal[2] - pivot[2]};
                    const float n1 = std::sqrt(
                        v1[0] * v1[0] + v1[1] * v1[1] + v1[2] * v1[2]);
                    const float n2 = std::sqrt(
                        v2[0] * v2[0] + v2[1] * v2[1] + v2[2] * v2[2]);
                    if (n1 < 1e-6 || n2 < 1e-6) continue;
                    const float cosine = std::max(-1.0f, std::min(1.0f,
                        (v1[0] * v2[0] + v1[1] * v2[1] +
                         v1[2] * v2[2]) / (n1 * n2)));
                    double angle = std::acos(static_cast<double>(cosine));
                    if (angle < 1e-4) continue;
                    angle = std::min(angle,
                        static_cast<double>(std::max(0.01f, angle_ptr[ik_bone])));
                    const float axis[3] = {
                        v1[1] * v2[2] - v1[2] * v2[1],
                        v1[2] * v2[0] - v1[0] * v2[2],
                        v1[0] * v2[1] - v1[1] * v2[0]};
                    const float axis_length = std::sqrt(
                        axis[0] * axis[0] + axis[1] * axis[1] +
                        axis[2] * axis[2]);
                    if (axis_length < 1e-8) continue;
                    float parent_rotation[9] = {1, 0, 0, 0, 1, 0, 0, 0, 1};
                    const int parent = parents.data()[link_bone];
                    if (parent >= 0 && parent < bone_count) {
                        const float* parent_world = world.data() + parent * 16;
                        for (int row = 0; row < 3; ++row) {
                            for (int col = 0; col < 3; ++col) {
                                parent_rotation[row * 3 + col] =
                                    parent_world[row * 4 + col];
                            }
                        }
                    }
                    const auto delta_q = axis_angle_quaternion(axis, angle);
                    const auto delta_rotation = quaternion_matrix(delta_q.data());
                    float local_rotation[9] = {};
                    for (int row = 0; row < 3; ++row) {
                        for (int col = 0; col < 3; ++col) {
                            for (int a = 0; a < 3; ++a) {
                                for (int b = 0; b < 3; ++b) {
                                    local_rotation[row * 3 + col] +=
                                        parent_rotation[a * 3 + row] *
                                        delta_rotation[a * 3 + b] *
                                        parent_rotation[b * 3 + col];
                                }
                            }
                        }
                    }
                    const auto current_rotation = quaternion_matrix(
                        rotation_ptr + link_bone * 4);
                    float new_local[9] = {};
                    for (int row = 0; row < 3; ++row) {
                        for (int col = 0; col < 3; ++col) {
                            for (int k = 0; k < 3; ++k) {
                                new_local[row * 3 + col] +=
                                    local_rotation[row * 3 + k] *
                                    current_rotation[k * 3 + col];
                            }
                        }
                    }
                    std::array<float, 16> local4 = {
                        new_local[0], new_local[1], new_local[2], 0,
                        new_local[3], new_local[4], new_local[5], 0,
                        new_local[6], new_local[7], new_local[8], 0,
                        0, 0, 0, 1};
                    std::array<float, 4> next_rotation =
                        matrix_quaternion(local4.data());
                    if (limited_ptr[link_index]) {
                        const auto* prev = has_prev[link_index]
                            ? &prev_euler[link_index] : nullptr;
                        const auto euler = quaternion_euler_stable(
                            next_rotation.data(), prev);
                        std::array<float, 3> clamped{};
                        bool clipped = false;
                        for (int axis_index = 0; axis_index < 3; ++axis_index) {
                            clamped[axis_index] = std::min(
                                std::max(euler[axis_index],
                                         limit_ptr[link_index * 6 + axis_index]),
                                limit_ptr[link_index * 6 + 3 + axis_index]);
                            if (clamped[axis_index] != euler[axis_index]) {
                                clipped = true;
                            }
                        }
                        if (clipped) {
                            // 增量钳制：钳制结果与上一轮完全一致，说明这一轴已经
                            // 顶在限制上，继续累计只会来回抖动，舍弃本轮旋转。
                            if (prev != nullptr &&
                                euler_distance(clamped, *prev) < 1e-6f) {
                                continue;
                            }
                            prev_euler[link_index] = clamped;
                            has_prev[link_index] = 1;
                            next_rotation = euler_quaternion(
                                clamped[0], clamped[1], clamped[2]);
                        } else {
                            prev_euler[link_index] = euler;
                            has_prev[link_index] = 1;
                        }
                    }
                    std::copy(next_rotation.begin(), next_rotation.end(),
                              base_rotation_ptr + link_bone * 4);
                    std::copy(next_rotation.begin(), next_rotation.end(),
                              rotation_ptr + link_bone * 4);
                    changed_ptr[link_bone] = 1;
                    moved = true;
                    compute_world_rows(
                        bone_count, flags.data(), append_parents.data(),
                        append_ratios.data(), parents.data(), rest_offsets.data(),
                        rest_positions.data(), rotation_ptr, translations.data(),
                        order.data(), all_bones.data(), world.data());
                    for (int axis_index = 0; axis_index < 3; ++axis_index) {
                        effector[axis_index] =
                            world[target * 16 + axis_index * 4 + 3];
                    }
                    if (distance_to_goal() < 1e-3) break;
                }
                if (!moved) break;
            }
            ++solved;
        }
    }
    return solved;
}

void physics_step(
    std::uintptr_t world_handle, Array<std::int32_t> body_map,
    Array<std::int32_t> bone_of_body, Array<std::int32_t> modes,
    Array<float> offsets, Array<float> world, float dt,
    Array<float> body_positions, Array<float> body_rotations,
    Array<std::int32_t> bone_order, Array<std::int32_t> parents,
    Array<std::int32_t> rigid_for_bone, Array<float> rest_offsets,
    Array<float> pose_rotations, Array<float> pose_translations,
    Array<float> inverse_offsets, Array<float> override_rotations,
    Array<float> override_translations,
    Array<std::uint8_t> override_mask) {
    const auto map_info = body_map.request();
    const auto bone_info = bone_of_body.request();
    const auto modes_info = modes.request();
    const auto offsets_info = offsets.request();
    const auto world_info = world.request();
    const auto positions_info = body_positions.request(true);
    const auto rotations_info = body_rotations.request(true);
    const auto order_info = bone_order.request();
    const auto parents_info = parents.request();
    const auto rigid_info = rigid_for_bone.request();
    const auto rest_info = rest_offsets.request();
    const auto pose_rot_info = pose_rotations.request();
    const auto pose_trans_info = pose_translations.request();
    const auto inverse_offsets_info = inverse_offsets.request();
    const auto override_rot_info = override_rotations.request(true);
    const auto override_trans_info = override_translations.request(true);
    const auto override_mask_info = override_mask.request(true);
    const auto body_count = map_info.shape[0];
    const auto bone_count = world_info.shape[0];
    require_shape(bone_info, "bone_of_body", {body_count});
    require_shape(modes_info, "modes", {body_count});
    require_shape(offsets_info, "offsets", {body_count, 4, 4});
    require_shape(world_info, "world", {-1, 4, 4});
    require_shape(positions_info, "body_positions", {body_count, 3});
    require_shape(rotations_info, "body_rotations", {body_count, 4});
    require_shape(order_info, "bone_order", {bone_count});
    require_shape(parents_info, "parents", {bone_count});
    require_shape(rigid_info, "rigid_for_bone", {bone_count});
    require_shape(rest_info, "rest_offsets", {bone_count, 3});
    require_shape(pose_rot_info, "pose_rotations", {bone_count, 4});
    require_shape(pose_trans_info, "pose_translations", {bone_count, 3});
    require_shape(inverse_offsets_info, "inverse_offsets", {body_count, 4, 4});
    require_shape(override_rot_info, "override_rotations", {bone_count, 4});
    require_shape(override_trans_info, "override_translations", {bone_count, 3});
    require_shape(override_mask_info, "override_mask", {bone_count});
    if (!world_handle) throw py::value_error("physics world handle is null");

    auto* handle = reinterpret_cast<BWWorld*>(world_handle);
    const auto* map_ptr = body_map.data();
    const auto* bone_ptr = bone_of_body.data();
    const auto* mode_ptr = modes.data();
    const auto* offset_ptr = offsets.data();
    const auto* world_ptr = world.data();
    const auto* order_ptr = bone_order.data();
    const auto* parent_ptr = parents.data();
    const auto* rigid_ptr = rigid_for_bone.data();
    const auto* rest_ptr = rest_offsets.data();
    const auto* pose_rot_ptr = pose_rotations.data();
    const auto* pose_trans_ptr = pose_translations.data();
    const auto* inverse_offset_ptr = inverse_offsets.data();
    auto* position_ptr = body_positions.mutable_data();
    auto* rotation_ptr = body_rotations.mutable_data();
    auto* override_rot_ptr = override_rotations.mutable_data();
    auto* override_trans_ptr = override_translations.mutable_data();
    auto* override_mask_ptr = override_mask.mutable_data();
    {
        py::gil_scoped_release release;
        for (py::ssize_t i = 0; i < body_count; ++i) {
            const int body = map_ptr[i];
            const int bone = bone_ptr[i];
            if (body < 0 || mode_ptr[i] != 0 || bone < 0 || bone >= bone_count) {
                continue;
            }
            const float* parent = world_ptr + bone * 16;
            const float* offset = offset_ptr + i * 16;
            float transform[16] = {};
            for (int row = 0; row < 4; ++row) {
                for (int col = 0; col < 4; ++col) {
                    for (int k = 0; k < 4; ++k) {
                        transform[row * 4 + col] +=
                            parent[row * 4 + k] * offset[k * 4 + col];
                    }
                }
            }

            const float position[3] = {
                transform[3], transform[7], transform[11]};
            const auto rotation = matrix_quaternion(transform);
            bw_set_body(handle, body, position, rotation.data());
        }

        bw_step(handle, dt, 3);
        for (py::ssize_t i = 0; i < body_count; ++i) {
            if (map_ptr[i] < 0) continue;
            bw_get_body(handle, map_ptr[i], position_ptr + i * 3,
                        rotation_ptr + i * 4);
        }

        auto* bone_world = new float[bone_count * 16];
        std::fill_n(override_mask_ptr, bone_count, std::uint8_t(0));
        const float identity[16] = {
            1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1};
        for (py::ssize_t order_index = 0; order_index < bone_count;
             ++order_index) {
            const int bone = order_ptr[order_index];
            if (bone < 0 || bone >= bone_count) continue;
            const int parent = parent_ptr[bone];
            const float* parent_world = parent >= 0 && parent < bone_count
                ? bone_world + parent * 16 : identity;
            const int rigid = rigid_ptr[bone];
            const bool has_override = rigid >= 0 && rigid < body_count &&
                map_ptr[rigid] >= 0;
            const float* rotation = pose_rot_ptr + bone * 4;
            const float* translation = pose_trans_ptr + bone * 3;
            std::array<float, 4> local_rotation{};
            std::array<float, 3> local_translation{};
            if (has_override) {
                const auto body = body_transform(
                    position_ptr + rigid * 3, rotation_ptr + rigid * 4);
                auto inverse_parent = inverse_rigid(parent_world);
                set_inverse_translation(inverse_parent.data(), parent_world);
                float parent_body[16] = {};
                multiply4(inverse_parent.data(), body.data(), parent_body);
                float local[16] = {};
                multiply4(parent_body, inverse_offset_ptr + rigid * 16, local);
                local_rotation = matrix_quaternion(local);
                for (int axis = 0; axis < 3; ++axis) {
                    local_translation[axis] =
                        local[axis * 4 + 3] - rest_ptr[bone * 3 + axis];
                }
                std::copy(local_rotation.begin(), local_rotation.end(),
                          override_rot_ptr + bone * 4);
                std::copy(local_translation.begin(), local_translation.end(),
                          override_trans_ptr + bone * 3);
                override_mask_ptr[bone] = 1;
                rotation = local_rotation.data();
                translation = local_translation.data();
            }
            auto local_matrix = quaternion_matrix(rotation);
            float transform[16] = {
                local_matrix[0], local_matrix[1], local_matrix[2],
                rest_ptr[bone * 3] + translation[0],
                local_matrix[3], local_matrix[4], local_matrix[5],
                rest_ptr[bone * 3 + 1] + translation[1],
                local_matrix[6], local_matrix[7], local_matrix[8],
                rest_ptr[bone * 3 + 2] + translation[2],
                0, 0, 0, 1};
            multiply4(parent_world, transform, bone_world + bone * 16);
        }
        delete[] bone_world;
    }
}

PYBIND11_MODULE(_pmx_core, module) {
    module.doc() = "PmxEditor Modern native compute backend";
    module.def("deform", &deform, "CPU skinning over zero-copy NumPy inputs");
    module.def("deform_subset", &deform_subset,
               "Incremental CPU skinning over zero-copy NumPy inputs");
    module.def("apply_vertex_morphs", &apply_vertex_morphs,
               "Apply sparse vertex and UV morphs over NumPy buffers");
    module.def("apply_bone_morphs", &apply_bone_morphs,
               "Apply sparse bone morphs over NumPy buffers");
    module.def("physics_step", &physics_step,
               "Batch Bullet exchange and pose reconstruction over NumPy buffers");
    module.def("world_rows", &world_rows,
               "Build hierarchical PMX world matrices over NumPy buffers");
    module.def("solve_ik", &solve_ik,
               "Solve CCD IK chains in the native compute backend");
}
