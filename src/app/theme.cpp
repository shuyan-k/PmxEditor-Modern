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

#include "app/ui_scale.hpp"
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

struct ThemeColors {
    ImVec4 accent;
    ImVec4 accent_text;
    ImVec4 success;
    ImVec4 warning;
    ImVec4 danger;
};

ThemeColors g_colors;

// 深色主题：深海军蓝底 + 冰蓝强调色，与项目图标同一套色系。
void apply_dark_palette(ImGuiStyle& style) {
    ImVec4* c = style.Colors;
    const ImVec4 accent(0.52f, 0.76f, 0.98f, 1.0f);
    c[ImGuiCol_Text] = ImVec4(0.87f, 0.90f, 0.95f, 1.00f);
    c[ImGuiCol_TextDisabled] = ImVec4(0.47f, 0.53f, 0.61f, 1.00f);
    c[ImGuiCol_WindowBg] = ImVec4(0.055f, 0.067f, 0.086f, 0.98f);
    c[ImGuiCol_ChildBg] = ImVec4(0.071f, 0.086f, 0.108f, 0.92f);
    c[ImGuiCol_PopupBg] = ImVec4(0.075f, 0.090f, 0.115f, 0.98f);
    c[ImGuiCol_Border] = ImVec4(0.27f, 0.33f, 0.41f, 0.45f);
    c[ImGuiCol_BorderShadow] = ImVec4(0.00f, 0.00f, 0.00f, 0.00f);
    c[ImGuiCol_FrameBg] = ImVec4(0.11f, 0.13f, 0.16f, 1.00f);
    c[ImGuiCol_FrameBgHovered] = ImVec4(0.16f, 0.20f, 0.25f, 1.00f);
    c[ImGuiCol_FrameBgActive] = ImVec4(0.20f, 0.25f, 0.32f, 1.00f);
    c[ImGuiCol_TitleBg] = ImVec4(0.060f, 0.075f, 0.095f, 1.00f);
    c[ImGuiCol_TitleBgActive] = ImVec4(0.080f, 0.098f, 0.122f, 1.00f);
    c[ImGuiCol_TitleBgCollapsed] = ImVec4(0.060f, 0.075f, 0.095f, 0.80f);
    c[ImGuiCol_MenuBarBg] = ImVec4(0.060f, 0.075f, 0.095f, 1.00f);
    c[ImGuiCol_ScrollbarBg] = ImVec4(0.03f, 0.04f, 0.05f, 0.45f);
    c[ImGuiCol_ScrollbarGrab] = ImVec4(0.28f, 0.33f, 0.40f, 1.00f);
    c[ImGuiCol_ScrollbarGrabHovered] = ImVec4(0.37f, 0.44f, 0.53f, 1.00f);
    c[ImGuiCol_ScrollbarGrabActive] = ImVec4(0.46f, 0.57f, 0.70f, 1.00f);
    c[ImGuiCol_CheckMark] = accent;
    c[ImGuiCol_SliderGrab] = ImVec4(0.40f, 0.60f, 0.82f, 1.00f);
    c[ImGuiCol_SliderGrabActive] = accent;
    c[ImGuiCol_Button] = ImVec4(0.13f, 0.16f, 0.20f, 1.00f);
    c[ImGuiCol_ButtonHovered] = ImVec4(0.19f, 0.24f, 0.31f, 1.00f);
    c[ImGuiCol_ButtonActive] = ImVec4(0.23f, 0.30f, 0.39f, 1.00f);
    c[ImGuiCol_Header] = ImVec4(0.16f, 0.21f, 0.27f, 0.85f);
    c[ImGuiCol_HeaderHovered] = ImVec4(0.21f, 0.28f, 0.36f, 1.00f);
    c[ImGuiCol_HeaderActive] = ImVec4(0.25f, 0.33f, 0.42f, 1.00f);
    c[ImGuiCol_Separator] = ImVec4(0.35f, 0.42f, 0.51f, 0.35f);
    c[ImGuiCol_SeparatorHovered] = ImVec4(0.50f, 0.70f, 0.90f, 0.60f);
    c[ImGuiCol_SeparatorActive] = accent;
    c[ImGuiCol_ResizeGrip] = ImVec4(0.45f, 0.62f, 0.82f, 0.18f);
    c[ImGuiCol_ResizeGripHovered] = ImVec4(0.50f, 0.72f, 0.95f, 0.55f);
    c[ImGuiCol_ResizeGripActive] = ImVec4(0.55f, 0.78f, 1.00f, 0.85f);
    c[ImGuiCol_Tab] = ImVec4(0.09f, 0.11f, 0.14f, 1.00f);
    c[ImGuiCol_TabHovered] = ImVec4(0.30f, 0.42f, 0.55f, 1.00f);
    c[ImGuiCol_TabSelected] = ImVec4(0.14f, 0.18f, 0.23f, 1.00f);
    c[ImGuiCol_TabSelectedOverline] = accent;
    c[ImGuiCol_TabDimmed] = ImVec4(0.08f, 0.10f, 0.12f, 1.00f);
    c[ImGuiCol_TabDimmedSelected] = ImVec4(0.12f, 0.15f, 0.19f, 1.00f);
    c[ImGuiCol_TabDimmedSelectedOverline] = ImVec4(0.40f, 0.56f, 0.72f, 1.00f);
    c[ImGuiCol_PlotLines] = ImVec4(0.55f, 0.76f, 0.96f, 1.00f);
    c[ImGuiCol_PlotLinesHovered] = ImVec4(0.75f, 0.85f, 1.00f, 1.00f);
    c[ImGuiCol_PlotHistogram] = ImVec4(0.65f, 0.80f, 0.95f, 1.00f);
    c[ImGuiCol_PlotHistogramHovered] = ImVec4(0.80f, 0.90f, 1.00f, 1.00f);
    c[ImGuiCol_TableHeaderBg] = ImVec4(0.10f, 0.12f, 0.16f, 1.00f);
    c[ImGuiCol_TableBorderStrong] = ImVec4(0.24f, 0.30f, 0.38f, 1.00f);
    c[ImGuiCol_TableBorderLight] = ImVec4(0.18f, 0.22f, 0.28f, 1.00f);
    c[ImGuiCol_TableRowBg] = ImVec4(0.00f, 0.00f, 0.00f, 0.00f);
    c[ImGuiCol_TableRowBgAlt] = ImVec4(1.00f, 1.00f, 1.00f, 0.025f);
    c[ImGuiCol_TextSelectedBg] = ImVec4(0.35f, 0.55f, 0.78f, 0.45f);
    c[ImGuiCol_DragDropTarget] = accent;
    c[ImGuiCol_DragDropTargetBg] = ImVec4(0.35f, 0.55f, 0.78f, 0.20f);
    c[ImGuiCol_NavCursor] = accent;
    c[ImGuiCol_NavWindowingHighlight] = ImVec4(1.00f, 1.00f, 1.00f, 0.70f);
    c[ImGuiCol_NavWindowingDimBg] = ImVec4(0.20f, 0.20f, 0.20f, 0.20f);
    c[ImGuiCol_ModalWindowDimBg] = ImVec4(0.02f, 0.03f, 0.04f, 0.60f);

    g_colors = ThemeColors{
        accent,
        ImVec4(0.04f, 0.06f, 0.09f, 1.0f),
        ImVec4(0.42f, 0.83f, 0.58f, 1.0f),
        ImVec4(1.00f, 0.72f, 0.30f, 1.0f),
        ImVec4(1.00f, 0.42f, 0.45f, 1.0f),
    };
}

