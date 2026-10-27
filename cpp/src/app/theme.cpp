// ImGui 主题与偏好持久化。配置文件是 UTF-8 的 key=value 文本，一行一项。
#include "app/theme.hpp"

#include <algorithm>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <string>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
// windef.h 把 near/far 定义成空宏，会破坏 PMX 结构体里的同名字段。
#undef near
#undef far
#endif

#include <imgui.h>

#include "app/viewer.hpp"

namespace {

namespace fs = std::filesystem;

#ifdef _WIN32
// Windows 的 fs::path 以宽字符存储，这里在 UTF-8 字符串与原生路径间转换。
std::wstring utf8_to_wide(const std::string& text) {
    if (text.empty()) return std::wstring();
    const int len = MultiByteToWideChar(CP_UTF8, 0, text.data(), static_cast<int>(text.size()),
                                        nullptr, 0);
    if (len <= 0) return std::wstring();
    std::wstring out(static_cast<std::size_t>(len), L'\0');
    MultiByteToWideChar(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), out.data(), len);
    return out;
}

std::string wide_to_utf8(const std::wstring& text) {
    if (text.empty()) return std::string();
    const int len = WideCharToMultiByte(CP_UTF8, 0, text.data(), static_cast<int>(text.size()),
                                        nullptr, 0, nullptr, nullptr);
    if (len <= 0) return std::string();
    std::string out(static_cast<std::size_t>(len), '\0');
    WideCharToMultiByte(CP_UTF8, 0, text.data(), static_cast<int>(text.size()), out.data(), len,
                        nullptr, nullptr);
    return out;
}

fs::path path_from_utf8(const std::string& text) { return fs::path(utf8_to_wide(text)); }

std::string path_to_utf8(const fs::path& path) { return wide_to_utf8(path.wstring()); }
#else
fs::path path_from_utf8(const std::string& text) { return fs::path(text); }

std::string path_to_utf8(const fs::path& path) { return path.string(); }
#endif

#ifdef _WIN32
// 环境变量直接取宽字符版本，避免中文用户名在 ANSI 代码页下被转坏。
std::wstring appdata_dir() {
    const DWORD size = GetEnvironmentVariableW(L"APPDATA", nullptr, 0);
    if (size == 0) return std::wstring();
    std::wstring buffer(size, L'\0');
    const DWORD written = GetEnvironmentVariableW(L"APPDATA", buffer.data(), size);
    if (written == 0 || written >= size) return std::wstring();
    buffer.resize(written);
    return buffer;
}
#endif

std::string trim(const std::string& text) {
    std::size_t begin = 0;
    std::size_t end = text.size();
    auto blank = [](char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; };
    while (begin < end && blank(text[begin])) ++begin;
    while (end > begin && blank(text[end - 1])) --end;
    return text.substr(begin, end - begin);
}

bool parse_bool(const std::string& text, bool& out) {
    if (text == "1" || text == "true" || text == "True") {
        out = true;
        return true;
    }
    if (text == "0" || text == "false" || text == "False") {
        out = false;
        return true;
    }
    return false;
}

bool parse_float(const std::string& text, float& out) {
    if (text.empty()) return false;
    char* end = nullptr;
    const float value = std::strtof(text.c_str(), &end);
    if (end == text.c_str() || *end != '\0') return false;
    out = value;
    return true;
}

bool parse_int(const std::string& text, int& out) {
    if (text.empty()) return false;
    char* end = nullptr;
    const long value = std::strtol(text.c_str(), &end, 10);
    if (end == text.c_str() || *end != '\0') return false;
    out = static_cast<int>(value);
    return true;
}

int as_bit(bool on) { return on ? 1 : 0; }

}  // namespace

void pmxtheme::apply_theme(const std::string& name) {
    if (name == "light") ImGui::StyleColorsLight();
    else ImGui::StyleColorsDark();

    ImGuiStyle& style = ImGui::GetStyle();
    style.WindowRounding = 6.0f;
    style.ChildRounding = 6.0f;
    style.FrameRounding = 4.0f;
    style.GrabRounding = 4.0f;
    style.PopupRounding = 5.0f;
    style.ScrollbarRounding = 6.0f;
    style.TabRounding = 4.0f;
    style.WindowBorderSize = 1.0f;
    style.ChildBorderSize = 1.0f;
    style.WindowPadding = ImVec2(10.0f, 10.0f);
    style.FramePadding = ImVec2(8.0f, 4.0f);
    style.ItemSpacing = ImVec2(8.0f, 6.0f);
}

std::string pmxtheme::settings_path() {
#ifdef _WIN32
    const std::wstring appdata = appdata_dir();
    if (!appdata.empty()) {
        const fs::path base(appdata);
        return path_to_utf8(base / L"PmxStudioCpp" / L"settings.ini");
    }
#endif
    return "settings.ini";
}

