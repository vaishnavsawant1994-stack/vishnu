# Workspace data and UI implementation slice

This is a local development implementation slice for approved Screens 17–20, not a claim of exact-match or cross-platform completion.

## Data behavior

- Workspace records are persisted in a dedicated SQLite database at the configured local data directory (`workspaces.sqlite3`). They do not depend on a hosted database.
- Nothing is created automatically at startup. “Import reference demo” explicitly creates an idempotent `Rudra Health Care · Reference Demo` record, marked illustrative and not a real customer.
- Projects are listed from the existing canonical Project API and linked by ID. A Workspace relationship does not copy or rename a Project.
- Studio persists bounded layout information and references only; the API rejects arbitrary embedded resource contents.
- Current runtime ownership is bound to its single canonical `owner` identity. Multi-owner account lifecycle needs further identity-authority integration.

## UI behavior

- The Labs entry opens a responsive Workspaces library with search, basic filters, pin/archive, creation templates and opt-in reference fixture.
- Creation saves a name, type and description/idea, then opens the persisted Workspace.
- Overview displays actual Workspace metadata and linked canonical Projects. Other resource groups are explicitly empty/not linked rather than showing invented totals.
- Studio supports a saved default view with a bounded set of layout panels. It is not yet the full interactive, populated 2D workbench in reference 20.
- Desktop browser and narrow mobile-browser journeys are covered in `tests/workspaces_browser.mjs`; API persistence and authorization behavior are covered in `tests/test_workspaces_api.py`.

## Known limits

Screens 17–20 are partial. Other resource families, Workspace-scoped chat, collaboration/sharing, access policy UX, full Studio panel types/geometry interactions, image-level comparison and native app parity remain incomplete. Existing native applications do not currently host this web surface. The only verified surface in this slice is the local web/PWA browser flow.
