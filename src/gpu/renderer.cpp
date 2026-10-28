#include "gpu/renderer.hpp"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iterator>
#include <string>
#include <unordered_set>

#include "core/fs.hpp"
#include "core/skinning.hpp"
#include "physics/physics.hpp"

#define STB_IMAGE_IMPLEMENTATION
#include <stb_image.h>

namespace pmx {
namespace {

constexpr int kFloatsPerVertex = 32;  // 8 vec4

// 刚体按组着色，与 Python 版 theme.py 的 GROUP_COLORS 完全一致。
const Vec3 kGroupColors[16] = {
    {0.937f, 0.420f, 0.420f}, {0.941f, 0.702f, 0.357f}, {0.910f, 0.831f, 0.353f},
    {0.369f, 0.788f, 0.541f}, {0.220f, 0.839f, 0.769f}, {0.310f, 0.616f, 1.000f},
    {0.561f, 0.486f, 0.941f}, {0.937f, 0.486f, 0.753f}, {0.753f, 0.518f, 0.341f},
    {0.553f, 0.608f, 0.710f}, {0.439f, 0.784f, 0.937f}, {0.651f, 0.788f, 0.369f},
    {0.898f, 0.561f, 0.353f}, {0.714f, 0.647f, 0.910f}, {0.498f, 0.659f, 0.627f},
    {0.788f, 0.788f, 0.788f},
};
constexpr GLuint kBindingBones = 0;
constexpr GLuint kBindingRest = 1;
constexpr GLuint kBindingVerts = 2;
constexpr GLuint kBindingPos = 3;
constexpr GLuint kBindingNrm = 4;
constexpr GLuint kBindingInstances = 5;

// 关闭物理后端时（-DPMX_ENABLE_PHYSICS=OFF）这些调用退化为空实现。
#ifdef PMX_ENABLE_PHYSICS
inline bool query_body(const Physics* p, int i, Vec3& pos, Quat& q) {
    return p && p->body_world(i, pos, q);
}
inline Mat4 query_bone_offset(const Physics* p, int i) {
    return p ? p->bone_offset(i) : identity4();
}
#else
inline bool query_body(const Physics*, int, Vec3&, Quat&) { return false; }
inline Mat4 query_bone_offset(const Physics*, int) { return identity4(); }
#endif

// ---------------------------------------------------------------- GLSL
const char* kSkinCS = R"(#version 460 core
layout(local_size_x = 64) in;

layout(std430, binding = 0) readonly buffer BoneSkin { mat4 skin[]; };
layout(std430, binding = 1) readonly buffer BoneRest { vec4 rest[]; };
layout(std430, binding = 2) readonly buffer VertIn { vec4 verts[]; };
layout(std430, binding = 3) writeonly buffer PosOut { vec4 outPos[]; };
layout(std430, binding = 4) writeonly buffer NrmOut { vec4 outNrm[]; };

vec4 qmul(vec4 a, vec4 b) {
    return vec4(a.w * b.xyz + b.w * a.xyz + cross(a.xyz, b.xyz),
                a.w * b.w - dot(a.xyz, b.xyz));
}

vec3 rotate_q(vec4 q, vec3 v) {
    vec3 t = 2.0 * cross(q.xyz, v);
    return v + q.w * t + cross(q.xyz, t);
}

vec4 quat_from_mat(mat3 m) {
    // GLSL 的 m[列][行]，与常规按 (行,列) 书写的公式索引相反，差分项要交换。
    float tr = m[0][0] + m[1][1] + m[2][2];
    vec4 q;
    if (tr > 0.0) {
        float s = sqrt(tr + 1.0) * 2.0;
        q.w = 0.25 * s;
        q.x = (m[1][2] - m[2][1]) / s;
        q.y = (m[2][0] - m[0][2]) / s;
        q.z = (m[0][1] - m[1][0]) / s;
    } else if (m[0][0] > m[1][1] && m[0][0] > m[2][2]) {
        float s = sqrt(1.0 + m[0][0] - m[1][1] - m[2][2]) * 2.0;
        q.w = (m[1][2] - m[2][1]) / s;
        q.x = 0.25 * s;
        q.y = (m[0][1] + m[1][0]) / s;
        q.z = (m[0][2] + m[2][0]) / s;
    } else if (m[1][1] > m[2][2]) {
        float s = sqrt(1.0 + m[1][1] - m[0][0] - m[2][2]) * 2.0;
        q.w = (m[2][0] - m[0][2]) / s;
        q.x = (m[0][1] + m[1][0]) / s;
        q.y = 0.25 * s;
        q.z = (m[1][2] + m[2][1]) / s;
    } else {
        float s = sqrt(1.0 + m[2][2] - m[0][0] - m[1][1]) * 2.0;
        q.w = (m[0][1] - m[1][0]) / s;
        q.x = (m[0][2] + m[2][0]) / s;
        q.y = (m[1][2] + m[2][1]) / s;
        q.z = 0.25 * s;
    }
    return normalize(q);
}

void main() {
    uint i = gl_GlobalInvocationID.x;
    if (i >= uint(verts.length() / 8u)) return;
    uint base = i * 8u;
    vec3 p0 = verts[base + 0].xyz;
    vec3 n0 = verts[base + 1].xyz;
    vec4 uvwt = verts[base + 2];
    ivec4 bi = ivec4(verts[base + 3]);
    vec4 w = verts[base + 4];
    vec3 sdefC = verts[base + 5].xyz;
    vec3 sdefR0 = verts[base + 6].xyz;
    vec3 sdefR1 = verts[base + 7].xyz;
    int wtype = int(uvwt.w + 0.5);

    int influence = wtype == 0 ? 1 : ((wtype == 1 || wtype == 3) ? 2 : 4);
    vec3 position = vec3(0.0);
    vec3 normal = vec3(0.0);
    bool resolved = false;

    // SDEF：中心/方向按权重混合后沿方向外推，半轴缩放还原体积。
    if (wtype == 3) {
        int b0 = bi.x;
        int b1 = bi.y;
        float w1 = clamp(w.y, 0.0, 1.0);
        float w0 = 1.0 - w1;
        vec3 c0 = (skin[b0] * vec4(sdefC, 1.0)).xyz;
        vec3 c1 = (skin[b1] * vec4(sdefC, 1.0)).xyz;
        vec3 pA = (skin[b0] * vec4(p0, 1.0)).xyz;
        vec3 pB = (skin[b1] * vec4(p0, 1.0)).xyz;
        vec3 blended = c0 * w0 + c1 * w1;
        vec3 direction = (pA - c0) * w0 + (pB - c1) * w1;
        float dir_len = length(direction);
        // PMX 里 R0/R1 存的是绝对坐标（中心 C + 半轴），需先减去 C 再取绝对值。
        vec3 r0v = abs(sdefR0 - sdefC);
        vec3 r1v = abs(sdefR1 - sdefC);
        bool has_r1 = abs(sdefR1.x) > 1e-6 || abs(sdefR1.y) > 1e-6 || abs(sdefR1.z) > 1e-6;
        vec3 axes = has_r1 ? r1v : r0v;
        float amax = max(max(axes.x, axes.y), axes.z);
        float radius = length(p0 - sdefC);
        if (dir_len > 1e-6) {
            mat3 R0 = mat3(skin[b0]);
            vec3 dl = transpose(R0) * direction;
            vec3 d_rest = p0 - sdefC;
            float len_rest = length(d_rest);
            float len_cur = length(dl);
            if (len_rest > 1e-6 && len_cur > 1e-6 && amax > 1e-6) {
                float sum_rest = 0.0;
                float sum_cur = 0.0;
                for (int k = 0; k < 3; ++k) {
                    float a = abs(axes[k]);
                    if (a < 1e-6) a = amax;
                    float tr = (d_rest[k] / len_rest) / a;
                    float tc = (dl[k] / len_cur) / a;
                    sum_rest += tr * tr;
                    sum_cur += tc * tc;
                }
                if (sum_rest > 1e-12 && sum_cur > 1e-12) {
                    radius = len_rest * sqrt(sum_rest / sum_cur);
                    radius = clamp(radius, len_rest * 0.6, len_rest * 1.4);
                }
            }
        }
        if (dir_len > 1e-6 && radius > 1e-6) {
            position = blended + direction * (radius / dir_len);
            resolved = true;
        }
    }

    // BDEF2/BDEF4：双四元数混合，避免大角度弯曲的糖纸效应。
    if (!resolved && (wtype == 1 || wtype == 2)) {
        vec4 qsum = vec4(0.0);
        vec4 dsum = vec4(0.0);
        vec4 reference = vec4(0.0, 0.0, 0.0, 1.0);
        bool has_ref = false;
        float wsum = 0.0;
        for (int k = 0; k < influence; ++k) {
            float wk = w[k];
            if (wk <= 0.0) continue;
            int b = bi[k];
            mat4 M = skin[b];
            vec4 q = quat_from_mat(mat3(M));
            // skin = W * T(-rest)，其平移列已是 t - R*rest，正是双四元数需要的平移。
            vec4 d = 0.5 * qmul(vec4(M[3].xyz, 0.0), q);
            float sgn = 1.0;
            if (!has_ref) {
                reference = q;
                has_ref = true;
            } else if (dot(q, reference) < 0.0) {
                sgn = -1.0;
            }
            qsum += q * wk * sgn;
            dsum += d * wk * sgn;
            wsum += wk;
        }
        float qlen = length(qsum);
        if (wsum > 1e-6 && qlen > 1e-6) {
            qsum /= qlen;
            dsum /= qlen;
            vec4 dconj = vec4(-qsum.xyz, qsum.w);
            vec3 translation = 2.0 * qmul(dsum, dconj).xyz;
            position = rotate_q(qsum, p0) + translation;
            resolved = true;
        }
    }

    for (int k = 0; k < influence; ++k) {
        int b = bi[k];
        if (!resolved) {
            // skin 已包含 T(-rest)，直接作用在静止坐标上。
            position += (skin[b] * vec4(p0, 1.0)).xyz * w[k];
        }
        normal += (mat3(skin[b]) * n0) * w[k];
    }

    float nlen = length(normal);
    outPos[i] = vec4(position, 1.0);
    outNrm[i] = vec4(nlen > 1e-6 ? normal / nlen : n0, 0.0);
}
)";

const char* kMeshVS = R"(#version 460 core
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

const char* kMeshFS = R"(#version 460 core
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

const char* kOutlineVS = R"(#version 460 core
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

const char* kOutlineFS = R"(#version 460 core
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

const char* kSolidVS = R"(#version 460 core
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNrm;
layout(location = 2) in vec4 aColor;
uniform mat4 uMVP;
out vec3 vN;
out vec3 vPos;
out vec4 vC;
void main() {
    vN = aNrm;
    vPos = aPos;
    vC = aColor;
    gl_Position = uMVP * vec4(aPos, 1.0);
}
)";

