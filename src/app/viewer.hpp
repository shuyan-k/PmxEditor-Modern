// 查看器共享状态：模型、姿态、渲染、撤销栈与检查器选择。
#pragma once

#include <functional>
#include <memory>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

#include "app/camera.hpp"
#include "core/morph.hpp"
#include "core/pmx.hpp"
#include "core/pose.hpp"
#include "core/vmd.hpp"
#include "gpu/renderer.hpp"
#ifdef PMX_ENABLE_PHYSICS
#include "physics/physics.hpp"
#endif

// 资源管理器文件对话框（Windows 专用，其他平台返回空路径）。
struct GLFWwindow;
extern const wchar_t* kPmxFilter;
extern const wchar_t* kVpdFilter;
extern const wchar_t* kVmdFilter;
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
    std::string vmd_path;
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
    float rim = 0.18f;
    float bg[3] = {0.13f, 0.14f, 0.16f};
    float light[3] = {0.35f, 0.72f, 0.45f};

    // VMD 动作：导入后按 30 fps 时间轴播放；暂停时保留当前帧姿态。
    std::unique_ptr<pmx::VmdMotion> motion;
    pmx::VmdBinding motion_binding;
    float motion_frame = 0.0f;
    float motion_speed = 1.0f;
    bool motion_playing = false;
    bool motion_loop = true;
    bool motion_dirty = false;  // 帧号变化，下一帧需要重新写入姿态
    // 手动摆过姿态的骨骼：播放时只取消这些骨骼的动作，其余骨骼继续受 VMD 驱动。
    std::unordered_set<int> motion_muted_bones;
    std::unordered_map<int, pmx::Quat> motion_muted_rot;
    std::unordered_map<int, pmx::Vec3> motion_muted_trans;
    // 手动旋转 IK 链内的骨骼时临时关闭的 IK 链（控制器本身除外），
    // 避免 IK 把被旋转骨骼的原点又拉回去。
    std::unordered_set<int> manual_ik_mutes;

    bool physics_enabled = false;
    float gravity = -9.8f;
    int iterations = 30;
    bool ground = true;
    std::string theme = "dark";

    // 编辑模式：可修改模型（骨骼 / 材质 / 形态定义 / 物理刚体等）。
    // 预览模式：模型数据只读，只保留视角、物理、动作（VMD）与形态控制，
    // 与 PmxEditor 的预览窗口一致。
    bool preview_mode = false;
    void set_preview_mode(bool preview);

    // 关闭请求（窗口 X / Alt+F4 / 菜单「退出」）：有未保存修改时先弹确认框。
    bool close_requested = false;
    // 保存当前模型；路径为空或 always_ask 时弹文件对话框。取消 / 失败返回 false。
    bool save_model_dialog(bool always_ask);
    void draw_close_confirm();

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

    // Ctrl+F：切到预览模式的「检索」标签并把输入焦点放进搜索框。
    bool focus_preview_search = false;

    // 双击落点附近有多个可选中对象时，在鼠标旁列出候选让用户点选。
    std::vector<pmx::Selection> pick_choices;
    float pick_choice_pos[2] = {0.0f, 0.0f};
    int pick_choice_frame = -1;  // 打开那一帧不再判定「点击外部关闭」

    // 视口拖动状态：未选中骨骼时左键只旋转视角，选中后左键位移 / 右键旋转。
    enum DragMode { DRAG_NONE, DRAG_ORBIT, DRAG_PAN, DRAG_MOVE, DRAG_ROTATE };
    DragMode drag_mode = DRAG_NONE;
    int drag_bone = -1;
    // 本次按下是否已经真正产生位移 / 旋转（单纯点击不应取消骨骼的动作）。
    bool drag_moved = false;

    // 撤销条目：整模型快照 + 姿态/形态；has_model=false 时是轻量姿态条目。
    struct PoseEntry {
        std::vector<pmx::Quat> base_rot;
        std::vector<pmx::Vec3> base_trans;
        std::unordered_map<int, pmx::Quat> ov_rot;
        std::unordered_map<int, pmx::Vec3> ov_trans;
        // 手动摆姿时临时关闭的 IK 链也要随撤销一起回滚，否则撤销后腿仍然不受 IK 控制。
        std::unordered_map<int, bool> ik_enabled;
        pmx::MorphWeights weights;
        std::vector<float> values;
    };
    struct UndoEntry {
        std::string label;
        bool has_model = false;
        pmx::Model model;
        PoseEntry pose;
        // 整模型快照的粗略字节数，用于按内存预算裁剪撤销栈。
        std::size_t bytes = 0;
    };
    std::vector<UndoEntry> undo_stack;
    std::vector<UndoEntry> redo_stack;
    std::string last_coalesce;
    double last_coalesce_time = 0.0;
    bool suppress_undo = false;

    bool load_model(const std::string& path, std::string* err);
    bool apply_vpd_file(const std::string& path, std::string* err);
    bool load_vmd_file(const std::string& path, std::string* err);
    void clear_motion();
    void update_motion(float dt);
    void apply_motion_frame();
    // 记住被手动摆过的骨骼：播放时用这里的值覆盖 VMD 轨道。
    void remember_manual_pose(int bone);
    void clear_manual_pose();
    // 手动旋转骨骼 b 时，关闭那些会因为这次旋转而改变目标 / 链接位置的 IK 链。
    void mute_conflicting_ik(int bone);
    void apply_manual_ik_mutes();
    bool save_model(const std::string& path, std::string* err);
    void apply_morphs();
    void reset_physics();
    // 播放中的「软复位」：只清速度，不重摆刚体（MMD/Blender 播放时就是这种行为）。
    void settle_physics();
    void draw_ui();
    // 双击候选框：悬浮在鼠标旁，点选后提交选择。
    void draw_pick_choices();
    void handle_input(GLFWwindow* window, int fb_w, int fb_h);
    void handle_shortcuts();
    void draw_scene(int fb_w, int fb_h);
    std::string window_title() const;

    pmx::Selection pick_at(float sx, float sy, int fb_w, int fb_h, int kinds);
    // 落点附近所有可选中对象（按距离升序），双击多于一个时弹候选框。
    std::vector<pmx::Selection> pick_candidates_at(float sx, float sy, int fb_w, int fb_h,
                                                   int kinds);
    // 应用一次拾取结果：选中并联动检查器，NONE 则取消选择。
    void apply_pick(const pmx::Selection& hit);
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
