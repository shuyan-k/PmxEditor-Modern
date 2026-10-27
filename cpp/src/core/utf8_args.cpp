#include "core/utf8_args.hpp"

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <shellapi.h>

#include <cwchar>
#endif

namespace pmx {

#ifdef _WIN32
namespace {

std::string wide_to_utf8(const wchar_t* text, int length) {
    if (!text || length <= 0) return std::string();
    const int bytes =
        ::WideCharToMultiByte(CP_UTF8, 0, text, length, nullptr, 0, nullptr, nullptr);
    if (bytes <= 0) return std::string();
    std::string out(static_cast<std::size_t>(bytes), '\0');
    ::WideCharToMultiByte(CP_UTF8, 0, text, length, out.data(), bytes, nullptr, nullptr);
    return out;
}

}  // namespace

std::vector<std::string> utf8_args(int argc, char** argv) {
    int wide_count = 0;
    LPWSTR* wide = ::CommandLineToArgvW(::GetCommandLineW(), &wide_count);
    if (!wide) {
        // 解析失败时退回 CRT 参数（此时非 ASCII 路径仍可能乱码，但至少不丢参数）。
        std::vector<std::string> out;
        out.reserve(static_cast<std::size_t>(argc));
        for (int i = 0; i < argc; ++i) out.emplace_back(argv[i] ? argv[i] : "");
        return out;
    }
    std::vector<std::string> out;
    out.reserve(static_cast<std::size_t>(wide_count));
    for (int i = 0; i < wide_count; ++i)
        out.push_back(wide_to_utf8(wide[i], static_cast<int>(std::wcslen(wide[i]))));
    ::LocalFree(wide);
    return out;
}
#else
std::vector<std::string> utf8_args(int argc, char** argv) {
    std::vector<std::string> out;
    out.reserve(static_cast<std::size_t>(argc));
    for (int i = 0; i < argc; ++i) out.emplace_back(argv[i] ? argv[i] : "");
    return out;
}
#endif

}  // namespace pmx
