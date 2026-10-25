# Build the pybind11 compute backend with the configured Visual Studio toolchain.
# Usage: powershell -ExecutionPolicy Bypass -File native\build_core.ps1 [-Python <python.exe>]
param([string]$Python = "")
$ErrorActionPreference = "Stop"
# 与 build.ps1 一致：先看环境变量 / vswhere，再回退到常见安装位置（含本机 D 盘 BuildTools）。
$candidates = @()
if ($env:VSINSTALLDIR) { $candidates += $env:VSINSTALLDIR.TrimEnd("\") }
$vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
if (Test-Path $vswhere) {
    $found = & $vswhere -latest -products * -property installationPath 2>$null
    if ($found) { $candidates += $found.Trim() }
}
$candidates += @(
    "C:\Program Files\Microsoft Visual Studio\2022\Enterprise",
    "C:\Program Files\Microsoft Visual Studio\2022\Professional",
    "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools",
    "C:\Program Files\Microsoft Visual Studio\2022\BuildTools",
    "D:\Project\DevEnv\VS2022BuildTools"
)
$vsDevCmd = $null
foreach ($base in $candidates) {
    $cand = Join-Path $base "Common7\Tools\VsDevCmd.bat"
    if (Test-Path $cand) { $vsDevCmd = $cand; break }
}
if (-not $vsDevCmd) {
    throw "Visual Studio (with C++ tools) not found; set VSINSTALLDIR or install VS2022 Build Tools"
}
# build.ps1 把导入库写在 native\obj\ 下；老的本机构建可能在 native\ 根目录留一份，两处都接受。
$libCandidates = @(
    (Join-Path $PSScriptRoot "obj\bullet_phys.lib"),
    (Join-Path $PSScriptRoot "bullet_phys.lib")
)
if (-not ($libCandidates | Where-Object { Test-Path $_ })) {
    throw "Missing bullet_phys.lib in native\obj or native\; build Bullet first (native\build.ps1)."
}

# 优先用仓库内便携运行时编译，保证扩展与 build\python 的解释器版本一致；显式 -Python 优先。
$portable = Join-Path (Split-Path -Parent $PSScriptRoot) "build\python\python.exe"
if ($Python) {
    $python = (Resolve-Path $Python).Path
} elseif (Test-Path $portable) {
    $python = $portable
} else {
    $python = (Get-Command python.exe -ErrorAction Stop).Source
}
Write-Host "python : $python"
$command = 'call "{0}" -no_logo -arch=amd64 -host_arch=amd64 && cd /d "{1}" && "{2}" setup_core.py build_ext --inplace' -f `
    $vsDevCmd, $PSScriptRoot, $python
& $env:ComSpec /d /s /c $command
if ($LASTEXITCODE -ne 0) {
    throw "pybind11 extension build failed with exit code $LASTEXITCODE"
}
Write-Host "Built:" (Join-Path (Split-Path -Parent $PSScriptRoot) "src\pmxeditor\_pmx_core*.pyd")
