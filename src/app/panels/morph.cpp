#include "app/panels.hpp"

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

#include <imgui.h>

#include "app/document_ops.hpp"
#include "app/panels/common.hpp"

namespace {

constexpr int kOffsetDisplayCap = 4000;

// 形态类型名（与 PMX 类型编号一致）。
const char* morph_type_name(int type) {
    switch (type) {
        case 0: return "组";
        case 1: return "顶点";
        case 2: return "骨骼";
        case 3: return "UV";
        case 4: return "附加 UV1";
        case 5: return "附加 UV2";
        case 6: return "附加 UV3";
        case 7: return "附加 UV4";
        case 8: return "材质";
        case 9: return "翻转";
        case 10: return "冲量";
        default: return "未知";
    }
}

const char* morph_panel_name(int panel) {
    switch (panel) {
        case 0: return "系统";
        case 1: return "眉";
        case 2: return "眼";
        case 3: return "口";
        case 4: return "其他";
        default: return "其他";
    }
}

std::string ref_name(const std::string& name, const char* empty_text) {
    return name.empty() ? std::string(empty_text) : name;
}

std::string morph_ref_name(const pmx::Model& model, int index) {
    if (index < 0 || index >= static_cast<int>(model.morphs.size())) return "?";
    return ref_name(model.morphs[static_cast<std::size_t>(index)].name, "未命名形态");
}

std::string bone_ref_name(const pmx::Model& model, int index) {
    if (index < 0 || index >= static_cast<int>(model.bones.size())) return "?";
    return ref_name(model.bones[static_cast<std::size_t>(index)].name, "未命名骨骼");
}

std::string material_ref_name(const pmx::Model& model, int index) {
    if (index < 0 || index >= static_cast<int>(model.materials.size())) return "全部材质";
    return ref_name(model.materials[static_cast<std::size_t>(index)].name, "未命名材质");
}

std::string rigid_ref_name(const pmx::Model& model, int index) {
    if (index < 0 || index >= static_cast<int>(model.rigid.size())) return "?";
    return ref_name(model.rigid[static_cast<std::size_t>(index)].name, "未命名刚体");
}

std::string indexed_name(int index, const std::string& name) {
    char prefix[24];
    std::snprintf(prefix, sizeof prefix, "%03d · ", index);
    std::string text(prefix);
    text += name.empty() ? "未命名" : name;
    return text;
}

std::string morph_list_text(const pmx::Morph& morph, int index) {
    char prefix[24];
    std::snprintf(prefix, sizeof prefix, "%03d · ", index);
    std::string text(prefix);
    const std::string label = pmxui::base_name(morph.name, morph.name_en);
    text += label.empty() ? "未命名形态" : label;
    text += " · ";
    text += morph_panel_name(morph.panel);
    text += " · ";
    text += morph_type_name(morph.type);
    text += " · ";
    text += std::to_string(morph.offsets.size());
    text += " 项";
    return text;
}

// 偏移列表里的双列描述：目标 + 数值（对齐 Python 版 _offset_desc）。
void offset_desc(const pmx::Model& model, int type, const pmx::MorphOffset& off,
                 std::string& target, std::string& value) {
    char buf[320];
    switch (type) {
        case 0:
        case 9:
            target = std::string(type == 9 ? "翻转 · " : "形态 · ") + morph_ref_name(model, off.morph);
            std::snprintf(buf, sizeof buf, "× %.3f", off.ratio);
            value = buf;
            break;
        case 1:
            std::snprintf(buf, sizeof buf, "顶点 %d", off.vertex);
            target = buf;
            std::snprintf(buf, sizeof buf, "(%.3f, %.3f, %.3f)", off.offset.x, off.offset.y,
                          off.offset.z);
            value = buf;
            break;
        case 2:
            target = "骨骼 · " + bone_ref_name(model, off.bone);
            std::snprintf(buf, sizeof buf,
                          "移动 (%.3f, %.3f, %.3f) / 旋转 (%.3f, %.3f, %.3f, %.3f)",
                          off.move.x, off.move.y, off.move.z, off.rot.x, off.rot.y, off.rot.z,
                          off.rot.w);
            value = buf;
            break;
        case 3:
        case 4:
        case 5:
        case 6:
        case 7:
            std::snprintf(buf, sizeof buf, "UV %d", off.vertex);
            target = buf;
            std::snprintf(buf, sizeof buf, "(%.3f, %.3f, %.3f, %.3f)", off.offset.x, off.offset.y,
                          off.offset.z, off.offset.w);
            value = buf;
            break;
        case 8:
            target = "材质 · " + material_ref_name(model, off.material);
            std::snprintf(buf, sizeof buf, "%s · 漫反射 (%.3f, %.3f, %.3f)",
                          off.calc == 1 ? "加法" : "乘法", off.diffuse.x, off.diffuse.y,
                          off.diffuse.z);
            value = buf;
            break;
        case 10:
            target = "冲量 · " + rigid_ref_name(model, off.rigid);
            std::snprintf(buf, sizeof buf,
                          "速度 (%.3f, %.3f, %.3f) / 扭矩 (%.3f, %.3f, %.3f)", off.velocity.x,
                          off.velocity.y, off.velocity.z, off.torque.x, off.torque.y,
                          off.torque.z);
            value = buf;
            break;
        default:
            target = "?";
            value.clear();
            break;
    }
}

// 按类型构造零值偏移，字段严格对齐 Python 版 _add_offset。
pmx::MorphOffset make_default_offset(int type) {
    pmx::MorphOffset off;
    switch (type) {
        case 0:
        case 9:
            off.morph = 0;
            off.ratio = 0.0f;
            break;
        case 1:
            off.vertex = 0;
            off.offset = pmx::Vec4{};
            break;
        case 2:
            off.bone = 0;
            off.move = pmx::Vec3{};
            off.rot = pmx::Vec4{0.0f, 0.0f, 0.0f, 1.0f};
            break;
        case 3:
        case 4:
        case 5:
        case 6:
        case 7:
            off.vertex = 0;
            off.offset = pmx::Vec4{};
            break;
        case 8:
            off.material = -1;
            off.calc = 0;
            off.diffuse = pmx::Vec4{};
            off.specular = pmx::Vec3{};
            off.specular_coef = 0.0f;
            off.ambient = pmx::Vec3{};
            off.edge_color = pmx::Vec4{};
            off.edge_size = 0.0f;
            // C++ 结构体默认 texture/sphere/toon 是 1，这里必须显式归零。
            off.texture = pmx::Vec4{};
            off.sphere = pmx::Vec4{};
            off.toon = pmx::Vec4{};
            break;
        case 10:
            off.rigid = 0;
            off.local = 0;
            off.velocity = pmx::Vec3{};
            off.torque = pmx::Vec3{};
            break;
        default:
            break;
    }
    return off;
}

// 预览只影响当前视图：morph_values 记录数值，morph_weights 只保留当前一条。
void apply_morph_preview(Viewer& v, int index, float percent) {
    if (index < 0 || index >= static_cast<int>(v.model.morphs.size())) return;
    if (v.morph_values.size() != v.model.morphs.size())
        v.morph_values.assign(v.model.morphs.size(), 0.0f);
    const float weight = percent / 100.0f;
    v.morph_values[static_cast<std::size_t>(index)] = weight;
    v.morph_weights.clear();
    if (weight != 0.0f) v.morph_weights.emplace_back(index, weight);
    v.morph_dirty = true;
}

// 切换形态时清空预览（不写文件、不压撤销）。
void clear_morph_preview(Viewer& v) {
    v.morph_values.assign(v.model.morphs.size(), 0.0f);
    v.morph_weights.clear();
    v.morph_dirty = true;
}

struct IndexOption {
    int value;
    std::string label;
};

// 索引型下拉：field 指向 MorphOffset 里的 int 字段。
bool offset_index_combo(Viewer& v, int morph, int row, int pmx::MorphOffset::*field,
                        const char* id, const char* label, const char* key,
                        const std::vector<IndexOption>& options) {
    if (morph < 0 || morph >= static_cast<int>(v.model.morphs.size())) return false;
    const pmx::Morph& morph_ref = v.model.morphs[static_cast<std::size_t>(morph)];
    if (row < 0 || row >= static_cast<int>(morph_ref.offsets.size())) return false;
    const int current = morph_ref.offsets[static_cast<std::size_t>(row)].*field;

    std::string preview = "（无）";
    for (const IndexOption& option : options) {
        if (option.value == current) {
            preview = option.label;
            break;
        }
    }

    int picked = current;
    bool changed = false;
    ImGui::SetNextItemWidth(pmxui::scale(-110.0f));
    if (ImGui::BeginCombo(id, preview.c_str())) {
        for (const IndexOption& option : options) {
            const bool selected = option.value == current;
            const std::string text = option.label + "##opt" + std::to_string(option.value);
            if (ImGui::Selectable(text.c_str(), selected)) {
                picked = option.value;
                changed = true;
            }
            if (selected) ImGui::SetItemDefaultFocus();
        }
        ImGui::EndCombo();
    }
    ImGui::SameLine();
    ImGui::TextUnformatted(label);

    if (!changed || picked == current) return false;
    v.edit("修改形态偏移", [morph, row, field, picked](pmx::Model& m) {
        if (morph < 0 || morph >= static_cast<int>(m.morphs.size())) return;
        pmx::Morph& mref = m.morphs[static_cast<std::size_t>(morph)];
        if (row < 0 || row >= static_cast<int>(mref.offsets.size())) return;
        mref.offsets[static_cast<std::size_t>(row)].*field = picked;
    }, "morph", std::string("morph.offset.") + key);
    return true;
}

// 固定选项下拉：field 指向 MorphOffset 里的 uint8 字段（calc/local）。
bool offset_choice_combo(Viewer& v, int morph, int row, std::uint8_t pmx::MorphOffset::*field,
                         const char* id, const char* label, const char* key,
                         const char* const* items, int count) {
    if (morph < 0 || morph >= static_cast<int>(v.model.morphs.size())) return false;
    const pmx::Morph& morph_ref = v.model.morphs[static_cast<std::size_t>(morph)];
    if (row < 0 || row >= static_cast<int>(morph_ref.offsets.size())) return false;
    const int current = static_cast<int>(morph_ref.offsets[static_cast<std::size_t>(row)].*field);

    const std::string preview = (current >= 0 && current < count) ? items[current] : "?";
    int picked = current;
    bool changed = false;
    ImGui::SetNextItemWidth(pmxui::scale(-110.0f));
    if (ImGui::BeginCombo(id, preview.c_str())) {
        for (int i = 0; i < count; ++i) {
            const bool selected = i == current;
            const std::string text = std::string(items[i]) + "##choice" + std::to_string(i);
            if (ImGui::Selectable(text.c_str(), selected)) {
                picked = i;
                changed = true;
            }
            if (selected) ImGui::SetItemDefaultFocus();
        }
        ImGui::EndCombo();
    }
    ImGui::SameLine();
    ImGui::TextUnformatted(label);

    if (!changed || picked == current) return false;
    v.edit("修改形态偏移", [morph, row, field, picked](pmx::Model& m) {
        if (morph < 0 || morph >= static_cast<int>(m.morphs.size())) return;
        pmx::Morph& mref = m.morphs[static_cast<std::size_t>(morph)];
        if (row < 0 || row >= static_cast<int>(mref.offsets.size())) return;
        mref.offsets[static_cast<std::size_t>(row)].*field =
            static_cast<std::uint8_t>(picked);
    }, "morph", std::string("morph.offset.") + key);
    return true;
}

bool offset_drag_float(Viewer& v, int morph, int row, float pmx::MorphOffset::*field,
                       const char* label, const char* key, float lo, float hi) {
    if (morph < 0 || morph >= static_cast<int>(v.model.morphs.size())) return false;
    const pmx::Morph& morph_ref = v.model.morphs[static_cast<std::size_t>(morph)];
    if (row < 0 || row >= static_cast<int>(morph_ref.offsets.size())) return false;
    const float current = morph_ref.offsets[static_cast<std::size_t>(row)].*field;

    float value = current;
    ImGui::SetNextItemWidth(pmxui::scale(-110.0f));
    if (!ImGui::DragFloat(label, &value, 0.01f, lo, hi, "%.3f")) return false;
    if (value == current) return false;
    v.edit("修改形态偏移", [morph, row, field, value](pmx::Model& m) {
        if (morph < 0 || morph >= static_cast<int>(m.morphs.size())) return;
        pmx::Morph& mref = m.morphs[static_cast<std::size_t>(morph)];
        if (row < 0 || row >= static_cast<int>(mref.offsets.size())) return;
        mref.offsets[static_cast<std::size_t>(row)].*field = value;
    }, "morph", std::string("morph.offset.") + key);
    return true;
}

bool offset_input_int(Viewer& v, int morph, int row, int pmx::MorphOffset::*field,
                      const char* label, const char* key, int lo, int hi) {
    if (morph < 0 || morph >= static_cast<int>(v.model.morphs.size())) return false;
    const pmx::Morph& morph_ref = v.model.morphs[static_cast<std::size_t>(morph)];
    if (row < 0 || row >= static_cast<int>(morph_ref.offsets.size())) return false;
    const int current = morph_ref.offsets[static_cast<std::size_t>(row)].*field;

    int value = current;
    ImGui::SetNextItemWidth(pmxui::scale(-110.0f));
    if (!ImGui::InputInt(label, &value)) return false;
    value = std::clamp(value, lo, hi);
    if (value == current) return false;
    v.edit("修改形态偏移", [morph, row, field, value](pmx::Model& m) {
        if (morph < 0 || morph >= static_cast<int>(m.morphs.size())) return;
        pmx::Morph& mref = m.morphs[static_cast<std::size_t>(morph)];
        if (row < 0 || row >= static_cast<int>(mref.offsets.size())) return;
        mref.offsets[static_cast<std::size_t>(row)].*field = value;
    }, "morph", std::string("morph.offset.") + key);
    return true;
}

bool offset_drag_vec3(Viewer& v, int morph, int row, pmx::Vec3 pmx::MorphOffset::*field,
                      const char* label, const char* key) {
    if (morph < 0 || morph >= static_cast<int>(v.model.morphs.size())) return false;
    const pmx::Morph& morph_ref = v.model.morphs[static_cast<std::size_t>(morph)];
    if (row < 0 || row >= static_cast<int>(morph_ref.offsets.size())) return false;
    const pmx::Vec3 current = morph_ref.offsets[static_cast<std::size_t>(row)].*field;

    float tmp[3] = {current.x, current.y, current.z};
    ImGui::SetNextItemWidth(pmxui::scale(-110.0f));
    if (!ImGui::DragFloat3(label, tmp, 0.01f, -99999.0f, 99999.0f, "%.3f")) return false;
    const pmx::Vec3 value{tmp[0], tmp[1], tmp[2]};
    if (value.x == current.x && value.y == current.y && value.z == current.z) return false;
    v.edit("修改形态偏移", [morph, row, field, value](pmx::Model& m) {
        if (morph < 0 || morph >= static_cast<int>(m.morphs.size())) return;
        pmx::Morph& mref = m.morphs[static_cast<std::size_t>(morph)];
        if (row < 0 || row >= static_cast<int>(mref.offsets.size())) return;
        mref.offsets[static_cast<std::size_t>(row)].*field = value;
    }, "morph", std::string("morph.offset.") + key);
    return true;
}

bool offset_drag_vec4(Viewer& v, int morph, int row, pmx::Vec4 pmx::MorphOffset::*field,
                      const char* label, const char* key) {
    if (morph < 0 || morph >= static_cast<int>(v.model.morphs.size())) return false;
    const pmx::Morph& morph_ref = v.model.morphs[static_cast<std::size_t>(morph)];
    if (row < 0 || row >= static_cast<int>(morph_ref.offsets.size())) return false;
    const pmx::Vec4 current = morph_ref.offsets[static_cast<std::size_t>(row)].*field;

    float tmp[4] = {current.x, current.y, current.z, current.w};
    ImGui::SetNextItemWidth(pmxui::scale(-110.0f));
    if (!ImGui::DragFloat4(label, tmp, 0.01f, -99999.0f, 99999.0f, "%.3f")) return false;
    const pmx::Vec4 value{tmp[0], tmp[1], tmp[2], tmp[3]};
    if (value.x == current.x && value.y == current.y && value.z == current.z &&
        value.w == current.w)
        return false;
    v.edit("修改形态偏移", [morph, row, field, value](pmx::Model& m) {
        if (morph < 0 || morph >= static_cast<int>(m.morphs.size())) return;
        pmx::Morph& mref = m.morphs[static_cast<std::size_t>(morph)];
        if (row < 0 || row >= static_cast<int>(mref.offsets.size())) return;
        mref.offsets[static_cast<std::size_t>(row)].*field = value;
    }, "morph", std::string("morph.offset.") + key);
    return true;
}

// 顶点形态的 offset 是 Vec4，但 PMX 只使用前三个分量；这里保留 w 不动。
bool offset_drag_vec4_xyz(Viewer& v, int morph, int row, pmx::Vec4 pmx::MorphOffset::*field,
                          const char* label, const char* key) {
    if (morph < 0 || morph >= static_cast<int>(v.model.morphs.size())) return false;
    const pmx::Morph& morph_ref = v.model.morphs[static_cast<std::size_t>(morph)];
    if (row < 0 || row >= static_cast<int>(morph_ref.offsets.size())) return false;
    const pmx::Vec4 current = morph_ref.offsets[static_cast<std::size_t>(row)].*field;

    float tmp[3] = {current.x, current.y, current.z};
    ImGui::SetNextItemWidth(pmxui::scale(-110.0f));
    if (!ImGui::DragFloat3(label, tmp, 0.01f, -99999.0f, 99999.0f, "%.3f")) return false;
    if (tmp[0] == current.x && tmp[1] == current.y && tmp[2] == current.z) return false;
    const pmx::Vec3 value{tmp[0], tmp[1], tmp[2]};
    v.edit("修改形态偏移", [morph, row, field, value](pmx::Model& m) {
        if (morph < 0 || morph >= static_cast<int>(m.morphs.size())) return;
        pmx::Morph& mref = m.morphs[static_cast<std::size_t>(morph)];
        if (row < 0 || row >= static_cast<int>(mref.offsets.size())) return;
        pmx::Vec4& vec = mref.offsets[static_cast<std::size_t>(row)].*field;
        vec.x = value.x;
        vec.y = value.y;
        vec.z = value.z;
    }, "morph", std::string("morph.offset.") + key);
    return true;
}

// 选中偏移的编辑器：按形态类型给出不同字段，全部通过 v.edit 写入。
void draw_offset_editor(Viewer& v, int morph, int row, int type) {
    const pmx::Model& model = v.model;
    const int vertex_limit = std::max(0, static_cast<int>(model.vertices.size()) - 1);

    ImGui::PushID(row);
    switch (type) {
        case 0:
        case 9: {
            std::vector<IndexOption> morphs;
            morphs.reserve(model.morphs.size());
            for (int i = 0; i < static_cast<int>(model.morphs.size()); ++i)
                morphs.push_back({i, indexed_name(i, model.morphs[static_cast<std::size_t>(i)].name)});
            offset_index_combo(v, morph, row, &pmx::MorphOffset::morph, "##off_morph", "目标形态",
                               "morph", morphs);
            offset_drag_float(v, morph, row, &pmx::MorphOffset::ratio, "比例", "ratio",
                              -99999.0f, 99999.0f);
            break;
        }
        case 1: {
            offset_input_int(v, morph, row, &pmx::MorphOffset::vertex, "顶点索引", "vertex", 0,
                             vertex_limit);
            offset_drag_vec4_xyz(v, morph, row, &pmx::MorphOffset::offset, "偏移", "offset");
            break;
        }
        case 2: {
            std::vector<IndexOption> bones;
            bones.reserve(model.bones.size());
            for (int i = 0; i < static_cast<int>(model.bones.size()); ++i)
                bones.push_back({i, indexed_name(i, model.bones[static_cast<std::size_t>(i)].name)});
            offset_index_combo(v, morph, row, &pmx::MorphOffset::bone, "##off_bone", "目标骨骼",
                               "bone", bones);
            offset_drag_vec3(v, morph, row, &pmx::MorphOffset::move, "移动", "move");
            // 四元数按原始数值编辑，不做角度转换。
            offset_drag_vec4(v, morph, row, &pmx::MorphOffset::rot, "旋转（四元数）", "rot");
            break;
        }
        case 3:
        case 4:
        case 5:
        case 6:
        case 7: {
            offset_input_int(v, morph, row, &pmx::MorphOffset::vertex, "顶点索引", "vertex", 0,
                             vertex_limit);
            offset_drag_vec4(v, morph, row, &pmx::MorphOffset::offset, "UV 偏移", "offset");
            break;
        }
        case 8: {
            std::vector<IndexOption> materials;
            materials.push_back({-1, "全部材质"});
            materials.reserve(model.materials.size() + 1);
            for (int i = 0; i < static_cast<int>(model.materials.size()); ++i)
                materials.push_back(
                    {i, indexed_name(i, model.materials[static_cast<std::size_t>(i)].name)});
            offset_index_combo(v, morph, row, &pmx::MorphOffset::material, "##off_material",
                               "目标材质", "material", materials);

            static const char* kCalcItems[] = {"乘法", "加法"};
            offset_choice_combo(v, morph, row, &pmx::MorphOffset::calc, "##off_calc", "计算方式",
                                "calc", kCalcItems, IM_ARRAYSIZE(kCalcItems));

            offset_drag_vec4(v, morph, row, &pmx::MorphOffset::diffuse, "漫反射", "diffuse");
            offset_drag_vec3(v, morph, row, &pmx::MorphOffset::specular, "高光色", "specular");
            offset_drag_float(v, morph, row, &pmx::MorphOffset::specular_coef, "高光强度",
                              "specular_coef", -99999.0f, 99999.0f);
            offset_drag_vec3(v, morph, row, &pmx::MorphOffset::ambient, "环境色", "ambient");
            offset_drag_vec4(v, morph, row, &pmx::MorphOffset::edge_color, "描边颜色",
                             "edge_color");
            offset_drag_float(v, morph, row, &pmx::MorphOffset::edge_size, "描边大小",
                              "edge_size", -99999.0f, 99999.0f);
            offset_drag_vec4(v, morph, row, &pmx::MorphOffset::texture, "纹理", "texture");
            offset_drag_vec4(v, morph, row, &pmx::MorphOffset::sphere, "球面", "sphere");
            offset_drag_vec4(v, morph, row, &pmx::MorphOffset::toon, "Toon", "toon");
            break;
        }
        case 10: {
            std::vector<IndexOption> rigids;
            rigids.reserve(model.rigid.size());
            for (int i = 0; i < static_cast<int>(model.rigid.size()); ++i)
                rigids.push_back({i, indexed_name(i, model.rigid[static_cast<std::size_t>(i)].name)});
            offset_index_combo(v, morph, row, &pmx::MorphOffset::rigid, "##off_rigid", "目标刚体",
                               "rigid", rigids);

            static const char* kLocalItems[] = {"无", "局部"};
            offset_choice_combo(v, morph, row, &pmx::MorphOffset::local, "##off_local", "局部",
                                "local", kLocalItems, IM_ARRAYSIZE(kLocalItems));

            offset_drag_vec3(v, morph, row, &pmx::MorphOffset::velocity, "速度", "velocity");
            offset_drag_vec3(v, morph, row, &pmx::MorphOffset::torque, "扭矩", "torque");
            break;
        }
        default:
            ImGui::TextDisabled("该形态类型不支持偏移编辑");
            break;
    }
    ImGui::PopID();
}

}  // namespace

