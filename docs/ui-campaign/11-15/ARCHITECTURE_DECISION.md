# Architecture decision — Screens 11–15

Status: interim, source-audited only (2026-10-19).

## Decision

For the current bounded implementation, keep the existing PWA as the shared responsive web experience and add the dedicated Global Search view as a PWA module. Query only existing authenticated conversation and project list APIs. Do not create a duplicate search database or invent search routes. Existing Qt, Android, and iOS applications remain platform adapters/companions; this change does not make them render the PWA inside their installed shells.

This is not a final cross-platform architecture approval. Full integrated UI needs a separate security/package feasibility review covering desktop WebEngine/local session and native bridges, Android WebView/TWA/WebAuthn/cookie behavior, and iOS WKWebView/AuthenticationServices/associated domains. The current browser handoff is explicitly not parity.

## Alternatives

1. Shared responsive UI embedded in each app: maximizes visual parity, but requires qualifying each platform's session, origin, passkey, file, sensor, lifecycle, packaging, and bridge behavior.
2. Independent native screen implementations from shared tokens: preserves platform-native interaction but raises ongoing parity and test costs and cannot promise pixel identity.

No wholesale framework migration is authorized by this implementation. Choose between these only after the native security and runtime paths are demonstrated.

## Guardrails

- Existing runtime and owner-scoped APIs remain the source of truth.
- Unsupported result categories are explicitly listed, not filled with sample records.
- Search results open existing resource routes where those routes exist.
- Do not claim cross-platform parity based on a PWA URL opened by a companion app.
