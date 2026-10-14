# Vishnu Owner Product Operations

## Implemented product surfaces

- `/iphone/` provides persistent conversations, hands-free browser voice, interruption, approvals, Memory, Knowledge, Activities, workflows, qualification status and trusted-device management.
- Personal memory and uploaded knowledge are separate durable stores. Retrieved answers label memory separately from document citations.
- Workflows retain checkpoints in SQLite, fail closed after a restart, and require owner-directed resumption. Consequential tool calls still enter the one-use approval system.
- Existing owner-enrolled iPhone browsers retain their trusted cookies and receive the owner scope migration without re-enrollment. Each newer device has an independent scope set and can be revoked immediately.
- Model routing is provider-neutral and records provider selection/fallback. Temporary Gemini remains usable while the private endpoint is unavailable.

## Owner-facing data controls

- Memory: inspect retrieval score/history/relationships/conflicts; correct; permanently delete; export; apply retention; classify sensitive/secret.
- Knowledge: upload TXT, Markdown, CSV, JSON, PDF, DOCX or XLSX (10 MB maximum); index; search; inspect source chunks and citations; update metadata/access; delete; export.
- Devices: list, inspect last use/scopes, change permissions, and revoke a lost device.
- Activities: inspect model, action, approval, workflow, device and qualification audit events.

## Owner sign-in

Vishnu's owner identity is internal and independent of the current computer, phone, browser, hostname, and external sign-in provider. Stable `OWNER-…` and `VISHNU-…` identifiers live in the canonical `OwnerAccessStore`; the first trusted device is a separate `DeviceRegistry` record. The initial owner remains the single owner, and no device becomes an irreplaceable identity authority.

The desktop wizard and secure PWA setup use the shared `FirstRunCoordinator` and `OwnerAccessStore`. Both collect owner details, configure password and one-time recovery codes, require recovery acknowledgement, save privacy preferences, and allow model setup to be skipped. The PWA setup registers a distinct browser device and requires a WebAuthn passkey when the browser supports it. Existing installations are migrated in place and retain their current data and security methods.

**PWA runtime boundary:** A browser connects to an already deployed Vishnu runtime; it does not host the server or choose a data location. PWA first creation is exposed only when that runtime operator has configured `PERSONAL_AI_BOOTSTRAP_SECRET` with at least 32 characters. The code bootstraps one uninitialized runtime and is not a normal login. Configure it only through the deployment's private secret manager, keep the runtime HTTPS-only, and remove the setting after creation. The setup screen says that data location follows the runtime's saved privacy policy; it never silently enables cloud storage.

**Native first-device boundary:** Android and iOS expose Create my Vishnu, I already have Vishnu, and Restore Vishnu. Native creation calls the shared first-run coordinator on a configured HTTPS Vishnu runtime; the native app stores its independent device bearer in Android encrypted preferences or iOS Keychain. The server requires its one-time high-entropy bootstrap secret, creates the canonical owner identity, and issues recovery codes. Recovery codes are retained in secure platform storage until setup is acknowledged. Native setup can choose a supported local/provider model or explicitly configure AI later; provider credentials are sent only over HTTPS to the existing encrypted model credential system and are not persisted by the mobile app. Completion also requires device authentication, saved-recovery acknowledgement, and a persisted privacy choice. Restore consumes a one-time recovery code to enroll a new device on an already initialized runtime; it does not restore a missing server/runtime or migrate data between runtimes.

These native routes do not make the phone a Vishnu runtime and do not provide offline first-owner creation: an owner must already have a reachable, securely provisioned runtime and its setup code. Native passkey creation and backend hosting provisioning remain incomplete. Thus native flows are an initial implementation of the shared creation and device-recovery ceremony, not completion of universal phone-only onboarding. Existing phone companions continue to join via the established pairing flow.

The enrollment code remains a compatibility/bootstrap path, not the Vishnu identity or normal authentication method. A trusted owner can create a passkey, an owner password and one-time recovery codes in **Settings → Security**. Passkeys are authenticators for the same owner; Google remains optional and is bound to the exactly configured owner email.

Google owner sign-in requires both `GOOGLE_SIGNIN_CLIENT_ID` and `PERSONAL_AI_OWNER_GOOGLE_EMAIL`. Create a Google Identity Services Web client whose authorized JavaScript origin is the exact Vishnu HTTPS origin. The server verifies the Google ID-token signature, audience, expiry, subject, verified-email claim and exact configured owner email before issuing the same scoped HttpOnly trusted-device cookies. Other Google accounts fail closed. A Google client secret is not required for this authentication-only ID-token flow.

## Connector configuration

Gmail, Google Calendar, Slack and Home Assistant tools are registered only when their approved adapters are configured. Read operations are read-only. Sending, creating, updating or device-control calls require policy approval; deletion is destructive. Provider/account credentials belong in the encrypted vault or deployment environment and must never be committed.

## Self-hosted inference

The ready-to-deploy vLLM package is in `deploy/self-hosted-model/`. On an owner-purchased NVIDIA GPU host:

1. Copy its `.env.example` to `.env` and supply a random gateway bearer token and selected model ID.
2. Start the Compose stack and run `verify.sh`.
3. Configure Railway `LOCAL_AI_URL=https://<private-model-host>/v1`, `LOCAL_AI_KEY=<gateway-token>`, `LOCAL_AI_MODEL=<model-id>`, `AI_PROVIDER=local`, and `MODEL_LOCAL_FIRST=true`.
4. Verify `/iphone/api/system/status`, a normal turn, a model-timeout trial and the recorded fallback audit before removing Gemini fallback.

The GPU deployment is not claimed complete until a host is purchased and the live health/latency/privacy checks pass.

## Qualification boundary

Automated tests validate the recorder and owner interfaces but do not count as physical evidence. PR #18 must remain unmerged until the exact `78c7e9d6d848f0dcc93ee4f1f281fad4eff970f5` deployment has retained mandatory P3 real-device/production-like evidence. P3.2–P3.8 cannot be self-awarded by the model.
