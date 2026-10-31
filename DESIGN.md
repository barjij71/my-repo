# JARVIS Interface Design

## Direction

Extend the existing local command-center visual language rather than replacing it: black and graphite surfaces, restrained cyan/blue accents, crisp status color, and a central animated assistant core. The visual hierarchy should make the assistant's live state and the next useful action more prominent than decorative telemetry.

## Interface Contract

- The command screen is the primary workspace: assistant/avatar state, recent conversation, system status, and quick actions.
- Idle, connecting, listening, thinking, speaking, and error states use both visible text and a distinct visual treatment. Motion is status-linked, never the only status cue.
- Mic, voice output, cancellation, provider settings, system refresh, history clearing, and Windows Settings shortcuts invoke existing APIs or explicit allowlisted desktop bridge methods. Unsupported browser/device capabilities are shown as unavailable.
- Arabic input and output remain readable and use automatic text direction. English remains the interface's default language.
- Keep the dashboard usable from narrow browser widths through the Windows desktop shell; preserve keyboard focus, accessible names, and reduced-motion preferences.
- Keep model downloads, provider tests, destructive history removal, and Windows configuration changes explicit and separate from ornamental UI controls.

## Visual Foundations

- Canvas: near-black navy with subtle grid/radial depth; panels: graphite/navy with restrained borders.
- Accent: cyan/blue for active navigation and controls; green for confirmed ready states; amber/red for warning/error.
- Use the system UI font stack (Segoe UI first on Windows), compact uppercase labels only for metadata, and readable body text.
- Central avatar uses inline vector artwork and CSS-only motion; no network assets or heavyweight animation dependencies.

## Evidence and Limitations

The existing application is a single-page HTML/CSS/JavaScript dashboard served by FastAPI and embedded by pywebview on Windows. The redesign must preserve this deployment model. Browser microphone availability and Windows Settings integration vary by runtime and are reported honestly; the Android Flutter voice prototype is not represented as a live capability.
