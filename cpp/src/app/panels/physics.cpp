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

const char* const kRigidModes[] = {"0 跟随骨骼", "1 物理演算", "2 演算 + 对齐"};
const char* const kShapes[] = {"0 球", "1 箱", "2 胶囊"};
const char* const kJointTypes[] = {"0 弹簧 6DOF", "1 6DOF", "2 P2P",
                                   "3 ConeTwist", "4 Slider", "5 Hinge"};
const char* const kJointNames[] = {"弹簧 6DOF", "6DOF", "P2P", "ConeTwist", "Slider", "Hinge"};
const char* const kSizeHints[] = {"半径", "半宽 X / 高 Y / 深 Z", "半径 / 总高 / —"};

int joint_type_index(const pmx::Joint& jt) {
    return std::clamp(static_cast<int>(jt.type), 0, 5);
}

std::string rigid_item_text(const pmx::Model& model, int i) {
    char prefix[16];
    std::snprintf(prefix, sizeof prefix, "%02d · ", i);
    std::string text(prefix);
    const pmx::RigidBody& rb = model.rigid[static_cast<std::size_t>(i)];
    text += rb.name.empty() ? "未命名刚体" : rb.name.c_str();
    return text;
}

std::string joint_item_text(const pmx::Model& model, int i) {
    char prefix[16];
    std::snprintf(prefix, sizeof prefix, "%02d · ", i);
    std::string text(prefix);
    const pmx::Joint& jt = model.joints[static_cast<std::size_t>(i)];
    text += jt.name.empty() ? "未命名关节" : jt.name.c_str();
    return text;
}

// 骨骼下拉（含 -1）；value 只是临时选择值，返回 true 表示用户换了选项。
bool bone_combo(const char* label, int& value, const pmx::Model& model, const char* none_text) {
    const int n = static_cast<int>(model.bones.size());
    std::string preview;
    if (value >= 0 && value < n) {
        const pmx::Bone& bone = model.bones[static_cast<std::size_t>(value)];
        preview = std::to_string(value) + " · " + (bone.name.empty() ? "未命名" : bone.name);
    } else {
        preview = none_text;
    }

    bool changed = false;
    ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
    if (ImGui::BeginCombo(label, preview.c_str())) {
        if (ImGui::Selectable(none_text, value < 0)) {
            value = -1;
            changed = true;
        }
        for (int i = 0; i < n; ++i) {
            std::string text = std::to_string(i) + " · " +
                               (model.bones[static_cast<std::size_t>(i)].name.empty()
                                    ? "未命名"
                                    : model.bones[static_cast<std::size_t>(i)].name);
            text += "##pb" + std::to_string(i);
            if (ImGui::Selectable(text.c_str(), value == i)) {
                value = i;
                changed = true;
            }
        }
        ImGui::EndCombo();
    }
    return changed;
}

// 刚体下拉（关节的 A / B）；none_value 为「无」项。
bool rigid_combo(const char* label, int& value, const pmx::Model& model, const char* none_text) {
    const int n = static_cast<int>(model.rigid.size());
    std::string preview = (value >= 0 && value < n) ? rigid_item_text(model, value) : none_text;

    bool changed = false;
    ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
    if (ImGui::BeginCombo(label, preview.c_str())) {
        if (ImGui::Selectable(none_text, value < 0)) {
            value = -1;
            changed = true;
        }
        for (int i = 0; i < n; ++i) {
            std::string text = rigid_item_text(model, i) + "##pr" + std::to_string(i);
            if (ImGui::Selectable(text.c_str(), value == i)) {
                value = i;
                changed = true;
            }
        }
        ImGui::EndCombo();
    }
    return changed;
}

void warning_text(const char* text) {
    ImGui::PushStyleColor(ImGuiCol_Text, ImVec4(1.0f, 0.72f, 0.30f, 1.0f));
    ImGui::TextWrapped("%s", text);
    ImGui::PopStyleColor();
}

