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

constexpr float kRadToDeg = 57.29577951308232f;
constexpr float kDegToRad = 0.017453292519943295f;

void set_bone_flag(pmx::Bone& bone, std::uint16_t flag, bool on) {
    if (on) bone.flags = static_cast<std::uint16_t>(bone.flags | flag);
    else bone.flags = static_cast<std::uint16_t>(bone.flags & ~flag);
}

std::string bone_item_label(const pmx::Model& model, int i) {
    char prefix[24];
    std::snprintf(prefix, sizeof prefix, "%03d · ", i);
    std::string text(prefix);
    const std::string label =
        pmxui::base_name(model.bones[i].name, model.bones[i].name_en);
    text += label.empty() ? "未命名" : label;
    return text;
}

std::string bone_item_text(const pmx::Model& model, int i) {
    char prefix[24];
    std::snprintf(prefix, sizeof prefix, "%03d · ", i);
    std::string text(prefix);
    const std::string label = pmx::name_with_zh(pmx::NameKind::Bone, model.bones[i].name,
                                                model.bones[i].name_en);
    text += label.empty() ? "未命名" : label;
    return text;
}

// 骨骼下拉：value 只是临时选择值，返回 true 表示用户换了选项。
bool bone_combo(const char* label, int& value, const pmx::Model& model, int none_value,
                const char* none_text) {
    const int n = static_cast<int>(model.bones.size());
    std::string preview;
    if (value >= 0 && value < n) preview = bone_item_text(model, value);
    else preview = none_text;

    bool changed = false;
    ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
    if (ImGui::BeginCombo(label, preview.c_str())) {
        if (ImGui::Selectable(none_text, value == none_value)) {
            value = none_value;
            changed = true;
        }
        for (int i = 0; i < n; ++i) {
            std::string text = bone_item_text(model, i) + "##bone" + std::to_string(i);
            if (ImGui::Selectable(text.c_str(), value == i)) {
                value = i;
                changed = true;
            }
        }
        ImGui::EndCombo();
    }
    return changed;
}

bool flag_checkbox(Viewer& v, int index, std::uint16_t flag, const char* text) {
    bool on = (v.model.bones[index].flags & flag) != 0;
    if (!ImGui::Checkbox(text, &on)) return false;
    v.edit("修改骨骼标志", [index, flag, on](pmx::Model& m) {
        set_bone_flag(m.bones[index], flag, on);
    }, "bone");
    return true;
}

// 设置 parent 后是否会形成环路（与 Python _cycle 一致）。
bool bone_cycle(const pmx::Model& model, int start, int parent) {
    std::vector<bool> seen(model.bones.size(), false);
    int cur = parent;
    while (cur >= 0 && cur < static_cast<int>(model.bones.size())) {
        if (cur == start || seen[cur]) return true;
        seen[cur] = true;
        cur = model.bones[cur].parent;
    }
    return false;
}

// 度数显示、弧度存储的三分量拖动：先改临时值，确认变化后才压快照写回。
bool drag_angle_vec3(Viewer& v, const char* id, pmx::Vec3& value, float lo_deg, float hi_deg,
                     const char* label, const char* coalesce) {
    float tmp[3] = {value.x * kRadToDeg, value.y * kRadToDeg, value.z * kRadToDeg};
    ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
    if (!ImGui::DragFloat3(id, tmp, 1.0f, lo_deg, hi_deg, "%.1f°")) return false;
    const pmx::Vec3 next{tmp[0] * kDegToRad, tmp[1] * kDegToRad, tmp[2] * kDegToRad};
    v.edit(label, [&value, next](pmx::Model&) { value = next; }, "bone", coalesce);
    return true;
}

}  // namespace

