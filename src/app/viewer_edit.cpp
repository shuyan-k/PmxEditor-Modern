// 撤销栈（整模型快照 + 轻量姿态条目）与结构变化后的运行时重建。
#include "app/viewer.hpp"

#include <algorithm>
#include <chrono>
#include <utility>

#include "core/morph.hpp"

namespace {

constexpr std::size_t kUndoLimit = 12;
constexpr std::size_t kPoseLimit = 12;
// 整模型快照的内存预算（粗估）。高端模型动辄数百 MB / 份，只按条数限制会让
// 撤销栈随模型规模线性膨胀；超预算时从最旧的整模型条目开始丢弃。
constexpr std::size_t kUndoBytesBudget = 256ull * 1024ull * 1024ull;
// 无论预算如何，至少保留这么多整模型条目，保证「撤一步 / 重做一步」可用。
constexpr std::size_t kUndoModelKeep = 2;
constexpr double kCoalesceSeconds = 0.9;

double now_seconds() {
    using clock = std::chrono::steady_clock;
    return std::chrono::duration<double>(clock::now().time_since_epoch()).count();
}

// 粗略估算一份模型快照占用的堆内存，用于撤销栈的字节预算。
// 只统计大块（顶点 SoA / 索引 / 骨骼 / 形态 / 刚体）与字符串，误差不重要。
std::size_t approx_model_bytes(const pmx::Model& m) {
    const std::size_t add_uv = static_cast<std::size_t>(std::max(0, m.add_uv_count));
    const std::size_t per_vertex =
        sizeof(pmx::Vec3) * 2 + sizeof(pmx::Vec2) + sizeof(float) * 2 + add_uv * 4 * sizeof(float) +
        sizeof(std::uint8_t) + sizeof(std::array<int, 4>) + sizeof(std::array<float, 4>) +
        sizeof(std::array<float, 9>);
    std::size_t total = sizeof(pmx::Model);
    total += m.vertices.size() * per_vertex;
    total += m.indices.size() * sizeof(std::uint32_t);
    total += m.textures.size() * (sizeof(std::string) + 64);
    total += m.bones.size() * sizeof(pmx::Bone);
    total += m.materials.size() * sizeof(pmx::Material);
    total += m.morphs.size() * sizeof(pmx::Morph);
    total += m.frames.size() * sizeof(pmx::DisplayFrame);
    total += m.rigid.size() * sizeof(pmx::RigidBody);
    total += m.joints.size() * sizeof(pmx::Joint);
    total += m.soft_bodies.size() * sizeof(pmx::SoftBody);
    for (const auto& b : m.bones) total += b.name.size() + b.name_en.size();
    for (const auto& mt : m.materials) total += mt.name.size() + mt.name_en.size() + mt.memo.size();
    for (const auto& mo : m.morphs) {
        total += mo.name.size() + mo.name_en.size();
        total += mo.offsets.size() * sizeof(pmx::MorphOffset);
    }
    for (const auto& f : m.frames) {
        total += f.name.size() + f.name_en.size();
        total += f.items.size() * sizeof(pmx::DisplayFrameItem);
    }
    for (const auto& sb : m.soft_bodies) {
        total += sb.name.size() + sb.name_en.size();
        total += sb.anchors.size() * sizeof(pmx::SoftBodyAnchor);
        total += sb.pins.size() * sizeof(int);
    }
    total += m.name.size() + m.name_en.size() + m.comment.size() + m.comment_en.size() +
             m.path.size();
    return total;
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

    // 再按内存预算裁剪：从最旧的整模型条目开始丢，至少留下 kUndoModelKeep 条。
    std::size_t bytes = 0;
    std::size_t models = 0;
    for (const auto& e : stack) {
        if (e.has_model) {
            bytes += e.bytes;
            ++models;
        }
    }
    while (bytes > kUndoBytesBudget && models > kUndoModelKeep) {
        auto it = std::find_if(stack.begin(), stack.end(),
                               [](const Viewer::UndoEntry& e) { return e.has_model; });
        if (it == stack.end()) break;
        bytes -= it->bytes;
        --models;
        stack.erase(it);
    }
}

}  // namespace

