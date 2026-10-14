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

Vishnu's owner identity is internal and independent of the current computer, phone, browser, hostname, and external sign-in provider. A stable `OWNER-…` identifier and `VISHNU-…` identifier are created in the canonical `OwnerAccessStore` when the desktop first-run ceremony completes. The initial owner remains the single owner; devices are separate trusted participants.

The current desktop wizard is the only complete first-owner creation ceremony. It requires an owner password and explicit recovery-code acknowledgement, then lets the owner choose a local/external model or skip configuration. The first-run language describes this computer as the first trusted device, not the permanent owner authority. Existing installations are migrated in place and retain their current data and security methods.

**Platform boundary:** Android and iOS are currently companion clients and still require an existing Vishnu runtime/pairing ceremony. The PWA supports sign-in and trusted-browser enrollment for an already initialized owner; it does not create the first owner. Mobile-only and browser-only first creation, native passkey enrollment during creation, recovery-based cross-runtime restore, and a shared remote initialization ceremony are not implemented. Do not treat these routes as available until their platform flows, bootstrap protections, device registration, and recovery tests are qualified.

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