void panel_bone(Viewer& v) {
    pmx::Model& model = v.model;
    if (!v.pose) {
        ImGui::TextDisabled("未加载模型");
        return;
    }
    const int bone_count = static_cast<int>(model.bones.size());

    // 选中越界（例如撤销后骨骼变少）时清空选择。
    if (v.sel.kind == SelKind::Bone && (v.sel.index < 0 || v.sel.index >= bone_count))
        v.select(SelKind::None, -1);
    int idx = v.sel.kind == SelKind::Bone ? v.sel.index : -1;

    // ------------------------------------------------------------ 工具
    if (ImGui::Button("新建骨骼")) {
        v.push_undo("新建骨骼");
        const int created = pmxdoc::add_bone(model, idx);
        v.clamp_selection();
        v.select(SelKind::Bone, created);
        v.touched("structure");
        return;
    }
    ImGui::SetItemTooltip("新建骨骼（作为当前骨骼的子级）");
    ImGui::SameLine();
    bool copy_bone = false;
    bool remove_bone = false;
    ImGui::BeginDisabled(idx < 0);
    if (ImGui::Button("复制")) copy_bone = true;
    ImGui::EndDisabled();
    ImGui::SetItemTooltip("复制当前骨骼");
    ImGui::SameLine();
    ImGui::BeginDisabled(idx < 0);
    if (ImGui::Button("删除")) remove_bone = true;
    ImGui::EndDisabled();
    ImGui::SetItemTooltip("删除当前骨骼");

    if (copy_bone) {
        v.push_undo("复制骨骼");
        const int copy = pmxdoc::duplicate_bone(model, idx);
        v.clamp_selection();
        if (copy >= 0) v.select(SelKind::Bone, copy);
        else v.select(SelKind::None, -1);
        v.touched("structure");
        return;
    }
    if (remove_bone) {
        v.push_undo("删除骨骼");
        const int next = pmxdoc::remove_bone(model, idx);
        v.clamp_selection();
        if (next >= 0) v.select(SelKind::Bone, next);
        else v.select(SelKind::None, -1);
        v.touched("structure");
        return;
    }

    // ------------------------------------------------------------ 搜索 + 列表
    static char filter[128] = "";
    ImGui::SetNextItemWidth(-1.0f);
    ImGui::InputTextWithHint("##bone_search", "搜索骨骼名 / 中文 / 英文名", filter,
                             sizeof filter);

    ImGui::BeginChild("##bone_list", ImVec2(0, pmxui::scale(200.0f)), ImGuiChildFlags_Borders);
    std::vector<int> visible;
    visible.reserve(model.bones.size());
    for (int i = 0; i < bone_count; ++i) {
        const pmx::Bone& b = model.bones[i];
        if (pmxui::match_filter(filter, b.name, b.name_en,
                                pmx::name_zh(pmx::NameKind::Bone, b.name, b.name_en)))
            visible.push_back(i);
    }

    if (visible.empty()) {
        ImGui::TextDisabled("没有匹配的骨骼");
    } else {
        ImGuiListClipper clipper;
        clipper.Begin(static_cast<int>(visible.size()));
        while (clipper.Step()) {
            for (int k = clipper.DisplayStart; k < clipper.DisplayEnd; ++k) {
                const int i = visible[k];
                int depth = 0;
                for (int p = model.bones[i].parent;
                     p >= 0 && p < bone_count && depth < 12; p = model.bones[p].parent)
                    ++depth;
                std::string text(depth * 2, ' ');
                text += bone_item_label(model, i);
                const std::string zh =
                    pmxui::zh_only(pmx::NameKind::Bone, model.bones[i].name,
                                   model.bones[i].name_en);
                const std::string row_id = "bone_row" + std::to_string(i);
                if (pmxui::zh_row(row_id.c_str(), text, zh, i == idx)) {
                    v.select(SelKind::Bone, i);
                    idx = i;
                }
                // 视口双击选中的骨骼可能在列表可视区外，滚到中间。
                if (v.reveal_selection && i == idx) ImGui::SetScrollHereY(0.5f);
            }
        }
    }
    ImGui::EndChild();

    if (idx < 0 || idx >= bone_count) {
        ImGui::TextDisabled("未选择骨骼（点击上方列表选择）");
        return;
    }

    pmx::Bone& b = model.bones[idx];
    static bool move_verts = false;
    ImGui::TextDisabled("索引 %d · %d 根骨骼", idx, bone_count);

    ImGui::BeginChild("##bone_detail", ImVec2(0, 0));

    // ------------------------------------------------------------ 基本
    ImGui::SeparatorText("基本");
    pmxui::name_fields(v, b.name, b.name_en, "bone", "bone", "重命名骨骼");
    pmxui::zh_line(pmx::NameKind::Bone, b.name, b.name_en);

    {
        float pos[3] = {b.pos.x, b.pos.y, b.pos.z};
        ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
        if (ImGui::DragFloat3("位置", pos, 0.01f, 0.0f, 0.0f, "%.3f")) {
            const pmx::Vec3 next{pos[0], pos[1], pos[2]};
            const int target = idx;
            const bool shift_vertices = move_verts;
            v.edit(move_verts ? "移动骨骼并带动顶点" : "移动骨骼",
                   [target, next, shift_vertices](pmx::Model& m) {
                       pmx::Bone& bb = m.bones[target];
                       const pmx::Vec3 delta = next - bb.pos;
                       bb.pos = next;
                       if (shift_vertices &&
                           (delta.x != 0.0f || delta.y != 0.0f || delta.z != 0.0f))
                           pmx::shift_bone_vertices(m, target, delta);
                   },
                   "bone", "bone.pos");
        }
    }
    ImGui::Checkbox("移动时带动顶点", &move_verts);
    ImGui::SetItemTooltip("开启后修改位置会按蒙皮权重把位移写进顶点（原版 PmxEditor 不会这样）");

    {
        int parent = b.parent;
        if (bone_combo("父骨骼", parent, model, -1, "（无 · 根骨骼）")) {
            if (parent < 0 || !bone_cycle(model, idx, parent))
                v.edit("修改父骨骼", [idx, parent](pmx::Model& m) {
                    m.bones[idx].parent = parent;
                }, "bone");
            else
                v.status = "不能设置形成环路的父骨骼";
        }
    }

    {
        int layer = b.layer;
        ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
        if (ImGui::DragInt("变形层级", &layer, 0.2f, 0, 31))
            v.edit("修改变形层级", [idx, layer](pmx::Model& m) {
                m.bones[idx].layer = layer;
            }, "bone", "bone.layer");
    }

    {
        int move_delta = 0;
        ImGui::BeginDisabled(idx <= 0);
        if (ImGui::Button("上移")) move_delta = -1;
        ImGui::EndDisabled();
        ImGui::SetItemTooltip("在骨骼列表里上移一位（会重映射所有引用）");
        ImGui::SameLine();
        ImGui::BeginDisabled(idx + 1 >= bone_count);
        if (ImGui::Button("下移")) move_delta = 1;
        ImGui::EndDisabled();
        ImGui::SetItemTooltip("在骨骼列表里下移一位（会重映射所有引用）");
        if (move_delta != 0) {
            v.push_undo("调整骨骼顺序");
            const int moved = pmxdoc::move_bone(model, idx, move_delta);
            v.clamp_selection();
            v.select(SelKind::Bone, moved);
            v.touched("structure");
            ImGui::EndChild();
            return;
        }
    }

    // ------------------------------------------------------------ 连接与显示
    ImGui::SeparatorText("连接与显示");
    bool tail_is_bone = (b.flags & pmx::BF_TAIL_INDEX) != 0;
    if (ImGui::RadioButton("坐标偏移", !tail_is_bone) && tail_is_bone) {
        v.edit("修改连接方式", [idx](pmx::Model& m) {
            set_bone_flag(m.bones[idx], pmx::BF_TAIL_INDEX, false);
        }, "bone");
        tail_is_bone = false;
    }
    ImGui::SameLine();
    if (ImGui::RadioButton("骨骼", tail_is_bone) && !tail_is_bone) {
        v.edit("修改连接方式", [idx](pmx::Model& m) {
            set_bone_flag(m.bones[idx], pmx::BF_TAIL_INDEX, true);
        }, "bone");
        tail_is_bone = true;
    }

    if (tail_is_bone) {
        int tail = b.tail_bone;
        if (bone_combo("尾端骨骼", tail, model, -1, "（无）") && tail >= 0)
            v.edit("修改尾端骨骼", [idx, tail](pmx::Model& m) {
                m.bones[idx].tail_bone = tail;
            }, "bone");
    } else {
        pmxui::drag_vec3(v, "尾端偏移", b.tail_offset, 0.01f, 0.0f, 0.0f, "bone",
                         "修改尾端偏移", "bone.tail");
    }

    {
        struct FlagDef {
            const char* text;
            std::uint16_t flag;
        };
        static const FlagDef kFlags[] = {
            {"可旋转", pmx::BF_ROTATABLE},
            {"可移动", pmx::BF_TRANSLATABLE},
            {"显示", pmx::BF_VISIBLE},
            {"可操作", pmx::BF_ENABLED},
            {"物理后变形", pmx::BF_AFTER_PHYSICS},
            {"本地付与", pmx::BF_LOCAL_APPEND},
        };
        if (ImGui::BeginTable("##bone_flags", 2, ImGuiTableFlags_SizingStretchSame)) {
            for (const FlagDef& f : kFlags) {
                ImGui::TableNextColumn();
                flag_checkbox(v, idx, f.flag, f.text);
            }
            ImGui::EndTable();
        }
    }

    // ------------------------------------------------------------ 付与
    ImGui::SeparatorText("付与");
    const bool inherit_on =
        (b.flags & (pmx::BF_INHERIT_ROT | pmx::BF_INHERIT_MOV)) != 0;
    ImGui::BeginDisabled(!inherit_on);
    {
        int append_parent = b.append_parent;
        if (bone_combo("付与父级", append_parent, model, -1, "（父骨骼）"))
            v.edit("修改付与父级", [idx, append_parent](pmx::Model& m) {
                m.bones[idx].append_parent = append_parent;
            }, "bone");

        float ratio = b.append_ratio;
        ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
        if (ImGui::DragFloat("付与率", &ratio, 0.01f, -10.0f, 10.0f, "%.3f"))
            v.edit("修改付与率", [idx, ratio](pmx::Model& m) {
                m.bones[idx].append_ratio = ratio;
            }, "bone", "bone.ratio");
    }
    ImGui::EndDisabled();

    {
        bool inherit_rot = (b.flags & pmx::BF_INHERIT_ROT) != 0;
        bool inherit_mov = (b.flags & pmx::BF_INHERIT_MOV) != 0;
        if (ImGui::Checkbox("旋转付与", &inherit_rot))
            v.edit("修改付与标志", [idx, inherit_rot](pmx::Model& m) {
                set_bone_flag(m.bones[idx], pmx::BF_INHERIT_ROT, inherit_rot);
            }, "bone");
        ImGui::SameLine();
        if (ImGui::Checkbox("移动付与", &inherit_mov))
            v.edit("修改付与标志", [idx, inherit_mov](pmx::Model& m) {
                set_bone_flag(m.bones[idx], pmx::BF_INHERIT_MOV, inherit_mov);
            }, "bone");

        bool external = (b.flags & pmx::BF_EXTERNAL_PARENT) != 0;
        if (ImGui::Checkbox("外部父级", &external))
            v.edit("修改外部父级标志", [idx, external](pmx::Model& m) {
                set_bone_flag(m.bones[idx], pmx::BF_EXTERNAL_PARENT, external);
            }, "bone");
    }

    // ------------------------------------------------------------ 轴固定 / 局部轴
    ImGui::SeparatorText("轴固定 / 局部轴");
    {
        bool fixed_axis = (b.flags & pmx::BF_FIXED_AXIS) != 0;
        if (ImGui::Checkbox("轴固定", &fixed_axis))
            v.edit("修改轴标志", [idx, fixed_axis](pmx::Model& m) {
                set_bone_flag(m.bones[idx], pmx::BF_FIXED_AXIS, fixed_axis);
            }, "bone");
        ImGui::BeginDisabled(!fixed_axis);
        pmxui::drag_vec3(v, "轴方向", b.axis, 0.01f, 0.0f, 0.0f, "bone", "修改固定轴",
                         "bone.axis");
        ImGui::EndDisabled();

        bool local_axis = (b.flags & pmx::BF_LOCAL_AXIS) != 0;
        if (ImGui::Checkbox("局部轴", &local_axis))
            v.edit("修改轴标志", [idx, local_axis](pmx::Model& m) {
                set_bone_flag(m.bones[idx], pmx::BF_LOCAL_AXIS, local_axis);
            }, "bone");
        ImGui::BeginDisabled(!local_axis);
        pmxui::drag_vec3(v, "X 轴", b.local_x, 0.01f, 0.0f, 0.0f, "bone", "修改局部 X 轴",
                         "bone.localx");
        pmxui::drag_vec3(v, "Z 轴", b.local_z, 0.01f, 0.0f, 0.0f, "bone", "修改局部 Z 轴",
                         "bone.localz");
        ImGui::EndDisabled();
    }

    // ------------------------------------------------------------ IK
    ImGui::SeparatorText("IK");
    {
        bool ik_on = b.ik.has_value();
        if (ImGui::Checkbox("启用 IK", &ik_on)) {
            v.edit("切换 IK", [idx, ik_on](pmx::Model& m) {
                pmx::Bone& bb = m.bones[idx];
                if (ik_on) {
                    bb.flags = static_cast<std::uint16_t>(bb.flags | pmx::BF_IK);
                    pmx::IK ik;
                    ik.target = -1;
                    ik.loop = 0;
                    ik.angle = 1.0f;
                    bb.ik = ik;
                } else {
                    bb.flags = static_cast<std::uint16_t>(bb.flags & ~pmx::BF_IK);
                    bb.ik.reset();
                }
            }, "bone", "bone.ik");
        }
    }

    if (b.ik) {
        {
            int target = b.ik->target;
            if (bone_combo("目标骨骼", target, model, -1, "（无）"))
                v.edit("修改 IK 目标", [idx, target](pmx::Model& m) {
                    m.bones[idx].ik->target = target;
                }, "bone");
        }
        {
            int loop = b.ik->loop;
            ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
            if (ImGui::DragInt("循环次数", &loop, 0.2f, 0, 255))
                v.edit("修改 IK 循环", [idx, loop](pmx::Model& m) {
                    m.bones[idx].ik->loop = loop;
                }, "bone", "bone.ikloop");
        }
        {
            float deg = b.ik->angle * kRadToDeg;
            ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
            if (ImGui::DragFloat("单次角度", &deg, 0.5f, 0.0f, 180.0f, "%.1f°"))
                v.edit("修改 IK 单次角度", [idx, deg](pmx::Model& m) {
                    m.bones[idx].ik->angle = deg * kDegToRad;
                }, "bone", "bone.ikangle");
        }

        static int link_row = -1;
        static int link_owner = -2;
        if (link_owner != idx) {
            link_owner = idx;
            link_row = b.ik->links.empty() ? -1 : 0;
        }
        const int link_count = static_cast<int>(b.ik->links.size());
        if (link_count == 0) link_row = -1;
        else link_row = std::clamp(link_row, 0, link_count - 1);

        ImGui::BeginChild("##ik_links", ImVec2(0, pmxui::scale(84.0f)), ImGuiChildFlags_Borders);
        for (int i = 0; i < link_count; ++i) {
            const pmx::IKLink& link = b.ik->links[i];
            std::string name = "?";
            if (link.bone >= 0 && link.bone < bone_count) {
                const pmx::Bone& lb = model.bones[link.bone];
                name = pmx::name_with_zh(pmx::NameKind::Bone, lb.name, lb.name_en);
                if (name.empty()) name = "未命名";
            }
            char range[160];
            if (link.limited) {
                std::snprintf(range, sizeof range,
                              "  X[%.0f,%.0f] Y[%.0f,%.0f] Z[%.0f,%.0f]",
                              link.lo.x * kRadToDeg, link.hi.x * kRadToDeg,
                              link.lo.y * kRadToDeg, link.hi.y * kRadToDeg,
                              link.lo.z * kRadToDeg, link.hi.z * kRadToDeg);
            } else {
                std::snprintf(range, sizeof range, "  · 无限制");
            }
            std::string text = "· " + name + range + "##ik_link" + std::to_string(i);
            if (ImGui::Selectable(text.c_str(), i == link_row)) link_row = i;
        }
        if (link_count == 0) ImGui::TextDisabled("暂无链接");
        ImGui::EndChild();

        std::vector<bool> used(model.bones.size(), false);
        for (const pmx::IKLink& link : b.ik->links)
            if (link.bone >= 0 && link.bone < bone_count) used[link.bone] = true;
        std::vector<int> available;
        for (int i = 0; i < bone_count; ++i)
            if (!used[i]) available.push_back(i);

        static int add_link_bone = -1;
        if (!available.empty() &&
            std::find(available.begin(), available.end(), add_link_bone) == available.end())
            add_link_bone = available.front();
        const bool can_add = !available.empty();

        ImGui::BeginDisabled(!can_add);
        std::string preview = can_add ? bone_item_text(model, add_link_bone) : "（无可选骨骼）";
        ImGui::SetNextItemWidth(
            std::max(pmxui::scale(60.0f), ImGui::GetContentRegionAvail().x - pmxui::scale(150.0f)));
        if (ImGui::BeginCombo("##ik_link_pick", preview.c_str())) {
            for (int i : available) {
                std::string text = bone_item_text(model, i) + "##ik_pick" + std::to_string(i);
                if (ImGui::Selectable(text.c_str(), i == add_link_bone)) add_link_bone = i;
            }
            ImGui::EndCombo();
        }
        ImGui::EndDisabled();

        ImGui::SameLine();
        ImGui::BeginDisabled(!can_add);
        if (ImGui::Button("添加链接")) {
            const int link_bone = add_link_bone;
            v.edit("添加 IK 链接", [idx, link_bone](pmx::Model& m) {
                pmx::Bone& bb = m.bones[idx];
                if (!bb.ik) {
                    bb.flags = static_cast<std::uint16_t>(bb.flags | pmx::BF_IK);
                    pmx::IK ik;
                    ik.target = -1;
                    ik.loop = 0;
                    ik.angle = 1.0f;
                    bb.ik = ik;
                }
                pmx::IKLink link;
                link.bone = link_bone;
                bb.ik->links.push_back(link);
            }, "bone");
            link_row = static_cast<int>(b.ik->links.size()) - 1;
        }
        ImGui::EndDisabled();

        ImGui::SameLine();
        ImGui::BeginDisabled(link_row < 0);
        if (ImGui::Button("移除")) {
            const int row = link_row;
            v.edit("移除 IK 链接", [idx, row](pmx::Model& m) {
                auto& links = m.bones[idx].ik->links;
                if (row >= 0 && row < static_cast<int>(links.size()))
                    links.erase(links.begin() + row);
            }, "bone");
            link_row = static_cast<int>(b.ik->links.size()) - 1;
        }
        ImGui::EndDisabled();

        if (link_row >= 0 && link_row < static_cast<int>(b.ik->links.size())) {
            pmx::IKLink& link = b.ik->links[link_row];
            bool limited = link.limited;
            if (ImGui::Checkbox("角度限制", &limited)) {
                const int row = link_row;
                v.edit("修改 IK 角度限制", [idx, row, limited](pmx::Model& m) {
                    m.bones[idx].ik->links[row].limited = limited;
                }, "bone", "bone.iklimit");
            }
            drag_angle_vec3(v, "最小", link.lo, -180.0f, 180.0f, "修改 IK 角度范围",
                            "bone.ikrange");
            drag_angle_vec3(v, "最大", link.hi, -180.0f, 180.0f, "修改 IK 角度范围",
                            "bone.ikrange");
        }
    }

    // ------------------------------------------------------------ 撤销 / 重做 / 姿态
    ImGui::Separator();
    bool undo_now = false;
    bool redo_now = false;
    if (ImGui::Button("重置姿态")) v.reset_pose();
    ImGui::SameLine();
    ImGui::BeginDisabled(!v.can_undo());
    if (ImGui::Button("撤销")) undo_now = true;
    ImGui::EndDisabled();
    ImGui::SameLine();
    ImGui::BeginDisabled(!v.can_redo());
    if (ImGui::Button("重做")) redo_now = true;
    ImGui::EndDisabled();

    // 撤销/重做会整体替换模型，之后不能在引用骨骼。
    if (undo_now) v.undo();
    else if (redo_now) v.redo();

    ImGui::EndChild();
}
