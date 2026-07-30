<#
.SYNOPSIS
    Set up the Python virtual environment for mu2edaq-dataformat-viewer (PyQt6
    GUI) on Windows and install/update its dependencies. PowerShell port of
    bootstrap.sh.

.PARAMETER Dev
    Also install the dev extras.
#>
[CmdletBinding()]
param(
    [switch]$Dev
)

$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Here
$Venv = Join-Path $Here 'venv'

# Prefer 'python'; fall back to the py launcher ('python3' on Windows is the
# Microsoft Store alias stub, so it is not used here).
$Python = $env:PYTHON
if (-not $Python) {
    if (Get-Command python -ErrorAction SilentlyContinue) { $Python = 'python' }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { $Python = 'py' }
    else { Write-Error 'Python 3.9+ not found on PATH. Install it first.'; exit 1 }
}

& $Python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'
if ($LASTEXITCODE -ne 0) { Write-Error 'Python 3.9 or newer is required.'; exit 1 }

if (-not (Test-Path $Venv)) { & $Python -m venv $Venv }
$VenvPy = Join-Path $Venv 'Scripts\python.exe'
& $VenvPy -m pip install --upgrade pip | Out-Null
if ($Dev) { & $VenvPy -m pip install -e '.[dev]' } else { & $VenvPy -m pip install -r requirements.txt }

Write-Host ''
Write-Host 'Bootstrap complete. Start with:  .\start-mu2edaq-dataformat-viewer.ps1'
