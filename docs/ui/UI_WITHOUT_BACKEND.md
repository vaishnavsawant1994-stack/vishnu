# UI Without Backend / Disconnected / Placeholder Audit

**Baseline:** `4ec735de327f2bab6dccb774e2a9c28ef4fc44af`

## Result

No required canonical screen was conclusively proven presentation-only or disconnected in this source pass. That is a deliberately narrow claim: this environment did not execute every click, mutation, refresh and restart, so untested controls remain `NOT VERIFIED` rather than being declared good or broken.

## Confirmed non-defects

### PWA preview/demo datasets

`pwa/reference-pages.js` and project/product preview code can render sample records in explicit preview/demo mode. The UI labels these as sample/preview records and states that they are not saved to the owner account. Normal mode uses real API calls. These are developer/product preview facilities, not normal-production fake data.

### Desktop Owner Control Center JSON/text projections

`ui/control_panel.py` renders several runtime projections as plain JSON/text. Those views are connected to runtime authorities, so they are not fake. They are **product-quality partial UI**: useful diagnostics that should be redesigned where they remain owner-facing, rather than classified as disconnected.

## Defect candidates requiring executable confirmation

### PWA Live work vs Workflows navigation

The root PWA labels both `Live work` and `Workflows`, but both currently point to the `workflows` module key. Possible explanations include intentional aliasing or accidental duplicate navigation. Required action:

1. run the PWA;
2. activate each navigation item;
3. record rendered title/content and API calls;
4. if they are identical, keep one label for workflows and route `Live work` to WRK-001;
5. if contextual behavior differs, encode distinct stable route/module identifiers and tests.

Status: **PARTIAL / navigation ambiguity**, not yet DISCONNECTED.

### UI demo gates

Tests should assert that `uiDemo=1` or the equivalent preview flag cannot silently become normal owner state and that sample records are visibly labeled. Status: NOT VERIFIED in runtime.

### Optimistic UI / persistence

Settings, device permissions, provider configuration, project mutations, workflow controls and destructive actions must be exercised as:

`UI → API/runtime → storage → reload/restart → same canonical state`.

Static source cannot prove that every optimistic update rolls back on failure or that every returned error is rendered.

## TODO/no-op scan boundary

The first Product Truth audit generated static API/feature inventories but did not perform a framework-native full UI callback graph. This campaign traced the high-value surfaces and active navigation. A future repeatable scanner should map:

- HTML/button/Compose/SwiftUI/PyQt action nodes;
- handler/callback symbol;
- API/runtime mutation;
- persistence authority;
- success/error presentation;
- reachability from app shell.

Until that executable/static callback graph exists, this report intentionally does **not** claim there are zero no-op controls repository-wide.