// 亮色主题：冷灰白底，强调色加深以保证对比度。
void apply_light_palette(ImGuiStyle& style) {
    ImVec4* c = style.Colors;
    const ImVec4 accent(0.13f, 0.42f, 0.70f, 1.0f);
    c[ImGuiCol_Text] = ImVec4(0.11f, 0.13f, 0.17f, 1.00f);
    c[ImGuiCol_TextDisabled] = ImVec4(0.45f, 0.49f, 0.55f, 1.00f);
    c[ImGuiCol_WindowBg] = ImVec4(0.945f, 0.957f, 0.973f, 0.98f);
    c[ImGuiCol_ChildBg] = ImVec4(0.972f, 0.979f, 0.988f, 0.92f);
    c[ImGuiCol_PopupBg] = ImVec4(1.00f, 1.00f, 1.00f, 0.98f);
    c[ImGuiCol_Border] = ImVec4(0.70f, 0.75f, 0.81f, 0.80f);
    c[ImGuiCol_BorderShadow] = ImVec4(0.00f, 0.00f, 0.00f, 0.00f);
    c[ImGuiCol_FrameBg] = ImVec4(0.885f, 0.902f, 0.925f, 1.00f);
    c[ImGuiCol_FrameBgHovered] = ImVec4(0.835f, 0.862f, 0.895f, 1.00f);
    c[ImGuiCol_FrameBgActive] = ImVec4(0.780f, 0.820f, 0.870f, 1.00f);
    c[ImGuiCol_TitleBg] = ImVec4(0.900f, 0.917f, 0.940f, 1.00f);
    c[ImGuiCol_TitleBgActive] = ImVec4(0.955f, 0.965f, 0.978f, 1.00f);
    c[ImGuiCol_TitleBgCollapsed] = ImVec4(0.900f, 0.917f, 0.940f, 0.80f);
    c[ImGuiCol_MenuBarBg] = ImVec4(0.955f, 0.965f, 0.978f, 1.00f);
    c[ImGuiCol_ScrollbarBg] = ImVec4(0.85f, 0.87f, 0.90f, 0.50f);
    c[ImGuiCol_ScrollbarGrab] = ImVec4(0.68f, 0.72f, 0.78f, 1.00f);
    c[ImGuiCol_ScrollbarGrabHovered] = ImVec4(0.60f, 0.65f, 0.72f, 1.00f);
    c[ImGuiCol_ScrollbarGrabActive] = ImVec4(0.50f, 0.56f, 0.64f, 1.00f);
    c[ImGuiCol_CheckMark] = accent;
    c[ImGuiCol_SliderGrab] = ImVec4(0.30f, 0.56f, 0.80f, 1.00f);
    c[ImGuiCol_SliderGrabActive] = ImVec4(0.13f, 0.46f, 0.76f, 1.00f);
    c[ImGuiCol_Button] = ImVec4(0.88f, 0.90f, 0.93f, 1.00f);
    c[ImGuiCol_ButtonHovered] = ImVec4(0.82f, 0.87f, 0.93f, 1.00f);
    c[ImGuiCol_ButtonActive] = ImVec4(0.76f, 0.83f, 0.91f, 1.00f);
    c[ImGuiCol_Header] = ImVec4(0.80f, 0.86f, 0.93f, 1.00f);
    c[ImGuiCol_HeaderHovered] = ImVec4(0.74f, 0.82f, 0.91f, 1.00f);
    c[ImGuiCol_HeaderActive] = ImVec4(0.68f, 0.78f, 0.89f, 1.00f);
    c[ImGuiCol_Separator] = ImVec4(0.55f, 0.60f, 0.67f, 0.45f);
    c[ImGuiCol_SeparatorHovered] = ImVec4(0.16f, 0.45f, 0.72f, 0.60f);
    c[ImGuiCol_SeparatorActive] = accent;
    c[ImGuiCol_ResizeGrip] = ImVec4(0.16f, 0.45f, 0.72f, 0.18f);
    c[ImGuiCol_ResizeGripHovered] = ImVec4(0.16f, 0.45f, 0.72f, 0.55f);
    c[ImGuiCol_ResizeGripActive] = ImVec4(0.13f, 0.42f, 0.70f, 0.85f);
    c[ImGuiCol_Tab] = ImVec4(0.90f, 0.915f, 0.94f, 1.00f);
    c[ImGuiCol_TabHovered] = ImVec4(0.84f, 0.88f, 0.93f, 1.00f);
    c[ImGuiCol_TabSelected] = ImVec4(0.972f, 0.981f, 0.992f, 1.00f);
    c[ImGuiCol_TabSelectedOverline] = accent;
    c[ImGuiCol_TabDimmed] = ImVec4(0.88f, 0.90f, 0.93f, 1.00f);
    c[ImGuiCol_TabDimmedSelected] = ImVec4(0.94f, 0.95f, 0.965f, 1.00f);
    c[ImGuiCol_TabDimmedSelectedOverline] = ImVec4(0.55f, 0.68f, 0.82f, 1.00f);
    c[ImGuiCol_PlotLines] = ImVec4(0.16f, 0.45f, 0.72f, 1.00f);
    c[ImGuiCol_PlotLinesHovered] = ImVec4(0.10f, 0.35f, 0.60f, 1.00f);
    c[ImGuiCol_PlotHistogram] = ImVec4(0.20f, 0.50f, 0.76f, 1.00f);
    c[ImGuiCol_PlotHistogramHovered] = ImVec4(0.13f, 0.42f, 0.70f, 1.00f);
    c[ImGuiCol_TableHeaderBg] = ImVec4(0.89f, 0.91f, 0.94f, 1.00f);
    c[ImGuiCol_TableBorderStrong] = ImVec4(0.70f, 0.75f, 0.81f, 1.00f);
    c[ImGuiCol_TableBorderLight] = ImVec4(0.82f, 0.85f, 0.89f, 1.00f);
    c[ImGuiCol_TableRowBg] = ImVec4(0.00f, 0.00f, 0.00f, 0.00f);
    c[ImGuiCol_TableRowBgAlt] = ImVec4(0.00f, 0.00f, 0.00f, 0.03f);
    c[ImGuiCol_TextSelectedBg] = ImVec4(0.13f, 0.42f, 0.70f, 0.25f);
    c[ImGuiCol_DragDropTarget] = accent;
    c[ImGuiCol_DragDropTargetBg] = ImVec4(0.13f, 0.42f, 0.70f, 0.15f);
    c[ImGuiCol_NavCursor] = accent;
    c[ImGuiCol_NavWindowingHighlight] = ImVec4(0.00f, 0.00f, 0.00f, 0.60f);
    c[ImGuiCol_NavWindowingDimBg] = ImVec4(0.60f, 0.62f, 0.66f, 0.25f);
    c[ImGuiCol_ModalWindowDimBg] = ImVec4(0.20f, 0.22f, 0.26f, 0.35f);

    g_colors = ThemeColors{
        accent,
        ImVec4(1.00f, 1.00f, 1.00f, 1.0f),
        ImVec4(0.16f, 0.55f, 0.32f, 1.0f),
        ImVec4(0.78f, 0.45f, 0.05f, 1.0f),
        ImVec4(0.78f, 0.18f, 0.22f, 1.0f),
    };
}

}  // namespace

