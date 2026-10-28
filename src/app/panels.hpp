// 检查器面板入口（每个面板一个 .cpp，避免 main.cpp 继续膨胀）。
#pragma once

struct Viewer;

void panel_info(Viewer& v);
void panel_bone(Viewer& v);
void panel_frame(Viewer& v);
void panel_vertex(Viewer& v);
void panel_material(Viewer& v);
void panel_face(Viewer& v);
void panel_morph(Viewer& v);
void panel_physics(Viewer& v);
void panel_soft(Viewer& v);
void panel_settings(Viewer& v);