void panel_morph(Viewer& v) {
    if (!v.pose) {
        ImGui::TextDisabled("未加载模型");
        return;
    }

    static std::string filter;
    static float preview_pct = 0.0f;
    static int preview_owner = -1;
    static int offset_row = -1;
    static int offset_owner = -1;
    static int panel_pick = 4;
    static int panel_owner = -1;
    static int pending_delete = -1;

    // 结构变化后同时重置预览与详情里的临时状态。
    auto reset_preview_state = [&v]() {
        clear_morph_preview(v);
        preview_pct = 0.0f;
        preview_owner = -1;
        offset_owner = -1;
        panel_owner = -1;
    };

    int morph_count = static_cast<int>(v.model.morphs.size());

    // 撤销/结构变化后选中越界时清空选择。
    if (v.sel.kind == SelKind::Morph && (v.sel.index < 0 || v.sel.index >= morph_count))
        v.select(SelKind::None, -1);
    int idx = v.sel.kind == SelKind::Morph ? v.sel.index : -1;

    // ------------------------------------------------------------ 工具栏
    int add_type = -1;
    bool copy_now = false;

    if (ImGui::Button("新建形态")) ImGui::OpenPopup("##morph_add");
    ImGui::SetItemTooltip("新建形态（选择类型）");
    if (ImGui::BeginPopup("##morph_add")) {
        static const int kAddTypes[] = {1, 2, 3, 8, 0, 9, 10};
        for (int type : kAddTypes) {
            const std::string text = std::string("新建") + morph_type_name(type) + "形态";
            if (ImGui::Selectable(text.c_str())) {
                add_type = type;
                ImGui::CloseCurrentPopup();
            }
        }
        ImGui::EndPopup();
    }

    ImGui::SameLine();
    ImGui::BeginDisabled(idx < 0);
    if (ImGui::Button("复制")) copy_now = true;
    ImGui::EndDisabled();
    ImGui::SetItemTooltip("复制当前形态");

    ImGui::SameLine();
    ImGui::BeginDisabled(idx < 0);
    if (ImGui::Button("删除")) {
        pending_delete = idx;
        ImGui::OpenPopup("删除形态##morph");
    }
    ImGui::EndDisabled();
    ImGui::SetItemTooltip("删除当前形态（需二次确认）");

    if (add_type >= 0) {
        v.push_undo("新建形态");
        const int created = pmxdoc::add_morph(v.model, add_type);
        reset_preview_state();
        v.clamp_selection();
        if (created >= 0 && created < static_cast<int>(v.model.morphs.size()))
            v.select(SelKind::Morph, created);
        else
            v.select(SelKind::None, -1);
        v.touched("structure");
        return;
    }

    if (copy_now) {
        v.push_undo("复制形态");
        const int copy = pmxdoc::duplicate_morph(v.model, idx);
        reset_preview_state();
        v.clamp_selection();
        if (copy >= 0 && copy < static_cast<int>(v.model.morphs.size()))
            v.select(SelKind::Morph, copy);
        else
            v.select(SelKind::None, -1);
        v.touched("structure");
        return;
    }

    // ------------------------------------------------------------ 搜索 + 列表
    ImGui::SetNextItemWidth(-1.0f);
    ImGui::InputTextWithHint("##morph_search", "搜索形态名 / 中文 / 英文名", &filter);

    morph_count = static_cast<int>(v.model.morphs.size());
    ImGui::BeginChild("##morph_list", ImVec2(0, pmxui::scale(180.0f)), ImGuiChildFlags_Borders);
    {
        std::vector<int> visible;
        visible.reserve(v.model.morphs.size());
        for (int i = 0; i < morph_count; ++i) {
            const pmx::Morph& morph = v.model.morphs[static_cast<std::size_t>(i)];
            if (pmxui::match_filter(filter, morph.name, morph.name_en,
                                    pmx::name_zh(pmx::NameKind::Morph, morph.name,
                                                 morph.name_en)))
                visible.push_back(i);
        }

        if (morph_count == 0) {
            ImGui::TextDisabled("尚无形态");
        } else if (visible.empty()) {
            ImGui::TextDisabled("没有匹配的形态");
        } else {
            ImGuiListClipper clipper;
            clipper.Begin(static_cast<int>(visible.size()));
            while (clipper.Step()) {
                for (int k = clipper.DisplayStart; k < clipper.DisplayEnd; ++k) {
                    const int i = visible[static_cast<std::size_t>(k)];
                    const pmx::Morph& mo = v.model.morphs[static_cast<std::size_t>(i)];
                    std::string text = morph_list_text(mo, i);
                    const std::string zh = pmxui::zh_only(pmx::NameKind::Morph, mo.name,
                                                          mo.name_en);
                    const std::string row_id = "morph_row" + std::to_string(i);
                    if (pmxui::zh_row(row_id.c_str(), text, zh, i == idx)) {
                        v.select(SelKind::Morph, i);
                        idx = i;
                    }
                }
            }
        }
    }
    ImGui::EndChild();

    // 切换形态时清空预览，并重置详情里的临时状态。
    if (preview_owner != idx) {
        if (preview_owner >= 0 || idx >= 0) clear_morph_preview(v);
        preview_owner = idx;
        preview_pct = 0.0f;
        offset_owner = -1;
        panel_owner = -1;
    }

    if (idx < 0 || idx >= morph_count) {
        ImGui::TextDisabled("从上方列表选择一个形态");
    } else {
        pmx::Morph& mo = v.model.morphs[static_cast<std::size_t>(idx)];
        ImGui::TextDisabled("索引 %d · %d 个形态", idx, morph_count);
        ImGui::BeginChild("##morph_detail", ImVec2(0, 0));

        // -------------------------------------------------------- 基本
        ImGui::SeparatorText("基本");
        pmxui::name_fields(v, mo.name, mo.name_en, "morph", "morph");
        pmxui::zh_line(pmx::NameKind::Morph, mo.name, mo.name_en);

        if (panel_owner != idx) {
            panel_owner = idx;
            panel_pick = std::clamp(mo.panel, 0, 4);
        }
        static const char* kPanelItems[] = {"0 系统", "1 眉", "2 眼", "3 口", "4 其他"};
        ImGui::SetNextItemWidth(pmxui::scale(-110.0f));
        if (ImGui::Combo("操作面板", &panel_pick, kPanelItems, IM_ARRAYSIZE(kPanelItems))) {
            const int value = panel_pick;
            v.edit("修改操作面板", [idx, value](pmx::Model& m) {
                if (idx < 0 || idx >= static_cast<int>(m.morphs.size())) return;
                m.morphs[static_cast<std::size_t>(idx)].panel = value;
            }, "morph", "morph.panel");
        }
        ImGui::SetItemTooltip("0 系统 / 1 眉 / 2 眼 / 3 口 / 4 其他");
        ImGui::Text("类型  %s", morph_type_name(mo.type));

        // -------------------------------------------------------- 预览
        ImGui::SeparatorText("预览");
        ImGui::TextDisabled("仅影响当前视图，不写入文件");
        ImGui::SetNextItemWidth(std::max(pmxui::scale(80.0f), ImGui::GetContentRegionAvail().x - pmxui::scale(160.0f)));
        const bool preview_changed =
            ImGui::SliderFloat("##morph_weight", &preview_pct, 0.0f, 100.0f, "%.0f%%");
        ImGui::SameLine();
        ImGui::TextDisabled("%.0f%%", preview_pct);
        ImGui::SameLine();
        if (ImGui::Button("清零")) {
            preview_pct = 0.0f;
            apply_morph_preview(v, idx, preview_pct);
        }
        if (preview_changed) apply_morph_preview(v, idx, preview_pct);

        // -------------------------------------------------------- 偏移数据
        ImGui::SeparatorText("偏移数据");
        const int offset_count = static_cast<int>(mo.offsets.size());
        if (offset_owner != idx) {
            offset_owner = idx;
            offset_row = offset_count > 0 ? 0 : -1;
        }
        if (offset_count == 0) offset_row = -1;
        else offset_row = std::clamp(offset_row, 0, offset_count - 1);

        ImGui::BeginChild("##morph_offsets", ImVec2(0, pmxui::scale(180.0f)), ImGuiChildFlags_Borders);
        {
            if (offset_count == 0) {
                ImGui::TextDisabled("暂无偏移");
            } else if (ImGui::BeginTable("##morph_offset_table", 2,
                                         ImGuiTableFlags_RowBg | ImGuiTableFlags_BordersInnerV |
                                             ImGuiTableFlags_SizingStretchProp)) {
                ImGui::TableSetupColumn("目标", ImGuiTableColumnFlags_WidthStretch, 0.55f);
                ImGui::TableSetupColumn("数值", ImGuiTableColumnFlags_WidthStretch, 0.45f);
                ImGui::TableHeadersRow();

                const int shown = std::min(offset_count, kOffsetDisplayCap);
                ImGuiListClipper clipper;
                clipper.Begin(shown);
                while (clipper.Step()) {
                    for (int r = clipper.DisplayStart; r < clipper.DisplayEnd; ++r) {
                        std::string target;
                        std::string value;
                        offset_desc(v.model, mo.type,
                                    mo.offsets[static_cast<std::size_t>(r)], target, value);
                        ImGui::TableNextRow();
                        ImGui::TableSetColumnIndex(0);
                        const std::string label = target + "##offset_row" + std::to_string(r);
                        if (ImGui::Selectable(label.c_str(), r == offset_row,
                                              ImGuiSelectableFlags_SpanAllColumns))
                            offset_row = r;
                        ImGui::TableSetColumnIndex(1);
                        ImGui::TextUnformatted(value.c_str());
                    }
                }
                ImGui::EndTable();
            }
        }
        ImGui::EndChild();

        if (offset_count > kOffsetDisplayCap)
            ImGui::TextDisabled("共 %d 项，仅显示前 %d 项", offset_count, kOffsetDisplayCap);
        else
            ImGui::TextDisabled("共 %d 项", offset_count);

        bool add_offset = false;
        bool remove_offset = false;
        ImGui::BeginDisabled(mo.type < 0 || mo.type > 10);
        if (ImGui::Button("添加偏移")) add_offset = true;
        ImGui::EndDisabled();
        ImGui::SetItemTooltip("按当前形态类型追加一条零值偏移");
        ImGui::SameLine();
        ImGui::BeginDisabled(offset_row < 0);
        if (ImGui::Button("删除偏移")) remove_offset = true;
        ImGui::EndDisabled();
        ImGui::SetItemTooltip("删除选中的偏移");

        if (add_offset) {
            const int morph = idx;
            const int type = mo.type;
            v.push_undo("新建形态偏移");
            if (morph >= 0 && morph < static_cast<int>(v.model.morphs.size())) {
                pmx::Morph& target = v.model.morphs[static_cast<std::size_t>(morph)];
                target.offsets.push_back(make_default_offset(type));
                offset_row = static_cast<int>(target.offsets.size()) - 1;
            }
            v.clamp_selection();
            v.select(SelKind::Morph, morph);
            v.touched("morph");
            ImGui::EndChild();
            return;
        }

        if (remove_offset) {
            const int morph = idx;
            const int row = offset_row;
            v.push_undo("删除形态偏移");
            if (morph >= 0 && morph < static_cast<int>(v.model.morphs.size())) {
                std::vector<pmx::MorphOffset>& offsets =
                    v.model.morphs[static_cast<std::size_t>(morph)].offsets;
                if (row >= 0 && row < static_cast<int>(offsets.size()))
                    offsets.erase(offsets.begin() + row);
                offset_row = offsets.empty()
                                 ? -1
                                 : std::min(row, static_cast<int>(offsets.size()) - 1);
            }
            v.clamp_selection();
            v.select(SelKind::Morph, morph);
            v.touched("morph");
            ImGui::EndChild();
            return;
        }

        // -------------------------------------------------------- 编辑选中偏移
        ImGui::SeparatorText("编辑选中偏移");
        if (offset_row < 0 || offset_row >= offset_count) {
            ImGui::TextDisabled("选中一条偏移后进行编辑");
        } else {
            ImGui::TextDisabled("第 %d 条 / 共 %d 条", offset_row, offset_count);
            draw_offset_editor(v, idx, offset_row, mo.type);
        }

        ImGui::EndChild();
    }

    // ------------------------------------------------------------ 删除确认
    int delete_target = -1;
    if (ImGui::BeginPopupModal("删除形态##morph", nullptr,
                               ImGuiWindowFlags_AlwaysAutoResize)) {
        const int target = pending_delete;
        if (target < 0 || target >= static_cast<int>(v.model.morphs.size())) {
            ImGui::TextDisabled("形态已不存在");
            if (ImGui::Button("关闭")) {
                pending_delete = -1;
                ImGui::CloseCurrentPopup();
            }
        } else {
            const pmx::Morph& morph = v.model.morphs[static_cast<std::size_t>(target)];
            const std::string name = morph.name.empty() ? "未命名形态" : morph.name;
            ImGui::Text("确定删除「%s」？", name.c_str());
            if (ImGui::Button("删除")) {
                delete_target = target;
                pending_delete = -1;
                ImGui::CloseCurrentPopup();
            }
            ImGui::SameLine();
            if (ImGui::Button("取消")) {
                pending_delete = -1;
                ImGui::CloseCurrentPopup();
            }
        }
        ImGui::EndPopup();
    }

    if (delete_target >= 0) {
        v.push_undo("删除形态");
        const int next = pmxdoc::remove_morph(v.model, delete_target);
        reset_preview_state();
        v.clamp_selection();
        if (next >= 0 && next < static_cast<int>(v.model.morphs.size()))
            v.select(SelKind::Morph, next);
        else
            v.select(SelKind::None, -1);
        v.touched("structure");
        return;
    }
}
