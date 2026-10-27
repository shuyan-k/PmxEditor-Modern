// MMD 风格 Bullet 物理封装（C ABI，供 ctypes 调用）
// 关键点：使用 btGeneric6DofSpringConstraint，完整保留 PMX Joint 的
// 三轴移动/旋转限位与弹簧参数；min > max 时按 MMD/Bullet 2.75 语义视为自由轴。
#include <btBulletDynamicsCommon.h>
#include <BulletDynamics/ConstraintSolver/btGeneric6DofSpringConstraint.h>
#include <BulletDynamics/ConstraintSolver/btConeTwistConstraint.h>
#include <BulletDynamics/ConstraintSolver/btHingeConstraint.h>
#include <BulletDynamics/ConstraintSolver/btSliderConstraint.h>
#include <BulletDynamics/ConstraintSolver/btPoint2PointConstraint.h>
#include <vector>
#include <cmath>

#ifdef _WIN32
#define BW_EXPORT extern "C" __declspec(dllexport)
#else
#define BW_EXPORT extern "C"
#endif

struct BWWorld {
    btDefaultCollisionConfiguration* config = nullptr;
    btCollisionDispatcher* dispatcher = nullptr;
    btBroadphaseInterface* broadphase = nullptr;
    btSequentialImpulseConstraintSolver* solver = nullptr;
    btDiscreteDynamicsWorld* world = nullptr;
    std::vector<btRigidBody*> bodies;
    std::vector<btTypedConstraint*> constraints;
    btRigidBody* ground = nullptr;
    btCollisionShape* groundShape = nullptr;
    // 速度安全阀：骨骼瞬移/约束爆冲时把能量钳回合理范围（MMD 模型
    // 尺度约 20 单位高，300 单位/s 约等于 24 m/s，远超正常摆动）
    float max_lin_vel = 300.0f;
    float max_ang_vel = 150.0f;
    // 速度死区：低于阈值直接清零，抑制收敛后的高频微振
    float sleep_lin_vel = 0.05f;
    float sleep_ang_vel = 0.05f;
    // 本帧是否有运动学刚体发生可见位移：有则唤醒全部动态刚体
    // （Bullet 的关节约束不会唤醒休眠刚体，不动则保持休眠省 CPU）
    bool kin_moved = false;
    float kin_move_epsilon = 0.001f;
    unsigned kin_wake_count = 0;  // 诊断：kin_moved 唤醒累计次数
};

static void clamp_velocities(BWWorld* w) {
    for (auto* b : w->bodies) {
        if (b->getMass() <= 0.0f) continue;
        btVector3 v = b->getLinearVelocity();
        float lv = v.length();
        if (lv > w->max_lin_vel) {
            b->setLinearVelocity(v * (w->max_lin_vel / lv));
        } else if (lv < w->sleep_lin_vel) {
            b->setLinearVelocity(btVector3(0, 0, 0));
        }
        btVector3 av = b->getAngularVelocity();
        float aav = av.length();
        if (aav > w->max_ang_vel) {
            b->setAngularVelocity(av * (w->max_ang_vel / aav));
        } else if (aav < w->sleep_ang_vel) {
            b->setAngularVelocity(btVector3(0, 0, 0));
        }
    }
}

static btQuaternion euler_to_quat(float rx, float ry, float rz) {
    // PMX 刚体/关节旋转是弧度制，MMD 使用 YXZ 顺序：R = Ry * Rx * Rz
    btQuaternion qx(btVector3(1, 0, 0), rx);
    btQuaternion qy(btVector3(0, 1, 0), ry);
    btQuaternion qz(btVector3(0, 0, 1), rz);
    btQuaternion q = qy * qx * qz;
    q.normalize();
    return q;
}

static btTransform make_transform(const float* pos, const float* rot) {
    btTransform t;
    t.setIdentity();
    t.setOrigin(btVector3(pos[0], pos[1], pos[2]));
    t.setRotation(euler_to_quat(rot[0], rot[1], rot[2]));
    return t;
}

