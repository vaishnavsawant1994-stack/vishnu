# Vishnu 2.0 — Phase 1: simplified onboarding, access and recovery

**Status:** OWNER-AGREED PRODUCT DESIGN BASELINE — documentation, **not** a shipped/qualified implementation  
**Decision recorded:** 2026-10-21  
**Applies to:** Vishnu single-owner desktop (Windows/macOS/Linux), web/PWA, Android and iOS  
**Scope:** Phase 1 only. Later phases and total product screen count remain under discussion.  
**Implementation truth:** [Current implementation status](ui/CURRENT_IMPLEMENTATION_STATUS.md) and [UI truth inventory](ui/ui_truth.json) take precedence for *what is coded or accepted*.

## 1. Intent and non-negotiable principles

A person should be able to create and start using Vishnu as easily as a modern social app. Keep powerful technology underneath a calm, professional and understandable interface:

1. **Simple on the surface, powerful underneath.** Ask only what is essential before first entry; never expose infrastructure jargon unless it becomes necessary.
2. **No duplicate identity or security authorities.** Reuse the current FirstRunCoordinator, OwnerAccessStore, DeviceRegistry, SecretVault, Data Plane and model/provider authorities.
3. **Preserve meaningful consent.** A single “I agree” must not silently grant camera/microphone, external-model disclosure, cloud synchronization or consequential tool action permissions.
4. **Safe-by-default setup.** No automatic external provider connection or cross-device data copy; no unrestricted autonomy. Say clearly what has *not* been configured.
5. **Never erase or recreate an existing owner because of a login/network error.** If setup was interrupted, resume from the last durable confirmed checkpoint.
6. **First device != permanent master device.** Owner identity is stable and independent of the current phone, laptop, browser, hostname or third-party identity account.
7. **Local-first and cloud optional.** A remote hosted runtime may be needed for phone/web creation; do not call remote server data “stored on my phone.”
8. **Progressive disclosure.** Detailed model, GPU, storage, synchronization, agent and permission controls belong in Home → Finish Setting Up Vishnu and Settings.
9. **Honest readiness.** “Identity created” is not identical to “AI can answer”; display which capabilities are configured, connected, unavailable or deferred.
10. **Consistent across devices.** Shared product language and journey, platform-appropriate native passkeys, local file pickers, biometrics and accessibility.

This baseline deliberately simplifies the old 28 candidate onboarding pages. It does not discard their backend functionality.

## 2. Canonical Phase 1 screen inventory

**Phase 1 approved design count: 9 core screens + 1 conditional connection screen.** This counts **unique owner tasks**, not platform duplicates, popovers, dialogs, loading states or the first meeting embedded in Home.

| ID | Final page | Audience and primary purpose | Primary action |
| --- | --- | --- | --- |
| P1-01 | **Welcome to Vishnu** | First launch/owner choice: Create, I Already Have Vishnu, Restore | Choose one journey |
| P1-02 | **What Should Vishnu Call You?** | New owner: name, optional preferred name and picture | Continue |
| P1-03 | **Secure Vishnu** | New owner: password, supported optional passkey/biometric sign-in, optional device nickname | Secure Vishnu |
| P1-04 | **Recovery Codes + Quick Review** | New owner: reveal/download/copy codes, confirm safe storage, review essential identity/security/defaults | Create My Vishnu |
| P1-05 | **Unlock Vishnu** | Returning owner: appropriate configured authentication; other methods as expandable controls | Unlock |
| P1-06 | **Connect This Device** | Existing owner on new device: connect, verify owner, request approval and show pending/approved/denied states | Connect / Request approval |
| P1-07 | **Recovery Options** | Lost login, lost device or data recovery: clearly distinguish access from data | Choose recovery route |
| P1-08 | **Recovery Verification** | Recovery code *or* encrypted backup material + security checks, depending on route | Verify / Continue |
| P1-09 | **Recovery Results** | Show exactly what identity/data/security was recovered, what remains missing, and next actions | Enter Vishnu / Finish securing |
| P1-10 | **Runtime Connection Assistant** (conditional) | Only where no usable local/linked runtime exists; plain-language connection/provisioning | Connect / Set up compatible runtime |

**Not additional Phase 1 pages:** installer and hardware diagnostics, quick review panel within P1-04, the animated first meeting inside Home, choose-other-login-method sheet, passkey OS prompt, trusted-device Approve/Deny dialog, setup resume screen/state, file chooser, loading/error/offline views, or the post-creation Settings checklist.

