# Backend Without Adequate UI

**Baseline:** `4ec735de327f2bab6dccb774e2a9c28ef4fc44af`

This report includes backend capability only when the owner reasonably needs to see, configure, authorize, revoke, recover or understand it. Infrastructure that is correctly internal is listed separately.

| Capability | Backend authority/evidence | Owner need | Recommended surface | Full page? | Priority | UI truth |
|---|---|---|---|---|---|---|
| First-run data placement | `data_plane/`, storage policy labels `device_only`, `progress_only`, `sync_everywhere`, `on_demand`; desktop/PWA/iOS onboarding currently lacks the choice | Know/control where data may live before creation completes | ONB-005 Data Placement Policy | Wizard step | P1 | MISSING |
| Final setup review | identity, device, recovery, preferences, provider and data-policy authorities already exist separately | Verify what was created before entering Home | ONB-008 Setup Review & Completion | Wizard step | P1 | MISSING |
| Storage-provider detail | `data_plane/storage_fabric.py`, transfer/provider capability and health foundation | Know destination, health, consent, encryption and transfer status; disconnect/retry | DAT-002 under Data & Storage | Yes/detail | P1 | MISSING |
| Accessibility preferences | runtime/preferences already contain `reduce_motion` / `high_contrast`; CSS/native conventions exist | Discover and control supported accommodations | SET-005 Accessibility | Settings subsection | P1 | MISSING |
| Sensorium provider status/evidence | Sensorium native/emulator/simulator/VM provider and evidence APIs | Inspect availability/qualification without low-level command access | SEN-002 Advanced Sensorium Status | Advanced page | P2 | MISSING |
| Self-update/release status | `updates/`, packaging/release/signature/reproducibility systems | Know installed version, update availability and safe restart/recovery | SYS-003 Updates | Settings page | P3 | MISSING |
| Product/about identity | build/version/license/third-party notice data exists in packaging/docs | See current Vishnu version, proprietary license and notices | SYS-004 About | Settings page | P3 | MISSING |
| Owner session management | PWA/native owner sessions, rotation/reauth and passkeys exist | See/revoke methods/sessions without viewing tokens | SEC-002 Sign-in Methods & Sessions | Security subsection | P2 | PARTIAL/fragmented |
| Recovery readiness | recovery codes, encrypted backup/package/restore authority exists | Know whether recovery is actually usable; link restore/lost-device revoke | REC-001 Recovery | Settings page | P1 | PARTIAL/fragmented |
| Device lifecycle detail | `DeviceRegistry`, `DeviceGateway`, scopes/revocation/last-seen | Rename/inspect scopes/revoke/mark lost and understand continuity | DEV-002 Device Detail | Yes/detail | P1/P2 | PARTIAL |
| Capability governance | OpenAPI/MCP catalog, approvals, vault, audit, revocation | Inspect risk/credentials/history/revoke | CAP-001/002 | Yes | P1 | PARTIAL; strongest existing UI |
| Security/audit history | owner audit/security-events APIs | Understand sensitive actions without secrets | SEC-003 | Yes/Advanced | P2 | PWA present; desktop gap |
| Approval queue | ApprovalManager + approvals-center APIs/events | See pending decisions consistently | APR-001 / Inbox | Page/context | P1 | PWA strongest; desktop gap |
| Computer/browser control status | computer/browser operators + policy/approval authorities | Know whether control is enabled, target device/profile and stop it | CTL-001 | Settings/Advanced | P2 | Desktop partial; PWA gap |
| Project/work authority | projects + WorkOrder aggregate/evidence/claims/recovery APIs | Track long-running work and proof | WRK/PRJ screens | Existing PWA | P2 | Present but needs visual/E2E acceptance |

## Correctly internal — no dedicated page required

These systems should remain implementation authorities, with only owner-meaningful status/control exposed through other screens:

1. SQLite connection/migration mechanics.
2. Root key derivation/storage internals.
3. SecretVault envelope/nonce/AAD details.
4. ToolRegistry registration mechanics.
5. Approval durability/one-use token internals.
6. Event bus/signal transport.
7. conflict-resolution algorithm internals.
8. lease/replay-protection internals.
9. encrypted transport segment framing.
10. retry/backoff machinery.
11. audit hash-chain mechanics.
12. qualification/evidence persistence implementation.

A missing low-level developer console for these is **not** a product UI defect.
