# Build the pybind11 compute backend with the configured Visual Studio toolchain.
# Usage: powershell -ExecutionPolicy Bypass -File native\build_core.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$vsRoot = "D:\Project\DevEnv\VS2022BuildTools"
$vsDevCmd = Join-Path $vsRoot "Common7\Tools\VsDevCmd.bat"
if (-not (Test-Path $vsDevCmd)) {
    throw "Visual Studio Build Tools not found at $vsRoot"
}
if (-not (Test-Path (Join-Path $PSScriptRoot "bullet_phys.lib"))) {
    throw "Missing native\bullet_phys.lib; build Bullet first."
}

$python = (Get-Command python.exe -ErrorAction Stop).Source
$command = 'call "{0}" -no_logo -arch=amd64 -host_arch=amd64 && cd /d "{1}" && "{2}" setup_core.py build_ext --inplace' -f `
    $vsDevCmd, $root, $python
& $env:ComSpec /d /s /c $command
if ($LASTEXITCODE -ne 0) {
    throw "pybind11 extension build failed with exit code $LASTEXITCODE"
}
Write-Host "Built:" (Join-Path $root "_pmx_core*.pyd")
