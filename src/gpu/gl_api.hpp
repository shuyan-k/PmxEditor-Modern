// 极简 OpenGL 4.6 函数加载器：只声明渲染器真正用到的入口，避免额外依赖。
#pragma once

#include <cstddef>
#include <cstdint>

#ifdef _WIN32
#define GL_APIENTRY __stdcall
#else
#define GL_APIENTRY
#endif

using GLenum = unsigned int;
using GLuint = unsigned int;
using GLint = int;
using GLsizei = int;
using GLfloat = float;
using GLchar = char;
using GLboolean = unsigned char;
using GLbitfield = unsigned int;
using GLintptr = std::ptrdiff_t;
using GLsizeiptr = std::ptrdiff_t;

// 枚举值（取自 GL 4.6 规范，避免引入 GL 头文件与系统版本冲突）。
namespace glc {
constexpr GLenum GL_FALSE = 0;
constexpr GLenum GL_TRUE = 1;
constexpr GLenum GL_NO_ERROR = 0;
constexpr GLenum GL_ZERO = 0;
constexpr GLenum GL_ONE = 1;
constexpr GLenum GL_SRC_ALPHA = 0x0302;
constexpr GLenum GL_ONE_MINUS_SRC_ALPHA = 0x0303;
constexpr GLenum GL_DEPTH_TEST = 0x0B71;
constexpr GLenum GL_STENCIL_TEST = 0x0B90;
constexpr GLenum GL_BLEND = 0x0BE2;
constexpr GLenum GL_CULL_FACE = 0x0B44;
constexpr GLenum GL_BACK = 0x0405;
constexpr GLenum GL_FRONT = 0x0404;
constexpr GLenum GL_FRONT_AND_BACK = 0x0408;
constexpr GLenum GL_CCW = 0x0901;
constexpr GLenum GL_CW = 0x0900;
constexpr GLenum GL_LEQUAL = 0x0203;
constexpr GLenum GL_LESS = 0x0201;
constexpr GLenum GL_ALWAYS = 0x0207;
constexpr GLenum GL_NOTEQUAL = 0x0205;
constexpr GLenum GL_KEEP = 0x1E00;
constexpr GLenum GL_REPLACE = 0x1E01;
constexpr GLenum GL_COLOR_BUFFER_BIT = 0x00004000;
constexpr GLenum GL_DEPTH_BUFFER_BIT = 0x00000100;
constexpr GLenum GL_STENCIL_BUFFER_BIT = 0x00000400;
constexpr GLenum GL_TRIANGLES = 0x0004;
constexpr GLenum GL_TRIANGLE_STRIP = 0x0005;
constexpr GLenum GL_LINES = 0x0001;
constexpr GLenum GL_UNSIGNED_BYTE = 0x1401;
constexpr GLenum GL_UNSIGNED_INT = 0x1405;
constexpr GLenum GL_FLOAT = 0x1406;
constexpr GLenum GL_RGBA = 0x1908;
constexpr GLenum GL_RGB = 0x1907;
constexpr GLenum GL_RGBA8 = 0x8058;
constexpr GLenum GL_SRGB8_ALPHA8 = 0x8C43;
constexpr GLenum GL_LINEAR = 0x2601;
constexpr GLenum GL_LINEAR_MIPMAP_LINEAR = 0x2703;
constexpr GLenum GL_NEAREST = 0x2600;
constexpr GLenum GL_REPEAT = 0x2901;
constexpr GLenum GL_CLAMP_TO_EDGE = 0x812F;
constexpr GLenum GL_TEXTURE_2D = 0x0DE1;
constexpr GLenum GL_TEXTURE0 = 0x84C0;
constexpr GLenum GL_TEXTURE_MIN_FILTER = 0x2801;
constexpr GLenum GL_TEXTURE_MAG_FILTER = 0x2800;
constexpr GLenum GL_TEXTURE_WRAP_S = 0x2802;
constexpr GLenum GL_TEXTURE_WRAP_T = 0x2803;
constexpr GLenum GL_TEXTURE_MAX_ANISOTROPY_EXT = 0x84FE;
constexpr GLenum GL_TEXTURE_MAX_LEVEL = 0x813D;
constexpr GLenum GL_UNPACK_ALIGNMENT = 0x0CF5;
constexpr GLenum GL_VERSION = 0x1F02;
constexpr GLenum GL_RENDERER = 0x1F01;
constexpr GLenum GL_VENDOR = 0x1F00;
constexpr GLenum GL_VERTEX_SHADER = 0x8B31;
constexpr GLenum GL_FRAGMENT_SHADER = 0x8B30;
constexpr GLenum GL_COMPUTE_SHADER = 0x91B9;
constexpr GLenum GL_COMPILE_STATUS = 0x8B81;
constexpr GLenum GL_LINK_STATUS = 0x8B82;
constexpr GLenum GL_INFO_LOG_LENGTH = 0x8B84;
constexpr GLenum GL_ARRAY_BUFFER = 0x8892;
constexpr GLenum GL_ELEMENT_ARRAY_BUFFER = 0x8893;
constexpr GLenum GL_STATIC_DRAW = 0x88E4;
constexpr GLenum GL_DYNAMIC_DRAW = 0x88E8;
constexpr GLenum GL_STREAM_DRAW = 0x88E0;
constexpr GLenum GL_SHADER_STORAGE_BUFFER = 0x90D2;
constexpr GLenum GL_SHADER_STORAGE_BARRIER_BIT = 0x00002000;
constexpr GLenum GL_VERTEX_ATTRIB_ARRAY_BARRIER_BIT = 0x00000001;
constexpr GLenum GL_MAP_READ_BIT = 0x0001;
constexpr GLenum GL_MAP_WRITE_BIT = 0x0002;
constexpr GLenum GL_MAP_INVALIDATE_BUFFER_BIT = 0x0008;
constexpr GLenum GL_MAP_UNSYNCHRONIZED_BIT = 0x0020;
constexpr GLenum GL_POLYGON_OFFSET_FILL = 0x8037;
constexpr GLenum GL_POLYGON_OFFSET_LINE = 0x2A02;
constexpr GLenum GL_FILL = 0x1B02;
constexpr GLenum GL_LINE = 0x1B01;
constexpr GLenum GL_MULTISAMPLE = 0x809D;
constexpr GLenum GL_DEPTH_CLAMP = 0x864F;
}  // namespace glc

