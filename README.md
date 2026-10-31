# JARVIS — Windows Personal Assistant

A Windows-first personal assistant with a local FastAPI web interface and configurable AI provider integration.

## Current status

This Windows-first project contains a local FastAPI dashboard and restricted computer-control implementation. It includes:
- A responsive Windows-first command-center dashboard with an animated assistant avatar, explicit idle/listening/thinking/speaking/error states, recent conversation, system status, and working voice/provider/history controls
- A browser chat interface with locally persisted conversation history; the latest 500 messages are stored in SQLite and can be reviewed or cleared from Tasks & Activity
- User-approved persistent fact memory stored locally in SQLite, with search/list and exact-ID forgetting; secret-looking values are rejected by basic pattern checks
- Optional push-to-talk dictation and hands-free live voice conversation use browser speech recognition, which may use an online provider. Spoken replies default to local Piper neural voices for English and Arabic. An optional Chatterbox Multilingual V3 engine supports Arabic and English with local synthesis, but requires CPU dependencies and a separate 3.2 GB model download; CPU performance and Android support are not verified. Chatterbox output is watermarked. The available Arabic voices are not dedicated Moroccan Darija voices. High-impact actions still require a separate explicit confirmation.
- A FastAPI API with bearer-token authentication
- Windows tools: open approved apps/sites and existing files/folders on available drives (C:, D:, etc.); copy plain text, commands, and paths to clipboard without executing them; stage confirmed file copies between available drives without overwriting an existing destination; inspect drives, installed apps, and RAM-heavy processes; run a dependency-free static triage on one file (SHA-256, file-type hint, and suspicious-string indicators, without execution or upload), and scan selected files/folders on demand with resource-bounded ClamAV (low process priority, PUA detection, file-count/size/recursion/timeout limits, no automatic signature update), with official ClamAV/ESET options if no scanner is found; stage moving one exact reviewed file to reversible quarantine only after explicit confirmation, verifying its SHA-256 first; stage Windows repair, app uninstall, and graceful process-close actions for explicit confirmation. File create/read/write remains limited to `Documents\\JARVISWorkspace`
- An authenticated provider manager for OpenAI, Claude/Anthropic, Gemini/Google, OpenRouter, and user-configured compatible endpoints, with bounded failover, per-provider health, timeout/retry/cooldown controls, and credential-store-only API keys
- Authenticated local CPU, memory, disk, uptime, network-adapter, and battery status. Browser-reported microphone/speaker counts do not request device permission or prove physical audio output.
- A Logs & Diagnostics dashboard page with severity filters, safe report copying, user-triggered log clearing, and actionable provider error guidance. The bounded in-memory log excludes prompts, API keys, and access tokens and is cleared when the backend restarts.
- Automated API and computer-tool tests; GitHub Actions runs on Windows and Linux
- Safe defaults: the server listens on `127.0.0.1`

## Requirements

- Windows 10 or 11
- Python 3.12 installed and available through the Windows Python Launcher (`py -3.12`)
- Microsoft Edge WebView2 Runtime
- An API key for at least one supported provider to use remote AI (OpenAI, Claude/Anthropic, Gemini/Google, or OpenRouter); provider setup is optional during first launch

## First launch

1. Open PowerShell in this project folder.
2. Run `.\start.ps1`.
3. JARVIS creates a project-local Python environment, creates a local access token in Windows Credential Manager, and opens its standalone desktop window. The desktop app loads the saved local token automatically; it is not printed or stored in browser storage.
4. If no provider key is configured, JARVIS still opens in limited mode. Open **Settings & Access → Provider Settings**, save a key for any supported provider, then select **Test Connection**. Provider testing uses a small request that may be billable. A stored OpenAI key can be replaced with `.\start.ps1 -ResetApiKey`.
5. In **Settings & Access**, download the Arabic and English Piper models once (about 127 MB) and use the preview buttons. For the optional Chatterbox engine, first run `.\install_chatterbox_voice.ps1` in PowerShell, confirm with `YES`, and restart JARVIS; then explicitly choose **Download Chatterbox V3 model (~3.2 GB)** in voice settings. Chatterbox may use several GB of RAM and may be slow on this PC. Select the engine only after its model is ready. Enable **VOICE ON** for spoken replies; **LIVE ON** starts hands-free listening and **LIVE OFF** stops it. Live listening can return text without a local speech model; offline models are needed for spoken replies. Allow microphone access when prompted. Speech recognition may send audio to the browser's provider; neural voice synthesis runs locally. Windows Settings and Sound shortcuts are available only in the desktop app and open a small allowlist of Settings pages.
6. The local backend listens only on `127.0.0.1:8765`; the user interface appears in a native WebView2 desktop window. WebView2 is required.

