// 面页：按材质查看三角面区间、浏览面列表，并把面移动到其他材质或删除。
//
// 对齐 Python 版 panels/face.py 的材质列表与重分配表单，并补上面列表/详情：
//  - 材质列表显示每个材质的起始面与面数；
//  - 面列表按材质内序号分页（每页 200），点击选中 SelKind::Face；
//  - 面数据（indices / face_count）的改动一律使用 "structure"；
//  - 移动面调用 pmxdoc::reassign_faces，删除面裁剪 indices 后重算 face_count。
// 删除时不调用 compact_vertices：Python 面页只移动面，compact_vertices 仅在
// doc.remove_material（删除材质）里使用，这里保持同样行为（保留孤立顶点）。
#include "app/panels.hpp"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

#include <imgui.h>

#include "app/document_ops.hpp"
#include "app/panels/common.hpp"
#include "core/pmx.hpp"

namespace {

constexpr int kFacePageSize = 200;

struct FacePanelState {
    std::string search;
    std::string filter_search;
    std::size_t filter_materials = 0;
    std::vector<int> filtered;

    int material = -1;
    int page = 0;
    int start = 0;
    int count = 0;
    int dst = -1;
    int last_material_sel = -1;
};

FacePanelState& state() {
    static FacePanelState s;
    return s;
}

void ensure_material_filter(const pmx::Model& model, FacePanelState& st) {
    if (st.filter_search == st.search && st.filter_materials == model.materials.size()) return;
    st.filter_search = st.search;
    st.filter_materials = model.materials.size();
    st.filtered.clear();
    for (int i = 0; i < static_cast<int>(model.materials.size()); ++i) {
        const pmx::Material& mt = model.materials[static_cast<std::size_t>(i)];
        if (st.search.empty() ||
            pmxui::match_filter(st.search, mt.name, mt.name_en,
                                pmx::name_zh(pmx::NameKind::Material, mt.name, mt.name_en)))
            st.filtered.push_back(i);
    }
}

std::string material_label(const pmx::Model& model, int index) {
    if (index < 0 || index >= static_cast<int>(model.materials.size())) return "（无）";
    const pmx::Material& mt = model.materials[static_cast<std::size_t>(index)];
    const std::string label =
        pmx::name_with_zh(pmx::NameKind::Material, mt.name, mt.name_en);
    char num[16];
    std::snprintf(num, sizeof(num), "%02d · ", index);
    return std::string(num) + (label.empty() ? "未命名材质" : label);
}

// 每个材质的 [起始面, 面数)，均以三角面为单位。
void material_spans(const pmx::Model& model, std::vector<int>& starts, std::vector<int>& counts) {
    starts.assign(model.materials.size(), 0);
    counts.assign(model.materials.size(), 0);
    int acc = 0;
    for (std::size_t i = 0; i < model.materials.size(); ++i) {
        const int cnt = std::max(0, model.materials[i].face_count) / 3;
        starts[i] = acc;
        counts[i] = cnt;
        acc += cnt;
    }
}

void reset_range(Viewer& v, FacePanelState& st) {
    st.page = 0;
    st.start = 0;
    st.count = 0;
    if (st.material < 0) return;
    int start = 0;
    int faces = 0;
    pmxdoc::material_face_range(v.model, st.material, &start, &faces);
    if (faces > 0) st.count = 1;
}

void select_material(Viewer& v, FacePanelState& st, int index) {
    const int nmat = static_cast<int>(v.model.materials.size());
    if (index < 0 || index >= nmat) return;
    st.material = index;
    if (st.dst < 0 || st.dst >= nmat || st.dst == index)
        st.dst = nmat > 1 ? (index + 1) % nmat : -1;
    reset_range(v, st);
    v.select(SelKind::Material, index);
    st.last_material_sel = index;
}

// 删/移之后源材质的面数变少，把表单范围收回到合法区间。
void clamp_range(const pmx::Model& model, FacePanelState& st) {
    int start = 0;
    int faces = 0;
    pmxdoc::material_face_range(model, st.material, &start, &faces);
    if (faces <= 0) {
        st.start = 0;
        st.count = 0;
        return;
    }
    st.start = std::clamp(st.start, 0, faces - 1);
    st.count = std::clamp(st.count, 1, faces - st.start);
}

void move_faces(Viewer& v, FacePanelState& st) {
    int start = 0;
    int faces = 0;
    pmxdoc::material_face_range(v.model, st.material, &start, &faces);
    if (faces <= 0 || st.dst < 0 || st.dst == st.material) return;
    const int from = std::clamp(st.start, 0, faces - 1);
    const int count = std::min(st.count, faces - from);
    if (count <= 0) return;

    v.push_undo("移动面到材质");
    const int moved = pmxdoc::reassign_faces(v.model, st.material, from, count, st.dst);
    v.clamp_selection();
    v.touched("structure");
    if (moved > 0) {
        v.status = "已移动 " + std::to_string(moved) + " 个面到材质 " +
                   std::to_string(st.dst);
    }
    clamp_range(v.model, st);
}

void delete_faces(Viewer& v, FacePanelState& st) {
    int start = 0;
    int faces = 0;
    pmxdoc::material_face_range(v.model, st.material, &start, &faces);
    if (faces <= 0) return;
    const int from = std::clamp(st.start, 0, faces - 1);
    const int count = std::min(st.count, faces - from);
    if (count <= 0) return;

    const std::size_t a = static_cast<std::size_t>(start + from) * 3;
    const std::size_t b = a + static_cast<std::size_t>(count) * 3;
    if (b > v.model.indices.size()) return;

    v.push_undo("删除面");
    auto& indices = v.model.indices;
    indices.erase(indices.begin() + static_cast<std::ptrdiff_t>(a),
                  indices.begin() + static_cast<std::ptrdiff_t>(b));
    pmx::Material& mt = v.model.materials[static_cast<std::size_t>(st.material)];
    mt.face_count = std::max(0, mt.face_count - count * 3);
    pmxdoc::recompute_face_counts(v.model);

    // 被删掉的面不再存在时清掉选择；其余情况按新面数收敛。
    if (v.sel.kind == SelKind::Face && v.sel.index >= start + from &&
        v.sel.index < start + from + count)
        v.select(SelKind::None, -1);
    v.clamp_selection();
    v.touched("structure");
    v.status = "已删除 " + std::to_string(count) + " 个面";
    clamp_range(v.model, st);
}

}  // namespace

