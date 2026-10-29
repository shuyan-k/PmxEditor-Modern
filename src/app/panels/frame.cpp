#include "app/panels.hpp"

#include <algorithm>
#include <cstdio>
#include <string>
#include <vector>

#include <imgui.h>

#include "app/document_ops.hpp"
#include "app/panels/common.hpp"

namespace {

std::string bone_entry_text(const pmx::Model& model, int i) {
    char prefix[24];
    std::snprintf(prefix, sizeof prefix, "%03d · ", i);
    std::string text(prefix);
    const std::string label =
        pmx::name_with_zh(pmx::NameKind::Bone, model.bones[i].name, model.bones[i].name_en);
    text += label.empty() ? "未命名" : label;
    return text;
}

std::string morph_entry_text(const pmx::Model& model, int i) {
    char prefix[24];
    std::snprintf(prefix, sizeof prefix, "%03d · ", i);
    std::string text(prefix);
    const std::string label =
        pmx::name_with_zh(pmx::NameKind::Morph, model.morphs[i].name, model.morphs[i].name_en);
    text += label.empty() ? "未命名" : label;
    return text;
}

// 项目列表里的显示文本：类型 0 骨骼 / 1 形态。
std::string frame_item_text(const pmx::Model& model, const pmx::DisplayFrameItem& item) {
    if (item.type == 0) {
        std::string name = "?";
        if (item.index >= 0 && item.index < static_cast<int>(model.bones.size())) {
            const pmx::Bone& bone = model.bones[item.index];
            name = pmx::name_with_zh(pmx::NameKind::Bone, bone.name, bone.name_en);
            if (name.empty()) name = "未命名";
        }
        return "骨骼 · " + name;
    }
    std::string name = "?";
    if (item.index >= 0 && item.index < static_cast<int>(model.morphs.size())) {
        const pmx::Morph& morph = model.morphs[item.index];
        name = pmx::name_with_zh(pmx::NameKind::Morph, morph.name, morph.name_en);
        if (name.empty()) name = "未命名";
    }
    return "形态 · " + name;
}

}  // namespace

