# Open two Windows PowerShell consoles: backend and frontend.
# Stop them separately with Ctrl+C, or close their windows.
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run scripts\setup-windows.ps1 first.' }
if (-not (Test-Path -LiteralPath (Join-Path $root 'frontend\node_modules'))) { throw 'Run scripts\setup-windows.ps1 first.' }
if (-not (Get-Command 'ffmpeg.exe' -ErrorAction SilentlyContinue)) { throw 'ffmpeg not found on PATH.' }
if (-not (Get-Command 'ffprobe.exe' -ErrorAction SilentlyContinue)) { throw 'ffprobe not found on PATH.' }
$npm = (Get-Command 'npm.cmd' -ErrorAction Stop).Source
$env:PATH = (Join-Path $root 'backend\.venv\Scripts') + ';' + $env:PATH
# Read only simple KEY=value assignments from private files, not executable PowerShell.
foreach ($private in @('backend\.channel-monitor.env', 'backend\.youtube.env')) {
  $full = Join-Path $root $private
  if (-not (Test-Path -LiteralPath $full)) { continue }
  foreach ($line in Get-Content -LiteralPath $full) {
    if ($line -match '^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
      $key = $Matches[1]
      $value = $Matches[2].Trim()
      if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
        $value = $value.Substring(1, $value.Length - 2)
      }
      [Environment]::SetEnvironmentVariable($key, $value, 'Process')
    }
  }
}
$backendDir = Join-Path $root 'backend'
$frontendDir = Join-Path $root 'frontend'
# Single quotes in paths must be doubled in PowerShell command literals.
$escapedBackend = $backendDir.Replace("'", "''")
$escapedFrontend = $frontendDir.Replace("'", "''")
$escapedPython = $python.Replace("'", "''")
$escapedNpm = $npm.Replace("'", "''")
$backendCmd = "Set-Location -LiteralPath '$escapedBackend'; & '$escapedPython' -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
$frontendCmd = "Set-Location -LiteralPath '$escapedFrontend'; & '$escapedNpm' run dev"
foreach ($command in @($backendCmd, $frontendCmd)) {
  $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
  Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoExit', '-EncodedCommand', $encoded) | Out-Null
}
Write-Host 'Started separate backend and frontend PowerShell windows.'
Write-Host 'Open http://localhost:3000  |  API http://127.0.0.1:8000/docs'
Write-Host 'Close both service windows or press Ctrl+C in each to stop.'