const char* kSolidFS = R"(#version 460 core
in vec3 vN;
in vec3 vPos;
in vec4 vC;
out vec4 fragColor;
uniform vec3 uLightDir;
uniform vec3 uEye;
void main() {
    vec3 n = normalize(vN);
    if (!gl_FrontFacing) n = -n;
    vec3 light = normalize(uLightDir);
    float ndl = max(dot(n, light), 0.0);
    float hemi = 0.5 + 0.5 * n.y;
    float shade = 0.44 + 0.36 * ndl + 0.20 * hemi;
    vec3 view = normalize(uEye - vPos);
    float rim = pow(1.0 - abs(dot(n, view)), 2.5);
    vec3 col = vC.rgb * shade + vC.rgb * rim * 0.28;
    fragColor = vec4(clamp(col, 0.0, 1.0), vC.a);
}
)";

const char* kInstVS = R"(#version 460 core
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec3 aNrm;
layout(std430, binding = 5) readonly buffer Instances { vec4 inst[]; };
uniform mat4 uMVP;
uniform int uInstanceBase;
out vec3 vN;
out vec3 vPos;
out vec4 vC;
void main() {
    // mat4 占 4 个 vec4 + 1 个颜色；分桶绘制时用 uInstanceBase 指向本组起点。
    uint base = uint(gl_InstanceID + uInstanceBase) * 5u;
    mat4 M = mat4(inst[base + 0], inst[base + 1], inst[base + 2], inst[base + 3]);
    vC = inst[base + 4];
    vec4 world = M * vec4(aPos, 1.0);
    vN = mat3(M) * aNrm;
    vPos = world.xyz;
    gl_Position = uMVP * world;
}
)";

const char* kLineVS = R"(#version 460 core
layout(location = 0) in vec3 aPos;
layout(location = 1) in vec4 aColor;
uniform mat4 uMVP;
out vec4 vC;
void main() {
    vC = aColor;
    gl_Position = uMVP * vec4(aPos, 1.0);
}
)";

const char* kLineFS = R"(#version 460 core
in vec4 vC;
out vec4 fragColor;
uniform float uAlpha;
void main() { fragColor = vec4(vC.rgb, vC.a * uAlpha); }
)";

// ---------------------------------------------------------------- 几何模板
struct TemplateMesh {
    std::vector<float> verts;   // pos3 nrm3 color4
    std::vector<std::uint32_t> idx;
};

void winding_fix(std::vector<float>& verts, std::vector<std::uint32_t>& idx) {
    for (std::size_t t = 0; t + 2 < idx.size(); t += 3) {
        const std::uint32_t a = idx[t], b = idx[t + 1], c = idx[t + 2];
        Vec3 pa{verts[a * 10 + 0], verts[a * 10 + 1], verts[a * 10 + 2]};
        Vec3 pb{verts[b * 10 + 0], verts[b * 10 + 1], verts[b * 10 + 2]};
        Vec3 pc{verts[c * 10 + 0], verts[c * 10 + 1], verts[c * 10 + 2]};
        Vec3 naive{verts[a * 10 + 3], verts[a * 10 + 4], verts[a * 10 + 5]};
        const Vec3 face = cross(pb - pa, pc - pa);
        if (length(face) < 1e-10f) {
            idx[t] = idx[t + 1] = idx[t + 2] = 0;
            continue;
        }
        if (dot(face, naive) < 0.0f) std::swap(idx[t + 1], idx[t + 2]);
    }
}

TemplateMesh make_box(float hx, float hy, float hz) {
    TemplateMesh m;
    const Vec3 n[6] = {{0, 0, 1}, {0, 0, -1}, {1, 0, 0}, {-1, 0, 0}, {0, 1, 0}, {0, -1, 0}};
    const float quad[6][12] = {
        {-hx, -hy, hz, hx, -hy, hz, hx, hy, hz, -hx, hy, hz},
        {-hx, -hy, -hz, -hx, hy, -hz, hx, hy, -hz, hx, -hy, -hz},
        {hx, -hy, -hz, hx, hy, -hz, hx, hy, hz, hx, -hy, hz},
        {-hx, -hy, -hz, -hx, -hy, hz, -hx, hy, hz, -hx, hy, -hz},
        {-hx, hy, -hz, -hx, hy, hz, hx, hy, hz, hx, hy, -hz},
        {-hx, -hy, -hz, hx, -hy, -hz, hx, -hy, hz, -hx, -hy, hz},
    };
    for (int f = 0; f < 6; ++f) {
        const auto base = static_cast<std::uint32_t>(m.verts.size() / 10);
        for (int v = 0; v < 4; ++v) {
            m.verts.push_back(quad[f][v * 3 + 0]);
            m.verts.push_back(quad[f][v * 3 + 1]);
            m.verts.push_back(quad[f][v * 3 + 2]);
            m.verts.push_back(n[f].x);
            m.verts.push_back(n[f].y);
            m.verts.push_back(n[f].z);
            m.verts.push_back(1.0f);
            m.verts.push_back(1.0f);
            m.verts.push_back(1.0f);
            m.verts.push_back(1.0f);
        }
        m.idx.insert(m.idx.end(), {base, base + 1, base + 2, base, base + 2, base + 3});
    }
    winding_fix(m.verts, m.idx);
    return m;
}

TemplateMesh make_sphere(float radius, int segments, int rings) {
    TemplateMesh m;
    for (int iy = 0; iy <= rings; ++iy) {
        const float theta = kPi * static_cast<float>(iy) / static_cast<float>(rings);
        const float y = std::cos(theta) * radius;
        const float rr = std::sin(theta) * radius;
        for (int ix = 0; ix < segments; ++ix) {
            const float phi = 2.0f * kPi * static_cast<float>(ix) / static_cast<float>(segments);
            const float px = rr * std::cos(phi);
            const float pz = rr * std::sin(phi);
            m.verts.insert(m.verts.end(), {px, y, pz,
                                           radius > 1e-9f ? px / radius : 0.0f,
                                           radius > 1e-9f ? y / radius : 1.0f,
                                           radius > 1e-9f ? pz / radius : 0.0f,
                                           1.0f, 1.0f, 1.0f, 1.0f});
        }
    }
    for (int iy = 0; iy < rings; ++iy) {
        for (int ix = 0; ix < segments; ++ix) {
            const std::uint32_t a = static_cast<std::uint32_t>(iy * segments + ix);
            const std::uint32_t b = static_cast<std::uint32_t>(iy * segments + (ix + 1) % segments);
            const std::uint32_t c = static_cast<std::uint32_t>((iy + 1) * segments + ix);
            const std::uint32_t d = static_cast<std::uint32_t>((iy + 1) * segments + (ix + 1) % segments);
            m.idx.insert(m.idx.end(), {a, c, b, b, c, d});
        }
    }
    winding_fix(m.verts, m.idx);
    return m;
}

TemplateMesh make_cylinder(float radius, float height, int segments) {
    // 单位圆柱（半径 1，高度 1，居中）：胶囊的柱段。两端由球模板封住，不封盖。
    TemplateMesh m;
    const float half = std::fabs(height) * 0.5f;
    for (int iy = 0; iy < 2; ++iy) {
        const float y = iy == 0 ? -half : half;
        for (int ix = 0; ix < segments; ++ix) {
            const float phi = 2.0f * kPi * static_cast<float>(ix) / static_cast<float>(segments);
            const float nx = std::cos(phi), nz = std::sin(phi);
            m.verts.insert(m.verts.end(), {radius * nx, y, radius * nz, nx, 0.0f, nz,
                                           1.0f, 1.0f, 1.0f, 1.0f});
        }
    }
    for (int ix = 0; ix < segments; ++ix) {
        const std::uint32_t a = static_cast<std::uint32_t>(ix);
        const std::uint32_t b = static_cast<std::uint32_t>((ix + 1) % segments);
        const std::uint32_t c = static_cast<std::uint32_t>(segments + ix);
        const std::uint32_t d = static_cast<std::uint32_t>(segments + (ix + 1) % segments);
        m.idx.insert(m.idx.end(), {a, c, b, b, c, d});
    }
    winding_fix(m.verts, m.idx);
    return m;
}

