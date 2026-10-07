# Register Windows Task Scheduler job: Continuous Accuracy Monitor for MetaForge Email Pipeline.
# Audits extraction accuracy of recent production records against baseline and raises Phase 4 alerts on degradation.
# Run this script once as Administrator.
param(
    [string]$ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [int]$IntervalMinutes = 60,
    [int]$SampleSize = 30
)

$ErrorActionPreference = "Stop"
$TaskName = "MetaForge-EmailPipeline-AccuracyMonitor"
$LogDir = Join-Path $ProjectPath "data\service-logs"
$LogFile = Join-Path $LogDir "accuracy_monitor.log"

$venvPython = Join-Path $ProjectPath ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    # Fallback to system python
    $venvPython = "python.exe"
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$scriptArgs = "-Command `"& '$venvPython' (Join-Path '$ProjectPath' 'accuracy_monitor.py') --limit $SampleSize *>> (Join-Path '$ProjectPath' 'data\service-logs\accuracy_monitor.log')`""

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass $scriptArgs" `
    -WorkingDirectory $ProjectPath

$isElevated = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isElevated) {
    $principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
} else {
    $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
}

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Continuous Accuracy Monitoring: evaluates recent production email extractions against verified baseline and alerts on degradation." `
    -Force | Out-Null

Write-Host "Registered scheduled task: $TaskName (every $IntervalMinutes minutes, sample size $SampleSize, runs as SYSTEM)"
Write-Host "Accuracy Monitor log: $LogFile"
Write-Host ""
Write-Host "Test now:"
Write-Host "  schtasks /Run /TN `"$TaskName`""
Write-Host ""
Write-Host "View task:"
Write-Host "  schtasks /Query /TN `"$TaskName`" /V /FO LIST"