## 3. The four-screen Create My Vishnu journey

```text
P1-01 Welcome
   → P1-02 Your Name
   → P1-03 Secure Vishnu
   → P1-04 Recovery Codes + Quick Review
   → Home (first meeting with Vishnu)
```

### P1-01 Welcome

- Vishnu brand/animated core, short friendly statement, three actions: **Create My Vishnu**, **I Already Have Vishnu**, **Restore My Vishnu**.
- Small links for language, accessibility, help and privacy. Responsive phone/desktop presentation.
- Detect setup/owner/device/runtime state *before deciding valid actions*.
- Existing ready install -> login/unlock; pending install -> **Continue Setup**; new install -> creation; revoked/unauthorized device -> safe sign-in/join, not new owner creation.
- Never show an unauthorized “create new owner” flow against an already initialized runtime.
- No GPU, cloud, endpoint, installer-folder or data-policy form on this page.

### P1-02 Your Name

- **Required:** a name Vishnu can address the person by. **Optional:** nickname/preferred name and profile picture (last name may be optional).
- Friendly live preview of Vishnu's greeting; avatar may be added later.
- Behind the scenes, safely create stable `owner_id` and `vishnu_id`, separate from device credentials, email and external model account.
- Resume/retry must not generate a second owner.

### P1-03 Secure Vishnu

- Explain simply: “Protect your personal Vishnu.”
- Current backend requires a strong owner password and confirmation; preserve this until an independently accepted passkey-first/password-optional alternative exists.
- Offer **Add Face ID / fingerprint / passkey**, **when supported**. The platform handles biometric capture; Vishnu does not store raw biometric data.
- Detect current device and prefill a friendly name such as “My Laptop” / “My Phone”; permit rename, but do not use nicknames as authentication.
- Register the first trusted device through existing device authority; no permanent master-device assumption.
- Show recovery help in plain language and the next step clearly.

### P1-04 Save Recovery Codes + Quick Review

- Show newly generated **one-time recovery codes** once, with **Download**, **Copy**, and optional **Print**, plus a clear confirmation that the owner stored them safely.
- Remind the owner to store codes away from this device and not share them.
- If interrupted after generation, **resume**; never regenerate silently. Offer explicit “Generate fresh codes” with warning that old codes are invalidated.
- Do **not** export the owner password, plaintext passkey secrets, device bearer tokens or API credentials in a “save everything” file. A trusted password manager holds passwords; passkeys remain in platform credential stores.
- Clearly explain: **recovery codes regain access; they are not an encrypted data backup**.
- Include a compact editable summary: owner, authentication, first trusted device, recovery readiness, AI deferred/available, data placement and privacy/autonomy defaults.
- On **Create My Vishnu**, validate essential state and finish idempotently through the existing coordinator. Show what has actually completed.
- After successful completion, open **Home**. A short, accessible Vishnu first greeting belongs to Home, not an additional blocking onboarding page.

## 4. Returning login (P1-05)

- On a trusted active device, use an eligible existing session or show a quick OS passkey/biometric unlock.
- Otherwise display password or other configured sign-in method under “Other ways to sign in.”
- Do not offer identity creation simply because the device lost its cookie/credential.
- Include account recovery, understandable denial/expired/rate-limit messaging, and optional reauthentication for sensitive settings.
- Signing in on an **unknown** device does not automatically grant trusted-device privileges; follow the join approval path when required.

## 5. Add a device (P1-06)

```text
I Already Have Vishnu
 → connect to existing runtime (P1-10 only if needed)
 → verify owner identity
 → pending device join + matching short-lived verification code
 → existing trusted device sees Approve / Deny prompt
 → independent revocable device credentials and scoped access
 → success (enter Vishnu)
```

- Detect device model/platform; optional “My Phone / My Laptop / Office Computer” nickname.
- Clearly show pending, approved, denied, expired, disconnected and retry states within P1-06.
- Show device details and matching verification code on the approving device.
- If all old trusted devices are lost, offer an authenticated recovery pathway instead of an impossible mandatory approval.
- Never silently sync all data or grant every device capability after pairing.

## 6. Recovery (P1-07 through P1-09)

**P1-07 Recovery Options:** choose **Recover login**, **Restore my data**, or **Recover on a replacement device**. Plain words, no confusing equivalence between account access and a backup.

