# UI with unavailable, preview-only, or unverified backend behavior

**Baseline:** `4ec735de327f2bab6dccb774e2a9c28ef4fc44af`

| Surface/control | Source evidence | Classification | Required action |
|---|---|---|---|
| Privacy settings: project-context, conversation-retention, save-conversations, telemetry controls | `pwa/index.html` privacy renderer marks controls disabled and explains installation limitations | Partial / intentionally disabled; not a fake active toggle | Keep disabled with reason until the service exists; verify remaining active controls persist |
| Account deletion and project-context permissions | Same renderer states required services are absent in this installation | UI copy present; backend action unavailable | Do not imply success; wire only after owner verification and persistence path exists |
| iOS cloud and Capability Forge controls | `PersonalAICompanionApp.swift` explicitly marks cloud/Forge cloud controls disabled in internal-testing build | Blocked by build/runtime configuration | Keep state visible; enable only with configured non-production server and verified auth path |
| PWA preview/demo-mode data | `sectionPreviewMode()` branches in Knowledge and related PWA code | Experimental/preview behavior | Confirm production routes cannot mistake preview data for owner data; maintain visible preview notice |
| Provider, device, data and notification status surfaces | Source exists; live mutations/provider delivery not executed in this campaign | Not verified, therefore partial | Run UI/API tests for save→reload and failure; correct stale state and errors if found |

No control is declared “fake” without direct behavioral execution. Explicitly disabled or preview-only paths are recorded as such; other uncertain controls are NOT VERIFIED.
