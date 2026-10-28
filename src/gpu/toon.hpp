// 卡通着色（Toon）管线：MMD 风格的网格/描边着色器源码与共用 toon 渐变贴图。
// 单独成模块，渲染器与外部工具共用同一份 GLSL，避免着色器文本重复维护。
#pragma once

namespace pmx {
namespace toon {

// 网格顶点着色器：顶点位置/法线来自计算着色器写出的 SSBO（binding 3/4），
// UV 仍从输入顶点缓冲（binding 2，每顶点 8 个 vec4，第 2 个是 UV）读取。
inline const char* const vertex_source = R"(#version 460 core
layout(std430, binding = 2) readonly buffer VertIn { vec4 verts[]; };
layout(std430, binding = 3) readonly buffer PosOut { vec4 outPos[]; };
layout(std430, binding = 4) readonly buffer NrmOut { vec4 outNrm[]; };
uniform mat4 uMVP;
uniform float uExpand;
out vec3 vN;
out vec2 vUV;
out vec3 vWorld;
void main() {
    uint i = uint(gl_VertexID);
    vec3 p = outPos[i].xyz;
    vec3 n = outNrm[i].xyz;
    vN = n;
    vUV = verts[i * 8u + 2u].xy;
    vWorld = p + n * uExpand;
    gl_Position = uMVP * vec4(vWorld, 1.0);
}
)";

// 网格片元着色器：Toon 光照（ramp 贴图）+ 球面贴图 + 边缘光。
inline const char* const fragment_source = R"(#version 460 core
in vec3 vN;
in vec2 vUV;
in vec3 vWorld;
out vec4 fragColor;
uniform sampler2D uTex;
uniform sampler2D uSphereTex;
uniform sampler2D uToonTex;
uniform int uUseTex;
uniform int uUseSphere;
uniform int uSphereMode;
uniform int uUseToonTex;
uniform vec4 uDiffuse;
uniform vec3 uAmbient;
uniform vec3 uSpecular;
uniform float uSpecCoef;
uniform float uToon;
uniform float uRim;
uniform vec3 uLightDir;
uniform vec3 uEye;
uniform mat4 uView;
void main() {
    vec4 tex = uUseTex == 1 ? texture(uTex, vUV) : vec4(1.0);
    if (tex.a < 0.02) discard;
    vec4 base = vec4(tex.rgb * uDiffuse.rgb, tex.a * uDiffuse.a);
    vec3 n = normalize(vN);
    if (!gl_FrontFacing) n = -n;
    vec3 light = normalize(uLightDir);
    float ndl = dot(n, light);
    float lambert = 0.54 + 0.16 * max(ndl, 0.0);
    // Toon 光照：优先采样 ramp 贴图（内置 toon01..10 或材质自带 toon），
    // 缺失时退回解析式两段阈值。MMD 的 toon 贴图是按 N·L(0..1) 排布的
    // 竖直渐变，直接用它做 v 坐标；若再映射到 [-1,1] 会把明暗分界推到背面，
    // 受光面几乎全亮、失去卡通分层。
    float shade;
    if (uUseToonTex == 1) {
        shade = mix(lambert, texture(uToonTex, vec2(0.5, clamp(ndl, 0.0, 1.0))).r, uToon);
    } else {
        float toon = 0.58 + 0.12 * smoothstep(0.20, 0.80, max(ndl, 0.0));
        shade = mix(lambert, toon, uToon);
    }
    vec3 col = base.rgb * shade + uAmbient * base.rgb * 0.06;
    float spec = pow(max(ndl, 0.0), 14.0) * uSpecCoef;
    col += uSpecular * spec;
    // 球面贴图按相机空间法线的 XY 采样（MMD 约定），转动视角时高光会滑动。
    if (uUseSphere == 1) {
        vec3 nv = normalize(mat3(uView) * n);
        vec2 suv = nv.xy * 0.5 + 0.5;
        vec4 sp = texture(uSphereTex, suv);
        if (uSphereMode == 1) col = col * (sp.rgb * 1.6);
        else if (uSphereMode == 2) col = col + sp.rgb * sp.a;
        else if (uSphereMode == 3) col = mix(col, sp.rgb, sp.a);
    }
    // 边缘光：贴着轮廓的位置补一点本体色，增强立体感又不破坏卡通分层。
    vec3 view_dir = normalize(uEye - vWorld);
    float rim = smoothstep(0.6, 1.0, 1.0 - max(dot(n, view_dir), 0.0));
    col += base.rgb * (uRim * rim);
    fragColor = vec4(clamp(col, 0.0, 1.0), base.a);
}
)";

// 描边顶点着色器：视空间沿法线外扩，偏移量乘深度，投影后屏幕宽度恒定。
inline const char* const outline_vertex_source = R"(#version 460 core
layout(std430, binding = 2) readonly buffer VertIn { vec4 verts[]; };
layout(std430, binding = 3) readonly buffer PosOut { vec4 outPos[]; };
layout(std430, binding = 4) readonly buffer NrmOut { vec4 outNrm[]; };
uniform mat4 uView;
uniform mat4 uProj;
uniform float uWidth;   // 描边半宽（NDC），屏幕像素宽度恒定
out vec2 vUV;
void main() {
    uint i = uint(gl_VertexID);
    vec3 p = outPos[i].xyz;
    vec3 n = outNrm[i].xyz;
    vUV = verts[i * 8u + 2u].xy;
    vec4 vp = uView * vec4(p, 1.0);
    // 视空间沿法线外扩，偏移量乘深度：投影后描边在屏幕上宽度恒定，
    // 相机拉远不会消失，拉近也不会变成粗黑边。
    float k = uWidth * (-vp.z) / uProj[1][1];
    vp.xyz += (mat3(uView) * n) * k;
    gl_Position = uProj * vp;
}
)";

inline const char* const outline_fragment_source = R"(#version 460 core
in vec2 vUV;
out vec4 fragColor;
uniform sampler2D uTex;
uniform int uUseTex;
uniform vec4 uOutlineColor;
void main() {
    // 与网格同一套 alpha 裁剪：否则蕾丝/纱这类贴图镂空的材质，外扩壳会
    // 填满被网格丢弃的透明像素，整片变成描边色（红褐色）。
    if (uUseTex == 1 && texture(uTex, vUV).a < 0.02) discard;
    fragColor = uOutlineColor;
}
)";

// ---- 共用 toon 渐变（MMD 内置 toon01.bmp 的等价物）
// 10 档竖直渐变，采样时 v 坐标即 N·L(0..1)：0 为暗部，1 为亮部。
// 编号越小明暗分界越硬（接近 MMD 默认的两段卡通），越大过渡越柔和。
// 渲染器据此生成 toon_ramps_ 贴图，着色器与渐变曲线只此一处。
inline constexpr int toon_ramp_count = 10;
inline constexpr int toon_ramp_height = 64;

// 返回第 index 档在 N·L = v 处的亮度（0..1）。
inline float toon_ramp_value(int index, float v) {
    const int i = index < 0 ? 0 : (index >= toon_ramp_count ? toon_ramp_count - 1 : index);
    const float step = 9.0f - i * 0.55f;    // 越大越硬
    const float edge = 0.40f + i * 0.015f;  // 明暗分界
    float t = (v - edge) * step + 0.5f;
    t = t < 0.0f ? 0.0f : (t > 1.0f ? 1.0f : t);
    return 0.42f + 0.58f * t;
}

}  // namespace toon
}  // namespace pmx