void upload_template(const TemplateMesh& src, GLuint* vao, GLuint* vbo, GLuint* ebo,
                     GLuint* index_count) {
    glGenVertexArrays(1, vao);
    glBindVertexArray(*vao);
    glGenBuffers(1, vbo);
    glBindBuffer(glc::GL_ARRAY_BUFFER, *vbo);
    glBufferData(glc::GL_ARRAY_BUFFER,
                 static_cast<GLsizeiptr>(src.verts.size() * sizeof(float)), src.verts.data(),
                 glc::GL_STATIC_DRAW);
    const GLsizei stride = 10 * sizeof(float);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 3, glc::GL_FLOAT, glc::GL_FALSE, stride, nullptr);
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1, 3, glc::GL_FLOAT, glc::GL_FALSE, stride,
                          reinterpret_cast<const void*>(3 * sizeof(float)));
    glEnableVertexAttribArray(2);
    glVertexAttribPointer(2, 4, glc::GL_FLOAT, glc::GL_FALSE, stride,
                          reinterpret_cast<const void*>(6 * sizeof(float)));
    glGenBuffers(1, ebo);
    glBindBuffer(glc::GL_ELEMENT_ARRAY_BUFFER, *ebo);
    glBufferData(glc::GL_ELEMENT_ARRAY_BUFFER,
                 static_cast<GLsizeiptr>(src.idx.size() * sizeof(std::uint32_t)), src.idx.data(),
                 glc::GL_STATIC_DRAW);
    *index_count = static_cast<GLuint>(src.idx.size());
    glBindVertexArray(0);
}

Mat4 project_view_proj(const Mat4& view, const Mat4& proj) { return mul(proj, view); }

bool project_to_screen(const Mat4& vp, Vec3 p, int width, int height, float& sx, float& sy) {
    const float x = vp.at(0, 0) * p.x + vp.at(0, 1) * p.y + vp.at(0, 2) * p.z + vp.at(0, 3);
    const float y = vp.at(1, 0) * p.x + vp.at(1, 1) * p.y + vp.at(1, 2) * p.z + vp.at(1, 3);
    const float w = vp.at(3, 0) * p.x + vp.at(3, 1) * p.y + vp.at(3, 2) * p.z + vp.at(3, 3);
    if (w <= 1e-6f) return false;
    sx = (x / w * 0.5f + 0.5f) * static_cast<float>(width);
    sy = (1.0f - (y / w * 0.5f + 0.5f)) * static_cast<float>(height);
    return true;
}

float point_segment_distance(float px, float py, float ax, float ay, float bx, float by) {
    const float dx = bx - ax, dy = by - ay;
    const float d2 = dx * dx + dy * dy;
    if (d2 <= 1e-9f) return std::hypot(px - ax, py - ay);
    float t = ((px - ax) * dx + (py - ay) * dy) / d2;
    t = clampf(t, 0.0f, 1.0f);
    return std::hypot(px - (ax + dx * t), py - (ay + dy * t));
}

}  // namespace

SceneRenderer::~SceneRenderer() {
    release_model();
    // 模板/网格/实例缓冲只在 init 时创建一次，随渲染器一起销毁。
    auto drop = [](OverlayMesh& m) {
        if (m.vbo) glDeleteBuffers(1, &m.vbo);
        if (m.ebo) glDeleteBuffers(1, &m.ebo);
        if (m.vao) glDeleteVertexArrays(1, &m.vao);
        m = OverlayMesh{};
    };
    drop(rigid_box_);
    drop(rigid_sphere_);
    drop(rigid_cylinder_);
    drop(joint_sphere_);
    drop(bone_mesh_);
    if (overlay_instance_ssbo_) {
        glDeleteBuffers(1, &overlay_instance_ssbo_);
        overlay_instance_ssbo_ = 0;
    }
    if (grid_vbo_) {
        glDeleteBuffers(1, &grid_vbo_);
        grid_vbo_ = 0;
    }
    if (grid_vao_) {
        glDeleteVertexArrays(1, &grid_vao_);
        grid_vao_ = 0;
    }
    for (GLuint& ramp : toon_ramps_) {
        if (ramp) glDeleteTextures(1, &ramp);
        ramp = 0;
    }
}

bool SceneRenderer::init(std::string* error) {
    std::string err;
    if (!skin_program_.build_compute(kSkinCS, &err)) {
        if (error) *error = err;
        return false;
    }
    if (!mesh_program_.build(kMeshVS, kMeshFS, &err) ||
        !outline_program_.build(kOutlineVS, kOutlineFS, &err) ||
        !solid_program_.build(kSolidVS, kSolidFS, &err) ||
        !inst_program_.build(kInstVS, kSolidFS, &err) ||
        !line_program_.build(kLineVS, kLineFS, &err)) {
        if (error) *error = err;
        return false;
    }
    glGenBuffers(1, &overlay_instance_ssbo_);
    gpu_check_enabled_ = std::getenv("PMX_GPU_CHECK") != nullptr;
    build_templates();
    build_toon_ramps();
    build_grid();
    ready_ = true;
    return true;
}

void SceneRenderer::build_templates() {
    const TemplateMesh box = make_box(1.0f, 1.0f, 1.0f);
    upload_template(box, &rigid_box_.vao, &rigid_box_.vbo, &rigid_box_.ebo, &rigid_box_.index_count);
    const TemplateMesh sphere = make_sphere(1.0f, 18, 12);
    upload_template(sphere, &rigid_sphere_.vao, &rigid_sphere_.vbo, &rigid_sphere_.ebo,
                    &rigid_sphere_.index_count);
    upload_template(sphere, &joint_sphere_.vao, &joint_sphere_.vbo, &joint_sphere_.ebo,
                    &joint_sphere_.index_count);
    const TemplateMesh capsule = make_cylinder(1.0f, 1.0f, 18);
    upload_template(capsule, &rigid_cylinder_.vao, &rigid_cylinder_.vbo, &rigid_cylinder_.ebo,
                    &rigid_cylinder_.index_count);

    glGenVertexArrays(1, &bone_mesh_.vao);
    glBindVertexArray(bone_mesh_.vao);
    glGenBuffers(1, &bone_mesh_.vbo);
    glBindBuffer(glc::GL_ARRAY_BUFFER, bone_mesh_.vbo);
    glBufferData(glc::GL_ARRAY_BUFFER, 0, nullptr, glc::GL_STREAM_DRAW);
    const GLsizei stride = 10 * sizeof(float);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 3, glc::GL_FLOAT, glc::GL_FALSE, stride, nullptr);
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1, 3, glc::GL_FLOAT, glc::GL_FALSE, stride,
                          reinterpret_cast<const void*>(3 * sizeof(float)));
    glEnableVertexAttribArray(2);
    glVertexAttribPointer(2, 4, glc::GL_FLOAT, glc::GL_FALSE, stride,
                          reinterpret_cast<const void*>(6 * sizeof(float)));
    glBindVertexArray(0);
}

void SceneRenderer::build_grid() {
    std::vector<float> verts;
    const float extent = 40.0f;
    const float step = 1.0f;
    const Vec4 minor(0.30f, 0.31f, 0.34f, 1.0f);
    const Vec4 major(0.42f, 0.43f, 0.47f, 1.0f);
    auto push = [&verts](Vec3 p, Vec4 c) {
        verts.insert(verts.end(), {p.x, p.y, p.z, c.x, c.y, c.z, c.w});
    };
    for (float x = -extent; x <= extent + 1e-4f; x += step) {
        const bool axis = std::fabs(x) < 1e-4f;
        const Vec4 c = (std::fabs(std::fmod(x, 5.0f)) < 1e-4f) ? major : minor;
        push({x, 0.0f, -extent}, axis ? Vec4(0.75f, 0.45f, 0.45f, 1.0f) : c);
        push({x, 0.0f, extent}, axis ? Vec4(0.75f, 0.45f, 0.45f, 1.0f) : c);
    }
    for (float z = -extent; z <= extent + 1e-4f; z += step) {
        const bool axis = std::fabs(z) < 1e-4f;
        const Vec4 c = (std::fabs(std::fmod(z, 5.0f)) < 1e-4f) ? major : minor;
        push({-extent, 0.0f, z}, axis ? Vec4(0.45f, 0.55f, 0.80f, 1.0f) : c);
        push({extent, 0.0f, z}, axis ? Vec4(0.45f, 0.55f, 0.80f, 1.0f) : c);
    }
    grid_vertex_count_ = static_cast<GLuint>(verts.size() / 7);
    glGenVertexArrays(1, &grid_vao_);
    glBindVertexArray(grid_vao_);
    glGenBuffers(1, &grid_vbo_);
    glBindBuffer(glc::GL_ARRAY_BUFFER, grid_vbo_);
    glBufferData(glc::GL_ARRAY_BUFFER, static_cast<GLsizeiptr>(verts.size() * sizeof(float)),
                 verts.data(), glc::GL_STATIC_DRAW);
    const GLsizei stride = 7 * sizeof(float);
    glEnableVertexAttribArray(0);
    glVertexAttribPointer(0, 3, glc::GL_FLOAT, glc::GL_FALSE, stride, nullptr);
    glEnableVertexAttribArray(1);
    glVertexAttribPointer(1, 4, glc::GL_FLOAT, glc::GL_FALSE, stride,
                          reinterpret_cast<const void*>(3 * sizeof(float)));
    glBindVertexArray(0);
}

void SceneRenderer::build_toon_ramps() {
    // 内置 toon01..10 的程序化近似：竖直灰度渐变，底部暗、顶部亮。
    // 低编号接近 MMD 的硬边两色，编号越大过渡越柔和。
    const int height = 64;
    std::vector<unsigned char> pixels(static_cast<std::size_t>(height) * 4);
    for (int i = 0; i < 10; ++i) {
        const float step = 9.0f - i * 0.55f;           // 越大越硬
        const float edge = 0.40f + i * 0.015f;         // 明暗分界
        for (int y = 0; y < height; ++y) {
            const float v = static_cast<float>(y) / static_cast<float>(height - 1);
            const float t = clampf((v - edge) * step + 0.5f, 0.0f, 1.0f);
            const auto c = static_cast<unsigned char>((0.42f + 0.58f * t) * 255.0f + 0.5f);
            const std::size_t o = static_cast<std::size_t>(y) * 4;
            pixels[o + 0] = c;
            pixels[o + 1] = c;
            pixels[o + 2] = c;
            pixels[o + 3] = 255;
        }
        GLuint tex = 0;
        glGenTextures(1, &tex);
        glBindTexture(glc::GL_TEXTURE_2D, tex);
        glPixelStorei(glc::GL_UNPACK_ALIGNMENT, 1);
        glTexImage2D(glc::GL_TEXTURE_2D, 0, glc::GL_RGBA8, 1, height, 0, glc::GL_RGBA,
                     glc::GL_UNSIGNED_BYTE, pixels.data());
        glTexParameteri(glc::GL_TEXTURE_2D, glc::GL_TEXTURE_MIN_FILTER,
                        static_cast<GLint>(glc::GL_LINEAR));
        glTexParameteri(glc::GL_TEXTURE_2D, glc::GL_TEXTURE_MAG_FILTER,
                        static_cast<GLint>(glc::GL_LINEAR));
        glTexParameteri(glc::GL_TEXTURE_2D, glc::GL_TEXTURE_WRAP_S,
                        static_cast<GLint>(glc::GL_CLAMP_TO_EDGE));
        glTexParameteri(glc::GL_TEXTURE_2D, glc::GL_TEXTURE_WRAP_T,
                        static_cast<GLint>(glc::GL_CLAMP_TO_EDGE));
        toon_ramps_[i] = tex;
    }
    glPixelStorei(glc::GL_UNPACK_ALIGNMENT, 4);
    glBindTexture(glc::GL_TEXTURE_2D, 0);
}

