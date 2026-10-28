// 顶点页：位置、法线、UV、边缩放与蒙皮权重。
//
// 对齐 Python 版 panels/vertex.py 的字段与提示；区别是这里直接绑定模型
// （拖动即写入，v.edit 负责快照与结构刷新），并用分页列表代替「索引微调框」，
// 避免百万级顶点一次性渲染。所有写入都走 "structure"（几何会重传网格）。
#include "app/panels.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <string>
#include <vector>

#include <imgui.h>

#include "app/panels/common.hpp"
#include "core/pmx.hpp"

namespace {

constexpr int kPageSize = 200;

const char* kWeightNames[] = {"BDEF1", "BDEF2", "BDEF4", "SDEF", "QDEF"};

const char* weight_type_name(int t) {
    return (t >= 0 && t < 5) ? kWeightNames[t] : kWeightNames[0];
}

// Python 版 _sync_wtype 的分支：BDEF1 一根、BDEF2/SDEF 两根、BDEF4/QDEF 四根。
int weight_slots(int wt) {
    if (wt == pmx::WT_BDEF1) return 1;
    if (wt == pmx::WT_BDEF2 || wt == pmx::WT_SDEF) return 2;
    return 4;
}

struct VertexPanelState {
    std::string search;
    std::string filter_search;
    std::size_t filter_count = 0;
    std::vector<int> filtered;
    int page = 0;
    int jump = 0;
    int last_sel = -1;
    bool scroll_sel = false;

    std::size_t stats_count = 0;
    bool stats_dirty = true;
    std::string stats;

