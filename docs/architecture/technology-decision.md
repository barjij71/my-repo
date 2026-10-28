# JARVIS technology decision

- **Status:** Flutter + shared Dart core approved as the production direction; platform validation and detailed feature decisions remain open.
- **Prepared:** 2026-10-28
- **Decision scope:** A shared JARVIS assistant for Windows and Android, with local data and permission-controlled device capabilities.

## 1. Verified requirements and constraints

| Area | Evidence |
|---|---|
| Repository | Public GitHub repository `barjij71/my-repo`; current working branch is `barjij71-jarvis-for-windows`. The worktree already contains unrelated, uncommitted JARVIS changes; those must not be included in this decision-record commit. |
| GitHub Actions | Actions are enabled. Existing Python tests run on Windows and Ubuntu, and a recent run succeeded. A Windows package workflow also exists. The GitHub token has repository and workflow scopes. |
| Copilot Coding Agent | **Unknown.** The token has a `copilot` scope, which does not establish that Coding Agent is enabled for this repository. Smallest check: inspect the repository's Copilot coding agent settings in GitHub or attempt a repository-scoped agent task. |
| Development host | Windows 11 Pro x64, build 26200. Python 3.12 and JDK 21 are available. Android platform-tools (`adb`) are present, but no Flutter SDK, .NET SDK, Android SDK, emulator, or attached Android device was found. |
| Current application | Python 3.12/FastAPI API, single-file HTML/JavaScript dashboard, SQLite history and memory, Windows Credential Manager/keyring, restricted Windows tools, and a PyInstaller/WebView2 desktop launcher. There is no Android app. |
| Android target | User specified Android 16 as the oldest supported version. Use API 36 as the production minimum and initial target; physical-device verification remains outstanding. |
| Offline behavior | Existing local SQLite history/memory and downloadable Piper English/Jordanian-Arabic TTS work offline. AI chat uses a remote provider; browser speech recognition may use an online service. No offline Arabic/Darija ASR or Moroccan-Darija voice has been verified. |
| Budget | No budget ceiling or paid-service approval is known. The prototype must use mocked AI and speech so it needs no provider credentials and causes no usage charges. |
| Device access | User requests broad Windows and Android capabilities, and has approved user-granted permissions with confirmation for sensitive actions. This means normal OS permissions and APIs, not bypassing Android sandboxing, Windows UAC, or other OS security boundaries. |
| Distribution | Windows currently uses a portable, unsigned PyInstaller build. Android distribution channel, signing ownership, update policy, privacy policy, and public-release/licensing obligations are unknown. |

## 2. Unknowns and resolution

| Unknown | Smallest resolution |
|---|---|
| Copilot Coding Agent enablement | Check the repository's GitHub Copilot settings; the local token scope is not proof of repository entitlement. |
| Device-specific permissions and hardware | No Android device is attached to ADB. Run the prototype on the user's Android 16 device before claiming microphone, audio-focus, background, or native-permission behavior works there. |
| Offline speech requirements | Keep ASR and TTS behind replaceable interfaces. Select real engines only after Arabic, Moroccan Darija, English quality, on-device performance, license, and download-size tests. |
| Budget and service policy | Keep the prototype mocked. Production provider selection and any recurring or per-request cost require an explicit budget and privacy review. |
| Distribution/signing | Decide Windows signing, Android signing-key ownership, store/sideload distribution, and update mechanism before release engineering. |

## 3. Candidate comparison

Scores are 1 (poor) to 5 (strong), based on the verified requirements and current platform documentation. They are comparative engineering judgments, not benchmark results. Criteria that frameworks cannot guarantee—especially Darija recognition and voice quality—are deliberately scored conservatively. The weighted score emphasizes shared implementation, Arabic-capable UI, reliable audio lifecycle, safe native integration, and testability; it does not replace the proof of concept.

