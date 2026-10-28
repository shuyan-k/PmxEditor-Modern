# 依赖解析：默认全部使用仓库内 third_party/ 的源码，断网也能构建；
# 只有显式 -DPMX_FETCH_DEPS=ON 且本地副本缺失时才从镜像拉取。
include(FetchContent)

set(PMX_THIRD_PARTY "${CMAKE_CURRENT_SOURCE_DIR}/third_party")

function(pmx_missing_dep NAME)
    message(FATAL_ERROR
        "缺少依赖 cpp/third_party/${NAME}。仓库应自带该目录；"
        "如确需联网获取，请加 -DPMX_FETCH_DEPS=ON。")
endfunction()

function(pmx_fetch NAME REPO TAG)
    FetchContent_Declare(${NAME}
        GIT_REPOSITORY "${PMX_DEPS_MIRROR}/${REPO}.git"
        GIT_TAG ${TAG}
        GIT_SHALLOW TRUE
        GIT_PROGRESS TRUE)
    FetchContent_MakeAvailable(${NAME})
endfunction()

# ---------------------------------------------------------------- GLFW 3.4
set(GLFW_BUILD_DOCS OFF CACHE BOOL "" FORCE)
set(GLFW_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(GLFW_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(GLFW_INSTALL OFF CACHE BOOL "" FORCE)
set(GLFW_LIBRARY_TYPE STATIC CACHE STRING "" FORCE)
# 只用 X11 后端：Wayland 后端需要 wayland-scanner 等额外工具，缺失时 GLFW 会直接
# FATAL_ERROR；XWayland 已能覆盖常见桌面。
set(GLFW_BUILD_WAYLAND OFF CACHE BOOL "" FORCE)

if(EXISTS "${PMX_THIRD_PARTY}/glfw/CMakeLists.txt")
    add_subdirectory("${PMX_THIRD_PARTY}/glfw" "${CMAKE_BINARY_DIR}/third_party/glfw")
else()
    if(NOT PMX_FETCH_DEPS)
        pmx_missing_dep(glfw)
    endif()
    pmx_fetch(glfw glfw 3.4)
endif()

# ---------------------------------------------------------------- Dear ImGui
if(EXISTS "${PMX_THIRD_PARTY}/imgui/imgui.cpp")
    set(IMGUI_DIR "${PMX_THIRD_PARTY}/imgui")
else()
    if(NOT PMX_FETCH_DEPS)
        pmx_missing_dep(imgui)
    endif()
    pmx_fetch(imgui imgui v1.92.9b)
    set(IMGUI_DIR "${imgui_SOURCE_DIR}")
endif()

add_library(imgui STATIC
    ${IMGUI_DIR}/imgui.cpp
    ${IMGUI_DIR}/imgui_draw.cpp
    ${IMGUI_DIR}/imgui_tables.cpp
    ${IMGUI_DIR}/imgui_widgets.cpp
    ${IMGUI_DIR}/misc/cpp/imgui_stdlib.cpp
    ${IMGUI_DIR}/backends/imgui_impl_glfw.cpp
    ${IMGUI_DIR}/backends/imgui_impl_opengl3.cpp)
target_include_directories(imgui PUBLIC
    ${IMGUI_DIR}
    ${IMGUI_DIR}/backends)
target_compile_definitions(imgui PUBLIC GLFW_INCLUDE_NONE)
target_link_libraries(imgui PUBLIC glfw)

# ---------------------------------------------------------------- stb_image
if(EXISTS "${PMX_THIRD_PARTY}/stb/stb_image.h")
    set(STB_DIR "${PMX_THIRD_PARTY}/stb")
else()
    if(NOT PMX_FETCH_DEPS)
        pmx_missing_dep(stb)
    endif()
    pmx_fetch(stb stb master)
    set(STB_DIR "${stb_SOURCE_DIR}")
endif()

add_library(stb_image INTERFACE)
target_include_directories(stb_image INTERFACE ${STB_DIR})

# ---------------------------------------------------------------- Bullet
if(PMX_ENABLE_PHYSICS)
    if(PMX_USE_SYSTEM_BULLET)
        find_package(Bullet REQUIRED)
        add_library(bullet INTERFACE)
        target_include_directories(bullet INTERFACE ${BULLET_INCLUDE_DIRS})
        target_link_libraries(bullet INTERFACE ${BULLET_LIBRARIES})
    else()
        set(BULLET_SRC "${PMX_BULLET_SRC_DIR}")
        if(EXISTS "${BULLET_SRC}/btBulletDynamicsCommon.h")
            file(GLOB_RECURSE BULLET_SOURCES CONFIGURE_DEPENDS
                "${BULLET_SRC}/LinearMath/*.cpp"
                "${BULLET_SRC}/BulletCollision/*.cpp"
                "${BULLET_SRC}/BulletDynamics/*.cpp"
                "${BULLET_SRC}/BulletSoftBody/*.cpp"
                "${BULLET_SRC}/Bullet3Common/*.cpp")
            list(FILTER BULLET_SOURCES EXCLUDE REGEX ".*Mt\\.cpp$")
            add_library(bullet STATIC ${BULLET_SOURCES})
            target_include_directories(bullet PUBLIC "${BULLET_SRC}")
            target_compile_definitions(bullet PUBLIC BT_USE_DOUBLE_PRECISION=0)
            if(MSVC)
                target_compile_options(bullet PRIVATE /W0 /bigobj)
            else()
                target_compile_options(bullet PRIVATE -w)
            endif()
        elseif(PMX_FETCH_DEPS)
            message(STATUS "Vendored Bullet not found; fetching Bullet 3.25 from ${PMX_DEPS_MIRROR}")
            set(BUILD_BULLET2_DEMOS OFF CACHE BOOL "" FORCE)
            set(BUILD_BULLET3 OFF CACHE BOOL "" FORCE)
            set(BUILD_CPU_DEMOS OFF CACHE BOOL "" FORCE)
            set(BUILD_OPENGL3_DEMOS OFF CACHE BOOL "" FORCE)
            set(BUILD_UNIT_TESTS OFF CACHE BOOL "" FORCE)
            # Extras（BulletRobotics/GUI）会连带编译 examples 下的 TinyRenderer，
            # 其旧代码无法通过 GCC 13，且本项目完全用不到。
            set(BUILD_EXTRAS OFF CACHE BOOL "" FORCE)
            set(USE_GRAPHICAL_BENCHMARK OFF CACHE BOOL "" FORCE)
            set(BUILD_PYBULLET OFF CACHE BOOL "" FORCE)
            pmx_fetch(bullet bullet3 3.25)
            add_library(bullet_impl INTERFACE)
            # Bullet 上游不声明各静态库之间的依赖，链接顺序需要重新扫描。
            if(CMAKE_VERSION VERSION_GREATER_EQUAL 3.24)
                target_link_libraries(bullet_impl INTERFACE
                    "$<LINK_GROUP:RESCAN,BulletDynamics,BulletCollision,BulletSoftBody,LinearMath,Bullet3Common>")
            else()
                target_link_libraries(bullet_impl INTERFACE BulletDynamics BulletCollision
                    BulletSoftBody LinearMath Bullet3Common)
            endif()
            # Bullet 的上游 CMake 只在目录级 INCLUDE_DIRECTORIES 里加了 src，
            # 不会随目标传递，这里补上，否则 <btBulletDynamicsCommon.h> 找不到。
            target_include_directories(bullet_impl INTERFACE "${bullet_SOURCE_DIR}/src")
            add_library(bullet ALIAS bullet_impl)
        else()
            message(FATAL_ERROR
                "找不到 Bullet 源码：${BULLET_SRC}。仓库自带 cpp/third_party/bullet/src，"
                "请检查后重试；或加 -DPMX_FETCH_DEPS=ON 联网获取。")
        endif()
    endif()
endif()
