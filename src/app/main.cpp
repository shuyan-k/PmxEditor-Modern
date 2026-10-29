// GLFW + Dear ImGui 查看器：加载 PMX / VPD，GPU 蒙皮渲染、物理演算与参数面板。
#ifdef _WIN32
// 先关掉 min/max 宏，否则 windows.h 会把 std::max 展开破坏标准库调用。
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <commdlg.h>
#include <dwmapi.h>
#endif

#include <GLFW/glfw3.h>
#include <imgui.h>
#include <imgui_impl_glfw.h>
#include <imgui_impl_opengl3.h>

#ifdef _WIN32
#define GLFW_EXPOSE_NATIVE_WIN32
#include <GLFW/glfw3native.h>
// windef.h 把 near/far 定义成空宏，会和 PMX 的 SoftBodyAnchor::near 等字段名冲突。
#undef near
#undef far
#endif

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iterator>
#include <memory>
#include <string>
#include <vector>

#include "app/camera.hpp"
#include "app/panels.hpp"
#include "app/theme.hpp"
#include "app/ui_scale.hpp"
#include "app/viewer.hpp"
#include "core/fs.hpp"
#include "core/morph.hpp"
#include "core/pmx.hpp"
#include "core/pose.hpp"
#include "core/utf8_args.hpp"
#include "core/vpd.hpp"
#include "gpu/gl_api.hpp"
#include "gpu/renderer.hpp"
#ifdef PMX_ENABLE_PHYSICS
#include "physics/physics.hpp"
#endif


// 系统文件对话框（资源管理器）的过滤器：字符串内用 \0 分隔项，末尾再补一个 \0。
const wchar_t* kPmxFilter = L"PMX 模型 (*.pmx)\0*.pmx\0所有文件 (*.*)\0*.*\0";
const wchar_t* kVpdFilter = L"VPD 姿态 (*.vpd)\0*.vpd\0所有文件 (*.*)\0*.*\0";
const wchar_t* kVmdFilter = L"VMD 动作 (*.vmd)\0*.vmd\0所有文件 (*.*)\0*.*\0";

#ifdef _WIN32
HWND g_owner = nullptr;  // 主窗口句柄，让对话框保持模态

std::wstring utf8_to_wide(const std::string& s) {
    if (s.empty()) return std::wstring();
    const int len = MultiByteToWideChar(CP_UTF8, 0, s.data(), static_cast<int>(s.size()),
                                        nullptr, 0);
    if (len <= 0) return std::wstring();
    std::wstring out(static_cast<std::size_t>(len), L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), out.data(), len);
    return out;
}

std::string wide_to_utf8(const std::wstring& s) {
    if (s.empty()) return std::string();
    const int len = WideCharToMultiByte(CP_UTF8, 0, s.data(), static_cast<int>(s.size()),
                                        nullptr, 0, nullptr, nullptr);
    if (len <= 0) return std::string();
    std::string out(static_cast<std::size_t>(len), '\0');
    WideCharToMultiByte(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), out.data(), len,
                        nullptr, nullptr);
    return out;
}

// 返回空字符串表示用户取消。
std::string pick_open_file(const wchar_t* filter, const wchar_t* title) {
    wchar_t buf[1024] = L"";
    OPENFILENAMEW ofn{};
    ofn.lStructSize = sizeof(ofn);
    ofn.hwndOwner = g_owner;
    ofn.lpstrFilter = filter;
    ofn.lpstrFile = buf;
    ofn.nMaxFile = 1024;
    ofn.lpstrTitle = title;
    ofn.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR;
    if (!GetOpenFileNameW(&ofn)) return std::string();
    return wide_to_utf8(buf);
}

std::string pick_save_file(const wchar_t* filter, const wchar_t* title,
                           const std::string& default_path, const wchar_t* def_ext) {
    wchar_t buf[1024] = L"";
    const std::wstring init = utf8_to_wide(default_path);
    if (!init.empty())
        wcsncpy_s(buf, init.c_str(), _TRUNCATE);
    OPENFILENAMEW ofn{};
    ofn.lStructSize = sizeof(ofn);
    ofn.hwndOwner = g_owner;
    ofn.lpstrFilter = filter;
    ofn.lpstrFile = buf;
    ofn.nMaxFile = 1024;
    ofn.lpstrTitle = title;
    ofn.lpstrDefExt = def_ext;
    ofn.Flags = OFN_OVERWRITEPROMPT | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR;
    if (!GetSaveFileNameW(&ofn)) return std::string();
    return wide_to_utf8(buf);
}
#else
// 非 Windows 平台没有资源管理器对话框，退回空路径（仍可用拖放）。
std::string pick_open_file(const wchar_t*, const wchar_t*) { return std::string(); }
std::string pick_save_file(const wchar_t*, const wchar_t*, const std::string&,
                           const wchar_t*) {
    return std::string();
}
#endif


namespace {

// 形态权重逐项比较：播放时只有权重变化才重建顶点形态与渲染基底。
bool same_morph_weights(const pmx::MorphWeights& a, const pmx::MorphWeights& b) {
    if (a.size() != b.size()) return false;
    for (std::size_t i = 0; i < a.size(); ++i)
        if (a[i].first != b[i].first || a[i].second != b[i].second) return false;
    return true;
}

}  // namespace


bool Viewer::load_model(const std::string& path, std::string* err) {
    try {
        model = pmx::load_pmx(path);
    } catch (const std::exception& e) {
        if (err) *err = e.what();
        return false;
    }
    pose = std::make_unique<pmx::Pose>(model);
    morph_values.assign(model.morphs.size(), 0.0f);
    morph_weights.clear();
    morph_dirty = true;
    // 换模型后旧的 VMD 绑定失效，动作随之清空。
    motion.reset();
    motion_binding = pmx::VmdBinding{};
    motion_frame = 0.0f;
    motion_playing = false;
    motion_dirty = false;
    vmd_path.clear();
    clear_manual_pose();
    select(SelKind::None, -1);
    undo_stack.clear();
    redo_stack.clear();
    last_coalesce.clear();
    dirty = false;
    model_path = path;

    if (!renderer.upload_model(model, err)) return false;
    {
        pmx::VertexMorphResult vm = pmx::apply_vertex_morphs(model, morph_weights);
        renderer.update_base(model, vm);
    }

    fit_camera();  // 相机自动取景
#ifdef PMX_ENABLE_PHYSICS
    physics.release();
    if (!physics.build(model)) status = "物理构建失败：" + physics.error;
    physics_enabled = false;
    physics.enabled = false;
#endif
    status = "已加载 " + path;
    return true;
}

void Viewer::apply_morphs() {
    const std::unordered_map<int, float> resolved =
        pmx::resolve_morph_weights(model, morph_weights);
    pmx::MorphWeights weights(resolved.begin(), resolved.end());
    pmx::VertexMorphResult vm = pmx::apply_vertex_morphs(model, weights);
    renderer.update_base(model, vm);
    if (pose) pose->apply(&weights);
    morph_dirty = false;
}

void Viewer::reset_physics() {
#ifdef PMX_ENABLE_PHYSICS
    if (!physics_ptr) return;
    physics.gravity = gravity;
    physics.iterations = iterations;
    physics.ground = ground;
    physics.set_params(gravity, iterations);
    physics.enabled = physics_enabled;
    if (physics_enabled && pose) {
        apply_morphs();
        physics.reset(*pose, &morph_weights, true);
    }
#endif
}

void Viewer::settle_physics() {
#ifdef PMX_ENABLE_PHYSICS
    if (!physics_ptr || !physics_enabled) return;
    physics.clear_velocities();
#endif
}