// 碰撞掩码：16 个组的复选框（4 列 × 4 行），外加全选 / 清空。
void rigid_mask_grid(Viewer& v, int index, std::uint16_t mask) {
    ImGui::PushID("rb_mask");
    if (ImGui::BeginTable("##grid", 4, ImGuiTableFlags_SizingStretchSame)) {
        for (int g = 0; g < 16; ++g) {
            ImGui::TableNextColumn();
            ImGui::PushID(g);
            bool on = (mask & static_cast<std::uint16_t>(1u << g)) != 0;
            const std::string label = std::to_string(g);
            if (ImGui::Checkbox(label.c_str(), &on)) {
                v.edit("修改碰撞掩码", [index, g, on](pmx::Model& m) {
                    const std::uint16_t bit = static_cast<std::uint16_t>(1u << g);
                    std::uint16_t& target = m.rigid[static_cast<std::size_t>(index)].mask;
                    target = on ? static_cast<std::uint16_t>(target | bit)
                                : static_cast<std::uint16_t>(target &
                                                             static_cast<std::uint16_t>(~bit));
                }, "physics", "rb.mask");
            }
            ImGui::PopID();
        }
        ImGui::EndTable();
    }
    ImGui::PopID();

    if (ImGui::Button("全选")) {
        v.edit("修改碰撞掩码", [index](pmx::Model& m) {
            m.rigid[static_cast<std::size_t>(index)].mask = 0xFFFF;
        }, "physics", "rb.mask");
    }
    ImGui::SameLine();
    if (ImGui::Button("清空")) {
        v.edit("修改碰撞掩码", [index](pmx::Model& m) {
            m.rigid[static_cast<std::size_t>(index)].mask = 0;
        }, "physics", "rb.mask");
    }
}

void draw_rigid_detail(Viewer& v, int index) {
    pmx::Model& model = v.model;
    pmx::RigidBody& rb = model.rigid[static_cast<std::size_t>(index)];

    ImGui::TextDisabled("索引 %d · %d 个刚体", index,
                        static_cast<int>(model.rigid.size()));

    ImGui::SeparatorText("基本");
    pmxui::name_fields(v, rb.name, rb.name_en, "rb", "physics", "重命名刚体");

    {
        int bone = rb.bone;
        if (bone_combo("关联骨骼", bone, model, "（未关联）") && bone != rb.bone)
            v.edit("修改刚体骨骼", [index, bone](pmx::Model& m) {
                m.rigid[static_cast<std::size_t>(index)].bone = bone;
            }, "physics", "rb.bone");
    }

    {
        int mode = std::clamp(static_cast<int>(rb.mode), 0, 2);
        ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
        if (ImGui::Combo("刚体模式", &mode, kRigidModes, IM_ARRAYSIZE(kRigidModes)))
            v.edit("修改刚体模式", [index, mode](pmx::Model& m) {
                m.rigid[static_cast<std::size_t>(index)].mode =
                    static_cast<std::uint8_t>(mode);
            }, "physics", "rb.mode");
    }

    ImGui::SeparatorText("形状与变换");
    {
        int shape = std::clamp(static_cast<int>(rb.shape), 0, 2);
        ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
        if (ImGui::Combo("形状", &shape, kShapes, IM_ARRAYSIZE(kShapes)))
            v.edit("修改刚体形状", [index, shape](pmx::Model& m) {
                m.rigid[static_cast<std::size_t>(index)].shape =
                    static_cast<std::uint8_t>(shape);
            }, "physics", "rb.shape");
    }
    pmxui::drag_vec3(v, "尺寸", rb.size, 0.01f, 0.0f, 9999.0f, "physics", "修改刚体尺寸",
                     "rb.size");
    ImGui::TextDisabled("%s", kSizeHints[std::clamp(static_cast<int>(rb.shape), 0, 2)]);

    pmxui::drag_vec3(v, "位置", rb.pos, 0.01f, 0.0f, 0.0f, "physics", "移动刚体", "rb.pos");
    pmxui::drag_angle3(v, "旋转", rb.rot, 1.0f, -360.0f, 360.0f, "physics", "旋转刚体",
                       "rb.rot");

    ImGui::SeparatorText("物理参数");
    pmxui::drag_float(v, "质量", rb.mass, 0.1f, 0.0f, 1000.0f, "physics_live", "修改质量",
                      "rb.mass");
    pmxui::drag_float(v, "移动衰减", rb.mov_damp, 0.01f, 0.0f, 1.0f, "physics",
                      "修改移动衰减", "rb.mdamp");
    pmxui::drag_float(v, "旋转衰减", rb.rot_damp, 0.01f, 0.0f, 1.0f, "physics",
                      "修改旋转衰减", "rb.rdamp");
    pmxui::drag_float(v, "反弹力", rb.repel, 0.01f, 0.0f, 1.0f, "physics", "修改反弹力",
                      "rb.repel");
    pmxui::drag_float(v, "摩擦力", rb.friction, 0.01f, 0.0f, 1.0f, "physics_live",
                      "修改摩擦力", "rb.friction");

    ImGui::SeparatorText("碰撞组");
    {
        int group = std::clamp(static_cast<int>(rb.group), 0, 15);
        ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
        if (ImGui::DragInt("所属组", &group, 0.2f, 0, 15))
            v.edit("修改刚体组", [index, group](pmx::Model& m) {
                m.rigid[static_cast<std::size_t>(index)].group =
                    static_cast<std::uint8_t>(group);
            }, "physics", "rb.group");
    }
    ImGui::TextDisabled("勾选可与本刚体碰撞的组");
    rigid_mask_grid(v, index, rb.mask);

    if (rb.mode == 0 && rb.mass > 0.0f)
        warning_text("骨骼跟随模式的刚体质量为 0，导出时可能被修正");
    if (rb.mode != 0 && rb.mass <= 0.0f)
        warning_text("物理演算刚体的质量为 0，Bullet 中不会运动");
}

