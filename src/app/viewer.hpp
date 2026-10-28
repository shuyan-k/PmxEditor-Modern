// 查看器共享状态：模型、姿态、渲染、撤销栈与检查器选择。
#pragma once

#include <functional>
#include <memory>
#include <string>
#include <unordered_map>
#include <vector>

#include "app/camera.hpp"
#include "core/morph.hpp"
#include "core/pmx.hpp"
#include "core/pose.hpp"
#include "gpu/renderer.hpp"
#ifdef PMX_ENABLE_PHYSICS
#include "physics/physics.hpp"
#endif

// 资源管理器文件对话框（Windows 专用，其他平台返回空路径）。
struct GLFWwindow;
extern const wchar_t* kPmxFilter;
extern const wchar_t* kVpdFilter;
std::string pick_open_file(const wchar_t* filter, const wchar_t* title);
std::string pick_save_file(const wchar_t* filter, const wchar_t* title,
                           const std::string& default_path, const wchar_t* def_ext);

// 检查器里的当前选择；骨骼/刚体/关节会同步到视口高亮。
enum class SelKind { None, Bone, Material, Morph, Rigid, Joint, Soft, Frame, Vertex, Face };

struct DocSelection {
    SelKind kind = SelKind::None;
    int index = -1;
};

struct Viewer {
    pmx::Model model;
    std::unique_ptr<pmx::Pose> pose;
    pmx::SceneRenderer renderer;
    pmx::OrbitCamera camera;
    pmx::RenderSettings settings;
    pmx::Selection selection;
#ifdef PMX_ENABLE_PHYSICS
    pmx::Physics physics;
    pmx::Physics* physics_ptr = &physics;
#else
    pmx::Physics* physics_ptr = nullptr;
#endif

    pmx::MorphWeights morph_weights;
    std::vector<float> morph_values;
    bool morph_dirty = true;

    std::string model_path;
    std::string vpd_path;
    std::string status = "未加载模型";
    std::string error;
    bool dirty = false;

    bool show_mesh = true;
    bool show_bones = true;
    bool show_rigid = true;
    bool show_joints = true;
    bool use_gpu = true;
    bool wireframe = false;
    bool grid = true;
    bool outline = true;
    float bone_alpha = 0.85f;
    float rigid_alpha = 0.55f;
    float joint_alpha = 0.75f;
    float toon = 1.0f;
    float bg[3] = {0.13f, 0.14f, 0.16f};
    float light[3] = {0.35f, 0.72f, 0.45f};

    bool physics_enabled = false;
    float gravity = -9.8f;
    int iterations = 30;
    bool ground = true;
    std::string theme = "dark";

    double fps_time = 0.0;
    float fps = 0.0f;
    int frames = 0;

    // 检查器选择（骨骼/刚体/关节同时驱动视口选中）。
    DocSelection sel;

    // 视口双击选中后，把对应面板切到前台并把列表滚到该行。
    // 标签切换要等下一帧 TabBarLayout 才生效，所以 reveal_tab 保持两帧。
    const char* reveal_tab = nullptr;
    int reveal_frames = 0;
    bool reveal_selection = false;

    // 骨骼/刚体/关节被整体隐藏时，双击选中的对象临时显示并高亮；
    // 取消选择后恢复隐藏。
    bool focus_overlay = false;

    // 视口拖动状态：未选中骨骼时左键只旋转视角，选中后左键位移 / 右键旋转。
    enum DragMode { DRAG_NONE, DRAG_ORBIT, DRAG_PAN, DRAG_MOVE, DRAG_ROTATE };
    DragMode drag_mode = DRAG_NONE;
    int drag_bone = -1;

    // 撤销条目：整模型快照 + 姿态/形态；has_model=false 时是轻量姿态条目。
    struct PoseEntry {
        std::vector<pmx::Quat> base_rot;
        std::vector<pmx::Vec3> base_trans;
        std::unordered_map<int, pmx::Quat> ov_rot;
        std::unordered_map<int, pmx::Vec3> ov_trans;
        pmx::MorphWeights weights;
        std::vector<float> values;
    };
    struct UndoEntry {
        std::string label;
        bool has_model = false;
        pmx::Model model;
        PoseEntry pose;
    };
    std::vector<UndoEntry> undo_stack;
    std::vector<UndoEntry> redo_stack;
    std::string last_coalesce;
    double last_coalesce_time = 0.0;
    bool suppress_undo = false;

    bool load_model(const std::string& path, std::string* err);
    bool apply_vpd_file(const std::string& path, std::string* err);
    bool save_model(const std::string& path, std::string* err);
    void apply_morphs();
    void reset_physics();
    void draw_ui();
    void handle_input(GLFWwindow* window, int fb_w, int fb_h);
    void handle_shortcuts();
    void draw_scene(int fb_w, int fb_h);
    std::string window_title() const;

    pmx::Selection pick_at(float sx, float sy, int fb_w, int fb_h, int kinds);
    const char* bone_drag_block(int index, bool move) const;
    std::string bone_name(int index) const;
    PoseEntry capture_pose() const;
    void restore_pose(const PoseEntry& entry);
    void reset_pose();
    void fit_camera();

    // ---------------------------------------------------------- 撤销 / 编辑
    void push_undo(const std::string& label, const std::string& coalesce = std::string());
    void push_pose_undo(const std::string& label, const std::string& coalesce = std::string());
    // 先压快照，再执行 fn；kind 决定刷新范围（bone/material/morph/physics/
    // physics_live/soft/structure/model）。
    void edit(const std::string& label, const std::function<void(pmx::Model&)>& fn,
              const std::string& kind = "model",
              const std::string& coalesce = std::string());
    // 已自行 push_undo 并直接改完模型时调用：标脏 + 按 kind 刷新。
    void touched(const std::string& kind);
    void undo();
    void redo();
    bool can_undo() const { return !undo_stack.empty(); }
    bool can_redo() const { return !redo_stack.empty(); }
    std::string undo_label() const;
    std::string redo_label() const;
    void mark_dirty() { dirty = true; }
    void clear_dirty() { dirty = false; }

    // 结构变化后重建 Pose / 网格 / 物理；尽量保留姿态、形态、相机与选择。
    void rebuild_runtime(bool geometry, bool skeleton, bool physics_rebuild);
    void refresh_after_edit(const std::string& kind);
    void select(SelKind kind, int index);
    void clamp_selection();
};
