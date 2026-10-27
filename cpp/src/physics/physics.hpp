// Bullet 物理世界：逐项复刻 native/bullet_wrap.cpp 的语义（固定 1/60 步进、
// 运动学刚体休眠策略、速度钳制、6DOF 弹簧关节）。
#pragma once

#include <array>
#include <vector>

#include "core/math.hpp"
#include "core/pmx.hpp"
#include "core/pose.hpp"

class btCollisionConfiguration;
class btCollisionDispatcher;
class btBroadphaseInterface;
class btSequentialImpulseConstraintSolver;
class btDiscreteDynamicsWorld;
class btSoftRigidDynamicsWorld;
class btSoftBody;
class btRigidBody;
class btTypedConstraint;

namespace pmx {

class Physics {
public:
    Physics() = default;
    ~Physics();
    Physics(const Physics&) = delete;
    Physics& operator=(const Physics&) = delete;

    bool build(const Model& model);
    void release();

    bool enabled = false;
    float gravity = -9.8f;
    int iterations = 30;
    bool ground = true;
    int warmup_steps = 30;

    // 静态刚体不参与演算；mode 0 为「骨骼跟随」运动学刚体。
    bool set_params(float new_gravity, int new_iterations);
    bool set_body_params(int index, float* mass, float* friction, float* restitution);

    // 复位到当前姿态（可选预热演算，避免开物理瞬间抖动）。
    void reset(Pose& pose, const MorphWeights* weights, bool warmup);

    // 每帧：同步运动学刚体 → stepSimulation → 回写骨骼覆盖。
    // weights 用于回写后重新叠加骨骼形态（与 Python 版 pose.apply 语义一致）。
    void step(Pose& pose, float dt, const MorphWeights* weights = nullptr);

    const std::vector<int>& bone_of_body() const { return bone_of_body_; }
    const std::vector<int>& body_mode() const { return modes_; }
    std::vector<int> dynamic_bones() const;
    // 刚体当前世界变换（复位/演算后的缓存值）。
    bool body_world(int rigid_index, Vec3& pos, Quat& q) const;
    // 刚体静止系相对骨骼静止系的偏移（渲染骨骼跟随时使用）。
    Mat4 bone_offset(int rigid_index) const;
    float last_max_delta = 1.0f;
    std::string error;

    // ---------------------------------------------------------------- 柔体
    // 是否至少有一个 PMX 柔体成功加入演算世界。
    bool soft_active() const { return soft_active_; }
    // 参与柔体的模型顶点索引（去重，与 soft_world_positions() 一一对应）；
    // 物理未启用时返回空（step 未运行的帧不暴露陈旧坐标）。
    const std::vector<int>& soft_vertex_indices() const {
        static const std::vector<int> empty;
        return enabled ? soft_indices_ : empty;
    }
    // 每帧 step 后的柔体顶点世界坐标（模型空间）；未启用/无柔体时为空。
    const std::vector<Vec3>& soft_world_positions() const {
        static const std::vector<Vec3> empty;
        return enabled ? soft_positions_ : empty;
    }

private:
    struct World;
    struct SoftState;
    World* world_ = nullptr;
    SoftState* soft_ = nullptr;
    const Model* model_ = nullptr;
    std::vector<int> body_map_;
    std::vector<int> bone_of_body_;
    std::vector<int> modes_;
    std::vector<Mat4> offsets_;
    std::vector<std::pair<Vec3, Quat>> rest_;
    std::vector<Vec3> body_positions_;
    std::vector<Quat> body_rotations_;
    std::vector<Vec3> last_step_positions_;
    bool soft_active_ = false;
    std::vector<int> soft_indices_;
    std::vector<Vec3> soft_positions_;

    void move_body(int index, Vec3 pos, Quat q);
    void set_body(int index, Vec3 pos, Quat q);
    void read_body(int index, Vec3& pos, Quat& q) const;
    void clamp_velocities();

    // 柔体实现（softbody.cpp）：刚体世界就绪后构建、复位时按当前姿态重建。
    btSoftRigidDynamicsWorld* soft_world() const;
    btRigidBody* rigid_body(int rigid_index) const;
    bool build_soft();
    bool build_soft_at(const std::vector<Vec3>& positions);
    void release_soft();
    void reset_soft(Pose& pose, const MorphWeights* weights);
    void update_soft_output();
};

}  // namespace pmx