BW_EXPORT BWWorld* bw_create(float gx, float gy, float gz, int iterations) {
    BWWorld* w = new BWWorld();
    w->config = new btDefaultCollisionConfiguration();
    w->dispatcher = new btCollisionDispatcher(w->config);
    w->broadphase = new btDbvtBroadphase();
    w->solver = new btSequentialImpulseConstraintSolver();
    w->world = new btDiscreteDynamicsWorld(w->dispatcher, w->broadphase, w->solver, w->config);
    w->world->setGravity(btVector3(gx, gy, gz));
    w->world->getSolverInfo().m_numIterations = iterations > 0 ? iterations : 10;
    w->world->getSolverInfo().m_solverMode |= SOLVER_USE_WARMSTARTING;
    return w;
}

BW_EXPORT void bw_destroy(BWWorld* w) {
    if (!w) return;
    for (auto* c : w->constraints) w->world->removeConstraint(c);
    for (auto* c : w->constraints) delete c;
    w->constraints.clear();
    for (auto* b : w->bodies) {
        w->world->removeRigidBody(b);
        delete b->getMotionState();
        delete b;
    }
    w->bodies.clear();
    if (w->ground) {
        w->world->removeRigidBody(w->ground);
        delete w->ground->getMotionState();
        delete w->ground;
        delete w->groundShape;
    }
    delete w->world;
    delete w->solver;
    delete w->broadphase;
    delete w->dispatcher;
    delete w->config;
    delete w;
}

BW_EXPORT void bw_set_gravity(BWWorld* w, float x, float y, float z) {
    if (w) w->world->setGravity(btVector3(x, y, z));
}

BW_EXPORT void bw_set_iterations(BWWorld* w, int n) {
    if (w) w->world->getSolverInfo().m_numIterations = n > 0 ? n : 10;
}

BW_EXPORT void bw_add_ground(BWWorld* w, float y) {
    if (!w || w->ground) return;
    w->groundShape = new btStaticPlaneShape(btVector3(0, 1, 0), -y);
    btTransform t;
    t.setIdentity();
    btDefaultMotionState* ms = new btDefaultMotionState(t);
    btRigidBody::btRigidBodyConstructionInfo info(0.0, ms, w->groundShape, btVector3(0, 0, 0));
    w->ground = new btRigidBody(info);
    w->ground->setFriction(0.8);
    w->world->addRigidBody(w->ground);
}

BW_EXPORT int bw_add_body(BWWorld* w, int shape, float sx, float sy, float sz,
                          float px, float py, float pz, float rx, float ry, float rz,
                          float mass, float lin_damp, float ang_damp, float restitution,
                          float friction, int group, int mask, int kinematic) {
    if (!w) return -1;
    btCollisionShape* cs = nullptr;
    switch (shape) {
        case 0: cs = new btSphereShape(sx); break;
        case 1: cs = new btBoxShape(btVector3(sx, sy, sz)); break;
        case 2: cs = new btCapsuleShape(sx, sy); break;
        default: cs = new btSphereShape(sx); break;
    }
    btTransform t = make_transform(&btVector3(px, py, pz)[0], &btVector3(rx, ry, rz)[0]);
    btVector3 inertia(0, 0, 0);
    if (mass > 0.0f) cs->calculateLocalInertia(mass, inertia);
    btDefaultMotionState* ms = new btDefaultMotionState(t);
    btRigidBody::btRigidBodyConstructionInfo info(mass, ms, cs, inertia);
    if (mass > 0.0f) {
        // 额外阻尼吸收高频振荡能量，抑制瞬移后的抖动（零成本防线）；
        // 本版 Bullet 没有 setAdditionalDamping 接口，走构造参数。
        info.m_additionalDamping = true;
    }
    btRigidBody* b = new btRigidBody(info);
    b->setDamping(lin_damp, ang_damp);
    b->setRestitution(restitution);
    b->setFriction(friction);

    int cg = 1 << (group & 15);
    int cm = mask & 0xFFFF;
    if (mass <= 0.0f) {
        if (kinematic) {
            b->setCollisionFlags(b->getCollisionFlags() | btCollisionObject::CF_KINEMATIC_OBJECT);
            // 不能 DISABLE_DEACTIVATION：island 管理器的接触回调会让
            // 「非 ISLAND_SLEEPING 的运动学刚体」每帧 activate 其接触对象
            // （activate 同时把休眠计时归零），头发贴头/裙贴腿这类持续接触
            // 使整片动态刚体永远无法入睡。改由 bw_move_body 按本帧是否
            // 位移在 ACTIVE_TAG / ISLAND_SLEEPING 之间切换。
            b->setActivationState(ISLAND_SLEEPING);
        } else {
            b->setCollisionFlags(b->getCollisionFlags() | btCollisionObject::CF_STATIC_OBJECT);
        }
    } else {
        // 允许休眠：静止 2 秒后整岛休眠是物理帧率的来源。休眠刚体不会被
        // 关节约束唤醒，因此由 bw_step 在运动学刚体移动时统一唤醒（见
        // kin_moved），避免「头发冻结在半空」。
        b->setActivationState(ACTIVE_TAG);
        b->setDeactivationTime(0.0f);
    }
    w->world->addRigidBody(b, cg, cm);
    w->bodies.push_back(b);
    return (int)w->bodies.size() - 1;
}