**P1-08 Recovery Verification:** route-specific input:
- Access recovery -> consume an approved, one-use recovery credential and re-establish sign-in/device trust.
- Data restore -> select authenticated encrypted archive, separate key material/passphrase when required; verify integrity and compatibility; show destination and overwrite safeguards.
- Replacement device -> prove owner authority, enroll new credentials, and offer to revoke a lost device.
- Reject unsafe or incomplete recovery while preserving the prior installation. Never import old login sessions, revoked devices or reusable secret authority from backup.

**P1-09 Recovery Results:** what identity was retained, which data objects were recovered, failed/unavailable items, newly trusted device state, lost-device revocation status and next steps. No “success” without verified outcome.

The advanced encrypted portable recovery package is **optional** and primarily managed from Settings → Backup & Recovery. The recovery journey must still permit its use if already available.

## 7. When a runtime connection is unavoidable (P1-10)

Hide infrastructure configuration entirely if the local or connected runtime already works. This is *not* a required page for everyone.

Explain in simple terms: **“Vishnu needs a place to run its main system. Connect an existing Vishnu or set up your own private runtime.”**

- **Local** = main software works on compatible hardware under owner control; suitable offline functions can operate without internet after setup.
- **Online / hosted** = Vishnu's runtime or AI may use owner-selected connected infrastructure. “Online GPU” is an *AI compute* option, not itself a complete Vishnu runtime.
- **Hybrid** = compatible local and approved remote components; no automatic external data disclosure.
- A new phone/browser can initiate owner creation using approved local or HTTPS-hosted provisioning. It may still need a functioning backend; “Skip for now” can defer **optional AI/provider setup**, not required runtime creation or connection.
- Show only needed information: connect by address/QR/deep link or guided compatible deployment; secure bootstrap, connectivity and HTTPS checks are handled in the background as much as possible. Show provider/cost/ownership clearly when a host is selected.
- No assumption that `device_only` on a phone with a hosted backend means data is physically stored on the phone.

## 8. Defaults during quick creation

These are **product-design defaults to align and test**, not a statement that all current entry points already behave identically.

| Choice | First-run behavior | Owner controls afterward |
| --- | --- | --- |
| AI provider | Not required; no provider secretly connected; indicate unavailable AI if none configured | Settings → AI Intelligence |
| AI processing mode | Do not force Local / Online / Hybrid selection during creation | Settings → AI Intelligence |
| Data placement | `device_only` as conservative default in the selected runtime; disclose actual hosting | Settings → Data & Storage |
| Data synchronization | Off unless deliberately enabled | Settings → Data & Storage |
| AI privacy | `local_only` initially; no unapproved external model calls | Settings → Privacy & Permissions |
| Autonomy | `ask` for consequential actions; enforcement remains on the security authority | Settings → Privacy & Permissions |
| Personal memory | Apply known consent/governance controls; no silent external ingestion | Settings → Memory |
| Camera, microphone, screen, location | Request separate OS/app permission **when the feature is needed** | Settings → Permissions |
| External apps | Not connected during quick setup | Settings → Apps & Capabilities |
| Encrypted data backup | Not silently uploaded; offer a guided backup later | Settings → Backup & Recovery |
| Profile/character/voice | Optional personalization after first entry | Settings → Appearance & Voice |

A Terms acknowledgement, where legally necessary, must not be conflated with blanket device access, third-party processing consent or autonomous action approval.

## 9. After creation: Home and Finish Setting Up Vishnu

The first welcome animation/greeting is a **Home state in Phase 2**. Show actual capability readiness: **Ready**, **Needs setup**, **Offline**, **Unavailable** or **Permission required**. If no functional AI provider exists, show **Connect AI** rather than a broken chat.

A dismissible, resumable checklist in Home and Settings links to existing sections, without adding more onboarding pages:

1. AI Intelligence — local/offline, external/online, hybrid, provider credentials, model tests and costs.
2. Data & Storage — folders, local storage, optional cloud, sync policy and actual host location.
3. Privacy & Permissions — memory, sensors, tools and autonomy controls.
4. Appearance & Character — themes, visual Vishnu and accessibility.
5. Voice — microphone, speech and voice choices.
6. Devices — pair, nickname, scope and revoke.
7. Backup & Recovery — create/verify an encrypted backup, recovery materials.
8. Apps & Capabilities — integrations, MCP/OpenAPI and permissioned tools.

These are **existing/later Settings tasks**, not new Phase 1 pages or eight separate mandatory steps.

## 10. Architecture and ownership