void draw_joint_detail(Viewer& v, int index) {
    pmx::Model& model = v.model;
    pmx::Joint& jt = model.joints[static_cast<std::size_t>(index)];

    ImGui::TextDisabled("索引 %d · %d 个关节", index,
                        static_cast<int>(model.joints.size()));

    ImGui::SeparatorText("基本");
    pmxui::name_fields(v, jt.name, jt.name_en, "jt", "physics", "重命名关节");

    {
        int type = joint_type_index(jt);
        ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
        if (ImGui::Combo("类型", &type, kJointTypes, IM_ARRAYSIZE(kJointTypes)))
            v.edit("修改关节类型", [index, type](pmx::Model& m) {
                m.joints[static_cast<std::size_t>(index)].type =
                    static_cast<std::uint8_t>(type);
            }, "physics", "jt.type");
    }

    {
        int a = jt.rigid_a;
        if (rigid_combo("刚体 A", a, model, "（无）") && a != jt.rigid_a)
            v.edit("修改关节刚体 A", [index, a](pmx::Model& m) {
                m.joints[static_cast<std::size_t>(index)].rigid_a = a;
            }, "physics", "jt.a");
    }
    {
        int b = jt.rigid_b;
        if (rigid_combo("刚体 B", b, model, "（无）") && b != jt.rigid_b)
            v.edit("修改关节刚体 B", [index, b](pmx::Model& m) {
                m.joints[static_cast<std::size_t>(index)].rigid_b = b;
            }, "physics", "jt.b");
    }

    pmxui::drag_vec3(v, "位置", jt.pos, 0.01f, 0.0f, 0.0f, "physics", "移动关节", "jt.pos");
    pmxui::drag_angle3(v, "旋转", jt.rot, 1.0f, -360.0f, 360.0f, "physics", "旋转关节",
                       "jt.rot");

    ImGui::SeparatorText("移动限制");
    pmxui::drag_vec3(v, "移动最小", jt.min_loc, 0.01f, -9999.0f, 9999.0f, "physics",
                     "修改关节限制", "jt.limits");
    pmxui::drag_vec3(v, "移动最大", jt.max_loc, 0.01f, -9999.0f, 9999.0f, "physics",
                     "修改关节限制", "jt.limits");

    ImGui::SeparatorText("旋转限制");
    ImGui::TextDisabled("以角度显示；最小 > 最大 表示自由轴");
    pmxui::drag_angle3(v, "旋转最小", jt.min_rot, 1.0f, -360.0f, 360.0f, "physics",
                       "修改关节限制", "jt.limits");
    pmxui::drag_angle3(v, "旋转最大", jt.max_rot, 1.0f, -360.0f, 360.0f, "physics",
                       "修改关节限制", "jt.limits");

    ImGui::SeparatorText("弹簧");
    ImGui::TextDisabled("仅弹簧 6DOF 生效");
    pmxui::drag_vec3(v, "移动弹簧", jt.spring_loc, 0.1f, 0.0f, 999.0f, "physics",
                     "修改关节弹簧", "jt.spring");
    pmxui::drag_vec3(v, "旋转弹簧", jt.spring_rot, 0.1f, 0.0f, 999.0f, "physics",
                     "修改关节弹簧", "jt.spring");

    for (int axis = 0; axis < 3; ++axis) {
        const char ax = "XYZ"[axis];
        if (jt.min_rot[axis] > jt.max_rot[axis]) {
            char text[96];
            std::snprintf(text, sizeof text, "%c 轴旋转 min > max：自由轴（MMD 中不限制）", ax);
            warning_text(text);
        }
        if (jt.min_loc[axis] > jt.max_loc[axis]) {
            char text[96];
            std::snprintf(text, sizeof text, "%c 轴移动 min > max：自由轴（MMD 中不限制）", ax);
            warning_text(text);
        }
    }
}

}  // namespace

