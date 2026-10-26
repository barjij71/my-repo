# JARVIS — Windows Personal Assistant

A Windows-first personal assistant with a local FastAPI web interface and OpenAI Responses API integration.

## Current status

This is the initial working scaffold. It includes:
- A browser chat interface with in-memory conversation history
- A FastAPI API with bearer-token authentication
- Windows Credential Manager integration for the OpenAI API key and local access token
- Automated API tests and GitHub Actions CI for Windows and Linux
- Safe defaults: the server listens on `127.0.0.1`, and this build cannot execute commands or control Windows

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
- Operating-system control, shell execution, file modifications, and other side effects are not implemented in this scaffold.
- Do not use this starter build to run untrusted code.