The launcher creates a project-local virtual environment and installs the required packages. It does not commit secrets.

## Configuration

- Add each API key in **Settings & Access → Provider Settings**. JARVIS tries the selected provider first, then automatically falls back to other configured providers on rate-limit/quota or transient connectivity errors. It honors `Retry-After` when available, applies a temporary cooldown, and automatically returns recovered providers to rotation after cooldown expiry. The UI distinguishes a saved credential from a verified connection; startup does not send a billable test request. Use **Test Connection** to verify a provider (the provider may charge for the small test request), and use **Remove saved key** to remove a credential stored by JARVIS. Environment-supplied credentials must be removed from the environment, not this screen. Each provider has its own saved model ID. Current defaults are `gpt-4.1-mini` (OpenAI), `claude-sonnet-4-6` (Claude), `gemini-2.5-flash` (Gemini), and `openrouter/auto` (OpenRouter). Model availability and account access can change; edit the model ID in the UI if needed.
- The default speech engine uses English (`en_US-lessac-medium`) and Arabic (`ar_JO-kareem-medium`) Piper neural models. JARVIS selects Arabic output when the reply contains Arabic script. The models are downloaded from the versioned Piper voice repository only after the user chooses **Download** in Settings & Access. Review each voice's model card and dataset license before use: [English model](https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0/en/en_US/lessac/medium) and [Arabic model](https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0/ar/ar_JO/kareem/medium).
- Optional Chatterbox Multilingual V3 uses the same built-in speaker conditioning for Arabic and English; no user recording or voice clone is required. The MIT-licensed model includes an audio watermark and its pinned weights require about 3.2 GB of disk space. In a source checkout, install optional CPU dependencies with `.\install_chatterbox_voice.ps1`, then download the model explicitly in Settings & Access. The portable Windows package does not bundle Chatterbox dependencies or weights. The 8 GB / Intel i3-6100U PC has not been performance-tested with this model; generation may be slow or memory-heavy. Arabic quality is not specifically verified for Moroccan Darija. The Flutter prototype still uses a mock speech engine; Android TTS runtime support is not implemented or claimed.
- `OPENAI_MODEL`: optional OpenAI model override; defaults to `gpt-4.1-mini`.
- To replace a stored OpenAI API key on the source checkout, close JARVIS and run `.\start.ps1 -ResetApiKey` in PowerShell. For the portable package, run `JARVIS.exe --reset-api-key` from its console or PowerShell, then enter the replacement key at the hidden prompt.
- `JARVIS_HOST`: bind address; defaults to `127.0.0.1`.
- `JARVIS_PORT`: local port; defaults to `8765`.

Do not expose the server to the public internet. LAN/mobile access is not enabled by default and needs separate network/firewall and authentication review.

### Provider adapters and failover

Provider metadata (adapter, endpoint, model, priority, enabled state, context limit, and retry/cooldown settings) is stored in the local JARVIS SQLite database. API keys are stored separately through Windows Credential Manager/system keyring; provider APIs and logs return only whether a key is configured, never its value. Built-in environment variables remain supported. A custom provider may use `JARVIS_PROVIDER_<PROVIDER_ID_UPPERCASE>_API_KEY`; IDs are converted to uppercase, and the key is read from the environment before the system keyring. Do not put keys in endpoints or SQLite configuration.

The authenticated **Settings & Access → Provider Settings** page can add, edit, enable/disable, prioritize, test, and remove custom providers. Supported adapters are:

- **OpenAI Responses** for the OpenAI-style Responses API. JARVIS local tools are available only on the preferred provider attempt; tool-capable adapters are never automatically retried after an ambiguous failure.
- **OpenAI-compatible Chat Completions** for endpoints that implement the OpenAI Chat Completions request/response format (including compatible hosted endpoints).
- **Anthropic Messages** for Anthropic's native Messages API.

These are explicit adapters, not universal API compatibility. Providers with different authentication, request, response, streaming, or tool-call formats need a separately implemented and tested adapter. Streaming and structured outputs are currently not implemented. Provider test requests are small but may be billable.