BW_EXPORT void bw_set_body(BWWorld* w, int index, const float* pos, const float* quat) {
    if (!w || index < 0 || index >= (int)w->bodies.size()) return;
    btRigidBody* b = w->bodies[index];
    btTransform t;
    t.setIdentity();
    t.setOrigin(btVector3(pos[0], pos[1], pos[2]));
    t.setRotation(btQuaternion(quat[0], quat[1], quat[2], quat[3]));
    b->setWorldTransform(t);
    b->setInterpolationWorldTransform(t);
    b->setLinearVelocity(btVector3(0, 0, 0));
    b->setAngularVelocity(btVector3(0, 0, 0));
    b->activate(true);
    if (btMotionState* ms = b->getMotionState()) ms->setWorldTransform(t);
}

// 运动学刚体的逐帧同步：只写 MotionState 与世界变换，不碰插值变换。
// stepSimulation 里的 saveKinematicState 会从 MotionState 读入新变换，
// 并用「上一帧插值变换 → 当前变换」推导运动学速度写入刚体——求解器据此
// 拿到正确的相对速度，关节动量传递平滑。旧写法把插值变换也刷成新值，
// 推导出的速度恒为 0，等价于每帧一次「零速瞬移」，关节只能靠 Baumgarte
// 位置修正硬拉动态刚体，能量突变表现为抖动（摆姿/瞬移时尤其明显）。
// 瞬移产生的第一帧超速由 bw_step 后对动态刚体的钳制兜底。
BW_EXPORT void bw_move_body(BWWorld* w, int index, const float* pos, const float* quat, float dt) {
    (void)dt;  // 速度由 saveKinematicState 按固定步长推导，这里无需 dt
    if (!w || index < 0 || index >= (int)w->bodies.size()) return;
    btRigidBody* b = w->bodies[index];
    btTransform t;
    t.setIdentity();
    t.setOrigin(btVector3(pos[0], pos[1], pos[2]));
    btQuaternion q(quat[0], quat[1], quat[2], quat[3]);
    q.normalize();
    t.setRotation(q);
    const btTransform prev = b->getWorldTransform();
    const bool moved =
        (t.getOrigin() - prev.getOrigin()).length2() >
            w->kin_move_epsilon * w->kin_move_epsilon ||
        std::fabs(t.getRotation().angle(prev.getRotation())) >
            w->kin_move_epsilon;
    if (moved) w->kin_moved = true;
    if (btMotionState* ms = b->getMotionState()) ms->setWorldTransform(t);
    b->setWorldTransform(t);
    if (b->getCollisionFlags() & btCollisionObject::CF_KINEMATIC_OBJECT) {
        if (moved) {
            // 本帧有位移：保持激活，saveKinematicState 才能推导运动学
            // 速度，接触回调也会据此唤醒贴着的动态刚体。
            b->setActivationState(ACTIVE_TAG);
            b->setDeactivationTime(0.0f);
        } else {
            // 静止的运动学刚体立即休眠，切断「接触唤醒 → 休眠计时归零」
            // 链路（见 bw_add_body 注释）。碰撞不受影响：求解器按动态方
            // 所在的岛处理接触对。速度清零避免残留值污染摩擦求解。
            b->setLinearVelocity(btVector3(0, 0, 0));
            b->setAngularVelocity(btVector3(0, 0, 0));
            b->setActivationState(ISLAND_SLEEPING);
        }
    } else {
        b->activate(true);
    }
}

BW_EXPORT void bw_set_limits(BWWorld* w, float max_lin_vel, float max_ang_vel,
                             float sleep_lin_vel, float sleep_ang_vel) {
    if (!w) return;
    if (max_lin_vel > 0.0f) w->max_lin_vel = max_lin_vel;
    if (max_ang_vel > 0.0f) w->max_ang_vel = max_ang_vel;
    if (sleep_lin_vel >= 0.0f) w->sleep_lin_vel = sleep_lin_vel;
    if (sleep_ang_vel >= 0.0f) w->sleep_ang_vel = sleep_ang_vel;
}

