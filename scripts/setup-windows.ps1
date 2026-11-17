# OpenShorts 2.0 native Windows setup; run from any directory.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
foreach ($cmd in @('py', 'npm.cmd', 'node.exe', 'ffmpeg.exe', 'ffprobe.exe')) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    throw "Missing $cmd. Install the Windows prerequisites listed in README.md, reopen PowerShell, then retry."
  }
}
$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
  Write-Host 'Creating Python 3.12 virtual environment...'
  & py -3.12 -m venv (Join-Path $root 'backend\.venv')
  if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 not available. Install it and run: py -3.12 --version' }
}
& $python -m pip install -r (Join-Path $root 'backend\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
Push-Location (Join-Path $root 'frontend')
try {
  if (-not (Test-Path -LiteralPath 'node_modules')) {
    & npm.cmd install
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
  }
  if (-not (Test-Path -LiteralPath '.env.local')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env.local'
  }
} finally { Pop-Location }
New-Item -ItemType Directory -Force -Path (Join-Path $root 'data') | Out-Null
Write-Host 'Setup complete. Run: powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-windows.ps1'
