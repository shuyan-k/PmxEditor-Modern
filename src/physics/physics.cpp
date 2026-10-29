#include "physics/physics.hpp"

#include <btBulletDynamicsCommon.h>
#include <BulletDynamics/ConstraintSolver/btConeTwistConstraint.h>
#include <BulletDynamics/ConstraintSolver/btGeneric6DofSpringConstraint.h>
#include <BulletDynamics/ConstraintSolver/btHingeConstraint.h>
#include <BulletDynamics/ConstraintSolver/btPoint2PointConstraint.h>
#include <BulletDynamics/ConstraintSolver/btSliderConstraint.h>
#include <BulletSoftBody/btSoftBodyRigidBodyCollisionConfiguration.h>
#include <BulletSoftBody/btSoftRigidDynamicsWorld.h>

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace pmx {
namespace {

btQuaternion to_bt(Quat q) { return btQuaternion(q.x, q.y, q.z, q.w); }

btVector3 to_bt(Vec3 v) { return btVector3(v.x, v.y, v.z); }

btTransform make_transform(Vec3 pos, Vec3 rot_rad) {
    btTransform t;
    t.setIdentity();
    t.setOrigin(to_bt(pos));
    // PMX 刚体/关节旋转为弧度，MMD 使用 YXZ 顺序：R = Ry * Rx * Rz
    btQuaternion qx(btVector3(1, 0, 0), rot_rad.x);
    btQuaternion qy(btVector3(0, 1, 0), rot_rad.y);
    btQuaternion qz(btVector3(0, 0, 1), rot_rad.z);
    btQuaternion q = qy * qx * qz;
    q.normalize();
    t.setRotation(q);
    return t;
}

Quat from_bt(btQuaternion q) { return Quat(q.x(), q.y(), q.z(), q.w()); }

Vec3 from_bt(btVector3 v) { return Vec3(v.x(), v.y(), v.z()); }

// MMD 在界面里显示重力 -9.8，但物理世界用的是 -9.8 × 10（PMX 模型单位约为
// 实物的 1/10）。倍数必须一致，否则布料会变得极「飘」：重力太小，约束和接触的
// 残余冲量就足以把它顶在半空，看起来就是衣服自己飞起来。
const float kGravityScale = 10.0f;
// MMD 的物理固定步长是 1/120，每帧最多 10 个子步。
const float kPhysicsFps = 120.0f;
const int kMaxSubSteps = 10;

// 6DOF 限位：把「锁死在某非零值」的轴改为锁定在静止位。部分胸部 / 裙摆模板
// 写了同值非零端点（例如 y=0.05），若原样交给 Bullet，约束会在静止姿态就要求
// 一个不存在的偏移，把整组刚体互相推挤（胸前一片会被挤成一团）。
void settle_limits(Vec3& lo, Vec3& hi) {
    for (int k = 0; k < 3; ++k) {
        if (std::fabs(lo[k] - hi[k]) <= 1e-6f && std::fabs(lo[k]) > 1e-6f) {
            lo[k] = 0.0f;
            hi[k] = 0.0f;
        }
    }
}


// PMX 关节框架使用 ZYX 顺序（R = Rz·Ry·Rx）。dll 侧按 YXZ 组四元数，
// 这里把目标矩阵分解成 YXZ 三元组，等价于还原同一个旋转。
Vec3 joint_frame_euler(Vec3 rot) {
    const float x = rot.x, y = rot.y, z = rot.z;
    const float cx = std::cos(x), sx = std::sin(x);
    const float cy = std::cos(y), sy = std::sin(y);
    const float cz = std::cos(z), sz = std::sin(z);
    const float r00 = cz * cy;
    const float r01 = cz * sy * sx - sz * cx;
    const float r02 = cz * sy * cx + sz * sx;
    const float r10 = sz * cy;
    const float r11 = sz * sy * sx + cz * cx;
    const float r12 = sz * sy * cx - cz * sx;
    const float r22 = cy * cx;
    float rx = std::asin(std::max(-1.0f, std::min(1.0f, -r12)));
    float ry, rz;
    if (std::fabs(r12) < 1.0f - 1e-6f) {
        ry = std::atan2(r02, r22);
        rz = std::atan2(r10, r11);
    } else {
        rz = 0.0f;
        ry = std::atan2(sx >= 0.0f ? r01 : -r01, r00);
    }
    return {rx, ry, rz};
}

}  // namespace

struct Physics::World {
    btDefaultCollisionConfiguration* config = nullptr;
    btCollisionDispatcher* dispatcher = nullptr;
    btBroadphaseInterface* broadphase = nullptr;
    btSequentialImpulseConstraintSolver* solver = nullptr;
    // 软体与刚体共用一个世界：刚体行为与 btDiscreteDynamicsWorld 一致。
    btSoftRigidDynamicsWorld* world = nullptr;
    std::vector<btRigidBody*> bodies;
    std::vector<btTypedConstraint*> constraints;
    btRigidBody* ground = nullptr;
    btCollisionShape* ground_shape = nullptr;
    // 地面不属于任何碰撞组：用重叠过滤回调强制它与所有刚体/柔体求交
    // （否则掩码为 0 的头发会直接穿过地面，与 MMD 的行为不符）。
    btOverlapFilterCallback* filter = nullptr;
    bool kin_moved = false;
};

Physics::~Physics() { release(); }

namespace {

// 地面强制参与碰撞：PMX 的掩码为 0 的刚体（常见于头发）在 Bullet 里「不与任何组
// 碰撞」，会直接穿过地板。MMD 用一个重叠过滤回调把地面豁免出来。
struct GroundFilter : public btOverlapFilterCallback {
    btBroadphaseProxy* ground = nullptr;
    bool needBroadphaseCollision(btBroadphaseProxy* a, btBroadphaseProxy* b) const override {
        if (a == ground || b == ground) return true;
        return (a->m_collisionFilterGroup & b->m_collisionFilterMask) != 0 &&
               (b->m_collisionFilterGroup & a->m_collisionFilterMask) != 0;
    }
};

}  // namespace

bool Physics::build(const Model& model) {
    release();
    error.clear();
    model_ = &model;
    auto* w = new World();
    world_ = w;
    w->config = new btSoftBodyRigidBodyCollisionConfiguration();
    w->dispatcher = new btCollisionDispatcher(w->config);
    w->broadphase = new btDbvtBroadphase();
    w->solver = new btSequentialImpulseConstraintSolver();
    w->world = new btSoftRigidDynamicsWorld(w->dispatcher, w->broadphase, w->solver, w->config);
    w->world->setGravity(btVector3(0.0f, gravity * kGravityScale, 0.0f));
    // 软体求解器使用世界信息里的重力，需与刚体重力保持一致。
    w->world->getWorldInfo().m_gravity = btVector3(0.0f, gravity * kGravityScale, 0.0f);
    w->world->getSolverInfo().m_numIterations = iterations > 0 ? iterations : 10;
    w->world->getSolverInfo().m_solverMode |= SOLVER_USE_WARMSTARTING;

    if (ground) {
        w->ground_shape = new btStaticPlaneShape(btVector3(0, 1, 0), 0.0f);
        btTransform t;
        t.setIdentity();
        auto* ms = new btDefaultMotionState(t);
        btRigidBody::btRigidBodyConstructionInfo info(0.0, ms, w->ground_shape,
                                                      btVector3(0, 0, 0));
        w->ground = new btRigidBody(info);
        w->ground->setFriction(0.8f);
        w->world->addRigidBody(w->ground, 0xFFFF, -1);
        auto* gf = new GroundFilter();
        gf->ground = w->ground->getBroadphaseProxy();
        w->world->getPairCache()->setOverlapFilterCallback(gf);
        w->filter = gf;
    }

    const std::size_t nr = model.rigid.size();
    body_map_.assign(nr, -1);
    bone_of_body_.assign(nr, -1);
    modes_.assign(nr, 0);
    offsets_.assign(nr, identity4());
    rest_.assign(nr, {Vec3{}, identity_quat()});
    body_positions_.assign(nr, Vec3{});
    body_rotations_.assign(nr, identity_quat());
    last_step_positions_.assign(nr, Vec3{});
    const int nb = static_cast<int>(model.bones.size());

    // 刚性链（六个轴全锁死的关节）仍交给求解器，由 Bullet 默认的限位 ERP 收敛；
    // 曾把整组改成运动学跟随，实测静态姿态反而被拖坏，已废弃。
    for (std::size_t i = 0; i < nr; ++i) {
        const RigidBody& rb = model.rigid[i];
        const int bone = (rb.bone >= 0 && rb.bone < nb) ? rb.bone : -1;
        // MMD：只有「骨骼跟随」(mode 0) 是运动学刚体，质量给 0；mode 1 / 2 都按
        // PMX 质量参与演算。
        const float mass = rb.mode != 0 ? rb.mass : 0.0f;
        const bool kinematic = rb.mode == 0;
        const int shape = static_cast<int>(rb.shape);
        float sx = rb.size.x, sy = rb.size.y, sz = rb.size.z;
        if (shape == 0) {
            sx = std::fabs(sx);
            sy = sx;
            sz = sx;
        } else if (shape == 2) {
            // PMX 胶囊 size.y 为圆柱段高度，与 btCapsuleShape 参数一致。
            const float r = std::fabs(sx);
            sx = r;
            sy = std::max(0.01f, std::fabs(sy));
            sz = r;
        } else {
            sx = std::max(0.001f, std::fabs(sx));
            sy = std::max(0.001f, std::fabs(sy));
            sz = std::max(0.001f, std::fabs(sz));
        }

        btCollisionShape* cs = nullptr;
        switch (shape) {
            case 0: cs = new btSphereShape(sx); break;
            case 1: cs = new btBoxShape(btVector3(sx, sy, sz)); break;
            case 2: cs = new btCapsuleShape(sx, sy); break;
            default: cs = new btSphereShape(sx); break;
        }

        const btTransform t = make_transform(rb.pos, rb.rot);
        btVector3 inertia(0, 0, 0);
        if (mass > 0.0f) cs->calculateLocalInertia(mass, inertia);
        auto* ms = new btDefaultMotionState(t);
        btRigidBody::btRigidBodyConstructionInfo info(mass, ms, cs, inertia);
        // MMD 对所有刚体都开 additionalDamping。
        info.m_additionalDamping = true;
        btRigidBody* body = new btRigidBody(info);
        body->setDamping(rb.mov_damp, rb.rot_damp);
        body->setRestitution(rb.repel);
        body->setFriction(rb.friction);
        // MMD：所有刚体都 DISABLE_DEACTIVATION，并给极低的休眠阈值。默认阈值
        // （0.8 / 1.0 rad）会让布片在「还没被约束拉回去」的时候就睡着，冻结成
        // 散开的形状，之后再也不动。
        body->setSleepingThresholds(0.01f, 0.0017453f);  // 0.1 度
        body->setActivationState(DISABLE_DEACTIVATION);

        // 与 MMD 一致：filterGroup = 1 << 组号（1..16），filterMask 用 PMX 原始掩码。
        const int cg = 1 << (rb.group & 31);
        const int cm = rb.mask & 0xFFFF;
        if (mass <= 0.0f) {
            if (kinematic) {
                body->setCollisionFlags(body->getCollisionFlags() |
                                        btCollisionObject::CF_KINEMATIC_OBJECT);
            } else {
                body->setCollisionFlags(body->getCollisionFlags() |
                                        btCollisionObject::CF_STATIC_OBJECT);
            }
        }
        w->world->addRigidBody(body, cg, cm);
        w->bodies.push_back(body);
        body_map_[i] = static_cast<int>(w->bodies.size()) - 1;
        bone_of_body_[i] = bone;
        modes_[i] = rb.mode;
        const Quat q = rigid_euler_quat(rb.rot.x, rb.rot.y, rb.rot.z);
        rest_[i] = {rb.pos, q};
        // 未复位/未演算前，刚体显示应停在静止位置（与 Python 版一致）。
        body_positions_[i] = rb.pos;
        body_rotations_[i] = q;
        if (bone >= 0) {
            offsets_[i] = mul(inverse_rigid(translation(model.bones[static_cast<std::size_t>(bone)].pos)),
                              from_quat_pos(q, rb.pos));
        } else {
            offsets_[i] = from_quat_pos(q, rb.pos);
        }
    }

    for (const Joint& j : model.joints) {
        const int a = j.rigid_a, b = j.rigid_b;
        if (a < 0 || b < 0 || a >= static_cast<int>(body_map_.size()) ||
            b >= static_cast<int>(body_map_.size()))
            continue;
        const int ba = body_map_[static_cast<std::size_t>(a)];
        const int bb = body_map_[static_cast<std::size_t>(b)];
        if (ba < 0 || bb < 0) continue;
        // Bullet 不允许约束两端是同一个刚体（btDiscreteDynamicsWorld::addConstraint 会断言），
        // PMX 里自连的关节本身也无意义，直接跳过。
        if (ba == bb) continue;

        btRigidBody* rbA = w->bodies[static_cast<std::size_t>(ba)];
        btRigidBody* rbB = w->bodies[static_cast<std::size_t>(bb)];
        const btTransform frame_world = make_transform(j.pos, joint_frame_euler(j.rot));
        const btTransform frame_a = rbA->getWorldTransform().inverse() * frame_world;
        const btTransform frame_b = rbB->getWorldTransform().inverse() * frame_world;

        // 限位：锁死在同一非零值的轴改到静止位，其余按文件原样。
        Vec3 min_loc = j.min_loc, max_loc = j.max_loc;
        Vec3 min_rot = j.min_rot, max_rot = j.max_rot;
        if (j.type == 0 || j.type == 1) {
            settle_limits(min_loc, max_loc);
            settle_limits(min_rot, max_rot);
        }
        const Vec3& slin = j.spring_loc;
        const Vec3& sang = j.spring_rot;

        btTypedConstraint* c = nullptr;
        switch (j.type) {
            case 0:
            case 1: {
                auto* g = new btGeneric6DofSpringConstraint(*rbA, *rbB, frame_a, frame_b, true);
                g->setLinearLowerLimit(to_bt(min_loc));
                g->setLinearUpperLimit(to_bt(max_loc));
                g->setAngularLowerLimit(to_bt(min_rot));
                g->setAngularUpperLimit(to_bt(max_rot));
                if (j.type == 0) {
                    // 与 MMD 一致：只对弹簧系数非零的轴 enableSpring + setStiffness，
                    // 阻尼与平衡点都用 Bullet 默认值（MMD 不设置这两项）。
                    for (int k = 0; k < 3; ++k) {
                        if (slin[k] != 0.0f) {
                            g->enableSpring(k, true);
                            g->setStiffness(k, slin[k]);
                        }
                        if (sang[k] != 0.0f) {
                            g->enableSpring(k + 3, true);
                            g->setStiffness(k + 3, sang[k]);
                        }
                    }
                }
                // 锁死轴不覆盖 STOP_ERP。MMD 直接用 Bullet 默认的 0.2：完全焊接的
                // 长链（如长袖的 30 节刚体）在手臂转动时会带一点弹性滞后，看起来
                // 是「摆过去」；把锁死轴改成 ERP=1.0 会让整条袖子像硬板一样瞬间跟手。
                c = g;
                break;
            }
            case 2: {
                auto* p = new btPoint2PointConstraint(*rbA, *rbB, frame_a.getOrigin(),
                                                      frame_b.getOrigin());
                p->m_setting.m_impulseClamp = 0.0f;
                c = p;
                break;
            }
            case 3: {
                auto* ct = new btConeTwistConstraint(*rbA, *rbB, frame_a, frame_b);
                ct->setLimit(min_rot.z, min_rot.y, min_rot.x, slin.x, slin.y, slin.z);
                ct->setDamping(min_loc.x);
                ct->setFixThresh(max_loc.x);
                c = ct;
                break;
            }
            case 4: {
                auto* s = new btSliderConstraint(*rbA, *rbB, frame_a, frame_b, true);
                s->setLowerLinLimit(min_loc.x);
                s->setUpperLinLimit(max_loc.x);
                s->setLowerAngLimit(min_rot.x);
                s->setUpperAngLimit(max_rot.x);
                s->setPoweredLinMotor(slin.x != 0.0f);
                s->setTargetLinMotorVelocity(slin.y);
                s->setMaxLinMotorForce(slin.z);
                s->setPoweredAngMotor(sang.x != 0.0f);
                s->setTargetAngMotorVelocity(sang.y);
                s->setMaxAngMotorForce(sang.z);
                c = s;
                break;
            }
            case 5: {
                auto* h = new btHingeConstraint(*rbA, *rbB, frame_a, frame_b);
                h->setLimit(min_rot.x, max_rot.x, slin.x, slin.y, slin.z);
                if (sang.x != 0.0f) h->enableAngularMotor(true, sang.y, sang.z);
                c = h;
                break;
            }
            default:
                continue;
        }
        c->setDbgDrawSize(1.0f);
        // 关闭相连刚体之间的碰撞：PMX 里这类关节两端的碰撞体通常大幅重叠，
        // 开着会让求解器先解穿透，把关节整体推开（胸部/袖口会鼓成一个球）。
        w->world->addConstraint(c, true);
        w->constraints.push_back(c);
    }

    // 柔体依赖刚体锚点，必须在刚体/关节建好之后创建。
    build_soft();

    enabled = false;
    return true;
}

void Physics::release() {
    // 柔体引用刚体锚点，先于刚体世界销毁。
    release_soft();
    auto* w = world_;
    if (!w) {
        enabled = false;
        return;
    }
    if (w->world) {
        for (auto* c : w->constraints) w->world->removeConstraint(c);
        for (auto* c : w->constraints) delete c;
        for (auto* b : w->bodies) {
            w->world->removeRigidBody(b);
            delete b->getMotionState();
            delete b->getCollisionShape();
            delete b;
        }
        if (w->ground) {
            w->world->removeRigidBody(w->ground);
            delete w->ground->getMotionState();
            delete w->ground;
            delete w->ground_shape;
        }
        delete w->world;
    }
    delete w->filter;
    delete w->solver;
    delete w->broadphase;
    delete w->dispatcher;
    delete w->config;
    delete w;
    world_ = nullptr;
    enabled = false;
}

bool Physics::set_params(float new_gravity, int new_iterations) {
    gravity = new_gravity;
    iterations = new_iterations > 0 ? new_iterations : 10;
    if (!world_) return false;
    world_->world->setGravity(btVector3(0.0f, gravity * kGravityScale, 0.0f));
    world_->world->getWorldInfo().m_gravity = btVector3(0.0f, gravity * kGravityScale, 0.0f);
    world_->world->getSolverInfo().m_numIterations = iterations;
    return true;
}

bool Physics::set_body_params(int index, float* mass, float* friction, float* restitution) {
    if (!world_ || index < 0 || index >= static_cast<int>(body_map_.size())) return false;
    const int bi = body_map_[static_cast<std::size_t>(index)];
    if (bi < 0) return false;
    btRigidBody* b = world_->bodies[static_cast<std::size_t>(bi)];
    const int flags = b->getCollisionFlags();
    if (mass) {
        if (flags & btCollisionObject::CF_STATIC_OBJECT) return false;
        if (flags & btCollisionObject::CF_KINEMATIC_OBJECT) return false;
        btVector3 inertia(0, 0, 0);
        if (*mass > 0.0f && b->getCollisionShape())
            b->getCollisionShape()->calculateLocalInertia(*mass, inertia);
        b->setMassProps(*mass, inertia);
        b->updateInertiaTensor();
        b->activate(true);
    }
    if (friction) b->setFriction(*friction);
    if (restitution) b->setRestitution(*restitution);
    return true;
}

void Physics::set_body(int index, Vec3 pos, Quat q) {
    if (!world_ || index < 0 || index >= static_cast<int>(world_->bodies.size())) return;
    btRigidBody* b = world_->bodies[static_cast<std::size_t>(index)];
    btTransform t;
    t.setIdentity();
    t.setOrigin(to_bt(pos));
    t.setRotation(to_bt(q));
    b->setWorldTransform(t);
    b->setInterpolationWorldTransform(t);
    b->setLinearVelocity(btVector3(0, 0, 0));
    b->setAngularVelocity(btVector3(0, 0, 0));
    b->activate(true);
    if (btMotionState* ms = b->getMotionState()) ms->setWorldTransform(t);
}

void Physics::move_body(int index, Vec3 pos, Quat q) {
    if (!world_ || index < 0 || index >= static_cast<int>(world_->bodies.size())) return;
    btRigidBody* b = world_->bodies[static_cast<std::size_t>(index)];
    btTransform t;
    t.setIdentity();
    t.setOrigin(to_bt(pos));
    btQuaternion bq = to_bt(normalize(q));
    bq.normalize();
    t.setRotation(bq);
    if (btMotionState* ms = b->getMotionState()) ms->setWorldTransform(t);
    b->setWorldTransform(t);
    // MMD 的运动学刚体常驻 DISABLE_DEACTIVATION，靠它把动态刚体一起拖走；
    // 这里不再按「本帧是否移动」切换休眠状态（那会让布片中途睡死）。
    b->setInterpolationWorldTransform(t);
}

void Physics::read_body(int index, Vec3& pos, Quat& q) const {
    if (!world_ || index < 0 || index >= static_cast<int>(world_->bodies.size())) return;
    const btTransform t = world_->bodies[static_cast<std::size_t>(index)]->getWorldTransform();
    pos = from_bt(t.getOrigin());
    q = from_bt(t.getRotation());
}


std::vector<int> Physics::dynamic_bones() const {
    std::vector<int> out;
    for (std::size_t i = 0; i < body_map_.size(); ++i) {
        if (body_map_[i] < 0 || modes_[i] == 0) continue;
        if (bone_of_body_[i] >= 0) out.push_back(bone_of_body_[i]);
    }
    std::sort(out.begin(), out.end());
    out.erase(std::unique(out.begin(), out.end()), out.end());
    return out;
}

bool Physics::body_world(int rigid_index, Vec3& pos, Quat& q) const {
    if (rigid_index < 0 || rigid_index >= static_cast<int>(body_map_.size())) return false;
    if (body_map_[static_cast<std::size_t>(rigid_index)] < 0) return false;
    pos = body_positions_[static_cast<std::size_t>(rigid_index)];
    q = body_rotations_[static_cast<std::size_t>(rigid_index)];
    return true;
}

Mat4 Physics::bone_offset(int rigid_index) const {
    if (rigid_index < 0 || rigid_index >= static_cast<int>(offsets_.size())) return identity4();
    return offsets_[static_cast<std::size_t>(rigid_index)];
}

// ---------------------------------------------------------------- 柔体桥接
btSoftRigidDynamicsWorld* Physics::soft_world() const {
    return world_ ? world_->world : nullptr;
}

btRigidBody* Physics::rigid_body(int rigid_index) const {
    if (!world_ || rigid_index < 0 || rigid_index >= static_cast<int>(body_map_.size()))
        return nullptr;
    const int bi = body_map_[static_cast<std::size_t>(rigid_index)];
    if (bi < 0 || bi >= static_cast<int>(world_->bodies.size())) return nullptr;
    return world_->bodies[static_cast<std::size_t>(bi)];
}

void Physics::clear_velocities() {
    if (!world_) return;
    for (auto* b : world_->bodies) {
        b->clearForces();
        b->setLinearVelocity(btVector3(0, 0, 0));
        b->setAngularVelocity(btVector3(0, 0, 0));
    }
}

void Physics::reset(Pose& pose, const MorphWeights* weights, bool warmup) {
    if (!world_) return;
    pose.clear_overrides();
    pose.apply(weights);
    const std::vector<Mat4>& W = pose.world();
    // 与 MMD 的「物理リセット」一致：所有刚体都按当前姿态落到骨头上，
    // 速度清零。MMD 会在这里用「全部按运动学」跑一步再做后续回写；
    // 这里只摆放（不演算），避免把布片先甩出去。
    for (std::size_t i = 0; i < body_map_.size(); ++i) {
        const int bi = body_map_[i];
        if (bi < 0) continue;
        const int bone = bone_of_body_[i];
        Vec3 pos;
        Quat q;
        if (bone >= 0 && bone < static_cast<int>(W.size()) && bone < pose.n) {
            const Mat4 M = mul(W[static_cast<std::size_t>(bone)], offsets_[i]);
            pos = {M.at(0, 3), M.at(1, 3), M.at(2, 3)};
            q = mat3_to_quat(upper3(M));
        } else {
            pos = rest_[i].first;
            q = rest_[i].second;
        }
        set_body(bi, pos, q);
        body_positions_[i] = pos;
        body_rotations_[i] = q;
    }
    for (auto* b : world_->bodies) {
        b->clearForces();
        b->setLinearVelocity(btVector3(0, 0, 0));
        b->setAngularVelocity(btVector3(0, 0, 0));
    }


    // 柔体按当前姿态（蒙皮后）重建，锚点重新绑定到刚体当前变换。
    reset_soft(pose, weights);

    if (warmup && warmup_steps > 0) {
        for (int k = 0; k < warmup_steps; ++k)
            world_->world->stepSimulation(1.0f / kPhysicsFps, kMaxSubSteps, 1.0f / kPhysicsFps);
        for (std::size_t i = 0; i < body_map_.size(); ++i) {
            const int bi = body_map_[i];
            if (bi < 0) continue;
            read_body(bi, body_positions_[i], body_rotations_[i]);
        }
        update_soft_output();
    }
    last_step_positions_ = body_positions_;
    last_max_delta = 1.0f;
}

void Physics::step(Pose& pose, float dt, const MorphWeights* weights) {
    if (!world_ || !enabled) {
        // 未启用演算时不保留上一帧的柔体坐标，避免界面读到陈旧数据。
        soft_indices_.clear();
        soft_positions_.clear();
        return;
    }
    auto* w = world_;
    const int nb = pose.n;

    // 0) 先还原成「纯动画」姿态：上一帧的物理覆盖必须清掉。运动学刚体跟随的是
    //    本帧动画姿态（而不是上一帧的物理结果），付与继承也要在干净姿态上求值。
    pose.clear_overrides();
    pose.apply(weights);
    const std::vector<Mat4>& W = pose.world();

    // 1) 运动学刚体同步：跟随骨骼把刚体搬到本帧位置。
    for (std::size_t i = 0; i < body_map_.size(); ++i) {
        const int bi = body_map_[i];
        if (bi < 0 || modes_[i] != 0) continue;
        const int bone = bone_of_body_[i];
        if (bone < 0 || bone >= nb) continue;
        const Mat4 M = mul(W[static_cast<std::size_t>(bone)], offsets_[i]);
        move_body(bi, Vec3(M.at(0, 3), M.at(1, 3), M.at(2, 3)),
                  mat3_to_quat(upper3(M)));
    }

    // 2) 演算：MMD 固定 1/120 秒步长，每帧最多 10 个子步。
    w->world->stepSimulation(dt, kMaxSubSteps, 1.0f / kPhysicsFps);
    // 柔体与刚体同一次 stepSimulation 推进，这里只回读输出坐标。
    update_soft_output();

    // 3) 回读
    for (std::size_t i = 0; i < body_map_.size(); ++i) {
        const int bi = body_map_[i];
        if (bi < 0) continue;
        read_body(bi, body_positions_[i], body_rotations_[i]);
    }


    // 4) 动态刚体覆盖骨骼：交给 Pose 按 eval_order 一次求值。
    //    同一根骨骼挂多个刚体时以最后一个为准；「物理后变形」骨骼不接收覆盖。
    std::unordered_map<int, BoneOverride> targets;
    for (std::size_t i = 0; i < body_map_.size(); ++i) {
        const int bi = body_map_[i];
        if (bi < 0 || modes_[i] == 0) continue;
        const int bone = bone_of_body_[i];
        if (bone < 0 || bone >= nb) continue;
        if (model_ && (model_->bones[static_cast<std::size_t>(bone)].flags &
                       BF_AFTER_PHYSICS))
            continue;
        BoneOverride& ov = targets[bone];
        ov.world = mul(from_quat_pos(body_rotations_[i], body_positions_[i]),
                       inverse_rigid(offsets_[i]));
        ov.keep_translation = modes_[i] == 2;
    }
    if (targets.empty()) {
        pose.apply(weights);
        pose.world();
    } else {
        pose.apply_physics_world(targets, weights);
    }

    if (body_positions_.size() == last_step_positions_.size() && !body_positions_.empty()) {
        float maxd = 0.0f;
        for (std::size_t i = 0; i < body_positions_.size(); ++i) {
            const Vec3 d = body_positions_[i] - last_step_positions_[i];
            maxd = std::max(maxd, std::max(std::fabs(d.x), std::max(std::fabs(d.y), std::fabs(d.z))));
        }
        last_max_delta = maxd;
        last_step_positions_ = body_positions_;
    }
}

}  // namespace pmx