BW_EXPORT void bw_get_body(BWWorld* w, int index, float* out_pos, float* out_quat) {
    if (!w || index < 0 || index >= (int)w->bodies.size()) return;
    btTransform t = w->bodies[index]->getWorldTransform();
    btVector3 p = t.getOrigin();
    btQuaternion q = t.getRotation();
    out_pos[0] = p.x(); out_pos[1] = p.y(); out_pos[2] = p.z();
    out_quat[0] = q.x(); out_quat[1] = q.y(); out_quat[2] = q.z(); out_quat[3] = q.w();
}

// 运行时修改刚体质量：静态/运动学刚体跳过，改完必须重算惯性张量并唤醒。
BW_EXPORT int bw_set_body_mass(BWWorld* w, int index, float mass) {
    if (!w || index < 0 || index >= (int)w->bodies.size()) return 0;
    btRigidBody* b = w->bodies[index];
    int flags = b->getCollisionFlags();
    if (flags & btCollisionObject::CF_STATIC_OBJECT) return 0;
    if (flags & btCollisionObject::CF_KINEMATIC_OBJECT) return 0;
    btVector3 inertia(0, 0, 0);
    if (mass > 0.0f && b->getCollisionShape()) {
        b->getCollisionShape()->calculateLocalInertia(mass, inertia);
    }
    b->setMassProps(mass, inertia);
    b->updateInertiaTensor();
    b->activate(true);
    return 1;
}

BW_EXPORT void bw_set_body_friction(BWWorld* w, int index, float friction) {
    if (!w || index < 0 || index >= (int)w->bodies.size()) return;
    w->bodies[index]->setFriction(friction);
}

BW_EXPORT void bw_set_body_restitution(BWWorld* w, int index, float restitution) {
    if (!w || index < 0 || index >= (int)w->bodies.size()) return;
    w->bodies[index]->setRestitution(restitution);
}

BW_EXPORT void bw_apply_impulse(BWWorld* w, int index, float ix, float iy, float iz,
                                float tx, float ty, float tz) {
    if (!w || index < 0 || index >= (int)w->bodies.size()) return;
    btRigidBody* b = w->bodies[index];
    b->activate(true);
    b->applyCentralImpulse(btVector3(ix, iy, iz));
    b->applyTorqueImpulse(btVector3(tx, ty, tz));
}

