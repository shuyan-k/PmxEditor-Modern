#include "app/panels.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <string>
#include <type_traits>
#include <vector>

#include <imgui.h>

#include "app/document_ops.hpp"
#include "app/panels/common.hpp"

namespace {

constexpr std::uint8_t kSbBendLink = 0x01;
constexpr std::uint8_t kSbCluster = 0x02;
constexpr std::uint8_t kSbRandomize = 0x04;

const char* const kShapes[] = {"0 三角网格", "1 四面体"};
const char* const kAeroModels[] = {"0 无", "1 顶点单面", "2 顶点双面",
                                   "3 双面升降力", "4 顶点单面（旧）"};
const char* const kConfigNames[] = {"VCF", "DP", "DG", "LF", "PR", "VC",
                                    "DF", "MT", "CHR", "KHR", "SHR", "AHR"};
const char* const kClusterNames[] = {"SRHR", "SKHR", "SSHR", "SR_SPLT", "SK_SPLT", "SS_SPLT"};
const char* const kIterationNames[] = {"V_IT", "P_IT", "D_IT", "C_IT"};
const char* const kMaterialNames[] = {"LST", "AST", "VST"};

std::string rigid_name_text(const pmx::Model& model, int i) {
    char prefix[16];
    std::snprintf(prefix, sizeof prefix, "%02d · ", i);
    std::string text(prefix);
    const pmx::RigidBody& rb = model.rigid[static_cast<std::size_t>(i)];
    const std::string label = pmx::name_with_zh(pmx::NameKind::Rigid, rb.name, rb.name_en);
    text += label.empty() ? "未命名刚体" : label;
    return text;
}

// 材质下拉（含 -1 无材质）。
bool material_combo(const char* label, int& value, const pmx::Model& model) {
    const int n = static_cast<int>(model.materials.size());
    std::string preview = "（无材质）";
    if (value >= 0 && value < n) {
        char prefix[16];
        std::snprintf(prefix, sizeof prefix, "%02d · ", value);
        preview = prefix;
        const pmx::Material& mt = model.materials[static_cast<std::size_t>(value)];
        preview += mt.name.empty() ? "未命名材质" : mt.name.c_str();
    }

    bool changed = false;
    ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
    if (ImGui::BeginCombo(label, preview.c_str())) {
        if (ImGui::Selectable("（无材质）", value < 0)) {
            value = -1;
            changed = true;
        }
        for (int i = 0; i < n; ++i) {
            char prefix[16];
            std::snprintf(prefix, sizeof prefix, "%02d · ", i);
            std::string text(prefix);
            const pmx::Material& mt = model.materials[static_cast<std::size_t>(i)];
            const std::string label =
                pmx::name_with_zh(pmx::NameKind::Material, mt.name, mt.name_en);
            text += label.empty() ? "未命名材质" : label;
            text += "##pm" + std::to_string(i);
            if (ImGui::Selectable(text.c_str(), value == i)) {
                value = i;
                changed = true;
            }
        }
        ImGui::EndCombo();
    }
    return changed;
}

// 锚点刚体下拉：直接列出全部刚体，不提供「无」项。
bool anchor_rigid_combo(const char* label, int& value, const pmx::Model& model) {
    const int n = static_cast<int>(model.rigid.size());
    if (n == 0) {
        ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
        ImGui::BeginDisabled(true);
        if (ImGui::BeginCombo(label, "（无刚体）")) ImGui::EndCombo();
        ImGui::EndDisabled();
        return false;
    }
    if (value < 0 || value >= n) value = 0;

    bool changed = false;
    ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
    if (ImGui::BeginCombo(label, rigid_name_text(model, value).c_str())) {
        for (int i = 0; i < n; ++i) {
            std::string text = rigid_name_text(model, i) + "##pa" + std::to_string(i);
            if (ImGui::Selectable(text.c_str(), value == i)) {
                value = i;
                changed = true;
            }
        }
        ImGui::EndCombo();
    }
    return changed;
}

bool soft_flag_checkbox(Viewer& v, int index, std::uint8_t flag, const char* text) {
    bool on = (v.model.soft_bodies[static_cast<std::size_t>(index)].flags & flag) != 0;
    if (!ImGui::Checkbox(text, &on)) return false;
    v.edit("修改柔体生成选项", [index, flag, on](pmx::Model& m) {
        std::uint8_t& flags = m.soft_bodies[static_cast<std::size_t>(index)].flags;
        flags = on ? static_cast<std::uint8_t>(flags | flag)
                   : static_cast<std::uint8_t>(flags & static_cast<std::uint8_t>(~flag));
    }, "soft", "soft.flags");
    return true;
}

// 求解参数网格：每行 3 组「名称 + 拖动框」，整列等宽。
template <typename T, std::size_t N>
void array_grid(Viewer& v, int soft_index, const char* table_id, const char* const* names,
                std::array<T, N> pmx::SoftBody::*field, float speed, T lo, T hi,
                const char* edit_label, const char* coalesce_prefix) {
    if (!ImGui::BeginTable(table_id, 3, ImGuiTableFlags_SizingStretchSame)) return;
    for (int i = 0; i < static_cast<int>(N); ++i) {
        ImGui::TableNextColumn();
        ImGui::PushID(i);
        ImGui::TextDisabled("%s", names[i]);
        ImGui::SetNextItemWidth(-1.0f);

        const T current = (v.model.soft_bodies[static_cast<std::size_t>(soft_index)].*field)
                               [static_cast<std::size_t>(i)];
        bool changed = false;
        T value = current;
        if constexpr (std::is_same_v<T, int>) {
            int tmp = static_cast<int>(current);
            if (ImGui::DragInt("##value", &tmp, speed, static_cast<int>(lo),
                               static_cast<int>(hi))) {
                value = static_cast<T>(tmp);
                changed = true;
            }
        } else {
            float tmp = static_cast<float>(current);
            if (ImGui::DragFloat("##value", &tmp, speed, static_cast<float>(lo),
                                 static_cast<float>(hi), "%.4f")) {
                value = static_cast<T>(tmp);
                changed = true;
            }
        }
        if (changed) {
            v.edit(edit_label, [soft_index, i, value, field](pmx::Model& m) {
                if (soft_index < 0 || soft_index >= static_cast<int>(m.soft_bodies.size()))
                    return;
                (m.soft_bodies[static_cast<std::size_t>(soft_index)].*field)
                    [static_cast<std::size_t>(i)] = value;
            }, "soft", std::string(coalesce_prefix) + std::to_string(i));
        }
        ImGui::PopID();
    }
    ImGui::EndTable();
}

// 碰撞掩码：16 个组的复选框（8 列 × 2 行），外加全选 / 清空。
void soft_mask_grid(Viewer& v, int index, std::uint16_t mask) {
    ImGui::PushID("soft_mask");
    if (ImGui::BeginTable("##grid", 8, ImGuiTableFlags_SizingStretchSame)) {
        for (int g = 0; g < 16; ++g) {
            ImGui::TableNextColumn();
            ImGui::PushID(g);
            bool on = (mask & static_cast<std::uint16_t>(1u << g)) != 0;
            const std::string label = std::to_string(g);
            if (ImGui::Checkbox(label.c_str(), &on)) {
                v.edit("修改柔体碰撞组", [index, g, on](pmx::Model& m) {
                    const std::uint16_t bit = static_cast<std::uint16_t>(1u << g);
                    std::uint16_t& target = m.soft_bodies[static_cast<std::size_t>(index)].mask;
                    target = on ? static_cast<std::uint16_t>(target | bit)
                                : static_cast<std::uint16_t>(target &
                                                             static_cast<std::uint16_t>(~bit));
                }, "soft", "soft.mask");
            }
            ImGui::PopID();
        }
        ImGui::EndTable();
    }
    ImGui::PopID();

    if (ImGui::Button("全选")) {
        v.edit("修改柔体碰撞组", [index](pmx::Model& m) {
            m.soft_bodies[static_cast<std::size_t>(index)].mask = 0xFFFF;
        }, "soft", "soft.mask");
    }
    ImGui::SameLine();
    if (ImGui::Button("清空")) {
        v.edit("修改柔体碰撞组", [index](pmx::Model& m) {
            m.soft_bodies[static_cast<std::size_t>(index)].mask = 0;
        }, "soft", "soft.mask");
    }
}

void draw_soft_detail(Viewer& v, int index) {
    pmx::Model& model = v.model;
    pmx::SoftBody& sb = model.soft_bodies[static_cast<std::size_t>(index)];
    const int rigid_count = static_cast<int>(model.rigid.size());
    const bool has_vertices = model.n_vertices() > 0;
    const int max_vertex = std::max(0, static_cast<int>(model.n_vertices()) - 1);

    ImGui::TextDisabled("索引 %d · %d 个柔体", index,
                        static_cast<int>(model.soft_bodies.size()));

    ImGui::SeparatorText("基本");
    pmxui::name_fields(v, sb.name, sb.name_en, "soft", "soft", "重命名柔体");
    pmxui::zh_line(pmx::NameKind::Soft, sb.name, sb.name_en);

    {
        int shape = std::clamp(static_cast<int>(sb.shape), 0, 1);
        ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
        if (ImGui::Combo("形状", &shape, kShapes, IM_ARRAYSIZE(kShapes)))
            v.edit("修改柔体形状", [index, shape](pmx::Model& m) {
                m.soft_bodies[static_cast<std::size_t>(index)].shape =
                    static_cast<std::uint8_t>(shape);
            }, "soft", "soft.shape");
    }
    {
        int material = sb.material;
        if (material_combo("材质", material, model) && material != sb.material)
            v.edit("修改柔体材质", [index, material](pmx::Model& m) {
                m.soft_bodies[static_cast<std::size_t>(index)].material = material;
            }, "soft", "soft.material");
    }
    {
        int group = std::clamp(static_cast<int>(sb.group), 0, 15);
        ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
        if (ImGui::DragInt("所属组", &group, 0.2f, 0, 15))
            v.edit("修改柔体所属组", [index, group](pmx::Model& m) {
                m.soft_bodies[static_cast<std::size_t>(index)].group =
                    static_cast<std::uint8_t>(group);
            }, "soft", "soft.group");
    }

    ImGui::SeparatorText("生成选项");
    soft_flag_checkbox(v, index, kSbBendLink, "生成弯曲链接");
    soft_flag_checkbox(v, index, kSbCluster, "生成簇");
    soft_flag_checkbox(v, index, kSbRandomize, "随机化约束");
    {
        int distance = sb.b_link_dist;
        ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
        if (ImGui::DragInt("弯曲链接距离", &distance, 0.2f, 0, 1000))
            v.edit("修改柔体生成选项", [index, distance](pmx::Model& m) {
                m.soft_bodies[static_cast<std::size_t>(index)].b_link_dist = distance;
            }, "soft", "soft.b_link_dist");
    }
    {
        int clusters = sb.cluster_count;
        ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
        if (ImGui::DragInt("簇数量", &clusters, 0.5f, 0, 100000))
            v.edit("修改柔体生成选项", [index, clusters](pmx::Model& m) {
                m.soft_bodies[static_cast<std::size_t>(index)].cluster_count = clusters;
            }, "soft", "soft.cluster_count");
    }

    ImGui::SeparatorText("质量与碰撞");
    pmxui::drag_float(v, "总质量", sb.total_mass, 0.1f, 0.0f, 100000.0f, "soft",
                      "修改柔体总质量", "soft.total_mass");
    pmxui::drag_float(v, "碰撞余量", sb.collision_margin, 0.01f, 0.0f, 1000.0f, "soft",
                      "修改柔体碰撞余量", "soft.collision_margin");
    {
        int aero = std::clamp(sb.aero_model, 0, 4);
        ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
        if (ImGui::Combo("气动模型", &aero, kAeroModels, IM_ARRAYSIZE(kAeroModels)))
            v.edit("修改气动模型", [index, aero](pmx::Model& m) {
                m.soft_bodies[static_cast<std::size_t>(index)].aero_model = aero;
            }, "soft", "soft.aero_model");
    }

    ImGui::SeparatorText("碰撞组");
    ImGui::TextDisabled("组号 0–15；勾选可碰撞的组");
    soft_mask_grid(v, index, sb.mask);

    ImGui::SeparatorText("求解参数");
    ImGui::TextDisabled("名称沿用 Bullet 软体参数");
    array_grid(v, index, "##soft_config", kConfigNames, &pmx::SoftBody::config, 0.01f,
               -99999.0f, 99999.0f, "修改柔体参数", "soft.config");
    array_grid(v, index, "##soft_cluster", kClusterNames, &pmx::SoftBody::cluster, 0.01f,
               -99999.0f, 99999.0f, "修改柔体参数", "soft.cluster");
    array_grid(v, index, "##soft_iteration", kIterationNames, &pmx::SoftBody::iteration, 0.2f,
               -1000, 1000, "修改柔体迭代次数", "soft.iteration");
    array_grid(v, index, "##soft_material", kMaterialNames, &pmx::SoftBody::material_params,
               0.01f, -99999.0f, 99999.0f, "修改柔体材质参数", "soft.material_params");

    // ------------------------------------------------------------ 锚点
    ImGui::SeparatorText("锚点");
    ImGui::TextDisabled("把柔体固定在刚体上的顶点");

    static int anchor_row = -1;
    static int anchor_owner = -1;
    static int anchor_rigid = -1;
    static int anchor_vertex = 0;
    static bool anchor_near = false;
    if (anchor_owner != index) {
        anchor_owner = index;
        anchor_row = sb.anchors.empty() ? -1 : 0;
        anchor_rigid = rigid_count > 0 ? 0 : -1;
        anchor_vertex = 0;
        anchor_near = false;
    }
    const int anchor_count = static_cast<int>(sb.anchors.size());
    if (anchor_count == 0) anchor_row = -1;
    else anchor_row = std::clamp(anchor_row, 0, anchor_count - 1);

    ImGui::BeginChild("##soft_anchors", ImVec2(0, pmxui::scale(96.0f)), ImGuiChildFlags_Borders);
    for (int i = 0; i < anchor_count; ++i) {
        const pmx::SoftBodyAnchor& anchor = sb.anchors[static_cast<std::size_t>(i)];
        std::string name = "?";
        if (anchor.rigid >= 0 && anchor.rigid < rigid_count) {
            const pmx::RigidBody& rb = model.rigid[static_cast<std::size_t>(anchor.rigid)];
            name = rb.name.empty() ? "未命名刚体" : rb.name;
        }
        char head[16];
        std::snprintf(head, sizeof head, "%02d · ", i);
        char body[256];
        std::snprintf(body, sizeof body, "刚体 %d「%s」· 顶点 %d%s", anchor.rigid,
                      name.c_str(), anchor.vertex, anchor.near ? " · 近" : "");
        std::string text = head;
        text += body;
        text += "##soft_anchor" + std::to_string(i);
        if (ImGui::Selectable(text.c_str(), i == anchor_row)) anchor_row = i;
    }
    if (anchor_count == 0) ImGui::TextDisabled("暂无锚点");
    ImGui::EndChild();

    ImGui::PushID("anchor");
    {
        int rigid = anchor_rigid;
        anchor_rigid_combo("刚体", rigid, model);
        anchor_rigid = rigid;
        ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
        ImGui::DragInt("顶点", &anchor_vertex, 0.2f, 0, max_vertex);
        anchor_vertex = std::clamp(anchor_vertex, 0, max_vertex);
        ImGui::SameLine();
        ImGui::Checkbox("近", &anchor_near);

        const bool can_add = rigid_count > 0 && has_vertices;
        ImGui::BeginDisabled(!can_add);
        if (ImGui::Button("添加锚点")) {
            const int rid = anchor_rigid;
            const int vertex = anchor_vertex;
            const std::uint8_t near = anchor_near ? 1 : 0;
            v.edit("添加柔体锚点", [index, rid, vertex, near](pmx::Model& m) {
                m.soft_bodies[static_cast<std::size_t>(index)].anchors.push_back(
                    {rid, vertex, near});
            }, "soft");
            anchor_row = static_cast<int>(sb.anchors.size()) - 1;
        }
        ImGui::EndDisabled();

        ImGui::SameLine();
        ImGui::BeginDisabled(anchor_row < 0);
        if (ImGui::Button("移除锚点")) {
            const int row = anchor_row;
            v.edit("移除柔体锚点", [index, row](pmx::Model& m) {
                auto& anchors = m.soft_bodies[static_cast<std::size_t>(index)].anchors;
                if (row >= 0 && row < static_cast<int>(anchors.size()))
                    anchors.erase(anchors.begin() + row);
            }, "soft");
            anchor_row = static_cast<int>(sb.anchors.size()) - 1;
        }
        ImGui::EndDisabled();
    }
    ImGui::PopID();

    // ------------------------------------------------------------ 固定点
    ImGui::SeparatorText("固定点");
    ImGui::TextDisabled("不参与演算的顶点");

    static int pin_row = -1;
    static int pin_owner = -1;
    static int pin_vertex = 0;
    if (pin_owner != index) {
        pin_owner = index;
        pin_row = sb.pins.empty() ? -1 : 0;
        pin_vertex = 0;
    }
    const int pin_count = static_cast<int>(sb.pins.size());
    if (pin_count == 0) pin_row = -1;
    else pin_row = std::clamp(pin_row, 0, pin_count - 1);

    ImGui::BeginChild("##soft_pins", ImVec2(0, pmxui::scale(76.0f)), ImGuiChildFlags_Borders);
    for (int i = 0; i < pin_count; ++i) {
        char head[16];
        std::snprintf(head, sizeof head, "%02d · ", i);
        std::string text = head;
        text += "顶点 " + std::to_string(sb.pins[static_cast<std::size_t>(i)]);
        text += "##soft_pin" + std::to_string(i);
        if (ImGui::Selectable(text.c_str(), i == pin_row)) pin_row = i;
    }
    if (pin_count == 0) ImGui::TextDisabled("暂无固定点");
    ImGui::EndChild();

    ImGui::PushID("pin");
    {
        ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
        ImGui::DragInt("顶点", &pin_vertex, 0.2f, 0, max_vertex);
        pin_vertex = std::clamp(pin_vertex, 0, max_vertex);

        ImGui::BeginDisabled(!has_vertices);
        if (ImGui::Button("添加")) {
            const int vertex = pin_vertex;
            v.edit("添加柔体固定点", [index, vertex](pmx::Model& m) {
                m.soft_bodies[static_cast<std::size_t>(index)].pins.push_back(vertex);
            }, "soft");
            pin_row = static_cast<int>(sb.pins.size()) - 1;
        }
        ImGui::EndDisabled();

        ImGui::SameLine();
        ImGui::BeginDisabled(pin_row < 0);
        if (ImGui::Button("移除")) {
            const int row = pin_row;
            v.edit("移除柔体固定点", [index, row](pmx::Model& m) {
                auto& pins = m.soft_bodies[static_cast<std::size_t>(index)].pins;
                if (row >= 0 && row < static_cast<int>(pins.size()))
                    pins.erase(pins.begin() + row);
            }, "soft");
            pin_row = static_cast<int>(sb.pins.size()) - 1;
        }
        ImGui::EndDisabled();
    }
    ImGui::PopID();
}

}  // namespace

