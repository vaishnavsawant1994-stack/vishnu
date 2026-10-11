# Our Products implementation plan

Tracking issue: #153

This branch introduces the owner-only productization layer for Vishnu. The implementation is staged so the existing single-owner product remains the authority while client products are built as isolated packages/runtime configurations.

## Scope

- Product catalogue and lifecycle
- Canonical product manifest and version snapshots
- Component registry references for agents, workflows, automations, tools, knowledge and integrations
- AI policy: disabled, client/BYOK, managed, local/self-hosted, hybrid
- Platform targets and build artifact records
- White-label branding metadata
- License and entitlement foundations
- Deployment/version/monitoring foundations
- Project-to-product promotion
- Owner-only API/UI integration
- Tests and qualification gates

## Security invariants

1. Export is allow-listed: only declared components leave Vishnu.
2. Owner memory, conversations, credentials, signing keys and unrelated components never enter a product package.
3. Client API keys are runtime secrets and are never embedded in APK/desktop/web artifacts.
4. Managed provider credentials stay server-side.
5. Product versions pin component versions; existing released products do not silently inherit new Vishnu code.
6. Current Vishnu remains single-owner. This work does not claim public tenant isolation.

## Delivery targets

Web/PWA, Android APK/AAB, Windows installer, iOS, macOS, Linux, Docker/server and API/worker targets use one canonical product definition and platform-specific builders.

## Qualification products

- Invoice Automation: AI disabled
- Research Employee: client/BYOK AI
- Sales Employee: hybrid AI

A production release is not qualified until manifest, dependency, permissions, secret scanning, AI-off, BYOK, managed AI, licensing, update and target-specific tests pass.
