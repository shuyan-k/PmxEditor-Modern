// ImGui 主题与偏好持久化：亮/暗配色、settings.ini 读写。
#pragma once

#include <string>

struct Viewer;

namespace pmxtheme {

// "light" 使用亮色主题，其余值统一按深色处理。
void apply_theme(const std::string& name);

// Windows: %APPDATA%/PmxStudioCpp/settings.ini；取不到 APPDATA 时退回当前目录。
std::string settings_path();

// 读取 key=value 文本；文件不存在时返回 false 且不修改 err。
bool load_settings(Viewer& v, std::string* err);

// 尽力保存，内部捕获异常，失败时静默返回。
void save_settings(const Viewer& v);

}  // namespace pmxtheme
