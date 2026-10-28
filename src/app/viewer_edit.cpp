// 撤销栈（整模型快照 + 轻量姿态条目）与结构变化后的运行时重建。
#include "app/viewer.hpp"

#include <algorithm>
#include <chrono>
#include <utility>

#include "core/morph.hpp"

namespace {

constexpr std::size_t kUndoLimit = 12;
constexpr std::size_t kPoseLimit = 12;
constexpr double kCoalesceSeconds = 0.9;

double now_seconds() {
    using clock = std::chrono::steady_clock;
    return std::chrono::duration<double>(clock::now().time_since_epoch()).count();
}

// 模型快照与姿态条目分开计数，互不挤占。
void trim_stack(std::vector<Viewer::UndoEntry>& stack) {
    auto trim_kind = [&stack](bool want_model, std::size_t limit) {
        while (true) {
            std::size_t count = 0;
            std::size_t first = stack.size();
            for (std::size_t i = 0; i < stack.size(); ++i) {
                if (stack[i].has_model == want_model) {
                    ++count;
                    first = std::min(first, i);
                }
            }
            if (count <= limit || first >= stack.size()) return;
            stack.erase(stack.begin() + static_cast<std::ptrdiff_t>(first));
        }
    };
    trim_kind(false, kPoseLimit);
    trim_kind(true, kUndoLimit);
}

}  // namespace

std::string Viewer::window_title() const {
    std::string title = "PmxStudio C++";
    if (!model_path.empty() || !model.name.empty()) {
        title += " — ";
        title += model.name.empty() ? model_path : model.name;
        if (dirty) title += " *";
    }
    return title;
}

std::string Viewer::undo_label() const {
    return undo_stack.empty() ? std::string() : undo_stack.back().label;
}

std::string Viewer::redo_label() const {
    return redo_stack.empty() ? std::string() : redo_stack.back().label;
}

void Viewer::push_undo(const std::string& label, const std::string& coalesce) {
    if (suppress_undo || !pose) return;
    const double now = now_seconds();
    if (!coalesce.empty() && coalesce == last_coalesce && now - last_coalesce_time < kCoalesceSeconds) {
        last_coalesce_time = now;
        return;
    }
    UndoEntry entry;
    entry.label = label;
    entry.has_model = true;
    entry.model = model;
    entry.pose = capture_pose();
    undo_stack.push_back(std::move(entry));
    trim_stack(undo_stack);
    redo_stack.clear();
    last_coalesce = coalesce;
    last_coalesce_time = now;
}

void Viewer::push_pose_undo(const std::string& label, const std::string& coalesce) {
    if (suppress_undo || !pose) return;
    const double now = now_seconds();
    if (!coalesce.empty() && coalesce == last_coalesce && now - last_coalesce_time < kCoalesceSeconds) {
        last_coalesce_time = now;
        return;
    }
    UndoEntry entry;
    entry.label = label;
    entry.has_model = false;
    entry.pose = capture_pose();
    undo_stack.push_back(std::move(entry));
    trim_stack(undo_stack);
    redo_stack.clear();
    last_coalesce = coalesce;
    last_coalesce_time = now;
}

void Viewer::edit(const std::string& label, const std::function<void(pmx::Model&)>& fn,
                  const std::string& kind, const std::string& coalesce) {
    if (!pose || !fn) return;
    push_undo(label, coalesce);
    fn(model);
    mark_dirty();
    refresh_after_edit(kind);
}

void Viewer::touched(const std::string& kind) {
    if (!pose) return;
    mark_dirty();
    refresh_after_edit(kind);
}

void Viewer::restore_pose(const PoseEntry& entry) {
    if (!pose || entry.base_rot.size() != static_cast<std::size_t>(pose->n)) return;
    pose->base_rot = entry.base_rot;
    pose->base_trans = entry.base_trans;
    pose->ov_rot = entry.ov_rot;
    pose->ov_trans = entry.ov_trans;
    morph_values = entry.values;
    morph_weights = entry.weights;
    morph_dirty = true;
    apply_morphs();
    pose->solve_ik();
    pose->world();
}

void Viewer::undo() {
    if (undo_stack.empty() || !pose) {
        status = "没有可撤销的操作";
        return;
    }
    last_coalesce.clear();
    UndoEntry entry = std::move(undo_stack.back());
    undo_stack.pop_back();
    if (!entry.has_model) {
        UndoEntry cur;
        cur.label = entry.label;
        cur.has_model = false;
        cur.pose = capture_pose();
        redo_stack.push_back(std::move(cur));
        trim_stack(redo_stack);
        restore_pose(entry.pose);
        status = "已撤销：" + entry.label;
        return;
    }
    UndoEntry cur;
    cur.label = entry.label;
    cur.has_model = true;
    cur.model = model;
    cur.pose = capture_pose();
    redo_stack.push_back(std::move(cur));
    trim_stack(redo_stack);

    model = std::move(entry.model);
    rebuild_runtime(true, true, true);
    restore_pose(entry.pose);
    clamp_selection();
    mark_dirty();
    status = "已撤销：" + entry.label;
}

