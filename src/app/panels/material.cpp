#include "app/panels.hpp"

#include <algorithm>
#include <cstdint>
#include <string>

#include <imgui.h>

#include "app/document_ops.hpp"
#include "app/panels/common.hpp"

namespace {

int selected_material(const Viewer& v) {
    if (v.sel.kind != SelKind::Material) return -1;
    if (v.sel.index < 0 || v.sel.index >= static_cast<int>(v.model.materials.size())) return -1;
    return v.sel.index;
}

// PMX 内部纹理路径可能带目录，列表与下拉里只显示文件名，完整路径放进悬浮提示。
std::string texture_file_name(const Viewer& v, int index) {
    const std::string path = v.model.resolve_texture(index);
    const std::size_t slash = path.find_last_of("/\\");
    return slash == std::string::npos ? path : path.substr(slash + 1);
}

// 纹理下拉：索引 + 文件名，末尾带「无」项。coalesce 为空表示每次都压快照。
bool texture_combo(Viewer& v, int material, int pmx::Material::*field, const char* id,
                   const char* label, const char* empty_text, const char* edit_label,
                   const char* coalesce) {
    const int count = static_cast<int>(v.model.textures.size());
    int current = v.model.materials[static_cast<std::size_t>(material)].*field;
    if (current < 0 || current >= count) current = -1;

    const std::string preview =
        current >= 0 ? std::to_string(current) + " · " + texture_file_name(v, current)
                     : std::string(empty_text);

    int picked = current;
    bool changed = false;
    ImGui::SetNextItemWidth(pmxui::scale(-110.0f));
    if (ImGui::BeginCombo(id, preview.c_str())) {
        if (ImGui::Selectable(empty_text, current < 0)) {
            picked = -1;
            changed = true;
        }
        for (int i = 0; i < count; ++i) {
            const std::string item = std::to_string(i) + " · " + texture_file_name(v, i);
            const bool selected = (i == current);
            if (ImGui::Selectable(item.c_str(), selected)) {
                picked = i;
                changed = true;
            }
            if (selected) ImGui::SetItemDefaultFocus();
        }
        ImGui::EndCombo();
    }
    if (current >= 0 && ImGui::IsItemHovered())
        ImGui::SetTooltip("%s", v.model.resolve_texture(current).c_str());
    ImGui::SameLine();
    ImGui::TextUnformatted(label);

    if (!changed || picked == current) return false;
    v.edit(edit_label, [material, field, picked](pmx::Model& m) {
        if (material < 0 || material >= static_cast<int>(m.materials.size())) return;
        m.materials[static_cast<std::size_t>(material)].*field = picked;
    }, "material", coalesce ? std::string(coalesce) : std::string());
    return true;
}

bool index_input(Viewer& v, int material, int pmx::Material::*field, const char* label,
                 const char* edit_label, int lo, int hi, const char* coalesce) {
    int value = v.model.materials[static_cast<std::size_t>(material)].*field;
    ImGui::SetNextItemWidth(pmxui::scale(-110.0f));
    if (!ImGui::InputInt(label, &value)) return false;
    value = std::clamp(value, lo, hi);
    v.edit(edit_label, [material, field, value](pmx::Model& m) {
        if (material < 0 || material >= static_cast<int>(m.materials.size())) return;
        m.materials[static_cast<std::size_t>(material)].*field = value;
    }, "material", coalesce ? std::string(coalesce) : std::string());
    return true;
}

bool color_edit4(Viewer& v, int material, pmx::Vec4 pmx::Material::*field, const char* label,
                 const char* edit_label, const char* coalesce) {
    const pmx::Vec4 current = v.model.materials[static_cast<std::size_t>(material)].*field;
    float tmp[4] = {current.x, current.y, current.z, current.w};
    ImGui::SetNextItemWidth(pmxui::scale(-110.0f));
    if (!ImGui::ColorEdit4(label, tmp, ImGuiColorEditFlags_Float)) return false;
    const pmx::Vec4 value{tmp[0], tmp[1], tmp[2], tmp[3]};
    v.edit(edit_label, [material, field, value](pmx::Model& m) {
        if (material < 0 || material >= static_cast<int>(m.materials.size())) return;
        m.materials[static_cast<std::size_t>(material)].*field = value;
    }, "material", coalesce ? std::string(coalesce) : std::string());
    return true;
}

bool color_edit3(Viewer& v, int material, pmx::Vec3 pmx::Material::*field, const char* label,
                 const char* edit_label, const char* coalesce) {
    const pmx::Vec3 current = v.model.materials[static_cast<std::size_t>(material)].*field;
    float tmp[3] = {current.x, current.y, current.z};
    ImGui::SetNextItemWidth(pmxui::scale(-110.0f));
    if (!ImGui::ColorEdit3(label, tmp, ImGuiColorEditFlags_Float)) return false;
    const pmx::Vec3 value{tmp[0], tmp[1], tmp[2]};
    v.edit(edit_label, [material, field, value](pmx::Model& m) {
        if (material < 0 || material >= static_cast<int>(m.materials.size())) return;
        m.materials[static_cast<std::size_t>(material)].*field = value;
    }, "material", coalesce ? std::string(coalesce) : std::string());
    return true;
}

bool flag_checkbox(Viewer& v, int material, std::uint8_t flag, const char* label) {
    bool on = (v.model.materials[static_cast<std::size_t>(material)].draw_flags & flag) != 0;
    if (!ImGui::Checkbox(label, &on)) return false;
    v.edit("修改绘制标志", [material, flag, on](pmx::Model& m) {
        if (material < 0 || material >= static_cast<int>(m.materials.size())) return;
        std::uint8_t& flags = m.materials[static_cast<std::size_t>(material)].draw_flags;
        flags = on ? static_cast<std::uint8_t>(flags | flag)
                   : static_cast<std::uint8_t>(flags & static_cast<std::uint8_t>(~flag));
    }, "material");
    return true;
}

void draw_material_detail(Viewer& v, int index) {
    pmx::Material& mt = v.model.materials[static_cast<std::size_t>(index)];
    const int material_count = static_cast<int>(v.model.materials.size());
    const int texture_count = static_cast<int>(v.model.textures.size());

    ImGui::TextDisabled("索引 %d · %d 个材质", index, material_count);
    ImGui::SeparatorText("基本");
    const std::string name_id = "material_name_" + std::to_string(index);
    pmxui::name_fields(v, mt.name, mt.name_en, name_id.c_str(), "material");
    pmxui::zh_line(pmx::NameKind::Material, mt.name, mt.name_en);
    ImGui::TextDisabled("面数 %d", mt.face_count > 0 ? mt.face_count / 3 : 0);

    ImGui::SeparatorText("颜色");
    color_edit4(v, index, &pmx::Material::diffuse, "漫反射", "修改漫反射",
                "material.diffuse");
    color_edit3(v, index, &pmx::Material::specular, "高光色", "修改高光色", "material.color");
    pmxui::drag_float(v, "高光强度", mt.specular_coef, 0.1f, 0.0f, 200.0f, "material",
                      "修改高光强度", "material.spec");
    color_edit3(v, index, &pmx::Material::ambient, "环境色", "修改环境色", "material.color");

    ImGui::SeparatorText("贴图");
    texture_combo(v, index, &pmx::Material::texture, "##mat_texture", "通常贴图", "（无贴图）",
                  "修改通常贴图", nullptr);
    index_input(v, index, &pmx::Material::texture, "贴图索引", "修改通常贴图", -1,
                texture_count - 1, "material.texture");
    {
        const std::string path =
            mt.texture >= 0 ? v.model.resolve_texture(mt.texture) : std::string();
        ImGui::TextDisabled("路径 %s", path.empty() ? "—" : path.c_str());
        if (!path.empty() && ImGui::IsItemHovered()) ImGui::SetTooltip("%s", path.c_str());
    }

    texture_combo(v, index, &pmx::Material::sphere, "##mat_sphere", "球面贴图", "（无球面贴图）",
                  "修改球面贴图", nullptr);
    index_input(v, index, &pmx::Material::sphere, "球面索引", "修改球面贴图", -1,
                texture_count - 1, "material.sphere");
    {
        static const char* kSphereModes[] = {"0 无", "1 乘算", "2 加算", "3 子纹理"};
        int mode = std::clamp(static_cast<int>(mt.sphere_mode), 0, 3);
        ImGui::SetNextItemWidth(pmxui::scale(-110.0f));
        if (ImGui::Combo("球面模式", &mode, kSphereModes, IM_ARRAYSIZE(kSphereModes))) {
            v.edit("修改球面模式", [index, mode](pmx::Model& m) {
                if (index < 0 || index >= static_cast<int>(m.materials.size())) return;
                m.materials[static_cast<std::size_t>(index)].sphere_mode =
                    static_cast<std::uint8_t>(mode);
            }, "material");
        }
    }

    bool shared = mt.toon_shared != 0;
    if (ImGui::Checkbox("共享 Toon", &shared)) {
        v.edit("切换共享 Toon", [index, shared](pmx::Model& m) {
            if (index < 0 || index >= static_cast<int>(m.materials.size())) return;
            pmx::Material& m2 = m.materials[static_cast<std::size_t>(index)];
            m2.toon_shared = shared ? 1 : 0;
            m2.toon = shared ? 0 : -1;
        }, "material");
    }
    if (mt.toon_shared != 0) {
        int shown = std::clamp(mt.toon + 1, 1, 10);
        ImGui::SetNextItemWidth(pmxui::scale(-110.0f));
        if (ImGui::InputInt("Toon 索引", &shown)) {
            shown = std::clamp(shown, 1, 10);
            const int value = shown - 1;
            v.edit("修改共享 Toon", [index, value](pmx::Model& m) {
                if (index < 0 || index >= static_cast<int>(m.materials.size())) return;
                m.materials[static_cast<std::size_t>(index)].toon = value;
            }, "material", "material.toon");
        }
        ImGui::TextDisabled("对应 toon01–toon10");
    } else {
        texture_combo(v, index, &pmx::Material::toon, "##mat_toon", "Toon 贴图", "（无 Toon）",
                      "修改 Toon 贴图", nullptr);
    }

    ImGui::SeparatorText("描边与阴影");
    color_edit4(v, index, &pmx::Material::edge_color, "描边颜色", "修改描边颜色",
                "material.edgecolor");
    pmxui::drag_float(v, "描边大小", mt.edge_size, 0.1f, 0.0f, 100.0f, "material",
                      "修改描边大小", "material.edgesize");

    struct FlagItem {
        const char* label;
        std::uint8_t flag;
    };
    static const FlagItem kFlags[] = {
        {"双面显示", pmx::MF_DOUBLE_SIDED}, {"地面阴影", pmx::MF_GROUND_SHADOW},
        {"阴影贴图", pmx::MF_SHADOW_MAP},   {"自阴影", pmx::MF_SELF_SHADOW},
        {"描边", pmx::MF_EDGE},             {"顶点色", pmx::MF_VERTEX_COLOR},
        {"点", pmx::MF_POINT},              {"线", pmx::MF_LINE},
    };
    if (ImGui::BeginTable("##material_flags", 2, ImGuiTableFlags_SizingStretchSame)) {
        for (const FlagItem& item : kFlags) {
            ImGui::TableNextColumn();
            flag_checkbox(v, index, item.flag, item.label);
        }
        ImGui::EndTable();
    }

    ImGui::SeparatorText("备注");
    std::string memo = mt.memo;
    ImGui::SetNextItemWidth(pmxui::scale(-110.0f));
    if (ImGui::InputText("备注", &memo)) {
        v.edit("修改材质备注", [index, memo](pmx::Model& m) {
            if (index < 0 || index >= static_cast<int>(m.materials.size())) return;
            m.materials[static_cast<std::size_t>(index)].memo = memo;
        }, "material", "material.memo");
    }
}

}  // namespace

