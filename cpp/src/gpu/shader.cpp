#include "gpu/shader.hpp"

#include <vector>

namespace pmx {
namespace {

GLuint compile_stage(GLenum stage, const char* src, std::string* error) {
    const GLuint sh = glCreateShader(stage);
    glShaderSource(sh, 1, &src, nullptr);
    glCompileShader(sh);
    GLint ok = 0;
    glGetShaderiv(sh, glc::GL_COMPILE_STATUS, &ok);
    if (!ok) {
        GLint len = 0;
        glGetShaderiv(sh, glc::GL_INFO_LOG_LENGTH, &len);
        std::vector<char> log(static_cast<std::size_t>(len > 1 ? len : 1), '\0');
        glGetShaderInfoLog(sh, len, nullptr, log.data());
        if (error) {
            *error = std::string(stage == glc::GL_VERTEX_SHADER ? "顶点" : "片元") +
                     "着色器编译失败: " + log.data();
        }
        glDeleteShader(sh);
        return 0;
    }
    return sh;
}

}  // namespace

ShaderProgram::~ShaderProgram() {
    if (program_) glDeleteProgram(program_);
}

bool ShaderProgram::build(const char* vs, const char* fs, std::string* error) {
    const GLuint v = compile_stage(glc::GL_VERTEX_SHADER, vs, error);
    if (!v) return false;
    const GLuint f = compile_stage(glc::GL_FRAGMENT_SHADER, fs, error);
    if (!f) {
        glDeleteShader(v);
        return false;
    }
    const GLuint prog = glCreateProgram();
    glAttachShader(prog, v);
    glAttachShader(prog, f);
    glLinkProgram(prog);
    glDeleteShader(v);
    glDeleteShader(f);
    GLint ok = 0;
    glGetProgramiv(prog, glc::GL_LINK_STATUS, &ok);
    if (!ok) {
        GLint len = 0;
        glGetProgramiv(prog, glc::GL_INFO_LOG_LENGTH, &len);
        std::vector<char> log(static_cast<std::size_t>(len > 1 ? len : 1), '\0');
        glGetProgramInfoLog(prog, len, nullptr, log.data());
        if (error) *error = std::string("着色器链接失败: ") + log.data();
        glDeleteProgram(prog);
        return false;
    }
    if (program_) glDeleteProgram(program_);
    program_ = prog;
    uniforms_.clear();
    return true;
}

bool ShaderProgram::build_compute(const char* cs, std::string* error) {
    const GLuint c = compile_stage(glc::GL_COMPUTE_SHADER, cs, error);
    if (!c) return false;
    const GLuint prog = glCreateProgram();
    glAttachShader(prog, c);
    glLinkProgram(prog);
    glDeleteShader(c);
    GLint ok = 0;
    glGetProgramiv(prog, glc::GL_LINK_STATUS, &ok);
    if (!ok) {
        GLint len = 0;
        glGetProgramiv(prog, glc::GL_INFO_LOG_LENGTH, &len);
        std::vector<char> log(static_cast<std::size_t>(len > 1 ? len : 1), '\0');
        glGetProgramInfoLog(prog, len, nullptr, log.data());
        if (error) *error = std::string("计算着色器链接失败: ") + log.data();
        glDeleteProgram(prog);
        return false;
    }
    if (program_) glDeleteProgram(program_);
    program_ = prog;
    uniforms_.clear();
    return true;
}

void ShaderProgram::use() const { glUseProgram(program_); }

GLint ShaderProgram::loc(const char* name) {
    auto it = uniforms_.find(name);
    if (it != uniforms_.end()) return it->second;
    const GLint v = glGetUniformLocation(program_, name);
    uniforms_.emplace(name, v);
    return v;
}

void ShaderProgram::set1i(const char* name, int v) { glUniform1i(loc(name), v); }
void ShaderProgram::set1f(const char* name, float v) { glUniform1f(loc(name), v); }

void ShaderProgram::set2f(const char* name, float x, float y) {
    glUniform2f(loc(name), x, y);
}

void ShaderProgram::set3f(const char* name, float x, float y, float z) {
    glUniform3f(loc(name), x, y, z);
}

void ShaderProgram::set4f(const char* name, float x, float y, float z, float w) {
    glUniform4f(loc(name), x, y, z, w);
}

void ShaderProgram::set_mat4(const char* name, const Mat4& m) {
    // Mat4 是行主序，必须让 GL 自行转置成列主序。
    glUniformMatrix4fv(loc(name), 1, glc::GL_TRUE, m.m);
}

void ShaderProgram::set_mat4_array(const char* name, const float* data, int count) {
    glUniformMatrix4fv(loc(name), count, glc::GL_FALSE, data);
}

}  // namespace pmx
