# Vishnu Owner Guide — What You Can Use Today

**Applies to audited main:** `5e2b88bff46bca2d4d212731ddad37fe59a7e88a`  
**Date:** 2026-10-17

This guide explains the product in owner language. It deliberately distinguishes implemented source from exact production/provider/physical-device acceptance.

## 1. Start Vishnu

### Desktop

Launch the desktop application through the normal Vishnu desktop entry point. The canonical desktop shell is `CanonicalMainWindow`.

Current top-level desktop destinations:
1. Home
2. Conversation
3. Memory
4. Knowledge
5. Activities
6. Dashboard
7. Apps & Tools
8. Our Products
9. Settings

**Limitation:** Desktop does not currently have parity with the PWA for several secondary screens such as Projects, Inbox, Live Work and detailed device/storage/security pages.

### Web/PWA

Open the configured trusted Vishnu web/PWA endpoint. The PWA is the broadest owner product today.

### Android / iPhone / iPad

Use the native companion primarily for OS-bound tasks: create/connect/restore, trust/provisioning/passkeys, selected capabilities, Sensorium permissions and recovery. Use **Open Vishnu** / the trusted PWA for the full owner workspace.

**Important:** simulator/emulator success is not the same as physical-device acceptance.

## 2. Create, join or restore Vishnu

### Where

Welcome / first-run flow.

### What you can do

- **Create my Vishnu** — create owner identity and first trusted device.
- **I already have Vishnu** — authenticate and enroll this device.
- **Restore Vishnu** — use supported recovery authority/package/code to regain access and establish a trusted device.

### Current setup concepts

The source includes owner identity, security setup, privacy/autonomy, AI provider setup, recovery codes, Data Placement Policy and a final Setup Review.

### Data-placement choices

- `device_only`
- `progress_only`
- `sync_everywhere`
- `on_demand`

Changing the default placement policy does **not** mean Vishnu silently moves existing data.

### Limitation

The repository has cross-platform source, but a complete fresh-device Create → Join → Restore acceptance run has not been proven on every declared platform at one exact SHA.

## 3. Talk to Vishnu

### Where

- Desktop: **Conversation**
- PWA: **Home → composer**

### How

1. Open Home/Conversation.
2. Type a request.
3. Send it.
4. Open conversation history when you need an older thread.
5. If Vishnu proposes a governed action, review the permission/approval prompt instead of assuming the action is automatically allowed.

### Internally

Conversation → owner/session context → model/agent routing → Memory/Knowledge retrieval where applicable → governed tool/capability decision → approval/security → result/audit → response.

### Limitation

Live model/provider behavior depends on configured provider accounts/credentials and has not been universally accepted across all platforms/providers.

## 4. Use Voice

### Where

- conversation microphone/voice controls
- **Settings → Voice**
- Desktop **Voice Studio** for advanced voice configuration
- **Voice Lab** only for experimental/qualification work

### How

1. Grant microphone permission when required.
2. Choose/configure the supported voice/provider behavior.
3. Speak to Vishnu.
4. Vishnu routes the turn through the conversation runtime.
5. If TTS is configured, the response can be synthesized to audio.

### Advanced integrations

OpenVoice and VoiceStudio adapters exist, but their local/external model/runtime prerequisites must actually be installed/configured.

### Limitation

Real provider accounts, physical microphones/speakers, acoustic performance and telephony are not universally qualified. Voice Lab/telephony is default-off experimental/governed functionality.

## 5. See what Vishnu remembers

### Where

- Desktop: **Memory**
- PWA: **Home → Memory**

### How

1. Open Memory.
2. Browse or search remembered information.
3. Open a Memory detail to understand the item and, where supported, why it was retrieved.
4. Use available owner controls to manage/govern remembered information.

### Internally

Memory UI → Memory owner/governance API → Memory store/shared SQLite → retrieval into conversation context.

### Limitation

The complete mutation/retrieval/governance/restart lifecycle has focused coverage but is not yet accepted as a single strict cross-platform E2E journey.

## 6. Use Knowledge and files

### Where

- Desktop/PWA: **Knowledge**
- PWA: **Knowledge → Add Source/Upload**
- Conversation attachments may also enter the content-ingestion path.

### How

1. Open Knowledge.
2. Add/upload a supported source.
3. Allow Vishnu to parse/index supported content.
4. Open a source to inspect it.
5. Ask Vishnu questions that can retrieve Knowledge context.

