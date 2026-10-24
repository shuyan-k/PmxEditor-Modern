# Builds a self-contained "minimal" CPython for this project into build\python.
# Usage: powershell -ExecutionPolicy Bypass -File tools\make_portable_python.ps1 [-Source <python.exe>] [-Dest build\python]
param(
    [string]$Source = "",
    [string]$Dest = "build\python"
)
$ErrorActionPreference = "Stop"
function Find-SourcePython {
    param([string]$Explicit)
    if ($Explicit) { return (Resolve-Path $Explicit).Path }
    $cand = @(
        "D:\APP\Python\python.exe",
        "C:\Python310\python.exe",
        (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -First 1).Source
    ) | Where-Object { $_ -and (Test-Path $_) }
    if (-not $cand) { throw "no python.exe found; pass -Source <path>" }
    return $cand[0]
}
$srcExe = Find-SourcePython -Explicit $Source
$srcRoot = Split-Path -Parent $srcExe
$ver = & $srcExe -c "import sys;print('%d.%d'%sys.version_info[:2])"
if ($ver -ne "3.10") { throw "need CPython 3.10 (native core is cp310), got $ver" }
if (Test-Path $Dest) { Remove-Item $Dest -Recurse -Force }
New-Item -ItemType Directory -Force $Dest | Out-Null
Write-Host "source : $srcRoot ($ver)"
Write-Host "dest   : $Dest"
# 1) interpreter + runtime dlls
foreach ($f in @("python.exe","pythonw.exe","python3.dll","python310.dll","vcruntime140.dll","vcruntime140_1.dll","LICENSE.txt")) {
    Copy-Item (Join-Path $srcRoot $f) $Dest -Force
}
# 2) stdlib without the heavy/unused parts
# distutils 不能裁：Nuitka 的 anti-bloat 会 import numpy.distutils.misc_util。
$skipDirs = @("test","tests","idlelib","ensurepip","tkinter","turtledemo","lib2to3","venv","site-packages","__pycache__","Tools","tcl")
& robocopy (Join-Path $srcRoot "Lib") (Join-Path $Dest "Lib") /E /NFL /NDL /NJH /NJS /NP /XD @skipDirs /XF *.pyc | Out-Null
& robocopy (Join-Path $srcRoot "DLLs") (Join-Path $Dest "DLLs") /E /NFL /NDL /NJH /NJS /NP | Out-Null
foreach ($d in @("include","libs")) {
    if (Test-Path (Join-Path $srcRoot $d)) {
        & robocopy (Join-Path $srcRoot $d) (Join-Path $Dest $d) /E /NFL /NDL /NJH /NJS /NP | Out-Null
    }
}
# 3) only the packages this project needs (+ their metadata)
$sp = Join-Path $Dest "Lib\site-packages"
New-Item -ItemType Directory -Force $sp | Out-Null
$srcSp = Join-Path $srcRoot "Lib\site-packages"
$pkgs = @("PyQt5","OpenGL","numpy","pybind11","setuptools","pkg_resources","_distutils_hack","pip",
          "PyQt5-*.dist-info","PyQt5_Qt5-*.dist-info","pyqt5_sip-*.dist-info","pyopengl-*.dist-info",
          "numpy-*.dist-info","pybind11-*.dist-info","setuptools-*.dist-info","pip-*.dist-info")
foreach ($p in $pkgs) {
    $items = @(Get-Item -Path (Join-Path $srcSp $p) -ErrorAction SilentlyContinue)
    foreach ($it in $items) {
        $target = Join-Path $sp $it.Name
        Copy-Item -LiteralPath $it.FullName -Destination $target -Recurse -Force
        Write-Host ("  + " + $it.Name)
    }
}
# 4) trim obvious ballast (tests, translations, type stubs)
Get-ChildItem -Path $sp -Recurse -Directory -Filter "tests" -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
foreach ($t in @("PyQt5\Qt5\translations","PyQt5\Qt5\qml","OpenGL\arrays\..\tests")) {
    $q = Join-Path $sp $t
    if (Test-Path $q) { Remove-Item $q -Recurse -Force }
}
Get-ChildItem -Path $sp -Recurse -Include "*.pyi","*.pdb" -File -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue
# 5) 打包工具也放进便携环境，保证"编译环境只依赖 build\python"
$py = Join-Path $Dest "python.exe"
& $py -m pip install --no-warn-script-location --disable-pip-version-check -q "nuitka==4.3.1" "zstandard"
$size = (Get-ChildItem $Dest -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("done   : {0:N1} MB" -f $size)
& (Join-Path $Dest "python.exe") -c "import sys,numpy,OpenGL.GL,PyQt5.QtWidgets;print('verify :',sys.version.split()[0],'numpy',numpy.__version__,'Qt',PyQt5.QtCore.QT_VERSION_STR)"
