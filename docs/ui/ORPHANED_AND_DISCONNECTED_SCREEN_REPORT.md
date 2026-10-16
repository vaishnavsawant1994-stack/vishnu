# Orphaned & Disconnected Screen Report

**Baseline:** `4ec735de327f2bab6dccb774e2a9c28ef4fc44af`

## Proven orphaned canonical screens: 0

No required canonical screen was proven unreachable after tracing the active composition paths that matter most:

- Desktop launches `CanonicalMainWindow`, not the older base class directly; this makes `Our Products` an active destination and wires Data & Cloud Storage / mobile pairing actions.
- PWA Agents and Our Products pages are injected into live navigation and have server asset routes.
- iOS Sensorium Privacy and Capability Forge V3 are reached by explicit `NavigationLink`s.
- PWA account menu explicitly reaches Settings, Trusted Devices and System Status.

This is not a claim that every UI file in the repository is instantiated. A complete import/route/runtime graph is still needed before declaring the repository free of dead UI modules.

## Orphan candidates requiring future static/runtime graph analysis

- old compatibility/legacy UI classes that are inherited or retained for tests;
- dialogs created only under feature flags/configuration;
- qualification/lab screens whose route is enabled only in specific compositions;
- HTML/JS modules retained as assets but potentially superseded by injected runtime navigation.

Rule: do not delete any candidate until imports/instantiation, routes/deep links, tests and compatibility use are proven absent.

## Proven disconnected canonical screens: 0

The high-value screens inspected have real runtime/API owners. No canonical screen was proven to be a visual shell with no product authority.

## Disconnection candidate: PWA Live work / Workflows

Two visible navigation labels currently map to the same `workflows` module identifier. This can cause either a duplicate destination or incorrect user mental model. It is classified as **navigation ambiguity**, not DISCONNECTED, until a browser interaction test records each click's rendered view and API requests.

## Required verification to close this report

Build a repeatable UI trace graph that records:

`visible control → event handler → client/API call → authorization/approval → mutation/read → storage/effect → returned result → UI update/error`.

For each screen also record `app launch → navigation path → screen instance` and valid deep links. Only then may the audit assert repository-wide zero orphan/no-op/disconnected controls.
