$paramLine = $null
param([switch]$ResetApiKey)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "JARVIS Windows launcher" -ForegroundColor Cyan
Write-Host "This launcher stores credentials in Windows Credential Manager, not in the project folder."

$Python = "py"
try {
    & $Python -3.12 --version | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Python 3.12 launcher unavailable" }
} catch {
    Write-Host "Python 3.12 is required. Install Python 3.12, then run start.ps1 again." -ForegroundColor Red
    exit 1
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    & $Python -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Could not create the virtual environment." }
}

& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not update pip." }

& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }

if ($ResetApiKey) {
    & ".\.venv\Scripts\python.exe" setup_credentials.py --reset-api-key
} else {
    & ".\.venv\Scripts\python.exe" setup_credentials.py
}
if ($LASTEXITCODE -ne 0) { throw "Credential setup failed." }

Write-Host "Opening JARVIS at http://127.0.0.1:8765" -ForegroundColor Green
Start-Process "http://127.0.0.1:8765"
& ".\.venv\Scripts\python.exe" app.py
