# UI surface inventory

**Baseline SHA:** `a8d3310b4d9090a42800621b1b27cb6045443c1e`.

## Surface inventory

| Surface | Source roots | Known screen families | Current audit status |
|---|---|---|---|
| Desktop | `desktop/`, `app/` | first-run/access, main conversation, owner/settings, memory, products, device/capability and qualification panels | Source inventory present; runtime rendering and every button's backend result not exhaustively executed |
| PWA/web | `pwa/`, `server/iphone_pwa.py`, `server/cloud_app.py` | first run/access, Home/chat, conversations, Memory, Knowledge, Projects/Work, Products, Visualize, Apps/Tools, owner/security/data/voice controls | Richest browser surface; route reachability/responsive behavior depends on workflow evidence and was not exhaustively manually clicked in this pass |
| Android | `android-companion/app/src/main/` | connect/onboarding, passkey, provisioning, portable recovery, Data Plane, Sensorium/privacy, camera, VoiceStudio Forge | Native activities/services exist; instrumentation is defined; physical phone flow not verified here |
| iOS | `ios-companion/PersonalAICompanion/` | connect/onboarding, passkey, provisioning, portable recovery, Data Plane, Sensorium/privacy/camera/audio, native capabilities/Forge | SwiftUI sources/tests exist; simulator workflow available; physical iPhone flow not verified here |
| Owner and qualification consoles | server owner UI/API routers, `voice/lab`, `intelligence_lab`, `future_intelligence` | release control, work/agent surfaces, Voice Lab, product runners, capability/Forge, Sensorium qualification | Advanced/owner-gated; not equivalent to normal owner product navigation |
| Installer/package | `installer/`, `packaging/`, `updates/`, `.github/workflows/` | setup/build/package/update workflows | Mostly build/qualification surfaces; signed external distribution not verified |

## Specific existing screen evidence

- PWA assets include `index.html`, `first-run.js`, `home-chat-redesign.js`, `knowledge-notes.js`, `memory-experiences.js`, `projects-workspace.js`, `our-products.html`, `visualize-workspace.js`, `agents.html`, `owner-controls.js`, `adaptive-composer.js`.
- Android includes `MainActivity`, `ConnectActivity`, `PasskeySetupActivity`, `RuntimeProvisioningActivity`, `PortableRecoveryActivity`, Sensorium activities/services and `ForgeV3Activity`.
- iOS includes `PersonalAICompanionApp`, `ConnectOnboardingView`, `NativePasskeyView`, `RuntimeProvisioningView`, `PortableRecoveryView`, Sensorium views/sessions and `NativeForgeV3`.
- Desktop source has 15 files; a full live GUI screen capture set was not generated.

## Definition and gaps

A screen is only counted as implemented when it renders, can be reached, loads expected data, invokes the real authority, reflects success/failure, persists required state and has security/test evidence. This source inventory does not establish those checks for each control. Detailed source paths and known navigation edges are in `NAVIGATION_MAP.md`; static API decorators are in `api_inventory.json`.
