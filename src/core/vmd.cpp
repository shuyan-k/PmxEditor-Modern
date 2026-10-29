#include "core/vmd.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <map>
#include <stdexcept>
#include <unordered_map>

#include "core/fs.hpp"
#include "core/text_codec.hpp"

namespace pmx {
namespace {

// ---------------------------------------------------------------- 插值曲线
float bezier_axis(float x1, float y1, float x2, float y2, float t) {
    auto bx = [&](float s) {
        const float u = 1.0f - s;
        return 3.0f * u * u * s * x1 + 3.0f * u * s * s * x2 + s * s * s;
    };
    auto by = [&](float s) {
        const float u = 1.0f - s;
        return 3.0f * u * u * s * y1 + 3.0f * u * s * s * y2 + s * s * s;
    };
    // Newton 迭代求 x(s)=t，再取 y(s)；遇到退化 / 不收敛时用二分兜底。
    float s = t;
    for (int i = 0; i < 8; ++i) {
        const float u = 1.0f - s;
        const float err = bx(s) - t;
        if (std::fabs(err) < 1e-6f) return clampf(by(s), 0.0f, 1.0f);
        const float d = 3.0f * u * u * x1 + 6.0f * u * s * (x2 - x1) + 3.0f * s * s * (1.0f - x2);
        if (std::fabs(d) < 1e-6f) break;
        s = clampf(s - err / d, 0.0f, 1.0f);
    }
    float lo = 0.0f, hi = 1.0f;
    for (int i = 0; i < 20; ++i) {
        s = 0.5f * (lo + hi);
        if (bx(s) < t) lo = s;
        else hi = s;
    }
    return clampf(by(0.5f * (lo + hi)), 0.0f, 1.0f);
}

// ---------------------------------------------------------------- 二进制读取
class Reader {
public:
    Reader(const std::uint8_t* data, std::size_t size) : data_(data), size_(size) {}

    bool remaining(std::size_t n) const { return offset_ + n <= size_; }
    std::size_t offset() const { return offset_; }

    std::uint32_t u32(const char* what) {
        need(4, what);
        std::uint32_t v = 0;
        std::memcpy(&v, data_ + offset_, 4);
        offset_ += 4;
        return v;
    }

    float f32(const char* what) {
        need(4, what);
        float v = 0.0f;
        std::memcpy(&v, data_ + offset_, 4);
        offset_ += 4;
        return v;
    }

    std::string raw(std::size_t n, const char* what) {
        need(n, what);
        std::string out(reinterpret_cast<const char*>(data_ + offset_), n);
        offset_ += n;
        return out;
    }

    void skip(std::size_t n, const char* what) {
        need(n, what);
        offset_ += n;
    }

private:
    void need(std::size_t n, const char* what) const {
        if (offset_ + n > size_)
            throw std::runtime_error(std::string("VMD 文件被截断（") + what + "）");
    }