void Viewer::redo() {
    if (redo_stack.empty() || !pose) {
        status = "没有可重做的操作";
        return;
    }
    last_coalesce.clear();
    UndoEntry entry = std::move(redo_stack.back());
    redo_stack.pop_back();
    if (!entry.has_model) {
        UndoEntry cur;
        cur.label = entry.label;
        cur.has_model = false;
        cur.pose = capture_pose();
        undo_stack.push_back(std::move(cur));
        trim_stack(undo_stack);
        restore_pose(entry.pose);
        status = "已重做：" + entry.label;
        return;
    }
    UndoEntry cur;
    cur.label = entry.label;
    cur.has_model = true;
    cur.model = model;
    cur.pose = capture_pose();
    undo_stack.push_back(std::move(cur));
    trim_stack(undo_stack);

    model = std::move(entry.model);
    rebuild_runtime(true, true, true);
    restore_pose(entry.pose);
    clamp_selection();
    mark_dirty();
    status = "已重做：" + entry.label;
}

void Viewer::refresh_after_edit(const std::string& kind) {
    if (!pose) return;
    if (kind == "structure" || kind == "reload") {
        rebuild_runtime(true, true, true);
    } else if (kind == "bone") {
        rebuild_runtime(true, true, false);
    } else if (kind == "material") {
        rebuild_runtime(true, false, false);
    } else if (kind == "physics") {
        rebuild_runtime(false, false, true);
    } else if (kind == "physics_live") {
#ifdef PMX_ENABLE_PHYSICS
        if (physics_ptr) physics.set_params(gravity, iterations);
#endif
        mark_dirty();
    } else if (kind == "soft") {
        rebuild_runtime(false, false, true);
    } else if (kind == "morph" || kind == "pose") {
        morph_dirty = true;
    } else {
        rebuild_runtime(false, true, false);
    }
}

void Viewer::rebuild_runtime(bool geometry, bool skeleton, bool physics_rebuild) {
    (void)skeleton;  // Pose 必须重建（它持有 Model 引用），这里统一处理
    PoseEntry old = capture_pose();
    const std::size_t old_morphs = morph_values.size();
    std::vector<float> old_values = morph_values;

    pose = std::make_unique<pmx::Pose>(model);
    if (old.base_rot.size() == static_cast<std::size_t>(pose->n)) {
        pose->base_rot = old.base_rot;
        pose->base_trans = old.base_trans;
        for (const auto& [i, q] : old.ov_rot)
            if (i >= 0 && i < pose->n) pose->ov_rot[i] = q;
        for (const auto& [i, t] : old.ov_trans)
            if (i >= 0 && i < pose->n) pose->ov_trans[i] = t;
    }

    morph_values.assign(model.morphs.size(), 0.0f);
    const std::size_t keep = std::min(old_morphs, model.morphs.size());
    std::copy(old_values.begin(), old_values.begin() + static_cast<std::ptrdiff_t>(keep),
              morph_values.begin());
    morph_weights.clear();
    for (std::size_t i = 0; i < morph_values.size(); ++i)
        if (morph_values[i] > 1e-4f) morph_weights.emplace_back(static_cast<int>(i), morph_values[i]);

    if (geometry) {
        std::string err;
        if (!renderer.upload_model(model, &err)) error = err;
    }

    morph_dirty = true;
    apply_morphs();
    pose->solve_ik();
    pose->world();

#ifdef PMX_ENABLE_PHYSICS
    if (physics_rebuild && physics_ptr) {
        physics.release();
        physics.gravity = gravity;
        physics.iterations = iterations;
        physics.enabled = physics_enabled;
        if (!physics.build(model)) status = "物理构建失败：" + physics.error;
        if (physics_enabled) physics.reset(*pose, &morph_weights, true);
    }
#endif
}

void Viewer::select(SelKind kind, int index) {
    sel.kind = kind;
    sel.index = index;
    switch (kind) {
        case SelKind::Bone:
            selection.kind = pmx::Selection::BONE;
            selection.index = index;
            break;
        case SelKind::Rigid:
            selection.kind = pmx::Selection::RIGID;
            selection.index = index;
            break;
        case SelKind::Joint:
            selection.kind = pmx::Selection::JOINT;
            selection.index = index;
            break;
        default:
            selection = pmx::Selection{};
            // 取消选择后，双击临时显示的叠加层对象恢复隐藏。
            focus_overlay = false;
            break;
    }
}

void Viewer::clamp_selection() {
    auto valid = [](int i, std::size_t n) { return i >= 0 && i < static_cast<int>(n); };
    bool ok = true;
    switch (sel.kind) {
        case SelKind::Bone: ok = valid(sel.index, model.bones.size()); break;
        case SelKind::Material: ok = valid(sel.index, model.materials.size()); break;
        case SelKind::Morph: ok = valid(sel.index, model.morphs.size()); break;
        case SelKind::Rigid: ok = valid(sel.index, model.rigid.size()); break;
        case SelKind::Joint: ok = valid(sel.index, model.joints.size()); break;
        case SelKind::Soft: ok = valid(sel.index, model.soft_bodies.size()); break;
        case SelKind::Frame: ok = valid(sel.index, model.frames.size()); break;
        case SelKind::Vertex: ok = valid(sel.index, model.vertices.size()); break;
        case SelKind::Face: ok = valid(sel.index, model.n_faces()); break;
        case SelKind::None: ok = false; break;
    }
    if (!ok) select(SelKind::None, -1);
    else select(sel.kind, sel.index);
}