pmx::Selection Viewer::pick_at(float sx, float sy, int fb_w, int fb_h, int kinds) {
    if (!pose) return pmx::Selection{};
    return renderer.pick(model, *pose, physics_ptr, camera.view(),
                         camera.projection(static_cast<float>(fb_w) /
                                           static_cast<float>(std::max(1, fb_h))),
                         fb_w, fb_h, sx, sy, 12.0f, kinds);
}

std::vector<pmx::Selection> Viewer::pick_candidates_at(float sx, float sy, int fb_w, int fb_h,
                                                       int kinds) {
    if (!pose) return {};
    return renderer.pick_candidates(
        model, *pose, physics_ptr, camera.view(),
        camera.projection(static_cast<float>(fb_w) / static_cast<float>(std::max(1, fb_h))), fb_w,
        fb_h, sx, sy, 12.0f, kinds);
}

void Viewer::apply_pick(const pmx::Selection& hit) {
    if (hit.kind == pmx::Selection::NONE) {
        if (sel.kind != SelKind::None) {
            select(SelKind::None, -1);
            status = "取消选择";
        }
        reveal_selection = false;
        reveal_frames = 0;
        focus_overlay = false;
        return;
    }
    if (hit.kind == pmx::Selection::BONE) {
        select(SelKind::Bone, hit.index);
        reveal_tab = "骨骼";
        status = preview_mode
                     ? "已选中「" + bone_name(hit.index) + "」：左键拖动位移 · 右键拖动旋转"
                     : "已选中「" + bone_name(hit.index) + "」：摆姿请切到预览模式（Ctrl+M）";
    } else if (hit.kind == pmx::Selection::RIGID) {
        select(SelKind::Rigid, hit.index);
        reveal_tab = "物理";
        status = "已选中刚体「" + model.rigid[static_cast<std::size_t>(hit.index)].name + "」";
    } else {
        select(SelKind::Joint, hit.index);
        reveal_tab = "物理";
        status = "已选中关节「" + model.joints[static_cast<std::size_t>(hit.index)].name + "」";
    }
    // 切面板要等下一帧生效，保持两帧让 SetSelected 与滚动都落地。
    reveal_frames = 2;
    reveal_selection = true;
    // 骨骼/刚体/关节被整体隐藏时，这一项临时显示并高亮，取消选择后恢复。
    focus_overlay = true;
}

void Viewer::draw_pick_choices() {
    if (pick_choices.empty()) return;

    auto label_of = [this](const pmx::Selection& c) {
        if (c.kind == pmx::Selection::BONE) {
            const std::string name = bone_name(c.index);
            return "骨骼  " + (name.empty() ? "#" + std::to_string(c.index) : name);
        }
        if (c.kind == pmx::Selection::RIGID) {
            const std::string& name = model.rigid[static_cast<std::size_t>(c.index)].name;
            return "刚体  " + (name.empty() ? "#" + std::to_string(c.index) : name);
        }
        const std::string& name = model.joints[static_cast<std::size_t>(c.index)].name;
        return "关节  " + (name.empty() ? "#" + std::to_string(c.index) : name);
    };

    // 真正的 ImGui Popup：点外部自动关闭，也不会被工作区其它窗口抢走点击。
    if (pick_choice_frame == ImGui::GetFrameCount()) ImGui::OpenPopup("###pmx_pick_choices");
    ImGui::SetNextWindowPos(ImVec2(pick_choice_pos[0] + 8.0f, pick_choice_pos[1] + 8.0f),
                            ImGuiCond_Always);
    ImGui::SetNextWindowBgAlpha(0.96f);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding, ImVec2(pmxui::scale(8.0f),
                                                            pmxui::scale(6.0f)));
    if (ImGui::BeginPopup("###pmx_pick_choices")) {
        ImGui::TextDisabled("选择对象（%d 个重叠）", static_cast<int>(pick_choices.size()));
        ImGui::Separator();
        int chosen = -1;
        for (std::size_t i = 0; i < pick_choices.size(); ++i) {
            // 名称可能重复，追加编号保证控件 ID 唯一。
            const std::string label = label_of(pick_choices[i]) + "##" + std::to_string(i);
            if (ImGui::Selectable(label.c_str())) chosen = static_cast<int>(i);
        }
        ImGui::Separator();
        ImGui::TextDisabled("Esc 或点击空白处取消");
        if (chosen >= 0) {
            apply_pick(pick_choices[static_cast<std::size_t>(chosen)]);
            pick_choices.clear();
            ImGui::CloseCurrentPopup();
        } else if (ImGui::IsKeyPressed(ImGuiKey_Escape, false)) {
            pick_choices.clear();
            ImGui::CloseCurrentPopup();
        }
        ImGui::EndPopup();
    } else if (pick_choice_frame != ImGui::GetFrameCount()) {
        pick_choices.clear();  // 点击外部时 popup 已自动关闭
    }
    ImGui::PopStyleVar();
}

const char* Viewer::bone_drag_block(int index, bool move) const {
    if (index < 0 || index >= static_cast<int>(model.bones.size())) return "不可操作";
    const std::uint16_t flags = model.bones[static_cast<std::size_t>(index)].flags;
    if (!(flags & pmx::BF_ENABLED)) return "不可操作";
    if (move && !(flags & pmx::BF_TRANSLATABLE)) return "不可移动";
    if (!move && !(flags & pmx::BF_ROTATABLE)) return "不可旋转";
    return "";
}

std::string Viewer::bone_name(int index) const {
    if (index < 0 || index >= static_cast<int>(model.bones.size())) return std::string();
    return model.bones[static_cast<std::size_t>(index)].name;
}

void Viewer::fit_camera() {
    if (model.vertices.pos.empty()) return;
    pmx::Vec3 lo = model.vertices.pos[0], hi = lo;
    for (const pmx::Vec3& p : model.vertices.pos) {
        lo.x = std::min(lo.x, p.x); lo.y = std::min(lo.y, p.y); lo.z = std::min(lo.z, p.z);
        hi.x = std::max(hi.x, p.x); hi.y = std::max(hi.y, p.y); hi.z = std::max(hi.z, p.z);
    }
    camera.fit(lo, hi);
}

Viewer::PoseEntry Viewer::capture_pose() const {
    PoseEntry e;
    if (!pose) return e;
    e.base_rot = pose->base_rot;
    e.base_trans = pose->base_trans;
    e.ov_rot = pose->ov_rot;
    e.ov_trans = pose->ov_trans;
    e.ik_enabled = pose->ik_enabled;
    e.weights = morph_weights;
    e.values = morph_values;
    return e;
}

void Viewer::reset_pose() {
    if (!pose) return;
    push_pose_undo("重置姿态");
    clear_manual_pose();
    pose->reset();
    pose->solve_ik();
    pose->world();
    status = "已重置姿态";
}

bool Viewer::save_model(const std::string& path, std::string* err) {
    try {
        pmx::save_pmx(model, path);
        model_path = path;
        clear_dirty();
        status = "已保存 " + path;
        return true;
    } catch (const std::exception& e) {
        if (err) *err = e.what();
        return false;
    }
}

