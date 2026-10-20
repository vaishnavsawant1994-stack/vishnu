# Screens 16–20 architecture decision (interim)

Date: 2026-10-20. Status: a bounded web implementation exists; native security review and full Workspace domain integration remain open.

## Current design

The existing responsive PWA is the first implementation surface. Screen 16 remains a safe web adapter over existing navigation/conversation functions. Workspace is now an independent owner-scoped local SQLite domain (`workspaces/store.py`), exposed through the authenticated `server/workspaces_api.py` router. Existing `ProjectStore` records can be linked by reference; they are not copied or treated as Workspaces. Workspace Studio stores bounded panel geometry and resource references, never arbitrary resource contents.

No Workspace example is seeded at application startup. A user may explicitly import one idempotent, clearly labeled reference-demo record for development. New Workspace CRUD and links persist locally; current owner binding assumes the runtime’s single canonical owner and requires future identity lifecycle integration.

## Still required before claiming parity

- Add actual links and UI for other canonical resource families; do not fabricate counts/content.
- Complete Workspace-aware conversation/chat and Studio panel functionality.
- Resolve multi-owner isolation and lifecycle against the product identity authority.
- Capture actual screenshots and compare against the approved desktop/mobile references.
- Qualify separate native applications and their secure session/device integration. Do not add a WebView or framework without a threat-model review of session, origin, passkeys, file access, sensors, packaging and bridges.

## Explicit non-decisions

- No claim of exact screenshot match, all-screen completion, native parity, production readiness or full suite qualification.
- No automatic customer/demo records or fake resource counts are inserted.
- No production deployment, merge, commit or push was performed.