### Internally

Source/file → content ingestion → File Intelligence parser/extractor → Knowledge store/index → retrieval → owner/conversation result.

### Limitation

OCR/model/format coverage varies by optional dependencies and real-world corpus qualification. Source presence is not a guarantee that every document/audio/video format is accepted perfectly.

## 7. Apps & Tools

### Where

**Apps & Tools** on Desktop/PWA.

### Use it for

- built-in tools/integrations
- connected services
- Universal Capabilities
- governed external tool access

### Security rule

External integrations should project through existing ToolRegistry/Capability/Approval/SecretVault authorities instead of creating separate ungoverned execution paths.

## 8. Add an OpenAPI capability

### Where

**Apps & Tools → Capabilities → Add → OpenAPI**

### How

1. Open Capabilities.
2. Choose Add Capability/OpenAPI.
3. Import/provide the supported OpenAPI description.
4. Review discovered operations/risk.
5. Configure credentials when needed.
6. Review permissions/approval requirements.
7. Save/connect.
8. Use the capability through Vishnu.
9. Inspect/revoke/rotate from Capability Detail when needed.

### Internally

Capability UI → owner API → catalog/service → risk/policy → ApprovalManager → SecretVault → ToolRegistry → bounded OpenAPI execution → audit/result.

### Limitation

Fixture/security qualification does not guarantee arbitrary third-party API compatibility or provider-side OAuth/consent.

## 9. Add an MCP capability

### Where

**Apps & Tools → Capabilities → Add → MCP**

### How

1. Add/configure the MCP endpoint/process supported by the integration.
2. Review discovered tools/schema.
3. Review risk/permissions.
4. Approve governed writes where required.
5. Use the projected tools through Vishnu.

REA and VoiceStudio are examples of integrations that can project capabilities through the governed MCP/ToolRegistry path.

### Limitation

An MCP server’s presence does not automatically make it trusted or production-qualified.

## 10. REA reverse-engineering integration

### What it is

Vishnu’s canonical REA integration comes from PR #224 and uses official REA 6.5.0 through local stdio MCP.

### How to use

1. Ensure the external REA/Node/native-analysis prerequisites are installed.
2. Configure/start the integration through its supported Vishnu capability path.
3. Use discovered REA tools through Vishnu’s governed ToolRegistry/approval system.

### Limitation

REA and many underlying native-analysis tools have their own runtime/binary/license prerequisites. REA is not a sandbox by itself.

## 11. Manage AI models/providers

### Where

**Settings → AI Models & Providers**

### How

1. Open provider settings.
2. Add/configure a supported provider.
3. Store credentials through the supported secret path.
4. Choose routing/provider settings where exposed.
5. Test through conversation/work.

### Limitation

Each external provider has independent credential, OAuth, consent, expiry/revocation and availability behavior. A configured provider is not automatically production-accepted.

## 12. Manage devices

### Where

- PWA/Desktop owner controls: **Settings/More → Devices**
- Native companion: **Connect / This Device / Trust**

### How to add a device

1. Open Devices/Add Device or native Connect.
2. Authenticate the owner.
3. Use the supported QR/pairing code/token/deep-link/passkey flow.
4. Approve the new device where required.
5. Review scopes/trust.
6. Confirm the device is registered.

### Lost device

**Settings → Devices → Device Detail → Mark Lost/Revoke** where supported.

### Internally

Owner session → DeviceRegistry → trust/scopes → DeviceGateway → trusted device.

### Limitation

Desktop/Android Device Detail parity is incomplete, and real physical-device enrollment/revocation needs exact-SHA acceptance.

## 13. Data & Storage

### Where

**Settings → Data & Storage**

### What you can control

- default placement policy
- configured provider readiness/detail where available
- local/cloud behavior governed by the Data Plane

### How

1. Open Data & Storage.
2. Review current policy and provider state.
3. Change the default policy if desired.
4. Confirm the policy change.
5. Open a provider detail to inspect safe status/health information.

### Important rule

Changing policy affects newly governed placement behavior. It does **not** silently migrate existing data.

### Limitation

Live remote provider transfer/consent/restore acceptance is still externally blocked/unfinished.

## 14. Projects

### Where

PWA: **Home → Projects → Project Workspace**

### How

