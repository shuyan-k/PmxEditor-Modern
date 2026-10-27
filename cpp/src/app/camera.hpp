// 轨道相机：目标点 + 球面角 + 距离，交互语义与 Python 版 OrbitCamera 一致。
#pragma once

#include "core/math.hpp"

namespace pmx {

class OrbitCamera {
public:
    Vec3 target{0.0f, 10.0f, 0.0f};
    float distance = 40.0f;
    float yaw = kPi;
    float pitch = 0.18f;
    float fov = 38.0f;
    float near_plane = 0.1f;
    float far_plane = 4000.0f;

    Vec3 eye() const;
    Mat4 view() const;
    Mat4 projection(float aspect) const;

    Vec3 right() const;
    Vec3 up_vec() const;

    void orbit(float dx, float dy);
    void pan(float dx, float dy);
    void zoom(float scroll);

    void fit(Vec3 lo, Vec3 hi);
    void frame(Vec3 center, float distance_);

    // 屏幕坐标（左上原点）→ 世界射线。
    Ray ray(float sx, float sy, int width, int height) const;
};

}  // namespace pmx
