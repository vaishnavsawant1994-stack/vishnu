# Vishnu Owner Journey Map

**Baseline:** `4ec735de327f2bab6dccb774e2a9c28ef4fc44af`

These journeys connect the screen blueprint to concrete owner goals. They are product acceptance paths, not a promise that every path is already executable on every platform.

## 1. New owner — create Vishnu

```text
ONB-001 Welcome
→ ONB-002 Owner Identity
→ ONB-003 Security Setup
→ ONB-004 Privacy & Autonomy
→ ONB-005 Data Placement Policy
→ ONB-006 AI Provider Setup
→ ONB-007 Recovery Code Setup
→ ONB-008 Review & Completion
→ HOME-001 Home
```

Acceptance:
- creation is single-owner, atomic/idempotent and resume-safe;
- Device 1 is registered separately from owner identity;
- recovery material is acknowledged before completion;
- Data Plane policy is explicit and does not silently move data;
- AI provider can be deferred;
- final review shows no secrets/recovery-code values.

Current gap: ONB-005 and ONB-008 are missing; Android native first-device parity is also incomplete.

## 2. Existing owner — join a new device

```text
ONB-001 Welcome
→ AUTH-002 Join Existing Vishnu
→ AUTH-001 Sign In / owner authentication
→ device pairing / existing trusted-device approval
→ DEV-001 Trusted Devices
→ DEV-002 new Device Detail
→ Home or native companion ready state
```

Acceptance:
- owner identity is reused, never recreated;
- requested device scopes are visible before approval;
- short-lived pairing material expires cleanly;
- new per-device credential is secure and revocable;
- denied/revoked device cannot access owner data by direct URL/API.

## 3. Lost first device — restore and revoke

```text
ONB-001 / AUTH-001
→ AUTH-003 Restore Access
→ verify recovery material / encrypted package
→ establish replacement trusted device
→ REC-001 Recovery Overview
→ DEV-001 Trusted Devices
→ DEV-002 Lost Device
→ Revoke / Mark Lost confirmation
→ SEC-003 Security Events
```

Acceptance:
- recovery does not require possession of the lost device;
- replacement device gets a distinct device identity;
- lost credentials become unusable after revocation;
- data restoration and device trust are separate concerns;
- owner can see the recovery/revocation audit trail.

## 4. Normal conversation

```text
HOME-001 Home
→ CHAT-001 Conversation Workspace
→ send message
→ streaming/thinking/tool state
→ response
→ optional CHAT-002 History
```

Acceptance:
- cancel/retry/interruption are represented;
- offline/local-model behavior is distinguished from provider failure;
- citations/attachments belong to the correct turn;
- conversation history can be continued without losing context authority.

## 5. Governed tool action

```text
CHAT-001 request
→ Vishnu proposes tool/capability action
→ APR-001 Approval / contextual approval card
→ SEC fresh-owner reauthentication if required
→ governed execution
→ ACT-002 Activity / WRK-002 Work Detail result
→ CHAT-001 result summary
```

Acceptance:
- approval states exactly what, why, target, risk and parameters;
- persistent permission is not confused with one-time action approval;
- expired/denied approval cannot execute;
- execution result and failure are auditable.

## 6. Connect an external service

```text
APP-001 Apps & Tools
→ APP-002 Connected Service Detail / Add
→ provider OAuth or secure credential prompt
→ permission/scope review
→ connection test
→ connected state
→ later revoke/disconnect
```

Acceptance:
- secret is never redisplayed after save;
- OAuth state/PKCE/session protections remain intact;
- provider failure gives safe actionable status;
- revoke removes future action authority and is reflected after refresh/restart.

## 7. Import an OpenAPI capability

```text
APP-001 Apps & Tools
→ CAP-001 Capabilities
→ Add → OpenAPI import/preview
→ validate/discover operations
→ CAP-002 Capability Detail
→ credential setup if needed
→ connect/risk review
→ read execution or exact write approval
→ audit/history
```

Acceptance:
- discovery does not itself authorize execution;
- redirects/host/network restrictions remain enforced;
- write/destructive operation requires canonical exact approval;
- credential rotation/revoke are available without exposing the secret.

## 8. Add an MCP server