BW_EXPORT int bw_add_joint(BWWorld* w, int type, int a, int b,
                           const float* pos, const float* rot,
                           const float* lmin, const float* lmax,
                           const float* amin, const float* amax,
                           const float* slin, const float* sang) {
    if (!w || a < 0 || b < 0 || a >= (int)w->bodies.size() || b >= (int)w->bodies.size()) return -1;
    btRigidBody* rbA = w->bodies[a];
    btRigidBody* rbB = w->bodies[b];
    btTransform frameWorld = make_transform(pos, rot);
    btTransform frameA = rbA->getWorldTransform().inverse() * frameWorld;
    btTransform frameB = rbB->getWorldTransform().inverse() * frameWorld;

    btTypedConstraint* c = nullptr;
    switch (type) {
        case 0:
        case 1: {
            btGeneric6DofSpringConstraint* g = new btGeneric6DofSpringConstraint(*rbA, *rbB, frameA, frameB, true);
            g->setLinearLowerLimit(btVector3(lmin[0], lmin[1], lmin[2]));
            g->setLinearUpperLimit(btVector3(lmax[0], lmax[1], lmax[2]));
            g->setAngularLowerLimit(btVector3(amin[0], amin[1], amin[2]));
            g->setAngularUpperLimit(btVector3(amax[0], amax[1], amax[2]));
            if (type == 0) {
                for (int i = 0; i < 3; ++i) {
                    g->enableSpring(i, true);
                    g->setStiffness(i, slin[i]);
                    g->setDamping(i, 0.5f);
                    g->enableSpring(i + 3, true);
                    g->setStiffness(i + 3, sang[i]);
                    g->setDamping(i + 3, 0.5f);
                }
                g->setEquilibriumPoint();
            }
            c = g;
            break;
        }
        case 2: {
            btPoint2PointConstraint* p = new btPoint2PointConstraint(*rbA, *rbB, frameA.getOrigin(), frameB.getOrigin());
            p->m_setting.m_impulseClamp = 0.0f;
            c = p;
            break;
        }
        case 3: {
            btConeTwistConstraint* ct = new btConeTwistConstraint(*rbA, *rbB, frameA, frameB);
            ct->setLimit(amin[2], amin[1], amin[0], slin[0], slin[1], slin[2]);
            ct->setDamping(lmin[0]);
            ct->setFixThresh(lmax[0]);
            c = ct;
            break;
        }
        case 4: {
            btSliderConstraint* s = new btSliderConstraint(*rbA, *rbB, frameA, frameB, true);
            s->setLowerLinLimit(lmin[0]);
            s->setUpperLinLimit(lmax[0]);
            s->setLowerAngLimit(amin[0]);
            s->setUpperAngLimit(amax[0]);
            s->setPoweredLinMotor(slin[0] != 0.0f);
            s->setTargetLinMotorVelocity(slin[1]);
            s->setMaxLinMotorForce(slin[2]);
            s->setPoweredAngMotor(sang[0] != 0.0f);
            s->setTargetAngMotorVelocity(sang[1]);
            s->setMaxAngMotorForce(sang[2]);
            c = s;
            break;
        }
        case 5: {
            btHingeConstraint* h = new btHingeConstraint(*rbA, *rbB, frameA, frameB);
            h->setLimit(amin[0], amax[0], slin[0], slin[1], slin[2]);
            if (sang[0] != 0.0f) h->enableAngularMotor(true, sang[1], sang[2]);
            c = h;
            break;
        }
        default:
            return -1;
    }
    if (!c) return -1;
    c->setDbgDrawSize(1.0f);
    w->world->addConstraint(c, true);
    w->constraints.push_back(c);
    return (int)w->constraints.size() - 1;
}

BW_EXPORT void bw_step(BWWorld* w, float dt, int max_substeps) {
    if (!w) return;
    if (w->kin_moved) {
        // 关节不会唤醒休眠刚体：运动学父级一动，把所有动态刚体唤醒
        for (auto* b : w->bodies) {
            if (b->getMass() > 0.0f) b->activate(true);
        }
        w->kin_moved = false;
        ++w->kin_wake_count;
    }
    w->world->stepSimulation(dt, max_substeps > 0 ? max_substeps : 4, 1.0f / 60.0f);
    clamp_velocities(w);
}

// 诊断：动态刚体激活状态计数（按 Bullet 枚举 1..5 直存）、最大休眠计时、
// 最大线/角速度、kin 唤醒累计。states6[1]=ACTIVE [2]=SLEEPING [3]=WANTS [4]=DISABLE_DEACT
BW_EXPORT void bw_diag(BWWorld* w, int* states6, float* max_deact,
                       float* max_lv, float* max_av, unsigned* kin_wakes) {
    if (!w) return;
    int st[6] = {0, 0, 0, 0, 0, 0};
    float md = 0.0f, mlv = 0.0f, mav = 0.0f;
    for (auto* b : w->bodies) {
        if (b->getMass() <= 0.0f) continue;
        int s = b->getActivationState();
        if (s >= 0 && s <= 5) ++st[s];
        if (b->getDeactivationTime() > md) md = b->getDeactivationTime();
        float lv = b->getLinearVelocity().length();
        float av = b->getAngularVelocity().length();
        if (lv > mlv) mlv = lv;
        if (av > mav) mav = av;
    }
    if (states6) for (int i = 0; i < 6; ++i) states6[i] = st[i];
    if (max_deact) *max_deact = md;
    if (max_lv) *max_lv = mlv;
    if (max_av) *max_av = mav;
    if (kin_wakes) *kin_wakes = w->kin_wake_count;
}

BW_EXPORT int bw_body_count(BWWorld* w) {
    return w ? (int)w->bodies.size() : 0;
}

BW_EXPORT void bw_clear_forces(BWWorld* w) {
    if (!w) return;
    for (auto* b : w->bodies) {
        if (b->getMass() > 0.0f) {
            b->clearForces();
            b->setLinearVelocity(btVector3(0, 0, 0));
            b->setAngularVelocity(btVector3(0, 0, 0));
        }
    }
}