#define PMX_GL_FUNCTIONS(X)                                                        \
    X(void, glClearColor, (GLfloat, GLfloat, GLfloat, GLfloat))                    \
    X(void, glClear, (GLbitfield))                                                 \
    X(void, glViewport, (GLint, GLint, GLsizei, GLsizei))                          \
    X(void, glEnable, (GLenum))                                                    \
    X(void, glDisable, (GLenum))                                                   \
    X(void, glDepthMask, (GLboolean))                                              \
    X(void, glDepthFunc, (GLenum))                                                 \
    X(void, glColorMask, (GLboolean, GLboolean, GLboolean, GLboolean))             \
    X(void, glStencilMask, (GLuint))                                                \
    X(void, glStencilFunc, (GLenum, GLint, GLuint))                                 \
    X(void, glStencilOp, (GLenum, GLenum, GLenum))                                  \
    X(void, glBlendFunc, (GLenum, GLenum))                                         \
    X(void, glBlendFuncSeparate, (GLenum, GLenum, GLenum, GLenum))                 \
    X(void, glCullFace, (GLenum))                                                  \
    X(void, glFrontFace, (GLenum))                                                 \
    X(void, glPolygonOffset, (GLfloat, GLfloat))                                   \
    X(void, glPolygonMode, (GLenum, GLenum))                                       \
    X(void, glLineWidth, (GLfloat))                                                \
    X(void, glDrawElements, (GLenum, GLsizei, GLenum, const void*))                \
    X(void, glDrawElementsInstanced, (GLenum, GLsizei, GLenum, const void*, GLsizei)) \
    X(void, glDrawArrays, (GLenum, GLint, GLsizei))                                \
    X(void, glDrawArraysInstanced, (GLenum, GLint, GLsizei, GLsizei))              \
    X(const GLchar*, glGetString, (GLenum))                                        \
    X(GLenum, glGetError, (void))                                                  \
    X(void, glGenBuffers, (GLsizei, GLuint*))                                      \
    X(void, glBindBuffer, (GLenum, GLuint))                                        \
    X(void, glBufferData, (GLenum, GLsizeiptr, const void*, GLenum))               \
    X(void, glBufferSubData, (GLenum, GLintptr, GLsizeiptr, const void*))          \
    X(void, glDeleteBuffers, (GLsizei, const GLuint*))                             \
    X(void, glBindBufferBase, (GLenum, GLuint, GLuint))                            \
    X(void*, glMapBufferRange, (GLenum, GLintptr, GLsizeiptr, GLbitfield))         \
    X(GLboolean, glUnmapBuffer, (GLenum))                                          \
    X(void, glGenVertexArrays, (GLsizei, GLuint*))                                 \
    X(void, glBindVertexArray, (GLuint))                                           \
    X(void, glDeleteVertexArrays, (GLsizei, const GLuint*))                        \
    X(void, glEnableVertexAttribArray, (GLuint))                                   \
    X(void, glVertexAttribPointer, (GLuint, GLint, GLenum, GLboolean, GLsizei, const void*)) \
    X(void, glVertexAttribIPointer, (GLuint, GLint, GLenum, GLsizei, const void*)) \
    X(void, glVertexAttribDivisor, (GLuint, GLuint))                               \
    X(GLuint, glCreateShader, (GLenum))                                            \
    X(void, glShaderSource, (GLuint, GLsizei, const GLchar* const*, const GLint*)) \
    X(void, glCompileShader, (GLuint))                                             \
    X(void, glGetShaderiv, (GLuint, GLenum, GLint*))                               \
    X(void, glGetShaderInfoLog, (GLuint, GLsizei, GLsizei*, GLchar*))              \
    X(void, glDeleteShader, (GLuint))                                              \
    X(GLuint, glCreateProgram, (void))                                             \
    X(void, glAttachShader, (GLuint, GLuint))                                      \
    X(void, glLinkProgram, (GLuint))                                               \
    X(void, glGetProgramiv, (GLuint, GLenum, GLint*))                              \
    X(void, glGetProgramInfoLog, (GLuint, GLsizei, GLsizei*, GLchar*))             \
    X(void, glUseProgram, (GLuint))                                                \
    X(void, glDeleteProgram, (GLuint))                                             \
    X(GLint, glGetUniformLocation, (GLuint, const GLchar*))                        \
    X(void, glUniform1i, (GLint, GLint))                                           \
    X(void, glUniform1f, (GLint, GLfloat))                                         \
    X(void, glUniform2f, (GLint, GLfloat, GLfloat))                                \
    X(void, glUniform3f, (GLint, GLfloat, GLfloat, GLfloat))                       \
    X(void, glUniform4f, (GLint, GLfloat, GLfloat, GLfloat, GLfloat))              \
    X(void, glUniformMatrix4fv, (GLint, GLsizei, GLboolean, const GLfloat*))       \
    X(void, glGenTextures, (GLsizei, GLuint*))                                     \
    X(void, glBindTexture, (GLenum, GLuint))                                       \
    X(void, glTexImage2D, (GLenum, GLint, GLint, GLsizei, GLsizei, GLint, GLenum, GLenum, const void*)) \
    X(void, glTexParameteri, (GLenum, GLenum, GLint))                              \
    X(void, glGenerateMipmap, (GLenum))                                            \
    X(void, glActiveTexture, (GLenum))                                             \
    X(void, glDeleteTextures, (GLsizei, const GLuint*))                            \
    X(void, glPixelStorei, (GLenum, GLint))                                        \
    X(void, glDispatchCompute, (GLuint, GLuint, GLuint))                           \
    X(void, glMemoryBarrier, (GLbitfield))

#define PMX_GL_DECLARE(ret, name, params) extern ret(GL_APIENTRY* name) params;
PMX_GL_FUNCTIONS(PMX_GL_DECLARE)
#undef PMX_GL_DECLARE

namespace glapi {
// 返回缺失入口名字（空字符串表示全部就绪）。
const char* load();
}  // namespace glapi
