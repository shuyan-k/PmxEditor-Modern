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

pmx::Selection Viewer::pick_at(float sx, float sy, int fb_w, int fb_h, int kinds) {
    if (!pose) return pmx::Selection{};
    return renderer.pick(model, *pose, physics_ptr, camera.view(),
                         camera.projection(static_cast<float>(fb_w) /
                                           static_cast<float>(std::max(1, fb_h))),
                         fb_w, fb_h, sx, sy, 12.0f, kinds);
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
    e.weights = morph_weights;
    e.values = morph_values;
    return e;
}

void Viewer::reset_pose() {
    if (!pose) return;
    push_pose_undo("重置姿态");
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
    if (ImGui::IsKeyPressed(ImGuiKey_F, false) && !io.KeyCtrl) fit_camera();
    if (ImGui::IsKeyPressed(ImGuiKey_R, false) && !io.KeyCtrl) reset_pose();
    if (ImGui::IsKeyPressed(ImGuiKey_P, false) && !io.KeyCtrl) {
        physics_enabled = !physics_enabled;
        reset_physics();
    }
    if (io.KeyCtrl && ImGui::IsKeyPressed(ImGuiKey_Z, false)) {
        if (io.KeyShift) redo();
        else undo();
    }
    if (io.KeyCtrl && ImGui::IsKeyPressed(ImGuiKey_Y, false)) redo();
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

    // ---- 按下：已选中的骨骼才可拖动，否则只操作视角
    if (ImGui::IsMouseClicked(ImGuiMouseButton_Left) && !double_click) {
        const pmx::Selection hit = pick_at(mx, my, fb_w, fb_h, pmx::PICK_BONE);
        if (hit.kind == pmx::Selection::BONE && selection.kind == pmx::Selection::BONE &&
            selection.index == hit.index && pose && !bone_drag_block(hit.index, true)[0]) {
            push_pose_undo("移动骨骼", "drag_bone");  // 撤销记录推迟到真正拖动前
            drag_mode = DRAG_MOVE;  // 左键位移（含 IK 控制器）
            drag_bone = hit.index;
        } else {
            if (hit.kind == pmx::Selection::BONE)
                status = "「" + bone_name(hit.index) + "」未选中：双击选中后才能位移 / 旋转";
            drag_mode = DRAG_ORBIT;
        }
    }
    if (ImGui::IsMouseClicked(ImGuiMouseButton_Right)) {
        const pmx::Selection hit = pick_at(mx, my, fb_w, fb_h, pmx::PICK_BONE);
        if (hit.kind == pmx::Selection::BONE && selection.kind == pmx::Selection::BONE &&
            selection.index == hit.index && pose && !bone_drag_block(hit.index, false)[0]) {
            push_pose_undo("旋转骨骼", "drag_bone");
            drag_mode = DRAG_ROTATE;  // 右键旋转
            drag_bone = hit.index;
        } else {
            if (hit.kind == pmx::Selection::BONE)
                status = "「" + bone_name(hit.index) + "」未选中：双击选中后才能位移 / 旋转";
            drag_mode = DRAG_PAN;
        }
    }
    if (ImGui::IsMouseClicked(ImGuiMouseButton_Middle))
        drag_mode = io.KeyShift ? DRAG_PAN : DRAG_ORBIT;

    // ---- 双击选中：骨骼 / 刚体 / 关节都可以（刚体、关节优先）
    if (double_click) {
        const pmx::Selection hit = pick_at(mx, my, fb_w, fb_h, pmx::PICK_ALL);
        drag_mode = DRAG_NONE;
        drag_bone = -1;
        if (hit.kind == pmx::Selection::NONE) {
            if (sel.kind != SelKind::None) {
                select(SelKind::None, -1);
                status = "取消选择";
            }
            reveal_selection = false;
            reveal_frames = 0;
        } else {
            if (hit.kind == pmx::Selection::BONE) {
                select(SelKind::Bone, hit.index);
                reveal_tab = "骨骼";
                status = "已选中「" + bone_name(hit.index) + "」：左键拖动位移 · 右键拖动旋转";
            } else if (hit.kind == pmx::Selection::RIGID) {
                select(SelKind::Rigid, hit.index);
                reveal_tab = "物理";
                status = "已选中刚体「" +
                         model.rigid[static_cast<std::size_t>(hit.index)].name + "」";
            } else {
                select(SelKind::Joint, hit.index);
                reveal_tab = "物理";
                status = "已选中关节「" +
                         model.joints[static_cast<std::size_t>(hit.index)].name + "」";
            }
            // 切面板要等下一帧生效，保持两帧让 SetSelected 与滚动都落地。
            reveal_frames = 2;
            reveal_selection = true;
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
                const float k = camera.distance * 0.0016f;
                const pmx::Vec3 delta = camera.right() * (dx * k) - camera.up_vec() * (dy * k);
                pose->translate_world(drag_bone, delta);
                pose->solve_ik();
                pose->world();
            }
            break;
        case DRAG_ROTATE:
            if (pose && drag_bone >= 0 && (dx != 0.0f || dy != 0.0f)) {
                pose->rotate_world(drag_bone, pmx::Vec3{0.0f, 1.0f, 0.0f}, dx * 0.012f);
                pose->rotate_world(drag_bone, camera.right(), dy * 0.012f);
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
    const ImVec2 display = ImGui::GetIO().DisplaySize;
    const float margin = pmxui::scale(8.0f);
    ImGui::SetNextWindowPos(ImVec2(margin, margin), ImGuiCond_FirstUseEver);
    ImGui::SetNextWindowSize(ImVec2(pmxui::scale(560.0f), pmxui::scale(780.0f)),
                             ImGuiCond_FirstUseEver);
    // 小分辨率（如 1280×720）下默认 780 高的面板会超出窗口底部，内容被裁掉且滚动条
    // 触不到底；限制最大尺寸让面板始终完整落在视口内，内容改由滚动条访问。
    ImGui::SetNextWindowSizeConstraints(
        ImVec2(pmxui::scale(320.0f), pmxui::scale(240.0f)),
        ImVec2(std::max(pmxui::scale(320.0f), display.x - margin * 2.0f),
               std::max(pmxui::scale(240.0f), display.y - margin * 2.0f)));
    ImGui::Begin("检查器");

    ImGui::TextWrapped("%s", status.c_str());
    if (!error.empty()) {
        ImGui::TextColored(ImVec4(1, 0.4f, 0.4f, 1), "%s", error.c_str());
        if (ImGui::Button("清除错误")) error.clear();
    }
    ImGui::Text("FPS %.1f | 顶点 %zu | 面 %zu | 骨骼 %zu | 刚体 %zu | 关节 %zu",
                fps, model.vertices.size(), model.n_faces(), model.bones.size(),
                model.rigid.size(), model.joints.size());
    ImGui::TextDisabled("相机 %.1f | GPU dispatch %d | %s", camera.distance,
                        renderer.gpu_skin_dispatch_count, dirty ? "未保存" : "无修改");

    if (ImGui::Button("打开 PMX…")) {
        const std::string path = pick_open_file(kPmxFilter, L"打开 PMX 模型");
        if (!path.empty()) {
            std::string err;
            if (load_model(path, &err)) error.clear();
            else error = err;
        }
    }
    ImGui::SameLine();
    if (ImGui::Button("导入 VPD…")) {
        const std::string path = pick_open_file(kVpdFilter, L"导入 VPD 姿态");
        if (!path.empty()) {
            std::string err;
            if (apply_vpd_file(path, &err)) error.clear();
            else error = err;
        }
    }
    ImGui::SameLine();
    if (ImGui::Button("保存")) {
        std::string target = model_path;
        if (target.empty())
            target = pick_save_file(kPmxFilter, L"保存 PMX 模型",
                                    model.name.empty() ? std::string() : model.name + ".pmx",
                                    L"pmx");
        if (!target.empty()) {
            std::string err;
            if (save_model(target, &err)) error.clear();
            else error = err;
        }
    }
    ImGui::SameLine();
    if (ImGui::Button("另存为…")) {
        const std::string target = pick_save_file(
            kPmxFilter, L"另存为 PMX 模型",
            model_path.empty() ? std::string() : model_path, L"pmx");
        if (!target.empty()) {
            std::string err;
            if (save_model(target, &err)) error.clear();
            else error = err;
        }
    }
    static bool vpd_include_all = false;
    ImGui::Checkbox("导出全部骨骼", &vpd_include_all);
    ImGui::SameLine();
    if (ImGui::Button("导出 VPD…") && pose) {
        std::string default_path = model_path;
        if (!default_path.empty()) {
            const std::size_t dot = default_path.find_last_of('.');
            const std::size_t slash = default_path.find_last_of("/\\");
            if (dot != std::string::npos && (slash == std::string::npos || dot > slash))
                default_path = default_path.substr(0, dot);
            default_path += ".vpd";
        }
        const std::string out = pick_save_file(kVpdFilter, L"导出 VPD 姿态", default_path, L"vpd");
        if (!out.empty()) {
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
        }
    }
    ImGui::BeginDisabled(!can_undo());
    if (ImGui::Button("撤销")) undo();
    ImGui::EndDisabled();
    ImGui::SameLine();
    ImGui::BeginDisabled(!can_redo());
    if (ImGui::Button("重做")) redo();
    ImGui::EndDisabled();
    ImGui::SameLine();
    ImGui::TextDisabled("%s", model_path.empty() ? "(未加载)" : model_path.c_str());

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
        tab("信息", &panel_info);
        tab("骨骼", &panel_bone);
        tab("表示枠", &panel_frame);
        tab("顶点", &panel_vertex);
        tab("材质", &panel_material);
        tab("面", &panel_face);
        tab("形态", &panel_morph);
        tab("物理", &panel_physics);
        tab("柔体", &panel_soft);
        tab("设置", &panel_settings);
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
    settings.toon = toon;
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
    }
}


int main(int argc, char** argv) {
    // CRT 的 argv 在 Windows 上按 ANSI 代码页解码，中文/日文路径会变成乱码，
    // 这里统一还原成 UTF-8 后再交给内部路径处理（fs.hpp）。
    const std::vector<std::string> args = pmx::utf8_args(argc, argv);
    if (!glfwInit()) {
        std::fprintf(stderr, "GLFW 初始化失败\n");
        return 1;
    }
    glfwWindowHint(GLFW_CONTEXT_VERSION_MAJOR, 4);
    glfwWindowHint(GLFW_CONTEXT_VERSION_MINOR, 6);
    glfwWindowHint(GLFW_OPENGL_PROFILE, GLFW_OPENGL_CORE_PROFILE);
    glfwWindowHint(GLFW_SAMPLES, 4);
    // 描边依赖模板缓冲（与 Python 版相同的倒置壳遮罩算法）。
    glfwWindowHint(GLFW_STENCIL_BITS, 8);

    GLFWwindow* window = glfwCreateWindow(1440, 900, "PmxStudio C++", nullptr, nullptr);
    if (!window) {
        std::fprintf(stderr, "无法创建 OpenGL 4.6 窗口\n");
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
        std::fprintf(stderr, "缺少 OpenGL 入口：%s\n", missing);
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
        std::fprintf(stderr, "渲染器初始化失败：%s\n", err.c_str());
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