void SceneRenderer::release_model() {
    GLuint buffers[] = {model_.vbo, model_.ebo, model_.bone_ssbo, model_.rest_ssbo,
                        model_.out_pos_ssbo, model_.out_nrm_ssbo};
    for (GLuint b : buffers)
        if (b) glDeleteBuffers(1, &b);
    if (model_.vao) glDeleteVertexArrays(1, &model_.vao);
    model_ = GpuModel{};
    for (auto& [name, tex] : textures_)
        if (tex.id) glDeleteTextures(1, &tex.id);
    textures_.clear();
}

bool SceneRenderer::upload_model(const Model& model, std::string* error) {
    if (!ready_) {
        if (error) *error = "渲染器尚未初始化";
        return false;
    }
    release_model();

    const int nv = static_cast<int>(model.vertices.size());
    if (nv <= 0) {
        if (error) *error = "模型没有顶点";
        return false;
    }
    std::vector<float> data(static_cast<std::size_t>(nv) * kFloatsPerVertex, 0.0f);
    for (int i = 0; i < nv; ++i) {
        const std::size_t o = static_cast<std::size_t>(i) * kFloatsPerVertex;
        const std::size_t k = static_cast<std::size_t>(i);
        data[o + 0] = model.vertices.pos[k].x;
        data[o + 1] = model.vertices.pos[k].y;
        data[o + 2] = model.vertices.pos[k].z;
        data[o + 4] = model.vertices.nrm[k].x;
        data[o + 5] = model.vertices.nrm[k].y;
        data[o + 6] = model.vertices.nrm[k].z;
        data[o + 8] = model.vertices.uv[k].x;
        data[o + 9] = model.vertices.uv[k].y;
        data[o + 10] = model.vertices.edge[k];
        data[o + 11] = static_cast<float>(model.vertices.wtype[k]);
        for (int c = 0; c < 4; ++c)
            data[o + 12 + c] = static_cast<float>(model.vertices.bones[k][static_cast<std::size_t>(c)]);
        for (int c = 0; c < 4; ++c)
            data[o + 16 + c] = model.vertices.weights[k][static_cast<std::size_t>(c)];
        const auto& sd = model.vertices.sdef[k];
        data[o + 20] = sd[0];
        data[o + 21] = sd[1];
        data[o + 22] = sd[2];
        data[o + 24] = sd[3];
        data[o + 25] = sd[4];
        data[o + 26] = sd[5];
        data[o + 28] = sd[6];
        data[o + 29] = sd[7];
        data[o + 30] = sd[8];
    }

    glGenVertexArrays(1, &model_.vao);
    glBindVertexArray(model_.vao);

    glGenBuffers(1, &model_.vbo);
    glBindBuffer(glc::GL_ARRAY_BUFFER, model_.vbo);
    glBufferData(glc::GL_ARRAY_BUFFER, static_cast<GLsizeiptr>(data.size() * sizeof(float)),
                 data.data(), glc::GL_DYNAMIC_DRAW);
    glBindBuffer(glc::GL_SHADER_STORAGE_BUFFER, model_.vbo);

    glGenBuffers(1, &model_.ebo);
    glBindBuffer(glc::GL_ELEMENT_ARRAY_BUFFER, model_.ebo);
    glBufferData(glc::GL_ELEMENT_ARRAY_BUFFER,
                 static_cast<GLsizeiptr>(model.indices.size() * sizeof(std::uint32_t)),
                 model.indices.data(), glc::GL_STATIC_DRAW);

    glBindBuffer(glc::GL_ELEMENT_ARRAY_BUFFER, model_.ebo);

    // 只绑定索引缓冲：位置/法线由 SSBO 按 gl_VertexID 取。
    glGenBuffers(1, &model_.out_pos_ssbo);
    glBindBuffer(glc::GL_SHADER_STORAGE_BUFFER, model_.out_pos_ssbo);
    glBufferData(glc::GL_SHADER_STORAGE_BUFFER,
                 static_cast<GLsizeiptr>(static_cast<std::size_t>(nv) * 4 * sizeof(float)),
                 nullptr, glc::GL_DYNAMIC_DRAW);
    glGenBuffers(1, &model_.out_nrm_ssbo);
    glBindBuffer(glc::GL_SHADER_STORAGE_BUFFER, model_.out_nrm_ssbo);
    glBufferData(glc::GL_SHADER_STORAGE_BUFFER,
                 static_cast<GLsizeiptr>(static_cast<std::size_t>(nv) * 4 * sizeof(float)),
                 nullptr, glc::GL_DYNAMIC_DRAW);

    const int nb = static_cast<int>(model.bones.size());
    glGenBuffers(1, &model_.bone_ssbo);
    glBindBuffer(glc::GL_SHADER_STORAGE_BUFFER, model_.bone_ssbo);
    glBufferData(glc::GL_SHADER_STORAGE_BUFFER,
                 static_cast<GLsizeiptr>(std::max(1, nb) * 16 * sizeof(float)), nullptr,
                 glc::GL_DYNAMIC_DRAW);
    glGenBuffers(1, &model_.rest_ssbo);
    glBindBuffer(glc::GL_SHADER_STORAGE_BUFFER, model_.rest_ssbo);
    glBufferData(glc::GL_SHADER_STORAGE_BUFFER,
                 static_cast<GLsizeiptr>(std::max(1, nb) * 4 * sizeof(float)), nullptr,
                 glc::GL_DYNAMIC_DRAW);

    glBindVertexArray(0);
    glBindBuffer(glc::GL_SHADER_STORAGE_BUFFER, 0);

    model_.vertex_count = static_cast<GLuint>(nv);
    model_.index_count = static_cast<GLuint>(model.indices.size());
    model_.bone_count = static_cast<GLuint>(nb);
    model_.ranges = material_ranges(model);
    model_.path = model.path;

    // 半透明材质排序用的面区间中心与骨骼锚点：中心取静止坐标平均值，
    // 锚点取区间首顶点权重最大的骨骼，蒙皮后中心跟着骨骼走。
    range_centers_.assign(model_.ranges.size(), Vec3{});
    range_bones_.assign(model_.ranges.size(), -1);
    for (std::size_t r = 0; r < model_.ranges.size(); ++r) {
        const MaterialRange& range = model_.ranges[r];
        if (range.count == 0 || range.start >= model.indices.size()) continue;
        Vec3 sum{};
        std::size_t n = 0;
        const std::size_t end = std::min(range.start + range.count, model.indices.size());
        for (std::size_t k = range.start; k < end; ++k) {
            const std::uint32_t vi = model.indices[k];
            if (vi >= model.vertices.size()) continue;
            sum += model.vertices.pos[vi];
            ++n;
        }
        if (n > 0) range_centers_[r] = sum * (1.0f / static_cast<float>(n));

        const std::uint32_t v0 = model.indices[range.start];
        if (v0 >= model.vertices.size()) continue;
        float best_weight = 0.0f;
        for (int c = 0; c < 4; ++c) {
            const int b = model.vertices.bones[v0][static_cast<std::size_t>(c)];
            const float w = model.vertices.weights[v0][static_cast<std::size_t>(c)];
            if (b >= 0 && w > best_weight) {
                best_weight = w;
                range_bones_[r] = b;
            }
        }
    }
    skin_cpu_.clear();

    // 骨骼静止位置只随模型结构变化，先上传一次。
    std::vector<float> rest(static_cast<std::size_t>(std::max(1, nb)) * 4, 0.0f);
    for (int i = 0; i < nb; ++i) {
        rest[static_cast<std::size_t>(i) * 4 + 0] = model.bones[static_cast<std::size_t>(i)].pos.x;
        rest[static_cast<std::size_t>(i) * 4 + 1] = model.bones[static_cast<std::size_t>(i)].pos.y;
        rest[static_cast<std::size_t>(i) * 4 + 2] = model.bones[static_cast<std::size_t>(i)].pos.z;
    }
    glBindBuffer(glc::GL_SHADER_STORAGE_BUFFER, model_.rest_ssbo);
    glBufferSubData(glc::GL_SHADER_STORAGE_BUFFER, 0,
                    static_cast<GLsizeiptr>(rest.size() * sizeof(float)), rest.data());

    skin_matrices_.assign(static_cast<std::size_t>(std::max(1, nb)) * 16, 0.0f);
    inst_data_.clear();
    textures_.clear();
    return true;
}