void Viewer::handle_shortcuts() {
    ImGuiIO& io = ImGui::GetIO();
    if (io.WantTextInput) return;
    if (io.KeyCtrl && ImGui::IsKeyPressed(ImGuiKey_M, false)) set_preview_mode(!preview_mode);
    if (ImGui::IsKeyPressed(ImGuiKey_F, false) && !io.KeyCtrl) fit_camera();
    if (ImGui::IsKeyPressed(ImGuiKey_R, false) && !io.KeyCtrl) reset_pose();
    if (ImGui::IsKeyPressed(ImGuiKey_P, false) && !io.KeyCtrl) {
        physics_enabled = !physics_enabled;
        reset_physics();
    }
    // 撤销 / 重做两种模式都可用：预览模式只允许撤销姿态条目，数据快照会被 undo() 拦下。
    if (io.KeyCtrl && ImGui::IsKeyPressed(ImGuiKey_Z, false)) {
        if (io.KeyShift) redo();
        else undo();
    }
    if (io.KeyCtrl && ImGui::IsKeyPressed(ImGuiKey_Y, false)) redo();
    // 预览模式模型只读：保存不可用（载入模型仍然允许）。
    if (!preview_mode) {
        const bool ctrl_s = io.KeyCtrl && ImGui::IsKeyPressed(ImGuiKey_S, false);
        if (ctrl_s && !model_path.empty() && !io.KeyShift) {
            std::string err;
            if (!save_model(model_path, &err)) error = err;
        } else if (ctrl_s) {
            const std::string target = pick_save_file(
                kPmxFilter, L"另存为 PMX 模型",
                model_path.empty() ? std::string() : model_path, L"pmx");
            if (!target.empty()) {
                std::string err;
                if (!save_model(target, &err)) error = err;
            }
        }
    }
    if (io.KeyCtrl && ImGui::IsKeyPressed(ImGuiKey_O, false)) {
        const std::string path = pick_open_file(kPmxFilter, L"打开 PMX 模型");
        if (!path.empty()) {
            std::string err;
            if (load_model(path, &err)) error.clear();
            else error = err;
        }
    }
}

void Viewer::handle_input(GLFWwindow* window, int fb_w, int fb_h) {
    ImGuiIO& io = ImGui::GetIO();
    (void)window;
    if (io.WantCaptureMouse) {
        drag_mode = DRAG_NONE;
        drag_bone = -1;
        return;
    }
    const float scale_x = fb_w > 0 ? static_cast<float>(fb_w) / std::max(1.0f, io.DisplaySize.x) : 1.0f;
    const float scale_y = fb_h > 0 ? static_cast<float>(fb_h) / std::max(1.0f, io.DisplaySize.y) : 1.0f;
    const float mx = io.MousePos.x * scale_x;
    const float my = io.MousePos.y * scale_y;

    // 双击帧同时会触发 IsMouseClicked：先判双击，避免多压一条空撤销记录。
    const bool double_click = ImGui::IsMouseDoubleClicked(ImGuiMouseButton_Left);

    // PmxEditor 把「改数据」与「试姿态」分开：预览模式相当于 TransformView（负责摆姿），
    // 编辑模式相当于 PmxView（只改数据，不做临时变换）。因此拖动骨骼只在预览模式生效。
    const bool can_pose = preview_mode;

    // ---- 按下：已选中的骨骼才可拖动，否则只操作视角
    if (ImGui::IsMouseClicked(ImGuiMouseButton_Left) && !double_click) {
        const pmx::Selection hit = pick_at(mx, my, fb_w, fb_h, pmx::PICK_BONE);
        if (can_pose && hit.kind == pmx::Selection::BONE &&
            selection.kind == pmx::Selection::BONE && selection.index == hit.index && pose &&
            !bone_drag_block(hit.index, true)[0]) {
            drag_mode = DRAG_MOVE;  // 左键位移（含 IK 控制器）
            drag_bone = hit.index;
            drag_moved = false;     // 撤销记录 / 取消动作都推迟到真正产生位移
        } else {
            if (hit.kind == pmx::Selection::BONE && !can_pose)
                status = "编辑模式只改数据；摆骨骼请切到预览模式（Ctrl+M）";
            else if (hit.kind == pmx::Selection::BONE &&
                     !(selection.kind == pmx::Selection::BONE &&
                       selection.index == hit.index))
                status = "「" + bone_name(hit.index) + "」未选中：双击选中后才能位移 / 旋转";
            drag_mode = DRAG_ORBIT;
        }
    }
    if (ImGui::IsMouseClicked(ImGuiMouseButton_Right)) {
        const pmx::Selection hit = pick_at(mx, my, fb_w, fb_h, pmx::PICK_BONE);
        if (can_pose && hit.kind == pmx::Selection::BONE &&
            selection.kind == pmx::Selection::BONE && selection.index == hit.index && pose &&
            !bone_drag_block(hit.index, false)[0]) {
            drag_mode = DRAG_ROTATE;  // 右键旋转
            drag_bone = hit.index;
            drag_moved = false;
        } else {
            if (hit.kind == pmx::Selection::BONE && !can_pose)
                status = "编辑模式只改数据；摆骨骼请切到预览模式（Ctrl+M）";
            else if (hit.kind == pmx::Selection::BONE &&
                     !(selection.kind == pmx::Selection::BONE &&
                       selection.index == hit.index))
                status = "「" + bone_name(hit.index) + "」未选中：双击选中后才能位移 / 旋转";
            drag_mode = DRAG_PAN;
        }
    }
    if (ImGui::IsMouseClicked(ImGuiMouseButton_Middle))
        drag_mode = io.KeyShift ? DRAG_PAN : DRAG_ORBIT;

    // ---- 双击选中：落点有多个可选中对象时，在鼠标旁弹候选框由用户指定。
    if (double_click) {
        drag_mode = DRAG_NONE;
        drag_bone = -1;
        const std::vector<pmx::Selection> hits =
            pick_candidates_at(mx, my, fb_w, fb_h, pmx::PICK_ALL);
        pick_choices.clear();
        if (hits.size() > 1) {
            pick_choices = hits;
            pick_choice_pos[0] = io.MousePos.x;
            pick_choice_pos[1] = io.MousePos.y;
            pick_choice_frame = ImGui::GetFrameCount();
            status = "落点有 " + std::to_string(hits.size()) + " 个可选中对象：请在候选框中选择";
        } else {
            apply_pick(hits.empty() ? pmx::Selection{} : hits.front());
        }
    }

    // ---- 拖动
    const float dx = io.MouseDelta.x * scale_x;
    const float dy = io.MouseDelta.y * scale_y;
    switch (drag_mode) {
        case DRAG_ORBIT:
            if (ImGui::IsMouseDown(ImGuiMouseButton_Left) ||
                ImGui::IsMouseDown(ImGuiMouseButton_Middle))
                camera.orbit(dx, dy);
            break;
        case DRAG_PAN:
            if (ImGui::IsMouseDown(ImGuiMouseButton_Right) ||
                ImGui::IsMouseDown(ImGuiMouseButton_Middle))
                camera.pan(dx, dy);
            break;
        case DRAG_MOVE:
            if (pose && drag_bone >= 0 && (dx != 0.0f || dy != 0.0f)) {
                if (!drag_moved) {
                    drag_moved = true;
                    push_pose_undo("移动骨骼", "drag_bone");
                    remember_manual_pose(drag_bone);  // 真正拖动才取消这根骨骼的动作
                    const pmx::Bone& owner = model.bones[static_cast<std::size_t>(drag_bone)];
                    if ((owner.flags & pmx::BF_IK) && owner.ik) {
                        manual_ik_mutes.erase(drag_bone);
                        pose->set_ik_enabled(drag_bone, true);
                    }
                }
                const float k = camera.distance * 0.0016f;
                const pmx::Vec3 delta = camera.right() * (dx * k) - camera.up_vec() * (dy * k);
                pose->translate_world(drag_bone, delta);
                remember_manual_pose(drag_bone);
                pose->solve_ik();
                pose->world();
            }
            break;
        case DRAG_ROTATE:
            if (pose && drag_bone >= 0 && (dx != 0.0f || dy != 0.0f)) {
                if (!drag_moved) {
                    drag_moved = true;
                    push_pose_undo("旋转骨骼", "drag_bone");
                    remember_manual_pose(drag_bone);  // 真正拖动才取消这根骨骼的动作
                    // 旋转只改末端朝向：关闭会被这次旋转牵动的 IK 链，避免原点被 IK 拉走。
                    mute_conflicting_ik(drag_bone);
                }
                pose->rotate_world(drag_bone, pmx::Vec3{0.0f, 1.0f, 0.0f}, dx * 0.012f);
                pose->rotate_world(drag_bone, camera.right(), dy * 0.012f);
                remember_manual_pose(drag_bone);
                pose->solve_ik();
                pose->world();
            }
            break;
        default:
            break;
    }
    if (ImGui::IsMouseReleased(ImGuiMouseButton_Left) ||
        ImGui::IsMouseReleased(ImGuiMouseButton_Right) ||
        ImGui::IsMouseReleased(ImGuiMouseButton_Middle)) {
        if ((drag_mode == DRAG_MOVE || drag_mode == DRAG_ROTATE) && pose) {
            // 松手时用完整迭代再收敛一次，保证姿态精确。
            pose->solve_ik();
            pose->world();
            status = "姿态已更新";
        }
        drag_mode = DRAG_NONE;
        drag_bone = -1;
    }

    if (io.MouseWheel != 0.0f) camera.zoom(io.MouseWheel);
}

