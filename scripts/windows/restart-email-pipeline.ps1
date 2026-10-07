# Restart email extraction scheduler + Celery workers (Windows, solo pool).
$ErrorActionPreference = "Stop"
$ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$venvPython = Join-Path $ProjectPath ".venv\Scripts\python.exe"
$logsDir = Join-Path $ProjectPath "data\service-logs"
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

if (-not (Test-Path $venvPython)) {
    throw "Python executable not found: $venvPython"
}

function Stop-PipelineProcesses {
    $venvPython = Join-Path $ProjectPath ".venv\Scripts\python.exe"
    $venvPythonLower = $venvPython.ToLowerInvariant()

    for ($attempt = 1; $attempt -le 6; $attempt++) {
        $targets = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
            Where-Object {
                $cmd = [string]$_.CommandLine
                if (-not $cmd) { return $false }
                $exe = ([string]$_.ExecutablePath).ToLowerInvariant()
                $inProject = ($exe -eq $venvPythonLower) -or ($cmd -like "*$ProjectPath*")
                if (-not $inProject) { return $false }
                return (
                    $cmd -like "*main.py scheduler*" -or
                    ($cmd -like "*-m celery*" -and $cmd -like "* worker *")
                )
            }

        if ($targets.Count -eq 0) {
            return
        }

        foreach ($proc in $targets) {
            Write-Host "Stopping PID $($proc.ProcessId)"
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 2
    }

    $remaining = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object {
            $cmd = [string]$_.CommandLine
            $cmd -and $cmd -like "*$ProjectPath*" -and (
                $cmd -like "*main.py scheduler*" -or
                ($cmd -like "*-m celery*" -and $cmd -like "* worker *")
            )
        })
    if ($remaining.Count -gt 0) {
        throw "Failed to stop $($remaining.Count) pipeline process(es): $($remaining.ProcessId -join ', ')"
    }
}

Stop-PipelineProcesses

$env:CELERY_BROKER_URL = "redis://localhost:6379/0"
$env:CELERY_RESULT_BACKEND = "redis://localhost:6379/0"

# Use `python -m celery` — celery.exe fails silently on this host.
$starts = @(
    @{
        Name = "scheduler"
        Args = @("main.py", "scheduler")
        Out = Join-Path $logsDir "scheduler.out.log"
        Err = Join-Path $logsDir "scheduler.err.log"
    },
    @{
        Name = "worker-high"
        Args = @("-m", "celery", "-A", "tasks", "worker", "-l", "info", "-P", "solo", "-c", "1", "-Q", "high_priority", "-n", "high_priority@SERVER")
        Out = Join-Path $logsDir "worker-high.out.log"
        Err = Join-Path $logsDir "worker-high.err.log"
    },
    @{
        Name = "worker-heavy"
        Args = @("-m", "celery", "-A", "tasks", "worker", "-l", "info", "-P", "solo", "-c", "1", "-Q", "heavy_ai", "-n", "heavy_ai@SERVER")
        Out = Join-Path $logsDir "worker-heavy.out.log"
        Err = Join-Path $logsDir "worker-heavy.err.log"
    },
    @{
        Name = "worker-io"
        Args = @("-m", "celery", "-A", "tasks", "worker", "-l", "info", "-P", "solo", "-c", "1", "-Q", "io_bound", "-n", "io_bound@SERVER")
        Out = Join-Path $logsDir "worker-io.out.log"
        Err = Join-Path $logsDir "worker-io.err.log"
    }
)

foreach ($svc in $starts) {
    Write-Host "Starting $($svc.Name) ..."
    # Truncate logs so a restart is easy to spot
    Set-Content -Path $svc.Out -Value "" -Encoding utf8
    Set-Content -Path $svc.Err -Value "" -Encoding utf8
    Start-Process -FilePath $venvPython `
        -ArgumentList $svc.Args `
        -WorkingDirectory $ProjectPath `
        -RedirectStandardOutput $svc.Out `
        -RedirectStandardError $svc.Err `
        -WindowStyle Hidden
}

Write-Host "Email pipeline restarted from $ProjectPath"
