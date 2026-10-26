# JARVIS — Windows Personal Assistant

A Windows-first personal assistant with a local FastAPI web interface and OpenAI Responses API integration.

## Current status

The current feature branch contains a first dashboard and restricted computer-control prototype. It includes:
- A responsive sci-fi Command Center dashboard inspired by the supplied reference image, with navigation, AI-core animation, activity feed, quick commands, and session timeline
- A browser chat interface with in-memory conversation history
- A FastAPI API with bearer-token authentication
- Windows tools: open approved apps/sites and existing files/folders on available drives (C:, D:, etc.); copy plain text, commands, and paths to clipboard without executing them; stage confirmed file copies between available drives without overwriting an existing destination; inspect drives, installed apps, and RAM-heavy processes; start Microsoft Defender quick scan; stage Windows repair, app uninstall, and graceful process-close actions for explicit confirmation. File create/read/write remains limited to `Documents\\JARVISWorkspace`
- Windows Credential Manager integration for the OpenAI API key and local access token
- Authenticated local CPU, memory, disk, and uptime metrics for the dashboard
- Automated API and computer-tool tests; GitHub Actions runs on Windows and Linux
- Safe defaults: the server listens on `127.0.0.1`

## Requirements

- Windows 10 or 11
- Python 3.12 installed and available through the Windows Python Launcher (`py -3.12`)
- An OpenAI API key with access to the configured API model

## First launch

1. Open PowerShell in this project folder.
2. Run `.\start.ps1`.
3. On first launch, enter your OpenAI API key at the hidden prompt. It is saved in Windows Credential Manager, not in the repository.
4. Copy the JARVIS local access token printed by the launcher into the browser page and select **Connect**.
5. The local interface opens at http://127.0.0.1:8765.

The launcher creates a project-local virtual environment and installs the required packages. It does not commit secrets. The access token is a secret: keep it private.

## Configuration

- `OPENAI_MODEL`: model ID to use; defaults to `gpt-4.1-mini`.
- `JARVIS_HOST`: bind address; defaults to `127.0.0.1`.
- `JARVIS_PORT`: local port; defaults to `8765`.

Do not expose the server to the public internet. LAN/mobile access is not enabled by default and needs separate network/firewall and authentication review.

## Tests

```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 -m pytest -q
```

GitHub Actions runs the test suite on Windows and Ubuntu for pushes to `main` and pull requests.

## Security principles

- Never commit API keys, access tokens, or local credential files.
- API key and access token are stored via Windows Credential Manager.
- The local web server binds to loopback by default.
- Provider exceptions are sanitized before returning errors to the browser.
- Arbitrary shell execution, direct command execution from the clipboard, force-killing processes, manual virus-file deletion, and arbitrary file editing outside `Documents\\JARVISWorkspace` are not enabled. Repair/uninstall/process-close actions are staged and require explicit confirmation. System repair may require launching JARVIS as Administrator. Defender scan/remediation is managed by Windows Security; review Protection history. Closing selected applications can free RAM, but there is no unsafe 'RAM cleaner' or automatic mass process killing. Voice capture, durable memory, general mouse/keyboard automation, screenshot capture, and full browser automation are not implemented yet.
- Do not use this starter build to run untrusted code.
