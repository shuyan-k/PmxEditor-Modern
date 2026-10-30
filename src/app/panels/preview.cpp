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

// ---------------------------------------------------------------- 快捷检索
// 预览模式只摆姿态，没有骨骼列表；这里提供「输入关键词 → 点行选中」的入口，
// 选中后即可在视口左键位移 / 右键旋转。检查器其余标签保持原样。
namespace {

enum SearchKind { kSearchBone = 0, kSearchRigid, kSearchJoint };
const char* const kSearchKinds[] = {"骨骼", "刚体", "关节"};

struct SearchRow {
    int index = 0;
    std::string text;  // 编号 + 原文（英文名为空时用英文 / 未命名）
    std::string zh;    // 中文译名；未收录时为空
};

struct SearchState {
    std::string search;
    int kind = kSearchBone;
    std::string cached_search;
    int cached_kind = -1;
    std::size_t cached_count = 0;
    std::vector<SearchRow> rows;
};

SearchState& search_state() {
    static SearchState s;
    return s;
}

std::size_t kind_count(const pmx::Model& model, int kind) {
    switch (kind) {
        case kSearchRigid: return model.rigid.size();
        case kSearchJoint: return model.joints.size();
        default: return model.bones.size();
    }
}

// 名称 + 英文名 + 中文都参与匹配；只在搜索词 / 类型 / 条目数变化时重建。
void rebuild_search_rows(const pmx::Model& model, SearchState& st) {
    const std::size_t count = kind_count(model, st.kind);
    if (st.cached_search == st.search && st.cached_kind == st.kind && st.cached_count == count)
        return;
    st.cached_search = st.search;
    st.cached_kind = st.kind;
    st.cached_count = count;
    st.rows.clear();

    for (std::size_t i = 0; i < count; ++i) {
        const pmx::NameKind nk = st.kind == kSearchRigid
                                     ? pmx::NameKind::Rigid
                                     : st.kind == kSearchJoint ? pmx::NameKind::Joint
                                                               : pmx::NameKind::Bone;
        const std::string name = st.kind == kSearchRigid
                                     ? model.rigid[i].name
                                     : st.kind == kSearchJoint ? model.joints[i].name
                                                               : model.bones[i].name;
        const std::string name_en = st.kind == kSearchRigid
                                        ? model.rigid[i].name_en
                                        : st.kind == kSearchJoint ? model.joints[i].name_en
                                                                  : model.bones[i].name_en;
        const std::string zh = pmx::name_zh(nk, name, name_en);
        if (!pmxui::match_filter(st.search, name, name_en, zh)) continue;

        char head[16];
        std::snprintf(head, sizeof(head), "%03d · ", static_cast<int>(i));
        std::string base = pmxui::base_name(name, name_en);
        if (base.empty()) base = "未命名";
        SearchRow row;
        row.index = static_cast<int>(i);
        row.text = std::string(head) + base;
        row.zh = pmxui::zh_only(nk, name, name_en);
        st.rows.push_back(std::move(row));
    }
}

bool kind_selected(const Viewer& v, int kind, int index) {
    if (kind == kSearchRigid) return v.sel.kind == SelKind::Rigid && v.sel.index == index;
    if (kind == kSearchJoint) return v.sel.kind == SelKind::Joint && v.sel.index == index;
    return v.sel.kind == SelKind::Bone && v.sel.index == index;
}

void select_from_search(Viewer& v, const SearchState& st, const SearchRow& row) {
    const int i = row.index;
    if (st.kind == kSearchRigid) {
        v.select(SelKind::Rigid, i);
        const pmx::RigidBody& rb = v.model.rigid[static_cast<std::size_t>(i)];
        const std::string label =
            pmxui::base_name(rb.name, rb.name_en).empty()
                ? "#" + std::to_string(i)
                : pmxui::base_name(rb.name, rb.name_en);
        v.status = "已选中刚体「" + label + "」";
    } else if (st.kind == kSearchJoint) {
        v.select(SelKind::Joint, i);
        const pmx::Joint& jt = v.model.joints[static_cast<std::size_t>(i)];
        const std::string label =
            pmxui::base_name(jt.name, jt.name_en).empty()
                ? "#" + std::to_string(i)
                : pmxui::base_name(jt.name, jt.name_en);
        v.status = "已选中关节「" + label + "」";
    } else {
        v.select(SelKind::Bone, i);
        v.status = "已选中「" + v.bone_name(i) + "」：左键拖动位移 · 右键拖动旋转";
    }
    // 对象被整体隐藏时临时显示并高亮，与视口双击选中的行为一致。
    v.focus_overlay = true;
}

}  // namespace

