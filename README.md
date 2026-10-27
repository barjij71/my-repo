# JARVIS — Windows Personal Assistant

A Windows-first personal assistant with a local FastAPI web interface and configurable AI provider integration.

## Current status

The main branch contains the initial Windows dashboard and restricted computer-control implementation. It includes:
- A responsive sci-fi Command Center dashboard inspired by the supplied reference image, with navigation, AI-core animation, activity feed, quick commands, and session timeline
- A browser chat interface with in-memory conversation history
- User-approved persistent fact memory stored locally in SQLite, with search/list and exact-ID forgetting; secret-looking values are rejected by basic pattern checks
- Optional push-to-talk dictation, spoken replies, and hands-free live voice conversation using browser speech APIs. Live mode is explicitly started/stopped by the user, automatically submits recognized speech, and speaks replies; browser speech recognition may use an online provider. High-impact actions still require a separate explicit confirmation.
- A FastAPI API with bearer-token authentication
- Windows tools: open approved apps/sites and existing files/folders on available drives (C:, D:, etc.); copy plain text, commands, and paths to clipboard without executing them; stage confirmed file copies between available drives without overwriting an existing destination; inspect drives, installed apps, and RAM-heavy processes; run a dependency-free static triage on one file (SHA-256, file-type hint, and suspicious-string indicators, without execution or upload), and scan selected files/folders on demand with resource-bounded ClamAV (low process priority, PUA detection, file-count/size/recursion/timeout limits, no automatic signature update), with official ClamAV/ESET options if no scanner is found; stage moving one exact reviewed file to reversible quarantine only after explicit confirmation, verifying its SHA-256 first; stage Windows repair, app uninstall, and graceful process-close actions for explicit confirmation. File create/read/write remains limited to `Documents\\JARVISWorkspace`
- Provider Settings for OpenAI, Grok/xAI, Claude/Anthropic, Gemini/Google, and OpenRouter, with a safe connection test; API keys are stored in Windows Credential Manager/system keyring and never returned to the browser
- Authenticated local CPU, memory, disk, and uptime metrics for the dashboard
- A Logs & Diagnostics dashboard page with severity filters, safe report copying, user-triggered log clearing, and actionable provider error guidance. The bounded in-memory log excludes prompts, API keys, and access tokens and is cleared when the backend restarts.
- Automated API and computer-tool tests; GitHub Actions runs on Windows and Linux
- Safe defaults: the server listens on `127.0.0.1`

## Requirements

- Windows 10 or 11
- Python 3.12 installed and available through the Windows Python Launcher (`py -3.12`)
- An API key for at least one supported provider (OpenAI, Grok/xAI, Claude/Anthropic, Gemini/Google, or OpenRouter)

## First launch

1. Open PowerShell in this project folder.
2. Run `.\start.ps1`.
3. On first launch, enter your OpenAI API key at the hidden prompt. It is saved in Windows Credential Manager, not in the repository. If OpenAI reports `AuthenticationError`, create a valid API key in your OpenAI Platform account, close JARVIS, then run `.\start.ps1 -ResetApiKey` and enter the replacement key at the hidden prompt.
4. Copy the JARVIS local access token printed by the launcher into the browser page and select **Connect**.
5. To chat hands-free, select **LIVE OFF** once to turn on live conversation, then allow microphone access in the browser. JARVIS automatically sends recognized speech and speaks replies. Select **LIVE ON** to stop. Browser speech recognition may send audio to its provider; use this mode only if comfortable with that privacy trade-off.
6. The local interface opens at http://127.0.0.1:8765.

The launcher creates a project-local virtual environment and installs the required packages. It does not commit secrets. The access token is a secret: keep it private.

## Configuration

- Provider and model are selected in **Settings & Access → Provider Settings**. Current defaults are `gpt-4.1-mini` (OpenAI), `grok-4.6` (Grok), `claude-sonnet-4-6` (Claude), `gemini-2.5-flash` (Gemini), and `openrouter/auto` (OpenRouter). Model availability and account access can change; edit the model ID in the UI if needed.\n- `OPENAI_MODEL`: optional OpenAI model override; defaults to `gpt-4.1-mini`.
- To replace a stored OpenAI API key on the source checkout, close JARVIS and run `.\start.ps1 -ResetApiKey` in PowerShell. For the portable package, run `JARVIS.exe --reset-api-key` from its console or PowerShell, then enter the replacement key at the hidden prompt.
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
- Saved memories are stored in a local SQLite database and are not encrypted by JARVIS; never save passwords, API keys, access tokens, authentication codes, or private keys. Secret detection is heuristic, not a guarantee.
- API key and access token are stored via Windows Credential Manager.
- The local web server binds to loopback by default.
- Provider exceptions are classified into safe, actionable diagnostics before returning errors to the browser; structured rate-limit codes are used where available to distinguish quota/billing limits from request/token rate limits. OpenAI uses the Responses API and local computer tools. Compatibility providers use Chat Completions and do not invoke local computer tools in this version. The Logs & Diagnostics API requires the local bearer token and never stores raw prompts, API keys, authorization headers, or raw provider error bodies.
- Arbitrary shell execution, direct command execution from the clipboard, force-killing processes, manual virus-file deletion, and arbitrary file editing outside `Documents\\JARVISWorkspace` are not enabled. Repair/uninstall/process-close actions are staged and require explicit confirmation. System repair may require launching JARVIS as Administrator. Defender scan/remediation is managed by Windows Security; review Protection history. Closing selected applications can free RAM, but there is no unsafe 'RAM cleaner' or automatic mass process killing. Persistent chat transcript/history, reminders/tasks, general mouse/keyboard automation, screenshot understanding, and full browser automation are not implemented yet. Explicitly saved fact memories persist locally. Voice input/output is optional and depends on browser support; no background listening is used.
- Do not use this starter build to run untrusted code.


### Lightweight malware review and user-controlled cleanup

- ClamAV scanning is on-demand, not a continuous background service. Each scan uses below-normal process priority, limits files to 50 MB, total scan data to 250 MB, 2,000 files, recursion depth 8, and a 15-minute timeout.
- Signatures are not automatically downloaded on every scan; this avoids surprise network and CPU use. Keep ClamAV signatures updated through its trusted updater when you choose.
- Potentially unwanted application (PUA) detection may flag legitimate security-testing tools, including Metasploit components. JARVIS must explain the finding and uncertainty; a detection alone does not prove malicious intent.
- JARVIS never deletes or quarantines a detection automatically. On the user's separate explicit request, it can stage moving one exact file to `%LOCALAPPDATA%\\JARVIS\\Quarantine`, then require confirmation. It checks the file's SHA-256 again before moving it. This is reversible quarantine, not permanent deletion; folders and files under Windows/Program Files are not eligible.
- A clean scan does not guarantee a file is safe, and bounded scans may skip oversized or excess files.

- If ClamAV is not installed, the built-in static triage can still report selected suspicious strings and a SHA-256 hash without running or uploading the file. This heuristic can miss malware and can flag legitimate tools; it must never be presented as a definitive malware verdict.
