# Vishnu — Owner and External Blockers

Reviewed: 2026-10-15

Only genuine owner or external dependencies are listed here. Repository work and safe automated qualification can continue in parallel.

## BLOCKER-001 — Restore production runtime and prove durable recovery

- Status: `BLOCKED_RUNTIME`
- Evidence: Railway reports the canonical `personal-ai-runtime` service offline with no active deployment. A 500 MB volume is mounted at `/data`, but the effective `PERSONAL_AI_DATA_DIR` value and current contents have not been verified.
- Required operation: determine the intended production release and restore a pinned deployment; verify health and exact running SHA; confirm the effective data root resolves under `/data`; create an encrypted backup; restore it to an isolated target and validate integrity.
- Constraint: no production deployment, restart, or restore was triggered during this audit. Production data was not read or copied.
- Automated fixture backup/restore tests are evidence for implementation behavior only, not production recovery.

## BLOCKER-002 — Real-device qualification

- Status: `BLOCKED_OWNER`
- Required evidence: owner-operated physical iPhone and Android checks on the pinned release candidate, including install/update, permissions, reconnect, notifications where applicable, and recovery.
- Simulator, emulator, browser, or virtual-device results cannot replace physical-device evidence.

## BLOCKER-003 — Provider consent and live connector acceptance

- Status: `BLOCKED_OWNER`
- Required action: grant OAuth/provider consent and configure credentials/scopes directly in the provider and deployment secret interfaces, then validate expiry, revocation, and data destinations.
- Do not send credentials or tokens through chat.

## BLOCKER-004 — Native signing and distribution identity

- Status: `BLOCKED_OWNER`
- Required action: supply/authorize Apple and platform signing identities, agreements, and notarization prerequisites when a release candidate is ready.
- Unsigned builds and CI packaging are not store/distribution acceptance.

## BLOCKER-005 — Project distribution terms

- Status: `DECISION_RECORDED — PROPRIETARY`
- Decision: retain all rights; grant no open-source or third-party reuse permission.
- Before any external source or binary distribution: verify ownership/contributor provenance, dependency notices, and customer-facing commercial terms; obtain legal review if the intended distribution model changes.

## BLOCKER-006 — Production release acceptance

- Status: `BLOCKED_OWNER`
- Required action: after the technical gates pass, complete the owner acceptance checklist, approve the pinned production release, and record rollback acceptance. No deployment approval is implied by this blocker list.
