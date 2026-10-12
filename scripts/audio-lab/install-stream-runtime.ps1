$ErrorActionPreference = 'Stop'
$repository = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$release = Split-Path $repository -Parent
$root = $repository
if (Test-Path (Join-Path $release 'backend.env')) { $root = $release }
$dataRoot = Join-Path $root 'data'
if ($env:POWERFUL_TS_DATA_DIR) { $dataRoot = $env:POWERFUL_TS_DATA_DIR }
$target = Join-Path $dataRoot 'audio-lab\deep_filter.dll'
$expected = 'F97E34275EB884B6076A96D261683D2A43C6B2D97DDF9E346BC06F7C8057EB04'
New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
if (-not (Test-Path $target)) {
    Invoke-WebRequest 'https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/deep_filter_ladspa-0.5.6-x86_64-pc-windows-msvc.dll' -OutFile $target
}
if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $expected) {
    throw 'DeepFilter runtime checksum mismatch; do not start this binary.'
}
& uv pip install --python (Join-Path $dataRoot 'audio-lab\.venv\Scripts\python.exe') 'websockets==16.0'
if ($LASTEXITCODE -ne 0) { throw 'Failed to install WebSocket dependency' }
Write-Output 'Verified official DeepFilterNet v0.5.6 Windows runtime.'
