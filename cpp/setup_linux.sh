#!/usr/bin/env bash
# Linux 一键构建：安装系统依赖 -> 配置 -> 编译 -> 跑无窗口测试。
set -euo pipefail
cd "$(dirname "$0")"

need_install() {
    ! command -v cmake >/dev/null 2>&1 && return 0
    ! pkg-config --exists x11 2>/dev/null && return 0
    ! pkg-config --exists xrandr 2>/dev/null && return 0
    return 1
}

if need_install; then
    if command -v apt-get >/dev/null 2>&1; then
        SUDO=""
        [ "$(id -u)" -ne 0 ] && SUDO="sudo"
        $SUDO apt-get update
        $SUDO apt-get install -y build-essential cmake ninja-build \
            libx11-dev libxrandr-dev libxinerama-dev libxcursor-dev libxi-dev \
            fonts-noto-cjk
    else
        echo "非 Debian/Ubuntu 系统：请自行安装 cmake、C++20 编译器与 X11 开发包" >&2
    fi
fi

GENERATOR=""
command -v ninja >/dev/null 2>&1 && GENERATOR="-G Ninja"

cmake -S . -B build $GENERATOR -DCMAKE_BUILD_TYPE=Release
cmake --build build -j"$(nproc)"

echo
./build/pmx_tests
echo "构建完成：$PWD/build/pmxstudio"
