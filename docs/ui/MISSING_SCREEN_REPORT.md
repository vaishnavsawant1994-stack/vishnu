# Vishnu Missing Screen Report

**Audited baseline:** `4ec735de327f2bab6dccb774e2a9c28ef4fc44af`  
**Canonical screens required:** 63  
**Genuinely missing canonical screens:** 6

This report contains only owner concepts that were not represented sufficiently by any current visible implementation. A screen is not marked missing merely because one platform lacks parity.

## P1 — ONB-005 Data Placement Policy

**Why required:** Vishnu already has canonical local-first placement policies: `device_only`, `progress_only`, `sync_everywhere`, `on_demand`. First-run should make that owner decision explicit rather than silently inheriting a default.

**Parent/navigation:** First Run → Privacy & Autonomy → Data Placement → AI Provider.  
**Features represented:** local-first ownership, sync policy, offline behavior, cloud optionality.  
**Backend already available:** yes, data-plane/storage policy authority exists.  
**Security:** policy changes must use canonical owner/device authority; no parallel preference store.  
**Required components:** policy cards, plain-language consequences, local/cloud indicator, confirmation, offline explanation.  
**Platforms:** Desktop, PWA first-device flow, iOS first-device flow, Android when native first-device creation is supported.  
**Priority:** P1.  
**Implementation recommendation:** bind directly to the existing canonical policy authority and persist before final setup review.

## P1 — ONB-008 Setup Review & Completion

**Why required:** first-run needs one final owner-verifiable summary before Home.

**Parent/navigation:** First Run final step.  
**Features represented:** Vishnu identity, first trusted device, authentication state, recovery readiness, chosen data policy, chosen AI provider/model.  
**Backend already available:** mostly yes; values are created earlier in onboarding.  
**Security:** must not display secrets/recovery material after acknowledgement; final commit must remain idempotent.  
**Required components:** summary sections, warnings for unresolved mandatory setup, back/edit links, `Enter Vishnu` primary action.  
**Platforms:** every supported first-device platform.  
**Priority:** P1.  
**Implementation recommendation:** make this a review/commit step, not another duplicate persistence authority.

## P1 — DAT-002 Connected Storage Provider Detail

**Why required:** if an owner connects remote/cloud storage, they must be able to understand the provider, destination, health, consent, movement and failure state.

**Parent/navigation:** Settings → Data & Storage → Connected Storage → provider.  
**Features represented:** provider connection, capability/health, selected destination, allowed data classes, transfer evidence, disconnect/revoke.  
**Backend already available:** storage-fabric/provider and data-plane authorities exist, but owner-facing provider detail is incomplete.  
**Security:** never redisplay secrets; destructive disconnect/movement must explain impact and use canonical confirmation/approval.  
**Required components:** provider identity, connection/health status, data classes, location, last sync/transfer evidence, reconnect/disconnect actions, offline/degraded states.  
**Platforms:** Desktop/PWA; native companion parity only if native provider management is intended.  
**Priority:** P1.  
**Implementation recommendation:** project canonical provider/storage evidence; do not infer successful movement from a UI click alone.

## P2 — SEN-002 Sensorium Status & Providers

**Why required:** Sensorium has owner-relevant provider availability/status/evidence beyond per-sensor permission switches.

**Parent/navigation:** Advanced → Sensorium → Status & Providers.  
**Features represented:** provider type, availability, current device, degraded/unavailable state, evidence summary.  
**Backend already available:** yes, including native-device-lab/provider status/evidence APIs.  
**Security:** read-only owner projection; do not expose arbitrary ADB/simctl execution or sensitive sensor payloads.  
**Required components:** provider rows, availability badges, evidence timestamp/summary, troubleshooting guidance.  
**Platforms:** Desktop/PWA owner management.  
**Priority:** P2.  
**Implementation recommendation:** keep low-level lab mechanics in Advanced/Diagnostics.

## P3 — SYS-003 Updates & Release

**Why required:** update/release infrastructure should have one owner-facing lifecycle instead of scattered technical state.

**Parent/navigation:** Settings → Updates or System → Updates.  
**Features represented:** current version, update available, release notes, verification, install/restart status, failure/recovery.  
**Backend already available:** update/release infrastructure exists, but owner projection is incomplete.  
**Security:** verified artifacts only; never imply an update is installed until verification/install evidence says so.  
**Required components:** version card, update state, release notes, verify/install/restart flow, error recovery.  
**Platforms:** Desktop first; PWA/native only where update ownership actually belongs to Vishnu rather than the browser/app store.  
**Priority:** P3.

## P3 — SYS-004 About / Version / Notices

**Why required:** owner should be able to discover installed version/build, proprietary license posture and third-party notices.

**Parent/navigation:** Settings → About.  
**Features represented:** Vishnu version/build, license, third-party notices, links to privacy/security/update status.  
**Backend already available:** metadata/release files exist.  
**Security:** no secret configuration or private diagnostics.  
**Required components:** version/build rows, license summary, notices, update link.  
**Platforms:** Desktop/PWA and native About surface where appropriate.  
**Priority:** P3.

## Corrected non-missing item — SET-005 Accessibility

`SET-005` is **PARTIAL**, not missing. Desktop `SettingsPanel` already exposes and persists **Reduce motion** and **High contrast**. Reduced motion is applied to the active pulse immediately; high-contrast state is persisted for full application after restart. Remaining work is organization/discoverability, appropriate PWA parity, OS-managed native behavior and complete accessibility acceptance testing.

## Implementation order

1. ONB-005 Data Placement Policy.
2. ONB-008 Setup Review & Completion.
3. DAT-002 Connected Storage Provider Detail.
4. SEN-002 Sensorium Status & Providers.
5. SYS-003 Updates & Release.
6. SYS-004 About / Version / Notices.

Do not build these as duplicate authorities. Each missing UI must project or mutate the existing canonical backend/security/storage authority and prove persistence/action results after refresh/restart where applicable.