void Viewer::draw_ui() {
    static bool vpd_include_all = false;

    auto open_pmx = [this]() {
        const std::string path = pick_open_file(kPmxFilter, L"打开 PMX 模型");
        if (path.empty()) return;
        std::string err;
        if (load_model(path, &err)) error.clear();
        else error = err;
    };
    auto import_vpd = [this]() {
        if (!pose) {
            error = "尚未加载模型";
            return;
        }
        const std::string path = pick_open_file(kVpdFilter, L"导入 VPD 姿态");
        if (path.empty()) return;
        std::string err;
        if (apply_vpd_file(path, &err)) error.clear();
        else error = err;
    };
    auto import_vmd = [this]() {
        if (!pose) {
            error = "尚未加载模型";
            return;
        }
        const std::string path = pick_open_file(kVmdFilter, L"导入 VMD 动作");
        if (path.empty()) return;
        std::string err;
        if (load_vmd_file(path, &err)) error.clear();
        else error = err;
    };
    auto save = [this]() {
        std::string target = model_path;
        if (target.empty())
            target = pick_save_file(kPmxFilter, L"保存 PMX 模型",
                                    model.name.empty() ? std::string() : model.name + ".pmx",
                                    L"pmx");
        if (target.empty()) return;
        std::string err;
        if (save_model(target, &err)) error.clear();
        else error = err;
    };
    auto save_as = [this]() {
        const std::string target = pick_save_file(
            kPmxFilter, L"另存为 PMX 模型",
            model_path.empty() ? std::string() : model_path, L"pmx");
        if (target.empty()) return;
        std::string err;
        if (save_model(target, &err)) error.clear();
        else error = err;
    };
    auto export_vpd = [this]() {
        if (!pose) return;
        std::string default_path = model_path;
        if (!default_path.empty()) {
            const std::size_t dot = default_path.find_last_of('.');
            const std::size_t slash = default_path.find_last_of("/\\");
            if (dot != std::string::npos && (slash == std::string::npos || dot > slash))
                default_path = default_path.substr(0, dot);
            default_path += ".vpd";
        }
        const std::string out = pick_save_file(kVpdFilter, L"导出 VPD 姿态", default_path, L"vpd");
        if (out.empty()) return;
        try {
            const pmx::VpdExport res =
                pmx::save_vpd(out, model, *pose, &morph_weights, "", vpd_include_all);
            status = "已导出 VPD " + res.path + "（" + std::to_string(res.bones) +
                     " 骨骼 / " + std::to_string(res.morphs) + " 形态，" +
                     res.encoding + "）";
            error.clear();
        } catch (const std::exception& e) {
            error = e.what();
        }
    };

    auto export_vmd = [this]() {
        if (!pose) return;
        std::string default_path = model_path;
        if (!default_path.empty()) {
            const std::size_t dot = default_path.find_last_of('.');
            const std::size_t slash = default_path.find_last_of("/\\");
            if (dot != std::string::npos && (slash == std::string::npos || dot > slash))
                default_path = default_path.substr(0, dot);
            default_path += ".vmd";
        }
        const std::string out =
            pick_save_file(kVmdFilter, L"导出 VMD 动作", default_path, L"vmd");
        if (out.empty()) return;
        try {
            const int frame = static_cast<int>(std::lround(motion_frame));
            const pmx::VmdExport res = pmx::save_vmd(out, model, *pose, &morph_weights, "",
                                                     vpd_include_all, frame);
            status = "已导出 VMD " + res.path + "（" + std::to_string(res.bones) + " 骨骼 / " +
                     std::to_string(res.morphs) + " 形态，第 " + std::to_string(res.frame) +
                     " 帧）";
            error.clear();
        } catch (const std::exception& e) {
            error = e.what();
        }
    };

    const ImGuiViewport* viewport = ImGui::GetMainViewport();
    const float margin = pmxui::scale(8.0f);
    const float menu_h = ImGui::GetFrameHeight();
    const float status_h = ImGui::GetFrameHeight() + pmxui::scale(4.0f);

    // ------------------------------------------------------------ 顶部菜单栏
    if (ImGui::BeginMainMenuBar()) {
        // 模式切换：编辑（可改模型）/ 预览（模型只读，只保留视角、物理、动作、形态）。
        {
            const ImVec4 acc = pmxtheme::accent();
            auto mode_button = [&](const char* label, bool active) {
                if (active) {
                    ImGui::PushStyleColor(ImGuiCol_Button, acc);
                    ImGui::PushStyleColor(ImGuiCol_ButtonHovered, acc);
                    ImGui::PushStyleColor(ImGuiCol_ButtonActive, acc);
                    ImGui::PushStyleColor(ImGuiCol_Text, pmxtheme::accent_text());
                } else {
                    ImGui::PushStyleColor(ImGuiCol_Button, ImVec4(0, 0, 0, 0));
                }
                const bool pressed = ImGui::SmallButton(label);
                if (active) {
                    ImGui::PopStyleColor(4);
                } else {
                    ImGui::PopStyleColor(1);
                }
                return pressed;
            };
            if (mode_button("编辑", !preview_mode)) set_preview_mode(false);
            if (mode_button("预览", preview_mode)) set_preview_mode(true);
        }
        if (ImGui::BeginMenu("文件")) {
            if (ImGui::MenuItem("打开 PMX…", "Ctrl+O")) open_pmx();
            if (ImGui::MenuItem("导入 VPD…", nullptr, false, pose != nullptr)) import_vpd();
            if (ImGui::MenuItem("导入 VMD…", nullptr, false, pose != nullptr)) import_vmd();
            ImGui::Separator();
            const bool can_edit = pose != nullptr && !preview_mode;
            if (ImGui::MenuItem("保存", "Ctrl+S", false, can_edit)) save();
            if (ImGui::MenuItem("另存为…", "Ctrl+Shift+S", false, can_edit)) save_as();
            ImGui::Separator();
            if (ImGui::MenuItem("导出 VPD…", nullptr, false, can_edit)) export_vpd();
            if (ImGui::MenuItem("导出 VMD…", nullptr, false, can_edit)) export_vmd();
            ImGui::MenuItem("导出全部骨骼", nullptr, &vpd_include_all, can_edit);
            ImGui::Separator();
            if (ImGui::MenuItem("退出", "Alt+F4")) {
                if (GLFWwindow* current = glfwGetCurrentContext())
                    glfwSetWindowShouldClose(current, 1);
            }
            ImGui::EndMenu();
        }
        if (ImGui::BeginMenu("视图")) {
            if (ImGui::MenuItem("预览模式", "Ctrl+M", preview_mode))
                set_preview_mode(!preview_mode);
            ImGui::Separator();
            ImGui::MenuItem("模型网格", nullptr, &show_mesh);
            ImGui::MenuItem("骨骼", nullptr, &show_bones);
            ImGui::MenuItem("刚体", nullptr, &show_rigid);
            ImGui::MenuItem("关节", nullptr, &show_joints);
            ImGui::MenuItem("地面网格", nullptr, &grid);
            ImGui::Separator();
            ImGui::MenuItem("线框", nullptr, &wireframe);
            ImGui::MenuItem("描边", nullptr, &outline);
            ImGui::MenuItem("GPU 蒙皮", nullptr, &use_gpu);
            bool flat_toon = toon > 0.5f;
            if (ImGui::MenuItem("卡通光照", nullptr, &flat_toon))
                toon = flat_toon ? 1.0f : 0.0f;
            ImGui::Separator();
            if (ImGui::MenuItem("重置姿态", "R")) reset_pose();
            if (ImGui::MenuItem("相机居中", "F")) fit_camera();
            if (ImGui::MenuItem("物理演算", "P", physics_enabled)) {
                physics_enabled = !physics_enabled;
                reset_physics();
            }
            ImGui::Separator();
            if (ImGui::BeginMenu("主题")) {
                const bool light = theme == "light";
                if (ImGui::MenuItem("深色", nullptr, !light) && light) {
                    theme = "dark";
                    pmxtheme::apply_theme(theme);
                    pmxtheme::save_settings(*this);
                }
                if (ImGui::MenuItem("亮色", nullptr, light) && !light) {
                    theme = "light";
                    pmxtheme::apply_theme(theme);
                    pmxtheme::save_settings(*this);
                }
                ImGui::EndMenu();
            }
            ImGui::EndMenu();
        }
        if (ImGui::BeginMenu("帮助")) {
            if (ImGui::MenuItem("快捷键…")) {
                // 快捷键表在「设置」标签里，直接切过去。
                reveal_tab = "设置";
                reveal_frames = 2;
            }
            ImGui::Separator();
            ImGui::TextDisabled("PmxStudio 0.1.0 · GPLv3");
            ImGui::EndMenu();
        }
        ImGui::EndMainMenuBar();
    }

    // ------------------------------------------------------------ 底部状态栏
    char stats[256];
    std::snprintf(stats, sizeof stats,
                  "FPS %.1f · 顶点 %zu · 面 %zu · 骨骼 %zu · 刚体 %zu · 关节 %zu · 相机 %.1f",
                  fps, model.vertices.size(), model.n_faces(), model.bones.size(),
                  model.rigid.size(), model.joints.size(), camera.distance);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowRounding, 0.0f);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowBorderSize, 0.0f);
    ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding,
                        ImVec2(pmxui::scale(10.0f), pmxui::scale(3.0f)));
    ImGui::PushStyleColor(ImGuiCol_WindowBg, ImGui::GetStyleColorVec4(ImGuiCol_TitleBg));
    ImGui::SetNextWindowPos(
        ImVec2(viewport->Pos.x, viewport->Pos.y + viewport->Size.y - status_h));
    ImGui::SetNextWindowSize(ImVec2(viewport->Size.x, status_h));
    ImGui::Begin("###pmx_status", nullptr,
                 ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoMove |
                     ImGuiWindowFlags_NoSavedSettings | ImGuiWindowFlags_NoFocusOnAppearing |
                     ImGuiWindowFlags_NoNav | ImGuiWindowFlags_NoScrollbar |
                     ImGuiWindowFlags_NoBringToFrontOnFocus);
    {
        const ImVec2 bar = ImGui::GetWindowPos();
        ImGui::GetWindowDrawList()->AddLine(
            ImVec2(bar.x, bar.y + 0.5f),
            ImVec2(bar.x + ImGui::GetWindowWidth(), bar.y + 0.5f),
            ImGui::GetColorU32(ImGuiCol_Separator), 1.0f);
        // 状态文本按剩余宽度裁剪，避免长路径盖住右侧统计。
        const ImVec2 text_pos = ImGui::GetCursorScreenPos();
        const float stats_w = ImGui::CalcTextSize(stats).x;
        const float left_w =
            std::max(0.0f, ImGui::GetWindowWidth() - stats_w - pmxui::scale(28.0f));
        ImGui::PushClipRect(
            text_pos,
            ImVec2(text_pos.x + left_w, text_pos.y + ImGui::GetTextLineHeight() + 2.0f), true);
        ImGui::TextUnformatted(status.c_str());
        ImGui::PopClipRect();
        ImGui::SameLine(
            std::max(0.0f, ImGui::GetWindowWidth() - stats_w - pmxui::scale(10.0f)));
        ImGui::TextDisabled("%s", stats);
    }
    ImGui::End();
    ImGui::PopStyleColor();
    ImGui::PopStyleVar(3);

    // ------------------------------------------------------------ 检查器
    const float max_w = std::max(pmxui::scale(320.0f), viewport->Size.x - margin * 2.0f);
    const float max_h = std::max(pmxui::scale(240.0f),
                                 viewport->Size.y - menu_h - status_h - margin * 2.0f);
    ImGui::SetNextWindowPos(ImVec2(viewport->Pos.x + margin, viewport->Pos.y + menu_h + margin),
                            ImGuiCond_FirstUseEver);
    ImGui::SetNextWindowSize(ImVec2(std::min(pmxui::scale(580.0f), max_w), max_h),
                             ImGuiCond_FirstUseEver);
    ImGui::SetNextWindowSizeConstraints(ImVec2(pmxui::scale(320.0f), pmxui::scale(240.0f)),
                                        ImVec2(max_w, max_h));
    // 窗口 ID 固定为 ###inspector，切换模式只改标题，位置/尺寸保持不变。
    ImGui::Begin(preview_mode ? "预览###inspector" : "检查器###inspector");

    // 模型名 + 脏标记 + 文件路径，作为检查器标题区的上下文。
    const std::string doc_name =
        !model.name.empty() ? model.name
                            : (model_path.empty() ? std::string("未加载模型")
                                                  : std::string("未命名模型"));
    ImGui::PushStyleColor(ImGuiCol_Text, pmxtheme::accent());
    ImGui::TextUnformatted(doc_name.c_str());
    ImGui::PopStyleColor();
    if (preview_mode) {
        ImGui::SameLine();
        ImGui::TextDisabled("只读预览");
    } else if (dirty) {
        ImGui::SameLine();
        ImGui::TextColored(pmxtheme::warning(), "● 未保存");
    }
    // 标题区只放文件名，完整路径留作悬停提示，避免长路径被窗口边缘截断。
    std::string file_label = model_path;
    const std::size_t last_slash = file_label.find_last_of("/\\");
    if (last_slash != std::string::npos && last_slash + 1 < file_label.size())
        file_label = file_label.substr(last_slash + 1);
    ImGui::TextDisabled("%s", model_path.empty() ? "拖入 .pmx / .vpd 文件即可载入"
                                                 : file_label.c_str());
    if (!model_path.empty()) ImGui::SetItemTooltip("%s", model_path.c_str());

    if (!error.empty()) {
        ImGui::PushStyleColor(ImGuiCol_Text, pmxtheme::danger());
        ImGui::TextWrapped("%s", error.c_str());
        ImGui::PopStyleColor();
        ImGui::SameLine();
        if (ImGui::SmallButton("清除")) error.clear();
    }
    ImGui::Spacing();

    // 主操作按钮用强调色，次要操作保持常规按钮。
    const ImVec4 accent = pmxtheme::accent();
    const ImVec4 accent_hover(std::min(1.0f, accent.x * 1.15f),
                              std::min(1.0f, accent.y * 1.12f),
                              std::min(1.0f, accent.z * 1.05f), accent.w);
    const ImVec4 accent_active(accent.x * 0.85f, accent.y * 0.85f, accent.z * 0.85f, accent.w);
    ImGui::PushStyleColor(ImGuiCol_Button, accent);
    ImGui::PushStyleColor(ImGuiCol_ButtonHovered, accent_hover);
    ImGui::PushStyleColor(ImGuiCol_ButtonActive, accent_active);
    ImGui::PushStyleColor(ImGuiCol_Text, pmxtheme::accent_text());
    if (ImGui::Button("打开 PMX…", ImVec2(pmxui::scale(120.0f), 0.0f))) open_pmx();
    ImGui::PopStyleColor(4);

    ImGui::SameLine();
    if (preview_mode) {
        ImGui::TextDisabled("可摆姿 · 数据只读（Ctrl+M 回编辑）");
    } else {
        ImGui::BeginDisabled(pose == nullptr);
        if (ImGui::Button("保存")) save();
        if (ImGui::IsItemHovered(ImGuiHoveredFlags_AllowWhenDisabled))
            ImGui::SetTooltip("保存到当前文件（Ctrl+S）");
        ImGui::EndDisabled();
    }

    // 撤销 / 重做两种模式都显示：预览模式只允许撤销摆姿条目，数据快照会被拦下。
    ImGui::SameLine();
    ImGui::BeginDisabled(!can_undo());
    if (ImGui::Button("撤销")) undo();
    if (ImGui::IsItemHovered(ImGuiHoveredFlags_AllowWhenDisabled) && can_undo())
        ImGui::SetTooltip("撤销：%s", undo_label().c_str());
    ImGui::EndDisabled();

    ImGui::SameLine();
    ImGui::BeginDisabled(!can_redo());
    if (ImGui::Button("重做")) redo();
    if (ImGui::IsItemHovered(ImGuiHoveredFlags_AllowWhenDisabled) && can_redo())
        ImGui::SetTooltip("重做：%s", redo_label().c_str());
    ImGui::EndDisabled();

    if (!pose) {
        ImGui::Spacing();
        ImGui::TextDisabled("尚未加载模型：拖入 .pmx 文件，或使用「文件 → 打开 PMX…」");
    }
    ImGui::Spacing();
    ImGui::Separator();

    if (ImGui::BeginTabBar("##inspector_tabs")) {
        auto tab = [this](const char* name, void (*fn)(Viewer&)) {
            // 视口双击选中的对象在对应面板里可见：自动把该标签切到前台。
            const ImGuiTabItemFlags flags =
                reveal_tab && std::strcmp(reveal_tab, name) == 0
                    ? ImGuiTabItemFlags_SetSelected
                    : ImGuiTabItemFlags_None;
            if (ImGui::BeginTabItem(name, nullptr, flags)) {
                fn(*this);
                ImGui::EndTabItem();
            }
        };
        if (preview_mode) {
            // 预览模式只保留控制类标签：动作、物理开关、形态、设置。
            tab("动作", &panel_motion);
            tab("物理", &panel_preview_physics);
            tab("形态", &panel_preview_morph);
            tab("设置", &panel_settings);
        } else {
            tab("信息", &panel_info);
            tab("骨骼", &panel_bone);
            tab("表示枠", &panel_frame);
            tab("顶点", &panel_vertex);
            tab("材质", &panel_material);
            tab("面", &panel_face);
            tab("形态", &panel_morph);
            tab("动作", &panel_motion);
            tab("物理", &panel_physics);
            tab("柔体", &panel_soft);
            tab("设置", &panel_settings);
        }
        ImGui::EndTabBar();
    }
    // 标签切换在下一帧生效，保持两帧后清零，避免一直强制选中。
    if (reveal_frames > 0 && --reveal_frames == 0) {
        reveal_tab = nullptr;
        reveal_selection = false;
    }
    ImGui::End();
}


