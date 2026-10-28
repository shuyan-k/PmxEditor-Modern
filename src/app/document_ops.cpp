// 结构性编辑（增删/复制/移动骨骼、材质、形态、表示枠、刚体、关节、柔体）。
// 语义逐条对齐 Python 版 src/pmxeditor/doc.py 第 230-771 行。
#include "app/document_ops.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <utility>
#include <vector>

namespace pmxdoc {
namespace {

// PMX 2.1 柔体标志（与 Python 版 pmx.py 的 SB_BEND_LINK / SB_CLUSTER 一致）。
constexpr std::uint8_t kSbBendLink = 0x01;
constexpr std::uint8_t kSbCluster = 0x02;

// 删除索引 removed 后的重映射：命中返回 -1，其后的索引整体减一。
int remap_index(int i, int removed) {
    if (i == removed) return -1;
    return i > removed ? i - 1 : i;
}

// 等价于 Python 的非负切片 indices[begin:end]（超界自动截断）。
std::vector<std::uint32_t> slice_indices(const std::vector<std::uint32_t>& v,
                                         long long begin, long long end) {
    const long long n = static_cast<long long>(v.size());
    if (begin < 0) begin = 0;
    if (end < 0) end = 0;
    if (begin > n) begin = n;
    if (end > n) end = n;
    if (end < begin) end = begin;
    return std::vector<std::uint32_t>(v.begin() + begin, v.begin() + end);
}

std::vector<std::uint32_t> slice_indices_to_end(const std::vector<std::uint32_t>& v,
                                                long long begin) {
    return slice_indices(v, begin, static_cast<long long>(v.size()));
}

// 按保留下来的旧顶点序号重排一列顶点数据（keep 递增）。
template <typename T>
void filter_by_keep(std::vector<T>& v, const std::vector<int>& keep) {
    std::vector<T> out;
    out.reserve(keep.size());
    for (int i : keep) {
        const std::size_t idx = static_cast<std::size_t>(i);
        if (idx >= v.size()) return;  // 数据长度与顶点数不一致时保持原样
        out.push_back(v[idx]);
    }
    v.swap(out);
}

// 附加 UV 是 add_uv_count * 4 个 float / 顶点的扁平数组，按步长重排。
void filter_add_uv(std::vector<float>& v, const std::vector<int>& keep, int stride) {
    if (stride <= 0 || v.empty()) return;
    const std::size_t s = static_cast<std::size_t>(stride);
    std::vector<float> out;
    out.reserve(keep.size() * s);
    for (int i : keep) {
        const std::size_t base = static_cast<std::size_t>(i) * s;
        if (base + s > v.size()) return;  // 宽度不一致时保持原样（Python 同样不做校验）
        out.insert(out.end(), v.begin() + base, v.begin() + base + s);
    }
    v.swap(out);
}

// 删除材质后重映射材质形态(8)的偏移；merge_into_prev 时被删材质并入前一个。
void remap_material_morphs(pmx::Model& m, int index, bool merge_into_prev) {
    for (auto& mo : m.morphs) {
        if (mo.type != 8) continue;
        for (auto& off : mo.offsets) {
            if (off.material == index) {
                off.material = merge_into_prev ? index - 1 : -1;
            } else if (off.material > index) {
                off.material -= 1;
            }
        }
        mo.offsets.erase(
            std::remove_if(mo.offsets.begin(), mo.offsets.end(),
                           [](const pmx::MorphOffset& o) { return o.material < 0; }),
            mo.offsets.end());
    }
}

// 删除材质后重映射柔体的材质引用。
void remap_soft_body_material(pmx::Model& m, int index) {
    for (auto& s : m.soft_bodies) {
        if (s.material == index) {
            s.material = -1;
        } else if (s.material > index) {
            s.material -= 1;
        }
    }
}

}  // namespace

// ---------------------------------------------------------------- 骨骼

int add_bone(pmx::Model& m, int parent) {
    pmx::Bone b;
    b.name = "新建骨骼";
    b.name_en = "new_bone";
    const int n = static_cast<int>(m.bones.size());
    if (parent >= 0 && parent < n) {
        const pmx::Bone& p = m.bones[static_cast<std::size_t>(parent)];
        b.parent = parent;
        pmx::Vec3 tail{p.pos.x, p.pos.y + 1.0f, p.pos.z};
        if ((p.flags & pmx::BF_TAIL_INDEX) && p.tail_bone >= 0 && p.tail_bone < n) {
            tail = m.bones[static_cast<std::size_t>(p.tail_bone)].pos;
        } else if (std::fabs(p.tail_offset.x) > 1e-6f ||
                   std::fabs(p.tail_offset.y) > 1e-6f ||
                   std::fabs(p.tail_offset.z) > 1e-6f) {
            tail = p.pos + p.tail_offset;
        }
        // 尾端与父骨重合时沿 Y 抬起 1，避免新骨骼长度为零。
        if (std::fabs(tail.x - p.pos.x) < 1e-4f &&
            std::fabs(tail.y - p.pos.y) < 0.05f &&
            std::fabs(tail.z - p.pos.z) < 1e-4f) {
            tail.y = p.pos.y + 1.0f;
        }
        b.pos = tail;
    }
    m.bones.push_back(b);
    return static_cast<int>(m.bones.size()) - 1;
}

int move_bone(pmx::Model& m, int index, int delta) {
    const int n = static_cast<int>(m.bones.size());
    if (index < 0 || index >= n) return index;
    const int dst = index + delta;
    if (dst < 0 || dst >= n) return index;

    // 交换后整个列表用同一张置换表重映射引用；越界索引保持原值。
    std::vector<int> perm(static_cast<std::size_t>(n));
    for (int i = 0; i < n; ++i) perm[static_cast<std::size_t>(i)] = i;
    std::swap(perm[static_cast<std::size_t>(index)], perm[static_cast<std::size_t>(dst)]);
    std::swap(m.bones[static_cast<std::size_t>(index)],
              m.bones[static_cast<std::size_t>(dst)]);
    auto mp = [&perm, n](int i) {
        return (i >= 0 && i < n) ? perm[static_cast<std::size_t>(i)] : i;
    };

    for (auto& b : m.bones) {
        b.parent = mp(b.parent);
        if ((b.flags & pmx::BF_TAIL_INDEX) && b.tail_bone >= 0) {
            b.tail_bone = mp(b.tail_bone);
        }
        b.append_parent = mp(b.append_parent);
        if (b.ik) {
            b.ik->target = mp(b.ik->target);
            for (auto& link : b.ik->links) link.bone = mp(link.bone);
        }
    }
    for (auto& bones : m.vertices.bones) {
        for (int c = 0; c < 4; ++c) {
            const int bi = bones[c];
            if (bi >= 0 && bi < n) bones[c] = perm[static_cast<std::size_t>(bi)];
        }
    }
    for (auto& mo : m.morphs) {
        if (mo.type != 2) continue;
        for (auto& off : mo.offsets) {
            if (off.bone >= 0 && off.bone < n) off.bone = mp(off.bone);
        }
    }
    for (auto& rb : m.rigid) rb.bone = mp(rb.bone);
    for (auto& f : m.frames) {
        for (auto& item : f.items) {
            if (item.type == 0) item.index = mp(item.index);
        }
    }
    return dst;
}

int duplicate_bone(pmx::Model& m, int index) {
    if (index < 0 || index >= static_cast<int>(m.bones.size())) return -1;
    const pmx::Bone& src = m.bones[static_cast<std::size_t>(index)];
    pmx::Bone b = src;
    b.name = src.name + "_副本";
    b.name_en = (src.name_en.empty() ? std::string("bone") : src.name_en) + "_copy";
    m.bones.push_back(std::move(b));
    return static_cast<int>(m.bones.size()) - 1;
}

int remove_bone(pmx::Model& m, int index) {
    const int n = static_cast<int>(m.bones.size());
    if (index < 0 || index >= n) return -1;
    const int parent = m.bones[static_cast<std::size_t>(index)].parent;
    m.bones.erase(m.bones.begin() + index);

    for (auto& b : m.bones) {
        if (b.parent == index) {
            // 被删骨骼的子级改挂到它的父级（Python 版同样不经过 _remap）。
            b.parent = parent;
        } else {
            b.parent = remap_index(b.parent, index);
        }
        if (b.flags & pmx::BF_TAIL_INDEX) {
            const int target = b.tail_bone;
            b.tail_bone = remap_index(b.tail_bone, index);
            if (target == index) {
                // 尾端正好指向被删骨骼：退回坐标偏移并清位。
                b.flags = static_cast<std::uint16_t>(b.flags & ~pmx::BF_TAIL_INDEX);
                b.tail_offset = pmx::Vec3{};
            }
        }
        b.append_parent = remap_index(b.append_parent, index);
        if (b.ik) {
            b.ik->target = remap_index(b.ik->target, index);
            for (auto& link : b.ik->links) link.bone = remap_index(link.bone, index);
            b.ik->links.erase(
                std::remove_if(b.ik->links.begin(), b.ik->links.end(),
                               [](const pmx::IKLink& l) { return l.bone < 0; }),
                b.ik->links.end());
            if (b.ik->target < 0) {
                b.ik.reset();
                b.flags = static_cast<std::uint16_t>(b.flags & ~pmx::BF_IK);
            }
        }
    }

    // 顶点权重：先替换为父骨骼（无父则 0），再把大于被删索引的骨骼整体减一。
    // 逐列执行，替换后的值也会参与第二遍判断（与 Python 的列式 np.where 一致）。
    for (auto& bones : m.vertices.bones) {
        for (int c = 0; c < 4; ++c) {
            if (bones[c] == index) bones[c] = parent >= 0 ? parent : 0;
            if (bones[c] > index) bones[c] -= 1;
        }
    }

    for (auto& mo : m.morphs) {
        if (mo.type != 2) continue;
        for (auto& off : mo.offsets) off.bone = remap_index(off.bone, index);
        mo.offsets.erase(
            std::remove_if(mo.offsets.begin(), mo.offsets.end(),
                           [](const pmx::MorphOffset& o) { return o.bone < 0; }),
            mo.offsets.end());
    }
    for (auto& rb : m.rigid) rb.bone = remap_index(rb.bone, index);
    for (auto& f : m.frames) {
        std::vector<pmx::DisplayFrameItem> items;
        for (const auto& item : f.items) {
            pmx::DisplayFrameItem kept = item;
            if (kept.type == 0) {
                kept.index = remap_index(kept.index, index);
                if (kept.index < 0) continue;
            }
            items.push_back(kept);
        }
        f.items = std::move(items);
    }
    // 柔体 anchor 记录的是刚体/顶点索引，与骨骼无关（Python 版此处也是空操作）。
    return std::min(index, static_cast<int>(m.bones.size()) - 1);
}

// ---------------------------------------------------------------- 材质

int add_material(pmx::Model& m) {
    pmx::Material mt;
    mt.name = "新建材质";
    mt.name_en = "new_material";
    mt.face_count = 0;
    m.materials.push_back(std::move(mt));
    return static_cast<int>(m.materials.size()) - 1;
}

int duplicate_material(pmx::Model& m, int index) {
    if (index < 0 || index >= static_cast<int>(m.materials.size())) return -1;
    const pmx::Material& src = m.materials[static_cast<std::size_t>(index)];
    pmx::Material mt = src;
    mt.name = src.name + "_副本";
    mt.name_en = (src.name_en.empty() ? std::string("material") : src.name_en) + "_copy";

    // 新材质排在列表末尾，它的面必须追加到扁平索引末尾，否则 face_count 会指向
    // 别的材质的面（原版 PmxEditor 的 Clone 也会连面一起复制）。
    const long long cnt = src.face_count;
    if (cnt > 0) {
        long long start = 0;
        for (int i = 0; i < index; ++i)
            start += m.materials[static_cast<std::size_t>(i)].face_count;
        const std::vector<std::uint32_t> faces = slice_indices(m.indices, start, start + cnt);
        m.indices.insert(m.indices.end(), faces.begin(), faces.end());
        mt.face_count = static_cast<int>(faces.size());
    }
    m.materials.push_back(std::move(mt));
    return static_cast<int>(m.materials.size()) - 1;
}

int reassign_faces(pmx::Model& m, int src, int start_face, int count_faces, int dst) {
    const int nmat = static_cast<int>(m.materials.size());
    if (src < 0 || src >= nmat || dst < 0 || dst >= nmat || src == dst) return 0;

    // face_count 存的是索引数，参数 start_face / count_faces 以三角面为单位。
    const long long src_faces = m.materials[static_cast<std::size_t>(src)].face_count / 3;
    const long long start = std::max(0, start_face);
    if (start >= src_faces) return 0;
    const long long count = std::min<long long>(count_faces, src_faces - start);
    if (count <= 0) return 0;

    // 按材质顺序切分扁平索引；face_count 超出部分的切片自动截断，剩余作附加区间。
    std::vector<std::vector<std::uint32_t>> parts;
    long long pos = 0;
    for (const auto& mt : m.materials) {
        const long long cnt = std::max(0, mt.face_count);
        parts.push_back(slice_indices(m.indices, pos, pos + cnt));
        pos += cnt;
    }
    std::vector<std::uint32_t> tail = slice_indices_to_end(m.indices, pos);

    long long a = start * 3;
    long long b = (start + count) * 3;
    std::vector<std::uint32_t>& part_src = parts[static_cast<std::size_t>(src)];
    const long long pn = static_cast<long long>(part_src.size());
    a = std::max(0LL, std::min(a, pn));
    b = std::max(a, std::min(b, pn));
    std::vector<std::uint32_t> moved(part_src.begin() + a, part_src.begin() + b);
    std::vector<std::uint32_t> rest;
    rest.reserve(part_src.size() - static_cast<std::size_t>(b - a));
    rest.insert(rest.end(), part_src.begin(), part_src.begin() + a);
    rest.insert(rest.end(), part_src.begin() + b, part_src.end());
    part_src = std::move(rest);
    parts[static_cast<std::size_t>(dst)].insert(
        parts[static_cast<std::size_t>(dst)].end(), moved.begin(), moved.end());
    m.materials[static_cast<std::size_t>(src)].face_count =
        static_cast<int>(part_src.size());
    m.materials[static_cast<std::size_t>(dst)].face_count =
        static_cast<int>(parts[static_cast<std::size_t>(dst)].size());

    std::vector<std::uint32_t> combined;
    combined.reserve(m.indices.size());
    for (const auto& part : parts)
        combined.insert(combined.end(), part.begin(), part.end());
    if (!tail.empty()) combined.insert(combined.end(), tail.begin(), tail.end());
    m.indices = std::move(combined);
    return static_cast<int>(count);
}

int compact_vertices(pmx::Model& m) {
    const int n = static_cast<int>(m.vertices.size());
    if (n == 0 || m.indices.empty()) return 0;

    std::vector<char> used(static_cast<std::size_t>(n), 0);
    for (std::uint32_t idx : m.indices) {
        if (idx < static_cast<std::uint32_t>(n)) used[static_cast<std::size_t>(idx)] = 1;
    }
    if (std::all_of(used.begin(), used.end(), [](char c) { return c != 0; })) return 0;

    std::vector<int> keep;
    std::vector<int> remap(static_cast<std::size_t>(n), -1);
    for (int i = 0; i < n; ++i) {
        if (!used[static_cast<std::size_t>(i)]) continue;
        remap[static_cast<std::size_t>(i)] = static_cast<int>(keep.size());
        keep.push_back(i);
    }

    pmx::VertexData& v = m.vertices;
    filter_by_keep(v.pos, keep);
    filter_by_keep(v.nrm, keep);
    filter_by_keep(v.uv, keep);
    if (!v.add_uv.empty()) filter_add_uv(v.add_uv, keep, m.add_uv_count * 4);
    filter_by_keep(v.edge, keep);
    filter_by_keep(v.wtype, keep);
    filter_by_keep(v.bones, keep);
    filter_by_keep(v.weights, keep);
    if (!v.sdef.empty()) filter_by_keep(v.sdef, keep);

    // 越界索引在 Python 里先被替换为 0 再查表；remap[0] 可能仍是 -1，
    // 写回 uint32 时与 int32 的 -1 位模式一致。
    for (auto& idx : m.indices) {
        const int safe = idx < static_cast<std::uint32_t>(n) ? static_cast<int>(idx) : 0;
        idx = static_cast<std::uint32_t>(remap[static_cast<std::size_t>(safe)]);
    }

    for (auto& mo : m.morphs) {
        // 顶点形态(1)与 UV 系形态(3..7)都按顶点索引寻址。
        if (mo.type != 1 && !(mo.type >= 3 && mo.type <= 7)) continue;
        std::vector<pmx::MorphOffset> out;
        out.reserve(mo.offsets.size());
        for (auto& off : mo.offsets) {
            const int vtx = off.vertex;
            const int nv = (vtx >= 0 && vtx < n)
                               ? remap[static_cast<std::size_t>(vtx)]
                               : -1;
            if (nv < 0) continue;
            off.vertex = nv;
            out.push_back(off);
        }
        mo.offsets = std::move(out);
    }

    for (auto& s : m.soft_bodies) {
        std::vector<pmx::SoftBodyAnchor> anchors;
        anchors.reserve(s.anchors.size());
        for (const auto& a : s.anchors) {
            const int nv = (a.vertex >= 0 && a.vertex < n)
                               ? remap[static_cast<std::size_t>(a.vertex)]
                               : -1;
            if (nv < 0) continue;
            anchors.push_back({a.rigid, nv, a.near});
        }
        s.anchors = std::move(anchors);
        std::vector<int> pins;
        pins.reserve(s.pins.size());
        for (int pv : s.pins) {
            if (pv < 0 || pv >= n) continue;
            const int np = remap[static_cast<std::size_t>(pv)];
            if (np >= 0) pins.push_back(np);
        }
        s.pins = std::move(pins);
    }
    return n - static_cast<int>(keep.size());
}

int remove_material(pmx::Model& m, int index, bool merge) {
    if (index < 0 || index >= static_cast<int>(m.materials.size())) return -1;

    if (merge && index > 0) {
        pmx::Material& prev = m.materials[static_cast<std::size_t>(index - 1)];
        prev.face_count += m.materials[static_cast<std::size_t>(index)].face_count;
        m.materials.erase(m.materials.begin() + index);
        remap_material_morphs(m, index, true);
        remap_soft_body_material(m, index);
        return index - 1;
    }

    // face_count 是索引数（每个三角面 3 个），与 indices 长度同单位。
    long long start = 0;
    for (int i = 0; i < index; ++i)
        start += m.materials[static_cast<std::size_t>(i)].face_count;
    const long long count = m.materials[static_cast<std::size_t>(index)].face_count;
    if (count > 0) {
        const long long total = static_cast<long long>(m.indices.size());
        long long a = start < 0 ? 0 : start;
        long long b = std::min(start + count, total);
        if (a > total) a = total;
        if (b < a) b = a;
        m.indices.erase(m.indices.begin() + a, m.indices.begin() + b);
    }
    m.materials.erase(m.materials.begin() + index);
    // 原版 PmxEditor 删除材质会把只被这些面引用的顶点一并删掉。
    if (count > 0) compact_vertices(m);

    remap_material_morphs(m, index, false);
    remap_soft_body_material(m, index);
    return std::min(index, static_cast<int>(m.materials.size()) - 1);
}

// ---------------------------------------------------------------- 形态

int add_morph(pmx::Model& m, int type) {
    pmx::Morph mo;
    mo.name = "新建形态";
    mo.name_en = "new_morph";
    mo.type = type;
    mo.panel = 4;
    m.morphs.push_back(std::move(mo));
    return static_cast<int>(m.morphs.size()) - 1;
}

int duplicate_morph(pmx::Model& m, int index) {
    if (index < 0 || index >= static_cast<int>(m.morphs.size())) return -1;
    const pmx::Morph& src = m.morphs[static_cast<std::size_t>(index)];
    pmx::Morph mo = src;
    mo.name = src.name + "_副本";
    mo.name_en = (src.name_en.empty() ? std::string("morph") : src.name_en) + "_copy";
    m.morphs.push_back(std::move(mo));
    return static_cast<int>(m.morphs.size()) - 1;
}

int remove_morph(pmx::Model& m, int index) {
    if (index < 0 || index >= static_cast<int>(m.morphs.size())) return -1;
    m.morphs.erase(m.morphs.begin() + index);

    for (auto& mo : m.morphs) {
        if (mo.type != 0 && mo.type != 9) continue;
        for (auto& off : mo.offsets) {
            if (off.morph == index) {
                off.morph = -1;
            } else if (off.morph > index) {
                off.morph -= 1;
            }
        }
        mo.offsets.erase(
            std::remove_if(mo.offsets.begin(), mo.offsets.end(),
                           [](const pmx::MorphOffset& o) { return o.morph < 0; }),
            mo.offsets.end());
    }
    for (auto& f : m.frames) {
        std::vector<pmx::DisplayFrameItem> items;
        items.reserve(f.items.size());
        for (const auto& item : f.items) {
            pmx::DisplayFrameItem kept = item;
            if (kept.type == 1) {
                if (kept.index == index) continue;
                if (kept.index > index) kept.index -= 1;
            }
            items.push_back(kept);
        }
        f.items = std::move(items);
    }
    return std::min(index, static_cast<int>(m.morphs.size()) - 1);
}

// ---------------------------------------------------------------- 表示枠

int add_frame(pmx::Model& m, int special) {
    pmx::DisplayFrame f;
    f.name = "新建表示枠";
    f.name_en = "new_frame";
    f.special = static_cast<std::uint8_t>(special & 1);
    m.frames.push_back(std::move(f));
    return static_cast<int>(m.frames.size()) - 1;
}

int duplicate_frame(pmx::Model& m, int index) {
    if (index < 0 || index >= static_cast<int>(m.frames.size())) return -1;
    const pmx::DisplayFrame& src = m.frames[static_cast<std::size_t>(index)];
    pmx::DisplayFrame f = src;
    f.name = src.name + "_副本";
    f.name_en = (src.name_en.empty() ? std::string("frame") : src.name_en) + "_copy";
    f.special = 0;
    m.frames.push_back(std::move(f));
    return static_cast<int>(m.frames.size()) - 1;
}

int remove_frame(pmx::Model& m, int index) {
    if (index < 0 || index >= static_cast<int>(m.frames.size())) return -1;
    m.frames.erase(m.frames.begin() + index);
    return std::min(index, static_cast<int>(m.frames.size()) - 1);
}

int move_frame(pmx::Model& m, int index, int delta) {
    const int n = static_cast<int>(m.frames.size());
    if (index < 0 || index >= n) return index;
    const int dst = index + delta;
    if (dst < 0 || dst >= n) return index;
    std::swap(m.frames[static_cast<std::size_t>(index)],
              m.frames[static_cast<std::size_t>(dst)]);
    return dst;
}

bool frame_add_item(pmx::Model& m, int index, int kind, int item) {
    if (index < 0 || index >= static_cast<int>(m.frames.size())) return false;
    pmx::DisplayFrame& f = m.frames[static_cast<std::size_t>(index)];
    const std::uint8_t ty = static_cast<std::uint8_t>(kind);
    if (item < 0) return false;
    for (const auto& it : f.items) {
        if (it.type == ty && it.index == item) return false;  // 同一项只能挂一次
    }
    f.items.push_back({ty, item});
    return true;
}

bool frame_remove_item(pmx::Model& m, int index, int pos) {
    if (index < 0 || index >= static_cast<int>(m.frames.size())) return false;
    pmx::DisplayFrame& f = m.frames[static_cast<std::size_t>(index)];
    if (pos < 0 || pos >= static_cast<int>(f.items.size())) return false;
    f.items.erase(f.items.begin() + pos);
    return true;
}

int frame_move_item(pmx::Model& m, int index, int pos, int delta) {
    if (index < 0 || index >= static_cast<int>(m.frames.size())) return pos;
    std::vector<pmx::DisplayFrameItem>& items =
        m.frames[static_cast<std::size_t>(index)].items;
    const int dst = pos + delta;
    if (pos < 0 || pos >= static_cast<int>(items.size()) || dst < 0 ||
        dst >= static_cast<int>(items.size())) {
        return pos;
    }
    std::swap(items[static_cast<std::size_t>(pos)], items[static_cast<std::size_t>(dst)]);
    return dst;
}

// ---------------------------------------------------------------- 刚体 / 关节

int add_rigid(pmx::Model& m, int bone) {
    pmx::RigidBody rb;
    rb.name = "新建刚体";
    rb.name_en = "new_rigid";
    rb.bone = bone;
    rb.mode = 1;
    rb.mass = 1.0f;
    rb.group = 0;
    rb.mask = 0xFFFF;
    if (bone >= 0 && bone < static_cast<int>(m.bones.size())) {
        rb.pos = m.bones[static_cast<std::size_t>(bone)].pos;
    }
    m.rigid.push_back(std::move(rb));
    return static_cast<int>(m.rigid.size()) - 1;
}

int duplicate_rigid(pmx::Model& m, int index) {
    if (index < 0 || index >= static_cast<int>(m.rigid.size())) return -1;
    const pmx::RigidBody& src = m.rigid[static_cast<std::size_t>(index)];
    pmx::RigidBody rb = src;
    rb.name = src.name + "_副本";
    rb.name_en = (src.name_en.empty() ? std::string("rigid") : src.name_en) + "_copy";
    m.rigid.push_back(std::move(rb));
    return static_cast<int>(m.rigid.size()) - 1;
}

int remove_rigid(pmx::Model& m, int index) {
    if (index < 0 || index >= static_cast<int>(m.rigid.size())) return -1;
    m.rigid.erase(m.rigid.begin() + index);

    for (auto& j : m.joints) {
        j.rigid_a = remap_index(j.rigid_a, index);
        j.rigid_b = remap_index(j.rigid_b, index);
    }
    m.joints.erase(
        std::remove_if(m.joints.begin(), m.joints.end(),
                       [](const pmx::Joint& j) { return j.rigid_a < 0 || j.rigid_b < 0; }),
        m.joints.end());

    for (auto& mo : m.morphs) {
        if (mo.type != 10) continue;
        for (auto& off : mo.offsets) off.rigid = remap_index(off.rigid, index);
        mo.offsets.erase(
            std::remove_if(mo.offsets.begin(), mo.offsets.end(),
                           [](const pmx::MorphOffset& o) { return o.rigid < 0; }),
            mo.offsets.end());
    }
    for (auto& s : m.soft_bodies) {
        std::vector<pmx::SoftBodyAnchor> anchors;
        anchors.reserve(s.anchors.size());
        for (const auto& a : s.anchors) {
            const int rid = remap_index(a.rigid, index);
            if (rid < 0) continue;
            anchors.push_back({rid, a.vertex, a.near});
        }
        s.anchors = std::move(anchors);
    }
    return std::min(index, static_cast<int>(m.rigid.size()) - 1);
}

int add_joint(pmx::Model& m) {
    pmx::Joint j;
    j.name = "新建关节";
    j.name_en = "new_joint";
    const int n = static_cast<int>(m.rigid.size());
    j.rigid_a = n >= 2 ? n - 2 : -1;
    j.rigid_b = n >= 1 ? n - 1 : -1;
    if (n > 0) j.pos = m.rigid[static_cast<std::size_t>(n - 1)].pos;
    m.joints.push_back(std::move(j));
    return static_cast<int>(m.joints.size()) - 1;
}

int duplicate_joint(pmx::Model& m, int index) {
    if (index < 0 || index >= static_cast<int>(m.joints.size())) return -1;
    const pmx::Joint& src = m.joints[static_cast<std::size_t>(index)];
    pmx::Joint j = src;
    j.name = src.name + "_副本";
    j.name_en = (src.name_en.empty() ? std::string("joint") : src.name_en) + "_copy";
    m.joints.push_back(std::move(j));
    return static_cast<int>(m.joints.size()) - 1;
}

int remove_joint(pmx::Model& m, int index) {
    if (index < 0 || index >= static_cast<int>(m.joints.size())) return -1;
    m.joints.erase(m.joints.begin() + index);
    return std::min(index, static_cast<int>(m.joints.size()) - 1);
}

// ---------------------------------------------------------------- 柔体

int add_softbody(pmx::Model& m) {
    pmx::SoftBody s;
    s.name = "新建柔体";
    s.name_en = "new_soft";
    s.shape = 0;
    s.material = m.materials.empty() ? -1 : 0;
    s.flags = static_cast<std::uint8_t>(kSbBendLink | kSbCluster);
    s.b_link_dist = 2;
    s.cluster_count = 10;
    s.total_mass = 2.5f;
    s.collision_margin = 0.05f;
    s.config = {1.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.5f, 0.5f, 0.0f, 0.0f, 0.0f, 0.0f};
    s.cluster = {0.5f, 0.5f, 0.5f, 0.5f, 0.5f, 0.5f};
    s.iteration = {1, 1, 1, 1};
    s.material_params = {1.0f, 1.0f, 1.0f};
    m.soft_bodies.push_back(std::move(s));
    return static_cast<int>(m.soft_bodies.size()) - 1;
}

int remove_softbody(pmx::Model& m, int index) {
    if (index < 0 || index >= static_cast<int>(m.soft_bodies.size())) return -1;
    m.soft_bodies.erase(m.soft_bodies.begin() + index);
    return std::min(index, static_cast<int>(m.soft_bodies.size()) - 1);
}

// ---------------------------------------------------------------- 面区间辅助

void recompute_face_counts(pmx::Model& m) {
    const long long total = static_cast<long long>(m.indices.size());
    long long pos = 0;
    for (auto& mt : m.materials) {
        const long long want = mt.face_count > 0 ? mt.face_count : 0;
        const long long take = std::min(want, total - pos);
        mt.face_count = static_cast<int>(take);
        pos += take;
    }
    // 所有材质取完后仍有索引，归给最后一个材质（没有材质时留作附加区间）。
    if (pos < total && !m.materials.empty()) {
        m.materials.back().face_count += static_cast<int>(total - pos);
    }
}

void material_face_range(const pmx::Model& m, int material, int* start_face, int* count) {
    // 返回三角面单位（face_count 是索引数，一个面 3 个索引），与面页的分页/移动一致。
    long long start = 0;
    long long cnt = 0;
    if (material >= 0 && material < static_cast<int>(m.materials.size())) {
        for (int i = 0; i < material; ++i) {
            const int fc = m.materials[static_cast<std::size_t>(i)].face_count;
            start += (fc > 0 ? fc : 0) / 3;
        }
        const int fc = m.materials[static_cast<std::size_t>(material)].face_count;
        cnt = (fc > 0 ? fc : 0) / 3;
    }
    if (start_face) *start_face = static_cast<int>(start);
    if (count) *count = static_cast<int>(cnt);
}

}  // namespace pmxdoc
