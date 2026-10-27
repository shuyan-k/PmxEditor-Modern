// GLSL 程序封装：编译/链接/错误日志与 uniform 位置缓存。
#pragma once

#include <string>
#include <unordered_map>

#include "core/math.hpp"
#include "gpu/gl_api.hpp"

namespace pmx {

class ShaderProgram {
public:
    ShaderProgram() = default;
    ~ShaderProgram();
    ShaderProgram(const ShaderProgram&) = delete;
    ShaderProgram& operator=(const ShaderProgram&) = delete;

    bool build(const char* vs, const char* fs, std::string* error);
    bool build_compute(const char* cs, std::string* error);

    void use() const;
    GLuint id() const { return program_; }

    GLint loc(const char* name);
    void set1i(const char* name, int v);
    void set1f(const char* name, float v);
    void set2f(const char* name, float x, float y);
    void set3f(const char* name, float x, float y, float z);
    void set3f(const char* name, Vec3 v) { set3f(name, v.x, v.y, v.z); }
    void set4f(const char* name, float x, float y, float z, float w);
    void set_mat4(const char* name, const Mat4& m);
    void set_mat4_array(const char* name, const float* data, int count);

private:
    GLuint program_ = 0;
    std::unordered_map<std::string, GLint> uniforms_;
};

}  // namespace pmx
