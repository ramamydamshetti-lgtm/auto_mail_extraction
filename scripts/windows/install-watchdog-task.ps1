# Register Windows Task Scheduler job: keep Memurai + email pipeline healthy (every 5 min).
# Run this script once as Administrator.
param(
    [string]$ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [int]$IntervalMinutes = 5
)

$ErrorActionPreference = "Stop"
$TaskName = "MetaForge-EmailPipeline-Watchdog"
$ScriptPath = Join-Path $PSScriptRoot "ensure-email-pipeline.ps1"
$LogDir = Join-Path $ProjectPath "data\service-logs"

if (-not (Test-Path $ScriptPath)) {
    throw "Watchdog script not found: $ScriptPath"
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`" -ProjectPath `"$ProjectPath`"" `
    -WorkingDirectory $ProjectPath

# Run whether user is logged in or not; use highest privileges to start Memurai service.
$principal = New-ScheduledTaskPrincipal `
    -UserId "SYSTEM" `
    -LogonType ServiceAccount `
    -RunLevel Highest

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Keeps Memurai (Redis) running and restarts MetaForge email extraction pipeline if unhealthy." `
    -Force | Out-Null

Write-Host "Registered scheduled task: $TaskName (every $IntervalMinutes minutes, runs as SYSTEM)"
Write-Host "Watchdog log: $LogDir\watchdog.log"
Write-Host ""
Write-Host "Test now:"
Write-Host "  schtasks /Run /TN `"$TaskName`""
Write-Host ""
Write-Host "View task:"
Write-Host "  schtasks /Query /TN `"$TaskName`" /V /FO LIST"