```text
CAP-001 Capabilities
→ Add MCP server
→ secure connection settings
→ discover tools
→ inspect schema/risk
→ approve individual tool
→ CAP-002 detail
→ execute through governed ToolRegistry
```

Acceptance:
- read-only attestation is explicit;
- write/destructive risk is not silently downgraded;
- invalid params/provider errors remain safe;
- revocation prevents restart rehydration from restoring authority.

## 9. Control where data lives

```text
SET-001 Settings
→ DAT-001 Data & Storage
→ inspect current policy/location/sync
→ choose new policy or connected storage
→ DAT-002 provider detail if remote provider is involved
→ explicit movement confirmation where required
→ updated persisted state
```

Acceptance:
- local copy/remote state are described separately;
- network loss is not shown as data loss;
- policy mutation persists after reload;
- remote transfer success is never claimed without data-plane evidence;
- owner can cancel/retry governed transfer where supported.

## 10. Add and use Knowledge

```text
KNW-001 Knowledge
→ Add Source / Upload
→ processing/indexing state
→ source becomes available
→ KNW-002 Source Detail
→ search/ask with citations
```

Acceptance:
- supported/unsupported file behavior is explicit;
- processing failure is visible and retryable where supported;
- deleting/disconnecting explains whether original source data remains;
- Memory and Knowledge remain distinct authorities.

## 11. Continue a project and inspect work

```text
PRJ-001 Projects
→ PRJ-002 Project Workspace
→ Work Plan / Live Work tab
→ WRK-002 Work Detail
→ evidence/approval/recovery state
→ project activity/result
```

Acceptance:
- assigning a task to Vishnu does not falsely imply execution started;
- WorkOrder status comes from canonical work authority;
- completion claims are backed by evidence/receipts;
- recovery-required/uncertain states are visible, not presented as success.

## 12. Create an automation

```text
AUT-001 Automations
→ Create Automation dialog
→ define instruction + schedule/condition + permissions
→ save
→ AUT-002 Automation Detail
→ observe next run / run history
→ pause/resume/delete
```

Acceptance:
- schedule/condition is understandable to owner;
- required approval/permissions are visible;
- failed run appears in Inbox/Activity with actionable error;
- pause/delete persists after reload.

## 13. Revoke a device

```text
DEV-001 Devices
→ DEV-002 Device Detail
→ Revoke / Mark Lost confirmation
→ refresh
→ device shows Revoked, never Active
→ SEC-003 audit entry
```

Acceptance:
- destructive impact is explicit;
- current device cannot accidentally strand the owner without appropriate recovery warning;
- revoked credential fails subsequent authenticated requests.

## 14. Stop Sensorium access

```text
Native companion
→ SEN-001 Sensorium Privacy & Permissions
→ inspect active sessions
→ Stop individual sensor OR STOP ALL SENSING
→ session state OFF
→ local/server audit where applicable
```

Acceptance:
- perception permission never grants tool/computer control;
- temporary sessions visibly expire;
- unavailable hardware reports unavailable rather than invented values;
- emergency stop does not delete unrelated Memory.

## 15. Recover from provider/model outage

```text
CHAT-001 or MOD-001 detects provider failure
→ degraded state explains unavailable provider
→ local/fallback route used if policy permits
→ SYS-001/SYS-002 shows provider health
→ owner can open MOD-002 to repair credentials/provider
```

Acceptance:
- text/local capability stays usable when possible;
- provider outage is not shown as total Vishnu failure;
- privacy policy remains enforced during fallback.

## 16. Security review

```text
SET-001 Settings
→ SEC-001 Security Overview
→ SEC-002 Sign-in Methods & Sessions
→ DEV-001 Trusted Devices
→ REC-001 Recovery
→ SEC-003 Audit History
```

Acceptance:
- owner can answer which sign-in methods/sessions/devices exist;
- tokens/secrets/private keys are never displayed;
- sensitive mutations require current authority and fresh reauthentication where designed.

## 17. Check/update Vishnu

Target journey after missing screens are implemented:

```text
SET-001 Settings
→ SYS-003 Updates & Release
→ inspect current/available version and verification
→ apply supported update
→ restart/recovery state
→ SYS-004 About confirms installed build
```

Acceptance:
- only signed/qualified update path is presented as installable;
- failed update has bounded recovery/rollback behavior;
- production deployment remains separate from local application update.