void Viewer::draw_scene(int fb_w, int fb_h) {
    settings.show_mesh = show_mesh;
    settings.show_bones = show_bones;
    settings.show_rigid = show_rigid;
    settings.show_joints = show_joints;
    settings.use_gpu_skinning = use_gpu;
    settings.wireframe = wireframe;
    settings.grid = grid;
    settings.outline = outline;
    settings.bone_alpha = bone_alpha;
    settings.rigid_alpha = rigid_alpha;
    settings.joint_alpha = joint_alpha;
    settings.focus_selection = focus_overlay;
    settings.toon = toon;
    settings.rim = rim;
    settings.background = {bg[0], bg[1], bg[2]};
    settings.light_dir = {light[0], light[1], light[2]};

    if (!pose) {
        glClearColor(bg[0], bg[1], bg[2], 1.0f);
        glClear(glc::GL_COLOR_BUFFER_BIT | glc::GL_DEPTH_BUFFER_BIT);
        return;
    }
    const float aspect = static_cast<float>(fb_w) / static_cast<float>(std::max(1, fb_h));
    renderer.render(model, *pose, physics_ptr, camera.view(), camera.projection(aspect),
                    fb_w, fb_h, settings, selection);
}

bool Viewer::apply_vpd_file(const std::string& path, std::string* err) {
    if (!pose) {
        if (err) *err = "尚未加载模型";
        return false;
    }
    try {
        const pmx::VpdFile vpd = pmx::load_vpd(path);
        push_pose_undo("导入 VPD");
        // 先清空旧形态，避免上一个 VPD 的权重残留。
        std::fill(morph_values.begin(), morph_values.end(), 0.0f);
        morph_weights.clear();
        clear_manual_pose();
        const pmx::VpdMatchResult result =
            pmx::apply_vpd(model, *pose, vpd, &morph_weights);
        for (const auto& [index, weight] : morph_weights)
            if (index >= 0 && index < static_cast<int>(morph_values.size()))
                morph_values[static_cast<std::size_t>(index)] = weight;
        morph_dirty = true;
        pose->solve_ik();
        pose->world();
        vpd_path = path;
        status = "已应用 VPD " + path + "（" + std::to_string(result.matched) + "/" +
                 std::to_string(result.total) + " 骨骼匹配）";
        return true;
    } catch (const std::exception& e) {
        if (err) *err = e.what();
        return false;
    }
}

