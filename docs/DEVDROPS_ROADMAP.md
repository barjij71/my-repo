# JARVIS implementation roadmap inspired by Daily Dev Drops

This roadmap adapts the workflow ideas to the existing Windows-first FastAPI application. It does not require installing Claude Code plugins into the runtime.

## Phase 1 — Map the codebase (Graphify-style)
- Identify API routes, provider configuration, UI entry points, credential handling, tests, and CI.
- Keep a short architecture map in this document and update it when the design changes.
- Never upload API keys or other secrets to code-indexing tools.

## Phase 2 — Plan and validate changes (Agent Skills-style)
- Make focused changes with explicit acceptance criteria.
- Add a regression test for each reported bug.
- Run the existing pytest suite and both Windows/Linux CI jobs before calling a change complete.

## Phase 3 — Provider routing (OmniRoute-style)
- Keep the current provider manager rather than introducing a second gateway without evidence it is needed.
- Persist each provider's model and API key independently.
- Only route to providers whose keys are configured; avoid logging secrets; test quota, transient failures, cooldown, and recovery.
- Keep provider credentials in the OS credential store.

## Phase 4 — Durable development context (claude-mem-style)
- Keep architecture decisions, commands, test results, and known limitations in versioned docs.
- Do not store credentials, private prompts, or sensitive user data in repository memory.

## Phase 5 — Lean edits and performance (Ponytail-style)
- Prefer narrow patches and avoid large dependencies or model downloads.
- Measure startup, test duration, request latency, and memory before claiming performance improvements.

## Current execution
- The repository is a Windows-first FastAPI + static HTML app. Provider settings are handled by GET/POST /api/providers; API keys use the OS keyring; CI runs pytest on Windows and Ubuntu.
- Fix in this branch: expose each provider's saved model/key-configured status to the UI so switching providers no longer hides its saved model configuration.
- Validation pending: GitHub Actions after the branch updates. No provider API key or model download is needed for tests.

## Remaining checklist
- [ ] Confirm Save Provider persists provider/model/key on Windows Credential Manager.
- [ ] Run Windows and Linux pytest CI.
- [ ] Review failover behavior for authentication errors versus quota/transient errors.
- [ ] Benchmark cold startup and test runtime on the target PC.
- [ ] Keep voice/Android work on the existing dedicated branch and do not merge unrelated changes here.
