# 依赖解析：优先使用本地 third_party/<name>，否则从可配置镜像以浅克隆方式拉取。
# 默认镜像为 gitee（GitHub 在当前网络不可达）；海外环境可 -DPMX_DEPS_MIRROR=https://github.com
include(FetchContent)

set(PMX_THIRD_PARTY "${CMAKE_CURRENT_SOURCE_DIR}/third_party")

function(pmx_add_local_or_fetch NAME REPO TAG)
    if(PMX_FETCH_DEPS AND EXISTS "${PMX_THIRD_PARTY}/${NAME}/CMakeLists.txt")
        add_subdirectory("${PMX_THIRD_PARTY}/${NAME}" "${CMAKE_BINARY_DIR}/_local/${NAME}")
        return()
    endif()

    FetchContent_Declare(${NAME}
        GIT_REPOSITORY "${PMX_DEPS_MIRROR}/${REPO}.git"
        GIT_TAG ${TAG}
        GIT_SHALLOW TRUE
        GIT_PROGRESS TRUE)
    FetchContent_MakeAvailable(${NAME})
endfunction()

# ---------------------------------------------------------------- GLFW
if(BUILD_SHARED_LIBS OR WIN32)
    set(GLFW_BUILD_DOCS OFF CACHE BOOL "" FORCE)
    set(GLFW_BUILD_TESTS OFF CACHE BOOL "" FORCE)
    set(GLFW_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
    set(GLFW_INSTALL OFF CACHE BOOL "" FORCE)
    set(GLFW_LIBRARY_TYPE STATIC CACHE STRING "" FORCE)
endif()
pmx_add_local_or_fetch(glfw glfw 3.4)

# ---------------------------------------------------------------- Dear ImGui
FetchContent_Declare(imgui
    GIT_REPOSITORY "${PMX_DEPS_MIRROR}/imgui.git"
    GIT_TAG v1.92.9b
    GIT_SHALLOW TRUE)
FetchContent_MakeAvailable(imgui)

add_library(imgui STATIC
    ${imgui_SOURCE_DIR}/imgui.cpp
    ${imgui_SOURCE_DIR}/imgui_draw.cpp
    ${imgui_SOURCE_DIR}/imgui_tables.cpp
    ${imgui_SOURCE_DIR}/imgui_widgets.cpp
    ${imgui_SOURCE_DIR}/misc/cpp/imgui_stdlib.cpp
    ${imgui_SOURCE_DIR}/backends/imgui_impl_glfw.cpp
    ${imgui_SOURCE_DIR}/backends/imgui_impl_opengl3.cpp)
target_include_directories(imgui PUBLIC
    ${imgui_SOURCE_DIR}
    ${imgui_SOURCE_DIR}/backends)
target_compile_definitions(imgui PUBLIC GLFW_INCLUDE_NONE)
target_link_libraries(imgui PUBLIC glfw)

# ---------------------------------------------------------------- stb_image
FetchContent_Declare(stb
    GIT_REPOSITORY "${PMX_DEPS_MIRROR}/stb.git"
    GIT_TAG master
    GIT_SHALLOW TRUE)
FetchContent_MakeAvailable(stb)

add_library(stb_image INTERFACE)
target_include_directories(stb_image INTERFACE ${stb_SOURCE_DIR})

# ---------------------------------------------------------------- Bullet
if(PMX_ENABLE_PHYSICS)
    if(PMX_USE_SYSTEM_BULLET)
        find_package(Bullet REQUIRED)
        add_library(bullet INTERFACE)
        target_include_directories(bullet INTERFACE ${BULLET_INCLUDE_DIRS})
        target_link_libraries(bullet INTERFACE ${BULLET_LIBRARIES})
    elseif(EXISTS "${PMX_LOCAL_BULLET_DIR}/src/btBulletDynamicsCommon.h")
        # 仓库自带的 Bullet 3.26（与 Python 版共用同一份源码，gitignore 内）。
        set(BULLET_SRC "${PMX_LOCAL_BULLET_DIR}/src")
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
    else()
        message(STATUS "Vendored Bullet not found; fetching Bullet3 from ${PMX_DEPS_MIRROR}")
        FetchContent_Declare(bullet
            GIT_REPOSITORY "${PMX_DEPS_MIRROR}/bullet3.git"
            GIT_TAG 3.25
            GIT_SHALLOW TRUE)
        set(BUILD_BULLET2_DEMOS OFF CACHE BOOL "" FORCE)
        set(BUILD_BULLET3 OFF CACHE BOOL "" FORCE)
        set(BUILD_CPU_DEMOS OFF CACHE BOOL "" FORCE)
        set(BUILD_OPENGL3_DEMOS OFF CACHE BOOL "" FORCE)
        set(BUILD_UNIT_TESTS OFF CACHE BOOL "" FORCE)
        set(USE_GRAPHICAL_BENCHMARK OFF CACHE BOOL "" FORCE)
        set(BUILD_PYBULLET OFF CACHE BOOL "" FORCE)
        FetchContent_MakeAvailable(bullet)
        if(TARGET BulletDynamics)
            add_library(bullet INTERFACE)
            target_link_libraries(bullet INTERFACE BulletDynamics BulletCollision
                BulletSoftBody LinearMath Bullet3Common)
        endif()
    endif()
endif()
