# Vishnu — Canonical Personal AI Product Handbook

> **Repository:** `vaishnavsawant1994-stack/vishnu` · **Reviewed:** 15 November 2026  
> **Identity:** This is the main Vishnu product source, not `Vishnu-V1.0` or `Vishnu-2-AI`. The historical `personal-ai` technical/package identifier remains for compatibility.

## Product mission and users

Build an owner-controlled personal AI that understands conversations, remembers contextual information, operates across project workspaces, interacts with authorized devices and tools, and executes approved tasks reliably. The single owner and their expressly authorized environments are the primary users; this source should not be advertised as a generic proven multi-tenant SaaS.

## Main product areas

1. **Conversation and project workspaces:** general chat, project-context chats, conversations, tasks, activities, files/sources and work assignment surfaces.
2. **Personal intelligence:** memory, knowledge ingestion/retrieval, contextual model routing, multimodal/voice foundations and configurable owner preferences.
3. **Agent/work execution:** tools, planning, permission-scoped approvals, task delegation, audit trails, interruption recovery and explicit emergency stop.
4. **Devices and user experiences:** Python/PyQt6 desktop, web/PWA, iOS/Android companion source, browser/device integrations, onboarding, notification and security UI.
5. **Operations:** provisioning, observability, deployment/packaging, test suites, backup/restore and release qualification materials.

Features are based on source areas and documentation; each requires separate evidence of working user journeys, backend integration and accepted release status.

## Architecture and source map

Python 3.11+ with PyQt6 desktop UI and FastAPI control-plane surfaces. SQLite-backed local/personal state and abstraction layers for memory, knowledge, model connectors, devices and worker execution. Main directories include `app/`, `core/`, `server/`, `ui/`, `memory/`, `knowledge/`, `projects/`, `workspaces/`, `security/`, `tests/`, `deploy/`, `desktop/`, `ios-companion/`, `android-companion/`, `automation/`, `plugins/` and `devices/`. See `ARCHITECTURE.md`, `ARCHITECTURE_V5.md` and `CYBERSECURITY_ASSURANCE.md` for specification and qualifications.

## Source, deployment and maturity boundaries

- `vishnu` is the designated main development repository. `Vishnu-V1.0` is an independently staged Windows/Web track; `Vishnu-2-AI` is a separate autonomy experiment.
- The README contains dated recovery/provenance and operational/production baseline statements. Treat these as historical evidence until checked against current Railway services, exact GitHub SHA, attached durable storage, backup restoration and current CI.
- Existence of a frontend screen or backend method does not prove each interactive route, storage path, AI provider, consent step, native companion or external tool is fully functional.
- Unmerged feature branches or local workstation edits are not automatically present on `main`.

## Local development and acceptance

Create a Python virtual environment, install the requirements files appropriate to the subsystem, configure a managed secret vault and data directory and use the documented `python -m app.main` startup. Execute current pytest, lint, GUI/browser and security checks on the exact commit. Never import old device identities, personal messages or owner credentials to simulate a successful migration.

Before live release test: creation and restore of the first owner, scoped identity/authorization, durable storage on restart/redeploy, memory and file privacy, operation approvals/Stop, agent outcome verification, mobile/desktop responsive UI, voice/device privacy, observability, rollback and restore drills.

## Highest-value next milestones

1. Map UI screens and workflows to real API/storage behavior and acceptance tests; preserve the original 3D sphere and approved interaction rules.
2. Verify repository/branch integration and current Railway deployment against pinned commit, not only README or CI names.
3. Qualify owner isolation, tool permissions, memory and secure automation in a disposable staging account.
4. Prove DB and user-data persistence through restarts, backups and restore.
5. Publish an exact-SHA release evidence report before presenting the platform as fully operational.

## References

- [Root README](../README.md)
- [Architecture](../ARCHITECTURE.md)
- [Architecture v5](../ARCHITECTURE_V5.md)
- [Cybersecurity assurance](../CYBERSECURITY_ASSURANCE.md)
- [Security policy](../SECURITY.md)
- [Qualification documentation](../docs/)
- [Tests](../tests/)

**Documentation update policy:** preserve historical evidence, report actual current status, and avoid publishing unsupported completion or live deployment claims.