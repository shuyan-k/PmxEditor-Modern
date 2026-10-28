@echo off
setlocal
cd /d "%~dp0"

where cmake >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 cmake，请安装 CMake 并加入 PATH。
    exit /b 1
)

cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
if errorlevel 1 exit /b 1

cmake --build build --config Release
if errorlevel 1 exit /b 1

echo.
echo 构建完成：
echo   %~dp0pmxstudio.exe
echo   %~dp0build\Release\pmx_tests.exe
endlocal
