// PMX 2.0 / 2.1 数据模型（与 Python 版 pmx.py 的字段一一对应）。
#pragma once

#include <array>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

#include "core/math.hpp"

namespace pmx {

// ---------------------------------------------------------------- 常量
constexpr int WT_BDEF1 = 0;
constexpr int WT_BDEF2 = 1;
constexpr int WT_BDEF4 = 2;
constexpr int WT_SDEF = 3;
constexpr int WT_QDEF = 4;

constexpr std::uint16_t BF_TAIL_INDEX = 0x0001;
constexpr std::uint16_t BF_ROTATABLE = 0x0002;
constexpr std::uint16_t BF_TRANSLATABLE = 0x0004;
constexpr std::uint16_t BF_VISIBLE = 0x0008;
constexpr std::uint16_t BF_ENABLED = 0x0010;
constexpr std::uint16_t BF_IK = 0x0020;
constexpr std::uint16_t BF_LOCAL_APPEND = 0x0080;
constexpr std::uint16_t BF_INHERIT_ROT = 0x0100;
constexpr std::uint16_t BF_INHERIT_MOV = 0x0200;
constexpr std::uint16_t BF_FIXED_AXIS = 0x0400;
constexpr std::uint16_t BF_LOCAL_AXIS = 0x0800;
constexpr std::uint16_t BF_AFTER_PHYSICS = 0x1000;
constexpr std::uint16_t BF_EXTERNAL_PARENT = 0x2000;

constexpr std::uint8_t MF_DOUBLE_SIDED = 0x01;
constexpr std::uint8_t MF_GROUND_SHADOW = 0x02;
constexpr std::uint8_t MF_SHADOW_MAP = 0x04;
constexpr std::uint8_t MF_SELF_SHADOW = 0x08;
constexpr std::uint8_t MF_EDGE = 0x10;
constexpr std::uint8_t MF_VERTEX_COLOR = 0x20;
constexpr std::uint8_t MF_POINT = 0x40;
constexpr std::uint8_t MF_LINE = 0x80;

struct IKLink {
    int bone = -1;
    bool limited = false;
    Vec3 lo{};
    Vec3 hi{};
};

struct IK {
    int target = -1;
    int loop = 40;
    float angle = 0.5f;
    std::vector<IKLink> links;
};

struct Bone {
    std::string name;
    std::string name_en;
    Vec3 pos{};
    int parent = -1;
    int layer = 0;
    std::uint16_t flags = BF_ROTATABLE | BF_TRANSLATABLE | BF_VISIBLE | BF_ENABLED;
    int tail_bone = -1;
    Vec3 tail_offset{};
    int append_parent = -1;
    float append_ratio = 0.0f;
    Vec3 axis{0.0f, 0.0f, 1.0f};
    Vec3 local_x{1.0f, 0.0f, 0.0f};
    Vec3 local_z{0.0f, 0.0f, 1.0f};
    int ext_key = 0;
    std::optional<IK> ik;
};

struct Material {
    std::string name;
    std::string name_en;
    Vec4 diffuse{1.0f, 1.0f, 1.0f, 1.0f};
    Vec3 specular{};
    float specular_coef = 0.0f;
    Vec3 ambient{0.5f, 0.5f, 0.5f};
    std::uint8_t draw_flags = MF_DOUBLE_SIDED | MF_GROUND_SHADOW | MF_EDGE;
    Vec4 edge_color{0.0f, 0.0f, 0.0f, 1.0f};
    float edge_size = 1.0f;
    int texture = -1;
    int sphere = -1;
    std::uint8_t sphere_mode = 0;
    std::uint8_t toon_shared = 0;
    int toon = 0;
    std::string memo;
    int face_count = 0;
};

struct MorphOffset {
    // 组 / 翻转
    int morph = -1;
    float ratio = 0.0f;
    // 顶点 / UV
    int vertex = 0;
    Vec4 offset{};
    // 骨骼
    int bone = -1;
    Vec3 move{};
    Vec4 rot{0.0f, 0.0f, 0.0f, 1.0f};
    // 材质
    int material = -1;
    std::uint8_t calc = 0;
    Vec4 diffuse{1.0f, 1.0f, 1.0f, 1.0f};
    Vec3 specular{};
    float specular_coef = 0.0f;
    Vec3 ambient{};
    Vec4 edge_color{0.0f, 0.0f, 0.0f, 1.0f};
    float edge_size = 0.0f;
    Vec4 texture{1.0f, 1.0f, 1.0f, 1.0f};
    Vec4 sphere{1.0f, 1.0f, 1.0f, 1.0f};
    Vec4 toon{1.0f, 1.0f, 1.0f, 1.0f};
    // 冲量
    int rigid = -1;
    std::uint8_t local = 0;
    Vec3 velocity{};
    Vec3 torque{};
};

struct Morph {
    std::string name;
    std::string name_en;
    int panel = 4;
    int type = 1;
    std::vector<MorphOffset> offsets;
};

struct DisplayFrameItem {
    std::uint8_t type = 0;  // 0 骨骼 / 1 形态
    int index = -1;
};

struct DisplayFrame {
    std::string name;
    std::string name_en;
    std::uint8_t special = 0;
    std::vector<DisplayFrameItem> items;
};

struct RigidBody {
    std::string name;
    std::string name_en;
    int bone = -1;
    // 所属碰撞组。PMX 文件里是 1..16（1 基），读写时统一换算成 0..15，
    // 与掩码位一一对应（bit g 即第 g 组）。
    std::uint8_t group = 0;
    // 碰撞掩码（bit=1 表示与改组碰撞）。PMX 文件里存的是「非衝突グループ」
    // （bit=1 表示不与该组碰撞），读写时已反转，因此这里与 Bullet 的
    // filterMask 语义一致。
    std::uint16_t mask = 0xFFFF;
    std::uint8_t shape = 0;
    Vec3 size{1.0f, 1.0f, 1.0f};
    Vec3 pos{};
    Vec3 rot{};
    float mass = 1.0f;
    float mov_damp = 0.5f;
    float rot_damp = 0.5f;
    float repel = 0.0f;
    float friction = 0.5f;
    std::uint8_t mode = 0;
};

struct Joint {
    std::string name;
    std::string name_en;
    std::uint8_t type = 0;
    int rigid_a = -1;
    int rigid_b = -1;
    Vec3 pos{};
    Vec3 rot{};
    Vec3 min_loc{};
    Vec3 max_loc{};
    Vec3 min_rot{};
    Vec3 max_rot{};
    Vec3 spring_loc{};
    Vec3 spring_rot{};
};

struct SoftBodyAnchor {
    int rigid = -1;
    int vertex = 0;
    std::uint8_t near = 0;
};

struct SoftBody {
    std::string name;
    std::string name_en;
    std::uint8_t shape = 0;
    int material = -1;
    // 同 RigidBody：组号已换算成 0..15。
    std::uint8_t group = 0;
    // 同 RigidBody：bit=1 表示与改组碰撞（读写时已由 PMX 非衝突グループ反转）。
    std::uint16_t mask = 0xFFFF;
    std::uint8_t flags = 0;
    int b_link_dist = 0;
    int cluster_count = 0;
    float total_mass = 0.0f;
    float collision_margin = 0.0f;
    int aero_model = 0;
    std::array<float, 12> config{};
    std::array<float, 6> cluster{};
    std::array<int, 4> iteration{};
    std::array<float, 3> material_params{};
    std::vector<SoftBodyAnchor> anchors;
    std::vector<int> pins;
};

// 顶点按 SoA 存放，便于批量上传 GPU 与 SIMD。
struct VertexData {
    std::vector<Vec3> pos;
    std::vector<Vec3> nrm;
    std::vector<Vec2> uv;
    std::vector<float> add_uv;  // add_uv_count * 4 个 float / 顶点
    std::vector<float> edge;
    std::vector<std::uint8_t> wtype;
    std::vector<std::array<int, 4>> bones;
    std::vector<std::array<float, 4>> weights;
    std::vector<std::array<float, 9>> sdef;  // C, R0, R1