| Criterion | Weight | A. Flutter + native integrations | B. .NET MAUI | C. Shared web UI + native shells | D. Separate native apps + shared API/core |
|---|---:|---:|---:|---:|---:|
| Windows desktop support | 1 | 5 | 5 | 4 | 5 |
| Android support | 1 | 5 | 5 | 4 | 5 |
| Shared code and maintenance | 3.5 | 4 | 4 | 3 | 2 |
| UI quality and accessibility | 1 | 4 | 4 | 3 | 5 |
| Arabic RTL / English LTR | 1.5 | 4 | 3 | 4 | 4 |
| Arabic, Darija, and English ASR integration | 1 | 3 | 3 | 3 | 4 |
| TTS quality and voice consistency | 1.5 | 3 | 3 | 3 | 4 |
| Audio ownership and concurrency | 2 | 4 | 3 | 2 | 5 |
| Offline/local model support | 1.5 | 4 | 3 | 2 | 5 |
| Safe native system integrations | 1.5 | 4 | 4 | 3 | 5 |
| Android permission/background behavior | 1 | 3 | 3 | 2 | 5 |
| Secure credential storage | 1 | 4 | 4 | 3 | 5 |
| Persistent local memory / optional sync | 1 | 4 | 4 | 3 | 4 |
| GitHub Actions and reproducible builds | 1.5 | 4 | 4 | 4 | 3 |
| Copilot compatibility and automated testing | 1.5 | 5 | 4 | 5 | 3 |
| Dependency size, installation, licensing | 1 | 3 | 2 | 4 | 2 |
| Independence from paid services | 1 | 4 | 4 | 3 | 4 |
| **Weighted result (out of 5)** |  | **3.96** | **3.64** | **3.19** | **3.91** |

The small numerical lead for Option D reflects native capability, not total project fit. Option D carries substantial duplicated-UI and maintenance cost, contrary to the primary shared Windows/Android requirement. Option A is therefore the recommended prototype candidate; its speech, native-access, and build assumptions must be tested before it becomes the production decision.

### Candidate notes

- **A — Flutter:** One UI and Dart domain layer for Windows and Android; platform channels/plugins isolate Windows and Android APIs. Best fit for shared interaction and RTL/LTR layout. It does not itself provide reliable Arabic/Darija ASR or a consistent offline voice; those remain engine choices behind interfaces.
- **B — .NET MAUI:** Credible Windows/Android option with mature native access and C# tests. It is viable, but the verified host has no .NET SDK, the current project is Python, and the shared speech/audio ecosystem still needs qualification.
- **C — Web UI and native shells:** Maximizes reuse of the current HTML dashboard and keeps the existing Windows FastAPI implementation. Android requires a separate shell and a deliberate local/remote backend and authentication design; WebView lifecycle and audio ownership make broad, reliable native automation harder.
- **D — Separate native apps:** Strongest access to each OS and best platform-specific UX, but duplicates most screens, lifecycle behavior, and test surface. Sharing only API contracts does not satisfy the maintenance goal as well as a shared client.

## 4. Provisional architecture

**Recommendation for the proof of concept: Flutter UI plus a shared Dart core, with explicit platform adapters.** Run the conversation client and local memory on each device; do not require a self-hosted remote server for basic UI, local history, or settings. AI-provider calls may use configured remote HTTPS APIs. Cross-device memory sync is out of scope until separately designed and approved.

Proposed boundaries:

- **Flutter UI:** Adaptive desktop/mobile navigation, accessible controls, explicit RTL/LTR direction, and a single conversation/audio state owner.
- **Shared Dart domain:** Conversation models, provider selection contracts, language and direction metadata, local-memory contracts, and a cancellable audio state machine.
- **Provider port:** Mock provider for tests; production HTTPS provider adapters are separate and must keep credentials out of UI state, logs, and synchronization.
- **Speech ports:** `SpeechRecognizer` and `SpeechSynthesizer` interfaces with explicit start/stop/cancel/status behavior. A mock engine is sufficient for the prototype. No claim is made yet about offline ASR, Darija quality, or a common voice across platforms.
- **Platform capability port:** Allowlisted operations implemented separately for Windows and Android. Each operation declares required permissions, impact level, and confirmation policy. Unsupported operations return an explicit unsupported result.
- **Windows adapter:** Use ordinary user permissions by default. Any elevated operation must be narrowly scoped, separately launched, and confirmed; never expose arbitrary shell execution as an assistant tool.
- **Android adapter:** Use Android's documented permissions and storage providers. Accessibility-service or special permissions, if ever proposed, require separate disclosure and opt-in. Respect app sandboxing, foreground-service, battery, and background-start restrictions; no hidden or persistent surveillance.
- **Persistence:** One local SQLite database per device with schema-versioned migrations. Store credentials in Windows Credential Manager and Android Keystore-backed storage through maintained platform adapters. Encryption and sync are separate design decisions.
- **Testing:** Dart unit and widget tests, platform-adapter tests with mocks, and device integration checks. GitHub Actions should analyze/test on Ubuntu and build Windows on `windows-latest` and Android on an Android-SDK-enabled hosted runner.
- **Legacy migration:** Keep the current Python app working while the isolated prototype proves the new direction. Do not mix the existing uncommitted desktop changes into the architecture-record commit or prototype commit.

