param([switch]$ResetApiKey)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "JARVIS Windows launcher" -ForegroundColor Cyan
Write-Host "This launcher stores credentials in Windows Credential Manager, not in the project folder."

$PythonEnvironment = ".venv"
if (Test-Path ".\.venv-chatterbox\Scripts\python.exe") {
    $PythonEnvironment = ".venv-chatterbox"
    Write-Host "Using the isolated Chatterbox environment." -ForegroundColor Cyan
}
$Python = Join-Path $PythonEnvironment "Scripts\python.exe"
try {
    & py -3.12 --version | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Python 3.12 launcher unavailable" }
} catch {
    Write-Host "Python 3.12 is required. Install Python 3.12, then run start.ps1 again." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $Python)) {
    & py -3.12 -m venv $PythonEnvironment
    if ($LASTEXITCODE -ne 0) { throw "Could not create the virtual environment." }
}

& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not update pip." }

& $Python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

Write-Host "Starting the JARVIS desktop window at http://127.0.0.1:8765" -ForegroundColor Green
if ($ResetApiKey) {
    & $Python jarvis_launcher.py --reset-api-key
} else {
    & $Python jarvis_launcher.py
}
if ($LASTEXITCODE -ne 0) { throw "JARVIS desktop launcher failed." }
