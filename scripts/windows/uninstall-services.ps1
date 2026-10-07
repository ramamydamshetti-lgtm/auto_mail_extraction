param(
    [Parameter(Mandatory = $true)]
    [string]$NssmPath,
    [string]$ServicePrefix = "MetaForgeEmailPipeline"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $NssmPath)) {
    throw "nssm.exe not found at path: $NssmPath"
}

$serviceNames = @(
    "$ServicePrefix-Scheduler",
    "$ServicePrefix-WorkerHighPriority",
    "$ServicePrefix-WorkerHeavyAI",
    "$ServicePrefix-WorkerIoBound"
)

foreach ($name in $serviceNames) {
    & $NssmPath stop $name 2>$null | Out-Null
    & $NssmPath remove $name confirm 2>$null | Out-Null
}

Write-Host "Removed services with prefix: $ServicePrefix"
