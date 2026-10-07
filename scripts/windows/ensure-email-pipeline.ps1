# Ensures Memurai (Redis) + email extraction pipeline are healthy.
# Safe to run repeatedly (e.g. every 5 minutes via Task Scheduler).
param(
    [string]$ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path,
    [int]$MaxHeartbeatAgeSeconds = 360,
    [switch]$ForceRestart
)

$ErrorActionPreference = "Continue"
$LogDir = Join-Path $ProjectPath "data\service-logs"
$LogFile = Join-Path $LogDir "watchdog.log"
$LockFile = Join-Path $LogDir "watchdog.lock"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Enter-WatchdogLock {
    if (Test-Path $LockFile) {
        $lockAge = (Get-Date) - (Get-Item $LockFile).LastWriteTime
        if ($lockAge.TotalMinutes -lt 10) {
            Write-WatchdogLog "SKIP: another watchdog/restart is in progress (lock age $([int]$lockAge.TotalSeconds)s)."
            exit 0
        }
        Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
    }
    Set-Content -Path $LockFile -Value $PID -Encoding ascii
}

function Exit-WatchdogLock {
    Remove-Item $LockFile -Force -ErrorAction SilentlyContinue
}

function Write-WatchdogLog {
    param([string]$Message)
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $LogFile -Value $line -Encoding utf8
}

function Test-RedisPort {
    try {
        return (Test-NetConnection -ComputerName 127.0.0.1 -Port 6379 -WarningAction SilentlyContinue).TcpTestSucceeded
    } catch {
        return $false
    }
}

function Ensure-Memurai {
    $svc = Get-Service -Name "Memurai" -ErrorAction SilentlyContinue
    if (-not $svc) {
        Write-WatchdogLog "WARN: Memurai service not installed on this server."
        return Test-RedisPort
    }
    if ($svc.StartType -ne "Automatic") {
        Write-WatchdogLog "ACTION: Setting Memurai start type to Automatic."
        Set-Service -Name "Memurai" -StartupType Automatic
    }
    # Restart Memurai automatically if it crashes (once per day reset).
    sc.exe failure Memurai reset=86400 actions=restart/60000/restart/60000/restart/60000 | Out-Null
    if ($svc.Status -ne "Running") {
        Write-WatchdogLog "ACTION: Starting Memurai (was $($svc.Status))."
        Start-Service Memurai
        Start-Sleep -Seconds 3
    }
    if (-not (Test-RedisPort)) {
        Write-WatchdogLog "CRITICAL: Redis port 6379 not reachable after Memurai start."
        return $false
    }
    return $true
}

function Get-PipelineProcesses {
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object {
            $cmd = [string]$_.CommandLine
            $cmd -and $cmd -like "*$ProjectPath*" -and (
                $cmd -like "*main.py scheduler*" -or
                ($cmd -like "*-m celery*" -and $cmd -like "* worker *")
            )
        }
}

function Get-PipelineRootProcesses {
    $all = @(Get-PipelineProcesses)
    if ($all.Count -eq 0) { return @() }

    $byPid = @{}
    foreach ($proc in $all) {
        $byPid[$proc.ProcessId] = $proc
    }

    return @($all | Where-Object {
        $parent = $byPid[$_.ParentProcessId]
        if (-not $parent) { return $true }
        $parentCmd = [string]$parent.CommandLine
        if ($_.CommandLine -like "*main.py scheduler*" -and $parentCmd -like "*main.py scheduler*") {
            return $false
        }
        if ($_.CommandLine -like "*celery*" -and $parentCmd -like "*celery*" -and $parentCmd -like "*worker*") {
            return $false
        }
        return $true
    })
}

