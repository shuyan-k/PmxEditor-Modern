// 设置页：叠加层透明度、物理参数与快捷键。显示开关与主题统一放在「视图」菜单。
#include "app/panels.hpp"

#include <string>

#include <imgui.h>

#include "app/panels/common.hpp"
#include "app/theme.hpp"

void panel_settings(Viewer& v) {
    ImGui::BeginChild("##settings_scroll", ImVec2(0, 0));

    ImGui::TextDisabled("显示开关、物理开关与界面主题见顶部「视图」菜单。");

    // ------------------------------------------------------------ 叠加层透明度
    ImGui::SeparatorText("叠加层不透明度");
    ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
    ImGui::SliderFloat("骨骼##bone_alpha", &v.bone_alpha, 0.0f, 1.0f, "%.2f");
    ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
    ImGui::SliderFloat("刚体##rigid_alpha", &v.rigid_alpha, 0.0f, 1.0f, "%.2f");
    ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
    ImGui::SliderFloat("关节##joint_alpha", &v.joint_alpha, 0.0f, 1.0f, "%.2f");

    // ------------------------------------------------------------ 卡通着色
    ImGui::SeparatorText("卡通着色");
    ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
    ImGui::SliderFloat("边缘光##rim", &v.rim, 0.0f, 0.6f, "%.2f");
    ImGui::SetItemTooltip("沿轮廓叠加本体色的强度；0 为关闭，接近 MMD 原版效果");

    // ------------------------------------------------------------ Bullet 物理
    ImGui::SeparatorText("Bullet 物理");
    ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
    ImGui::DragFloat("重力", &v.gravity, 0.1f, -100.0f, 100.0f, "%.1f");
    ImGui::SetNextItemWidth(pmxui::scale(-90.0f));
    ImGui::DragInt("迭代次数", &v.iterations, 1.0f, 1, 60);
    ImGui::Checkbox("显示地面", &v.ground);
    if (ImGui::Button("应用物理参数")) {
        v.reset_physics();
        pmxtheme::save_settings(v);
    }
    ImGui::SetItemTooltip("按当前重力 / 迭代次数重建物理世界，并写入配置文件");

    // ------------------------------------------------------------ 配置文件
    ImGui::SeparatorText("配置文件");
    ImGui::TextWrapped("%s", pmxtheme::settings_path().c_str());
    if (ImGui::Button("重新载入文件")) {
        std::string err;
        const bool loaded = pmxtheme::load_settings(v, &err);
        pmxtheme::apply_theme(v.theme);
        if (!err.empty()) v.error = err;
        else if (loaded) v.status = "设置已重新载入";
    }
    ImGui::TextDisabled("文件不存在时使用默认值。");

    // ------------------------------------------------------------ 快捷键
    ImGui::SeparatorText("快捷键");
    if (ImGui::BeginTable("##settings_shortcuts", 2, ImGuiTableFlags_SizingFixedFit)) {
        ImGui::TableSetupColumn("##key", ImGuiTableColumnFlags_WidthFixed, 150.0f);
        ImGui::TableSetupColumn("##desc", ImGuiTableColumnFlags_WidthStretch);
        struct Shortcut {
            const char* key;
            const char* desc;
        };
        const Shortcut shortcuts[] = {
            {"Ctrl+O", "打开模型"},
            {"Ctrl+M", "切换编辑 / 预览模式"},
            {"Ctrl+F", "预览模式：检索骨骼 / 刚体 / 关节"},
            {"Ctrl+S", "保存（仅编辑模式）"},
            {"Ctrl+Shift+S", "另存为（仅编辑模式）"},
            {"Ctrl+Z", "撤销"},
            {"Ctrl+Y", "重做"},
            {"Ctrl+Shift+Z", "重做"},
            {"F", "视图全部"},
            {"R", "重置姿态"},
            {"P", "物理开关"},
            {"双击", "选择骨骼 / 刚体 / 关节"},
            {"左键拖动骨骼", "位移（仅预览模式）"},
            {"右键拖动骨骼", "旋转（仅预览模式）"},
            {"中键拖动", "旋转视图"},
            {"Shift+中键拖动", "平移视图"},
            {"滚轮", "缩放"},
        };
        for (const Shortcut& shortcut : shortcuts) {
            ImGui::TableNextRow();
            ImGui::TableNextColumn();
            ImGui::TextUnformatted(shortcut.key);
            ImGui::TableNextColumn();
            ImGui::TextDisabled("%s", shortcut.desc);
        }
        ImGui::EndTable();
    }

    ImGui::EndChild();
}
