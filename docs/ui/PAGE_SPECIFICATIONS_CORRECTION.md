# Page Specifications Corrections

**Canonical blueprint baseline:** `1e6e89b64ca67c77c6189d37db8e581997af75f7`  
**Implementation evidence baseline:** `9adae5922e1a40b5e3cbaa86b4d6919e535a5b27`

This amendment supersedes stale status lines in `PAGE_SPECIFICATIONS.md` where later source implementation has changed the classification. It does **not** mark any screen strict COMPLETE; exact-SHA rendered visual, behavioral and accessibility acceptance remains outstanding.

## SET-005 — Accessibility

The historical line `Status: MISSING, P1` is superseded by the following source-proven truth:

- **Status:** PARTIAL, P1.
- **Exists:** yes on Desktop inside `ui/settings_panel.py`.
- **Reachable:** yes through Desktop Settings.
- **Backend/persistence:** `SettingsPanel.save()` persists `reduce_motion` and `high_contrast` through the existing preferences authority.
- **Runtime behavior:** reduced motion is applied to the active pulse immediately; high-contrast preference is persisted and the UI tells the owner full application occurs after restart.
- **PWA:** no equivalent coherent owner Accessibility subsection is claimed complete by this implementation slice.
- **Native:** use operating-system accessibility behavior by default; add app-specific controls only when Vishnu genuinely owns the setting.
- **Remaining work:** full keyboard/screen-reader/touch/contrast acceptance and web parity.

## ONB-005 — Data Placement Policy

- **Status:** PARTIAL, P1.
- **Desktop:** implemented in `ui/first_run_wizard.py` between Privacy and AI Provider.
- **PWA:** implemented in `pwa/first-run.js` / `pwa/first-run-actions.js`.
- **Authority:** the canonical Data Plane; exactly `device_only`, `progress_only`, `sync_everywhere`, `on_demand`.
- **Boundary:** changing the first-run default does not silently move existing data.
- **Not claimed:** Android/iOS first-device parity or rendered visual acceptance.

## ONB-008 — Setup Review & Completion

- **Status:** PARTIAL, P1.
- **Desktop/PWA:** a final review now summarizes owner, trusted device, security/recovery, data placement, privacy/autonomy and AI/deferred setup.
- **Authority:** Finish still calls the existing idempotent first-run completion authority; the UI does not create a second identity authority.
- **Not claimed:** Android/iOS parity or exact-SHA visual/a11y acceptance.

## DAT-002 — Connected Storage Provider Detail

- **Status:** PARTIAL, P1.
- **PWA owner deep link:** `/iphone/api/about/storage-provider/{provider_id}`.
- **Backend:** `/iphone/api/data-plane/providers/{provider_id}` and the canonical Data Plane provider registry/status.
- **Contents:** provider label/category, connection/consent state, safe destination metadata, capabilities, verification, reported error/sync state and a protection statement.
- **Security:** credential values, credential references and arbitrary provider config are deliberately omitted.
- **Boundary:** the detail page is read-only; data movement remains a separate governed action.

## SEN-002 — Sensorium Status & Providers

- **Status:** PARTIAL, P2.
- **PWA owner deep link:** `/iphone/api/about/sensorium`.
- **Read API:** `/iphone/api/about/sensorium/status`.
- **Authority:** saved `NativeDeviceLab` qualification evidence and canonical provider profiles.
- **Boundary:** the surface explicitly reports `physical_device=false`, `execution_authority=false` and `live_availability_verified=false`; it exposes no adb, simctl, shell, keyboard/mouse or app-launch execution authority.

## SYS-003 — Updates & Release

- **Status:** PARTIAL, P3.
- **PWA owner deep link:** `/iphone/api/about/updates`.
- **Contents:** installed version/build/channel plus governed release-authority availability/status where present.
- **Truth boundary:** Vishnu does **not** claim an installed-app updater. The page explicitly says a signed in-app updater is not connected and platform/installation-owner management remains authoritative.
- **Release control:** when the existing governed release authority is available, the page links to it; production promotion continues to require its canonical authority and policy.

## SYS-004 — About / Version / Notices

- **Status:** PARTIAL, P3.
- **Existing PWA Settings surface:** About & Updates reads `/iphone/api/about`.
- **Owner deep link:** `/iphone/api/about/notices`.
- **Contents:** Vishnu version/build, proprietary `All Rights Reserved` identity, third-party notice guidance, Privacy/Security and Updates links.
- **Not claimed:** final legal-notice packaging acceptance or exact-SHA rendered acceptance.

## Current source-presence totals

`docs/ui/ui_truth.json` is the machine authority for this implementation branch and now records:

- canonical required: **63**
- source-present canonical: **63**
- strict complete: **0**
- partial: **58**
- experimental: **5**
- missing: **0**
- source-proven platform implementation instances: **121**
- visually verified canonical screens: **0**

These totals mean every canonical owner task now has source implementation in some form. They do **not** mean all 63 pages are product-accepted. Responsive/browser/native rendering, full behavior, keyboard, screen-reader, text-scaling, contrast and other exact-SHA acceptance work remains separate.