    int member_vertex = -1;
    std::size_t member_indices = 0;
    std::size_t member_materials = 0;
    std::string member;
};

VertexPanelState& state() {
    static VertexPanelState s;
    return s;
}

// 搜索只匹配十进制顶点号（列表可能很大，只在搜索内容变化时重建一次）。
void ensure_filter(const pmx::Model& model, VertexPanelState& st) {
    const std::size_t n = model.vertices.pos.size();
    if (st.filter_search == st.search && st.filter_count == n) return;
    st.filter_search = st.search;
    st.filter_count = n;
    st.filtered.clear();
    if (st.search.empty()) return;
    const std::string needle = pmxui::lower_copy(st.search);
    for (std::size_t i = 0; i < n; ++i) {
        if (std::to_string(i).find(needle) != std::string::npos)
            st.filtered.push_back(static_cast<int>(i));
    }
}

std::string bone_label(const pmx::Model& model, int index) {
    if (index < 0 || index >= static_cast<int>(model.bones.size())) return "（无）";
    char buf[192];
    const std::string& name = model.bones[static_cast<std::size_t>(index)].name;
    std::snprintf(buf, sizeof(buf), "%03d · %s", index,
                  name.empty() ? "未命名" : name.c_str());
    return buf;
}

// 找出顶点所属的第一个面及材质；结果按「顶点号 + indices/材料数量」缓存。
void update_membership(const pmx::Model& model, VertexPanelState& st, int vi) {
    if (vi < 0) return;
    if (st.member_vertex == vi && st.member_indices == model.indices.size() &&
        st.member_materials == model.materials.size())
        return;
    st.member_vertex = vi;
    st.member_indices = model.indices.size();
    st.member_materials = model.materials.size();

    const auto& indices = model.indices;
    for (std::size_t f = 0; f + 2 < indices.size(); f += 3) {
        if (static_cast<int>(indices[f]) == vi || static_cast<int>(indices[f + 1]) == vi ||
            static_cast<int>(indices[f + 2]) == vi) {
            const int face = static_cast<int>(f / 3);
            int acc = 0;
            int mat = -1;
            for (std::size_t mi = 0; mi < model.materials.size(); ++mi) {
                const int cnt = std::max(0, model.materials[mi].face_count) / 3;
                if (face < acc + cnt) {
                    mat = static_cast<int>(mi);
                    break;
                }
                acc += cnt;
            }
            char buf[256];
            if (mat >= 0) {
                const std::string& nm = model.materials[static_cast<std::size_t>(mat)].name;
                std::snprintf(buf, sizeof(buf), "材质 %d「%s」· 面 %d", mat,
                              nm.empty() ? "未命名材质" : nm.c_str(), face);
            } else {
                std::snprintf(buf, sizeof(buf), "面 %d（材质未定）", face);
            }
            st.member = buf;
            return;
        }
    }
    st.member = "未被任何面引用";
}

std::string compute_stats(const pmx::Model& model) {
    const pmx::VertexData& verts = model.vertices;
    const std::size_t n = verts.pos.size();
    if (n == 0) return "未载入模型";
    int counts[5] = {0, 0, 0, 0, 0};
    int bad = 0;
    int orphan = 0;
    for (std::size_t i = 0; i < n; ++i) {
        const int wt = i < verts.wtype.size() ? static_cast<int>(verts.wtype[i]) : 0;
        if (wt >= 0 && wt < 5) ++counts[wt];
        if (wt != pmx::WT_SDEF && i < verts.weights.size()) {
            float sum = 0.0f;
            for (float w : verts.weights[i]) sum += w;
            if (sum < 0.999f) ++bad;
        }
        if (wt != pmx::WT_SDEF && i < verts.bones.size() && verts.bones[i][0] < 0) ++orphan;
    }
    std::string out = "顶点 " + std::to_string(n) + " 个";
    for (int t = 0; t < 5; ++t) {
        if (counts[t] == 0) continue;
        out += std::string(" · ") + kWeightNames[t] + " " + std::to_string(counts[t]);
    }
    if (bad) out += " · 权重和不足 " + std::to_string(bad);
    if (orphan) out += " · 无主骨骼 " + std::to_string(orphan);
    return out;
}

void draw_detail(Viewer& v, VertexPanelState& st, int si) {
    const pmx::Model& model = v.model;
    const pmx::VertexData& verts = model.vertices;
    const bool data_ok = si >= 0 && si < static_cast<int>(verts.pos.size()) &&
                         si < static_cast<int>(verts.nrm.size()) &&
                         si < static_cast<int>(verts.uv.size());

    ImGui::SeparatorText("属性");
    if (!data_ok) {
        ImGui::TextDisabled(si < 0 ? "未选择顶点" : "顶点数据不完整");
    } else {
        std::array<float, 3> pos{verts.pos[si].x, verts.pos[si].y, verts.pos[si].z};
        if (ImGui::DragFloat3("位置", pos.data(), 0.01f, 0.0f, 0.0f, "%.4f")) {
            v.edit("修改顶点位置",
                   [si, pos](pmx::Model& m) {
                       if (si < static_cast<int>(m.vertices.pos.size()))
                           m.vertices.pos[si] = pmx::Vec3{pos[0], pos[1], pos[2]};
                   },
                   "structure", std::string("vtx_pos:") + std::to_string(si));
        }
        std::array<float, 3> nrm{verts.nrm[si].x, verts.nrm[si].y, verts.nrm[si].z};
        if (ImGui::DragFloat3("法线", nrm.data(), 0.01f, 0.0f, 0.0f, "%.4f")) {
            v.edit("修改顶点法线",
                   [si, nrm](pmx::Model& m) {
                       if (si < static_cast<int>(m.vertices.nrm.size()))
                           m.vertices.nrm[si] = pmx::Vec3{nrm[0], nrm[1], nrm[2]};
                   },
                   "structure", std::string("vtx_nrm:") + std::to_string(si));
        }
        std::array<float, 2> uv{verts.uv[si].x, verts.uv[si].y};
        if (ImGui::DragFloat2("UV", uv.data(), 0.001f, -99999.0f, 99999.0f, "%.5f")) {
            v.edit("修改顶点 UV",
                   [si, uv](pmx::Model& m) {
                       if (si < static_cast<int>(m.vertices.uv.size()))
                           m.vertices.uv[si] = pmx::Vec2{uv[0], uv[1]};
                   },
                   "structure", std::string("vtx_uv:") + std::to_string(si));
        }
        float edge = si < static_cast<int>(verts.edge.size()) ? verts.edge[si] : 0.0f;
        if (ImGui::DragFloat("边缩放", &edge, 0.01f, 0.0f, 1000.0f, "%.5f")) {
            v.edit("修改边缩放",
                   [si, edge](pmx::Model& m) {
                       if (si < static_cast<int>(m.vertices.edge.size()))
                           m.vertices.edge[si] = edge;
                   },
                   "structure", std::string("vtx_edge:") + std::to_string(si));
        }
    }

    ImGui::SeparatorText("蒙皮");
    if (!data_ok) {
        ImGui::TextDisabled(si < 0 ? "未选择顶点" : "顶点数据不完整");
        ImGui::SeparatorText("诊断");
        ImGui::TextWrapped("%s", st.stats.c_str());
        return;
    }

    int wt = si < static_cast<int>(verts.wtype.size()) ? static_cast<int>(verts.wtype[si]) : 0;
    if (wt < 0 || wt >= 5) wt = 0;
    ImGui::SetNextItemWidth(pmxui::scale(-96.0f));
    if (ImGui::BeginCombo("权重类型", weight_type_name(wt))) {
        for (int t = 0; t < 5; ++t) {
            const bool selected = t == wt;
            if (ImGui::Selectable(kWeightNames[t], selected)) {
                v.edit("修改权重类型",
                       [si, t](pmx::Model& m) {
                           if (si >= static_cast<int>(m.vertices.wtype.size())) return;
                           m.vertices.wtype[si] = static_cast<std::uint8_t>(t);
                           if (t == pmx::WT_BDEF1 &&
                               si < static_cast<int>(m.vertices.weights.size()))
                               m.vertices.weights[si] = {1.0f, 0.0f, 0.0f, 0.0f};
                       },
                       "structure", std::string("vtx_wtype:") + std::to_string(si));
                st.stats_dirty = true;
            }
            if (selected) ImGui::SetItemDefaultFocus();
        }
        ImGui::EndCombo();
    }

    const int slots = weight_slots(wt);
    for (int k = 0; k < 4; ++k) {
        ImGui::BeginDisabled(k >= slots);
        ImGui::Text("W%d", k + 1);
        ImGui::SameLine();
        const int cur = si < static_cast<int>(verts.bones.size()) ? verts.bones[si][k] : -1;
        const std::string preview = bone_label(model, cur);
        ImGui::SetNextItemWidth(pmxui::scale(-86.0f));
        if (ImGui::BeginCombo(("##vbone" + std::to_string(k)).c_str(), preview.c_str())) {
            if (ImGui::Selectable("（无）", cur < 0)) {
                v.edit("修改顶点骨骼",
                       [si, k](pmx::Model& m) {
                           if (si < static_cast<int>(m.vertices.bones.size()))
                               m.vertices.bones[si][k] = -1;
                       },
                       "structure",
                       std::string("vtx_bone:") + std::to_string(si) + ":" + std::to_string(k));
            }
            for (int bi = 0; bi < static_cast<int>(model.bones.size()); ++bi) {
                const std::string item = bone_label(model, bi);
                if (ImGui::Selectable(item.c_str(), bi == cur)) {
                    v.edit("修改顶点骨骼",
                           [si, k, bi](pmx::Model& m) {
                               if (si < static_cast<int>(m.vertices.bones.size()))
                                   m.vertices.bones[si][k] = bi;
                           },
                           "structure",
                           std::string("vtx_bone:") + std::to_string(si) + ":" +
                               std::to_string(k));
                }
            }
            ImGui::EndCombo();
        }
        ImGui::SameLine();
        ImGui::SetNextItemWidth(pmxui::scale(76.0f));
        ImGui::BeginDisabled(wt == pmx::WT_BDEF1);
        float weight = si < static_cast<int>(verts.weights.size()) ? verts.weights[si][k] : 0.0f;
        if (ImGui::DragFloat(("##vweight" + std::to_string(k)).c_str(), &weight, 0.005f, 0.0f,
                             1.0f, "%.4f")) {
            v.edit("修改顶点权重",
                   [si, k, weight](pmx::Model& m) {
                       if (si < static_cast<int>(m.vertices.weights.size()))
                           m.vertices.weights[si][k] = weight;
                   },
                   "structure",
                   std::string("vtx_weight:") + std::to_string(si) + ":" + std::to_string(k));
        }
        ImGui::EndDisabled();
        ImGui::EndDisabled();
    }

    float sum = 0.0f;
    if (si < static_cast<int>(verts.weights.size())) {
        for (int k = 0; k < slots; ++k) sum += verts.weights[si][k];
    }
    ImGui::TextDisabled("权重和 %.4f（%s）", sum,
                        wt == pmx::WT_SDEF ? "SDEF 按前两根骨骼" : "应为 1");

    ImGui::BeginDisabled(wt != pmx::WT_SDEF);
    if (si < static_cast<int>(verts.sdef.size())) {
        const std::array<float, 9>& sd = verts.sdef[si];
        std::array<float, 3> c{sd[0], sd[1], sd[2]};
        if (ImGui::DragFloat3("中心 C", c.data(), 0.01f, 0.0f, 0.0f, "%.4f")) {
            v.edit("修改 SDEF 中心",
                   [si, c](pmx::Model& m) {
                       if (si >= static_cast<int>(m.vertices.sdef.size())) return;
                       for (int j = 0; j < 3; ++j) m.vertices.sdef[si][j] = c[j];
                   },
                   "structure", std::string("vtx_sdef_c:") + std::to_string(si));
        }
        std::array<float, 3> r0{sd[3], sd[4], sd[5]};
        if (ImGui::DragFloat3("R0", r0.data(), 0.01f, 0.0f, 0.0f, "%.4f")) {
            v.edit("修改 SDEF R0",
                   [si, r0](pmx::Model& m) {
                       if (si >= static_cast<int>(m.vertices.sdef.size())) return;
                       for (int j = 0; j < 3; ++j) m.vertices.sdef[si][3 + j] = r0[j];
                   },
                   "structure", std::string("vtx_sdef_r0:") + std::to_string(si));
        }
        std::array<float, 3> r1{sd[6], sd[7], sd[8]};
        if (ImGui::DragFloat3("R1", r1.data(), 0.01f, 0.0f, 0.0f, "%.4f")) {
            v.edit("修改 SDEF R1",
                   [si, r1](pmx::Model& m) {
                       if (si >= static_cast<int>(m.vertices.sdef.size())) return;
                       for (int j = 0; j < 3; ++j) m.vertices.sdef[si][6 + j] = r1[j];
                   },
                   "structure", std::string("vtx_sdef_r1:") + std::to_string(si));
        }
    } else {
        ImGui::TextDisabled("无 SDEF 数据");
    }
    ImGui::EndDisabled();

    ImGui::SeparatorText("诊断");
    if (ImGui::SmallButton("刷新诊断")) st.stats_dirty = true;
    ImGui::TextWrapped("%s", st.stats.c_str());
}

}  // namespace

