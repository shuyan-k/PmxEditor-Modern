#include "gpu/gl_api.hpp"

#include <GLFW/glfw3.h>

#include <string>

#define PMX_GL_DEFINE(ret, name, params) ret(GL_APIENTRY* name) params = nullptr;
PMX_GL_FUNCTIONS(PMX_GL_DEFINE)
#undef PMX_GL_DEFINE

namespace glapi {
namespace {
std::string g_missing;
}

const char* load() {
    g_missing.clear();
#define PMX_GL_LOAD(ret, name, params)                                            \
    name = reinterpret_cast<ret(GL_APIENTRY*) params>(glfwGetProcAddress(#name)); \
    if (!name) {                                                                  \
        if (!g_missing.empty()) g_missing += ", ";                                \
        g_missing += #name;                                                       \
    }
    PMX_GL_FUNCTIONS(PMX_GL_LOAD)
#undef PMX_GL_LOAD
    return g_missing.c_str();
}

}  // namespace glapi