void panel_face(Viewer& v) {
    FacePanelState& st = state();
    const pmx::Model& model = v.model;
    const int nmat = static_cast<int>(model.materials.size());

    if (nmat == 0) {
        st.material = -1;
        st.dst = -1;
        ImGui::TextDisabled("未载入模型");
        return;
    }

    // 外部选中材质（例如材质页）时同步当前材质。
    if (v.sel.kind == SelKind::Material && v.sel.index != st.last_material_sel) {
        st.last_material_sel = v.sel.index;
        if (v.sel.index >= 0 && v.sel.index < nmat) {
            st.material = v.sel.index;
            if (st.dst < 0 || st.dst >= nmat || st.dst == st.material)
                st.dst = nmat > 1 ? (st.material + 1) % nmat : -1;
            reset_range(v, st);
        }
    }
    if (st.material < 0 || st.material >= nmat) {
        st.material = 0;
        st.dst = nmat > 1 ? 1 : -1;
        reset_range(v, st);
    }
    if (st.dst < 0 || st.dst >= nmat)
        st.dst = nmat > 1 ? (st.material + 1) % nmat : -1;

    ImGui::Text("共 %zu 个三角面 · %d 个材质", model.indices.size() / 3, nmat);

    ImGui::SetNextItemWidth(pmxui::scale(-96.0f));
    if (ImGui::InputTextWithHint("##fsearch", "搜索材质名 / 中文 / 英文名", &st.search))
        st.page = 0;
    ImGui::SameLine();
    if (ImGui::Button("清除")) {
        st.search.clear();
        st.page = 0;
    }
    ensure_material_filter(model, st);

    std::vector<int> starts;
    std::vector<int> counts;
    material_spans(model, starts, counts);

    ImGui::SeparatorText("材质");
    ImGui::BeginChild("##matlist", ImVec2(0, pmxui::scale(150.0f)),
                      ImGuiChildFlags_Borders | ImGuiChildFlags_ResizeY);
    if (st.filtered.empty()) {
        ImGui::TextDisabled("无匹配结果");
    } else {
        ImGuiListClipper clipper;
        clipper.Begin(static_cast<int>(st.filtered.size()));
        while (clipper.Step()) {
            for (int r = clipper.DisplayStart; r < clipper.DisplayEnd; ++r) {
                const int i = st.filtered[static_cast<std::size_t>(r)];
                const std::size_t mi = static_cast<std::size_t>(i);
                const pmx::Material& mt = model.materials[mi];
                const std::string base = pmxui::base_name(mt.name, mt.name_en);
                char head[24];
                std::snprintf(head, sizeof(head), "%02d · ", i);
                const std::string row = std::string(head) +
                                        (base.empty() ? "未命名材质" : base) + "   起 " +
                                        std::to_string(starts[mi]) + " · " +
                                        std::to_string(counts[mi]) + " 面";
                const std::string zh = pmxui::zh_only(pmx::NameKind::Material, mt.name,
                                                      mt.name_en);
                const std::string row_id = "face_mat" + std::to_string(i);
                if (counts[mi] <= 0)
                    ImGui::PushStyleColor(ImGuiCol_Text,
                                          ImGui::GetStyleColorVec4(ImGuiCol_TextDisabled));
                if (pmxui::zh_row(row_id.c_str(), row, zh, i == st.material))
                    select_material(v, st, i);
                if (counts[mi] <= 0) ImGui::PopStyleColor();
            }
        }
    }
    ImGui::EndChild();

    int fstart = 0;
    int fcount = 0;
    pmxdoc::material_face_range(model, st.material, &fstart, &fcount);
    if (fcount < 0) fcount = 0;
    ImGui::Text("当前材质 %s · 面区间 起 %d · %d 个", material_label(model, st.material).c_str(),
                fstart, fcount);

    if (fcount > 0) {
        st.start = std::clamp(st.start, 0, fcount - 1);
        st.count = std::clamp(st.count, 1, fcount - st.start);
    } else {
        st.start = 0;
        st.count = 0;
    }

    ImGui::SeparatorText("面列表");
    const int pages = std::max(1, (fcount + kFacePageSize - 1) / kFacePageSize);
    st.page = std::clamp(st.page, 0, pages - 1);
    ImGui::Text("第 %d / %d 页 · 每页 %d 个面", st.page + 1, pages, kFacePageSize);
    ImGui::BeginDisabled(st.page <= 0);
    if (ImGui::Button("上一页")) --st.page;
    ImGui::EndDisabled();
    ImGui::SameLine();
    ImGui::BeginDisabled(st.page + 1 >= pages);
    if (ImGui::Button("下一页")) ++st.page;
    ImGui::EndDisabled();

    ImGui::BeginChild("##facelist", ImVec2(0, pmxui::scale(170.0f)),
                      ImGuiChildFlags_Borders | ImGuiChildFlags_ResizeY);
    if (fcount == 0) {
        ImGui::TextDisabled("该材质没有面");
    } else {
        const int begin = st.page * kFacePageSize;
        const int end = std::min(fcount, begin + kFacePageSize);
        for (int r = begin; r < end; ++r) {
            const std::size_t base = static_cast<std::size_t>(fstart + r) * 3;
            if (base + 2 >= model.indices.size()) break;
            const unsigned a = static_cast<unsigned>(model.indices[base]);
            const unsigned b = static_cast<unsigned>(model.indices[base + 1]);
            const unsigned c = static_cast<unsigned>(model.indices[base + 2]);
            char row[128];
            std::snprintf(row, sizeof(row), "面 %d  顶点 %u / %u / %u", r, a, b, c);
            const int global = fstart + r;
            const bool selected = v.sel.kind == SelKind::Face && v.sel.index == global;
            if (ImGui::Selectable(row, selected)) v.select(SelKind::Face, global);
        }
    }
    ImGui::EndChild();

    ImGui::SeparatorText("详细信息");
    const int face = v.sel.kind == SelKind::Face ? v.sel.index : -1;
    const bool face_ok =
        face >= 0 && static_cast<std::size_t>(face) * 3 + 2 < model.indices.size();
    if (!face_ok) {
        ImGui::TextDisabled("未选择面");
    } else {
        const std::size_t base = static_cast<std::size_t>(face) * 3;
        int face_mat = -1;
        for (std::size_t mi = 0; mi < starts.size(); ++mi) {
            if (face >= starts[mi] && face < starts[mi] + counts[mi]) {
                face_mat = static_cast<int>(mi);
                break;
            }
        }
        const int rel = face - (face_mat >= 0 ? starts[static_cast<std::size_t>(face_mat)] : 0);
        ImGui::Text("面 %d（材质内第 %d 个）", face, rel);
        if (face_mat >= 0) {
            const pmx::Material& mt =
                model.materials[static_cast<std::size_t>(face_mat)];
            std::string label = pmx::name_with_zh(pmx::NameKind::Material, mt.name, mt.name_en);
            if (label.empty()) label = "未命名材质";
            ImGui::Text("材质 %d「%s」", face_mat, label.c_str());
        } else
            ImGui::TextDisabled("材质未定");
        ImGui::Text("三个顶点索引 %u / %u / %u",
                    static_cast<unsigned>(model.indices[base]),
                    static_cast<unsigned>(model.indices[base + 1]),
                    static_cast<unsigned>(model.indices[base + 2]));
        for (int k = 0; k < 3; ++k) {
            const std::uint32_t vi = model.indices[base + static_cast<std::size_t>(k)];
            if (vi < model.vertices.pos.size()) {
                const pmx::Vec3& p = model.vertices.pos[vi];
                ImGui::Text("v%u  (%.4f, %.4f, %.4f)", vi, p.x, p.y, p.z);
            } else {
                ImGui::TextDisabled("v%u  （越界）", vi);
            }
        }
    }

    ImGui::SeparatorText("重分配");
    ImGui::TextDisabled("移到目标材质的面会追加在它原有面之后");

    ImGui::SetNextItemWidth(pmxui::scale(-96.0f));
    if (ImGui::BeginCombo("源材质", material_label(model, st.material).c_str())) {
        for (int i = 0; i < nmat; ++i) {
            const bool selected = i == st.material;
            if (ImGui::Selectable(material_label(model, i).c_str(), selected))
                select_material(v, st, i);
            if (selected) ImGui::SetItemDefaultFocus();
        }
        ImGui::EndCombo();
    }

    ImGui::SetNextItemWidth(pmxui::scale(120.0f));
    ImGui::InputInt("起始面", &st.start, 1, 10);
    ImGui::SetNextItemWidth(pmxui::scale(120.0f));
    ImGui::InputInt("数量", &st.count, 1, 10);
    if (fcount > 0) {
        st.start = std::clamp(st.start, 0, fcount - 1);
        st.count = std::clamp(st.count, 1, fcount - st.start);
    } else {
        st.start = 0;
        st.count = 0;
    }

    ImGui::SetNextItemWidth(pmxui::scale(-96.0f));
    if (ImGui::BeginCombo("目标材质", material_label(model, st.dst).c_str())) {
        for (int i = 0; i < nmat; ++i) {
            const bool selected = i == st.dst;
            if (ImGui::Selectable(material_label(model, i).c_str(), selected)) st.dst = i;
            if (selected) ImGui::SetItemDefaultFocus();
        }
        ImGui::EndCombo();
    }

    const pmx::Material& src_mt = model.materials[static_cast<std::size_t>(st.material)];
    const std::string src_label =
        pmx::name_with_zh(pmx::NameKind::Material, src_mt.name, src_mt.name_en);
    const std::string src_text = src_label.empty() ? "未命名材质" : src_label;

    std::string note;
    bool can_move = false;
    if (st.dst < 0 || st.dst >= nmat) {
        note = "请选择目标材质。";
    } else if (st.dst == st.material) {
        note = "源材质与目标材质相同，无法移动。";
    } else if (fcount <= 0) {
        note = "当前材质没有可移动的面。";
    } else {
        const std::string span =
            st.count == 1 ? "第 " + std::to_string(st.start + 1) + " 个面"
                          : "第 " + std::to_string(st.start + 1) + "–" +
                                std::to_string(st.start + st.count) + " 个面";
        const std::string& dst_name = model.materials[static_cast<std::size_t>(st.dst)].name;
        const std::string dst_label = pmx::name_with_zh(
            pmx::NameKind::Material, dst_name,
            model.materials[static_cast<std::size_t>(st.dst)].name_en);
        note = src_text + "：" + span + " → " +
               (dst_label.empty() ? std::string("未命名材质") : dst_label);
        can_move = true;
    }
    ImGui::TextWrapped("%s", note.c_str());

    ImGui::BeginDisabled(!can_move);
    if (ImGui::Button("移动这些面")) move_faces(v, st);
    ImGui::EndDisabled();
    ImGui::SameLine();
    ImGui::BeginDisabled(fcount <= 0);
    if (ImGui::Button("删除这些面")) delete_faces(v, st);
    ImGui::EndDisabled();
}