std::string Viewer::window_title() const {
    std::string title = "PmxStudio";
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
    entry.bytes = approx_model_bytes(entry.model);
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

void Viewer::set_preview_mode(bool preview) {
    if (preview_mode == preview) return;
    preview_mode = preview;
    if (preview_mode) {
        // 进入预览：清掉编辑态选择与拖动，避免残留高亮 / 撤销记录。
        drag_mode = DRAG_NONE;
        drag_bone = -1;
        pick_choices.clear();
        select(SelKind::None, -1);
        status = "已切换到预览模式：模型只读，可控制视角 / 物理 / 动作 / 形态";
    } else {
        status = "已切换到编辑模式";
    }
}

void Viewer::edit(const std::string& label, const std::function<void(pmx::Model&)>& fn,
                  const std::string& kind, const std::string& coalesce) {
    if (!pose || !fn) return;
    // 预览模式下模型只读：所有修改入口直接忽略。
    if (preview_mode) return;
    push_undo(label, coalesce);
    fn(model);
    mark_dirty();
    refresh_after_edit(kind);
}

void Viewer::touched(const std::string& kind) {
    if (!pose || preview_mode) return;
    mark_dirty();
    refresh_after_edit(kind);
}

void Viewer::restore_pose(const PoseEntry& entry) {
    if (!pose || entry.base_rot.size() != static_cast<std::size_t>(pose->n)) return;
    pose->base_rot = entry.base_rot;
    pose->base_trans = entry.base_trans;
    pose->ov_rot = entry.ov_rot;
    pose->ov_trans = entry.ov_trans;
    pose->ik_enabled = entry.ik_enabled;
    // 撤销 / 重做换回了另一份姿态，不再保留「手动取消动作 / 手动关闭 IK」的记录。
    clear_manual_pose();
    morph_values = entry.values;
    morph_weights = entry.weights;
    morph_dirty = true;
    apply_morphs();
    pose->solve_ik();
    pose->world();
}

void Viewer::remember_manual_pose(int bone) {
    if (!motion || !pose || bone < 0 || bone >= pose->n) return;
    motion_muted_bones.insert(bone);
    motion_muted_rot[bone] = pose->base_rot[static_cast<std::size_t>(bone)];
    motion_muted_trans[bone] = pose->base_trans[static_cast<std::size_t>(bone)];
}

void Viewer::clear_manual_pose() {
    motion_muted_bones.clear();
    motion_muted_rot.clear();
    motion_muted_trans.clear();
    manual_ik_mutes.clear();
}

void Viewer::mute_conflicting_ik(int bone) {
    if (!pose || bone < 0 || bone >= pose->n) return;
    // CCD 只旋转链上的骨骼。旋转 b 本身不会移动 b 的原点（local_matrix = T*R），
    // 只有当 IK 会去旋转 b 的**祖先**时才会把 b 的 head 带走，这类链才需要临时关闭。
    std::unordered_set<int> ancestors;
    for (int p = pose->parent[static_cast<std::size_t>(bone)]; p >= 0 && p < pose->n;
         p = pose->parent[static_cast<std::size_t>(p)])
        ancestors.insert(p);
    // subtrees 含自身：控制器与 b 一起刚性移动时，整条链的结论不变，不用关闭。
    const std::vector<int>& sub = pose->subtrees[static_cast<std::size_t>(bone)];
    auto in_subtree = [&sub](int index) {
        return index >= 0 && std::find(sub.begin(), sub.end(), index) != sub.end();
    };
    for (int i = 0; i < static_cast<int>(model.bones.size()); ++i) {
        const pmx::Bone& owner = model.bones[static_cast<std::size_t>(i)];
        if (!(owner.flags & pmx::BF_IK) || !owner.ik) continue;
        bool affects = false;
        for (const pmx::IKLink& link : owner.ik->links)
            if (ancestors.count(link.bone)) {
                affects = true;
                break;
            }
        if (!affects) continue;
        // 只有这次旋转会改变目标 / 控制器（从而让 IK 重解）时才需要关闭：
        // 转目标骨本身或转目标骨下面的骨骼，IK 的结论不变，关掉反而破坏动作。
        const bool target_moved =
            owner.ik->target != bone && in_subtree(owner.ik->target);
        const bool controller_moved = i != bone && in_subtree(i);
        if (!target_moved && !controller_moved) continue;
        pose->set_ik_enabled(i, false);
        manual_ik_mutes.insert(i);
    }
}

void Viewer::apply_manual_ik_mutes() {
    if (!pose) return;
    for (int b : manual_ik_mutes) pose->set_ik_enabled(b, false);
}

void Viewer::undo() {
    if (preview_mode) return;
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
    cur.bytes = approx_model_bytes(cur.model);
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
    if (preview_mode) return;
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
    cur.bytes = approx_model_bytes(cur.model);
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
