// 设置页：显示开关、叠加层透明度、物理参数、界面主题与快捷键。
#include "app/panels.hpp"

#include <string>

#include <imgui.h>

#include "app/panels/common.hpp"
#include "app/theme.hpp"

void panel_settings(Viewer& v) {
    ImGui::BeginChild("##settings_scroll", ImVec2(0, 0));

    // ------------------------------------------------------------ 视图显示
    ImGui::SeparatorText("视图显示");
    if (ImGui::BeginTable("##settings_display", 2, ImGuiTableFlags_SizingStretchSame)) {
        struct Toggle {
            const char* label;
            bool* value;
        };
        const Toggle toggles[] = {
            {"地面网格##show_grid", &v.grid},
            {"骨骼##show_bones", &v.show_bones},
            {"刚体##show_rigid", &v.show_rigid},
            {"关节##show_joints", &v.show_joints},
            {"模型网格##show_mesh", &v.show_mesh},
            {"GPU 蒙皮##use_gpu", &v.use_gpu},
            {"线框##wireframe", &v.wireframe},
            {"描边##outline", &v.outline},
        };
        for (const Toggle& toggle : toggles) {
            ImGui::TableNextColumn();
            ImGui::Checkbox(toggle.label, toggle.value);
        }
        ImGui::TableNextColumn();
        {
            bool toon = v.toon > 0.5f;
            if (ImGui::Checkbox("卡通光照##toon", &toon)) v.toon = toon ? 1.0f : 0.0f;
        }
        ImGui::EndTable();
    }

    // ------------------------------------------------------------ 叠加层透明度
    ImGui::SeparatorText("叠加层不透明度");
    ImGui::SetNextItemWidth(-90.0f);
    ImGui::SliderFloat("骨骼##bone_alpha", &v.bone_alpha, 0.0f, 1.0f, "%.2f");
    ImGui::SetNextItemWidth(-90.0f);
    ImGui::SliderFloat("刚体##rigid_alpha", &v.rigid_alpha, 0.0f, 1.0f, "%.2f");
    ImGui::SetNextItemWidth(-90.0f);
    ImGui::SliderFloat("关节##joint_alpha", &v.joint_alpha, 0.0f, 1.0f, "%.2f");

    // ------------------------------------------------------------ Bullet 物理
    ImGui::SeparatorText("Bullet 物理");
    ImGui::SetNextItemWidth(-90.0f);
    ImGui::DragFloat("重力", &v.gravity, 0.1f, -100.0f, 100.0f, "%.1f");
    ImGui::SetNextItemWidth(-90.0f);
    ImGui::DragInt("迭代次数", &v.iterations, 1.0f, 1, 60);
    ImGui::Checkbox("显示地面", &v.ground);
    if (ImGui::Checkbox("物理演算##physics_enabled", &v.physics_enabled)) {
        v.reset_physics();
    }
    ImGui::SetItemTooltip("与 P 键等效：开启时先按当前形态预热，再逐帧演算");
    if (ImGui::Button("应用物理参数")) {
        v.reset_physics();
        pmxtheme::save_settings(v);
    }
    ImGui::SetItemTooltip("按当前重力 / 迭代次数重建物理世界，并写入配置文件");

    // ------------------------------------------------------------ 界面主题
    ImGui::SeparatorText("界面主题");
    const bool light = v.theme == "light";
    if (ImGui::RadioButton("深色", !light) && light) {
        v.theme = "dark";
        pmxtheme::apply_theme(v.theme);
        pmxtheme::save_settings(v);
    }
    ImGui::SameLine();
    if (ImGui::RadioButton("亮色", light) && !light) {
        v.theme = "light";
        pmxtheme::apply_theme(v.theme);
        pmxtheme::save_settings(v);
    }

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
            {"Ctrl+S", "保存"},
            {"Ctrl+Shift+S", "另存为"},
            {"Ctrl+Z", "撤销"},
            {"Ctrl+Y", "重做"},
            {"Ctrl+Shift+Z", "重做"},
            {"F", "视图全部"},
            {"R", "重置姿态"},
            {"P", "物理开关"},
            {"双击", "选择骨骼 / 刚体 / 关节"},
            {"左键拖动骨骼", "位移"},
            {"右键拖动骨骼", "旋转"},
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
