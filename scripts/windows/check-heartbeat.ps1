param(
    [string]$ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [int]$MaxAgeSeconds = 300
)

$ErrorActionPreference = "Stop"

$pythonExe = Join-Path $ProjectPath ".venv\Scripts\python.exe"
$scriptPath = Join-Path $ProjectPath "scripts\check_heartbeat.py"
$heartbeatPath = Join-Path $ProjectPath "data\scheduler_heartbeat.json"

if (-not (Test-Path $pythonExe)) {
    Write-Host "CRITICAL: python not found at $pythonExe"
    exit 2
}
if (-not (Test-Path $scriptPath)) {
    Write-Host "CRITICAL: check script not found at $scriptPath"
    exit 2
}

& $pythonExe $scriptPath --heartbeat-path $heartbeatPath --max-age-seconds $MaxAgeSeconds
exit $LASTEXITCODE
