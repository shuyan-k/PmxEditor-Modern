// 预览模式（模型只读）的控制面板：物理开关与参数、形态滑杆。
// 与编辑模式的区别只有一个：这里不产生任何对模型数据的修改，只影响当前视图。
#include "app/panels.hpp"

#include <algorithm>
#include <cstdio>
#include <string>
#include <vector>

#include <imgui.h>

#include "app/panels/common.hpp"

namespace {

const char* const kMorphPanels[] = {"全部", "眉", "眼", "口", "其他"};

// 把 morph_values 汇总成生效权重；只影响当前视图，不写入模型。
void commit_morph_preview(Viewer& v) {
    v.morph_weights.clear();
    for (std::size_t i = 0; i < v.morph_values.size(); ++i) {
        const float weight = v.morph_values[i];
        if (weight > 1e-4f) v.morph_weights.emplace_back(static_cast<int>(i), weight);
    }
    v.morph_dirty = true;
}

bool morph_matches_panel(const pmx::Morph& mo, int panel) {
    if (panel == 0) return true;
    // PMX 操作面板：0 系统 / 1 眉 / 2 眼 / 3 口 / 4 其他。
    if (panel == 4) return mo.panel >= 4 || mo.panel < 0;
    return mo.panel == panel;
}

}  // namespace

void panel_preview_physics(Viewer& v) {
    if (!v.pose) {
        ImGui::TextDisabled("未加载模型");
        return;
    }
    if (!v.physics_ptr) {
        ImGui::TextDisabled("当前构建未启用物理（PMX_ENABLE_PHYSICS=OFF）");
        return;
    }

    bool enabled = v.physics_enabled;
    if (ImGui::Checkbox("启用物理演算", &enabled)) {
        v.physics_enabled = enabled;
        v.reset_physics();
    }
    ImGui::SetItemTooltip("与快捷键 P 相同：重建物理世界并按当前姿态摆放刚体");

    ImGui::SameLine();
    if (ImGui::Button("重置物理")) v.reset_physics();
    ImGui::SetItemTooltip("把所有刚体按当前姿态重新摆放并清零速度");

    ImGui::Spacing();
    ImGui::SeparatorText("参数");
    ImGui::BeginDisabled(!v.physics_enabled);
    ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
    ImGui::DragFloat("重力", &v.gravity, 0.1f, -100.0f, 100.0f, "%.1f");
    ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
    ImGui::DragInt("迭代次数", &v.iterations, 1.0f, 1, 60);
    ImGui::Checkbox("显示地面", &v.ground);
    if (ImGui::Button("应用参数")) v.reset_physics();
    ImGui::EndDisabled();
    ImGui::TextDisabled("重力 / 迭代次数是查看器的全局参数，不属于模型数据。");

    ImGui::Spacing();
    ImGui::SeparatorText("当前物理");
    ImGui::TextDisabled("刚体 %d · 关节 %d", static_cast<int>(v.model.rigid.size()),
                        static_cast<int>(v.model.joints.size()));
    ImGui::TextDisabled(v.physics_enabled ? "状态：演算中" : "状态：已关闭（姿态来自动画）");
}

void panel_preview_morph(Viewer& v) {
    if (!v.pose) {
        ImGui::TextDisabled("未加载模型");
        return;
    }
    const int count = static_cast<int>(v.model.morphs.size());
    if (count == 0) {
        ImGui::TextDisabled("这个模型没有形态数据");
        return;
    }
    if (v.morph_values.size() != static_cast<std::size_t>(count))
        v.morph_values.assign(static_cast<std::size_t>(count), 0.0f);

    // ------------------------------------------------------------ 过滤
    static int panel = 0;
    static char filter[64] = "";
    ImGui::SetNextItemWidth(pmxui::scale(110.0f));
    ImGui::Combo("##morph_panel", &panel, kMorphPanels, IM_ARRAYSIZE(kMorphPanels));
    ImGui::SameLine();
    ImGui::SetNextItemWidth(
        std::max(pmxui::scale(80.0f), ImGui::GetContentRegionAvail().x - pmxui::scale(92.0f)));
    ImGui::InputTextWithHint("##morph_filter", "搜索形态名…", filter, IM_ARRAYSIZE(filter));
    ImGui::SameLine();
    if (ImGui::Button("全部复位")) {
        std::fill(v.morph_values.begin(), v.morph_values.end(), 0.0f);
        commit_morph_preview(v);
    }

    // ------------------------------------------------------------ 滑杆列表
    ImGui::BeginChild("##preview_morphs", ImVec2(0, 0), ImGuiChildFlags_Borders);
    int shown = 0;
    for (int i = 0; i < count; ++i) {
        const pmx::Morph& mo = v.model.morphs[static_cast<std::size_t>(i)];
        if (!morph_matches_panel(mo, panel)) continue;
        if (filter[0] != '\0') {
            // 名称同时匹配日文原名与英文名，大小写不敏感。
            const std::string needle = filter;
            const std::string hay = mo.name + " " + mo.name_en;
            if (hay.find(needle) == std::string::npos) continue;
        }
        ImGui::PushID(i);
        float percent = v.morph_values[static_cast<std::size_t>(i)] * 100.0f;
        const std::string label =
            (mo.name.empty() ? "形态 " + std::to_string(i) : mo.name) + "##m";
        if (ImGui::SliderFloat(label.c_str(), &percent, 0.0f, 100.0f, "%.0f%%")) {
            v.morph_values[static_cast<std::size_t>(i)] = percent / 100.0f;
            commit_morph_preview(v);
        }
        ImGui::PopID();
        ++shown;
    }
    if (shown == 0) ImGui::TextDisabled("没有匹配的形态");
    ImGui::EndChild();
}