```text
Desktop / Web PWA / Android / iOS
  → common product flow (Create / Unlock / Join / Recover / Resume)
  → FirstRunCoordinator + owner authentication/session policy
  → OwnerAccessStore (one owner identity, password, passkeys, recovery codes)
  → DeviceRegistry / DeviceGateway (trusted independent device, scope, revoke)
  → SecretVault / ApprovalManager (secrets, consequential action controls)
  → Data Plane + BackupService / DisasterRecoveryService
  → model router/provider settings (optional)
  → Home and post-create Settings
```

Existing sources to **reuse, not duplicate**:

| Responsibility | Current source |
| --- | --- |
| Durable, idempotent setup state | `onboarding/first_run.py` |
| Owner identity, password, codes, passkeys | `security/owner_access.py` |
| Hosted/PWA Create/Join/Login/Restore API | `server/iphone_pwa.py` |
| Web Genesis presentation/actions | `pwa/first-run.js`, `pwa/first-run-actions.js` |
| Native desktop flow | `ui/first_run_wizard.py` |
| Android passkey/recovery/entry | `android-companion/` |
| iOS passkey/recovery/entry | `ios-companion/` |
| Data, recovery and devices | Existing `data_plane/`, `recovery/`, device registry/gateway |
| Authority, encryption, approvals | Existing `security/` and `approvals/` |

State transition rules: `uninitialized → setup_in_progress → ready`; `connect_pending` for joining; `restoring/restore_failed` for data recovery. Resume after interruption, enforce one-owner creation, fail closed when authorization or restore integrity cannot be verified, and never mark ready before mandatory security/recovery checks pass.

## 11. Expected UI behavior (all platforms)

Each logical screen must cover applicable loading, empty, validation, network-disconnected, wrong-password, expired-session, access-denied, approval-pending, rate-limited, cancelled, retry, success and resume states. These are **states**, not independently counted pages.

Product-wide: responsive desktop/tablet/mobile, visible focus, keyboard operation, accessible passkey prompts, screen-reader labels/status, scalable type, reduced motion, privacy-respecting display of sensitive codes, and localized plain-language copy.

## 12. What exists now vs. what this document requests

**Existing source evidence:** setup coordinator; hashed password/one-use code store; trusted-device and owner APIs; browser Genesis Create/Join/Restore flows; native wizard and native passkey/recovery entry points. These are **not** proof of a released, identical, fully tested end-to-end experience.

**Known alignment work before calling Phase 1 complete:**
- Reconcile web short three-stage Create UI with desktop/native screens and legacy advanced setup paths; keep controls accessible in Settings.
- Implement/review a single combined Recovery Codes + Quick Review step; do not accidentally weaken recovery acknowledgement or cause regeneration on resume.
- Verify secure downloaded recovery-codes behavior on supported platforms; *no plaintext owner-password or passkey export*.
- Verify runtime detection, local/hosted explanation, encrypted backup recovery, and device joining across supported environments.
- Qualify physical passkey/biometric flows, first-device creation on each platform, trusted-device approval, lost-device recovery and safe data restoration.
- Confirm conservative defaults using actual authority/API state rather than presentation-only UI controls.
- Add exact-SHA UI, accessibility, cross-platform, failure/retry and persisted-state evidence.
- Do not mark Phase 1 fully implemented, released or deployed solely because this document is merged.

Known historical source evidence: [UI implementation status](ui/CURRENT_IMPLEMENTATION_STATUS.md), [product truth](audit/VISHNU_PRODUCT_TRUTH_MAP.md), [local web + desktop development](LOCAL_DEVELOPMENT_WEB_AND_WINDOWS.md). These documents have their own dated baselines.

## 13. Screen count and continuation rule

**Phase 1 design: 9 core unique screens + 1 conditional page; no inflation from dialogs, repeat platform layouts or Home.** It does **not** supersede the separately audited 63-screen canonical implementation taxonomy, the historical 114 numbered visual-design references, or the overall final Vishnu product count. Reconcile mapping and duplication only after all product phases are discussed.

For future product discussions:
1. Read **this document** for the agreed Phase 1 user experience.
2. Read `docs/ui/ui_truth.json` and recent source/PRs for actual implementation status.
3. Apply **simple on the surface, powerful underneath** to each future phase.
4. Track any proposed change to this baseline explicitly; do not quietly reintroduce mandatory technical onboarding pages.
5. After Phase 2–7 discussions, produce a unified module/screen/route/platform/authority matrix and **then** settle the final product screen count.

**Decision:** Finalized as a *product and UX direction*; implementation, tests and release verification remain separate.
