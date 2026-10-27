#include "core/pmx.hpp"

#include <filesystem>

#include "core/fs.hpp"

namespace pmx {

int Model::bone_index(const std::string& bone_name) const {
    for (std::size_t i = 0; i < bones.size(); ++i)
        if (bones[i].name == bone_name) return static_cast<int>(i);
    return -1;
}

std::string Model::base_dir() const {
    if (path.empty()) return std::string();
    return utf8_string(utf8_path(path).parent_path());
}

std::string Model::resolve_texture(int index) const {
    if (index < 0 || index >= static_cast<int>(textures.size())) return std::string();
    namespace fs = std::filesystem;
    // PMX 内部用反斜杠分隔，跨平台统一替换（在 UTF-8 字符串上做，避免窄字符编码误差）。
    std::string s = textures[static_cast<std::size_t>(index)];
    for (char& c : s)
        if (c == '\\') c = '/';
    const fs::path rel = utf8_path(s);
    if (rel.is_absolute()) return utf8_string(rel);
    const std::string dir = base_dir();
    if (dir.empty()) return utf8_string(rel.lexically_normal());
    return utf8_string((utf8_path(dir) / rel).lexically_normal());
}

std::vector<MaterialRange> material_ranges(const Model& model) {
    std::vector<MaterialRange> out;
    std::size_t start = 0;
    for (std::size_t i = 0; i < model.materials.size(); ++i) {
        int cnt = model.materials[i].face_count;
        if (cnt > 0) {
            out.push_back({static_cast<int>(i), start, static_cast<std::size_t>(cnt)});
        }
        if (cnt > 0) start += static_cast<std::size_t>(cnt);
    }
    if (start < model.indices.size()) {
        out.push_back({-1, start, model.indices.size() - start});
    }
    return out;
}

int shift_bone_vertices(Model& model, int bone, Vec3 delta) {
    if (bone < 0 || bone >= static_cast<int>(model.bones.size())) return 0;
    VertexData& v = model.vertices;
    int hit = 0;
    for (std::size_t i = 0; i < v.size(); ++i) {
        float w = 0.0f;
        for (int c = 0; c < 4; ++c)
            if (v.bones[i][c] == bone) w += v.weights[i][c];
        if (w > 0.0f) {
            v.pos[i] += delta * w;
            ++hit;
        }
    }
    return hit;
}

}  // namespace pmx