void panel_vertex(Viewer& v) {
    VertexPanelState& st = state();
    const pmx::Model& model = v.model;
    const pmx::VertexData& verts = model.vertices;
    const int n = static_cast<int>(verts.pos.size());

    int si = v.sel.kind == SelKind::Vertex ? v.sel.index : -1;
    if (si < 0 || si >= n) si = -1;

    ImGui::Text("共 %d 个顶点", n);
    if (n == 0) {
        ImGui::TextDisabled("未载入模型");
        return;
    }

    ImGui::SeparatorText("定位");
    if (si >= 0) {
        update_membership(model, st, si);
        ImGui::Text("顶点 %d / %d", si, n);
        ImGui::TextWrapped("%s", st.member.c_str());
    } else {
        ImGui::TextDisabled("未选择顶点");
    }

    ImGui::SetNextItemWidth(pmxui::scale(-96.0f));
    if (ImGui::InputTextWithHint("##vsearch", "搜索索引（顶点号）", &st.search)) st.page = 0;
    ImGui::SameLine();
    if (ImGui::Button("清除")) {
        st.search.clear();
        st.page = 0;
    }

    ensure_filter(model, st);
    const int total = st.search.empty() ? n : static_cast<int>(st.filtered.size());

    // 外部选中（列表点击 / 视口操作）后自动翻到所在页并滚到该行。
    if (si != st.last_sel) {
        st.last_sel = si;
        st.scroll_sel = si >= 0;
        if (si >= 0) {
            int pos = si;
            if (!st.search.empty()) {
                const auto it = std::find(st.filtered.begin(), st.filtered.end(), si);
                pos = it != st.filtered.end()
                          ? static_cast<int>(it - st.filtered.begin())
                          : 0;
            }
            st.page = pos / kPageSize;
        }
    }

    ImGui::SetNextItemWidth(pmxui::scale(120.0f));
    if (ImGui::InputInt("跳转到", &st.jump, 0, 0)) st.jump = std::clamp(st.jump, 0, n - 1);
    ImGui::SameLine();
    if (ImGui::Button("前往")) {
        const int target = std::clamp(st.jump, 0, n - 1);
        if (!st.search.empty()) {
            const auto it = std::find(st.filtered.begin(), st.filtered.end(), target);
            st.page = it != st.filtered.end()
                          ? static_cast<int>(it - st.filtered.begin()) / kPageSize
                          : 0;
        } else {
            st.page = target / kPageSize;
        }
        st.last_sel = target;
        st.scroll_sel = true;
        v.select(SelKind::Vertex, target);
        si = target;
    }

    ImGui::BeginDisabled(si < 0);
    if (ImGui::Button("上一个") && si >= 0)
        v.select(SelKind::Vertex, si > 0 ? si - 1 : 0);
    ImGui::SameLine();
    if (ImGui::Button("下一个") && si >= 0)
        v.select(SelKind::Vertex, std::min(n - 1, si + 1));
    ImGui::EndDisabled();

    const int pages = std::max(1, (total + kPageSize - 1) / kPageSize);
    st.page = std::clamp(st.page, 0, pages - 1);
    ImGui::Text("第 %d / %d 页 · 共 %d 项", st.page + 1, pages, total);
    ImGui::BeginDisabled(st.page <= 0);
    if (ImGui::Button("上一页")) --st.page;
    ImGui::EndDisabled();
    ImGui::SameLine();
    ImGui::BeginDisabled(st.page + 1 >= pages);
    if (ImGui::Button("下一页")) ++st.page;
    ImGui::EndDisabled();

    ImGui::BeginChild("##vlist", ImVec2(0, pmxui::scale(170.0f)), ImGuiChildFlags_Borders);
    if (total == 0) {
        ImGui::TextDisabled("无匹配结果");
    } else {
        const int begin = st.page * kPageSize;
        const int end = std::min(total, begin + kPageSize);
        for (int r = begin; r < end; ++r) {
            const int index = st.search.empty() ? r : st.filtered[static_cast<std::size_t>(r)];
            const int wt =
                index < static_cast<int>(verts.wtype.size()) ? verts.wtype[index] : 0;
            char row[96];
            std::snprintf(row, sizeof(row), "#%d  %s", index, weight_type_name(wt));
            if (ImGui::Selectable(row, index == si)) {
                v.select(SelKind::Vertex, index);
                st.last_sel = index;
                st.scroll_sel = false;
            }
            if (index == si && st.scroll_sel) {
                ImGui::SetScrollHereY(0.5f);
                st.scroll_sel = false;
            }
        }
    }
    ImGui::EndChild();

    si = v.sel.kind == SelKind::Vertex ? v.sel.index : -1;
    if (si < 0 || si >= n) si = -1;

    if (st.stats_dirty || st.stats_count != verts.pos.size()) {
        st.stats = compute_stats(model);
        st.stats_count = verts.pos.size();
        st.stats_dirty = false;
    }

    draw_detail(v, st, si);
}
