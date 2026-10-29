// 面板公用小工具：搜索归一化、名称输入、拖动控件（先压快照再写回）。
#pragma once

#include <algorithm>
#include <cctype>
#include <string>

#include <imgui.h>
#include <misc/cpp/imgui_stdlib.h>

#include "app/ui_scale.hpp"
#include "app/viewer.hpp"
#include "core/name_zh.hpp"

namespace pmxui {

inline std::string lower_copy(std::string s) {
    for (char& c : s)
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return s;
}

// 搜索同时匹配原名、英文对照名与中文译名。
inline bool match_filter(const std::string& filter, const std::string& name,
                         const std::string& name_en, const std::string& zh = {}) {
    if (filter.empty()) return true;
    const std::string needle = lower_copy(filter);
    return lower_copy(name + " " + name_en + " " + zh).find(needle) != std::string::npos;
}

// 详情区的中文对照；未收录时不显示。
inline void zh_line(pmx::NameKind kind, const std::string& name, const std::string& name_en) {
    const std::string zh = pmx::name_zh(kind, name, name_en);
    if (!zh.empty() && zh != name) ImGui::TextDisabled("中文：%s", zh.c_str());
}

// 名称 / 英文名输入框。返回是否有改动。
inline bool name_fields(Viewer& v, std::string& name, std::string& name_en, const char* id,
                        const char* kind, const char* label = "修改名称") {
    bool changed = false;
    ImGui::PushID(id);
    std::string tmp = name;
    ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
    if (ImGui::InputText("名称", &tmp)) {
        v.edit(label, [&name, &tmp](pmx::Model&) { name = tmp; }, kind,
               std::string("name:") + id);
        changed = true;
    }
    tmp = name_en;
    ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
    if (ImGui::InputText("英文名", &tmp)) {
        v.edit(label, [&name_en, &tmp](pmx::Model&) { name_en = tmp; }, kind,
               std::string("name_en:") + id);
        changed = true;
    }
    ImGui::PopID();
    return changed;
}

// 拖动浮点：控件先改临时值，确认有变化才压撤销快照并写回模型。
inline bool drag_float(Viewer& v, const char* id, float& value, float speed, float lo, float hi,
                       const char* kind, const char* label, const char* coalesce = nullptr,
                       const char* fmt = "%.3f") {
    float tmp = value;
    if (!ImGui::DragFloat(id, &tmp, speed, lo, hi, fmt)) return false;
    v.edit(label, [&value, tmp](pmx::Model&) { value = tmp; }, kind,
           coalesce ? coalesce : label);
    return true;
}

// 角度字段（显示度数，存弧度）。
inline bool drag_angle(Viewer& v, const char* id, float& radians, float speed, float lo_deg,
                       float hi_deg, const char* kind, const char* label,
                       const char* coalesce = nullptr) {
    constexpr float k = 57.29577951308232f;
    float deg = radians * k;
    if (!ImGui::DragFloat(id, &deg, speed, lo_deg, hi_deg, "%.1f°")) return false;
    v.edit(label, [&radians, deg](pmx::Model&) { radians = deg / k; }, kind,
           coalesce ? coalesce : label);
    return true;
}

// 三分量拖动：整组只压一条撤销。
inline bool drag_vec3(Viewer& v, const char* id, pmx::Vec3& value, float speed, float lo,
                      float hi, const char* kind, const char* label,
                      const char* coalesce = nullptr) {
    float tmp[3] = {value.x, value.y, value.z};
    if (!ImGui::DragFloat3(id, tmp, speed, lo, hi, "%.3f")) return false;
    v.edit(label, [&value, tmp](pmx::Model&) {
        value = pmx::Vec3{tmp[0], tmp[1], tmp[2]};
    }, kind, coalesce ? coalesce : label);
    return true;
}

inline bool drag_angle3(Viewer& v, const char* id, pmx::Vec3& radians, float speed, float lo_deg,
                        float hi_deg, const char* kind, const char* label,
                        const char* coalesce = nullptr) {
    constexpr float k = 57.29577951308232f;
    float tmp[3] = {radians.x * k, radians.y * k, radians.z * k};
    if (!ImGui::DragFloat3(id, tmp, speed, lo_deg, hi_deg, "%.1f°")) return false;
    v.edit(label, [&radians, tmp](pmx::Model&) {
        radians = pmx::Vec3{tmp[0] / k, tmp[1] / k, tmp[2] / k};
    }, kind, coalesce ? coalesce : label);
    return true;
}

}  // namespace pmxui
