// 数学基础：行主序 4x4 矩阵 + 四元数，语义与 Python/NumPy 参考实现一一对应。
// 约定：列向量，v' = M * v；矩阵按 m[row * 4 + col] 存放。
#pragma once

#include <array>
#include <cmath>
#include <cstdint>

namespace pmx {

constexpr float kPi = 3.14159265358979323846f;

struct Vec2 {
    float x = 0.0f, y = 0.0f;
    Vec2() = default;
    Vec2(float x_, float y_) : x(x_), y(y_) {}
    float& operator[](int i) { return (&x)[i]; }
    float operator[](int i) const { return (&x)[i]; }
};

struct Vec3 {
    float x = 0.0f, y = 0.0f, z = 0.0f;
    Vec3() = default;
    Vec3(float x_, float y_, float z_) : x(x_), y(y_), z(z_) {}
    explicit Vec3(float v) : x(v), y(v), z(v) {}
    float& operator[](int i) { return (&x)[i]; }
    float operator[](int i) const { return (&x)[i]; }
};

inline Vec3 operator+(Vec3 a, Vec3 b) { return {a.x + b.x, a.y + b.y, a.z + b.z}; }
inline Vec3 operator-(Vec3 a, Vec3 b) { return {a.x - b.x, a.y - b.y, a.z - b.z}; }
inline Vec3 operator-(Vec3 a) { return {-a.x, -a.y, -a.z}; }
inline Vec3 operator*(Vec3 a, float s) { return {a.x * s, a.y * s, a.z * s}; }
inline Vec3 operator*(float s, Vec3 a) { return a * s; }
inline Vec3 operator/(Vec3 a, float s) { return {a.x / s, a.y / s, a.z / s}; }
inline Vec3& operator+=(Vec3& a, Vec3 b) { a = a + b; return a; }
inline Vec3& operator-=(Vec3& a, Vec3 b) { a = a - b; return a; }
inline Vec3& operator*=(Vec3& a, float s) { a = a * s; return a; }
inline Vec3 cross(Vec3 a, Vec3 b) {
    return {a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x};
}
inline float dot(Vec3 a, Vec3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
inline float length(Vec3 a) { return std::sqrt(dot(a, a)); }
inline Vec3 normalize(Vec3 a) {
    float n = length(a);
    return n > 1e-8f ? a / n : Vec3(0.0f, 1.0f, 0.0f);
}
inline Vec3 lerp(Vec3 a, Vec3 b, float t) { return a + (b - a) * t; }
inline float clampf(float v, float lo, float hi) { return v < lo ? lo : (v > hi ? hi : v); }

struct Vec4 {
    float x = 0.0f, y = 0.0f, z = 0.0f, w = 0.0f;
    Vec4() = default;
    Vec4(float x_, float y_, float z_, float w_) : x(x_), y(y_), z(z_), w(w_) {}
    float& operator[](int i) { return (&x)[i]; }
    float operator[](int i) const { return (&x)[i]; }
};

// 四元数：x, y, z, w（与 PMX / 参考实现一致）。
struct Quat {
    float x = 0.0f, y = 0.0f, z = 0.0f, w = 1.0f;
    Quat() = default;
    Quat(float x_, float y_, float z_, float w_) : x(x_), y(y_), z(z_), w(w_) {}
    float& operator[](int i) { return (&x)[i]; }
    float operator[](int i) const { return (&x)[i]; }
};

inline Quat identity_quat() { return Quat(0.0f, 0.0f, 0.0f, 1.0f); }

inline Quat normalize(Quat q) {
    float n = std::sqrt(q.x * q.x + q.y * q.y + q.z * q.z + q.w * q.w);
    if (n < 1e-8f) return identity_quat();
    return Quat(q.x / n, q.y / n, q.z / n, q.w / n);
}

inline float quat_dot(Quat a, Quat b) {
    return a.x * b.x + a.y * b.y + a.z * b.z + a.w * b.w;
}

inline Quat quat_mul(Quat a, Quat b) {
    return Quat(a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
                a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
                a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
                a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z);
}

inline Quat axis_angle_quat(Vec3 axis, float angle) {
    float n = length(axis);
    if (n < 1e-8f) return identity_quat();
    axis = axis / n;
    float h = angle * 0.5f;
    float s = std::sin(h);
    return Quat(axis.x * s, axis.y * s, axis.z * s, std::cos(h));
}

// 骨骼姿态欧拉：R = Rz * Ry * Rx（与 PMXEditor 的骨骼旋转顺序一致）。
inline Quat euler_to_quat(float rx, float ry, float rz) {
    Quat qx = axis_angle_quat({1.0f, 0.0f, 0.0f}, rx);
    Quat qy = axis_angle_quat({0.0f, 1.0f, 0.0f}, ry);
    Quat qz = axis_angle_quat({0.0f, 0.0f, 1.0f}, rz);
    return normalize(quat_mul(qz, quat_mul(qy, qx)));
}

// 刚体/关节旋转欧拉：R = Ry * Rx * Rz（MMD 用的 YXZ 顺序）。
inline Quat rigid_euler_quat(float rx, float ry, float rz) {
    Quat qx = axis_angle_quat({1.0f, 0.0f, 0.0f}, rx);
    Quat qy = axis_angle_quat({0.0f, 1.0f, 0.0f}, ry);
    Quat qz = axis_angle_quat({0.0f, 0.0f, 1.0f}, rz);
    return normalize(quat_mul(qy, quat_mul(qx, qz)));
}

struct Mat3 {
    float m[9] = {1.0f, 0.0f, 0.0f,
                  0.0f, 1.0f, 0.0f,
                  0.0f, 0.0f, 1.0f};
    float& at(int r, int c) { return m[r * 3 + c]; }
    float at(int r, int c) const { return m[r * 3 + c]; }
    Vec3 col(int c) const { return {m[c], m[3 + c], m[6 + c]}; }
    Vec3 row(int r) const { return {m[r * 3], m[r * 3 + 1], m[r * 3 + 2]}; }
};

inline Mat3 transpose(const Mat3& a) {
    Mat3 out;
    for (int r = 0; r < 3; ++r)
        for (int c = 0; c < 3; ++c) out.at(r, c) = a.at(c, r);
    return out;
}

inline Vec3 mul(const Mat3& a, Vec3 v) {
    return {a.at(0, 0) * v.x + a.at(0, 1) * v.y + a.at(0, 2) * v.z,
            a.at(1, 0) * v.x + a.at(1, 1) * v.y + a.at(1, 2) * v.z,
            a.at(2, 0) * v.x + a.at(2, 1) * v.y + a.at(2, 2) * v.z};
}

inline Mat3 mul(const Mat3& a, const Mat3& b) {
    Mat3 out;
    for (int r = 0; r < 3; ++r)
        for (int c = 0; c < 3; ++c) {
            float sum = 0.0f;
            for (int k = 0; k < 3; ++k) sum += a.at(r, k) * b.at(k, c);
            out.at(r, c) = sum;
        }
    return out;
}

inline Mat3 quat_to_mat3(Quat q) {
    q = normalize(q);
    float x = q.x, y = q.y, z = q.z, w = q.w;
    float s = 2.0f;
    float xx = x * x * s, yy = y * y * s, zz = z * z * s;
    float xy = x * y * s, xz = x * z * s, yz = y * z * s;
    float wx = w * x * s, wy = w * y * s, wz = w * z * s;
    Mat3 out;
    out.at(0, 0) = 1.0f - (yy + zz);
    out.at(0, 1) = xy - wz;
    out.at(0, 2) = xz + wy;
    out.at(1, 0) = xy + wz;
    out.at(1, 1) = 1.0f - (xx + zz);
    out.at(1, 2) = yz - wx;
    out.at(2, 0) = xz - wy;
    out.at(2, 1) = yz + wx;
    out.at(2, 2) = 1.0f - (xx + yy);
    return out;
}

inline Quat mat3_to_quat(const Mat3& m) {
    float tr = m.at(0, 0) + m.at(1, 1) + m.at(2, 2);
    Quat q;
    if (tr > 0.0f) {
        float s = std::sqrt(tr + 1.0f) * 2.0f;
        q.w = 0.25f * s;
        q.x = (m.at(2, 1) - m.at(1, 2)) / s;
        q.y = (m.at(0, 2) - m.at(2, 0)) / s;
        q.z = (m.at(1, 0) - m.at(0, 1)) / s;
    } else if (m.at(0, 0) > m.at(1, 1) && m.at(0, 0) > m.at(2, 2)) {
        float s = std::sqrt(1.0f + m.at(0, 0) - m.at(1, 1) - m.at(2, 2)) * 2.0f;
        q.w = (m.at(2, 1) - m.at(1, 2)) / s;
        q.x = 0.25f * s;
        q.y = (m.at(0, 1) + m.at(1, 0)) / s;
        q.z = (m.at(0, 2) + m.at(2, 0)) / s;
    } else if (m.at(1, 1) > m.at(2, 2)) {
        float s = std::sqrt(1.0f + m.at(1, 1) - m.at(0, 0) - m.at(2, 2)) * 2.0f;
        q.w = (m.at(0, 2) - m.at(2, 0)) / s;
        q.x = (m.at(0, 1) + m.at(1, 0)) / s;
        q.y = 0.25f * s;
        q.z = (m.at(1, 2) + m.at(2, 1)) / s;
    } else {
        float s = std::sqrt(1.0f + m.at(2, 2) - m.at(0, 0) - m.at(1, 1)) * 2.0f;
        q.w = (m.at(1, 0) - m.at(0, 1)) / s;
        q.x = (m.at(0, 2) + m.at(2, 0)) / s;
        q.y = (m.at(1, 2) + m.at(2, 1)) / s;
        q.z = 0.25f * s;
    }
    return normalize(q);
}

inline Quat slerp_quat(Quat a, Quat b, float t) {
    a = normalize(a);
    b = normalize(b);
    float d = quat_dot(a, b);
    if (d < 0.0f) {
        b = Quat(-b.x, -b.y, -b.z, -b.w);
        d = -d;
    }
    d = clampf(d, -1.0f, 1.0f);
    if (d > 0.9995f) {
        Quat q(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t,
               a.z + (b.z - a.z) * t, a.w + (b.w - a.w) * t);
        return normalize(q);
    }
    float th = std::acos(d);
    float s = std::sin(th);
    float w0 = std::sin((1.0f - t) * th) / s;
    float w1 = std::sin(t * th) / s;
    return normalize(Quat(a.x * w0 + b.x * w1, a.y * w0 + b.y * w1,
                          a.z * w0 + b.z * w1, a.w * w0 + b.w * w1));
}

inline void quat_to_euler(Quat q, float& rx, float& ry, float& rz) {
    q = normalize(q);
    float x = q.x, y = q.y, z = q.z, w = q.w;
    float sinr = 2.0f * (w * x + y * z);
    float cosr = 1.0f - 2.0f * (x * x + y * y);
    rx = std::atan2(sinr, cosr);
    float sinp = 2.0f * (w * y - z * x);
    ry = std::asin(clampf(sinp, -1.0f, 1.0f));
    float siny = 2.0f * (w * z + x * y);
    float cosy = 1.0f - 2.0f * (y * y + z * z);
    rz = std::atan2(siny, cosy);
}

inline float wrap_pi(float a) {
    a = std::fmod(a + kPi, 2.0f * kPi);
    if (a < 0.0f) a += 2.0f * kPi;
    return a - kPi;
}

inline void euler_alt(float rx, float ry, float rz, float& ax, float& ay, float& az) {
    ax = wrap_pi(rx + kPi);
    ay = wrap_pi(kPi - ry);
    az = wrap_pi(rz + kPi);
}

inline float euler_distance(float ax, float ay, float az, float bx, float by, float bz) {
    auto d = [](float u, float v) {
        float x = std::fmod(float(u) - float(v) + kPi, 2.0f * kPi);
        if (x < 0.0f) x += 2.0f * kPi;
        x -= kPi;
        return x;
    };
    float dx = d(ax, bx), dy = d(ay, by), dz = d(az, bz);
    return dx * dx + dy * dy + dz * dz;
}

// Rz.Ry.Rx 分解在俯仰 ±90° 附近有两个等价分支，按上一轮角度选择以保持连续。
inline void quat_to_euler_stable(Quat q, bool has_prev, float px, float py, float pz,
                                 float& rx, float& ry, float& rz) {
    quat_to_euler(q, rx, ry, rz);
    if (!has_prev) return;
    float ax, ay, az;
    euler_alt(rx, ry, rz, ax, ay, az);
    if (euler_distance(ax, ay, az, px, py, pz) <
        euler_distance(rx, ry, rz, px, py, pz)) {
        rx = ax; ry = ay; rz = az;
    }
}

struct Mat4 {
    float m[16] = {1.0f, 0.0f, 0.0f, 0.0f,
                   0.0f, 1.0f, 0.0f, 0.0f,
                   0.0f, 0.0f, 1.0f, 0.0f,
                   0.0f, 0.0f, 0.0f, 1.0f};
    float& at(int r, int c) { return m[r * 4 + c]; }
    float at(int r, int c) const { return m[r * 4 + c]; }
};

inline Mat4 identity4() { return Mat4{}; }

inline Mat4 translation(Vec3 t) {
    Mat4 out;
    out.at(0, 3) = t.x;
    out.at(1, 3) = t.y;
    out.at(2, 3) = t.z;
    return out;
}

inline Mat4 from_quat_pos(Quat q, Vec3 t) {
    Mat4 out;
    Mat3 r = quat_to_mat3(q);
    for (int i = 0; i < 3; ++i)
        for (int j = 0; j < 3; ++j) out.at(i, j) = r.at(i, j);
    out.at(0, 3) = t.x;
    out.at(1, 3) = t.y;
    out.at(2, 3) = t.z;
    return out;
}

inline Mat4 mul(const Mat4& a, const Mat4& b) {
    Mat4 out;
    for (int r = 0; r < 4; ++r)
        for (int c = 0; c < 4; ++c) {
            float sum = 0.0f;
            for (int k = 0; k < 4; ++k) sum += a.at(r, k) * b.at(k, c);
            out.at(r, c) = sum;
        }
    return out;
}

inline Mat4& operator*=(Mat4& a, const Mat4& b) { a = mul(a, b); return a; }

// OpenGL 的 mat4/mat3 按列主序存放，上传 SSBO 前要把行主序矩阵转置。
inline void store_column_major(const Mat4& a, float* out) {
    for (int r = 0; r < 4; ++r)
        for (int c = 0; c < 4; ++c) out[c * 4 + r] = a.m[r * 4 + c];
}

inline Mat3 upper3(const Mat4& a) {
    Mat3 out;
    for (int r = 0; r < 3; ++r)
        for (int c = 0; c < 3; ++c) out.at(r, c) = a.at(r, c);
    return out;
}

inline Vec3 transform_point(const Mat4& a, Vec3 p) {
    return {a.at(0, 0) * p.x + a.at(0, 1) * p.y + a.at(0, 2) * p.z + a.at(0, 3),
            a.at(1, 0) * p.x + a.at(1, 1) * p.y + a.at(1, 2) * p.z + a.at(1, 3),
            a.at(2, 0) * p.x + a.at(2, 1) * p.y + a.at(2, 2) * p.z + a.at(2, 3)};
}

inline Vec3 transform_dir(const Mat4& a, Vec3 p) {
    return {a.at(0, 0) * p.x + a.at(0, 1) * p.y + a.at(0, 2) * p.z,
            a.at(1, 0) * p.x + a.at(1, 1) * p.y + a.at(1, 2) * p.z,
            a.at(2, 0) * p.x + a.at(2, 1) * p.y + a.at(2, 2) * p.z};
}

// 刚体变换求逆（R 正交）。
inline Mat4 inverse_rigid(const Mat4& a) {
    Mat4 out;
    for (int r = 0; r < 3; ++r)
        for (int c = 0; c < 3; ++c) out.at(r, c) = a.at(c, r);
    Vec3 t(a.at(0, 3), a.at(1, 3), a.at(2, 3));
    // out 的第 r 行是 a 的第 r 列（转置），因此平移 = -R^T * t。
    Vec3 inv{-(a.at(0, 0) * t.x + a.at(1, 0) * t.y + a.at(2, 0) * t.z),
             -(a.at(0, 1) * t.x + a.at(1, 1) * t.y + a.at(2, 1) * t.z),
             -(a.at(0, 2) * t.x + a.at(1, 2) * t.y + a.at(2, 2) * t.z)};
    out.at(0, 3) = inv.x;
    out.at(1, 3) = inv.y;
    out.at(2, 3) = inv.z;
    return out;
}

// 透视投影（与 Python OrbitCamera 一致，OpenGL 的 -1..1 深度）。
inline Mat4 perspective(float fov_deg, float aspect, float near_planes, float far_planes) {
    float f = 1.0f / std::tan(fov_deg * kPi / 180.0f * 0.5f);
    Mat4 out;
    out.m[0] = f / (aspect > 0.01f ? aspect : 0.01f);
    out.m[5] = f;
    out.m[10] = (far_planes + near_planes) / (near_planes - far_planes);
    out.m[11] = (2.0f * far_planes * near_planes) / (near_planes - far_planes);
    out.m[14] = -1.0f;
    out.m[15] = 0.0f;
    return out;
}

struct Ray {
    Vec3 origin;
    Vec3 direction;
};

}  // namespace pmx
