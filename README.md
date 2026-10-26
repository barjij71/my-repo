# JARVIS — Windows Personal Assistant

A Windows-first personal assistant with a local FastAPI web interface and OpenAI Responses API integration.

## Status

Initial scaffold. The application does not execute operating-system commands or control the PC. Those capabilities will remain disabled until separately designed, permission-gated, and tested.

## Requirements

- Windows 10/11
- Python 3.12 (recommended)
- An OpenAI API key configured locally; never commit secrets

## Development

Create a virtual environment and install dependencies from `requirements.txt`, then configure secrets using the local setup instructions once the installer is finalized.

## Security principles

- Bind the local server to `127.0.0.1` by default.
- Never commit API keys, access tokens, or local credential files.
- Do not print secrets to the console or return provider exception details to the browser.
- Keep operating-system control and destructive actions disabled by default.
- Run automated tests before considering a change complete.
