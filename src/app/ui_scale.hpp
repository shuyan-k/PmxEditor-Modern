// UI 缩放：4K / 高 DPI 下把字体、控件尺寸与固定像素宽度一起放大。
// ImGui 的坐标单位是“屏幕坐标”，Windows 上即物理像素（framebuffer 与窗口等大），
// 因此需要显式按 DPI 缩放；macOS 的 framebuffer 已是 2x，缩放因子会自动算成 1。
#pragma once

namespace pmxui {

inline float& ui_scale_ref() {
    static float value = 1.0f;
    return value;
}

// 启动时与窗口跨显示器移动时更新。
inline void set_ui_scale(float scale) {
    ui_scale_ref() = scale > 0.0f ? scale : 1.0f;
}

inline float ui_scale() { return ui_scale_ref(); }

// 把按 100% DPI 设计的像素值换算成当前界面单位。
inline float scale(float value) { return value * ui_scale_ref(); }

}  // namespace pmxui
