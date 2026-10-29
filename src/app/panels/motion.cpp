// 「动作」面板：VMD 导入 / 清除、时间轴拖动、播放速度与匹配情况。
#include "app/panels.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <string>

#include <imgui.h>

#include "app/panels/common.hpp"
#include "core/vmd.hpp"

void panel_motion(Viewer& v) {
    if (!v.pose) {
        ImGui::TextDisabled("未加载模型");
        return;
    }

    if (ImGui::Button("导入 VMD…")) {
        const std::string path = pick_open_file(kVmdFilter, L"导入 VMD 动作");
        if (!path.empty()) {
            std::string err;
            if (v.load_vmd_file(path, &err)) v.error.clear();
            else v.error = err;
        }
    }
    ImGui::SetItemTooltip("载入 .vmd 动作并按 30 fps 时间轴预览");
    ImGui::SameLine();
    ImGui::BeginDisabled(!v.motion);
    if (ImGui::Button("清除动作")) v.clear_motion();
    ImGui::EndDisabled();

    if (!v.motion) {
        ImGui::Spacing();
        ImGui::TextDisabled("拖入 .vmd 文件，或使用「文件 → 导入 VMD…」。");
        ImGui::TextDisabled("动作按名称绑定到模型骨骼 / 形态，未匹配的轨道会被跳过。");
        return;
    }

    const pmx::VmdMotion& motion = *v.motion;
    ImGui::SeparatorText("动作信息");
    ImGui::TextWrapped("%s", motion.source.c_str());
    if (!motion.model_name.empty())
        ImGui::TextDisabled("动作模型：%s", motion.model_name.c_str());
    ImGui::TextDisabled("骨骼轨道 %d · 形态轨道 %d · 相机轨道 %d · 时长 %d 帧",
                        static_cast<int>(motion.bone_tracks.size()),
                        static_cast<int>(motion.morph_tracks.size()), motion.camera_keys,
                        motion.max_frame);
    ImGui::TextDisabled("已匹配：骨骼 %d/%d，形态 %d/%d", v.motion_binding.bone_matched,
                        static_cast<int>(motion.bone_tracks.size()),
                        v.motion_binding.morph_matched,
                        static_cast<int>(motion.morph_tracks.size()));
    ImGui::TextDisabled("播放中手动拖动骨骼会自动暂停动作。");

    // ------------------------------------------------------------ 播放
    ImGui::SeparatorText("播放");
    ImGui::BeginDisabled(motion.max_frame <= 0);
    if (ImGui::Button(v.motion_playing ? "暂停" : "播放")) {
        if (!v.motion_playing) {
            if (v.motion_frame >= static_cast<float>(motion.max_frame)) v.motion_frame = 0.0f;
            v.motion_dirty = true;
            if (v.physics_enabled) v.settle_physics();
        }
        v.motion_playing = !v.motion_playing;
    }
    ImGui::SetItemTooltip("播放中手动拖动骨骼会自动暂停动作");
    ImGui::SameLine();
    if (ImGui::Button("回到起点")) {
        v.motion_frame = 0.0f;
        v.motion_dirty = true;
        if (v.physics_enabled) v.settle_physics();
    }
    ImGui::EndDisabled();
    ImGui::SameLine();
    ImGui::Checkbox("循环", &v.motion_loop);

    ImGui::SetNextItemWidth(pmxui::scale(-100.0f));
    ImGui::SliderFloat("速度", &v.motion_speed, 0.1f, 4.0f, "%.2fx");
    ImGui::SetItemTooltip("1.00x 表示与 MMD 相同的 30 fps 时间轴");

    if (motion.max_frame > 0) {
        int frame = static_cast<int>(std::lround(v.motion_frame));
        char frame_format[64];
        std::snprintf(frame_format, sizeof frame_format, "帧 %%d / %d", motion.max_frame);
        ImGui::SetNextItemWidth(-1.0f);
        if (ImGui::SliderInt("##motion_frame", &frame, 0, motion.max_frame, frame_format)) {
            v.motion_frame = static_cast<float>(frame);
            v.motion_dirty = true;
            // 拖到任意帧等同一次瞬移：只清速度，不重摆刚体（重摆会把刚性链扯断）。
            if (v.physics_enabled) v.settle_physics();
        }
    } else {
        ImGui::TextDisabled("动作只有第 0 帧");
    }
    ImGui::TextDisabled("当前帧 %.2f", static_cast<double>(v.motion_frame));

    // ------------------------------------------------------------ 未匹配名称
    const int missing = static_cast<int>(v.motion_binding.missing_bones.size() +
                                         v.motion_binding.missing_morphs.size());
    if (missing > 0) {
        ImGui::SeparatorText("未匹配名称");
        ImGui::TextDisabled("以下轨道在模型中找不到同名骨骼 / 形态，播放时被跳过：");
        ImGui::BeginChild("##motion_missing", ImVec2(0, pmxui::scale(140.0f)),
                          ImGuiChildFlags_Borders);
        for (const std::string& name : v.motion_binding.missing_bones)
            ImGui::TextUnformatted(("骨骼 · " + name).c_str());
        for (const std::string& name : v.motion_binding.missing_morphs)
            ImGui::TextUnformatted(("形态 · " + name).c_str());
        ImGui::EndChild();
    }

    const int renamed = static_cast<int>(v.motion_binding.renamed_bones.size() +
                                         v.motion_binding.renamed_morphs.size());
    if (renamed > 0)
        ImGui::TextDisabled("%d 个轨道通过宽松匹配（忽略空格 / 大小写）绑定成功", renamed);
}