    std::size_t size() const { return pos.size(); }
};

struct Model {
    std::string path;
    float version = 2.0f;
    int encoding = 0;  // 0 UTF-16LE, 1 UTF-8
    int add_uv_count = 0;
    int vsz = 2, tsz = 1, msz = 1, bsz = 2, mosz = 1, rsz = 1;
    std::string name, name_en, comment, comment_en;

    VertexData vertices;
    std::vector<std::uint32_t> indices;
    std::vector<std::string> textures;
    std::vector<Material> materials;
    std::vector<Bone> bones;
    std::vector<Morph> morphs;
    std::vector<DisplayFrame> frames;
    std::vector<RigidBody> rigid;
    std::vector<Joint> joints;
    std::vector<SoftBody> soft_bodies;

    std::size_t n_vertices() const { return vertices.size(); }
    std::size_t n_faces() const { return indices.size() / 3; }
    std::size_t n_bones() const { return bones.size(); }

    int bone_index(const std::string& bone_name) const;
    std::string base_dir() const;
    std::string resolve_texture(int index) const;
};

// ---------------------------------------------------------------- 读写
// 失败时抛出 std::runtime_error（消息为中文，与 Python 版一致）。
Model load_pmx(const std::string& path);
void save_pmx(Model& model, const std::string& path);

// 按材质切分面区间；face_count 之后剩余索引作为附加区间。
struct MaterialRange {
    int material = -1;
    std::size_t start = 0;
    std::size_t count = 0;
};
std::vector<MaterialRange> material_ranges(const Model& model);

// 把骨骼位移按蒙皮权重写进顶点（「移动骨骼同时带动顶点」）。
int shift_bone_vertices(Model& model, int bone, Vec3 delta);

// 顶点权重类型降级表：SDEF 在演算时按 BDEF2 处理（仅运行时，不改原始数据）。
inline std::uint8_t runtime_weight_type(std::uint8_t t) { return t == WT_SDEF ? WT_BDEF2 : t; }

}  // namespace pmx
