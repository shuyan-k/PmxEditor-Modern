// UTF-8 路径辅助。
// Windows 下 std::ifstream(const char*) / std::filesystem::path(const std::string&)
// 都按系统 ANSI 代码页解释，UTF-8 的中文/日文目录会直接打不开。所有文件访问
// 统一先转成宽字符 filesystem::path，路径字符串本身保持 UTF-8。
#pragma once

#include <filesystem>
#include <fstream>
#include <ios>
#include <string>

namespace pmx {

inline std::filesystem::path utf8_path(const std::string& utf8) {
#if defined(__cpp_lib_char8_t)
    return std::filesystem::path(std::u8string(utf8.begin(), utf8.end()));
#else
    return std::filesystem::u8path(utf8);
#endif
}

inline std::string utf8_string(const std::filesystem::path& path) {
#if defined(__cpp_lib_char8_t)
    const std::u8string u8 = path.u8string();
    return std::string(u8.begin(), u8.end());
#else
    return path.u8string();
#endif
}

inline std::ifstream open_ifstream(const std::string& path) {
    return std::ifstream(utf8_path(path), std::ios::binary);
}

inline std::ofstream open_ofstream(const std::string& path,
                                   std::ios::openmode mode = std::ios::binary |
                                                              std::ios::trunc) {
    return std::ofstream(utf8_path(path), mode);
}

inline bool path_exists(const std::string& path) {
    std::error_code ec;
    return std::filesystem::exists(utf8_path(path), ec);
}

}  // namespace pmx
