# Vishnu

<!-- repository-profile:start -->
## Repository profile

**Purpose:** Operational continuation repository for the single-owner Vishnu product. This repository also preserves a dated recovery snapshot and documents the historical import boundary.

**Core contents:** Python/PyQt6 desktop application, FastAPI control surface, model routing, SQLite-backed product data, memory and knowledge systems, governed tools/autonomy, companion/PWA areas, device pairing, audit/events, tests, qualification material, and deployment/packaging directories.

**Operational source of truth (2026-10-04):** This repository is the canonical repository for new development and deployments. Railway production follows `main`; the accepted stable deployment baseline is `2e74e8a45cd9543b7578bb879df39a90d407737e`. The active preview candidate is tracked separately under `ui/approved-pages-implementation-20261003`. This is an operational decision; it does not claim that the imported historical Git lineage is complete.

**Historical provenance:** Import commits identify `sawantvaishnav1994-ai/personal-ai` at `f289a3b` and `fec51eb` as source points, including an upstream PR that was not merged at import time. The original source could not be resolved through the available GitHub connection during the 2026-10-04 review, so its later disposition and complete ancestry remain unverified. Keep the import commits and this note until the original source can be independently confirmed.

**Product model:** The current release is treated as a single-owner installation. Its owner-scoped authentication and SQLite data model are a better fit for this model than for a public multi-user service. Do not advertise tenant isolation or public multi-user support until those boundaries are implemented and tested.

**Security note:** This repository is public. Keep secrets, owner keys, production credentials, personal data, and private deployment configuration out of Git history.

**Release evidence:** See [docs/RELEASE_READINESS_2026-10-04.md](docs/RELEASE_READINESS_2026-10-04.md) for verified deployments, branch protection, backup status, CI scope, device gates, and performance limits.
<!-- repository-profile:end -->

Independent Vishnu assistant codebase designed from scratch.

## Current integrated product

- PyQt6 desktop shell
- Living pulse AI visual states
- Model router (Local OpenAI-compatible + OpenRouter)
- SQLite conversations, memory objects, relationships, tasks and audit events
- Memory graph data service
- Tool registry with risk levels
- Autonomy modes: observe / suggest / ask / act
- Agent planner + executor with structured step results
- File tools
- Browser opener/search URL tools
- System information + safe app launcher
- Notes and reminders
- Document helpers for DOCX/PPTX/XLSX
- Screen screenshot capture hook
- Voice input/output service interfaces
- Local FastAPI control API
- Device pairing foundation with authenticated bearer tokens
- Plugin manifest model (no arbitrary in-process import)
- Event/audit bus
- Configuration and secrets abstraction
- Tests
- GitHub Actions CI file
- Packaging entrypoints
- iPhone/PWA persistent conversations and hands-free voice
- Owner-facing Memory Graph, Tree, Detail and controls
- Separate document Knowledge ingestion, search and citations
- Durable governed workflows, recovery and emergency stop
- Per-device scopes, device listing and revocation
- Replaceable cloud/self-hosted model routing

Operational details: [`docs/OWNER_PRODUCT_OPERATIONS.md`](docs/OWNER_PRODUCT_OPERATIONS.md).

## Create Vishnu without a laptop

A laptop is not required to establish the first Vishnu owner identity. The Android and iOS applications include **I don't have a Vishnu runtime yet**, which generates a high-entropy one-time bootstrap secret on the phone and opens an owner-approved deployment flow. The bootstrap secret is never placed in the deployment URL and the hosting provider does not become the Vishnu owner identity.

For a browser-only start, create a strong one-time bootstrap secret in your password manager, keep it private, and provide it when the deployment form asks for `PERSONAL_AI_OWNER_BOOTSTRAP_SECRET`.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/vaishnavsawant1994-stack/vishnu)

The checked-in `render.yaml` creates the canonical headless Vishnu runtime with a persistent disk, disables automatic redeploys, generates the encrypted-vault host secret in the provider secret store, and asks the owner for the one-time first-run bootstrap secret. After deployment, open the HTTPS runtime and complete the same **Create my Vishnu** ceremony used by every other first device.

Render is an optional hosting path, not an identity or mandatory data authority. Owners with a local computer, home server, NAS, or another compatible HTTPS host can run the same canonical runtime there instead.

## Run

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # Windows
# or: cp .env.example .env
python -m app.main
```

## Secure vault startup

Vishnu fails closed when it cannot unlock its encrypted secret vault. The
recommended desktop configuration stores the generated root key in the operating
system keychain. On a headless machine or in CI, set
`PERSONAL_AI_VAULT_PASSWORD` to a strong value supplied by the deployment secret
store. Never commit that password, an exported root key, provider tokens, or
signing material to this repository.

For a local non-interactive smoke test:

```bash
PERSONAL_AI_VAULT_PASSWORD='temporary-test-only' python -m app.main
```

The example value is for disposable test data only. Production deployments must
use an owner-controlled secret and a durable data directory. Optional provider,
signing, device and microphone features may remain unconfigured; their absence
must be reported as deferred external qualification rather than bypassed.

This project does not contain or reproduce Brahma Echo source code.