void SceneRenderer::update_base(const Model& model, const VertexMorphResult& morph) {
    if (model_.vbo == 0) return;
    if (morph.pos == nullptr || morph.uv == nullptr) return;
    if (morph.pos == &model.vertices.pos && morph.uv == &model.vertices.uv) return;
    const int nv = static_cast<int>(model.vertices.size());
    glBindBuffer(glc::GL_SHADER_STORAGE_BUFFER, model_.vbo);
    // 逐顶点跨越 128 字节：整体映射后只改位置(0..2)与 UV(8..9)。
    const GLsizeiptr total =
        static_cast<GLsizeiptr>(static_cast<std::size_t>(nv) * kFloatsPerVertex * sizeof(float));
    auto* base = static_cast<std::uint8_t*>(
        glMapBufferRange(glc::GL_SHADER_STORAGE_BUFFER, 0, total,
                         glc::GL_MAP_WRITE_BIT | glc::GL_MAP_UNSYNCHRONIZED_BIT));
    if (base) {
        const auto& pos = *morph.pos;
        const auto& uv = *morph.uv;
        for (int i = 0; i < nv; ++i) {
            float* o = reinterpret_cast<float*>(
                base + static_cast<std::size_t>(i) * kFloatsPerVertex * sizeof(float));
            o[0] = pos[static_cast<std::size_t>(i)].x;
            o[1] = pos[static_cast<std::size_t>(i)].y;
            o[2] = pos[static_cast<std::size_t>(i)].z;
            o[8] = uv[static_cast<std::size_t>(i)].x;
            o[9] = uv[static_cast<std::size_t>(i)].y;
        }
        glUnmapBuffer(glc::GL_SHADER_STORAGE_BUFFER);
    }
    glBindBuffer(glc::GL_SHADER_STORAGE_BUFFER, 0);
}

void SceneRenderer::validate_gpu_skin(const Model& model, Pose& pose) {
    const std::size_t nv = model.vertices.size();
    glBindBuffer(glc::GL_SHADER_STORAGE_BUFFER, model_.out_pos_ssbo);
    auto* gpu = static_cast<float*>(glMapBufferRange(
        glc::GL_SHADER_STORAGE_BUFFER, 0,
        static_cast<GLsizeiptr>(nv * 4 * sizeof(float)), glc::GL_MAP_READ_BIT));
    if (!gpu) {
        std::printf("[GPU-CHECK] 读取 outPos 失败\n");
        return;
    }
    SkinDeformer deformer(model);
    std::vector<Vec3> cpu_pos, cpu_nrm;
    deformer.deform(model.vertices.pos, model.vertices.nrm, pose.world(), cpu_pos, cpu_nrm);
    double max_diff = 0.0;
    int bad = 0;
    for (std::size_t i = 0; i < nv; ++i) {
        const Vec3 g{gpu[i * 4 + 0], gpu[i * 4 + 1], gpu[i * 4 + 2]};
        const double d = std::max({std::fabs(static_cast<double>(g.x - cpu_pos[i].x)),
                                   std::fabs(static_cast<double>(g.y - cpu_pos[i].y)),
                                   std::fabs(static_cast<double>(g.z - cpu_pos[i].z))});
        max_diff = std::max(max_diff, d);
        if (!std::isfinite(g.x) || !std::isfinite(g.y) || !std::isfinite(g.z)) ++bad;
    }
    glUnmapBuffer(glc::GL_SHADER_STORAGE_BUFFER);
    std::printf("[GPU-CHECK] 顶点 %zu，最大偏差 %.9f，非法分量顶点 %d\n", nv, max_diff, bad);
    std::fflush(stdout);
}

void SceneRenderer::upload_skin_matrices(const Model& model, Pose& pose) {
    const std::vector<Mat4>& W = pose.world();
    const std::size_t nb = std::max<std::size_t>(1, model.bones.size());
    skin_matrices_.assign(nb * 16, 0.0f);
    // 半透明排序要用同一套 skin 矩阵把静止中心变换到当前姿态。
    skin_cpu_.assign(nb, identity4());
    for (std::size_t i = 0; i < model.bones.size(); ++i) {
        // skin = W * T(-rest)：等价于世界矩阵作用于 (p - rest)。
        // SSBO 里的 mat4 是列主序，必须转置后再写。
        Mat4 skin = mul(W[i], translation(-model.bones[i].pos));
        skin_cpu_[i] = skin;
        store_column_major(skin, skin_matrices_.data() + i * 16);
    }
    glBindBuffer(glc::GL_SHADER_STORAGE_BUFFER, model_.bone_ssbo);
    glBufferSubData(glc::GL_SHADER_STORAGE_BUFFER, 0,
                    static_cast<GLsizeiptr>(skin_matrices_.size() * sizeof(float)),
                    skin_matrices_.data());
}

void SceneRenderer::dispatch_gpu_skin() {
    glBindBufferBase(glc::GL_SHADER_STORAGE_BUFFER, kBindingBones, model_.bone_ssbo);
    glBindBufferBase(glc::GL_SHADER_STORAGE_BUFFER, kBindingRest, model_.rest_ssbo);
    glBindBufferBase(glc::GL_SHADER_STORAGE_BUFFER, kBindingVerts, model_.vbo);
    glBindBufferBase(glc::GL_SHADER_STORAGE_BUFFER, kBindingPos, model_.out_pos_ssbo);
    glBindBufferBase(glc::GL_SHADER_STORAGE_BUFFER, kBindingNrm, model_.out_nrm_ssbo);
    skin_program_.use();
    const GLuint groups = (model_.vertex_count + 63u) / 64u;
    glDispatchCompute(groups, 1, 1);
    glMemoryBarrier(glc::GL_SHADER_STORAGE_BARRIER_BIT | glc::GL_VERTEX_ATTRIB_ARRAY_BARRIER_BIT);
    gpu_skin_dispatch_count = static_cast<int>(groups);
}

void SceneRenderer::upload_cpu_skin(const Model& model, Pose& pose) {
    SkinDeformer deformer(model);
    std::vector<Vec3> pos, nrm;
    deformer.deform(model.vertices.pos, model.vertices.nrm, pose.world(), pos, nrm);
    std::vector<float> pbuf(static_cast<std::size_t>(pos.size()) * 4);
    std::vector<float> nbuf(static_cast<std::size_t>(nrm.size()) * 4);
    for (std::size_t i = 0; i < pos.size(); ++i) {
        pbuf[i * 4 + 0] = pos[i].x;
        pbuf[i * 4 + 1] = pos[i].y;
        pbuf[i * 4 + 2] = pos[i].z;
        pbuf[i * 4 + 3] = 1.0f;
        nbuf[i * 4 + 0] = nrm[i].x;
        nbuf[i * 4 + 1] = nrm[i].y;
        nbuf[i * 4 + 2] = nrm[i].z;
        nbuf[i * 4 + 3] = 0.0f;
    }
    glBindBuffer(glc::GL_SHADER_STORAGE_BUFFER, model_.out_pos_ssbo);
    glBufferSubData(glc::GL_SHADER_STORAGE_BUFFER, 0,
                    static_cast<GLsizeiptr>(pbuf.size() * sizeof(float)), pbuf.data());
    glBindBuffer(glc::GL_SHADER_STORAGE_BUFFER, model_.out_nrm_ssbo);
    glBufferSubData(glc::GL_SHADER_STORAGE_BUFFER, 0,
                    static_cast<GLsizeiptr>(nbuf.size() * sizeof(float)), nbuf.data());
    // CPU 路径下顶点着色器同样按 SSBO 读取，绑定要与计算路径保持一致。
    glBindBufferBase(glc::GL_SHADER_STORAGE_BUFFER, kBindingVerts, model_.vbo);
    glBindBufferBase(glc::GL_SHADER_STORAGE_BUFFER, kBindingPos, model_.out_pos_ssbo);
    glBindBufferBase(glc::GL_SHADER_STORAGE_BUFFER, kBindingNrm, model_.out_nrm_ssbo);
}

SceneRenderer::Texture& SceneRenderer::texture_for(const Model& model, int index) {
    static Texture missing;
    if (index < 0 || index >= static_cast<int>(model.textures.size())) return missing;
    const std::string path = model.resolve_texture(index);
    auto it = textures_.find(path);
    if (it != textures_.end()) return it->second;
    Texture tex;
    int w = 0, h = 0, comp = 0;
    stbi_set_flip_vertically_on_load(0);
    // stbi_load 用 fopen 打开窄字符路径，中文/日文纹理目录会失败；先按 UTF-8 路径读入内存。
    std::ifstream file = open_ifstream(path);
    const std::string bytes((std::istreambuf_iterator<char>(file)),
                            std::istreambuf_iterator<char>());
    unsigned char* pixels =
        bytes.empty() ? nullptr
                      : stbi_load_from_memory(reinterpret_cast<const stbi_uc*>(bytes.data()),
                                              static_cast<int>(bytes.size()), &w, &h, &comp, 4);
    if (pixels) {
        glGenTextures(1, &tex.id);
        glBindTexture(glc::GL_TEXTURE_2D, tex.id);
        glPixelStorei(glc::GL_UNPACK_ALIGNMENT, 4);
        glTexImage2D(glc::GL_TEXTURE_2D, 0, glc::GL_RGBA8, w, h, 0, glc::GL_RGBA,
                     glc::GL_UNSIGNED_BYTE, pixels);
        glGenerateMipmap(glc::GL_TEXTURE_2D);
        glTexParameteri(glc::GL_TEXTURE_2D, glc::GL_TEXTURE_MIN_FILTER,
                        static_cast<GLint>(glc::GL_LINEAR_MIPMAP_LINEAR));
        glTexParameteri(glc::GL_TEXTURE_2D, glc::GL_TEXTURE_MAG_FILTER,
                        static_cast<GLint>(glc::GL_LINEAR));
        glTexParameteri(glc::GL_TEXTURE_2D, glc::GL_TEXTURE_WRAP_S,
                        static_cast<GLint>(glc::GL_REPEAT));
        glTexParameteri(glc::GL_TEXTURE_2D, glc::GL_TEXTURE_WRAP_T,
                        static_cast<GLint>(glc::GL_REPEAT));
        stbi_image_free(pixels);
        tex.valid = true;
    }
    auto res = textures_.emplace(path, tex);
    return res.first->second;
}