void pmxtheme::apply_theme(const std::string& name) {
    ImGuiStyle& style = ImGui::GetStyle();
    // 先回到默认尺寸再统一缩放：主题切换或 DPI 变化后重复调用结果一致，不会叠加。
    style = ImGuiStyle();
    const bool light = name == "light";
    if (light) {
        ImGui::StyleColorsLight();
        apply_light_palette(style);
    } else {
        ImGui::StyleColorsDark();
        apply_dark_palette(style);
    }

    const float s = pmxui::ui_scale();
    style.ScaleAllSizes(s);
    style.FontScaleDpi = s;  // 1.92 动态字体图集会按缩放后的字号重新光栅化，不会模糊

    style.WindowRounding = 9.0f * s;
    style.ChildRounding = 7.0f * s;
    style.FrameRounding = 5.0f * s;
    style.GrabRounding = 5.0f * s;
    style.PopupRounding = 7.0f * s;
    style.ScrollbarRounding = 7.0f * s;
    style.TabRounding = 5.0f * s;
    style.WindowBorderSize = 1.0f * s;
    style.ChildBorderSize = 1.0f * s;
    style.PopupBorderSize = 1.0f * s;
    style.TabBarBorderSize = 1.0f * s;
    style.WindowPadding = ImVec2(12.0f * s, 12.0f * s);
    style.FramePadding = ImVec2(9.0f * s, 5.0f * s);
    style.CellPadding = ImVec2(6.0f * s, 3.0f * s);
    style.ItemSpacing = ImVec2(8.0f * s, 7.0f * s);
    style.ItemInnerSpacing = ImVec2(6.0f * s, 4.0f * s);
    style.IndentSpacing = 18.0f * s;
    style.ScrollbarSize = 12.0f * s;
    style.GrabMinSize = 10.0f * s;
    style.WindowTitleAlign = ImVec2(0.0f, 0.5f);
    style.WindowMenuButtonPosition = ImGuiDir_None;
    style.ButtonTextAlign = ImVec2(0.5f, 0.5f);
    style.DisabledAlpha = 0.45f;
}

const ImVec4& pmxtheme::accent() { return g_colors.accent; }
const ImVec4& pmxtheme::accent_text() { return g_colors.accent_text; }
const ImVec4& pmxtheme::success() { return g_colors.success; }
const ImVec4& pmxtheme::warning() { return g_colors.warning; }
const ImVec4& pmxtheme::danger() { return g_colors.danger; }

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