1. Open Projects.
2. Create/open a project.
3. Add goals/tasks/work.
4. Inspect Live Work, evidence and activity where available.
5. Continue or recover work through the project/work surfaces.

### Limitation

Desktop project parity is incomplete. The PWA is the stronger owner surface for Projects today.

## 15. Live Work

### Where

PWA: **Home → Live Work → Work Detail**

### What it shows

Durable work, attempts/progress/evidence/claims/completion/recovery information.

### Limitation

Current historical audit found a navigation ambiguity because `Live work` and `Workflows` may share a module key. Treat this as PARTIAL until executable route/content/API behavior is confirmed.

## 16. Automations / Workflows

### Where

**Automations / Workflows** in the PWA/owner controls.

### How

1. Create/configure a workflow/automation.
2. Choose trigger/schedule/event behavior supported by the product.
3. Review permissions and external dependencies.
4. Run/enable it.
5. Inspect run history and errors.

### Limitation

Actual recurring/background execution depends on a runtime being deployed/running and correctly configured. UI/source presence alone does not keep an automation alive.

## 17. Inbox / Attention

### Where

PWA: **Home → Inbox/Attention**

### Use it for

- approvals requiring your decision
- recovery/continuation attention
- evidence/review events
- important work states

### Limitation

Desktop parity is incomplete.

## 18. Activity

### Where

- Desktop: **Activities**
- PWA: **Activity**

### Use it for

Reviewing timeline/evidence/work/security-relevant activity projected by supported systems.

## 19. Approvals

### Where

Approval prompts and **Approvals Center** where exposed.

### What happens

Vishnu should require canonical ApprovalManager/policy approval for governed risky writes instead of allowing integrations to invent their own bypass.

### Limitation

The audit has not route-by-route proven that every possible write endpoint invokes the complete desired approval chain.

## 20. Security

### Where

**Settings → Security**

### Owner tasks

- review sign-in methods/sessions
- review security/audit history where available
- manage sensitive account/device/capability state
- reauthenticate for protected actions

### Limitation

Security Audit History and Approvals are stronger on PWA than desktop today.

## 21. Recovery

### Where

- **Settings → Recovery**
- Welcome/Sign In → **Restore Vishnu**

### How

1. Keep recovery material safe.
2. On restore, authenticate with the supported recovery mechanism.
3. Validate/restore supported state.
4. establish a trusted device.
5. revoke a lost device when applicable.

### Limitation

The repository has DR/recovery tests, but a current accepted restore from the actual intended production data root is still required before making a production-recovery claim.

## 22. Sensorium privacy and sensors

### Where

- iPhone/iPad native companion: **Sensorium Privacy & Sensors**
- PWA Advanced/Settings: **Sensorium Status** for saved qualification evidence

### How

1. Review sensor permissions/privacy.
2. Grant only the sensors you intend Vishnu to use.
3. Use STOP/disable controls where supported.
4. Review provider/evidence status separately from live availability.

### Limitation

Android native Sensorium Privacy is an expected current platform gap. PWA status is read-only saved evidence; it does not grant adb/simctl/shell/device-control authority. Physical L4 remains unqualified.

## 23. Computer & Browser Control

### Where

Desktop/Advanced controls where configured.

### How

Use only through the governed policy/approval/device path for supported operations.

### Limitation

PWA owner status/control is an expected gap. Do not assume the presence of computer/browser operators means unrestricted control is enabled.

## 24. Our Products / Product Composer

### Where

**Our Products → Product Detail / Build Lifecycle**

### What it does

Defines/builds Vishnu-generated products/artifacts using product definitions and platform runners.

### Limitation

This remains advanced/experimental. Real mobile/desktop signing, notarization/store publication and production release acceptance are separate external gates.

## 25. Dashboard and System Status

### Where

- Desktop: **Dashboard**
- PWA: **Settings/Account → System Status**

### Use it for

Owner-safe operational/runtime status and diagnostics.

## 26. About and Updates

### Where

**Settings → About / Updates**

### What it shows

- safe version/build identity
- release/channel information where available
- proprietary/all-rights-reserved identity
- notices/privacy/security links

### Important limitation

There is no claimed signed in-app updater. Installation updates remain managed by the platform/installation owner until a real updater authority is connected.

## 27. Accessibility

Desktop source includes persisted Reduce Motion and High Contrast controls. Current design system also has accessibility/responsive rules.

