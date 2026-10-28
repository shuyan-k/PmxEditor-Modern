#include "core/vpd.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <unordered_map>

#include "core/fs.hpp"

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#endif

namespace pmx {
namespace {

[[noreturn]] void fail(const char* fmt, int line, const char* what) {
    char buf[256];
    std::snprintf(buf, sizeof(buf), fmt, line, what);
    throw std::runtime_error(buf);
}

std::string local_to_utf8(const std::string& raw) {
#ifdef _WIN32
    if (raw.empty()) return raw;
    int wl = MultiByteToWideChar(932, 0, raw.data(), static_cast<int>(raw.size()), nullptr, 0);
    if (wl <= 0) return raw;
    std::wstring wide(static_cast<std::size_t>(wl), L'\0');
    MultiByteToWideChar(932, 0, raw.data(), static_cast<int>(raw.size()), wide.data(), wl);
    int u8l = WideCharToMultiByte(CP_UTF8, 0, wide.data(), wl, nullptr, 0, nullptr, nullptr);
    if (u8l <= 0) return raw;
    std::string out(static_cast<std::size_t>(u8l), '\0');
    WideCharToMultiByte(CP_UTF8, 0, wide.data(), wl, out.data(), u8l, nullptr, nullptr);
    return out;
#else
    // 非 Windows 环境缺少 CP932 表时按字节保留，名称匹配会失败但不会崩溃。
    return raw;
#endif
}

bool valid_utf8(const std::string& s) {
    std::size_t i = 0;
    while (i < s.size()) {
        const auto c = static_cast<unsigned char>(s[i]);
        std::size_t len = 1;
        if (c < 0x80) {
            ++i;
            continue;
        } else if ((c & 0xE0) == 0xC0) {
            len = 2;
        } else if ((c & 0xF0) == 0xE0) {
            len = 3;
        } else if ((c & 0xF8) == 0xF0) {
            len = 4;
        } else {
            return false;
        }
        if (i + len > s.size()) return false;
        for (std::size_t k = 1; k < len; ++k)
            if ((static_cast<unsigned char>(s[i + k]) & 0xC0) != 0x80) return false;
        i += len;
    }
    return true;
}

std::string trim(const std::string& s) {
    std::size_t b = 0, e = s.size();
    while (b < e && std::isspace(static_cast<unsigned char>(s[b]))) ++b;
    while (e > b && std::isspace(static_cast<unsigned char>(s[e - 1]))) --e;
    return s.substr(b, e - b);
}

bool is_ignorable(const std::string& line) {
    const std::string s = trim(line);
    if (s.empty()) return true;
    if (s.rfind("//", 0) == 0 || s.rfind("#", 0) == 0 || s.rfind(";", 0) == 0) return true;
    return false;
}

std::string strip_comment(const std::string& line) {
    std::string out = line;
    for (const char* marker : {";", "//"}) {
        const std::size_t pos = out.find(marker);
        if (pos != std::string::npos) out = out.substr(0, pos);
    }
    return trim(out);
}

std::vector<double> numbers(const std::string& line, int count, const char* what, int line_no) {
    std::string normalized = line;
    for (char& ch : normalized)
        if (ch == ',') ch = ' ';
    std::istringstream ss(normalized);
    std::vector<double> values;
    double v;
    while (ss >> v) values.push_back(v);
    if (static_cast<int>(values.size()) != count)
        fail("第 %d 行的%s数值个数不符", line_no, what);
    for (double value : values)
        if (!std::isfinite(value)) fail("第 %d 行的%s包含非有限数值", line_no, what);
    return values;
}

std::string lower_ascii(std::string s) {
    for (char& c : s) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    return s;
}

// 宽松名称键：去空白/下划线、忽略大小写（NFKC 全半角归一在 C++ 端省略）。
std::string loose_key(const std::string& name) {
    std::string out;
    out.reserve(name.size());
    for (std::size_t i = 0; i < name.size();) {
        const auto c = static_cast<unsigned char>(name[i]);
        if (c == ' ' || c == '_' || c == '\t') {
            ++i;
            continue;
        }
        if (name.compare(i, 3, "\xE3\x80\x80") == 0) {  // U+3000 全角空格
            i += 3;
            continue;
        }
        // ASCII 小写化；多字节原样保留
        if (c < 0x80) {
            out.push_back(static_cast<char>(std::tolower(c)));
            ++i;
        } else {
            out.push_back(name[i]);
            ++i;
        }
    }
    return out;
}

}  // namespace

std::string decode_vpd_text(const std::vector<std::uint8_t>& data, std::string* encoding) {
    auto set = [encoding](const char* name) {
        if (encoding) *encoding = name;
    };
    if (data.size() >= 3 && data[0] == 0xEF && data[1] == 0xBB && data[2] == 0xBF) {
        set("utf-8");
        return std::string(reinterpret_cast<const char*>(data.data() + 3), data.size() - 3);
    }
    if (data.size() >= 2 && data[0] == 0xFF && data[1] == 0xFE) {
        std::string out;
        for (std::size_t i = 2; i + 1 < data.size(); i += 2) {
            const std::uint32_t cp = static_cast<std::uint32_t>(data[i]) |
                                     (static_cast<std::uint32_t>(data[i + 1]) << 8);
            if (cp < 0x80) {
                out.push_back(static_cast<char>(cp));
            } else if (cp < 0x800) {
                out.push_back(static_cast<char>(0xC0 | (cp >> 6)));
                out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
            } else {
                out.push_back(static_cast<char>(0xE0 | (cp >> 12)));
                out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
                out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
            }
        }
        set("utf-16le");
        return out;
    }
    std::string raw(reinterpret_cast<const char*>(data.data()), data.size());
    if (valid_utf8(raw)) {
        set("utf-8");
        return raw;
    }
    set("cp932");
    return local_to_utf8(raw);
}

VpdFile load_vpd(const std::string& path) {
    std::ifstream f = open_ifstream(path);
    if (!f) throw std::runtime_error("无法打开 VPD 文件：" + path);
    std::vector<std::uint8_t> data((std::istreambuf_iterator<char>(f)),
                                   std::istreambuf_iterator<char>());
    std::string encoding;
    const std::string text = decode_vpd_text(data, &encoding);
    return parse_vpd_text(text, path, encoding);
}

VpdFile parse_vpd_text(const std::string& text, const std::string& source,
                       const std::string& encoding) {
    std::vector<std::string> lines;
    {
        std::istringstream ss(text);
        std::string line;
        while (std::getline(ss, line)) {
            if (!line.empty() && line.back() == '\r') line.pop_back();
            lines.push_back(line);
        }
    }

    VpdFile file;
    file.source = source;
    file.encoding = encoding;
    std::size_t index = 0;
    while (index < lines.size()) {
        const std::string raw = trim(lines[index]);
        const int line_no = static_cast<int>(index) + 1;
        ++index;
        if (is_ignorable(raw)) continue;
        const std::string lower = lower_ascii(raw);
        const bool is_bone = lower.rfind("bone", 0) == 0;
        const bool is_morph = lower.rfind("morph", 0) == 0;
        const std::size_t brace = raw.find('{');
        if (brace == std::string::npos || !(is_bone || is_morph)) continue;

        std::string name = trim(raw.substr(brace + 1));
        const std::size_t close = name.find('}');
        if (close != std::string::npos) name = trim(name.substr(0, close));
        if (name.empty()) fail("第 %d 行的%s名称为空", line_no, is_bone ? "骨骼" : "形态");

        // 收集块体直到右花括号
        std::vector<std::pair<std::string, int>> body;
        bool closed = false;
        while (index < lines.size()) {
            const int content_no = static_cast<int>(index) + 1;
            std::string content = strip_comment(lines[index]);
            ++index;
            if (content.empty()) continue;
            const std::size_t rb = content.find('}');
            if (rb != std::string::npos) {
                const std::string head = trim(content.substr(0, rb));
                if (!head.empty()) body.emplace_back(head, content_no);
                closed = true;
                break;
            }
            body.emplace_back(content, content_no);
        }
        if (!closed) fail("第 %d 行的%s块缺少右花括号", line_no, is_bone ? "骨骼" : "形态");

        if (is_morph) {
            if (body.size() != 1) fail("第 %d 行的形态块应只有 1 行权重", line_no, "形态");
            VpdMorph mo;
            mo.name = name;
            mo.weight = static_cast<float>(numbers(body[0].first, 1, "形态权重", body[0].second)[0]);
            mo.line = line_no;
            file.morphs.push_back(std::move(mo));
            continue;
        }

        std::pair<std::string, int> pos_line, rot_line;
        if (body.size() == 2) {
            pos_line = body[0];
            rot_line = body[1];
        } else if (body.size() == 3) {
            pos_line = body[1];
            rot_line = body[2];
        } else {
            fail("第 %d 行的骨骼块行数应为 2 或 3", line_no, "骨骼");
        }

        VpdBone bone;
        bone.name = name;
        bone.line = line_no;
        const auto p = numbers(pos_line.first, 3, "位移", pos_line.second);
        bone.pos = {static_cast<float>(p[0]), static_cast<float>(p[1]),
                    static_cast<float>(p[2])};
        const auto r = numbers(rot_line.first, 4, "四元数", rot_line.second);
        bone.rot = {static_cast<float>(r[0]), static_cast<float>(r[1]),
                    static_cast<float>(r[2]), static_cast<float>(r[3])};
        const float len = std::sqrt(bone.rot.x * bone.rot.x + bone.rot.y * bone.rot.y +
                                    bone.rot.z * bone.rot.z + bone.rot.w * bone.rot.w);
        if (len < 1e-8f) fail("第 %d 行的%s四元数长度为 0", rot_line.second, "四元数");
        bone.rot = Quat(bone.rot.x / len, bone.rot.y / len, bone.rot.z / len, bone.rot.w / len);
        file.bones.push_back(std::move(bone));
    }
    if (file.bones.empty() && file.morphs.empty())
        throw std::runtime_error("VPD 中没有找到任何骨骼或形态块");
    return file;
}

VpdMatchResult apply_vpd(const Model& model, Pose& pose, const VpdFile& vpd,
                         MorphWeights* morph_weights) {
    std::unordered_map<std::string, int> exact_bones;
    std::unordered_map<std::string, int> loose_bones;
    std::unordered_map<std::string, int> exact_morphs;
    std::unordered_map<std::string, int> loose_morphs;
    for (std::size_t i = 0; i < model.bones.size(); ++i) {
        const Bone& b = model.bones[i];
        exact_bones.emplace(trim(b.name), static_cast<int>(i));
        exact_bones.emplace(trim(b.name_en), static_cast<int>(i));
        loose_bones.emplace(loose_key(b.name), static_cast<int>(i));
        loose_bones.emplace(loose_key(b.name_en), static_cast<int>(i));
    }
    for (std::size_t i = 0; i < model.morphs.size(); ++i) {
        const Morph& mo = model.morphs[i];
        exact_morphs.emplace(trim(mo.name), static_cast<int>(i));
        exact_morphs.emplace(trim(mo.name_en), static_cast<int>(i));
        loose_morphs.emplace(loose_key(mo.name), static_cast<int>(i));
        loose_morphs.emplace(loose_key(mo.name_en), static_cast<int>(i));
    }

    VpdMatchResult result;
    result.total = static_cast<int>(vpd.bones.size());
    for (const VpdBone& entry : vpd.bones) {
        int target = -1;
        auto hit = exact_bones.find(trim(entry.name));
        if (hit == exact_bones.end()) {
            auto loose = loose_bones.find(loose_key(entry.name));
            if (loose != loose_bones.end()) target = loose->second;
        } else {
            target = hit->second;
        }
        if (target < 0) {
            result.missing.push_back(entry.name);
            continue;
        }
        ++result.matched;
        const std::string& target_name = model.bones[static_cast<std::size_t>(target)].name;
        if (entry.name != target_name) result.renamed.emplace_back(entry.name, target_name);
        pose.base_rot[static_cast<std::size_t>(target)] = entry.rot;
        pose.base_trans[static_cast<std::size_t>(target)] = entry.pos;
    }

    if (morph_weights) {
        for (const VpdMorph& entry : vpd.morphs) {
            int target = -1;
            auto hit = exact_morphs.find(trim(entry.name));
            if (hit == exact_morphs.end()) {
                auto loose = loose_morphs.find(loose_key(entry.name));
                if (loose != loose_morphs.end()) target = loose->second;
            } else {
                target = hit->second;
            }
            if (target < 0) continue;
            morph_weights->emplace_back(target, entry.weight);
            result.morph_weights.emplace_back(target, entry.weight);
        }
    }
    pose.invalidate_world();
    pose.apply(morph_weights);
    return result;
}

namespace {

// 数值格式化：小于半个末位单位时归零，避免导出 "-0.000000"。
std::string format_values(const double* values, int count, int digits) {
    std::string out;
    char buf[64];
    for (int i = 0; i < count; ++i) {
        double v = values[i];
        const double eps = 0.5 * std::pow(10.0, -digits);
        if (std::fabs(v) < eps || !std::isfinite(v)) v = 0.0;
        std::snprintf(buf, sizeof(buf), "%.*f", digits, v);
        if (i) out += ',';
        out += buf;
    }
    return out;
}

std::string join_quat(Quat q, int digits) {
    const double v[4] = {static_cast<double>(q.x), static_cast<double>(q.y),
                         static_cast<double>(q.z), static_cast<double>(q.w)};
    return format_values(v, 4, digits);
}

std::string join_vec3(Vec3 p, int digits) {
    const double v[3] = {static_cast<double>(p.x), static_cast<double>(p.y),
                         static_cast<double>(p.z)};
    return format_values(v, 3, digits);
}

#ifdef _WIN32
// UTF-8 → CP932；遇到无法表示的字符返回 false，由调用方退回 UTF-8。
bool utf8_to_cp932(const std::string& s, std::string& out) {
    if (s.empty()) {
        out.clear();
        return true;
    }
    const int wl = MultiByteToWideChar(CP_UTF8, 0, s.data(), static_cast<int>(s.size()),
                                       nullptr, 0);
    if (wl <= 0) return false;
    std::wstring wide(static_cast<std::size_t>(wl), L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.data(), static_cast<int>(s.size()), wide.data(), wl);
    BOOL used_default = FALSE;
    const int len = WideCharToMultiByte(932, 0, wide.data(), wl, nullptr, 0, nullptr,
                                        &used_default);
    if (len <= 0 || used_default) return false;
    out.assign(static_cast<std::size_t>(len), '\0');
    used_default = FALSE;
    WideCharToMultiByte(932, 0, wide.data(), wl, out.data(), len, nullptr, &used_default);
    return !used_default;
}
#endif

}  // namespace

std::string build_vpd_text(const Model& model, const Pose& pose,
                           const MorphWeights* morph_weights,
                           const std::string& model_name, bool include_all, int digits) {
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

    std::string title = model_name;
    if (title.empty()) title = (model.name.empty() ? "model" : model.name) + ".pmx";

    std::ostringstream out;
    out << "Vocaloid Pose Data file\n\n" << title << ";\n" << entries.size() << ";\n\n";
    for (std::size_t seq = 0; seq < entries.size(); ++seq) {
        const Entry& e = entries[seq];
        out << "Bone" << seq << '{' << model.bones[static_cast<std::size_t>(e.index)].name
            << "\n" << join_vec3(e.trans, digits) << ";\n"
            << join_quat(e.rot, digits) << ";\n}\n\n";
    }

    int morph_count = 0;
    if (morph_weights) {
        for (const auto& [index, weight] : *morph_weights) {
            if (index < 0 || index >= static_cast<int>(model.morphs.size())) continue;
            if (std::fabs(weight) <= 1e-4f || !std::isfinite(weight)) continue;
            const double w[1] = {static_cast<double>(weight)};
            out << "Morph" << morph_count << '{'
                << model.morphs[static_cast<std::size_t>(index)].name << "\n"
                << format_values(w, 1, digits) << ";\n}\n\n";
            ++morph_count;
        }
    }

    std::string text = out.str();
    while (!text.empty() && text.back() == '\n') text.pop_back();
    text += '\n';
    return text;
}

VpdExport save_vpd(const std::string& path, const Model& model, const Pose& pose,
                   const MorphWeights* morph_weights, const std::string& model_name,
                   bool include_all) {
    const std::string text = build_vpd_text(model, pose, morph_weights, model_name,
                                            include_all);
    VpdExport result;
    result.path = path;
    result.bones = 0;
    result.morphs = 0;
    // 计数用于界面提示：按行首的 Bone/Morph 块统计（骨骼名里也可能出现这些词）。
    for (std::size_t pos = text.find("\nBone"); pos != std::string::npos;
         pos = text.find("\nBone", pos + 5))
        ++result.bones;
    for (std::size_t pos = text.find("\nMorph"); pos != std::string::npos;
         pos = text.find("\nMorph", pos + 6))
        ++result.morphs;

    std::string payload;
#ifdef _WIN32
    if (utf8_to_cp932(text, payload)) {
        result.encoding = "cp932";
    } else {
        payload = text;
        result.encoding = "utf-8";
    }
#else
    payload = text;
    result.encoding = "utf-8";
#endif
    std::string crlf;
    crlf.reserve(payload.size() + payload.size() / 16);
    for (char ch : payload) {
        if (ch == '\n') crlf += "\r\n";
        else crlf += ch;
    }
    std::ofstream file = open_ofstream(path);
    if (!file) throw std::runtime_error("无法写入 VPD：" + path);
    file.write(crlf.data(), static_cast<std::streamsize>(crlf.size()));
    if (!file) throw std::runtime_error("写入 VPD 失败：" + path);
    return result;
}

}  // namespace pmx
