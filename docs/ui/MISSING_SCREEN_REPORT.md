# Missing Screen Report

**Baseline:** `4ec735de327f2bab6dccb774e2a9c28ef4fc44af`

Seven canonical owner concepts are missing. These are not seven arbitrary new top-level navigation entries; each is placed in an existing flow/Settings/Advanced location.

## ONB-005 — Data Placement Policy — P1

**Why required:** local-first placement is a core owner decision and four canonical policies already exist in the architecture. First-run currently chooses privacy/autonomy and model provider but not data placement.  
**Parent:** Create Vishnu → Privacy & Autonomy → **Data Placement** → AI Provider.  
**Backend available:** yes, Data Plane policy and storage settings architecture.  
**Required UI:** four option cards for `device_only`, `progress_only`, `sync_everywhere`, `on_demand`; plain-language examples; local/cloud availability; no-silent-movement statement.  
**Security:** owner-only; policy change cannot silently transfer existing data.  
**Platforms:** Desktop, PWA, Android/iOS first-device creation.  
**Implementation:** persist selection in canonical policy authority; add resume-safe migration for interrupted setup; test reload/restart.

## ONB-008 — Setup Review & Completion — P1

**Why required:** current setup can finish without one clear owner summary.  
**Parent:** Recovery Codes → **Review & Finish** → Home.  
**Backend available:** identity, trusted device, data policy, recovery and provider state are individually available.  
**Required UI:** owner/display name, first trusted device, auth method, recovery readiness, data policy, AI provider/model, deferred items, `Enter Vishnu`.  
**Security:** no secrets/recovery code values in final summary.  
**Platforms:** every first-device creation platform.  
**Implementation:** read existing setup state, never duplicate creation; finalization must be idempotent.

## DAT-002 — Connected Storage Provider Detail — P1

**Why required:** the storage fabric can reason about providers/transfers, but owner needs visibility before real remote movement.  
**Parent:** Settings → Data & Storage → Connected Storage → provider.  
**Backend available:** provider capability/health/transfer/storage-fabric foundation.  
**Required UI:** provider/account label, destination, capability/health, credential-present state, encryption statement, explicit sync/transfer status, last error, disconnect and retry/cancel.  
**Security:** never reveal credential value; movement requires explicit policy/confirmation; provider failure cannot imply local-data loss.  
**Platforms:** Desktop/PWA.  
**Implementation:** start read-only health/detail first; only expose movement mutations already governed by Data Plane authority.

## SET-005 — Accessibility — P1

**Why required:** reduce-motion/high-contrast behavior exists but is not a coherent discoverable setting.  
**Parent:** Settings → Accessibility.  
**Backend available:** preferences/runtime and existing design tokens/CSS.  
**Required UI:** follow-system where applicable, Reduce Motion, High Contrast and only other accommodations Vishnu truly supports.  
**Security:** normal owner preference, no special privilege.  
**Platforms:** Desktop/PWA; native apps should primarily honor OS settings.  
**Implementation:** persist preference; assert visual classes/token changes after reload; add keyboard/screen-reader labels.

## SEN-002 — Sensorium Status & Providers — P2

**Why required:** advanced owners need to understand provider availability/qualification, while current native Sensorium UI focuses correctly on local consent.  
**Parent:** Settings → Advanced → Sensorium.  
**Backend available:** provider/status/evidence APIs for virtual/native/emulator/simulator/VM paths.  
**Required UI:** provider type, availability, associated device, qualification level, evidence timestamp, limitations.  
**Security:** read-only; no arbitrary ADB/simctl/shell command surface.  
**Platforms:** Desktop/PWA Advanced.  
**Implementation:** read-only projection with explicit `NOT VERIFIED` / simulator vs physical-device labels.

## SYS-003 — Updates & Release — P3

**Why required:** owner should know installed version and update status without using repository tooling.  
**Parent:** Settings → Updates.  
**Backend available:** update/package/release verification infrastructure.  
**Required UI:** current build, update available, release notes, signature/verification status, download/apply/restart state, failure recovery.  
**Security:** update must preserve existing release verification; no automatic production promotion.  
**Platforms:** Desktop/PWA as deployment architecture permits.  
**Implementation:** begin as read-only version/update availability if self-update mutation is not yet canonical.

## SYS-004 — About / Version / Notices — P3

**Why required:** product/version/license identity should be discoverable.  
**Parent:** Settings → About.  
**Backend available:** build/version metadata, proprietary license posture and third-party dependency notices.  
**Required UI:** Vishnu name/version/build, proprietary notice, third-party notices, Privacy/Security/Updates links.  
**Security:** no secrets/host internals.  
**Platforms:** Desktop/PWA.  
**Implementation:** static/runtime metadata projection with copyable build identifier.