void panel_soft(Viewer& v) {
    if (!v.pose) {
        ImGui::TextDisabled("未加载模型");
        return;
    }
    pmx::Model& model = v.model;
    const int soft_count = static_cast<int>(model.soft_bodies.size());

    // 选中越界（撤销后柔体变少）时清空选择。
    if (v.sel.kind == SelKind::Soft && (v.sel.index < 0 || v.sel.index >= soft_count))
        v.select(SelKind::None, -1);
    int idx = v.sel.kind == SelKind::Soft ? v.sel.index : -1;
    if (idx < 0 || idx >= soft_count) idx = -1;

    // ------------------------------------------------------------ 工具
    static int pending_delete = -1;

    if (ImGui::Button("新建柔体")) {
        v.push_undo("新建柔体");
        const int created = pmxdoc::add_softbody(model);
        v.clamp_selection();
        if (created >= 0) v.select(SelKind::Soft, created);
        else v.select(SelKind::None, -1);
        v.touched("structure");
        return;
    }
    ImGui::SetItemTooltip("新建柔体（PMX 2.1）");
    ImGui::SameLine();
    ImGui::BeginDisabled(idx < 0);
    if (ImGui::Button("删除")) {
        pending_delete = idx;
        ImGui::OpenPopup("删除柔体##soft");
    }
    ImGui::SetItemTooltip("删除当前柔体");
    ImGui::EndDisabled();

    // ------------------------------------------------------------ 列表
    ImGui::BeginChild("##soft_list", ImVec2(0, pmxui::scale(200.0f)), ImGuiChildFlags_Borders);
    if (soft_count == 0) {
        ImGui::TextDisabled("尚无柔体（PMX 2.1 才能保存）");
    } else {
        ImGuiListClipper clipper;
        clipper.Begin(soft_count);
        while (clipper.Step()) {
            for (int i = clipper.DisplayStart; i < clipper.DisplayEnd; ++i) {
                const pmx::SoftBody& s = model.soft_bodies[static_cast<std::size_t>(i)];
                char head[16];
                std::snprintf(head, sizeof head, "%02d · ", i);
                std::string row = head;
                const std::string label = pmxui::base_name(s.name, s.name_en);
                row += label.empty() ? "未命名柔体" : label;
                row += "   · 材质 " + std::to_string(s.material) + " · 组 " +
                       std::to_string(static_cast<int>(s.group));
                char mass[48];
                std::snprintf(mass, sizeof mass, "   质量 %.2f", s.total_mass);
                row += mass;
                const std::string zh = pmxui::zh_only(pmx::NameKind::Soft, s.name, s.name_en);
                const std::string row_id = "soft_row" + std::to_string(i);
                if (pmxui::zh_row(row_id.c_str(), row, zh, i == idx)) {
                    v.select(SelKind::Soft, i);
                    idx = i;
                }
            }
        }
    }
    ImGui::EndChild();

    if (idx >= 0) {
        ImGui::BeginChild("##soft_detail", ImVec2(0, 0));
        draw_soft_detail(v, idx);
        ImGui::EndChild();
    } else {
        ImGui::TextDisabled("未选择柔体（点击上方列表选择）");
    }

    // ------------------------------------------------------------ 删除确认
    int remove_index = -1;
    if (ImGui::BeginPopupModal("删除柔体##soft", nullptr,
                               ImGuiWindowFlags_AlwaysAutoResize)) {
        if (pending_delete < 0 || pending_delete >= soft_count) {
            ImGui::TextDisabled("柔体已不存在");
            if (ImGui::Button("关闭")) {
                pending_delete = -1;
                ImGui::CloseCurrentPopup();
            }
        } else {
            const pmx::SoftBody& s =
                model.soft_bodies[static_cast<std::size_t>(pending_delete)];
            ImGui::Text("确定删除「%s」？", s.name.empty() ? "未命名" : s.name.c_str());
            ImGui::TextDisabled("它的 %d 个锚点与 %d 个固定点会一起移除。",
                                static_cast<int>(s.anchors.size()),
                                static_cast<int>(s.pins.size()));
            if (ImGui::Button("删除")) {
                remove_index = pending_delete;
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

    if (remove_index >= 0) {
        v.push_undo("删除柔体");
        const int next = pmxdoc::remove_softbody(model, remove_index);
        v.clamp_selection();
        if (next >= 0) v.select(SelKind::Soft, next);
        else v.select(SelKind::None, -1);
        v.touched("structure");
        return;
    }
}