bool pmxtheme::load_settings(Viewer& v, std::string* err) {
    const std::string text = settings_path();
    const fs::path path = path_from_utf8(text);
    std::error_code ec;
    if (!fs::exists(path, ec) || ec) return false;

    std::ifstream in(path, std::ios::binary);
    if (!in) {
        if (err) *err = "无法读取配置文件：" + text;
        return false;
    }

    std::string line;
    while (std::getline(in, line)) {
        if (!line.empty() && line.back() == '\r') line.pop_back();
        const std::size_t eq = line.find('=');
        if (eq == std::string::npos) continue;
        const std::string key = trim(line.substr(0, eq));
        const std::string value = trim(line.substr(eq + 1));
        if (key.empty()) continue;

        bool flag = false;
        float number = 0.0f;
        int integer = 0;
        if (key == "theme") {
            if (!value.empty()) v.theme = value;
        } else if (key == "show_mesh" && parse_bool(value, flag)) {
            v.show_mesh = flag;
        } else if (key == "show_bones" && parse_bool(value, flag)) {
            v.show_bones = flag;
        } else if (key == "show_rigid" && parse_bool(value, flag)) {
            v.show_rigid = flag;
        } else if (key == "show_joints" && parse_bool(value, flag)) {
            v.show_joints = flag;
        } else if (key == "use_gpu" && parse_bool(value, flag)) {
            v.use_gpu = flag;
        } else if (key == "wireframe" && parse_bool(value, flag)) {
            v.wireframe = flag;
        } else if (key == "grid" && parse_bool(value, flag)) {
            v.grid = flag;
        } else if (key == "outline" && parse_bool(value, flag)) {
            v.outline = flag;
        } else if (key == "toon" && parse_bool(value, flag)) {
            v.toon = flag ? 1.0f : 0.0f;
        } else if (key == "bone_alpha" && parse_float(value, number)) {
            v.bone_alpha = std::clamp(number, 0.0f, 1.0f);
        } else if (key == "rigid_alpha" && parse_float(value, number)) {
            v.rigid_alpha = std::clamp(number, 0.0f, 1.0f);
        } else if (key == "joint_alpha" && parse_float(value, number)) {
            v.joint_alpha = std::clamp(number, 0.0f, 1.0f);
        } else if (key == "gravity" && parse_float(value, number)) {
            v.gravity = number;
        } else if (key == "iterations" && parse_int(value, integer)) {
            v.iterations = std::clamp(integer, 1, 60);
        } else if (key == "ground" && parse_bool(value, flag)) {
            v.ground = flag;
        } else if (key == "physics_enabled" && parse_bool(value, flag)) {
            v.physics_enabled = flag;
        } else if (key == "last_model") {
            // 只在尚未载入模型时恢复路径，避免覆盖当前会话的保存目标。
            if (v.model_path.empty() && !value.empty()) v.model_path = value;
        }
    }
    return true;
}

void pmxtheme::save_settings(const Viewer& v) {
    try {
        const std::string text = settings_path();
        const fs::path path = path_from_utf8(text);
        if (path.has_parent_path()) {
            std::error_code ec;
            fs::create_directories(path.parent_path(), ec);
        }

        std::ofstream out(path, std::ios::binary | std::ios::trunc);
        if (!out) return;

        out << "theme=" << v.theme << '\n';
        out << "show_mesh=" << as_bit(v.show_mesh) << '\n';
        out << "show_bones=" << as_bit(v.show_bones) << '\n';
        out << "show_rigid=" << as_bit(v.show_rigid) << '\n';
        out << "show_joints=" << as_bit(v.show_joints) << '\n';
        out << "use_gpu=" << as_bit(v.use_gpu) << '\n';
        out << "wireframe=" << as_bit(v.wireframe) << '\n';
        out << "grid=" << as_bit(v.grid) << '\n';
        out << "outline=" << as_bit(v.outline) << '\n';
        out << "toon=" << as_bit(v.toon > 0.5f) << '\n';
        out << "bone_alpha=" << v.bone_alpha << '\n';
        out << "rigid_alpha=" << v.rigid_alpha << '\n';
        out << "joint_alpha=" << v.joint_alpha << '\n';
        out << "gravity=" << v.gravity << '\n';
        out << "iterations=" << v.iterations << '\n';
        out << "ground=" << as_bit(v.ground) << '\n';
        out << "physics_enabled=" << as_bit(v.physics_enabled) << '\n';
        out << "last_model=" << v.model_path << '\n';
    } catch (...) {
        // 配置文件只是偏好，写失败不影响继续使用。
    }
}
