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
};

static btQuaternion euler_to_quat(float rx, float ry, float rz) {
    // PMX 采用 XYZ 欧拉角（等价于 Blender 'XYZ'），即 Rz * Ry * Rx
    btQuaternion q;
    q.setEulerZYX(rz, ry, rx);
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
    btRigidBody* b = new btRigidBody(info);
    b->setDamping(lin_damp, ang_damp);
    b->setRestitution(restitution);
    b->setFriction(friction);

    int cg = 1 << (group & 15);
    int cm = mask & 0xFFFF;
    if (mass <= 0.0f) {
        if (kinematic) {
            b->setCollisionFlags(b->getCollisionFlags() | btCollisionObject::CF_KINEMATIC_OBJECT);
            b->setActivationState(DISABLE_DEACTIVATION);
        } else {
            b->setCollisionFlags(b->getCollisionFlags() | btCollisionObject::CF_STATIC_OBJECT);
        }
    } else {
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
    b->activate(true);
    if (btMotionState* ms = b->getMotionState()) ms->setWorldTransform(t);
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
    w->world->stepSimulation(dt, max_substeps > 0 ? max_substeps : 4, 1.0f / 60.0f);
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