bool Viewer::load_vmd_file(const std::string& path, std::string* err) {
    if (!pose) {
        if (err) *err = "尚未加载模型";
        return false;
    }
    try {
        auto loaded = std::make_unique<pmx::VmdMotion>(pmx::load_vmd(path));
        motion = std::move(loaded);
        motion_binding = pmx::bind_vmd(model, *motion);
        motion_frame = 0.0f;
        motion_speed = 1.0f;
        motion_loop = true;
        motion_playing = motion->max_frame > 0;
        motion_dirty = true;
        vmd_path = path;
        clear_manual_pose();
        apply_motion_frame();  // 先落到第 0 帧，物理复位也以该帧为初始姿态
#ifdef PMX_ENABLE_PHYSICS
        if (physics_enabled) reset_physics();
#endif
        const pmx::VmdMotion& m = *motion;
        status = "已导入 VMD " + path + "（骨骼 " +
                 std::to_string(motion_binding.bone_matched) + "/" +
                 std::to_string(m.bone_tracks.size()) + " 匹配 · 形态 " +
                 std::to_string(motion_binding.morph_matched) + "/" +
                 std::to_string(m.morph_tracks.size()) + " 匹配 · " +
                 std::to_string(m.max_frame) + " 帧）";
        return true;
    } catch (const std::exception& e) {
        if (err) *err = e.what();
        return false;
    }
}

