# Vishnu UI — Current Implementation Status

**Canonical blueprint merge:** `1e6e89b64ca67c77c6189d37db8e581997af75f7`  
**Implementation branch:** `codex/ui-completion-20261017`  
**Status:** source implementation campaign in qualification; no production deployment

This file is the concise current-status companion to the historical UI audit documents. Historical reports retain the counts that were true at their audited baseline; `docs/ui/ui_truth.json` is the machine-readable current authority.

## Current canonical result

- Canonical logical screens required: **63**
- Canonical screens with source implementation in some form: **63**
- PARTIAL: **58**
- EXPERIMENTAL: **5**
- MISSING: **0**
- Strict COMPLETE: **0**
- Exact-SHA visually verified canonical screens: **0**
- Source-proven Desktop/PWA/Android/iOS implementation instances: **121** across 252 classified slots
- Secondary UI families: **34**
- Major visual-state types: **14**

`0 COMPLETE` remains deliberate claim discipline. Source presence, routing, tests and backend wiring are not substitutes for final exact-SHA rendered visual, behavioral and accessibility acceptance.

## Source gaps closed in this implementation campaign

### ONB-005 — Data Placement Policy

Desktop and PWA first-run expose the canonical Data Plane policies:

- `device_only`
- `progress_only`
- `sync_everywhere`
- `on_demand`

The selected default is persisted through the existing Data Plane. The UI explicitly says changing the default does not silently move data that already exists.

### ONB-008 — Setup Review & Completion

Desktop and PWA first-run now require a review before the existing idempotent setup-completion authority is called. The review summarizes owner identity, first trusted device, security/recovery, data placement, privacy/autonomy and AI/deferred setup.

### DAT-002 — Connected Storage Provider Detail

Owner-safe provider detail is available through:

- API: `/iphone/api/data-plane/providers/{provider_id}`
- Owner page: `/iphone/api/about/storage-provider/{provider_id}`

Credential values, credential references and arbitrary provider config are omitted. Existing-data movement is not implied or performed by the read-only page.

### SEN-002 — Sensorium Status & Providers

Owner-read evidence is available through:

- JSON: `/iphone/api/about/sensorium/status`
- Owner page: `/iphone/api/about/sensorium`

It reports saved `NativeDeviceLab` qualification evidence only. The surface explicitly states that live availability is not verified, physical-device qualification is not claimed, and execution authority is false. No adb/simctl/shell/device-control console is exposed.

### SYS-003 — Updates & Release

Owner page: `/iphone/api/about/updates`

It reports installed version/build/channel and, when present, the existing governed release authority. It does not fabricate an installed-app updater: the page explicitly states that a signed in-app updater is not connected and that installation updates remain platform/installation-owner managed.

### SYS-004 — About / Version / Notices

Owner identity is available through `/iphone/api/about` and the dedicated notices page `/iphone/api/about/notices`. It exposes safe build/version information, proprietary `All Rights Reserved` identity, third-party notice guidance and Privacy/Security/Updates links.

## Older UI branches

The older 29-screen and 30-screen draft inventories are superseded. Their useful functional changes were reconciled into the current implementation branch; their taxonomies are not canonical.

## Remaining acceptance campaign

Before any screen may be promoted to strict COMPLETE, its declared platform scope still needs applicable evidence for:

- real route/navigation reachability;
- authoritative reads and governed writes;
- persistence across refresh/restart where expected;
- loading, empty, error, offline/degraded, denied and approval states;
- responsive phone/tablet/laptop/desktop behavior;
- keyboard navigation/focus behavior;
- screen-reader semantics and announcements;
- text scaling / Dynamic Type / font scaling where applicable;
- contrast and Reduce Motion behavior;
- exact-SHA rendered evidence;
- security boundaries and secret redaction.

The five experimental screens remain explicitly experimental until separately qualified or deliberately retained as advanced experimental surfaces. No production deployment is part of this UI implementation campaign.
