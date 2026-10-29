// 名称编码辅助：MMD 的 VMD / VPD 使用 Shift-JIS（CP932），社区导出的文件也可能是 UTF-8。
// 读取时先按 UTF-8 严格校验，校验失败再按 CP932 解码；写出时优先 CP932，失败退回 UTF-8。
#pragma once

#include <cctype>
#include <string>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#endif

namespace pmx {

inline bool valid_utf8(const std::string& s) {
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

inline bool ascii_only(const std::string& s) {
    for (char ch : s)
        if (static_cast<unsigned char>(ch) >= 0x80) return false;
    return true;
}

inline std::string cp932_to_utf8(const std::string& raw) {
#ifdef _WIN32
    if (raw.empty()) return raw;
    const int wl = MultiByteToWideChar(932, 0, raw.data(), static_cast<int>(raw.size()),
                                       nullptr, 0);
    if (wl <= 0) return raw;
    std::wstring wide(static_cast<std::size_t>(wl), L'\0');
    MultiByteToWideChar(932, 0, raw.data(), static_cast<int>(raw.size()), wide.data(), wl);
    const int u8l = WideCharToMultiByte(CP_UTF8, 0, wide.data(), wl, nullptr, 0, nullptr,
                                        nullptr);
    if (u8l <= 0) return raw;
    std::string out(static_cast<std::size_t>(u8l), '\0');
    WideCharToMultiByte(CP_UTF8, 0, wide.data(), wl, out.data(), u8l, nullptr, nullptr);
    return out;
#else
    // 非 Windows 环境缺少 CP932 转换表，按字节保留（名称匹配可能失败，但不会崩溃）。
    return raw;
#endif
}

// UTF-8 → CP932；含 CP932 无法表示的字符时返回 false，由调用方决定回退策略。
inline bool utf8_to_cp932(const std::string& s, std::string& out) {
#ifdef _WIN32
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
#else
    (void)s;
    out.clear();
    return false;
#endif
}

// 二进制名称字段解码：纯 ASCII 原样返回，否则优先 UTF-8、失败再按 CP932。
inline std::string decode_text_name(const std::string& raw) {
    if (raw.empty() || ascii_only(raw)) return raw;
    if (valid_utf8(raw)) return raw;
    return cp932_to_utf8(raw);
}

inline std::string trim_name(const std::string& s) {
    std::size_t b = 0, e = s.size();
    while (b < e && std::isspace(static_cast<unsigned char>(s[b]))) ++b;
    while (e > b && std::isspace(static_cast<unsigned char>(s[e - 1]))) --e;
    return s.substr(b, e - b);
}

// 宽松名称键：去空白 / 下划线、ASCII 小写（用于模型与动作名称的兜底匹配）。
inline std::string loose_name_key(const std::string& name) {
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

}  // namespace pmx