void panel_physics(Viewer& v) {
    if (!v.pose) {
        ImGui::TextDisabled("未加载模型");
        return;
    }
    pmx::Model& model = v.model;
    const int rigid_count = static_cast<int>(model.rigid.size());
    const int joint_count = static_cast<int>(model.joints.size());

    // 选中越界（撤销后数量变少）时清空选择。
    if (v.sel.kind == SelKind::Rigid && (v.sel.index < 0 || v.sel.index >= rigid_count))
        v.select(SelKind::None, -1);
    if (v.sel.kind == SelKind::Joint && (v.sel.index < 0 || v.sel.index >= joint_count))
        v.select(SelKind::None, -1);

    // 0 = 刚体，1 = 关节；外部选中时同步切换。
    static int kind = 0;
    if (v.sel.kind == SelKind::Rigid) kind = 0;
    else if (v.sel.kind == SelKind::Joint) kind = 1;

    // ------------------------------------------------------------ 类型切换
    if (ImGui::RadioButton("刚体", kind == 0) && kind != 0) {
        kind = 0;
        if (!model.rigid.empty()) v.select(SelKind::Rigid, 0);
        else v.select(SelKind::None, -1);
    }
    ImGui::SameLine();
    if (ImGui::RadioButton("关节", kind == 1) && kind != 1) {
        kind = 1;
        if (!model.joints.empty()) v.select(SelKind::Joint, 0);
        else v.select(SelKind::None, -1);
    }

    const int count = kind == 0 ? rigid_count : joint_count;
    int idx = kind == 0 ? (v.sel.kind == SelKind::Rigid ? v.sel.index : -1)
                        : (v.sel.kind == SelKind::Joint ? v.sel.index : -1);
    if (idx < 0 || idx >= count) idx = -1;

    // ------------------------------------------------------------ 工具
    static int pending_delete = -1;
    static int pending_kind = 0;

    if (ImGui::Button(kind == 0 ? "新建刚体" : "新建关节")) {
        v.push_undo(kind == 0 ? "新建刚体" : "新建关节");
        if (kind == 0) {
            // 刚体默认关联当前选中的骨骼。
            const bool bone_selected =
                v.sel.kind == SelKind::Bone && v.sel.index >= 0 &&
                v.sel.index < static_cast<int>(model.bones.size());
            const int bone = bone_selected ? v.sel.index : -1;
            const int created = pmxdoc::add_rigid(model, bone);
            v.clamp_selection();
            if (created >= 0) v.select(SelKind::Rigid, created);
            else v.select(SelKind::None, -1);
        } else {
            const int created = pmxdoc::add_joint(model);
            v.clamp_selection();
            if (created >= 0) v.select(SelKind::Joint, created);
            else v.select(SelKind::None, -1);
        }
        v.touched("structure");
        return;
    }
    ImGui::SetItemTooltip(kind == 0 ? "新建刚体（关联当前选中骨骼）" : "新建关节");

    ImGui::SameLine();
    ImGui::BeginDisabled(idx < 0);
    if (ImGui::Button("复制")) {
        v.push_undo("复制物理项目");
        const int copy = kind == 0 ? pmxdoc::duplicate_rigid(model, idx)
                                   : pmxdoc::duplicate_joint(model, idx);
        v.clamp_selection();
        if (copy >= 0) v.select(kind == 0 ? SelKind::Rigid : SelKind::Joint, copy);
        else v.select(SelKind::None, -1);
        v.touched("structure");
        return;
    }
    ImGui::SetItemTooltip("复制当前项目");
    ImGui::SameLine();
    if (ImGui::Button("删除")) {
        pending_delete = idx;
        pending_kind = kind;
        ImGui::OpenPopup("删除物理项目##physics");
    }
    ImGui::SetItemTooltip("删除当前项目");
    ImGui::EndDisabled();

    // ------------------------------------------------------------ 搜索 + 列表
    static char filter[128] = "";
    ImGui::SetNextItemWidth(-1.0f);
    ImGui::InputTextWithHint("##physics_search", "搜索名称 / 关联骨骼", filter, sizeof filter);

    ImGui::BeginChild("##physics_list", ImVec2(0, pmxui::scale(200.0f)), ImGuiChildFlags_Borders);
    std::vector<int> visible;
    visible.reserve(static_cast<std::size_t>(count));
    if (kind == 0) {
        for (int i = 0; i < rigid_count; ++i) {
            const pmx::RigidBody& rb = model.rigid[static_cast<std::size_t>(i)];
            bool match = pmxui::match_filter(filter, rb.name, rb.name_en);
            if (!match && rb.bone >= 0 && rb.bone < static_cast<int>(model.bones.size()))
                match = pmxui::match_filter(
                    filter, model.bones[static_cast<std::size_t>(rb.bone)].name, std::string());
            if (match) visible.push_back(i);
        }
    } else {
        for (int i = 0; i < joint_count; ++i) {
            const pmx::Joint& jt = model.joints[static_cast<std::size_t>(i)];
            if (pmxui::match_filter(filter, jt.name, jt.name_en)) visible.push_back(i);
        }
    }

    if (count == 0) {
        ImGui::TextDisabled("%s", kind == 0 ? "尚无刚体（点击上方新建）"
                                            : "尚无关节（点击上方新建）");
    } else if (visible.empty()) {
        ImGui::TextDisabled("%s", kind == 0 ? "没有匹配的刚体" : "没有匹配的关节");
    } else {
        ImGuiListClipper clipper;
        clipper.Begin(static_cast<int>(visible.size()));
        while (clipper.Step()) {
            for (int k = clipper.DisplayStart; k < clipper.DisplayEnd; ++k) {
                const int i = visible[static_cast<std::size_t>(k)];
                std::string row;
                if (kind == 0) {
                    const pmx::RigidBody& rb = model.rigid[static_cast<std::size_t>(i)];
                    row = rigid_item_text(model, i);
                    row += "   · 骨骼 ";
                    if (rb.bone >= 0 && rb.bone < static_cast<int>(model.bones.size())) {
                        const pmx::Bone& bone =
                            model.bones[static_cast<std::size_t>(rb.bone)];
                        row += bone.name.empty() ? "未命名" : bone.name.c_str();
                    } else {
                        row += "未关联";
                    }
                    row += " · 组 " + std::to_string(static_cast<int>(rb.group));
                    row += "##rb_row" + std::to_string(i);
                } else {
                    const pmx::Joint& jt = model.joints[static_cast<std::size_t>(i)];
                    row = joint_item_text(model, i);
                    row += "   · ";
                    row += kJointNames[joint_type_index(jt)];
                    row += "   " + std::to_string(jt.rigid_a) + " → " +
                           std::to_string(jt.rigid_b);
                    row += "##jt_row" + std::to_string(i);
                }
                if (ImGui::Selectable(row.c_str(), i == idx)) {
                    v.select(kind == 0 ? SelKind::Rigid : SelKind::Joint, i);
                    idx = i;
                }
            }
        }
    }
    ImGui::EndChild();

    if (idx >= 0) {
        ImGui::BeginChild("##physics_detail", ImVec2(0, 0));
        if (kind == 0) draw_rigid_detail(v, idx);
        else draw_joint_detail(v, idx);
        ImGui::EndChild();
    } else {
        ImGui::TextDisabled("%s", kind == 0 ? "未选择刚体（点击上方列表选择）"
                                            : "未选择关节（点击上方列表选择）");
    }

    // ------------------------------------------------------------ 删除确认
    int remove_index = -1;
    int remove_kind = 0;
    if (ImGui::BeginPopupModal("删除物理项目##physics", nullptr,
                               ImGuiWindowFlags_AlwaysAutoResize)) {
        const int limit = pending_kind == 0 ? rigid_count : joint_count;
        const bool valid = pending_delete >= 0 && pending_delete < limit;
        if (!valid) {
            ImGui::TextDisabled("项目已不存在");
            if (ImGui::Button("关闭")) {
                pending_delete = -1;
                ImGui::CloseCurrentPopup();
            }
        } else {
            const std::string name =
                pending_kind == 0
                    ? model.rigid[static_cast<std::size_t>(pending_delete)].name
                    : model.joints[static_cast<std::size_t>(pending_delete)].name;
            ImGui::Text("确定删除「%s」？", name.empty() ? "未命名" : name.c_str());
            if (pending_kind == 0)
                ImGui::TextDisabled("引用该刚体的关节与柔体锚点会一并清理。");
            if (ImGui::Button("删除")) {
                remove_index = pending_delete;
                remove_kind = pending_kind;
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
        v.push_undo(remove_kind == 0 ? "删除刚体" : "删除关节");
        const int next = remove_kind == 0 ? pmxdoc::remove_rigid(model, remove_index)
                                          : pmxdoc::remove_joint(model, remove_index);
        v.clamp_selection();
        if (next >= 0)
            v.select(remove_kind == 0 ? SelKind::Rigid : SelKind::Joint, next);
        else
            v.select(SelKind::None, -1);
        v.touched("structure");
        return;
    }
}