    const std::uint8_t* data_;
    std::size_t size_;
    std::size_t offset_ = 0;
};

// 固定长度名称字段：截到首个 NUL 再解码。
std::string read_name_field(Reader& r, std::size_t width) {
    const std::string bytes = r.raw(width, "名称");
    const std::size_t nul = bytes.find('\0');
    const std::string text = nul == std::string::npos ? bytes : bytes.substr(0, nul);
    return trim_name(decode_text_name(text));
}

// 64 字节插值表：前 16 字节是 4×4 表格（行 X1/Y1/X2/Y2，列 X/Y/Z/旋转），其余为副本。
std::array<VmdCurve, 4> read_curves(const std::uint8_t* ip) {
    std::array<VmdCurve, 4> curves;
    for (int axis = 0; axis < 4; ++axis) {
        VmdCurve c;
        c.x1 = static_cast<float>(ip[axis]) / 127.0f;
        c.y1 = static_cast<float>(ip[4 + axis]) / 127.0f;
        c.x2 = static_cast<float>(ip[8 + axis]) / 127.0f;
        c.y2 = static_cast<float>(ip[12 + axis]) / 127.0f;
        curves[static_cast<std::size_t>(axis)] = c;
    }
    return curves;
}

// ---------------------------------------------------------------- 采样
template <class Key>
std::size_t upper_key_index(const std::vector<Key>& keys, double frame) {
    return static_cast<std::size_t>(
        std::upper_bound(keys.begin(), keys.end(), frame,
                         [](double f, const Key& k) { return f < k.frame; }) -
        keys.begin());
}

void sample_bone(const VmdBoneTrack& track, double frame, Vec3& pos, Quat& rot) {
    const std::vector<VmdBoneKey>& keys = track.keys;
    if (keys.empty()) {
        pos = Vec3{};
        rot = identity_quat();
        return;
    }
    if (frame <= keys.front().frame) {
        pos = keys.front().pos;
        rot = keys.front().rot;
        return;
    }
    if (frame >= keys.back().frame) {
        pos = keys.back().pos;
        rot = keys.back().rot;
        return;
    }
    const std::size_t hi = upper_key_index(keys, frame);
    const VmdBoneKey& a = keys[hi - 1];
    const VmdBoneKey& b = keys[hi];
    const float span = static_cast<float>(b.frame - a.frame);
    const float t = span > 0.0f ? static_cast<float>(frame - a.frame) / span : 0.0f;
    const std::array<VmdCurve, 4>& curve = a.curve;
    const float ex = curve[0].ease(t);
    const float ey = curve[1].ease(t);
    const float ez = curve[2].ease(t);
    pos.x = a.pos.x + (b.pos.x - a.pos.x) * ex;
    pos.y = a.pos.y + (b.pos.y - a.pos.y) * ey;
    pos.z = a.pos.z + (b.pos.z - a.pos.z) * ez;
    rot = slerp_quat(a.rot, b.rot, curve[3].ease(t));
}

float sample_morph(const VmdMorphTrack& track, double frame) {
    const std::vector<VmdMorphKey>& keys = track.keys;
    if (keys.empty()) return 0.0f;
    if (frame <= keys.front().frame) return keys.front().weight;
    if (frame >= keys.back().frame) return keys.back().weight;
    const std::size_t hi = upper_key_index(keys, frame);
    const VmdMorphKey& a = keys[hi - 1];
    const VmdMorphKey& b = keys[hi];
    const float span = static_cast<float>(b.frame - a.frame);
    const float t = span > 0.0f ? static_cast<float>(frame - a.frame) / span : 0.0f;
    return a.weight + (b.weight - a.weight) * t;
}

void sort_keys(VmdMotion& motion) {
    for (VmdBoneTrack& track : motion.bone_tracks)
        std::stable_sort(track.keys.begin(), track.keys.end(),
                         [](const VmdBoneKey& a, const VmdBoneKey& b) {
                             return a.frame < b.frame;
                         });
    for (VmdMorphTrack& track : motion.morph_tracks)
        std::stable_sort(track.keys.begin(), track.keys.end(),
                         [](const VmdMorphKey& a, const VmdMorphKey& b) {
                             return a.frame < b.frame;
                         });
    int max_frame = 0;
    for (const VmdBoneTrack& track : motion.bone_tracks)
        if (!track.keys.empty()) max_frame = std::max(max_frame, track.keys.back().frame);
    for (const VmdMorphTrack& track : motion.morph_tracks)
        if (!track.keys.empty()) max_frame = std::max(max_frame, track.keys.back().frame);
    motion.max_frame = std::max(0, max_frame);
}

// ---------------------------------------------------------------- 写出辅助
void put_u32(std::string& out, std::uint32_t v) {
    out.append(reinterpret_cast<const char*>(&v), 4);
}

void put_f32(std::string& out, float v) {
    out.append(reinterpret_cast<const char*>(&v), 4);
}

// 按 UTF-8 字符边界截断，避免把多字节字符切成两半。
std::size_t fit_utf8_length(const std::string& s, std::size_t width) {
    if (s.size() <= width) return s.size();
    std::size_t n = width;
    while (n > 0 && !valid_utf8(s.substr(0, n))) --n;
    return n;
}

// VMD 定长名称字段：优先 CP932，超出宽度时缩短，无法编码则写 UTF-8。
std::string encode_name_field(const std::string& name, std::size_t width) {
    std::string cp;
    if (utf8_to_cp932(name, cp) && cp.size() <= width) return cp;
    const std::string utf8 = name.substr(0, fit_utf8_length(name, width));
    std::string cp2;
    if (utf8_to_cp932(utf8, cp2) && cp2.size() <= width) return cp2;
    return utf8;
}

void put_name_field(std::string& out, const std::string& name, std::size_t width) {
    const std::string encoded = encode_name_field(name, width);
    out.append(encoded);
    out.append(width - encoded.size(), '\0');
}

// MMD 默认线性缓动：X1=Y1=20, X2=Y2=107（0..127）。
std::array<std::uint8_t, 64> default_interpolation() {
    std::array<std::uint8_t, 64> ip{};
    for (int i = 0; i < 16; ++i)
        ip[static_cast<std::size_t>(i)] = static_cast<std::uint8_t>(i < 8 ? 20 : 107);
    // 其余 48 字节是前 16 字节的副本。
    for (int i = 16; i < 64; ++i)
        ip[static_cast<std::size_t>(i)] = ip[static_cast<std::size_t>(i - 16)];
    return ip;
}

}  // namespace

float VmdCurve::ease(float t) const {
    if (t <= 0.0f) return 0.0f;
    if (t >= 1.0f) return 1.0f;
    if (!std::isfinite(x1) || !std::isfinite(y1) || !std::isfinite(x2) || !std::isfinite(y2))
        return t;
    // 线性（含全零的退化表）直接返回。
    if (x1 <= 0.0f && y1 <= 0.0f && x2 >= 1.0f && y2 >= 1.0f) return t;
    if (x1 <= 0.0f && x2 <= 0.0f) return t;
    if (y1 <= 0.0f && y2 <= 0.0f) return t;
    return bezier_axis(clampf(x1, 0.0f, 1.0f), clampf(y1, 0.0f, 1.0f), clampf(x2, 0.0f, 1.0f),
                       clampf(y2, 0.0f, 1.0f), t);
}

VmdMotion load_vmd(const std::string& path) {
    std::ifstream file = open_ifstream(path);
    if (!file) throw std::runtime_error("无法打开 VMD 文件：" + path);
    std::vector<std::uint8_t> data((std::istreambuf_iterator<char>(file)),
                                   std::istreambuf_iterator<char>());
    if (data.size() < 30) throw std::runtime_error("VMD 文件过短：" + path);

    const std::string header(reinterpret_cast<const char*>(data.data()), 30);
    if (header.rfind("Vocaloid Motion Data", 0) != 0)
        throw std::runtime_error("不是 VMD 动作文件：" + path);

    VmdMotion motion;
    motion.source = path;
    motion.version = trim_name(header.substr(21, 4));
    if (motion.version.empty()) motion.version = "0002";

    Reader r(data.data(), data.size());
    r.skip(30, "文件头");
    motion.model_name =
        read_name_field(r, motion.version == "0001" ? 10 : 20);

    const std::uint32_t bone_count = r.u32("骨骼帧数");
    if (bone_count > 1000000)
        throw std::runtime_error("VMD 骨骼帧数异常：" + path);

    std::unordered_map<std::string, std::size_t> bone_track_index;
    motion.bone_tracks.reserve(bone_count);
    for (std::uint32_t i = 0; i < bone_count; ++i) {
        const std::string name = read_name_field(r, 15);
        const std::uint32_t frame_raw = r.u32("骨骼帧号");
        const Vec3 pos{r.f32("骨骼位移"), r.f32("骨骼位移"), r.f32("骨骼位移")};
        Quat rot;
        rot.x = r.f32("骨骼旋转");
        rot.y = r.f32("骨骼旋转");
        rot.z = r.f32("骨骼旋转");
        rot.w = r.f32("骨骼旋转");
        const std::string ip_bytes = r.raw(64, "插值曲线");
        std::array<std::uint8_t, 64> ip{};
        std::memcpy(ip.data(), ip_bytes.data(), 64);

        if (name.empty()) continue;
        auto it = bone_track_index.find(name);
        std::size_t track = 0;
        if (it == bone_track_index.end()) {
            track = motion.bone_tracks.size();
            bone_track_index.emplace(name, track);
            motion.bone_tracks.push_back(VmdBoneTrack{name, {}});
        } else {
            track = it->second;
        }
        VmdBoneKey key;
        key.frame = static_cast<int>(frame_raw);
        key.pos = pos;
        key.rot = normalize(rot);
        key.curve = read_curves(ip.data());
        motion.bone_tracks[track].keys.push_back(key);
    }

    if (!r.remaining(4)) {
        sort_keys(motion);
        return motion;
    }
    const std::uint32_t morph_count = r.u32("形态帧数");
    if (morph_count > 1000000)
        throw std::runtime_error("VMD 形态帧数异常：" + path);
    std::unordered_map<std::string, std::size_t> morph_track_index;
    motion.morph_tracks.reserve(morph_count);
    for (std::uint32_t i = 0; i < morph_count; ++i) {
        const std::string name = read_name_field(r, 15);
        const std::uint32_t frame_raw = r.u32("形态帧号");
        const float weight = r.f32("形态权重");
        if (name.empty()) continue;
        auto it = morph_track_index.find(name);
        std::size_t track = 0;
        if (it == morph_track_index.end()) {
            track = motion.morph_tracks.size();
            morph_track_index.emplace(name, track);
            motion.morph_tracks.push_back(VmdMorphTrack{name, {}});
        } else {
            track = it->second;
        }
        motion.morph_tracks[track].keys.push_back(
            VmdMorphKey{static_cast<int>(frame_raw), weight});
    }

    // 相机 / 光照 / 阴影 / 表示枠(IK) 帧。相机只统计帧数。
    if (r.remaining(4)) {
        const std::uint32_t camera_count = r.u32("相机帧数");
        if (camera_count <= data.size() / 61) {
            motion.camera_keys = static_cast<int>(camera_count);
            const std::size_t bytes = static_cast<std::size_t>(camera_count) * 61;
            if (r.remaining(bytes)) r.skip(bytes, "相机帧");
        } else {
            motion.camera_keys = static_cast<int>(camera_count);
        }
    }

    // 光照帧（28 字节/帧）与自阴影帧（9 字节/帧）：不参与预览，跳到表示枠帧。
    if (r.remaining(4)) {
        const std::uint32_t light_count = r.u32("光照帧数");
        const std::size_t bytes = static_cast<std::size_t>(light_count) * 28;
        if (light_count > data.size() / 28 || !r.remaining(bytes)) {
            sort_keys(motion);
            return motion;
        }
        r.skip(bytes, "光照帧");
    }
    if (r.remaining(4)) {
        const std::uint32_t shadow_count = r.u32("自阴影帧数");
        const std::size_t bytes = static_cast<std::size_t>(shadow_count) * 9;
        if (shadow_count > data.size() / 9 || !r.remaining(bytes)) {
            sort_keys(motion);
            return motion;
        }
        r.skip(bytes, "自阴影帧");
    }

    // 表示枠帧（MMD 的 IK 开关就藏在这里）：
    // frame(u32) + visible(i8) + count(u32) + count × (name[20] + state(i8))。
    if (r.remaining(4)) {
        const std::uint32_t prop_count = r.u32("表示枠帧数");
        if (prop_count <= data.size() / 21) {
            motion.ik_frames.reserve(prop_count);
            for (std::uint32_t i = 0; i < prop_count; ++i) {
                const std::uint32_t frame = r.u32("表示枠帧号");
                const std::int8_t visible =
                    static_cast<std::int8_t>(r.raw(1, "可见性")[0]);
                const std::uint32_t state_count = r.u32("IK 状态数");
                if (state_count > 100000) break;
                VmdIkFrame f;
                f.frame = static_cast<int>(frame);
                f.visible = visible != 0;
                f.states.reserve(state_count);
                for (std::uint32_t k = 0; k < state_count; ++k) {
                    VmdIkState st;
                    st.bone = read_name_field(r, 20);
                    st.enabled = static_cast<std::int8_t>(r.raw(1, "IK 开关")[0]) != 0;
                    f.states.push_back(std::move(st));
                }
                motion.ik_frames.push_back(std::move(f));
            }
            std::stable_sort(motion.ik_frames.begin(), motion.ik_frames.end(),
                             [](const VmdIkFrame& a, const VmdIkFrame& b) {
                                 return a.frame < b.frame;
                             });
        }
    }

    sort_keys(motion);
    return motion;
}

VmdBinding bind_vmd(const Model& model, const VmdMotion& motion) {
    std::unordered_map<std::string, int> exact_bones;
    std::unordered_map<std::string, int> loose_bones;
    std::unordered_map<std::string, int> exact_morphs;
    std::unordered_map<std::string, int> loose_morphs;
    for (std::size_t i = 0; i < model.bones.size(); ++i) {
        const Bone& bone = model.bones[i];
        exact_bones.emplace(trim_name(bone.name), static_cast<int>(i));
        exact_bones.emplace(trim_name(bone.name_en), static_cast<int>(i));
        loose_bones.emplace(loose_name_key(bone.name), static_cast<int>(i));
        loose_bones.emplace(loose_name_key(bone.name_en), static_cast<int>(i));
    }
    for (std::size_t i = 0; i < model.morphs.size(); ++i) {
        const Morph& morph = model.morphs[i];
        exact_morphs.emplace(trim_name(morph.name), static_cast<int>(i));
        exact_morphs.emplace(trim_name(morph.name_en), static_cast<int>(i));
        loose_morphs.emplace(loose_name_key(morph.name), static_cast<int>(i));
        loose_morphs.emplace(loose_name_key(morph.name_en), static_cast<int>(i));
    }

    VmdBinding binding;
    binding.bone_target.assign(motion.bone_tracks.size(), -1);
    binding.morph_target.assign(motion.morph_tracks.size(), -1);
    for (std::size_t i = 0; i < motion.bone_tracks.size(); ++i) {
        const std::string& name = motion.bone_tracks[i].name;
        int target = -1;
        auto exact = exact_bones.find(trim_name(name));
        if (exact != exact_bones.end()) {
            target = exact->second;
        } else {
            auto loose = loose_bones.find(loose_name_key(name));
            if (loose != loose_bones.end()) target = loose->second;
        }
        if (target < 0) {
            binding.missing_bones.push_back(name);
            continue;
        }
        binding.bone_target[i] = target;
        ++binding.bone_matched;
        const std::string& model_name = model.bones[static_cast<std::size_t>(target)].name;
        if (name != model_name) binding.renamed_bones.emplace_back(name, model_name);
    }
    for (std::size_t i = 0; i < motion.morph_tracks.size(); ++i) {
        const std::string& name = motion.morph_tracks[i].name;
        int target = -1;
        auto exact = exact_morphs.find(trim_name(name));
        if (exact != exact_morphs.end()) {
            target = exact->second;
        } else {
            auto loose = loose_morphs.find(loose_name_key(name));
            if (loose != loose_morphs.end()) target = loose->second;
        }
        if (target < 0) {
            binding.missing_morphs.push_back(name);
            continue;
        }
        binding.morph_target[i] = target;
        ++binding.morph_matched;
        const std::string& model_name = model.morphs[static_cast<std::size_t>(target)].name;
        if (name != model_name) binding.renamed_morphs.emplace_back(name, model_name);
    }
    // 表示枠帧：把 IK 名称绑定到骨骼（只对模型里确实带 IK 的骨骼生效）。
    binding.ik_states.assign(motion.ik_frames.size(), {});
    for (std::size_t i = 0; i < motion.ik_frames.size(); ++i) {
        for (const VmdIkState& st : motion.ik_frames[i].states) {
            int target = -1;
            auto exact = exact_bones.find(trim_name(st.bone));
            if (exact != exact_bones.end()) {
                target = exact->second;
            } else {
                auto loose = loose_bones.find(loose_name_key(st.bone));
                if (loose != loose_bones.end()) target = loose->second;
            }
            const bool usable =
                target >= 0 && model.bones[static_cast<std::size_t>(target)].ik.has_value();
            if (usable) ++binding.ik_matched;
            binding.ik_states[i].emplace_back(usable ? target : -1, st.enabled);
        }
    }
    return binding;
}

void evaluate_vmd(const VmdMotion& motion, const VmdBinding& binding, double frame,
                  Pose& pose, MorphWeights* morph_weights) {
    pose.reset();
    // 表示枠 / IK：取 <= 当前帧的最后一个表示枠帧，状态保持到下一次变化。
    // 关掉足 IK 后腿由骨骼轨道直接驱动，这正是「腿对不对」的关键。
    if (!motion.ik_frames.empty() && !binding.ik_states.empty()) {
        std::size_t idx = 0;
        bool found = false;
        for (std::size_t i = 0; i < motion.ik_frames.size(); ++i) {
            if (motion.ik_frames[i].frame <= static_cast<int>(frame)) {
                idx = i;
                found = true;
            } else {
                break;
            }
        }
        if (found) {
            for (const auto& st : binding.ik_states[idx])
                if (st.first >= 0) pose.set_ik_enabled(st.first, st.second);
        }
    }
    const int n = pose.n;
    for (std::size_t i = 0; i < motion.bone_tracks.size(); ++i) {
        if (i >= binding.bone_target.size()) break;
        const int target = binding.bone_target[i];
        if (target < 0 || target >= n) continue;
        Vec3 pos;
        Quat rot;
        sample_bone(motion.bone_tracks[i], frame, pos, rot);
        pose.base_rot[static_cast<std::size_t>(target)] = rot;
        pose.base_trans[static_cast<std::size_t>(target)] = pos;
    }

    std::map<int, float> resolved;
    for (std::size_t i = 0; i < motion.morph_tracks.size(); ++i) {
        if (i >= binding.morph_target.size()) break;
        const int target = binding.morph_target[i];
        if (target < 0) continue;
        const float weight = sample_morph(motion.morph_tracks[i], frame);
        if (std::fabs(weight) > 1e-6f) resolved[target] = weight;
    }
    MorphWeights weights;
    weights.reserve(resolved.size());
    for (const auto& [index, weight] : resolved) weights.emplace_back(index, weight);

    pose.invalidate_world();
    pose.apply(&weights);
    if (morph_weights) *morph_weights = std::move(weights);
}

VmdExport save_vmd(const std::string& path, const Model& model, const Pose& pose,
                   const MorphWeights* morph_weights, const std::string& model_name,
                   bool include_all, int frame) {
    struct Entry {
        int index;
        Vec3 trans;
        Quat rot;
    };
    std::vector<Entry> entries;
    const int count = std::min(pose.n, static_cast<int>(model.bones.size()));
    for (int i = 0; i < count; ++i) {
        Quat rot = pose.base_rot[static_cast<std::size_t>(i)];
        const Vec3 trans = pose.base_trans[static_cast<std::size_t>(i)];
        const double len = std::sqrt(static_cast<double>(rot.x) * rot.x +
                                     static_cast<double>(rot.y) * rot.y +
                                     static_cast<double>(rot.z) * rot.z +
                                     static_cast<double>(rot.w) * rot.w);
        if (!std::isfinite(len) || len < 1e-8) {
            rot = identity_quat();
        } else {
            rot.x = static_cast<float>(rot.x / len);
            rot.y = static_cast<float>(rot.y / len);
            rot.z = static_cast<float>(rot.z / len);
            rot.w = static_cast<float>(rot.w / len);
        }
        if (!std::isfinite(trans.x) || !std::isfinite(trans.y) || !std::isfinite(trans.z))
            continue;
        const bool moved = std::fabs(trans.x) > 1e-6f || std::fabs(trans.y) > 1e-6f ||
                           std::fabs(trans.z) > 1e-6f;
        const bool turned = std::fabs(rot.w - 1.0f) > 1e-6f ||
                            std::fabs(rot.x) > 1e-6f || std::fabs(rot.y) > 1e-6f ||
                            std::fabs(rot.z) > 1e-6f;
        if (include_all || moved || turned) entries.push_back({i, trans, rot});
    }

    std::vector<std::pair<int, float>> morphs;
    if (morph_weights) {
        for (const auto& [index, weight] : *morph_weights) {
            if (index < 0 || index >= static_cast<int>(model.morphs.size())) continue;
            if (std::fabs(weight) <= 1e-4f || !std::isfinite(weight)) continue;
            morphs.emplace_back(index, weight);
        }
    }

    std::string title = model_name;
    if (title.empty()) title = model.name.empty() ? "pmxstudio" : model.name;

    std::string payload;
    payload.reserve(64 + entries.size() * 111 + morphs.size() * 23);
    std::string header = "Vocaloid Motion Data 0002";
    header.append(30 - header.size(), '\0');
    payload += header;
    put_name_field(payload, title, 20);
    put_u32(payload, static_cast<std::uint32_t>(entries.size()));
    const std::array<std::uint8_t, 64> ip = default_interpolation();
    for (const Entry& e : entries) {
        put_name_field(payload, model.bones[static_cast<std::size_t>(e.index)].name, 15);
        put_u32(payload, static_cast<std::uint32_t>(std::max(0, frame)));
        put_f32(payload, e.trans.x);
        put_f32(payload, e.trans.y);
        put_f32(payload, e.trans.z);
        put_f32(payload, e.rot.x);
        put_f32(payload, e.rot.y);
        put_f32(payload, e.rot.z);
        put_f32(payload, e.rot.w);
        payload.append(reinterpret_cast<const char*>(ip.data()), ip.size());
    }
    put_u32(payload, static_cast<std::uint32_t>(morphs.size()));
    for (const auto& [index, weight] : morphs) {
        put_name_field(payload, model.morphs[static_cast<std::size_t>(index)].name, 15);
        put_u32(payload, static_cast<std::uint32_t>(std::max(0, frame)));
        put_f32(payload, weight);
    }
    // 相机 / 光照 / 阴影 / IK 轨道：无内容。
    put_u32(payload, 0);
    put_u32(payload, 0);
    put_u32(payload, 0);
    put_u32(payload, 0);

    std::ofstream file = open_ofstream(path);
    if (!file) throw std::runtime_error("无法写入 VMD：" + path);
    file.write(payload.data(), static_cast<std::streamsize>(payload.size()));
    if (!file) throw std::runtime_error("写入 VMD 失败：" + path);

    VmdExport result;
    result.path = path;
    result.bones = static_cast<int>(entries.size());
    result.morphs = static_cast<int>(morphs.size());
    result.frame = frame;
    return result;
}

}  // namespace pmx