SceneRenderer::Texture SceneRenderer::toon_for(const Model& model, const Material& mt) {
    if (mt.toon_shared == 0) return texture_for(model, mt.toon);
    const int index = std::clamp(static_cast<int>(mt.toon), 0, 9);
    Texture builtin;
    builtin.id = toon_ramps_[index];
    builtin.valid = builtin.id != 0;
    return builtin;
}

void SceneRenderer::bind_material(const Model& model, const Material& mt,
                                  const RenderSettings& settings) {
    mesh_program_.set4f("uDiffuse", mt.diffuse.x, mt.diffuse.y, mt.diffuse.z, mt.diffuse.w);
    mesh_program_.set3f("uAmbient", mt.ambient);
    mesh_program_.set3f("uSpecular", mt.specular);
    mesh_program_.set1f("uSpecCoef", mt.specular_coef);
    mesh_program_.set1f("uToon", settings.toon);
    mesh_program_.set3f("uLightDir", normalize(settings.light_dir));

    Texture& tex = texture_for(model, mt.texture);
    glActiveTexture(glc::GL_TEXTURE0);
    glBindTexture(glc::GL_TEXTURE_2D, tex.valid ? tex.id : 0);
    mesh_program_.set1i("uTex", 0);
    mesh_program_.set1i("uUseTex", tex.valid ? 1 : 0);

    Texture& sph = texture_for(model, mt.sphere);
    glActiveTexture(glc::GL_TEXTURE0 + 1);
    glBindTexture(glc::GL_TEXTURE_2D, sph.valid ? sph.id : 0);
    mesh_program_.set1i("uSphereTex", 1);
    mesh_program_.set1i("uUseSphere", sph.valid ? 1 : 0);
    mesh_program_.set1i("uSphereMode", static_cast<int>(mt.sphere_mode));

    const Texture toon = toon_for(model, mt);
    glActiveTexture(glc::GL_TEXTURE0 + 2);
    glBindTexture(glc::GL_TEXTURE_2D, toon.valid ? toon.id : 0);
    mesh_program_.set1i("uToonTex", 2);
    mesh_program_.set1i("uUseToonTex", toon.valid ? 1 : 0);
    glActiveTexture(glc::GL_TEXTURE0);
}

void SceneRenderer::rebuild_bone_overlay(const Model& model, Pose& pose,
                                         const RenderSettings& settings,
                                         const Selection& selection) {
    bone_verts_.clear();
    const std::vector<Mat4>& W = pose.world();
    const int nb = static_cast<int>(model.bones.size());
    // 配色与 Python 版 theme.py 一致：普通 = BONE_RGB，物理后骨骼偏青，IK 偏橙，
    // 选中 = ACCENT（#4f9dff）。
    const Vec4 normal_color(0.72f, 0.78f, 0.88f, settings.bone_alpha);
    const Vec4 after_physics_color(0.35f, 0.85f, 0.78f, settings.bone_alpha);
    const Vec4 ik_color(0.98f, 0.75f, 0.35f, settings.bone_alpha);
    const Vec4 selected_color(0.31f, 0.62f, 1.0f, std::min(1.0f, settings.bone_alpha + 0.29f));
    auto add_tri = [this](Vec3 a, Vec3 b, Vec3 c, Vec4 color) {
        const Vec3 n = normalize(cross(b - a, c - a));
        for (const Vec3& p : {a, b, c}) {
            bone_verts_.insert(bone_verts_.end(), {p.x, p.y, p.z, n.x, n.y, n.z,
                                                   color.x, color.y, color.z, color.w});
        }
    };
    for (int i = 0; i < nb; ++i) {
        const bool selected = selection.kind == Selection::BONE && selection.index == i;
        // 骨骼整体隐藏时，只把双击选中的那一根画出来（高亮），取消选择后恢复隐藏。
        if (!settings.show_bones && !(settings.focus_selection && selected)) continue;
        const Bone& b = model.bones[static_cast<std::size_t>(i)];
        if (!(b.flags & BF_VISIBLE) || !(b.flags & BF_ENABLED)) continue;
        const Mat4& M = W[static_cast<std::size_t>(i)];
        const Vec3 head(M.at(0, 3), M.at(1, 3), M.at(2, 3));
        Vec3 tail;
        if ((b.flags & BF_TAIL_INDEX) && b.tail_bone >= 0 && b.tail_bone < nb) {
            const Mat4& T = W[static_cast<std::size_t>(b.tail_bone)];
            tail = {T.at(0, 3), T.at(1, 3), T.at(2, 3)};
        } else {
            tail = head + b.tail_offset;
        }
        Vec3 dir = tail - head;
        float len = length(dir);
        if (len < 1e-5f) {
            tail = head + Vec3(0.0f, 0.4f, 0.0f);
            dir = tail - head;
            len = length(dir);
        }
        dir = dir * (1.0f / std::max(1e-6f, len));
        Vec3 side(M.at(0, 0), M.at(1, 0), M.at(2, 0));
        Vec3 up2(M.at(0, 2), M.at(1, 2), M.at(2, 2));
        if (length(side) < 1e-6f || length(up2) < 1e-6f) {
            Vec3 up(0.0f, 1.0f, 0.0f);
            if (std::fabs(dir.y) > 0.98f) up = Vec3(0.0f, 0.0f, 1.0f);
            side = normalize(cross(dir, up));
            up2 = normalize(cross(side, dir));
        } else {
            side = normalize(side);
            up2 = normalize(up2);
        }
        const float width = std::max(0.008f, len * (selected ? 0.05f : 0.035f));
        const Vec3 mid = head + dir * (len * 0.22f);
        const Vec3 ring[4] = {mid + side * width, mid + up2 * width, mid - side * width,
                              mid - up2 * width};
        Vec4 color = normal_color;
        if (b.flags & BF_AFTER_PHYSICS) color = after_physics_color;
        if (b.flags & BF_IK) color = ik_color;
        if (selected) color = selected_color;
        for (int k = 0; k < 4; ++k) {
            const Vec3 a = ring[k];
            const Vec3 b2 = ring[(k + 1) % 4];
            add_tri(head, a, b2, color);
            add_tri(tail, b2, a, color);
        }
    }
    if (bone_verts_.empty()) return;
    glBindBuffer(glc::GL_ARRAY_BUFFER, bone_mesh_.vbo);
    glBufferData(glc::GL_ARRAY_BUFFER,
                 static_cast<GLsizeiptr>(bone_verts_.size() * sizeof(float)), bone_verts_.data(),
                 glc::GL_STREAM_DRAW);
}

void SceneRenderer::build_instances(const Model& model, Pose& pose, Physics* physics,
                                    const RenderSettings& settings,
                                    const Selection& selection) {
    inst_data_.clear();
    instance_counts_[0] = instance_counts_[1] = instance_counts_[2] = instance_counts_[3] = 0;
    const std::vector<Mat4>& W = pose.world();
    // 与 Python 版一致：静态刚体压暗为 RIGID_STATIC_RGB，动态刚体按组着色；
    // 关节 type 1 蓝、弹簧橙；选中统一用 ACCENT（#4f9dff）。
    const Vec4 rigid_static(0.58f, 0.60f, 0.66f, settings.rigid_alpha);
    const Vec4 rigid_selected(0.31f, 0.62f, 1.0f, std::min(1.0f, settings.rigid_alpha + 0.30f));
    const Vec4 joint_color(0.62f, 0.72f, 0.95f, settings.joint_alpha);
    const Vec4 joint_spring(0.95f, 0.72f, 0.33f, settings.joint_alpha);
    const Vec4 joint_selected(0.31f, 0.62f, 1.0f, std::min(1.0f, settings.joint_alpha + 0.32f));

    using Item = std::pair<Mat4, Vec4>;
    std::vector<Item> boxes, spheres, cylinders, joints;
    auto scale_mat = [](float sx, float sy, float sz) {
        Mat4 s;
        s.m[0] = sx;
        s.m[5] = sy;
        s.m[10] = sz;
        return s;
    };

    // 叠加层整体隐藏时，只绘制双击选中的那一个刚体/关节（高亮），取消选择后恢复隐藏。
    const bool focus_rigid = settings.focus_selection && selection.kind == Selection::RIGID;
    const bool focus_joint = settings.focus_selection && selection.kind == Selection::JOINT;

    if (settings.show_rigid || focus_rigid) {
        const int nr = static_cast<int>(model.rigid.size());
        for (int i = 0; i < nr; ++i) {
            const bool sel = selection.kind == Selection::RIGID && selection.index == i;
            if (!settings.show_rigid && !sel) continue;
            const RigidBody& rb = model.rigid[static_cast<std::size_t>(i)];
            Vec3 pos = rb.pos;
            Quat q = rigid_euler_quat(rb.rot.x, rb.rot.y, rb.rot.z);
            if (!query_body(physics, i, pos, q) && rb.bone >= 0 && rb.bone < pose.n) {
                const Mat4 off = query_bone_offset(physics, i);
                const Mat4 m = mul(W[static_cast<std::size_t>(rb.bone)], off);
                pos = {m.at(0, 3), m.at(1, 3), m.at(2, 3)};
                q = mat3_to_quat(upper3(m));
            }
            const Mat4 rot = from_quat_pos(q, pos);
            const float sx = std::fabs(rb.size.x), sy = std::fabs(rb.size.y),
                        sz = std::fabs(rb.size.z);
            // PMX 以 mode == 0 表示「跟随骨骼」，即静态（运动学）刚体。
            Vec4 color = rigid_static;
            if (rb.mode != 0) {
                const Vec3& gc = kGroupColors[static_cast<std::size_t>(rb.group) % 16u];
                color = Vec4(gc.x, gc.y, gc.z, settings.rigid_alpha);
            }
            if (sel) color = rigid_selected;
            if (rb.shape == 0) {
                const float r = std::max(1e-3f, sx);
                spheres.emplace_back(mul(rot, scale_mat(r, r, r)), color);
            } else if (rb.shape == 2) {
                // PMX 胶囊：size.x = 半径，size.y = 圆柱段高度，两端半球由球模板补齐。
                const float r = std::max(1e-3f, sx);
                const float h = std::max(1e-3f, sy);
                cylinders.emplace_back(mul(rot, scale_mat(r, h, r)), color);
                const Mat4 cap0 = mul(rot, mul(translation({0.0f, -h * 0.5f, 0.0f}),
                                                scale_mat(r, r, r)));
                const Mat4 cap1 = mul(rot, mul(translation({0.0f, h * 0.5f, 0.0f}),
                                                scale_mat(r, r, r)));
                spheres.emplace_back(cap0, color);
                spheres.emplace_back(cap1, color);
            } else {
                boxes.emplace_back(mul(rot, scale_mat(std::max(1e-3f, sx), std::max(1e-3f, sy),
                                                      std::max(1e-3f, sz))),
                                   color);
            }
        }
    }

    if (settings.show_joints || focus_joint) {
        const int nj = static_cast<int>(model.joints.size());
        for (int i = 0; i < nj; ++i) {
            const bool sel = selection.kind == Selection::JOINT && selection.index == i;
            if (!settings.show_joints && !sel) continue;
            const Joint& j = model.joints[static_cast<std::size_t>(i)];
            const Mat4 m = from_quat_pos(rigid_euler_quat(j.rot.x, j.rot.y, j.rot.z), j.pos);
            // 关节只显示为实体球：选中略大，弹簧（type 0）橙色，6DOF（type 1）蓝色。
            const float radius = sel ? 0.055f : 0.048f;
            joints.emplace_back(mul(m, scale_mat(radius, radius, radius)),
                                sel ? joint_selected
                                    : (j.type == 0 ? joint_spring : joint_color));
        }
    }

    auto push_bucket = [this](const std::vector<Item>& items, int slot) {
        instance_counts_[slot] = static_cast<int>(items.size());
        for (const Item& it : items) {
            // 实例 SSBO 里的 mat4 是列主序，需转置；颜色紧跟其后。
            const std::size_t at = inst_data_.size();
            inst_data_.resize(at + 20);
            store_column_major(it.first, inst_data_.data() + at);
            inst_data_[at + 16] = it.second.x;
            inst_data_[at + 17] = it.second.y;
            inst_data_[at + 18] = it.second.z;
            inst_data_[at + 19] = it.second.w;
        }
    };
    // 顺序必须是 盒 → 球 → 柱 → 关节，对应 instance_counts_ 与渲染分桶。
    push_bucket(boxes, 0);
    push_bucket(spheres, 1);
    push_bucket(cylinders, 2);
    push_bucket(joints, 3);
}