void panel_frame(Viewer& v) {
    pmx::Model& model = v.model;
    if (!v.pose) {
        ImGui::TextDisabled("未加载模型");
        return;
    }
    const int frame_count = static_cast<int>(model.frames.size());

    // 选中越界（例如撤销后表示枠变少）时清空选择。
    if (v.sel.kind == SelKind::Frame && (v.sel.index < 0 || v.sel.index >= frame_count))
        v.select(SelKind::None, -1);
    int idx = v.sel.kind == SelKind::Frame ? v.sel.index : -1;

    // ------------------------------------------------------------ 工具
    if (ImGui::Button("新建表示枠")) {
        v.push_undo("新建表示枠");
        const int created = pmxdoc::add_frame(model);
        v.clamp_selection();
        v.select(SelKind::Frame, created);
        v.touched("model");
        return;
    }
    ImGui::SetItemTooltip("新建表示枠");
    ImGui::SameLine();
    bool copy_frame = false;
    bool remove_frame = false;
    ImGui::BeginDisabled(idx < 0);
    if (ImGui::Button("复制")) copy_frame = true;
    ImGui::EndDisabled();
    ImGui::SetItemTooltip("复制表示枠");
    ImGui::SameLine();
    ImGui::BeginDisabled(idx < 0);
    if (ImGui::Button("删除")) remove_frame = true;
    ImGui::EndDisabled();
    ImGui::SetItemTooltip("删除表示枠");

    if (copy_frame) {
        v.push_undo("复制表示枠");
        const int copy = pmxdoc::duplicate_frame(model, idx);
        v.clamp_selection();
        if (copy >= 0) v.select(SelKind::Frame, copy);
        else v.select(SelKind::None, -1);
        v.touched("model");
        return;
    }
    if (remove_frame) {
        v.push_undo("删除表示枠");
        const int next = pmxdoc::remove_frame(model, idx);
        v.clamp_selection();
        if (next >= 0) v.select(SelKind::Frame, next);
        else v.select(SelKind::None, -1);
        v.touched("model");
        return;
    }

    // ------------------------------------------------------------ 搜索 + 列表
    static char filter[128] = "";
    ImGui::SetNextItemWidth(-1.0f);
    ImGui::InputTextWithHint("##frame_search", "搜索表示枠名 / 中文", filter, sizeof filter);

    ImGui::BeginChild("##frame_list", ImVec2(0, pmxui::scale(200.0f)), ImGuiChildFlags_Borders);
    std::vector<int> visible;
    visible.reserve(model.frames.size());
    for (int i = 0; i < frame_count; ++i) {
        const pmx::DisplayFrame& f = model.frames[i];
        if (pmxui::match_filter(filter, f.name, f.name_en,
                                pmx::name_zh(pmx::NameKind::Frame, f.name, f.name_en)))
            visible.push_back(i);
    }

    if (visible.empty()) {
        ImGui::TextDisabled("没有匹配的表示枠");
    } else {
        ImGuiListClipper clipper;
        clipper.Begin(static_cast<int>(visible.size()));
        while (clipper.Step()) {
            for (int k = clipper.DisplayStart; k < clipper.DisplayEnd; ++k) {
                const int i = visible[k];
                const pmx::DisplayFrame& f = model.frames[i];
                char prefix[24];
                std::snprintf(prefix, sizeof prefix, "%03d · ", i);
                std::string text(prefix);
                text += f.name.empty() ? "未命名表示枠" : f.name;
                if (f.special)
                    text += "   (特殊枠 · " + std::to_string(f.items.size()) + " 项)";
                else
                    text += "   (" + std::to_string(f.items.size()) + " 项)";
                text += "##frame_row";
                text += std::to_string(i);
                if (ImGui::Selectable(text.c_str(), i == idx)) {
                    v.select(SelKind::Frame, i);
                    idx = i;
                }
            }
        }
    }
    ImGui::EndChild();

    if (idx < 0 || idx >= frame_count) {
        ImGui::TextDisabled("未选择表示枠（点击上方列表选择）");
        return;
    }

    pmx::DisplayFrame& frame = model.frames[idx];
    ImGui::TextDisabled("索引 %d · %d 个表示枠", idx, frame_count);

    ImGui::BeginChild("##frame_detail", ImVec2(0, 0));

    // ------------------------------------------------------------ 基本
    ImGui::SeparatorText("基本");
    pmxui::name_fields(v, frame.name, frame.name_en, "frame", "model", "重命名表示枠");
    pmxui::zh_line(pmx::NameKind::Frame, frame.name, frame.name_en);
    {
        bool special = frame.special != 0;
        if (ImGui::Checkbox("特殊枠", &special))
            v.edit("修改特殊枠标志", [idx, special](pmx::Model& m) {
                m.frames[idx].special = special ? 1 : 0;
            }, "model", "frame.special");
        ImGui::SetItemTooltip("特殊枠（通常是「センター」这类固定分组）");
    }

    // ------------------------------------------------------------ 项目
    ImGui::SeparatorText("项目");
    static int item_row = -1;
    static int item_owner = -2;
    if (item_owner != idx) {
        item_owner = idx;
        item_row = frame.items.empty() ? -1 : 0;
    }
    const int item_count = static_cast<int>(frame.items.size());
    if (item_count == 0) item_row = -1;
    else item_row = std::clamp(item_row, 0, item_count - 1);

    ImGui::BeginChild("##frame_items", ImVec2(0, pmxui::scale(150.0f)), ImGuiChildFlags_Borders);
    for (int i = 0; i < item_count; ++i) {
        char prefix[16];
        std::snprintf(prefix, sizeof prefix, "%02d  ", i);
        std::string text(prefix);
        text += frame_item_text(model, frame.items[i]);
        text += "##frame_item";
        text += std::to_string(i);
        if (ImGui::Selectable(text.c_str(), i == item_row)) item_row = i;
    }
    if (item_count == 0) ImGui::TextDisabled("暂无项目");
    ImGui::EndChild();

    {
        int item_delta = 0;
        bool remove_item = false;
        ImGui::BeginDisabled(item_row <= 0);
        if (ImGui::Button("上移")) item_delta = -1;
        ImGui::EndDisabled();
        ImGui::SameLine();
        ImGui::BeginDisabled(item_row < 0 || item_row + 1 >= item_count);
        if (ImGui::Button("下移")) item_delta = 1;
        ImGui::EndDisabled();
        ImGui::SameLine();
        ImGui::BeginDisabled(item_row < 0);
        if (ImGui::Button("移除")) remove_item = true;
        ImGui::EndDisabled();

        if (item_delta != 0) {
            v.push_undo("调整表示枠内顺序");
            item_row = pmxdoc::frame_move_item(model, idx, item_row, item_delta);
            v.touched("model");
        } else if (remove_item) {
            const int pos = item_row;
            v.push_undo("从表示枠移除项目");
            if (pmxdoc::frame_remove_item(model, idx, pos)) {
                const int left = static_cast<int>(frame.items.size());
                item_row = left == 0 ? -1 : std::min(pos, left - 1);
                v.touched("model");
            }
        }
    }

    // 已加入当前枠的骨骼 / 形态不再出现在下拉里。
    std::vector<bool> used_bones(model.bones.size(), false);
    std::vector<bool> used_morphs(model.morphs.size(), false);
    for (const pmx::DisplayFrameItem& item : frame.items) {
        if (item.type == 0 && item.index >= 0 &&
            item.index < static_cast<int>(used_bones.size()))
            used_bones[item.index] = true;
        else if (item.type == 1 && item.index >= 0 &&
                 item.index < static_cast<int>(used_morphs.size()))
            used_morphs[item.index] = true;
    }
    std::vector<int> avail_bones;
    std::vector<int> avail_morphs;
    for (int i = 0; i < static_cast<int>(model.bones.size()); ++i)
        if (!used_bones[i]) avail_bones.push_back(i);
    for (int i = 0; i < static_cast<int>(model.morphs.size()); ++i)
        if (!used_morphs[i]) avail_morphs.push_back(i);

    static int bone_choice = -1;
    static int morph_choice = -1;
    if (!avail_bones.empty() &&
        std::find(avail_bones.begin(), avail_bones.end(), bone_choice) == avail_bones.end())
        bone_choice = avail_bones.front();
    if (!avail_morphs.empty() &&
        std::find(avail_morphs.begin(), avail_morphs.end(), morph_choice) == avail_morphs.end())
        morph_choice = avail_morphs.front();

    {
        const bool can_add = !avail_bones.empty();
        ImGui::BeginDisabled(!can_add);
        std::string preview = can_add ? bone_entry_text(model, bone_choice) : "（无骨骼）";
        ImGui::SetNextItemWidth(std::max(pmxui::scale(60.0f), ImGui::GetContentRegionAvail().x - pmxui::scale(70.0f)));
        if (ImGui::BeginCombo("##frame_add_bone", preview.c_str())) {
            for (int i : avail_bones) {
                std::string text = bone_entry_text(model, i) + "##frame_bone" + std::to_string(i);
                if (ImGui::Selectable(text.c_str(), i == bone_choice)) bone_choice = i;
            }
            ImGui::EndCombo();
        }
        ImGui::EndDisabled();
        ImGui::SameLine();
        ImGui::BeginDisabled(!can_add);
        if (ImGui::Button("加骨骼")) {
            const int bone = bone_choice;
            v.push_undo("加入骨骼到表示枠");
            if (pmxdoc::frame_add_item(model, idx, 0, bone)) {
                item_row = static_cast<int>(frame.items.size()) - 1;
                v.touched("model");
            }
        }
        ImGui::EndDisabled();
    }

    {
        const bool can_add = !avail_morphs.empty();
        ImGui::BeginDisabled(!can_add);
        std::string preview = can_add ? morph_entry_text(model, morph_choice) : "（无形态）";
        ImGui::SetNextItemWidth(std::max(pmxui::scale(60.0f), ImGui::GetContentRegionAvail().x - pmxui::scale(70.0f)));
        if (ImGui::BeginCombo("##frame_add_morph", preview.c_str())) {
            for (int i : avail_morphs) {
                std::string text =
                    morph_entry_text(model, i) + "##frame_morph" + std::to_string(i);
                if (ImGui::Selectable(text.c_str(), i == morph_choice)) morph_choice = i;
            }
            ImGui::EndCombo();
        }
        ImGui::EndDisabled();
        ImGui::SameLine();
        ImGui::BeginDisabled(!can_add);
        if (ImGui::Button("加形态")) {
            const int morph = morph_choice;
            v.push_undo("加入形态到表示枠");
            if (pmxdoc::frame_add_item(model, idx, 1, morph)) {
                item_row = static_cast<int>(frame.items.size()) - 1;
                v.touched("model");
            }
        }
        ImGui::EndDisabled();
    }

    ImGui::TextDisabled("共 %d 项", static_cast<int>(frame.items.size()));

    // ------------------------------------------------------------ 顺序
    ImGui::Separator();
    {
        int frame_delta = 0;
        ImGui::BeginDisabled(idx <= 0);
        if (ImGui::Button("枠上移")) frame_delta = -1;
        ImGui::EndDisabled();
        ImGui::SameLine();
        ImGui::BeginDisabled(idx + 1 >= frame_count);
        if (ImGui::Button("枠下移")) frame_delta = 1;
        ImGui::EndDisabled();

        if (frame_delta != 0) {
            v.push_undo("调整表示枠顺序");
            const int moved = pmxdoc::move_frame(model, idx, frame_delta);
            v.clamp_selection();
            v.select(SelKind::Frame, moved);
            v.touched("model");
            ImGui::EndChild();
            return;
        }
    }

    ImGui::EndChild();
}
