# Secondary UI & Visual-State Inventory

**Baseline:** `4ec735de327f2bab6dccb774e2a9c28ef4fc44af`

Canonical screen count is deliberately independent of transient presentation. The finished product requires **34 secondary UI families**. A platform may render a family as a desktop dialog, web modal/drawer, Android sheet/dialog or iOS sheet/navigation confirmation.

| # | Secondary surface | Parent concept | Core requirement |
|---:|---|---|---|
| 1 | Action approval prompt | APR-001 / contextual work | target, reason, risk, impact, allow/deny |
| 2 | Fresh-owner reauthentication | security-sensitive actions | secure password/passkey flow; no secret echo |
| 3 | Generic destructive confirmation | delete/revoke/disconnect | object-specific impact and destructive label |
| 4 | Credential entry | providers/integrations/capabilities | secure input, stored-state indicator only after save |
| 5 | Provider connect/test | MOD/APP | test result and safe error |
| 6 | OpenAPI import/preview | CAP | paste/upload URL/spec, validate, preview operations |
| 7 | MCP add/discover | CAP | URL/auth, tool discovery, errors |
| 8 | MCP risk attestation/approval | CAP | schema/risk review before enabling |
| 9 | Exact one-time write approval | CAP/Tools | exact parameters + single-use authority |
| 10 | Capability disconnect/revoke confirmation | CAP | consequence + audit |
| 11 | Device pairing QR/code | DEV/AUTH | short-lived code/QR, expiry, requested scopes |
| 12 | Pending-device approval | DEV/AUTH | requesting device/platform/scopes, approve/deny |
| 13 | Device revoke/mark-lost confirmation | DEV | revoke credentials, continuity/data consequences |
| 14 | Recovery-code save acknowledgement | ONB/REC | copy/download acknowledgement and warnings |
| 15 | Restore confirmation | AUTH/REC | source/destination and irreversible/restart implications |
| 16 | Backup create/export/import | REC/DAT | destination, encryption and result |
| 17 | Data-movement confirmation | DAT | source, destination, policy, encryption, size/status |
| 18 | Sync-conflict resolution | DAT | competing versions, safe choice, no silent discard |
| 19 | Knowledge add/upload | KNW | source/file, privacy/location, processing state |
| 20 | Knowledge remove/disconnect | KNW | what is removed vs source file retained |
| 21 | Memory delete/retention confirmation | MEM/PRI | scope, retention, undo where possible |
| 22 | Project create/edit | PRJ | name/goal/type/target date |
| 23 | Project task create/edit | PRJ | title/owner/status/dependencies; assignment ≠ execution |
| 24 | WorkOrder detail shell | WRK | responsive authoritative detail; full-screen on phone |
| 25 | Automation create/edit | AUT | instruction, trigger, permissions/destination |
| 26 | Automation pause/delete | AUT | status/history and confirmation |
| 27 | Account/notification menu | shell | unread/account actions, keyboard/touch dismissal |
| 28 | Conversation history drawer/sheet | CHAT | search/open; responsive implementation of CHAT-002 |
| 29 | Attachment/file picker | CHAT/KNW | supported types, upload/processing failure |
| 30 | Conversation retry/cancel feedback | CHAT | interrupted state, retry/cancel result |
| 31 | OS sensor permission prompt | VOC/SEN | platform-native permission and denied fallback |
| 32 | Voice authorization/persona dialogs | VOC | explicit authorized voice/persona changes |
| 33 | Telephony consent/approval | VOC Lab | explicit destination/consent/default-off safeguards |
| 34 | Emergency stop confirmation | Security/Sensorium/Work | clear scope, immediate stop, audit, no silent resume |

## Visual-state vocabulary — 14 types

1. Initial
2. Loading
3. Empty
4. Populated
5. Editing
6. Saving
7. Success
8. Error
9. Offline
10. Permission denied
11. Approval required
12. Disabled
13. Revoked / expired
14. Degraded

Each screen declares only applicable states. `Offline` and `Degraded` are especially important in a local-first product: remote unavailability must not be presented as total product failure when local work remains available.

## Canonical approval design

Every approval presentation must answer:

- What is Vishnu asking to do?
- Why is it needed?
- What resource/service/device will be affected?
- Is the operation read-only, write or destructive?
- What exact parameters/scope are being authorized?
- Is approval one-time or persistent?
- What happens if the owner denies it?

Never use a persistent permission toggle as a substitute for an exact one-time action approval.
