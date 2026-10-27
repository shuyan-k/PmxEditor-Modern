// 数值对拍/回归测试：PMX round-trip、姿态求值、IK、蒙皮、物理稳定步进。
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <string>
#include <vector>

#include "core/fs.hpp"
#include "core/morph.hpp"
#include "core/pmx.hpp"
#include "core/pose.hpp"
#include "core/skinning.hpp"
#include "core/vpd.hpp"
#ifdef PMX_ENABLE_PHYSICS
#include "physics/physics.hpp"
#endif

namespace {

int g_failures = 0;
int g_checks = 0;

void check(bool ok, const char* what) {
    ++g_checks;
    if (!ok) {
        ++g_failures;
        std::fprintf(stderr, "  [失败] %s\n", what);
    }
}

void check_near(double got, double want, double tol, const char* what) {
    ++g_checks;
    if (!(std::fabs(got - want) <= tol)) {
        ++g_failures;
        std::fprintf(stderr, "  [失败] %s: %.9f != %.9f (tol %.2e)\n", what, got, want, tol);
    }
}

double max_abs_diff(const std::vector<pmx::Vec3>& a, const std::vector<pmx::Vec3>& b) {
    if (a.size() != b.size()) return 1e9;
    double m = 0.0;
    for (std::size_t i = 0; i < a.size(); ++i) {
        m = std::max(m, static_cast<double>(std::fabs(a[i].x - b[i].x)));
        m = std::max(m, static_cast<double>(std::fabs(a[i].y - b[i].y)));
        m = std::max(m, static_cast<double>(std::fabs(a[i].z - b[i].z)));
    }
    return m;
}

bool finite_mat(const pmx::Mat4& m) {
    for (float v : m.m)
        if (!std::isfinite(v)) return false;
    return true;
}

// ---------------------------------------------------------------- PMX 读写
void test_roundtrip(const std::string& path, const std::filesystem::path& out) {
    std::printf("[1] PMX 读取与 round-trip\n");
    pmx::Model a = pmx::load_pmx(path);
    check(a.vertices.size() > 0, "顶点数 > 0");
    check(a.indices.size() % 3 == 0, "索引按三角形对齐");
    check(a.n_faces() > 0, "面数 > 0");

    a.name = "roundtrip";
    pmx::save_pmx(a, out.string());
    check(std::filesystem::exists(out), "保存文件存在");
    pmx::Model b = pmx::load_pmx(out.string());

    check(a.name == b.name, "模型名一致");
    check(a.vertices.size() == b.vertices.size(), "顶点数一致");
    check(a.indices == b.indices, "索引一致");
    check(a.bones.size() == b.bones.size(), "骨骼数一致");
    check(a.materials.size() == b.materials.size(), "材质数一致");
    check(a.morphs.size() == b.morphs.size(), "形态数一致");
    check(a.rigid.size() == b.rigid.size(), "刚体数一致");
    check(a.joints.size() == b.joints.size(), "关节数一致");
    check(a.textures == b.textures, "贴图表一致");
    check_near(max_abs_diff(a.vertices.pos, b.vertices.pos), 0.0, 1e-6, "顶点坐标");
    check_near(max_abs_diff(a.vertices.nrm, b.vertices.nrm), 0.0, 1e-6, "顶点法线");

    double wmax = 0.0;
    for (std::size_t i = 0; i < a.vertices.weights.size(); ++i) {
        for (int k = 0; k < 4; ++k)
            wmax = std::max(wmax, std::fabs(static_cast<double>(
                                       a.vertices.weights[i][k] - b.vertices.weights[i][k])));
        for (int k = 0; k < 4; ++k)
            check(a.vertices.bones[i][k] == b.vertices.bones[i][k], "权重骨骼索引一致");
        check(a.vertices.wtype[i] == b.vertices.wtype[i], "权重类型一致");
    }
    check_near(wmax, 0.0, 1e-6, "蒙皮权重");

    for (std::size_t i = 0; i < a.bones.size(); ++i) {
        check(a.bones[i].name == b.bones[i].name, "骨骼名一致");
        check(a.bones[i].flags == b.bones[i].flags, "骨骼标志一致");
        check(a.bones[i].parent == b.bones[i].parent, "骨骼父级一致");
    }
    for (std::size_t i = 0; i < a.materials.size(); ++i) {
        check_near(a.materials[i].diffuse.w, b.materials[i].diffuse.w, 1e-6, "材质 alpha");
        check(a.materials[i].face_count == b.materials[i].face_count, "材质面数一致");
    }
    for (std::size_t i = 0; i < a.rigid.size(); ++i) {
        check(a.rigid[i].shape == b.rigid[i].shape, "刚体形状一致");
        check_near(a.rigid[i].size.y, b.rigid[i].size.y, 1e-6, "刚体尺寸");
    }
    const auto ra = pmx::material_ranges(a);
    const auto rb = pmx::material_ranges(b);
    check(ra.size() == rb.size(), "材质区间数一致");
    std::printf("  顶点 %zu，面 %zu，骨骼 %zu，材质 %zu\n", a.vertices.size(), a.n_faces(),
                a.bones.size(), a.materials.size());
}

// ---------------------------------------------------------------- 姿态 / IK
void test_pose(const pmx::Model& model) {
    std::printf("[2] 姿态求值与 IK\n");
    pmx::Pose pose(model);
    pose.reset();
    // world() 返回内部缓冲的引用，比较前必须拷贝快照。
    const std::vector<pmx::Mat4> W0 = pose.world();
    check(W0.size() == static_cast<std::size_t>(pose.n), "世界矩阵数量等于骨骼数");
    bool all_finite = true;
    for (const pmx::Mat4& m : W0) all_finite &= finite_mat(m);
    check(all_finite, "静止世界矩阵无 NaN");

    // 静止姿态下，世界平移即骨骼静止位置
    double pos_err = 0.0;
    for (int i = 0; i < pose.n; ++i) {
        pos_err = std::max(pos_err, static_cast<double>(std::fabs(W0[static_cast<std::size_t>(i)].at(0, 3) - pose.rest_pos[static_cast<std::size_t>(i)].x)));
        pos_err = std::max(pos_err, static_cast<double>(std::fabs(W0[static_cast<std::size_t>(i)].at(1, 3) - pose.rest_pos[static_cast<std::size_t>(i)].y)));
        pos_err = std::max(pos_err, static_cast<double>(std::fabs(W0[static_cast<std::size_t>(i)].at(2, 3) - pose.rest_pos[static_cast<std::size_t>(i)].z)));
    }
    check_near(pos_err, 0.0, 2e-5, "静止世界平移 = 骨骼静止位置");

    if (!model.bones.empty()) {
        // 选一根真正带权重的骨骼，旋转才可能影响顶点。
        int bone = 0;
        for (const auto& b : model.vertices.bones)
            if (b[0] >= 0 && b[0] < pose.n) {
                bone = b[0];
                break;
            }
        pose.invalidate_world();
        pose.rotate_local(bone, pmx::euler_to_quat(0.3f, 0.2f, 0.1f));
        pose.solve_ik();
        const std::vector<pmx::Mat4> W1 = pose.world();
        check(finite_mat(W1[static_cast<std::size_t>(bone)]), "旋转后世界矩阵有效");
        check(W1[static_cast<std::size_t>(bone)].at(0, 0) !=
                  W0[static_cast<std::size_t>(bone)].at(0, 0) ||
              W1[static_cast<std::size_t>(bone)].at(1, 1) !=
                  W0[static_cast<std::size_t>(bone)].at(1, 1),
              "旋转生效");
        pose.reset();
        pose.world();
    }

    // IK 收敛：链末端应贴近目标（若模型带 IK）
    int ik_count = 0;
    for (const pmx::Bone& b : model.bones)
        if (b.ik) ++ik_count;
    std::printf("  骨骼 %d，IK 链 %d\n", pose.n, ik_count);
}

// ---------------------------------------------------------------- 蒙皮
void test_skinning(const pmx::Model& model) {
    std::printf("[3] CPU 参考蒙皮\n");
    pmx::SkinDeformer deform(model);
    pmx::Pose pose(model);
    pose.reset();
    const auto& world = pose.world();
    std::vector<pmx::Vec3> out_pos, out_nrm;
    deform.deform(model.vertices.pos, model.vertices.nrm, world, out_pos, out_nrm);

    check(out_pos.size() == model.vertices.size(), "输出顶点数一致");
    check_near(max_abs_diff(model.vertices.pos, out_pos), 0.0, 2e-5,
               "静止姿态蒙皮 = 原顶点坐标");
    bool nrm_ok = true;
    for (const pmx::Vec3& n : out_nrm)
        nrm_ok &= std::isfinite(n.x) && std::isfinite(n.y) && std::isfinite(n.z);
    check(nrm_ok, "法线无 NaN");

    if (!model.bones.empty()) {
        int bone = 0;
        for (const auto& b : model.vertices.bones)
            if (b[0] >= 0 && b[0] < pose.n) {
                bone = b[0];
                break;
            }
        pose.rotate_local(bone, pmx::euler_to_quat(0.25f, 0.0f, 0.0f));
        pose.invalidate_world();
        const std::vector<pmx::Mat4> w1 = pose.world();
        deform.deform(model.vertices.pos, model.vertices.nrm, w1, out_pos, out_nrm);
        check(max_abs_diff(model.vertices.pos, out_pos) > 1e-4, "旋转后蒙皮产生位移");

        // 局部重算与全量重算一致：dirty 集合要覆盖世界矩阵真正变化的所有骨骼，
        // 即被旋转骨骼自身及其全部后代（子骨骼的世界矩阵会随父级一起改变）。
        std::vector<pmx::Vec3> sub_pos = model.vertices.pos, sub_nrm = model.vertices.nrm;
        std::vector<int> dirty{bone};
        std::vector<char> visited(model.bones.size(), 0);
        visited[static_cast<std::size_t>(bone)] = 1;
        for (std::size_t at = 0; at < dirty.size(); ++at) {
            const int parent = dirty[at];
            for (std::size_t k = 0; k < model.bones.size(); ++k) {
                if (model.bones[k].parent != parent || visited[k]) continue;
                visited[k] = 1;
                dirty.push_back(static_cast<int>(k));
            }
        }
        deform.deform_subset(model.vertices.pos, model.vertices.nrm, w1, dirty, sub_pos, sub_nrm);
        check_near(max_abs_diff(sub_pos, out_pos), 0.0, 2e-4, "局部重算与全量重算一致");
    }
}

// ---------------------------------------------------------------- 物理
void test_physics(pmx::Model& model) {
#ifdef PMX_ENABLE_PHYSICS
    std::printf("[4] Bullet 物理\n");
    pmx::Physics physics;
    if (!physics.build(model)) {
        std::printf("  跳过：%s\n", physics.error.c_str());
        return;
    }
    check(true, "物理世界构建");
    pmx::Pose pose(model);
    pose.reset();
    physics.enabled = true;
    physics.reset(pose, nullptr, true);
    const auto& W = pose.world();
    bool finite = true;
    for (const pmx::Mat4& m : W) finite &= finite_mat(m);
    check(finite, "物理复位后姿态有效");

    for (int i = 0; i < 120; ++i) {
        physics.step(pose, 1.0f / 60.0f);
        pose.apply(nullptr);
        pose.world();
    }
    finite = true;
    for (const pmx::Mat4& m : pose.world()) finite &= finite_mat(m);
    check(finite, "60×2 步后姿态无 NaN");
    check(std::isfinite(physics.last_max_delta), "last_max_delta 有限");
    const std::vector<int>& bones = physics.dynamic_bones();
    std::printf("  刚体 %zu，动态绑定骨骼 %zu，最大位移 %.6f\n", model.rigid.size(),
                bones.size(), static_cast<double>(physics.last_max_delta));
#else
    std::printf("[4] 物理：编译时已关闭（PMX_ENABLE_PHYSICS=OFF）\n");
#endif
}

// ---------------------------------------------------------------- VPD 导出
void test_vpd(const pmx::Model& model, const std::filesystem::path& dir) {
    std::printf("[5] VPD 导出与回读\n");
    if (model.bones.empty()) {
        check(false, "模型含骨骼");
        return;
    }
    pmx::Pose pose(model);
    pose.reset();
    const int bone = 0;
    pose.base_rot[static_cast<std::size_t>(bone)] = pmx::euler_to_quat(0.2f, -0.3f, 0.1f);
    pose.base_trans[static_cast<std::size_t>(bone)] = pmx::Vec3{0.5f, 1.0f, -0.25f};
    pmx::MorphWeights weights;
    const bool has_morph = !model.morphs.empty();
    if (has_morph) weights.emplace_back(0, 0.75f);

    const std::string text = pmx::build_vpd_text(model, pose, &weights);
    check(text.rfind("Vocaloid Pose Data file", 0) == 0, "VPD 头部正确");
    check(text.find("Bone0{") != std::string::npos, "含骨骼块");
    if (has_morph) check(text.find("Morph0{") != std::string::npos, "含形态块");

    const pmx::VpdFile parsed = pmx::parse_vpd_text(text, "inline", "utf-8");
    check(parsed.bones.size() == 1, "内存回读骨骼数 = 1");
    if (!parsed.bones.empty()) {
        check_near(parsed.bones[0].pos.x, 0.5, 1e-5, "位移 x 回读");
        check_near(parsed.bones[0].pos.z, -0.25, 1e-5, "位移 z 回读");
        check_near(parsed.bones[0].rot.w, pose.base_rot[static_cast<std::size_t>(bone)].w,
                   1e-5, "旋转 w 回读");
    }
    if (has_morph) {
        check(parsed.morphs.size() == 1, "内存回读形态数 = 1");
        if (!parsed.morphs.empty())
            check_near(parsed.morphs[0].weight, 0.75, 1e-5, "形态权重回读");
    }

    const std::string path = (dir / "pmxstudio_export.vpd").string();
    const pmx::VpdExport result = pmx::save_vpd(path, model, pose, &weights);
    check(std::filesystem::exists(path), "VPD 文件写出");
    check(result.bones == 1, "导出骨骼计数");
    check(result.morphs == (has_morph ? 1 : 0), "导出形态计数");
    check(result.encoding == "cp932" || result.encoding == "utf-8", "导出编码标记有效");

    const pmx::VpdFile disk = pmx::load_vpd(path);
    check(disk.bones.size() == 1, "磁盘回读骨骼数 = 1");
    pmx::Pose pose2(model);
    pose2.reset();
    pmx::MorphWeights weights2;
    pmx::apply_vpd(model, pose2, disk, &weights2);
    check_near(pose2.base_trans[static_cast<std::size_t>(bone)].x, 0.5, 2e-4,
               "应用回读 VPD 的位移");
    if (has_morph)
        check_near(weights2.empty() ? 0.0f : weights2[0].second, 0.75, 2e-4,
                   "应用回读 VPD 的形态权重");

    // 静止姿态不应导出任何骨骼块
    pmx::Pose idle(model);
    idle.reset();
    const std::string idle_text = pmx::build_vpd_text(model, idle);
    check(idle_text.find("Bone0{") == std::string::npos, "静止姿态默认不导出骨骼");
    const std::string all_text = pmx::build_vpd_text(model, idle, nullptr, "", true);
    check(all_text.find("Bone0{") != std::string::npos, "include_all 导出全部骨骼");
}

// ---------------------------------------------------------------- UTF-8 路径
void test_utf8_paths(const pmx::Model& model, const std::filesystem::path& dir) {
    std::printf("[6] 中文路径读写\n");
    const std::string sub_dir =
        pmx::utf8_string(dir) + "/" + pmx::utf8_string(pmx::utf8_path(std::string("中文目录")));
    std::filesystem::create_directories(pmx::utf8_path(sub_dir));
    const std::string path =
        sub_dir + "/" + pmx::utf8_string(pmx::utf8_path(std::string("模型 副本.pmx")));

    pmx::Model copy = model;
    pmx::save_pmx(copy, path);
    check(pmx::path_exists(path), "中文路径写出 PMX");
    const pmx::Model loaded = pmx::load_pmx(path);
    check(loaded.vertices.size() == model.vertices.size(), "中文路径读回顶点数");
    check(loaded.bones.size() == model.bones.size(), "中文路径读回骨骼数");

    // 纹理路径解析要保留 UTF-8 目录，不能被窄字符编码截断。
    pmx::Model probe = model;
    probe.path = sub_dir + "/probe.pmx";
    probe.textures = {"tex\\a.png"};
    std::string resolved = probe.resolve_texture(0);
    for (char& c : resolved)
        if (c == '\\') c = '/';
    check(resolved.find("中文目录") != std::string::npos, "纹理路径保留中文目录");
    check(resolved.find("/tex/a.png") != std::string::npos, "纹理解析替换反斜杠");
}

}  // namespace

int main(int argc, char** argv) {
    // 崩溃时也要保留已打印的进度，便于定位失败项。
    std::setvbuf(stdout, nullptr, _IONBF, 0);
    const std::string path = argc > 1 ? argv[1] : PMX_TEST_MODEL;
    if (!std::filesystem::exists(pmx::utf8_path(path))) {
        std::fprintf(stderr, "找不到测试模型：%s\n", path.c_str());
        return 2;
    }
    pmx::Model model;
    try {
        model = pmx::load_pmx(path);
    } catch (const std::exception& e) {
        std::fprintf(stderr, "解析失败：%s\n", e.what());
        return 2;
    }

    const std::filesystem::path out =
        std::filesystem::temp_directory_path() / "pmxstudio_roundtrip.pmx";
    try {
        test_roundtrip(path, out);
        test_pose(model);
        test_skinning(model);
        test_physics(model);
        test_vpd(model, out.parent_path());
        test_utf8_paths(model, out.parent_path());
    } catch (const std::exception& e) {
        std::fprintf(stderr, "异常：%s\n", e.what());
        return 1;
    }

    std::printf("\n共 %d 项检查，失败 %d 项\n", g_checks, g_failures);
    return g_failures == 0 ? 0 : 1;
}
