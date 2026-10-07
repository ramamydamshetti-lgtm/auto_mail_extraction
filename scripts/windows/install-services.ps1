param(
    [Parameter(Mandatory = $true)]
    [string]$NssmPath,
    [string]$ServicePrefix = "MetaForgeEmailPipeline",
    [string]$ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $NssmPath)) {
    throw "nssm.exe not found at path: $NssmPath"
}

$venvPython = Join-Path $ProjectPath ".venv\Scripts\python.exe"
$venvCelery = Join-Path $ProjectPath ".venv\Scripts\celery.exe"

if (-not (Test-Path $venvPython)) {
    throw "Python executable not found: $venvPython"
}
if (-not (Test-Path $venvCelery)) {
    throw "Celery executable not found: $venvCelery"
}

$logsDir = Join-Path $ProjectPath "data\service-logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

$services = @(
    @{
        Name = "$ServicePrefix-Scheduler"
        App = $venvPython
        Args = "main.py scheduler"
    },
    @{
        Name = "$ServicePrefix-WorkerHighPriority"
        App = $venvCelery
        Args = "-A tasks worker --loglevel=info --queues=high_priority --hostname=high_priority@%COMPUTERNAME%"
    },
    @{
        Name = "$ServicePrefix-WorkerHeavyAI"
        App = $venvCelery
        Args = "-A tasks worker --loglevel=info --queues=heavy_ai --hostname=heavy_ai@%COMPUTERNAME%"
    },
    @{
        Name = "$ServicePrefix-WorkerIoBound"
        App = $venvCelery
        Args = "-A tasks worker --loglevel=info --queues=io_bound --hostname=io_bound@%COMPUTERNAME%"
    }
)

foreach ($svc in $services) {
    & $NssmPath remove $svc.Name confirm 2>$null | Out-Null
    & $NssmPath install $svc.Name $svc.App $svc.Args
    & $NssmPath set $svc.Name AppDirectory $ProjectPath
    & $NssmPath set $svc.Name Start SERVICE_AUTO_START
    & $NssmPath set $svc.Name AppStdout (Join-Path $logsDir "$($svc.Name).out.log")
    & $NssmPath set $svc.Name AppStderr (Join-Path $logsDir "$($svc.Name).err.log")
    & $NssmPath set $svc.Name AppRotateFiles 1
    & $NssmPath set $svc.Name AppRotateOnline 1
    & $NssmPath set $svc.Name AppRotateBytes 10485760
    & $NssmPath start $svc.Name
}

Write-Host "Installed and started services with prefix: $ServicePrefix"
