<#
.SYNOPSIS
    Standardized Mu2e control-room start script (PowerShell port of
    start-mu2edaq-dataformat-viewer.sh) for the Data Format Viewer (Qt GUI).

.DESCRIPTION
    Honors CRS_PORT_LISTEN as the default listen port (default 7755). Runs the
    viewer in the background via Start-Process with a pid file (the same file
    stop-mu2edaq-dataformat-viewer.ps1 reads).
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)][string[]]$ViewerArgs
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

if (-not $env:CRS_PORT_LISTEN) { $env:CRS_PORT_LISTEN = '7755' }
$PidFile = Join-Path $ScriptDir 'dataformat-viewer.pid'
$LogFile = Join-Path $ScriptDir 'dataformat-viewer.log'
$VenvPy = Join-Path $ScriptDir 'venv\Scripts\python.exe'
if (-not (Test-Path $VenvPy)) { $VenvPy = 'python' }

function Test-ProcessAlive([int]$ProcId) {
    return [bool](Get-Process -Id $ProcId -ErrorAction SilentlyContinue)
}
if (Test-Path $PidFile) {
    $old = (Get-Content $PidFile -Raw).Trim()
    if ($old -match '^\d+$' -and (Test-ProcessAlive ([int]$old))) {
        Write-Host "Data Format Viewer already running (PID $old)."
        exit 0
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
}

Write-Host "Starting Data Format Viewer (listen=$($env:CRS_PORT_LISTEN))"
$argList = @((Join-Path $ScriptDir 'mu2edaq-dataformat-viewer.py'))
if ($ViewerArgs) { $argList += $ViewerArgs }
$proc = Start-Process -FilePath $VenvPy -ArgumentList $argList -WorkingDirectory $ScriptDir `
    -RedirectStandardOutput $LogFile -RedirectStandardError "$LogFile.err" `
    -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 1
if (-not (Test-ProcessAlive $proc.Id)) {
    Write-Error "Data Format Viewer failed to start; see $LogFile"
    exit 1
}
Set-Content -Path $PidFile -Value $proc.Id -Encoding ascii
Write-Host "Data Format Viewer started (PID $($proc.Id)); log: $LogFile"
