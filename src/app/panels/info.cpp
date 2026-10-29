// 模型信息页：统计概览、名称与描述、文件信息、附加 UV、结构校验。
#include "app/panels.hpp"

#include <algorithm>
#include <cstddef>
#include <cstdio>
#include <string>
#include <utility>
#include <vector>

#include <imgui.h>
#include <misc/cpp/imgui_stdlib.h>

#include "app/panels/common.hpp"
#include "app/theme.hpp"

namespace {

// 与 Python 版 validate_model 一致的结构检查，返回中文问题列表。
std::vector<std::string> validate_model(const pmx::Model& model) {
    std::vector<std::string> issues;
    char text[512];
    const int bone_count = static_cast<int>(model.bones.size());

    for (int i = 0; i < bone_count; ++i) {
        const pmx::Bone& bone = model.bones[static_cast<std::size_t>(i)];
        if (bone.parent >= bone_count) {
            std::snprintf(text, sizeof text, "骨骼 %d「%s」的父骨骼索引越界 (%d)", i,
                          bone.name.c_str(), bone.parent);
            issues.emplace_back(text);
        }
        if ((bone.flags & pmx::BF_TAIL_INDEX) && bone.tail_bone >= bone_count) {
            std::snprintf(text, sizeof text, "骨骼 %d「%s」的尾端骨骼索引越界 (%d)", i,
                          bone.name.c_str(), bone.tail_bone);
            issues.emplace_back(text);
        }
        if (bone.ik) {
            for (const pmx::IKLink& link : bone.ik->links) {
                if (link.bone >= bone_count) {
                    std::snprintf(text, sizeof text,
                                  "骨骼 %d「%s」的 IK 链接索引越界 (%d)", i,
                                  bone.name.c_str(), link.bone);
                    issues.emplace_back(text);
                }
            }
        }
    }

    long long face_total = 0;
    for (const pmx::Material& material : model.materials) face_total += material.face_count;
    if (face_total != static_cast<long long>(model.indices.size())) {
        std::snprintf(text, sizeof text, "材质面数合计 %lld 与索引数 %zu 不一致", face_total,
                      model.indices.size());
        issues.emplace_back(text);
    }

    for (int i = 0; i < static_cast<int>(model.rigid.size()); ++i) {
        const pmx::RigidBody& rigid = model.rigid[static_cast<std::size_t>(i)];
        if (rigid.bone >= bone_count) {
            std::snprintf(text, sizeof text, "刚体 %d「%s」关联骨骼越界 (%d)", i,
                          rigid.name.c_str(), rigid.bone);
            issues.emplace_back(text);
        }
    }

    const int rigid_count = static_cast<int>(model.rigid.size());
    for (int i = 0; i < static_cast<int>(model.joints.size()); ++i) {
        const pmx::Joint& joint = model.joints[static_cast<std::size_t>(i)];
        if (joint.rigid_a >= rigid_count || joint.rigid_b >= rigid_count) {
            std::snprintf(text, sizeof text, "关节 %d「%s」关联刚体越界 (%d, %d)", i,
                          joint.name.c_str(), joint.rigid_a, joint.rigid_b);
            issues.emplace_back(text);
        }
    }

    if (model.add_uv_count < 0 || model.add_uv_count > 4) {
        std::snprintf(text, sizeof text, "附加 UV 数 %d 超出 0–4", model.add_uv_count);
        issues.emplace_back(text);
    } else {
        const std::size_t vertices = model.vertices.size();
        const std::size_t stride = static_cast<std::size_t>(model.add_uv_count) * 4;
        if (vertices > 0 && model.vertices.add_uv.size() != vertices * stride) {
            const std::size_t width = model.vertices.add_uv.size() / vertices;
            std::snprintf(text, sizeof text,
                          "附加 UV 数 %d 与顶点附加 UV 数据宽度 %zu 不一致",
                          model.add_uv_count, width);
            issues.emplace_back(text);
        }
    }
    return issues;
}

}  // namespace

