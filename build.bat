@echo off
setlocal
cd /d "%~dp0"

rem Keep this file ASCII-only: cmd.exe parses the script in the console code page,
rem so UTF-8 Chinese text here would print as mojibake (and can break parsing).

where cmake >nul 2>nul
if errorlevel 1 (
    echo [ERROR] cmake not found. Install CMake and add it to PATH.
    exit /b 1
)

cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
if errorlevel 1 exit /b 1

cmake --build build --config Release
if errorlevel 1 exit /b 1

echo.
echo Build completed:
echo   %~dp0pmxstudio.exe
echo   %~dp0build\Release\pmx_tests.exe
endlocal
