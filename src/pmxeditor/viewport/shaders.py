"""着色器源码与编译工具。"""
from __future__ import annotations

from OpenGL import GL


# ---------------------------------------------------------------- 着色器

MESH_VS = """
#version 120
attribute vec3 aPos;
attribute vec3 aNrm;
attribute vec2 aUV;
uniform mat4 uMVP;
uniform float uExpand;
varying vec3 vN;
varying vec2 vUV;
void main() {
    vN = aNrm;
    vUV = aUV;
    gl_Position = uMVP * vec4(aPos + aNrm * uExpand, 1.0);
}
"""

MESH_FS = """
#version 120
uniform sampler2D uTex;
uniform int uUseTex;
uniform vec4 uDiffuse;
uniform vec3 uAmbient;
uniform vec3 uSpecular;
uniform float uSpecCoef;
uniform float uToon;
uniform int uOutline;
uniform vec4 uOutlineColor;
uniform vec3 uLightDir;
uniform sampler2D uSphereTex;
uniform int uUseSphere;
uniform int uSphereMode;
varying vec3 vN;
varying vec2 vUV;
void main() {
    if (uOutline == 1) {
        gl_FragColor = uOutlineColor;
        return;
    }
    vec4 tex = uUseTex == 1 ? texture2D(uTex, vUV) : vec4(1.0);
    if (tex.a < 0.02) discard;
    vec4 base = vec4(tex.rgb * uDiffuse.rgb, tex.a * uDiffuse.a);
    vec3 n = normalize(vN);
    float ndl = max(dot(n, normalize(uLightDir)), 0.0);
    float lambert = 0.54 + 0.16 * ndl;
    float toon = 0.58 + 0.12 * smoothstep(0.20, 0.80, ndl);
    float shade = mix(lambert, toon, uToon);
    vec3 col = base.rgb * shade + uAmbient * base.rgb * 0.06;
    float spec = pow(max(ndl, 0.0), 14.0) * uSpecCoef;
    col += uSpecular * spec;
    if (uUseSphere == 1) {
        vec2 suv = n.xy * 0.5 + 0.5;
        vec4 sp = texture2D(uSphereTex, suv);
        if (uSphereMode == 1) {
            col = col * (sp.rgb * 1.6);
        } else if (uSphereMode == 2) {
            col = col + sp.rgb * sp.a;
        } else if (uSphereMode == 3) {
            col = mix(col, sp.rgb, sp.a);
        }
    }
    gl_FragColor = vec4(clamp(col, 0.0, 1.0), base.a);
}
"""

LINE_VS = """
#version 120
attribute vec3 aPos;
attribute vec3 aColor;
uniform mat4 uMVP;
varying vec3 vC;
void main() {
    vC = aColor;
    gl_Position = uMVP * vec4(aPos, 1.0);
}
"""

LINE_FS = """
#version 120
uniform float uAlpha;
varying vec3 vC;
void main() {
    gl_FragColor = vec4(vC, uAlpha);
}
"""

# 骨骼/关节/刚体实体叠加层：逐顶点颜色 + 双面光照 + 边缘菲涅尔，
# 半透明显示时不写深度，避免遮挡模型和彼此。
SOLID_VS = """
#version 120
attribute vec3 aPos;
attribute vec3 aNrm;
attribute vec4 aColor;
uniform mat4 uMVP;
varying vec3 vN;
varying vec3 vPos;
varying vec4 vC;
void main() {
    vN = aNrm;
    vPos = aPos;
    vC = aColor;
    gl_Position = uMVP * vec4(aPos, 1.0);
}
"""

SOLID_FS = """
#version 120
uniform vec3 uLightDir;
uniform vec3 uEye;
varying vec3 vN;
varying vec3 vPos;
varying vec4 vC;
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
    gl_FragColor = vec4(clamp(col, 0.0, 1.0), vC.a);
}
"""


def _compile(vs: str, fs: str, bindings=None):
    prog = GL.glCreateProgram()
    shaders = []
    for src, kind in ((vs, GL.GL_VERTEX_SHADER), (fs, GL.GL_FRAGMENT_SHADER)):
        sh = GL.glCreateShader(kind)
        GL.glShaderSource(sh, src)
        GL.glCompileShader(sh)
        ok = GL.glGetShaderiv(sh, GL.GL_COMPILE_STATUS)
        log = GL.glGetShaderInfoLog(sh)
        if not ok:
            raise RuntimeError("着色器编译失败: %s" % (log.decode("utf-8", "replace")
                                                       if isinstance(log, bytes) else log))
        GL.glAttachShader(prog, sh)
        shaders.append(sh)
    for name, loc in (bindings or {}).items():
        GL.glBindAttribLocation(prog, loc, name)
    GL.glLinkProgram(prog)
    if not GL.glGetProgramiv(prog, GL.GL_LINK_STATUS):
        log = GL.glGetProgramInfoLog(prog)
        raise RuntimeError("着色器链接失败: %s" % (log.decode("utf-8", "replace")
                                                   if isinstance(log, bytes) else log))
    for sh in shaders:
        GL.glDeleteShader(sh)
    return prog
