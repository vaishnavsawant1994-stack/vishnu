# Repository inventory

**Baseline:** `vaishnavsawant1994-stack/vishnu`, `main` SHA `a8d3310b4d9090a42800621b1b27cb6045443c1e`.

The inventory was generated from the checked-out tree. It records 58 top-level subsystem directories and their tracked file counts. It is not a claim that every file is active. Each subsystem's entry points, API/UI evidence, storage, and test mapping are linked in [repository_inventory.json](repository_inventory.json) and the domain inventories.

## Top-level subsystems

| Subsystem | Purpose | Initial truth classification |
|---|---|---|
| `app`, `server`, `cloud_runtime` | Desktop and hosted runtime composition; FastAPI services and routers | Active; multiple composition roots must stay aligned |
| `desktop`, `pwa`, `android-companion`, `ios-companion`, `web-companion`, `dashboard`, `ui` | Product surfaces | Active surfaces; feature parity and end-to-end reachability vary |
| `identity`, `security`, `approvals`, `devices`, `trust_continuity`, `continuity`, `recovery` | Identity, authentication, policy, device trust, continuity and recovery | Canonical security/state owners; review authority boundaries before edits |
| `core`, `data_plane`, `memory`, `knowledge`, `projects` | Shared storage foundation, local-first placement, and distinct user-data domains | Active; SQLite and provider transfer scope described in DATA_ARCHITECTURE.md |
| `agent`, `tools`, `apps_tools`, `capabilities`, `integrations`, `plugins`, `browser` | Agent and governed action/capability layer | Active; execution requires existing registries and governance |
| `models`, `file_intelligence`, `vision`, `visual_intelligence`, `voice`, `sensorium`, `activities` | Intelligence and modality subsystems | Mix of product paths and gated/experimental paths; no blanket provider/device claim |
| `automation`, `proactive`, `notifications`, `playbooks`, `evidence` | Workflows, user attention and execution evidence | Active; background/live delivery requires configuration-specific qualification |
| `products`, `packaging`, `installer`, `updates`, `deploy` | Product composition, build and release | Active implementation, external signing and production acceptance remain separate |
| `future_intelligence`, `intelligence_lab`, `evolution`, `training` | Research, training, self-improvement and lab work | Experimental/gated; not general-purpose autonomous production authority |
| `qualification`, `readiness`, `tests`, `scripts`, `.github/workflows` | Quality gates, evidence and automation | Active verification infrastructure; green historical CI is tied to its SHA |
| `docs`, `personal-ai` | Documentation and retained historical boundary | Mixed current/history; see architecture reconciliation |

The complete path-level inventory is machine-readable in `repository_inventory.json`. A directory's `ACTIVE_CANDIDATE` label means it is present in current source and merits subsystem-level evaluation; it does not mean it is reachable from user navigation. The file counts include generated/support assets and are not feature counts.

## Repository scale at the audited SHA

- 1,827 tracked files at root checkout inventory time.
- 58 top-level subsystem directories.
- 2,407 commits in Git history after fetching full history.
- 240 pull requests returned by paginated GitHub REST history: 204 merged, 36 closed without merge, 0 open at retrieval.
- 647 Python test modules matching `tests/test_*.py`; the tests directory contains 684 files total.
- 818 statically discovered API-style route decorators from the refreshed scan of Python files outside tests. Dynamic mounts and non-FastAPI endpoints may be absent.

## High-level source ownership

- Desktop product startup: `app/main.py`; hosted runtime: `server/hosted_runtime.py` and `server/cloud_app.py`.
- Identity, session and owner policy: `identity/`, `security/`, `server/identity_api.py`, `server/owner_product.py`.
- Shared SQLite boundary and migrations: `core/sqlite.py`, domain migrations/stores under `devices/`, `memory/`, `knowledge/`, `projects/`, `products/`, and `data_plane/`.
- Device trust and commands: `devices/`, `trust_continuity/`, `continuity/`, platform companions.
- Governed actions: `tools/`, `approvals/`, `capabilities/`, `integrations/`, `server/capability_console_api.py` and related routers.
- Primary browser owner product: `server/iphone_pwa.py`, `server/cloud_app.py`, `pwa/`.
- Native mobile sources: `android-companion/app/src/main/` and `ios-companion/PersonalAICompanion/`.

## Audit limits

The machine inventories are source-derived. They do not automatically prove runtime composition, navigation reachability, database use, policy checks, or actual user-visible outcomes. Those properties are marked `NOT VERIFIED` in the feature and traceability maps until runtime evidence ties them together. No production environment, live credentials, or real provider was accessed.