### Limitation

The 63 canonical screen set has not yet received strict exact-SHA accessibility acceptance. PWA accessibility-settings organization is still a platform gap.

## 28. What is intentionally internal

You do not need normal owner pages for:

- SQLite migration mechanics
- SecretVault envelope/nonce/AAD internals
- root-key internals
- ToolRegistry registration mechanics
- one-use approval persistence internals
- retry/backoff mechanics
- replay/lease internals
- encrypted transfer framing
- audit hash-chain implementation
- qualification evidence persistence

You benefit from these through reliability/security rather than operating them directly.

## 29. What is experimental

Treat these as advanced/research rather than normal production behavior:

- Intelligence Lab
- higher-autonomy/evolution research
- Capability Forge V3
- Sensorium causal/procedural research
- Voice Lab / governed telephony
- self-improvement/training/model-promotion research
- Our Products/public distribution lifecycle
- selected Agent Workforce advanced surfaces

## 30. Owner feature directory

| I want to… | Go to | Feature |
|---|---|---|
| Talk to Vishnu | Home / Conversation | Conversation |
| Find an old chat | Home/Conversation → History | Conversation History |
| See what Vishnu remembers | Memory | Memory |
| Add documents | Knowledge → Add Source | Knowledge / File Intelligence |
| Connect an API | Apps & Tools → Capabilities → Add → OpenAPI | Universal OpenAPI |
| Connect MCP | Apps & Tools → Capabilities → Add → MCP | Universal MCP |
| Manage devices | Settings/More → Devices | Trusted Devices |
| Add a device | Devices → Add Device / native Connect | Device Enrollment |
| Revoke a lost device | Devices → Device Detail | Device Trust/Recovery |
| Change AI provider | Settings → AI Models & Providers | Model Providers |
| Change voice | Settings → Voice | Voice Intelligence |
| Control storage | Settings → Data & Storage | Data Plane |
| Inspect a storage provider | Data & Storage → Provider Detail | Storage Fabric |
| See work in progress | Live Work | Canonical Work |
| Continue a project | Projects → Project Workspace | Projects |
| Create automation | Automations / Workflows | Automation |
| Review pending decisions | Inbox / Approvals | Attention / Approvals |
| Review activity | Activity | Activities/Evidence |
| Review sign-in methods | Settings → Security | Sessions/Passkeys |
| Restore Vishnu | Welcome/Sign In → Restore Vishnu | Recovery |
| Stop sensing | Native Sensorium Privacy | Sensorium |
| Diagnose runtime | Settings/Account → System Status | System Status |
| Check version | Settings → About / Updates | About / Release |
| Build a Vishnu product | Our Products | Product Composer |

## 31. Troubleshooting truth checklist

If something exists in source but you cannot use it:

1. **Is it on the right platform?** Many broad tasks live in the PWA by design.
2. **Are you signed in with an owner session?** Protected owner APIs fail closed.
3. **Is the required device trusted and scoped?** Device identity is separate from owner identity.
4. **Does the feature require an external provider account?** Models, storage, VoiceStudio/OpenVoice, OAuth and telephony may need setup.
5. **Does it require approval?** Governed writes may pause for ApprovalManager.
6. **Is the runtime actually running?** Automations/background work require an active configured runtime.
7. **Is the feature experimental/default-off?** Labs/Forge/telephony/training may intentionally be disabled.
8. **Are you confusing CI qualification with production?** Emulator/simulator/preview success is not physical-device/production acceptance.

## 32. Current limitations that matter most

- 0/63 canonical owner screens are strict COMPLETE under exact-SHA visual/behavior/a11y rules.
- 35 expected platform UI cells remain explicitly missing; intentional N/A cells are excluded.
- real production runtime/data-root/backup acceptance is not established by source alone.
- physical Android/iPhone/iPad qualification is still separate from emulator/simulator success.
- external provider/OAuth/storage/voice behavior depends on real account configuration.
- public signing/notarization/store distribution remains external.
- PWA Live Work vs Workflows navigation requires executable disambiguation.

For technical provenance, locations and status, see `docs/audit/WHAT_VISHNU_HAS.md`, `FEATURE_PROVENANCE.md`, `WHERE_EVERYTHING_LIVES.md`, `SYSTEM_CONNECTIONS.md` and `VISHNU_CURRENT_COMPLETENESS.md`.