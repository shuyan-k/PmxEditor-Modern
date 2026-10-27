#include "core/morph.hpp"

#include <unordered_set>

namespace pmx {
namespace {

void resolve_into(const Model& model, const MorphWeights& weights, int depth,
                  std::unordered_set<int>& seen, std::unordered_map<int, float>& out) {
    for (const auto& [mi, raw_w] : weights) {
        const float w = raw_w;
        if (w == 0.0f || mi < 0 || mi >= static_cast<int>(model.morphs.size())) continue;
        const Morph& mo = model.morphs[static_cast<std::size_t>(mi)];
        if ((mo.type == 0 || mo.type == MORPH_FLIP) && depth < 8 && !seen.count(mi)) {
            MorphWeights child;
            for (const MorphOffset& o : mo.offsets) {
                if (o.morph < 0 || o.morph >= static_cast<int>(model.morphs.size())) continue;
                if (o.ratio == 0.0f) continue;
                float cw = mo.type == 0 ? w * o.ratio : (1.0f - w) * o.ratio;
                bool merged = false;
                for (auto& [idx, value] : child) {
                    if (idx == o.morph) {
                        value += cw;
                        merged = true;
                        break;
                    }
                }
                if (!merged) child.emplace_back(o.morph, cw);
            }
            seen.insert(mi);
            resolve_into(model, child, depth + 1, seen, out);
            seen.erase(mi);
        } else if (mo.type != 0 && mo.type != MORPH_FLIP) {
            out[mi] += w;
        }
    }
}

}  // namespace

std::unordered_map<int, float> resolve_morph_weights(const Model& model,
                                                     const MorphWeights& weights) {
    std::unordered_map<int, float> out;
    if (weights.empty()) return out;
    std::unordered_set<int> seen;
    resolve_into(model, weights, 0, seen, out);
    return out;
}

VertexMorphResult apply_vertex_morphs(const Model& model, const MorphWeights& weights) {
    VertexMorphResult result;
    if (weights.empty()) {
        result.pos = &model.vertices.pos;
        result.uv = &model.vertices.uv;
        return result;
    }
    bool need_pos = false, need_uv = false;
    for (const auto& [mi, w] : weights) {
        if (w == 0.0f || mi < 0 || mi >= static_cast<int>(model.morphs.size())) continue;
        const int t = model.morphs[static_cast<std::size_t>(mi)].type;
        if (t == 1) need_pos = true;
        else if (t == 3) need_uv = true;
    }
    if (!need_pos && !need_uv) {
        result.pos = &model.vertices.pos;
        result.uv = &model.vertices.uv;
        return result;
    }
    if (need_pos) result.pos_storage = model.vertices.pos;
    if (need_uv) result.uv_storage = model.vertices.uv;
    const int nv = static_cast<int>(model.vertices.size());
    for (const auto& [mi, w] : weights) {
        if (w == 0.0f || mi < 0 || mi >= static_cast<int>(model.morphs.size())) continue;
        const Morph& mo = model.morphs[static_cast<std::size_t>(mi)];
        if (mo.type == 1) {
            for (const MorphOffset& o : mo.offsets) {
                if (o.vertex < 0 || o.vertex >= nv) continue;
                result.pos_storage[static_cast<std::size_t>(o.vertex)] +=
                    Vec3{o.offset.x, o.offset.y, o.offset.z} * w;
            }
        } else if (mo.type == 3) {
            for (const MorphOffset& o : mo.offsets) {
                if (o.vertex < 0 || o.vertex >= nv) continue;
                Vec2& uv = result.uv_storage[static_cast<std::size_t>(o.vertex)];
                uv.x += o.offset.x * w;
                uv.y += o.offset.y * w;
            }
        }
    }
    result.pos = need_pos ? &result.pos_storage : &model.vertices.pos;
    result.uv = need_uv ? &result.uv_storage : &model.vertices.uv;
    return result;
}

std::unordered_map<int, MaterialColor> material_morph_colors(const Model& model,
                                                             const MorphWeights& weights) {
    std::unordered_map<int, MaterialColor> out;
    for (const auto& [mi, w] : weights) {
        if (w == 0.0f || mi < 0 || mi >= static_cast<int>(model.morphs.size())) continue;
        const Morph& mo = model.morphs[static_cast<std::size_t>(mi)];
        if (mo.type != 8) continue;
        for (const MorphOffset& o : mo.offsets) {
            if (o.material < 0 || o.material >= static_cast<int>(model.materials.size())) continue;
            MaterialColor& cur = out[o.material];
            const float dz = o.diffuse.x - 1.0f, dw = o.diffuse.w - 1.0f;
            if (o.calc == 0) {
                cur.mul.x *= 1.0f + dz * w;
                cur.mul.y *= 1.0f + (o.diffuse.y - 1.0f) * w;
                cur.mul.z *= 1.0f + (o.diffuse.z - 1.0f) * w;
                cur.mul.w *= 1.0f + dw * w;
                cur.add.x += o.specular.x * w + o.ambient.x * w * 0.5f;
                cur.add.y += o.specular.y * w + o.ambient.y * w * 0.5f;
                cur.add.z += o.specular.z * w + o.ambient.z * w * 0.5f;
            } else {
                cur.mul.x += dz * w;
                cur.mul.y += (o.diffuse.y - 1.0f) * w;
                cur.mul.z += (o.diffuse.z - 1.0f) * w;
                cur.mul.w += dw * w;
                cur.add.x += o.specular.x * w;
                cur.add.y += o.specular.y * w;
                cur.add.z += o.specular.z * w;
            }
        }
    }
    return out;
}

}  // namespace pmx
