# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

One person using JARVIS locally on their Windows PC to chat, use optional speech input/output, and request permission-bounded computer assistance.

## Product Purpose

JARVIS provides a local assistant interface for text and optional voice conversations, with an authenticated FastAPI backend, configurable AI providers, local conversation history and memory, and a restricted set of Windows tools. Success means the user can understand the assistant's real state, communicate reliably, and approve consequential actions explicitly.

## Positioning

JARVIS combines multiple configurable AI-provider adapters with local Windows tools and optional local speech synthesis, while keeping credentials in the system credential store and limiting computer actions through allowlisted tools and confirmation steps.

## Operating Context

The backend runs locally on Windows and binds to loopback by default. The dashboard is served as a web interface and can be displayed in the desktop WebView2 shell. Provider calls require the user's configured credentials and may be billable. Browser speech recognition may use an online service; Piper and optional Chatterbox synthesis run locally after explicit model setup.

## Capabilities and Constraints

- Implemented: authenticated chat and provider management; OpenAI Responses, OpenAI-compatible Chat Completions, and Anthropic Messages adapters; bounded failover; local chat history and SQLite memory; restricted Windows tools; Piper voice output; optional Chatterbox setup requiring explicit consent.
- Speech recognition depends on browser/WebView support and user microphone permission. Voice quality, real-time performance, and Chatterbox operation are not assumed without testing.
- The Flutter prototype's Android voice remains mocked and is not an implemented Windows or Android runtime capability.
- Arbitrary shell execution, unrestricted file access, hidden remote access, privilege escalation, automatic destructive actions, and broad browser automation are not supported.
- Windows system settings changes require an explicit user action; the interface must not imply an operation succeeded unless the operating system confirms it.

## Brand Commitments

The product name is JARVIS. The user's brief calls for a futuristic Windows assistant interface, dark black/graphite surfaces, restrained cyan/blue highlights, an animated central assistant/core, and legible Arabic and English rendering. Interface behavior must remain truthful about which features are implemented, unavailable, or mocked.

## Evidence on Hand

The repository's FastAPI routes, local dashboard, Windows desktop launcher, provider manager, voice implementation, and automated tests are the available implementation evidence. No verified live provider credentials, real generated Arabic/English audio evidence, or Windows manual-test results are part of this record.

## Product Principles

- Show actual connection, listening, processing, speaking, and error state; never imply capability without evidence.
- Keep provider credentials and private conversation content out of logs and browser responses.
- Use explicit consent for optional model downloads and confirmation for consequential local actions.
- Make failure recoverable with clear status and next steps.
- Preserve keyboard access, readable Arabic/English text, and support for reduced motion.