### Proposed repository layout

```text
apps/
  jarvis_flutter/          # Windows and Android Flutter shell
packages/
  jarvis_core/             # Shared Dart domain, ports, and test fakes
  jarvis_platform/         # Narrow Windows/Android platform adapters
docs/
  architecture/
    technology-decision.md
```

The proof of concept may keep this layout under `prototype/` if needed to avoid changing the existing application's entry points.

## 5. Risks and mitigations

| Risk | Mitigation |
|---|---|
| "Full access" could be interpreted as bypassing OS security | Treat it only as broad capability coverage through normal, user-granted permissions. Preserve UAC, Android sandboxing, explicit confirmations, an allowlist, and auditable actions. |
| Darija speech quality is not guaranteed by any UI framework | Mock speech in the prototype; run a separately consented, human-evaluated engine bake-off using Moroccan Arabic and English before promising speech support. |
| Android ASR may use remote services or have device/vendor-specific behavior | Ask for consent before microphone use, label online processing, expose cancellation, and test supported on-device engines on physical devices. Android's generic `SpeechRecognizer` may stream audio remotely and is not intended for continuous recognition. |
| Background voice consumes battery and is restricted by Android | Keep voice foreground/user-triggered initially; use platform-recommended background APIs only for a separately approved use case. |
| Flutter native plugins may not cover the required Windows controls | Prototype only harmless app/system metadata capabilities first; add narrow native plugins only after an operation-by-operation threat and permissions review. |
| Existing Python app has substantial behavior and local data | Keep it intact during the POC; specify an export/import and migration plan before any replacement. |
| Dependency, model, and app-store licensing | Track licenses for Flutter plugins, inference runtimes, and each voice/model separately before distribution. |
| Secrets or private data could leak through AI calls or sync | Mock provider in POC; production adapters require explicit data-flow disclosure, redaction, secure storage, and no default cloud memory sync. |
| No local Android SDK/device is available | Bootstrap reproducible CI builds, then validate runtime permissions/audio on the user's Android 16 device before declaring the platform verified. |

## 6. Build tools and CI

- **Local Flutter prototype:** Flutter stable SDK, Dart SDK supplied by Flutter, Android SDK command-line tools/platform SDK 36, JDK 21, and Windows desktop prerequisites (Visual Studio Build Tools with the C++ desktop workload and Windows SDK). Flutter is not installed on the current host; .NET MAUI tools are also absent.
- **Android validation:** GitHub-hosted Ubuntu runner with Java 21 and Android SDK packages; a physical Android 16 device is required for hardware, permission, and audio validation. `adb` alone is present locally but no Android SDK/emulator/device was detected.
- **Windows validation:** `windows-latest` runner for `flutter build windows`; Windows app installation/signing is not part of the proof of concept.
- **CI checks:** `flutter analyze`, `flutter test`, Windows build, and Android APK build. Do not place API keys or personal device data in CI. An emulator test is optional and cannot replace physical-device testing.
- **GitHub:** Actions are enabled and previous tests succeeded. Repository-specific Copilot Coding Agent availability remains unverified.

## 7. Minimal proof-of-concept plan