void panel_material(Viewer& v) {
    static std::string filter;
    static int pending_delete = -1;

    const bool loaded = v.pose != nullptr;
    int current = selected_material(v);

    ImGui::BeginDisabled(!loaded);
    if (ImGui::Button("新建材质")) {
        v.push_undo("新建材质");
        const int index = pmxdoc::add_material(v.model);
        v.clamp_selection();
        if (index >= 0 && index < static_cast<int>(v.model.materials.size()))
            v.select(SelKind::Material, index);
        v.touched("structure");
    }
    ImGui::SameLine();
    ImGui::BeginDisabled(current < 0);
    if (ImGui::Button("复制材质")) {
        v.push_undo("复制材质");
        const int index = pmxdoc::duplicate_material(v.model, current);
        v.clamp_selection();
        if (index >= 0 && index < static_cast<int>(v.model.materials.size()))
            v.select(SelKind::Material, index);
        v.touched("structure");
    }
    ImGui::SameLine();
    if (ImGui::Button("删除材质")) {
        pending_delete = current;
        ImGui::OpenPopup("删除材质##material");
    }
    ImGui::EndDisabled();
    ImGui::EndDisabled();

    ImGui::SetNextItemWidth(-1.0f);
    ImGui::InputTextWithHint("##material_search", "搜索材质名 / 中文 / 英文名", &filter);

    const int material_count = static_cast<int>(v.model.materials.size());
    int shown_rows = 0;
    ImGui::BeginChild("##material_list", ImVec2(0, pmxui::scale(180.0f)), ImGuiChildFlags_Borders);
    for (int i = 0; i < material_count; ++i) {
        const pmx::Material& mt = v.model.materials[static_cast<std::size_t>(i)];
        if (!pmxui::match_filter(filter, mt.name, mt.name_en,
                                 pmx::name_zh(pmx::NameKind::Material, mt.name, mt.name_en)))
            continue;
        ++shown_rows;

        ImGui::PushID(i);
        const ImVec4 swatch(mt.diffuse.x, mt.diffuse.y, mt.diffuse.z, 1.0f);
        ImGui::ColorButton("##swatch", swatch,
                           ImGuiColorEditFlags_NoTooltip | ImGuiColorEditFlags_NoDragDrop,
                           ImVec2(pmxui::scale(16.0f), pmxui::scale(16.0f)));
        ImGui::SameLine();

        std::string row = pmxui::base_name(mt.name, mt.name_en);
        if (row.empty()) row = "未命名材质";
        row += "  ·  ";
        row += std::to_string(mt.face_count > 0 ? mt.face_count / 3 : 0);
        row += " 面";
        const bool selected = (v.sel.kind == SelKind::Material && v.sel.index == i);
        const std::string zh = pmxui::zh_only(pmx::NameKind::Material, mt.name, mt.name_en);
        const std::string row_id = "mat_row" + std::to_string(i);
        if (pmxui::zh_row(row_id.c_str(), row, zh, selected)) v.select(SelKind::Material, i);

        const std::string path =
            mt.texture >= 0 ? v.model.resolve_texture(mt.texture) : std::string();
        ImGui::TextDisabled("    #%d  %s", i, path.empty() ? "（无贴图）" : path.c_str());
        if (!path.empty() && ImGui::IsItemHovered()) ImGui::SetTooltip("%s", path.c_str());
        ImGui::PopID();
    }
    if (material_count == 0) ImGui::TextDisabled("尚无材质");
    else if (shown_rows == 0) ImGui::TextDisabled("没有匹配的材质");
    ImGui::EndChild();

    current = selected_material(v);
    ImGui::BeginChild("##material_detail", ImVec2(0, 0));
    if (current < 0) {
        ImGui::TextDisabled("从上方列表选择一个材质");
    } else {
        ImGui::PushID(current);
        draw_material_detail(v, current);
        ImGui::PopID();
    }
    ImGui::EndChild();

    if (ImGui::BeginPopupModal("删除材质##material", nullptr,
                               ImGuiWindowFlags_AlwaysAutoResize)) {
        const int index = pending_delete;
        if (index < 0 || index >= static_cast<int>(v.model.materials.size())) {
            ImGui::TextDisabled("材质已不存在");
            if (ImGui::Button("关闭")) {
                pending_delete = -1;
                ImGui::CloseCurrentPopup();
            }
        } else {
            const pmx::Material& mt = v.model.materials[static_cast<std::size_t>(index)];
            const int faces = mt.face_count > 0 ? mt.face_count / 3 : 0;
            ImGui::Text("删除「%s」（%d 个三角面）", mt.name.c_str(), faces);
            ImGui::TextDisabled("并入上一个材质保留几何；\n连同三角面删除会真正删掉这些面。");

            bool close = false;
            if (ImGui::Button("连同三角面删除")) {
                v.push_undo("删除材质");
                const int result = pmxdoc::remove_material(v.model, index, false);
                v.clamp_selection();
                if (result >= 0 && result < static_cast<int>(v.model.materials.size()))
                    v.select(SelKind::Material, result);
                v.touched("structure");
                close = true;
            }
            ImGui::SetItemDefaultFocus();
            if (index > 0) {
                ImGui::SameLine();
                if (ImGui::Button("并入上一个材质")) {
                    v.push_undo("并入材质");
                    const int result = pmxdoc::remove_material(v.model, index, true);
                    v.clamp_selection();
                    if (result >= 0 && result < static_cast<int>(v.model.materials.size()))
                        v.select(SelKind::Material, result);
                    v.touched("structure");
                    close = true;
                }
            }
            ImGui::SameLine();
            if (ImGui::Button("取消")) close = true;
            if (close) {
                pending_delete = -1;
                ImGui::CloseCurrentPopup();
            }
        }
        ImGui::EndPopup();
    }
}
