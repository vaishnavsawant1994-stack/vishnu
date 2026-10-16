# Data Architecture

Baseline: `a8d3310b4d9090a42800621b1b27cb6045443c1e`.

## Persistent authorities

| Domain | Authority | Protection / behavior |
|---|---|---|
| Device trust/state | DeviceRegistry shared SQLite | Versioned migrations; trust/revocation/device scopes. |
| Memory | MemoryStore shared SQLite | Versioned migration; sensitive at-rest encryption; backup/DR coverage. |
| Knowledge | Knowledge store/shared SQLite | Kept separate from Memory; UCI indexing/retrieval. |
| Projects/Products | Domain stores/shared SQLite | Versioned local persistence. |
| Approval/execution | Durable SQLite approval/control stores | Exact-use/security-epoch/dispatch recovery state. |
| Capability catalog | Capability catalog SQLite | Capability/connection metadata; raw secrets delegated to vault. |
| Connector state/audit | Integration state store | Lifecycle/audit and credential references. |
| Secrets | SecretVault/root-key authority | Encrypted credentials; crash-safe root-key rotation. |
| Data Plane | Local policy/lease/transfer/provider state | Owner-selected placement/sync policy, encrypted transport and recovery. |
| Evidence/audit | Evidence/lifecycle stores | Durable receipts/qualification/security provenance. |
| Native/browser state | Platform secure/session stores | Platform scoped; must not be treated as global owner identity authority. |

## Local-first policy

Supported policy vocabulary: `device_only`, `progress_only`, `sync_everywhere`, `on_demand`.

The intended chain is `owner selection -> persisted policy -> local state -> authorized lease -> encryption/envelope -> optional remote/provider transfer -> conflict/progress/tombstone/recovery`. Remote availability does not authorize silent movement.

## Storage fabric

Current #245 work adds resumable/range transfers, multipart S3/R2/B2 behavior, provider capability/health modeling, segmented encryption, placement plans and replica-health metadata. It does not turn provider availability into silent copy/repair authority.

## Hardening lineage

#203-#219 introduced shared SQLite/migrations across DeviceRegistry, Memory, Knowledge/Projects/Products; Memory sensitive encryption; runtime composition/invariants; locks/SBOM/license/reproducibility; backup/portable DR; endurance/concurrency; fault injection.

## NOT VERIFIED in this audit head

- Exhaustive table/index inventory across every SQLite file.
- Proof that every legacy table/migration is still consumed.
- Exhaustive browser/native cache-retention analysis.
- Live production backup/restore on the production volume (repository readiness work explicitly separated this from code qualification).

Those items remain follow-up executable inventory tasks rather than unsupported claims.