1. Add an isolated Flutter prototype and shared Dart core without replacing or editing the existing Python application.
2. Demonstrate Windows desktop launch and a reproducible Android API 36 build; use API 29 only as a provisional minimum for the prototype, not a product promise.
3. Implement a chat screen with English LTR and Arabic RTL switching, plus a local mock AI provider that requires no secrets or network.
4. Implement a controllable mock speech engine with start/stop/cancel and a test proving a second playback cannot overlap the first.
5. Add unit/widget tests for language direction, mock responses, cancellation, and unsupported platform operations.
6. Add a dedicated GitHub Actions workflow for analysis/tests and Windows/Android builds; push only the isolated TDR/prototype commits to the feature branch and inspect the resulting run.
7. Only after those checks, revisit the weighted comparison and record test results and limitations. Android API 36 is the production minimum; the prototype's API 29 floor is only a build setting and does not change that requirement.

### Proof-of-concept acceptance criteria

- `flutter analyze` and automated tests pass without provider credentials.
- Windows desktop build completes and launches to the mock chat screen.
- Android APK build completes with API 36 compile target and runs on an Android 16 device or emulator if one becomes available.
- The same shared-core tests and mock provider run for both platforms.
- English displays LTR and Arabic displays RTL without corrupting mixed-direction text.
- Mock audio can be started, stopped, and cancelled; automated tests prove overlapping playback is rejected/cancelled deterministically.
- CI reports a successful run for the prototype commit.
- The result explicitly labels actual speech recognition, real TTS quality, physical-device behavior, production credentials, and system control as unverified.

## 8. Proof-of-concept results

Verified on 2026-10-28:

- **GitHub commit:** `c825e5c4d84acec43f0deac3d12015a5b0e6b9c9` (`Add JARVIS technology proof of concept`).
- **GitHub Actions:** both `verify-and-build-android` and `build-windows` succeeded on the prototype commit: https://github.com/barjij71/my-repo/actions/runs/40604964896
- **Flutter checks:** `flutter analyze` reported no issues; all four tests passed locally and in CI. Tests cover English/Arabic direction, mock responses, unsupported device-control reporting, and speech overlap/cancellation.
- **Windows:** the GitHub-built Windows artifact was downloaded and launched on this Windows 11 host; its process remained running. A local source build could not find a suitable Visual Studio toolchain, so the verified binary came from the GitHub-hosted Windows runner.
- **Android:** GitHub produced a debug APK targeting API 36 with a prototype-only API 29 minimum. The user's production minimum is Android 16/API 36. No emulator or physical Android device is attached; installation, runtime permissions, and behavior on the user's device remain unverified.
- **Explicitly not demonstrated:** real provider calls, microphone capture, ASR, TTS audio or quality, background behavior, persistent memory, secure credential storage, production signing, or any native system-control action. The prototype intentionally uses mocks and has no device permissions.

The POC satisfies the reproducible-build and mock interaction criteria, but not hardware validation or production speech/security requirements.

## 9. Approval checkpoint

The user has selected Android 16/API 36 as the oldest supported Android release and approved broad capabilities only when granted through normal OS permissions, with confirmation for sensitive actions. Distribution/signing, budget, real speech engines, physical-device behavior, and Copilot Coding Agent enablement remain unknown.

**Approval:** On 2026-10-28, the user approved Flutter plus a shared Dart core as the production direction.

This approval is not approval to bypass operating-system protections or to add unbounded automation. Keep system operations behind permission-aware platform interfaces, use explicit confirmations for sensitive actions, and fail safely where the OS does not support a capability. Android API 36 is the production minimum. Real ASR/TTS engines, budget, distribution/signing, and physical-device behavior still require resolution. The existing Python application has not been migrated; the verified app remains a mock-only prototype.

## 10. References

- Flutter supported deployment platforms: https://docs.flutter.dev/reference/supported-platforms
- .NET MAUI supported platforms: https://learn.microsoft.com/dotnet/maui/supported-platforms?view=net-maui-10.0
- Capacitor platform/plugin model: https://capacitorjs.com/docs
- Android background-work and lifecycle guidance: https://developer.android.com/develop/background-work
- Android `SpeechRecognizer` security, lifecycle, and remote-processing notes: https://developer.android.com/reference/android/speech/SpeechRecognizer
- WebView2 Evergreen deployment and per-user installation: https://learn.microsoft.com/microsoft-edge/webview2/concepts/distribution