void SceneRenderer::render(const Model& model, Pose& pose, Physics* physics, const Mat4& view,
                           const Mat4& proj, int width, int height,
                           const RenderSettings& settings, const Selection& selection) {
    if (!ready_ || model_.vao == 0 || width <= 0 || height <= 0) return;
    const Mat4 vp = mul(proj, view);
    // 相机世界位置：view = [R | t]，eye = -R^T t。
    const Vec3 view_t(view.at(0, 3), view.at(1, 3), view.at(2, 3));
    const Vec3 eye_neg = mul(transpose(upper3(view)), view_t);
    const Vec3 eye{-eye_neg.x, -eye_neg.y, -eye_neg.z};

    glViewport(0, 0, width, height);
    glClearColor(settings.background.x, settings.background.y, settings.background.z, 1.0f);
    glClear(glc::GL_COLOR_BUFFER_BIT | glc::GL_DEPTH_BUFFER_BIT | glc::GL_STENCIL_BUFFER_BIT);
    glEnable(glc::GL_DEPTH_TEST);
    glDepthFunc(glc::GL_LESS);
    glDepthMask(glc::GL_TRUE);
    glEnable(glc::GL_MULTISAMPLE);
    glDisable(glc::GL_CULL_FACE);
    glDisable(glc::GL_BLEND);
    glPolygonMode(glc::GL_FRONT_AND_BACK, settings.wireframe ? glc::GL_LINE : glc::GL_FILL);

    // ---- 网格地面
    if (settings.grid) {
        line_program_.use();
        line_program_.set_mat4("uMVP", vp);
        line_program_.set1f("uAlpha", 1.0f);
        glBindVertexArray(grid_vao_);
        glDrawArrays(glc::GL_LINES, 0, static_cast<GLsizei>(grid_vertex_count_));
        glBindVertexArray(0);
    }

    // ---- 蒙皮：GPU 计算着色器写 outPos/outNrm，CPU 路径则直接上传
    upload_skin_matrices(model, pose);
    if (settings.use_gpu_skinning) dispatch_gpu_skin();
    else upload_cpu_skin(model, pose);
    if (settings.use_gpu_skinning && gpu_check_enabled_ && !gpu_checked_) {
        validate_gpu_skin(model, pose);
        gpu_checked_ = true;
    }

    // ---- 主网格
    if (settings.show_mesh) {
        glBindVertexArray(model_.vao);
        glBindBuffer(glc::GL_ELEMENT_ARRAY_BUFFER, model_.ebo);

        std::vector<int> opaque, alpha;
        // PMX 面片在右手系视图中是顺时针朝外（MMD 用左手系），需与模板几何分开处理绕序。
        glFrontFace(glc::GL_CW);
        // 相机位置与视图矩阵是全局 uniform，逐材质只改材质参数。
        mesh_program_.use();
        mesh_program_.set_mat4("uView", view);
        mesh_program_.set3f("uEye", eye);
        mesh_program_.set1f("uRim", settings.rim);
        for (std::size_t r = 0; r < model_.ranges.size(); ++r) {
            const int mi = model_.ranges[r].material;
            const float a = mi >= 0 ? model.materials[static_cast<std::size_t>(mi)].diffuse.w : 1.0f;
            if (a >= 0.999f) opaque.push_back(static_cast<int>(r));
            else alpha.push_back(static_cast<int>(r));
        }

        auto draw_range = [&](int ri, bool outline) {
            const MaterialRange& range = model_.ranges[static_cast<std::size_t>(ri)];
            if (range.count == 0) return;
            const Material& mt = range.material >= 0
                                     ? model.materials[static_cast<std::size_t>(range.material)]
                                     : Material{};
            if (outline) {
                outline_program_.use();
                outline_program_.set_mat4("uView", view);
                outline_program_.set_mat4("uProj", proj);
                // NDC 半宽：投影后约 0.4~1.2 像素，且不随相机距离变化。
                outline_program_.set1f("uWidth", 0.0009f + mt.edge_size * 0.00045f);
                outline_program_.set4f("uOutlineColor", mt.edge_color.x, mt.edge_color.y,
                                       mt.edge_color.z, std::min(1.0f, mt.edge_color.w * 0.9f));
                // 外壳沿用材质贴图做 alpha 裁剪，避免填满贴图的镂空区域。
                Texture& tex = texture_for(model, mt.texture);
                glActiveTexture(glc::GL_TEXTURE0);
                glBindTexture(glc::GL_TEXTURE_2D, tex.valid ? tex.id : 0);
                outline_program_.set1i("uTex", 0);
                outline_program_.set1i("uUseTex", tex.valid ? 1 : 0);
            } else {
                mesh_program_.use();
                mesh_program_.set_mat4("uMVP", vp);
                mesh_program_.set1f("uExpand", 0.0f);
                bind_material(model, mt, settings);
            }
            glDrawElements(glc::GL_TRIANGLES, static_cast<GLsizei>(range.count),
                           glc::GL_UNSIGNED_INT,
                           reinterpret_cast<const void*>(static_cast<std::uintptr_t>(
                               range.start * sizeof(std::uint32_t))));
        };

        for (int ri : opaque) {
            const MaterialRange& range = model_.ranges[static_cast<std::size_t>(ri)];
            const Material& mt = range.material >= 0
                                     ? model.materials[static_cast<std::size_t>(range.material)]
                                     : Material{};
            if (mt.draw_flags & MF_DOUBLE_SIDED) {
                glDisable(glc::GL_CULL_FACE);
            } else {
                glEnable(glc::GL_CULL_FACE);
                glCullFace(glc::GL_BACK);
            }
            draw_range(ri, false);
        }

        // 倒置壳描边必须在网格之后：网格已写好深度，外壳只在轮廓外侧露出；
        // 若先画外壳会把整个可见面涂成描边色。描边又要画在透明材质之前：
        // 透明材质不写深度，若描边后画，外壳会盖在纱/布表面，露出大块描边色。
        if (settings.outline) {
            bool any_edge = false;
            for (int ri : opaque) {
                const MaterialRange& range = model_.ranges[static_cast<std::size_t>(ri)];
                if (range.material >= 0 &&
                    (model.materials[static_cast<std::size_t>(range.material)].draw_flags & MF_EDGE))
                    any_edge = true;
            }
            if (any_edge) {
                glEnable(glc::GL_BLEND);
                glBlendFunc(glc::GL_SRC_ALPHA, glc::GL_ONE_MINUS_SRC_ALPHA);
                glDepthMask(glc::GL_FALSE);
                // 与 Python 版一致：先用模板缓冲标记当前材质已覆盖的像素，
                // 外壳只在材质轮廓外侧绘制。单层/朝内的布料如果用纯深度裁剪，
                // 外扩后的壳会落在表面之前，把整片衣服涂成描边色。
                glEnable(glc::GL_STENCIL_TEST);
                glStencilMask(0xFF);
                for (int ri : opaque) {
                    const MaterialRange& range = model_.ranges[static_cast<std::size_t>(ri)];
                    if (range.material < 0) continue;
                    const auto& mt = model.materials[static_cast<std::size_t>(range.material)];
                    if (!(mt.draw_flags & MF_EDGE) || mt.edge_size <= 0.0f) continue;

                    glClear(glc::GL_STENCIL_BUFFER_BIT);
                    // 只写模板：材质已绘制，深度相等即视为覆盖。
                    glDisable(glc::GL_CULL_FACE);
                    glColorMask(glc::GL_FALSE, glc::GL_FALSE, glc::GL_FALSE, glc::GL_FALSE);
                    glDepthFunc(glc::GL_LEQUAL);
                    glStencilFunc(glc::GL_ALWAYS, 1, 0xFF);
                    glStencilOp(glc::GL_KEEP, glc::GL_KEEP, glc::GL_REPLACE);
                    draw_range(ri, false);

                    glColorMask(glc::GL_TRUE, glc::GL_TRUE, glc::GL_TRUE, glc::GL_TRUE);
                    glDepthFunc(glc::GL_LESS);
                    glStencilFunc(glc::GL_NOTEQUAL, 1, 0xFF);
                    glStencilOp(glc::GL_KEEP, glc::GL_KEEP, glc::GL_KEEP);
                    glEnable(glc::GL_CULL_FACE);
                    glCullFace(glc::GL_FRONT);
                    draw_range(ri, true);
                }
                glDisable(glc::GL_STENCIL_TEST);
                glCullFace(glc::GL_BACK);
                glDepthMask(glc::GL_TRUE);
                glDisable(glc::GL_BLEND);
            }
        }

        // 半透明材质最后画，才能正确覆盖前面已经完成的描边。
        if (!alpha.empty()) {
            // 关掉深度写入后，绘制顺序就是最终叠加顺序：按面区间中心到相机的
            // 距离从远到近排序（中心随锚点骨骼蒙皮），否则固定材质顺序会让
            // 远侧布料盖住近侧。
            auto range_distance = [&](int ri) {
                const std::size_t k = static_cast<std::size_t>(ri);
                Vec3 center = k < range_centers_.size() ? range_centers_[k] : Vec3{};
                const int bone = k < range_bones_.size() ? range_bones_[k] : -1;
                if (bone >= 0 && static_cast<std::size_t>(bone) < skin_cpu_.size())
                    center = transform_point(skin_cpu_[static_cast<std::size_t>(bone)], center);
                return length(center - eye);
            };
            std::sort(alpha.begin(), alpha.end(),
                      [&](int a, int b) { return range_distance(a) > range_distance(b); });
            glEnable(glc::GL_BLEND);
            glBlendFunc(glc::GL_SRC_ALPHA, glc::GL_ONE_MINUS_SRC_ALPHA);
            glDepthMask(glc::GL_FALSE);
            glDisable(glc::GL_CULL_FACE);
            for (int ri : alpha) draw_range(ri, false);
            glDepthMask(glc::GL_TRUE);
            glDisable(glc::GL_BLEND);
        }
        glBindVertexArray(0);
        glFrontFace(glc::GL_CCW);
    }

    // ---- 叠加层（半透明实体，不写深度；关闭深度测试使骨骼/刚体不被模型遮挡）
    glPolygonMode(glc::GL_FRONT_AND_BACK, glc::GL_FILL);
    glEnable(glc::GL_BLEND);
    glBlendFunc(glc::GL_SRC_ALPHA, glc::GL_ONE_MINUS_SRC_ALPHA);
    glDepthMask(glc::GL_FALSE);
    glDisable(glc::GL_DEPTH_TEST);
    glDisable(glc::GL_CULL_FACE);

    // 叠加层整体隐藏时仍要画选中的那一个（双击临时显示）。
    const bool focus_bone = settings.focus_selection && selection.kind == Selection::BONE;
    const bool focus_overlay_inst = settings.focus_selection &&
                                    (selection.kind == Selection::RIGID ||
                                     selection.kind == Selection::JOINT);

    if (settings.show_bones || focus_bone) {
        rebuild_bone_overlay(model, pose, settings, selection);
        if (!bone_verts_.empty()) {
            solid_program_.use();
            solid_program_.set_mat4("uMVP", vp);
            solid_program_.set3f("uLightDir", normalize(settings.light_dir));
            solid_program_.set3f("uEye", eye);
            glBindVertexArray(bone_mesh_.vao);
            glDrawArrays(glc::GL_TRIANGLES, 0, static_cast<GLsizei>(bone_verts_.size() / 10));
            glBindVertexArray(0);
        }
    }

    if (settings.show_rigid || settings.show_joints || focus_overlay_inst) {
        build_instances(model, pose, physics, settings, selection);
        if (!inst_data_.empty()) {
            glBindBuffer(glc::GL_SHADER_STORAGE_BUFFER, overlay_instance_ssbo_);
            glBufferData(glc::GL_SHADER_STORAGE_BUFFER,
                         static_cast<GLsizeiptr>(inst_data_.size() * sizeof(float)),
                         inst_data_.data(), glc::GL_STREAM_DRAW);
            glBindBufferBase(glc::GL_SHADER_STORAGE_BUFFER, kBindingInstances,
                             overlay_instance_ssbo_);
            inst_program_.use();
            inst_program_.set_mat4("uMVP", vp);
            inst_program_.set3f("uLightDir", normalize(settings.light_dir));
            inst_program_.set3f("uEye", eye);
            OverlayMesh* meshes[4] = {&rigid_box_, &rigid_sphere_, &rigid_cylinder_,
                                      &joint_sphere_};
            int base_instance = 0;
            for (int b = 0; b < 4; ++b) {
                const int count = instance_counts_[b];
                if (count > 0 && meshes[b]->index_count > 0) {
                    inst_program_.set1i("uInstanceBase", base_instance);
                    glBindVertexArray(meshes[b]->vao);
                    glDrawElementsInstanced(glc::GL_TRIANGLES,
                                            static_cast<GLsizei>(meshes[b]->index_count),
                                            glc::GL_UNSIGNED_INT, nullptr, count);
                }
                base_instance += count;
            }
            glBindVertexArray(0);
        }
    }

    glDepthMask(glc::GL_TRUE);
    glEnable(glc::GL_DEPTH_TEST);
    glDisable(glc::GL_BLEND);
    glPolygonMode(glc::GL_FRONT_AND_BACK, glc::GL_FILL);
    glBindBuffer(glc::GL_SHADER_STORAGE_BUFFER, 0);
}

