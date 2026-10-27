cmake_minimum_required(VERSION 3.20)

# CMake 4 默认拒绝 cmake_minimum_required < 3.5 的第三方工程，GLFW 3.4 仍使用旧式声明。
set(CMAKE_POLICY_VERSION_MINIMUM 3.5 CACHE STRING "" FORCE)

project(PmxStudioCpp VERSION 0.1.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

if(MSVC)
    add_compile_options(/utf-8 /EHsc /MP)
    add_compile_definitions(_CRT_SECURE_NO_WARNINGS NOMINMAX WIN32_LEAN_AND_MEAN)
else()
    add_compile_options(-Wall -Wextra -Wno-unused-parameter)
endif()

option(PMX_BUILD_APP "Build the GLFW + ImGui viewer" ON)
option(PMX_BUILD_TESTS "Build parity/unit tests" ON)
option(PMX_ENABLE_PHYSICS "Build Bullet physics backend" ON)
option(PMX_USE_SYSTEM_BULLET "Use an installed Bullet instead of the vendored source" OFF)
option(PMX_FETCH_DEPS "Fetch GLFW/ImGui/stb when no local copy exists" ON)
set(PMX_DEPS_MIRROR "https://gitee.com/mirrors" CACHE STRING
    "Git mirror used for dependencies (use https://github.com for upstream)")
set(PMX_LOCAL_BULLET_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../native/bullet_src"
    CACHE PATH "Vendored Bullet 3.26 source tree")

include(cmake/Dependencies.cmake)

# ---------------------------------------------------------------- core
set(PMX_CORE_SOURCES
    src/core/pmx_io.cpp
    src/core/model.cpp
    src/core/pose.cpp
    src/core/skinning.cpp
    src/core/morph.cpp
    src/core/vpd.cpp
)

add_library(pmx_core STATIC ${PMX_CORE_SOURCES})
target_include_directories(pmx_core PUBLIC src)
target_compile_features(pmx_core PUBLIC cxx_std_20)

if(PMX_ENABLE_PHYSICS)
    target_sources(pmx_core PRIVATE src/physics/physics.cpp src/physics/softbody.cpp)
    target_link_libraries(pmx_core PRIVATE bullet)
    target_compile_definitions(pmx_core PUBLIC PMX_ENABLE_PHYSICS=1)
endif()

# ---------------------------------------------------------------- gpu
set(PMX_GPU_SOURCES
    src/gpu/gl_api.cpp
    src/gpu/shader.cpp
    src/gpu/renderer.cpp
)

add_library(pmx_gpu STATIC ${PMX_GPU_SOURCES})
target_include_directories(pmx_gpu PUBLIC src)
target_link_libraries(pmx_gpu PUBLIC pmx_core glfw stb_image)
# 系统 GL 头只声明到 1.1，与自定义加载器的函数指针同名冲突；统一关掉 GLFW 的 GL 包含。
target_compile_definitions(pmx_gpu PUBLIC PMX_GPU_OPENGL=1 GLFW_INCLUDE_NONE)

# ---------------------------------------------------------------- app
if(PMX_BUILD_APP)
    file(GLOB PMX_APP_SOURCES CONFIGURE_DEPENDS src/app/*.cpp src/app/panels/*.cpp)
    add_executable(pmxstudio ${PMX_APP_SOURCES})
    target_link_libraries(pmxstudio PRIVATE pmx_gpu imgui glfw)
    if(WIN32)
        set_target_properties(pmxstudio PROPERTIES WIN32_EXECUTABLE OFF)
        # 资源管理器文件对话框（GetOpenFileNameW / GetSaveFileNameW）
        target_link_libraries(pmxstudio PRIVATE comdlg32)
    endif()
endif()

# ---------------------------------------------------------------- tests
if(PMX_BUILD_TESTS)
    add_executable(pmx_tests tests/test_core.cpp)
    target_link_libraries(pmx_tests PRIVATE pmx_core)
    target_compile_definitions(pmx_tests PRIVATE
        PMX_TEST_MODEL="${CMAKE_CURRENT_SOURCE_DIR}/../tests/test_model.pmx")

    # 与 Python 版做读写一致性校验的命令行探针（tools/parity_check.py 调用）。
    add_executable(pmx_parity_probe tests/parity_probe.cpp)
    target_link_libraries(pmx_parity_probe PRIVATE pmx_core)
endif()

# 把依赖的运行时 DLL 放到可执行文件旁边（Windows 开发期免安装）。
if(WIN32 AND PMX_BUILD_APP)
    add_custom_command(TARGET pmxstudio POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            $<TARGET_FILE:glfw> $<TARGET_FILE_DIR:pmxstudio>)
endif()