void Viewer::clear_motion() {
    motion.reset();
    motion_binding = pmx::VmdBinding{};
    motion_frame = 0.0f;
    motion_playing = false;
    motion_dirty = false;
    vmd_path.clear();
    clear_manual_pose();
    status = "已清除 VMD 动作";
    if (physics_enabled) settle_physics();
}

void Viewer::apply_motion_frame() {
    if (!motion || !pose) return;
    pmx::MorphWeights weights;
    pmx::evaluate_vmd(*motion, motion_binding, motion_frame, *pose, &weights);
    // 只取消被手动摆过的那几根骨骼：evaluate_vmd 会整体 reset，这里把手动值写回去。
    if (!motion_muted_bones.empty()) {
        for (int b : motion_muted_bones) {
            if (b < 0 || b >= pose->n) continue;
            const auto r = motion_muted_rot.find(b);
            const auto t = motion_muted_trans.find(b);
            if (r != motion_muted_rot.end())
                pose->base_rot[static_cast<std::size_t>(b)] = r->second;
            if (t != motion_muted_trans.end())
                pose->base_trans[static_cast<std::size_t>(b)] = t->second;
        }
        pose->apply(&weights);
    }
    // VMD 的 reset 会清空 IK 开关，把「手动旋转时临时关闭」的链重新关掉。
    apply_manual_ik_mutes();
    if (!same_morph_weights(weights, morph_weights)) {
        morph_weights = std::move(weights);
        std::fill(morph_values.begin(), morph_values.end(), 0.0f);
        for (const auto& [index, weight] : morph_weights)
            if (index >= 0 && index < static_cast<int>(morph_values.size()))
                morph_values[static_cast<std::size_t>(index)] = weight;
        morph_dirty = true;
    }
    pose->invalidate_world();
}

void Viewer::update_motion(float dt) {
    if (!motion || !pose) return;
    bool jumped = false;
    if (motion_playing) {
        const float end = static_cast<float>(std::max(0, motion->max_frame));
        // VMD 帧号按 30 fps 计；单帧 dt 上限 0.1s，避免拖动窗口后跳帧。
        float next = motion_frame + std::min(dt, 0.1f) * 30.0f * motion_speed;
        if (end <= 0.0f) {
            next = 0.0f;
        } else if (next > end) {
            if (motion_loop) {
                next = std::fmod(next, end);
                jumped = true;
            } else {
                next = end;
                motion_playing = false;
            }
        }
        motion_frame = std::max(0.0f, next);
        motion_dirty = true;
    }
    if (motion_dirty) {
        apply_motion_frame();
        motion_dirty = false;
    }
    // 循环回绕会把姿态从末帧瞬移到首帧。MMD / Blender 播放时不会重摆刚体，
    // 这里只清速度：重摆会把几十节的袖链瞬间扯断，之后就被甩飞。
    if (jumped) settle_physics();
}

void on_drop(GLFWwindow* window, int count, const char** paths) {
    auto* viewer = static_cast<Viewer*>(glfwGetWindowUserPointer(window));
    if (!viewer || count <= 0) return;
    std::string path = paths[0];
    auto ends = [&path](const char* ext) {
        const std::size_t n = std::strlen(ext);
        return path.size() >= n &&
               std::equal(ext, ext + n, path.end() - n,
                          [](char a, char b) {
                              return std::tolower(static_cast<unsigned char>(a)) ==
                                     std::tolower(static_cast<unsigned char>(b));
                          });
    };
    if (ends(".pmx")) {
        std::string err;
        if (!viewer->load_model(path, &err)) viewer->error = err;
    } else if (ends(".vpd")) {
        std::string err;
        if (!viewer->apply_vpd_file(path, &err)) viewer->error = err;
        else viewer->error.clear();
    } else if (ends(".vmd")) {
        std::string err;
        if (!viewer->load_vmd_file(path, &err)) viewer->error = err;
        else viewer->error.clear();
    }
}


#ifdef _WIN32
// 让系统标题栏跟随深色主题；Win10 20H1+ 用属性 20，旧版本回退到 19。
void apply_native_title_bar(GLFWwindow* window, bool dark) {
    HWND hwnd = glfwGetWin32Window(window);
    if (!hwnd) return;
    const BOOL value = dark ? TRUE : FALSE;
    if (FAILED(DwmSetWindowAttribute(hwnd, 20, &value, sizeof(value))))
        DwmSetWindowAttribute(hwnd, 19, &value, sizeof(value));
    // 部分系统不会立即重绘非客户区，强制一次框架刷新让标题栏换色可见。
    SetWindowPos(hwnd, nullptr, 0, 0, 0, 0,
                 SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED);
}
#endif

// 以 GUI 子系统启动时没有控制台，错误信息需要同时弹窗，否则会静默退出。
static void report_error(const std::string& message) {
    std::fprintf(stderr, "%s\n", message.c_str());
#ifdef _WIN32
    const int len = ::MultiByteToWideChar(CP_UTF8, 0, message.data(),
                                          static_cast<int>(message.size()), nullptr, 0);
    if (len > 0) {
        std::wstring wide(static_cast<std::size_t>(len), L'\0');
        ::MultiByteToWideChar(CP_UTF8, 0, message.data(), static_cast<int>(message.size()),
                              wide.data(), len);
        ::MessageBoxW(nullptr, wide.c_str(), L"PmxStudio", MB_OK | MB_ICONERROR);
    }
#endif
}

// args 已在入口处由 pmx::utf8_args 转成 UTF-8：Windows 的 CRT argv 按 ANSI 代码页解码，
// 中文/日文路径会变成乱码，所以不直接用 argv。
static int run_viewer(const std::vector<std::string>& args) {
    if (!glfwInit()) {
        report_error("GLFW 初始化失败");
        return 1;
    }
    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 4);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 6);
    glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);
    glfwWindowHint(GLFW_SAMPLES, 4);
    // 描边依赖模板缓冲（与 Python 版相同的倒置壳遮罩算法）。
    glfwWindowHint(GLFW_STENCIL_BITS, 8);

    GLFWwindow* window = glfwCreateWindow(1440, 900, "PmxStudio", nullptr, nullptr);
    if (!window) {
        report_error("无法创建 OpenGL 4.6 窗口");
        glfwTerminate();
        return 1;
    }
    glfwMakeContextCurrent(window);
    glfwSwapInterval(1);
    glfwSetDropCallback(window, on_drop);

    // ---- 分辨率 / DPI 适配
    // ImGui 的坐标单位是屏幕坐标：Windows/X11 上 framebuffer 与窗口等大，需要按
    // content scale 手动放大字体与控件；macOS 的 framebuffer 已是 content scale 倍，
    // 两者相除后缩放因子自动为 1，不会二次放大。
    int win_w = 0, win_h = 0, fb_w0 = 0, fb_h0 = 0;
    glfwGetWindowSize(window, &win_w, &win_h);
    glfwGetFramebufferSize(window, &fb_w0, &fb_h0);
    float cs_x = 1.0f, cs_y = 1.0f;
    glfwGetWindowContentScale(window, &cs_x, &cs_y);
    (void)cs_y;
    const float fb_ratio = static_cast<float>(fb_w0) / static_cast<float>(std::max(1, win_w));
    pmxui::set_ui_scale(std::clamp(cs_x / std::max(1.0f, fb_ratio), 1.0f, 3.0f));
    // 拿不到可靠 DPI 时（部分 Linux 桌面没有 Xft.dpi）可用环境变量强制缩放。
    bool ui_scale_locked = false;
    if (const char* env = std::getenv("PMX_UI_SCALE")) {
        const float forced = std::strtof(env, nullptr);
        if (forced > 0.0f) {
            pmxui::set_ui_scale(std::clamp(forced, 1.0f, 3.0f));
            ui_scale_locked = true;
        }
    }

    // 默认 1440×900 逻辑尺寸，按 DPI 放大后限制在显示器工作区的 92% 内（4K 放得下）。
    int target_w = static_cast<int>(1440.0f * pmxui::ui_scale());
    int target_h = static_cast<int>(900.0f * pmxui::ui_scale());
    if (GLFWmonitor* monitor = glfwGetPrimaryMonitor()) {
        int mx = 0, my = 0, mw = 0, mh = 0;
        glfwGetMonitorWorkarea(monitor, &mx, &my, &mw, &mh);
        if (mw > 0 && mh > 0) {
            target_w = std::min(target_w, static_cast<int>(static_cast<float>(mw) * 0.92f));
            target_h = std::min(target_h, static_cast<int>(static_cast<float>(mh) * 0.92f));
            glfwSetWindowSize(window, target_w, target_h);
            glfwSetWindowPos(window, mx + (mw - target_w) / 2, my + (mh - target_h) / 2);
        }
    }
    glfwSetWindowSizeLimits(
        window, std::min(target_w, static_cast<int>(760.0f * pmxui::ui_scale())),
        std::min(target_h, static_cast<int>(500.0f * pmxui::ui_scale())), GLFW_DONT_CARE,
        GLFW_DONT_CARE);
