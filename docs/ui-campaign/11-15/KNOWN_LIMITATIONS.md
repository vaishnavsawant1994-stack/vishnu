# Known limitations and blockers

- Global Search currently searches only the existing Conversations and Projects list APIs. Workspaces, Work, Files, Agents, Memory, Knowledge, Artifacts, Devices, Evidence and other types are not indexed by this module.
- Project-result navigation is wired to the existing Projects module and the selected project is loaded by ID. A browser journey now exercises the real project detail route; other project result types and authenticated owner-session behavior still need broader qualification.
- Search results and visual design have not been integration-tested against the active owner session or compared as screenshots to the approved references in this slice.
- Existing History and Voice functionality is not certified to every detail of Screens 13 and 14; persistence, native microphone route behavior, transcript reconciliation, inspector and voice controls need journey tests.
- PyQt6 desktop and Android/iOS companion apps remain separate product surfaces; the latter launch the PWA in an external browser. The same screens are not implemented inside every installed app.
- No macOS/iPadOS build or physical Android/iOS qualification was performed.
- No deployment, commit, push, merge, or PR was performed.

These gaps mean cross-platform completion is not achieved yet.

## Follow-up verification (2026-10-20)

- Compared the generated Home preview capture at `artifacts/campaign-demo/home-desktop.png` with the user-supplied Screen 11 Home reference. The layout is directionally similar, but spacing, controls, icon treatment, shell detail, and some content hierarchy differ. This is not a screenshot-match pass.
- Re-ran focused contracts: `python -m pytest tests/test_genesis_native_ui_contract.py tests/test_p3_iphone_pwa.py tests/test_first_run_onboarding.py -q` passed (59 tests).
- Re-ran desktop/mobile campaign preview journeys and the live local web route check; both passed. They qualify the read-only browser preview only, not authenticated owner data or native apps.
- The complete Python suite is currently not green: `python -m pytest -q` reported 3,793 passed, 72 failed, and 2 skipped. Failures include at least a Windows newline expectation, a SQLite temporary-file lock, and a stale service-worker cache-version assertion; the remaining failures have not been triaged and are not claimed as unrelated.
- Updated two service-worker cache-version UI contracts from v45 to the current v46. Fixed Global Search project selection to open the selected project through the canonical project module, and expanded the browser journey to load the actual project detail view rather than stubbing navigation.
- This environment has no Gradle executable/wrapper and no `xcodebuild`, so Android and iOS package builds could not be qualified. Windows app launch was observed, but the two open native windows made the UI automation target ambiguous; no native screenshot acceptance is claimed.
