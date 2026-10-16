# Data and storage architecture

**Baseline SHA:** `a8d3310b4d9090a42800621b1b27cb6045443c1e`.

## Stores and owners

| Store | Canonical owner / role | Encryption and recovery evidence | UI / policy |
|---|---|---|---|
| SQLite databases | `core/sqlite.py` common connection/migration foundation; domain stores for devices, Memory, Knowledge, projects/products, workflows, capabilities and audit | Versioned migration tests; transaction, concurrency, integrity and encrypted backup/restore suites exist. Actual deployed DB file and schema are runtime-config dependent | Local-first user data; per-domain UI varies |
| SecretVault / RootKeyStore | `security/` plus keychain/password boundary | Authenticated encryption and crash-safe rotation tests; key is intended for OS keychain or deployment secret, not repository | Owner config; missing unlock fails closed |
| Data Plane logical records and transfer checkpoints | `data_plane/` integrated into existing data plane, referencing logical items/locations | PR #245 adds resumable checkpoints, encryption reuse and range/multipart transport; live provider recovery not verified | Policies: `device_only`, `progress_only`, `sync_everywhere`, `on_demand`; no silent movement |
| Browser/PWA cache and local state | `pwa/`, service worker and data-plane cache | Offline shell and bounded cache qualification exists; sensitive values in local browser storage require separate review per key | PWA state/settings; no blanket claim of encrypted browser storage |
| Android/iOS stores and OS secure storage | Native `ManagedByteStore`, mobile data-plane stores, keychain/secure-storage APIs | Instrumentation/unit/simulator sources exist; physical secure-storage behavior not exercised here | Mobile feature parity is partial |
| Evidence, logs and audit | `evidence/`, domain audit tables/events and workflow evidence | Retention/immutability varies by domain; qualification artifacts and provider logs are not a single store | Owner/admin and internal evidence panels |
| Optional remote providers | Configured S3-compatible or other provider adapters/relay | Transfer layer is implemented and tests exist; live provider account, destination, credentials and backup restore are not verified | Explicit provider setup/consent required |

## Placement semantics

`device_only` is local to the owner's selected device/runtime. `progress_only` is intended for limited continuity/progress state. `sync_everywhere` requests synchronization across trusted locations. `on_demand` defers transfer until requested. Exact per-domain classification, supported migration behavior and failure UX should be checked in the policy-aware store path; do not infer that every data type supports every policy just because the enum exists.

PR #245 reuses existing `DataItem`/`DataLocation` rather than adding another logical-object database. It introduces resumable provider transfers, multipart support and bounded-memory range handling, encrypted segments via existing secret/envelope authority, placement planning and non-destructive health reconciliation. It does not auto-create cloud copies or silently repair replicas.

## Risks and unverified items

- No live runtime was queried; the effective data path and mounted volume contents are unknown.
- The repository has multiple domain stores and runtime compositions. This audit does not assert every store has migrated to the shared SQLite boundary.
- Real provider transfer, revocation behavior against a live provider, conflict races at scale, production backup freshness and isolated production restore are not verified.
- Browser and native local storage encryption/classification must be established per value, not inferred from transport security.
- Older docs describe Railway; the current checked-in `render.yaml` describes Render. The production host/data root is unverified and must not be changed during this audit.