#ifdef _WIN32
    g_owner = glfwGetWin32Window(window);  // 文件对话框的属主，保持模态
#endif

    const char* missing = glapi::load();
    if (missing && *missing) {
        report_error(std::string("缺少 OpenGL 入口：") + missing);
        glfwDestroyWindow(window);
        glfwTerminate();
        return 1;
    }

    Viewer viewer;
    glfwSetWindowUserPointer(window, &viewer);

    // 偏好先于模型加载：配置文件里的 last_model 只在没有命令行参数时生效。
    std::string settings_err;
    pmxtheme::load_settings(viewer, &settings_err);

    std::string err;
    if (!viewer.renderer.init(&err)) {
        report_error("渲染器初始化失败：" + err);
        glfwDestroyWindow(window);
        glfwTerminate();
        return 1;
    }

    std::string initial = args.size() > 1 ? args[1] : viewer.model_path;
    if (initial.empty()) initial = "tests/test_model.pmx";
    if (!viewer.load_model(initial, &err)) {
        viewer.model_path = initial;
        viewer.error = err;
    }
    viewer.fps_time = glfwGetTime();

    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    ImGui::GetIO().ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard;
    // 只有一个检查器窗口，布局由代码按 DPI 决定；持久化 imgui.ini 会在换分辨率/DPI 后
    // 留下旧的像素尺寸，反而把控件挤坏，这里禁用。
    ImGui::GetIO().IniFilename = nullptr;
    pmxtheme::apply_theme(viewer.theme);
    // 默认字体不含中日韩字形，按平台候选列表加载一款系统字体（ImGui 1.92 按需加载字形）。
    {
        static const char* kFonts[] = {
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/msyhbd.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "/System/Library/Fonts/PingFang.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        };
        // 按 UTF-8 路径读入内存再注册字体：ImGui 自身会转宽字符，但统一走 fs.hpp
        // 可以覆盖 Windows / MinGW / Linux 的所有路径分支。
        static std::vector<char> font_bytes;  // 必须存活到字体图集销毁
        for (const char* f : kFonts) {
            if (!pmx::path_exists(f)) continue;
            std::ifstream in = pmx::open_ifstream(f);
            if (!in) continue;
            font_bytes.assign(std::istreambuf_iterator<char>(in),
                              std::istreambuf_iterator<char>());
            if (font_bytes.empty()) continue;
            ImFontConfig cfg;
            cfg.FontDataOwnedByAtlas = false;
            if (ImGui::GetIO().Fonts->AddFontFromMemoryTTF(
                    font_bytes.data(), static_cast<int>(font_bytes.size()), 18.0f, &cfg))
                break;
            font_bytes.clear();
        }
    }
    ImGui_ImplGlfw_InitForOpenGL(window, true);
    ImGui_ImplOpenGL3_Init("#version 460");

    while (!glfwWindowShouldClose(window)) {
        glfwPollEvents();

#ifdef _WIN32
        // 首帧或切换主题时把原生标题栏同步成深色 / 浅色。
        static std::string last_theme;
        if (viewer.theme != last_theme) {
            apply_native_title_bar(window, viewer.theme != "light");
            last_theme = viewer.theme;
        }
#endif

        // 跨显示器拖动或系统缩放变化时重新计算 UI 缩放；style 只能在帧间修改。
        {
            int ww = 0, wh = 0, fw = 0, fh = 0;
            glfwGetWindowSize(window, &ww, &wh);
            glfwGetFramebufferSize(window, &fw, &fh);
            float sx = 1.0f, sy = 1.0f;
            glfwGetWindowContentScale(window, &sx, &sy);
            (void)wh;
            (void)fh;
            (void)sy;
            const float ratio = static_cast<float>(fw) / static_cast<float>(std::max(1, ww));
            const float next = std::clamp(sx / std::max(1.0f, ratio), 1.0f, 3.0f);
            if (!ui_scale_locked && std::fabs(next - pmxui::ui_scale()) > 0.01f) {
                pmxui::set_ui_scale(next);
                pmxtheme::apply_theme(viewer.theme);
            }
        }

        int fb_w = 0, fb_h = 0;
        glfwGetFramebufferSize(window, &fb_w, &fb_h);

        ImGui_ImplOpenGL3_NewFrame();
        ImGui_ImplGlfw_NewFrame();
        ImGui::NewFrame();

        viewer.handle_shortcuts();
        viewer.handle_input(window, fb_w, fb_h);
        viewer.update_motion(ImGui::GetIO().DeltaTime);

        if (viewer.pose) {
            if (viewer.morph_dirty) viewer.apply_morphs();
            else viewer.pose->apply(&viewer.morph_weights);
            viewer.pose->solve_ik();
#ifdef PMX_ENABLE_PHYSICS
            if (viewer.physics_ptr && viewer.physics_ptr->enabled) {
                viewer.physics_ptr->step(*viewer.pose, 1.0f / 60.0f,
                                         &viewer.morph_weights);
            }
#endif
            viewer.pose->world();
        }

        viewer.draw_scene(fb_w, fb_h);
        viewer.draw_ui();
        viewer.draw_pick_choices();  // 双击候选框画在最上层

        static std::string last_title;
        const std::string title = viewer.window_title();
        if (title != last_title) {
            glfwSetWindowTitle(window, title.c_str());
            last_title = title;
        }

        ImGui::Render();
        ImGui_ImplOpenGL3_RenderDrawData(ImGui::GetDrawData());
        glfwSwapBuffers(window);

        ++viewer.frames;
        const double now = glfwGetTime();
        if (now - viewer.fps_time >= 0.5) {
            viewer.fps = static_cast<float>(viewer.frames / (now - viewer.fps_time));
            viewer.frames = 0;
            viewer.fps_time = now;
        }
    }

    pmxtheme::save_settings(viewer);
    ImGui_ImplOpenGL3_Shutdown();
    ImGui_ImplGlfw_Shutdown();
    ImGui::DestroyContext();
    viewer.renderer.release_model();
    glfwDestroyWindow(window);
    glfwTerminate();
    return 0;
}

#ifdef _WIN32
// Windows 下以 GUI 子系统链接（无控制台窗口），入口是 WinMain。
// CRT 在本子系统下不提供可靠的 argc/argv，用 pmx::utf8_args 重新解析宽字符命令行。
extern "C" int WINAPI WinMain(HINSTANCE, HINSTANCE, LPSTR, int) {
    return run_viewer(pmx::utf8_args(0, nullptr));
}
#else
int main(int argc, char** argv) { return run_viewer(pmx::utf8_args(argc, argv)); }
#endif