function Get-HeartbeatState {
    $hbPath = Join-Path $ProjectPath "data\scheduler_heartbeat.json"
    if (-not (Test-Path $hbPath)) {
        return @{ Ok = $false; Reason = "heartbeat file missing" }
    }
    try {
        $data = Get-Content $hbPath -Raw | ConvertFrom-Json
        $status = [string]$data.status
        $ts = [string]$data.timestamp_utc
        if (-not $ts) {
            return @{ Ok = $false; Reason = "heartbeat timestamp missing" }
        }
        $hbTime = [DateTime]::Parse($ts, $null, [Globalization.DateTimeStyles]::RoundtripKind)
        if ($hbTime.Kind -ne [DateTimeKind]::Utc) {
            $hbTime = $hbTime.ToUniversalTime()
        }
        $age = [int](([DateTime]::UtcNow - $hbTime).TotalSeconds)
        if ($age -gt $MaxHeartbeatAgeSeconds) {
            return @{ Ok = $false; Reason = "heartbeat stale (${age}s > ${MaxHeartbeatAgeSeconds}s)"; Status = $status; Age = $age }
        }
        if ($status -eq "degraded") {
            $err = [string]$data.last_error
            return @{ Ok = $false; Reason = "heartbeat degraded: $err"; Status = $status; Age = $age }
        }
        if ($status -ne "running") {
            return @{ Ok = $false; Reason = "heartbeat status=$status"; Status = $status; Age = $age }
        }
        return @{ Ok = $true; Reason = "healthy"; Status = $status; Age = $age }
    } catch {
        return @{ Ok = $false; Reason = "heartbeat read error: $($_.Exception.Message)" }
    }
}

function Invoke-PipelineRestart {
    Write-WatchdogLog "ACTION: Restarting email pipeline."
    & (Join-Path $PSScriptRoot "restart-email-pipeline.ps1")
}

$redisOk = Ensure-Memurai
Enter-WatchdogLock
try {
    $procs = @(Get-PipelineRootProcesses)
    $schedulers = @($procs | Where-Object { $_.CommandLine -like "*main.py scheduler*" })
    $workers = @($procs | Where-Object { $_.CommandLine -like "*celery*" -and $_.CommandLine -like "*worker*" })
    $hb = Get-HeartbeatState

    $healthy = $redisOk -and
        ($schedulers.Count -eq 1) -and
        ($workers.Count -eq 3) -and
        $hb.Ok

    if ($ForceRestart) {
        Write-WatchdogLog "INFO: ForceRestart requested."
        $healthy = $false
    }

    if ($healthy) {
        Write-WatchdogLog ("OK: pipeline healthy | schedulers={0} workers={1} redis={2} heartbeat={3} age={4}s" -f `
            $schedulers.Count, $workers.Count, $redisOk, $hb.Status, $hb.Age)
        exit 0
    }

    $reasons = @()
    if (-not $redisOk) { $reasons += "redis down" }
    if ($schedulers.Count -ne 1) { $reasons += "schedulers=$($schedulers.Count) (expected 1)" }
    if ($workers.Count -ne 3) { $reasons += "workers=$($workers.Count) (expected 3)" }
    if (-not $hb.Ok) { $reasons += $hb.Reason }

    Write-WatchdogLog ("UNHEALTHY: {0}" -f ($reasons -join "; "))

    if (-not $redisOk) {
        Ensure-Memurai | Out-Null
    }

    Invoke-PipelineRestart
    Start-Sleep -Seconds 15
    $after = Get-HeartbeatState
    $procsAfter = @(Get-PipelineRootProcesses)
    $schedAfter = @($procsAfter | Where-Object { $_.CommandLine -like "*main.py scheduler*" })
    $workersAfter = @($procsAfter | Where-Object { $_.CommandLine -like "*celery*" -and $_.CommandLine -like "*worker*" })
    Write-WatchdogLog ("RECOVERY: schedulers=$($schedAfter.Count) workers=$($workersAfter.Count) heartbeatOk=$($after.Ok) reason=$($after.Reason)")
    if ($after.Ok -and (Test-RedisPort) -and ($schedAfter.Count -eq 1) -and ($workersAfter.Count -eq 3)) {
        exit 0
    }
    Write-WatchdogLog "CRITICAL: recovery incomplete; pipeline still unhealthy after restart."
    exit 1
} catch {
    Write-WatchdogLog "CRITICAL: restart failed: $($_.Exception.Message)"
    exit 2
} finally {
    Exit-WatchdogLock
}