void panel_info(Viewer& v) {
    if (!v.pose) {
        ImGui::TextUnformatted("尚未载入模型");
        return;
    }

    pmx::Model& model = v.model;
    ImGui::BeginChild("##info_scroll", ImVec2(0, 0));

    // ------------------------------------------------------------ 统计概览
    {
        struct StatItem {
            const char* label;
            std::size_t value;
        };
        const StatItem stats[] = {
            {"顶点", model.n_vertices()},
            {"三角面", model.n_faces()},
            {"骨骼", model.bones.size()},
            {"材质", model.materials.size()},
            {"形态", model.morphs.size()},
            {"贴图", model.textures.size()},
            {"刚体", model.rigid.size()},
            {"关节", model.joints.size()},
            {"柔体", model.soft_bodies.size()},
        };
        if (ImGui::BeginTable("##info_stats", 3, ImGuiTableFlags_SizingStretchSame)) {
            for (const StatItem& item : stats) {
                ImGui::TableNextColumn();
                ImGui::Text("%zu", item.value);
                ImGui::TextDisabled("%s", item.label);
            }
            ImGui::EndTable();
        }
    }

    // ------------------------------------------------------------ 名称与描述
    ImGui::SeparatorText("显示名称");
    pmxui::name_fields(v, model.name, model.name_en, "info", "model");
    pmxui::zh_line(pmx::NameKind::Model, model.name, model.name_en);

    ImGui::SeparatorText("描述");
    {
        std::string comment = model.comment;
        const ImVec2 size(-1.0f, 96.0f);
        if (ImGui::InputTextMultiline("##info_comment", &comment, size)) {
            if (comment != model.comment) {
                const std::string next = comment;
                v.edit("修改描述", [next](pmx::Model& m) { m.comment = next; }, "model",
                       "model.comment");
            }
        }
    }

    // ------------------------------------------------------------ 文件信息
    ImGui::SeparatorText("文件信息");
    if (ImGui::BeginTable("##info_file", 2, ImGuiTableFlags_SizingFixedFit)) {
        ImGui::TableSetupColumn("##key", ImGuiTableColumnFlags_WidthFixed, 64.0f);
        ImGui::TableSetupColumn("##value", ImGuiTableColumnFlags_WidthStretch);

        auto next_label = [](const char* label) {
            ImGui::TableNextRow();
            ImGui::TableNextColumn();
            ImGui::TextDisabled("%s", label);
            ImGui::TableNextColumn();
        };

        next_label("路径");
        {
            std::string path_text = model.path.empty() ? "（尚未保存）" : model.path;
            ImGui::SetNextItemWidth(-1.0f);
            ImGui::InputText("##info_path", &path_text, ImGuiInputTextFlags_ReadOnly);
        }

        next_label("版本");
        ImGui::Text("%.1f", model.version);

        next_label("编码");
        {
            const char* kEncodings[] = {"UTF-16LE", "UTF-8"};
            const int current = model.encoding == 1 ? 1 : 0;
            int picked = current;
            ImGui::SetNextItemWidth(-1.0f);
            if (ImGui::BeginCombo("##info_encoding", kEncodings[current])) {
                for (int i = 0; i < 2; ++i) {
                    if (ImGui::Selectable(kEncodings[i], i == current)) picked = i;
                    if (i == current) ImGui::SetItemDefaultFocus();
                }
                ImGui::EndCombo();
            }
            if (picked != model.encoding) {
                const int encoding = picked;
                v.edit("切换文字编码", [encoding](pmx::Model& m) {
                    m.encoding = encoding;
                }, "model");
            }
        }

        next_label("索引宽度");
        ImGui::Text("V%d T%d M%d B%d Mo%d R%d", model.vsz, model.tsz, model.msz, model.bsz,
                    model.mosz, model.rsz);

        next_label("附加 UV");
        {
            const int current = std::clamp(model.add_uv_count, 0, 4);
            int picked = current;
            ImGui::SetNextItemWidth(-1.0f);
            const std::string preview = std::to_string(current) + " 组";
            if (ImGui::BeginCombo("##info_add_uv", preview.c_str())) {
                for (int n = 0; n <= 4; ++n) {
                    const std::string item =
                        std::to_string(n) + " 组 · 每顶点 " + std::to_string(n * 4) + " 个浮点";
                    if (ImGui::Selectable(item.c_str(), n == current)) picked = n;
                    if (n == current) ImGui::SetItemDefaultFocus();
                }
                ImGui::EndCombo();
            }
            ImGui::SetItemTooltip(
                "附加 UV 会为每个顶点补 4×N 个浮点（PMX 规定 0–4），改动会影响顶点缓冲");
            if (picked != model.add_uv_count) {
                const int count = picked;
                v.edit("修改附加 UV 数", [count](pmx::Model& m) {
                    const std::size_t vertices = m.vertices.size();
                    const int old_count = m.add_uv_count;
                    const int old_stride = old_count > 0 ? old_count * 4 : 0;
                    const int new_stride = count * 4;
                    const int keep = std::min(old_count, count) * 4;
                    std::vector<float> next(vertices * static_cast<std::size_t>(new_stride),
                                            0.0f);
                    if (keep > 0 && old_stride > 0) {
                        for (std::size_t i = 0; i < vertices; ++i) {
                            const std::size_t src =
                                i * static_cast<std::size_t>(old_stride);
                            const std::size_t dst =
                                i * static_cast<std::size_t>(new_stride);
                            for (int k = 0; k < keep; ++k) {
                                const std::size_t from =
                                    src + static_cast<std::size_t>(k);
                                if (from >= m.vertices.add_uv.size()) break;
                                next[dst + static_cast<std::size_t>(k)] =
                                    m.vertices.add_uv[from];
                            }
                        }
                    }
                    m.vertices.add_uv = std::move(next);
                    m.add_uv_count = count;
                }, "structure");
            }
        }
        ImGui::EndTable();
    }

    // ------------------------------------------------------------ 结构校验
    ImGui::SeparatorText("模型校验");
    {
        const std::vector<std::string> issues = validate_model(model);
        if (issues.empty()) {
            ImGui::PushStyleColor(ImGuiCol_Text, pmxtheme::success());
            ImGui::TextUnformatted("未发现结构问题");
            ImGui::PopStyleColor();
        } else {
            ImGui::PushStyleColor(ImGuiCol_Text, pmxtheme::warning());
            for (const std::string& issue : issues) ImGui::Text("· %s", issue.c_str());
            ImGui::PopStyleColor();
        }
    }

    ImGui::EndChild();
}