void panel_preview_search(Viewer& v) {
    if (!v.pose) {
        ImGui::TextDisabled("未加载模型");
        return;
    }
    SearchState& st = search_state();
    const pmx::Model& model = v.model;

    // 视口双击后揭示到本页：清掉过滤并切到对应类型，保证选中行可见。
    if (v.reveal_selection) {
        switch (v.sel.kind) {
            case SelKind::Bone: st.kind = kSearchBone; break;
            case SelKind::Rigid: st.kind = kSearchRigid; break;
            case SelKind::Joint: st.kind = kSearchJoint; break;
            default: break;
        }
        st.search.clear();
    }

    ImGui::SetNextItemWidth(pmxui::scale(96.0f));
    ImGui::Combo("##preview_search_kind", &st.kind, kSearchKinds, IM_ARRAYSIZE(kSearchKinds));
    ImGui::SameLine();
    ImGui::SetNextItemWidth(-1.0f);
    if (v.focus_preview_search) ImGui::SetKeyboardFocusHere();
    ImGui::InputTextWithHint("##preview_search",
                             "搜索名称 / 中文 / 英文名（Ctrl+F），回车选中第一项", &st.search);
    // InputText 有焦点时按回车直接选中第一条，少点一次。
    const bool submitted =
        ImGui::IsItemActive() && ImGui::IsKeyPressed(ImGuiKey_Enter, false);
    v.focus_preview_search = false;

    rebuild_search_rows(model, st);

    if (submitted && !st.rows.empty()) select_from_search(v, st, st.rows.front());

    ImGui::BeginChild("##preview_search_list", ImVec2(0, 0), ImGuiChildFlags_Borders);
    if (st.rows.empty()) {
        ImGui::TextDisabled(kind_count(model, st.kind) == 0 ? "这个模型没有对应数据"
                                                           : "没有匹配项");
    } else {
        ImGuiListClipper clipper;
        clipper.Begin(static_cast<int>(st.rows.size()));
        while (clipper.Step()) {
            for (int r = clipper.DisplayStart; r < clipper.DisplayEnd; ++r) {
                const SearchRow& row = st.rows[static_cast<std::size_t>(r)];
                const std::string id = "preview_search_row" + std::to_string(row.index);
                if (pmxui::zh_row(id.c_str(), row.text, row.zh,
                                  kind_selected(v, st.kind, row.index)))
                    select_from_search(v, st, row);
                // 视口双击选中的对象可能在列表可视区外，滚到中间。
                if (v.reveal_selection && kind_selected(v, st.kind, row.index))
                    ImGui::SetScrollHereY(0.5f);
            }
        }
    }
    ImGui::EndChild();
}

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
    ImGui::InputTextWithHint("##morph_filter", "搜索形态名 / 中文 / 英文名…", filter,
                             IM_ARRAYSIZE(filter));
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
        // 名称同时匹配日文原名、英文对照名与中文译名，大小写不敏感。
        if (!pmxui::match_filter(filter, mo.name, mo.name_en,
                                 pmx::name_zh(pmx::NameKind::Morph, mo.name, mo.name_en)))
            continue;
        ImGui::PushID(i);
        float percent = v.morph_values[static_cast<std::size_t>(i)] * 100.0f;
        std::string display = pmx::name_with_zh(pmx::NameKind::Morph, mo.name, mo.name_en);
        if (display.empty()) display = "形态 " + std::to_string(i);
        const std::string label = display + "##m";
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
