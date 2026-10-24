# Build the Bullet physics wrapper DLL with MSVC (no CMake required).
# Usage: powershell -ExecutionPolicy Bypass -File native\build.ps1
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$bullet = Join-Path $here "bullet_src\src"
if (-not (Test-Path $bullet)) { throw "Missing Bullet source at native\bullet_src\src" }

# 优先用环境变量 / vswhere 找 VS，其次才是默认安装位置：
# 本机把 BuildTools 装在 D:\Project\DevEnv\VS2022BuildTools，写死路径会直接失败。
$candidates = @()
if ($env:VSINSTALLDIR) { $candidates += $env:VSINSTALLDIR.TrimEnd("\") }
$vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
if (Test-Path $vswhere) {
    $found = & $vswhere -latest -products * -property installationPath 2>$null
    if ($found) { $candidates += $found.Trim() }
}
$candidates += @(
    "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools",
    "C:\Program Files\Microsoft Visual Studio\2022\BuildTools",
    "D:\Project\DevEnv\VS2022BuildTools"
)
$msvc = $null
foreach ($root in $candidates) {
    $tools = Join-Path $root "VC\Tools\MSVC"
    if (Test-Path $tools) {
        $msvc = Get-ChildItem $tools -Directory | Sort-Object Name -Descending | Select-Object -First 1
        if ($msvc) { Write-Host "MSVC:" $msvc.FullName; break }
    }
}
$sdkBase = "C:\Program Files (x86)\Windows Kits\10"
if ($env:WindowsSdkDir) { $sdkBase = $env:WindowsSdkDir.TrimEnd("\") }
$sdk = Get-ChildItem (Join-Path $sdkBase "Include") -Directory | Sort-Object Name -Descending | Select-Object -First 1
if (-not $msvc -or -not $sdk) { throw "MSVC or Windows SDK not found" }

$env:INCLUDE = @(
    (Join-Path $msvc.FullName "include"),
    (Join-Path $sdk.FullName "ucrt"),
    (Join-Path $sdk.FullName "um"),
    (Join-Path $sdk.FullName "shared"),
    (Join-Path $sdk.FullName "winrt")
) -join ";"
$env:LIB = @(
    (Join-Path $msvc.FullName "lib\x64"),
    (Join-Path $sdkBase "Lib\$($sdk.Name)\ucrt\x64"),
    (Join-Path $sdkBase "Lib\$($sdk.Name)\um\x64")
) -join ";"
$env:PATH = (Join-Path $msvc.FullName "bin\Hostx64\x64") + ";" +
    (Join-Path $sdkBase "bin\$($sdk.Name)\x64") + ";" + $env:PATH

$dirs = @(
    "LinearMath",
    "BulletCollision\BroadphaseCollision",
    "BulletCollision\CollisionDispatch",
    "BulletCollision\CollisionShapes",
    "BulletCollision\Gimpact",
    "BulletCollision\NarrowPhaseCollision",
    "BulletDynamics\ConstraintSolver",
    "BulletDynamics\Dynamics"
)
$sources = @()
foreach ($d in $dirs) {
    $sources += Get-ChildItem (Join-Path $bullet $d) -Filter *.cpp |
        Where-Object { $_.Name -notmatch "Mt\.cpp$" } |
        ForEach-Object { '"bullet_src\src\' + $d + '\' + $_.Name + '"' }
}
$sources += '"bullet_wrap.cpp"'
$rsp = Join-Path $here "sources.rsp"
$sources | Set-Content -Path $rsp -Encoding ascii

# 目标文件统一放进 native\obj\，避免上百个 .obj 散落在源码目录里。
$objdir = Join-Path $here "obj"
if (-not (Test-Path $objdir)) { New-Item -ItemType Directory -Path $objdir | Out-Null }
Push-Location $here
try {
    & cl.exe /nologo /LD /MP /O2 /EHsc /MD /std:c++14 /utf-8 /Foobj\ /Fdobj\ /D_CRT_SECURE_NO_WARNINGS /DNDEBUG `
        /I"bullet_src\src" /I"." "@$rsp" /Fe:bullet_phys.dll /link /OPT:REF /OPT:ICF /IMPLIB:obj\bullet_phys.lib /PDB:obj\bullet_phys.pdb
    if ($LASTEXITCODE -ne 0) { throw "cl.exe failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}
Write-Host "Built:" (Join-Path $here "bullet_phys.dll")