With automatic failover enabled, the highest-priority enabled, healthy provider is tried first, then the remaining enabled providers by priority. With it disabled, only the explicitly preferred provider is used. Connection/DNS failures, timeouts, HTTP 5xx, rate limits, quota exhaustion, and permanent request errors are classified separately; permanent errors are not retried on the same provider but can fall through to another provider. Configured transient retries are limited to connection/timeouts/server failures; rate-limit/quota responses are not immediately retried and use bounded cooldowns, honoring `Retry-After` when supplied. Quota cooldown can be disabled per provider. The maximum is five attempts and 180 seconds per request, with a default 90-second overall budget and per-provider timeout. Cooldowns and health are in memory and reset on backend restart. A provider becomes eligible again after its cooldown; recovery is not inferred from background probes.

Conversation messages are passed unchanged between providers when their configured context limits allow. When history exceeds a provider's estimated text budget, older messages are shortened/omitted first; the chat response includes `context_reduced: true` when this occurs. This is a conservative character-based estimate, not tokenizer-accurate context accounting.

The dashboard's **Cancel request** cancels the local asynchronous provider request and prevents further retries. A provider may still finish work for a request it already received; a synchronous local computer-control tool already executing may finish its current action before cancellation is handled. No tool-capable provider is automatically retried after an ambiguous failure.

## Tests

```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 -m pytest -q
```

GitHub Actions runs the test suite on Windows and Ubuntu for pushes to `main` and pull requests.

## Security principles

- Never commit API keys, access tokens, or local credential files.
- Saved memories and the latest 500 chat messages are stored in a local SQLite database and are not encrypted by JARVIS. Chat transcripts are saved only after a successful provider response and can be cleared from Tasks & Activity. Never save passwords, API keys, access tokens, authentication codes, or private keys; secret detection is heuristic, not a guarantee.
- API key and access token are stored via Windows Credential Manager.
- The local web server binds to loopback by default.
- Provider exceptions are classified into safe, actionable diagnostics before returning errors to the browser; structured rate-limit codes are used where available to distinguish quota/billing limits from request/token rate limits. OpenAI uses the Responses API and local computer tools. Compatibility providers use Chat Completions and do not invoke local computer tools in this version. Automatic failover is request-level: it retries the request with the next configured provider on rate-limit/quota and transient connection failures, tracks in-memory cooldowns, and automatically makes providers eligible again when their cooldown expires. It does not increase any provider's quota; providers must each have their own valid API key and model access. A provider with invalid credentials or an unavailable model is reported rather than treated as a rate-limit event. The Logs & Diagnostics API requires the local bearer token and never stores raw prompts, API keys, authorization headers, or raw provider error bodies.
- Arbitrary shell execution, direct command execution from the clipboard, force-killing processes, manual virus-file deletion, and arbitrary file editing outside `Documents\\JARVISWorkspace` are not enabled. Repair/uninstall/process-close actions are staged and require explicit confirmation. System repair may require launching JARVIS as Administrator. Defender scan/remediation is managed by Windows Security; review Protection history. Closing selected applications can free RAM, but there is no unsafe 'RAM cleaner' or automatic mass process killing. Reminders/tasks, general mouse/keyboard automation, screenshot understanding, and full browser automation are not implemented yet. Explicitly saved fact memories persist locally. Microphone recognition is optional, depends on browser support, and may use an online speech provider; no background listening is used. Downloaded voice models stay on the PC and are synthesized locally.
- Do not use this starter build to run untrusted code.


### Lightweight malware review and user-controlled cleanup

- ClamAV scanning is on-demand, not a continuous background service. Each scan uses below-normal process priority, limits files to 50 MB, total scan data to 250 MB, 2,000 files, recursion depth 8, and a 15-minute timeout.
- Signatures are not automatically downloaded on every scan; this avoids surprise network and CPU use. Keep ClamAV signatures updated through its trusted updater when you choose.
- Potentially unwanted application (PUA) detection may flag legitimate security-testing tools, including Metasploit components. JARVIS must explain the finding and uncertainty; a detection alone does not prove malicious intent.
- JARVIS never deletes or quarantines a detection automatically. On the user's separate explicit request, it can stage moving one exact file to `%LOCALAPPDATA%\\JARVIS\\Quarantine`, then require confirmation. It checks the file's SHA-256 again before moving it. This is reversible quarantine, not permanent deletion; folders and files under Windows/Program Files are not eligible.
- A clean scan does not guarantee a file is safe, and bounded scans may skip oversized or excess files.

- If ClamAV is not installed, the built-in static triage can still report selected suspicious strings and a SHA-256 hash without running or uploading the file. This heuristic can miss malware and can flag legitimate tools; it must never be presented as a definitive malware verdict.
