# Sign the release exe: dist\release\PmxEditor_Modern.exe
#
# Usage (repo root):
#   powershell -ExecutionPolicy Bypass -File tools\sign_release.ps1
#   powershell -ExecutionPolicy Bypass -File tools\sign_release.ps1 -Password "xxxx"
#
# Password resolution order: -Password parameter > PMXE_SIGN_PASSWORD env var
# > code_sign.pass file > interactive prompt.
# code_sign.pfx / code_sign.pass are listed in .gitignore; never commit them.
# NOTE: keep this file ASCII-only. Windows PowerShell 5.1 reads .ps1 files
# without BOM as ANSI and mangles non-ASCII text.
[CmdletBinding()]
param(
    [string]$ExePath = "dist\release\PmxEditor_Modern.exe",
    [string]$PfxPath = "code_sign.pfx",
    [string]$Password,
    [string]$Subject = "CN=shuyan-k",
    [switch]$TrustCert
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root $ExePath
$pfx = Join-Path $root $PfxPath
$passFile = Join-Path $root "code_sign.pass"

# ---- password ---------------------------------------------------------------
if (-not $Password) { $Password = $env:PMXE_SIGN_PASSWORD }
if (-not $Password -and (Test-Path $passFile)) {
    $Password = (Get-Content $passFile -Raw).Trim()
}
if (-not $Password) {
    $secure = Read-Host "Code-signing certificate password" -AsSecureString
    $Password = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
}

# ---- certificate: create a self-signed one when the pfx is missing ----------
if (-not (Test-Path $pfx)) {
    Write-Host "No $PfxPath found; creating self-signed code-signing certificate ($Subject)..."
    $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $Subject `
        -KeyExportPolicy Exportable -CertStoreLocation "Cert:\CurrentUser\My"
    $secure = ConvertTo-SecureString -String $Password -Force -AsPlainText
    Export-PfxCertificate -Cert $cert -FilePath $pfx -Password $secure | Out-Null
    Write-Host "Exported $PfxPath (expires $($cert.NotAfter))"
}

# ---- signtool: latest Windows Kits 10 x64 -----------------------------------
$kitsBin = "C:\Program Files (x86)\Windows Kits\10\bin"
$signtool = Get-ChildItem $kitsBin -Filter "signtool.exe" -Recurse -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -match '\\x64\\' } |
    Sort-Object { [version]($_.FullName -replace '.*\\bin\\([0-9.]+)\\.*', '$1') } -Descending |
    Select-Object -First 1 -ExpandProperty FullName
if (-not $signtool) { throw "signtool.exe not found; install the Windows 10/11 SDK" }

# ---- sign and verify ----------------------------------------------------------
if (-not (Test-Path $exe)) { throw "File to sign not found: $exe (run the Nuitka build first)" }
Write-Host "Signing $ExePath ..."
& $signtool sign /f $pfx /p $Password /fd SHA256 $exe
if ($LASTEXITCODE -ne 0) { throw "signtool sign failed, exit code $LASTEXITCODE" }

# A self-signed certificate is not trusted until its (own) root is installed
# into CurrentUser\Root. -TrustCert does that once; afterwards verify passes.
if ($TrustCert) {
    # X509Certificate2 ctor works on both PS 5.1 and 7 (Get-PfxCertificate -Password is PS6+ only)
    $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($pfx, $Password)
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store("Root", "CurrentUser")
    $store.Open("ReadWrite")
    try { $store.Add($cert) } finally { $store.Close() }
    Write-Host "Certificate installed into CurrentUser\Root (trusted on this machine)"
}

& $signtool verify /pa $exe
if ($LASTEXITCODE -ne 0) {
    $sig = Get-AuthenticodeSignature $exe
    if ($sig.Status -eq 'HashMismatch') { throw "signtool verify failed: hash mismatch" }
    Write-Warning "Signature embedded, but the self-signed root is not trusted yet."
    Write-Warning "Re-run with -TrustCert once, or install the cert into CurrentUser\Root manually."
} else {
    Write-Host "Signed and verified: $exe"
}