Selection SceneRenderer::pick(const Model& model, Pose& pose, Physics* physics, const Mat4& view,
                              const Mat4& proj, int width, int height, float sx, float sy,
                              float max_px, int kinds) const {
    Selection bone_hit;
    Selection overlay_hit;
    if (model_.vao == 0) return bone_hit;
    const Mat4 vp = project_view_proj(view, proj);
    const std::vector<Mat4>& W = pose.world();
    float bone_dist = max_px;
    float overlay_dist = max_px;

    // 骨骼：线段（头 → 尾）距离
    const int nb = static_cast<int>(model.bones.size());
    for (int i = 0; (kinds & PICK_BONE) && i < nb; ++i) {
        const Bone& b = model.bones[static_cast<std::size_t>(i)];
        if (!(b.flags & BF_VISIBLE)) continue;
        const Mat4& M = W[static_cast<std::size_t>(i)];
        const Vec3 head(M.at(0, 3), M.at(1, 3), M.at(2, 3));
        Vec3 tail;
        if ((b.flags & BF_TAIL_INDEX) && b.tail_bone >= 0 && b.tail_bone < nb) {
            const Mat4& T = W[static_cast<std::size_t>(b.tail_bone)];
            tail = {T.at(0, 3), T.at(1, 3), T.at(2, 3)};
        } else {
            tail = head + b.tail_offset;
        }
        if (length(tail - head) < 1e-4f) tail = head + Vec3(0.0f, 0.3f, 0.0f);
        float hx, hy, tx, ty;
        if (!project_to_screen(vp, head, width, height, hx, hy)) continue;
        if (!project_to_screen(vp, tail, width, height, tx, ty)) continue;
        // 命中半径随投影长度变化：远处骨骼投影只有几像素，固定阈值会误抓整片区域。
        float radius = max_px;
        if (kinds & PICK_BONE) {
            const float seg_px = std::hypot(tx - hx, ty - hy);
            radius = std::min(std::max(max_px, 0.4f * seg_px), 16.0f);
        }
        const float d = point_segment_distance(sx, sy, hx, hy, tx, ty);
        if (d < radius && d < bone_dist) {
            bone_dist = d;
            bone_hit = {Selection::BONE, i};
        }
    }

    // 刚体/关节：中心投影距离
    const int nr = static_cast<int>(model.rigid.size());
    for (int i = 0; (kinds & PICK_RIGID) && i < nr; ++i) {
        const RigidBody& rb = model.rigid[static_cast<std::size_t>(i)];
        Vec3 pos = rb.pos;
        Quat q = rigid_euler_quat(rb.rot.x, rb.rot.y, rb.rot.z);
        query_body(physics, i, pos, q);
        float px, py;
        if (!project_to_screen(vp, pos, width, height, px, py)) continue;
        const float d = std::hypot(px - sx, py - sy);
        if (d < overlay_dist) {
            overlay_dist = d;
            overlay_hit = {Selection::RIGID, i};
        }
    }
    const int nj = static_cast<int>(model.joints.size());
    for (int i = 0; (kinds & PICK_JOINT) && i < nj; ++i) {
        const Joint& j = model.joints[static_cast<std::size_t>(i)];
        float px, py;
        if (!project_to_screen(vp, j.pos, width, height, px, py)) continue;
        const float d = std::hypot(px - sx, py - sy);
        if (d < overlay_dist) {
            overlay_dist = d;
            overlay_hit = {Selection::JOINT, i};
        }
    }
    // 刚体/关节画在最上层，全量拾取时优先命中它们（与 Python 版双击语义一致）。
    if (overlay_hit.kind != Selection::NONE) return overlay_hit;
    return bone_hit;
}

}  // namespace pmx
