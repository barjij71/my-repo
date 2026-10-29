$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "This installs Chatterbox into the separate .venv-chatterbox environment." -ForegroundColor Cyan
Write-Host "The normal .venv environment remains unchanged. JARVIS will use the optional environment after installation."
Write-Host "The 3.2 GB model is not downloaded by this installer."
Write-Host "This machine has 8 GB RAM and an Intel i3 CPU; CPU synthesis may be slow or memory-heavy."
$Confirmation = Read-Host "Continue with the optional dependency installation? Type YES"
if ($Confirmation -cne "YES") {
    Write-Host "Installation cancelled."
    exit 0
}

$Python = ".\.venv-chatterbox\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    & py -3.12 -m venv .venv-chatterbox
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the isolated Chatterbox Python 3.12 environment."
    }
}

& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Could not update pip in the isolated Chatterbox environment." }

& $Python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Could not install JARVIS dependencies in the isolated Chatterbox environment." }

& $Python -m pip install --index-url https://download.pytorch.org/whl/cpu "torch==2.6.0+cpu" "torchaudio==2.6.0+cpu"
if ($LASTEXITCODE -ne 0) { throw "Could not install the CPU-only PyTorch runtime." }

& $Python -m pip install -r requirements-chatterbox.txt
if ($LASTEXITCODE -ne 0) { throw "Could not install the optional Chatterbox dependencies." }

& $Python -m pip install --no-deps "chatterbox-tts==0.1.7"
if ($LASTEXITCODE -ne 0) { throw "Could not install Chatterbox TTS." }

$VoiceDirectory = if ($env:JARVIS_VOICE_DIR) {
    $env:JARVIS_VOICE_DIR
} else {
    Join-Path $env:LOCALAPPDATA "JARVIS\voices"
}
Write-Host "Model files will be saved to: $(Join-Path $VoiceDirectory 'chatterbox-model')"
Write-Host "Optional Chatterbox dependencies installed. Restart JARVIS, then choose Chatterbox in Settings & Access." -ForegroundColor Green
