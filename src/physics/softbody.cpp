// PMX 2.1 柔体演算：把材质面网格转成 btSoftBody，锚定刚体、固定 pin 顶点，
// 与刚体共用 btSoftRigidDynamicsWorld 的固定 1/60 步进。由 physics.cpp 调用。
#include "physics/physics.hpp"

#if defined(PMX_ENABLE_PHYSICS)

#include <btBulletDynamicsCommon.h>
#include <BulletSoftBody/btSoftRigidDynamicsWorld.h>
#include <BulletSoftBody/btSoftBody.h>

#include "core/morph.hpp"
#include "core/skinning.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <numeric>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <utility>

namespace pmx {
namespace {

btVector3 to_bt(Vec3 v) { return btVector3(v.x, v.y, v.z); }

Vec3 from_bt(btVector3 v) { return Vec3(v.x(), v.y(), v.z()); }

bool finite_vec3(Vec3 v) {
    return std::isfinite(v.x) && std::isfinite(v.y) && std::isfinite(v.z);
}

bool finite_bt(btVector3 v) {
    return std::isfinite(v.x()) && std::isfinite(v.y()) && std::isfinite(v.z());
}

// 柔体节点速度上限：与刚体的 300 一致，防止锚点拉断时数值爆炸。
constexpr float kMaxNodeSpeed = 300.0f;

// Bullet 的弯曲链接用 Floyd 求图距离（n×n），节点多时内存/时间开销很大。
// 超过阈值就跳过该可选特性，只保留三角面结构链接。
constexpr int kMaxBendNodes = 4000;
constexpr int kMaxBendDistance = 8;

}  // namespace

// 每个柔体记录 Bullet 对象与「节点 → 模型顶点」映射，供回读世界坐标。
struct Physics::SoftState {
    struct Entry {
        btSoftBody* body = nullptr;
        std::vector<int> node_vertices;
        std::vector<Vec3> last_positions;  // 上一帧有效坐标，NaN 时回退
    };
    std::vector<Entry> entries;
};

namespace {

// 按材质面区间构建一个柔体；positions 为模型空间顶点坐标。
// 失败（无材质/无有效三角面）返回 nullptr，不抛异常。
btSoftBody* create_soft_body(const Model& model, const SoftBody& sb,
                             const std::vector<Vec3>& positions,
                             const std::vector<btRigidBody*>& rigids,
                             btSoftRigidDynamicsWorld* sw,
                             std::vector<int>& node_vertices) {
    if (sb.material < 0 || sb.material >= static_cast<int>(model.materials.size()))
        return nullptr;
    if (positions.empty() || model.indices.empty()) return nullptr;

    // 面区间：material_ranges 的 start/count 单位是索引数。
    std::size_t start = 0, count = 0;
    bool found = false;
    for (const MaterialRange& r : material_ranges(model)) {
        if (r.material == sb.material) {
            start = r.start;
            count = r.count;
            found = true;
            break;
        }
    }
    if (!found || count < 3) return nullptr;
    const std::size_t nv = positions.size();
    const std::size_t end = std::min(start + count, model.indices.size());
    if (start >= end) return nullptr;

    const float margin = std::isfinite(sb.collision_margin)
                             ? clampf(sb.collision_margin, 0.0f, 10.0f)
                             : 0.0f;
    btSoftBody* psb = new btSoftBody(&sw->getWorldInfo());
    psb->getCollisionShape()->setMargin(margin);
    // 默认构造不创建材质，而 appendNode/Link/Face 都会直接取 m_materials[0]；
    // appendMaterial 对空数组做 ZeroInitialize，因此刚度要显式恢复为 Bullet 默认 1。
    btSoftBody::Material* pm = psb->appendMaterial();
    pm->m_kLST = 1.0f;
    pm->m_kAST = 1.0f;
    pm->m_kVST = 1.0f;
    pm->m_flags = btSoftBody::fMaterial::Default;

    std::unordered_map<int, int> vmap;
    node_vertices.clear();
    auto node_of = [&](std::uint32_t vi) {
        const int key = static_cast<int>(vi);
        auto it = vmap.find(key);
        if (it != vmap.end()) return it->second;
        const int node = static_cast<int>(node_vertices.size());
        psb->appendNode(to_bt(positions[vi]), 1.0f);
        node_vertices.push_back(key);
        vmap.emplace(key, node);
        return node;
    };

    struct Tri {
        int n[3];
        float area2;  // 叉积长度 = 2×面积
    };
    std::vector<Tri> tris;
    tris.reserve((end - start) / 3);

    for (std::size_t k = start; k + 2 < end; k += 3) {
        const std::uint32_t ia = model.indices[k];
        const std::uint32_t ib = model.indices[k + 1];
        const std::uint32_t ic = model.indices[k + 2];
        if (ia >= nv || ib >= nv || ic >= nv) continue;
        if (ia == ib || ib == ic || ic == ia) continue;
        const Vec3 pa = positions[ia];
        const Vec3 pb = positions[ib];
        const Vec3 pc = positions[ic];
        if (!finite_vec3(pa) || !finite_vec3(pb) || !finite_vec3(pc)) continue;
        const float area2 = length(cross(pb - pa, pc - pa));
        if (!(area2 > 1e-12f)) continue;  // 退化面会导致节点质量为 0
        Tri t;
        t.n[0] = node_of(ia);
        t.n[1] = node_of(ib);
        t.n[2] = node_of(ic);
        t.area2 = area2;
        tris.push_back(t);
    }
    if (tris.empty() || node_vertices.empty()) {
        delete psb;
        return nullptr;
    }

    // 三角面 + 边链接（去重）。面用于碰撞/面积，链接用于结构约束。
    std::vector<double> node_area(node_vertices.size(), 0.0);
    std::unordered_set<std::uint64_t> edges;
    edges.reserve(tris.size() * 2);
    for (const Tri& t : tris) {
        const double share = static_cast<double>(t.area2) / 3.0;
        for (int j = 0; j < 3; ++j) {
            node_area[static_cast<std::size_t>(t.n[j])] += share;
            const int a = t.n[j];
            const int b = t.n[(j + 1) % 3];
            const std::uint64_t key =
                (static_cast<std::uint64_t>(std::min(a, b)) << 32) |
                static_cast<std::uint32_t>(std::max(a, b));
            if (edges.insert(key).second) psb->appendLink(a, b);
        }
        psb->appendFace(t.n[0], t.n[1], t.n[2]);
    }

    // 质量：PMX 的总质量按面积分摊到各节点；pins 之后再清零。
    const double total_mass =
        (std::isfinite(sb.total_mass) && sb.total_mass > 1e-6f) ? sb.total_mass : 1.0;
    double area_sum = std::accumulate(node_area.begin(), node_area.end(), 0.0);
    std::vector<double> weights(node_area.size(), 1.0);
    if (area_sum > 1e-12) {
        const double average = area_sum / static_cast<double>(node_area.size());
        for (std::size_t i = 0; i < node_area.size(); ++i)
            weights[i] = node_area[i] > 1e-12 ? node_area[i] : average;
    }
    const double weight_sum =
        std::accumulate(weights.begin(), weights.end(), 0.0);
    if (weight_sum > 1e-12) {
        for (std::size_t i = 0; i < weights.size(); ++i)
            psb->setMass(static_cast<int>(i),
                         static_cast<btScalar>(total_mass * weights[i] / weight_sum));
    }

    // 固定点：质量 0 → 不参与积分，始终停在重建时的世界位置。
    for (int vi : sb.pins) {
        auto it = vmap.find(vi);
        if (it != vmap.end()) psb->setMass(it->second, 0.0f);
    }

    // 材质刚度（PMX 3 项：LST/AST/VST）。全 0 视为未配置，沿用 Bullet 默认 1。
    const float lst = sb.material_params[0];
    const float ast = sb.material_params[1];
    const float vst = sb.material_params[2];
    if (std::isfinite(lst) && std::isfinite(ast) && std::isfinite(vst) &&
        (lst > 0.0f || ast > 0.0f || vst > 0.0f)) {
        pm->m_kLST = clampf(lst, 0.0f, 1.0f);
        pm->m_kAST = clampf(ast, 0.0f, 1.0f);
        pm->m_kVST = clampf(vst, 0.0f, 1.0f);
    }

    // 求解参数：顺序与 PMX 2.1 / Bullet 一致。
    btSoftBody::Config& cfg = psb->m_cfg;
    const float* c = sb.config.data();
    auto cfg01 = [](btScalar* dst, float v) {
        if (std::isfinite(v)) *dst = clampf(v, 0.0f, 1.0f);
    };
    if (std::isfinite(c[0])) cfg.kVCF = std::max<btScalar>(0.0f, c[0]);
    cfg01(&cfg.kDP, c[1]);
    if (std::isfinite(c[2])) cfg.kDG = std::max<btScalar>(0.0f, c[2]);
    if (std::isfinite(c[3])) cfg.kLF = std::max<btScalar>(0.0f, c[3]);
    if (std::isfinite(c[4])) cfg.kPR = c[4];
    if (std::isfinite(c[5])) cfg.kVC = std::max<btScalar>(0.0f, c[5]);
    cfg01(&cfg.kDF, c[6]);
    cfg01(&cfg.kMT, c[7]);
    cfg01(&cfg.kCHR, c[8]);
    cfg01(&cfg.kKHR, c[9]);
    cfg01(&cfg.kSHR, c[10]);
    cfg01(&cfg.kAHR, c[11]);

    // 簇参数（仅生成簇后生效）。
    const float* cl = sb.cluster.data();
    cfg01(&cfg.kSRHR_CL, cl[0]);
    cfg01(&cfg.kSKHR_CL, cl[1]);
    cfg01(&cfg.kSSHR_CL, cl[2]);
    cfg01(&cfg.kSR_SPLT_CL, cl[3]);
    cfg01(&cfg.kSK_SPLT_CL, cl[4]);
    cfg01(&cfg.kSS_SPLT_CL, cl[5]);

    // 迭代次数（V/P/D/C）；全 0 时至少做一次位置求解。
    int it_v = std::clamp(sb.iteration[0], 0, 64);
    int it_p = std::clamp(sb.iteration[1], 0, 64);
    int it_d = std::clamp(sb.iteration[2], 0, 64);
    int it_c = std::clamp(sb.iteration[3], 0, 64);
    if (it_v == 0 && it_p == 0 && it_d == 0 && it_c == 0) it_p = 1;
    cfg.viterations = it_v;
    cfg.piterations = it_p;
    cfg.diterations = it_d;
    cfg.citerations = it_c;

    // 气动模型：越界值回退为 V_Point。
    const int aero = (sb.aero_model >= 0 && sb.aero_model <= 6) ? sb.aero_model : 0;
    cfg.aeromodel = static_cast<btSoftBody::eAeroModel::_>(aero);

    // 可选结构生成：弯曲链接 / 簇 / 随机化（标志位见 pmx.hpp）。
    const int node_count = static_cast<int>(node_vertices.size());
    if ((sb.flags & 0x01) != 0 && sb.b_link_dist > 1 &&
        node_count <= kMaxBendNodes) {
        psb->generateBendingConstraints(std::min(sb.b_link_dist, kMaxBendDistance),
                                        pm);
    }
    if ((sb.flags & 0x02) != 0 && sb.cluster_count > 0) {
        psb->generateClusters(std::min(sb.cluster_count, node_count));
    }
    if ((sb.flags & 0x04) != 0) psb->randomizeConstraints();

    // 锚点：用当前节点位置相对刚体局部坐标固定；禁止被锚定刚体与柔体互相碰撞，
    // 避免节点贴着刚体表面持续抖动。
    for (const SoftBodyAnchor& a : sb.anchors) {
        if (a.rigid < 0 || a.rigid >= static_cast<int>(rigids.size())) continue;
        btRigidBody* rb = rigids[static_cast<std::size_t>(a.rigid)];
        if (!rb) continue;
        auto it = vmap.find(a.vertex);
        if (it == vmap.end()) continue;
        const int node = it->second;
        const btVector3 local =
            rb->getWorldTransform().inverse() * psb->m_nodes[node].m_x;
        psb->appendAnchor(node, rb, local, true, 1.0f);
    }

    // 位姿匹配（kMT）需要记录当前帧，否则该系数不会生效。
    if (cfg.kMT > 0.0f) psb->setPose(false, true);

    return psb;
}

}  // namespace

bool Physics::build_soft() {
    if (!model_) return false;
    return build_soft_at(model_->vertices.pos);
}

bool Physics::build_soft_at(const std::vector<Vec3>& positions) {
    release_soft();
    if (!world_ || !model_ || model_->soft_bodies.empty()) return true;
    btSoftRigidDynamicsWorld* sw = soft_world();
    if (!sw) {
        error = "柔体构建失败：物理世界未就绪（已回退为仅刚体）";
        return false;
    }

    std::vector<btRigidBody*> rigids(model_->rigid.size(), nullptr);
    for (std::size_t i = 0; i < rigids.size(); ++i)
        rigids[i] = rigid_body(static_cast<int>(i));

    soft_ = new SoftState();
    try {
        for (const SoftBody& sb : model_->soft_bodies) {
            SoftState::Entry entry;
            entry.body = create_soft_body(*model_, sb, positions, rigids, sw,
                                          entry.node_vertices);
            if (!entry.body) continue;
            // 先用 entries 接管所有权，后续 reserve/add 抛异常时也能正确回收。
            soft_->entries.push_back(std::move(entry));
            SoftState::Entry& added = soft_->entries.back();
            added.last_positions.reserve(added.body->m_nodes.size());
            for (int i = 0; i < added.body->m_nodes.size(); ++i)
                added.last_positions.push_back(from_bt(added.body->m_nodes[i].m_x));
            const int cg = 1 << (sb.group & 15);
            const int cm = sb.mask & 0xFFFF;
            sw->addSoftBody(added.body, cg, cm);
        }
    } catch (const std::exception& ex) {
        release_soft();
        error = "柔体构建失败：" + std::string(ex.what()) + "（已回退为仅刚体）";
        return false;
    } catch (...) {
        release_soft();
        error = "柔体构建失败（未知异常，已回退为仅刚体）";
        return false;
    }

    if (soft_->entries.empty()) {
        release_soft();
        // 柔体都构建失败（材质无效/无有效三角面）时给出提示，仍保留刚体世界。
        error = "柔体构建失败：没有可用的材质面区间（已回退为仅刚体）";
        return false;
    }
    soft_active_ = true;
    update_soft_output();
    return true;
}

void Physics::release_soft() {
    soft_active_ = false;
    soft_indices_.clear();
    soft_positions_.clear();
    SoftState* state = soft_;
    soft_ = nullptr;
    if (!state) return;
    btSoftRigidDynamicsWorld* sw = soft_world();
    for (SoftState::Entry& entry : state->entries) {
        if (!entry.body) continue;
        if (sw) sw->removeSoftBody(entry.body);
        delete entry.body;
    }
    delete state;
}

void Physics::reset_soft(Pose& pose, const MorphWeights* weights) {
    if (!world_ || !model_) return;
    if (model_->soft_bodies.empty()) {
        release_soft();
        return;
    }

    // 按当前姿态蒙皮得到柔体初始坐标；失败时回退到模型静止坐标。
    std::vector<Vec3> positions;
    try {
        std::vector<Vec3> base;
        const std::vector<Vec3>* src = &model_->vertices.pos;
        if (weights && !weights->empty()) {
            VertexMorphResult vm = apply_vertex_morphs(*model_, *weights);
            if (vm.pos) {
                base = *vm.pos;
                src = &base;
            }
        }
        std::vector<Vec3> zero_normals;
        const std::vector<Vec3>* nrm = &model_->vertices.nrm;
        if (nrm->size() != src->size()) {
            zero_normals.assign(src->size(), Vec3{});
            nrm = &zero_normals;
        }
        std::vector<Vec3> out_normals;
        SkinDeformer deformer(*model_);
        deformer.deform(*src, *nrm, pose.world(), positions, out_normals);
    } catch (const std::exception&) {
        positions.clear();
    }
    if (positions.size() != model_->vertices.pos.size())
        positions = model_->vertices.pos;

    build_soft_at(positions);
}

void Physics::update_soft_output() {
    soft_indices_.clear();
    soft_positions_.clear();
    if (!soft_ || !soft_active_) return;

    // 同一顶点可能被多个柔体引用，按首次出现去重。
    std::unordered_map<int, std::size_t> index_of;
    for (SoftState::Entry& entry : soft_->entries) {
        if (!entry.body) continue;
        const int count = static_cast<int>(
            std::min(entry.node_vertices.size(), entry.last_positions.size()));
        for (int i = 0; i < count; ++i) {
            btSoftBody::Node& node = entry.body->m_nodes[i];
            Vec3 p = from_bt(node.m_x);
            const bool invalid = !finite_bt(node.m_x) || node.m_x.length2() > 1.0e10f;
            if (invalid) {
                p = entry.last_positions[static_cast<std::size_t>(i)];
                node.m_x = to_bt(p);
                node.m_q = node.m_x;
                node.m_v = btVector3(0, 0, 0);
            } else {
                entry.last_positions[static_cast<std::size_t>(i)] = p;
            }
            if (!finite_bt(node.m_v)) {
                node.m_v = btVector3(0, 0, 0);
            } else {
                const btScalar speed = node.m_v.length();
                if (speed > kMaxNodeSpeed)
                    node.m_v *= kMaxNodeSpeed / speed;
            }
            const int vertex = entry.node_vertices[static_cast<std::size_t>(i)];
            auto inserted = index_of.emplace(vertex, soft_positions_.size());
            if (!inserted.second) continue;
            soft_indices_.push_back(vertex);
            soft_positions_.push_back(p);
        }
    }
}

}  // namespace pmx

#endif  // PMX_ENABLE_PHYSICS
