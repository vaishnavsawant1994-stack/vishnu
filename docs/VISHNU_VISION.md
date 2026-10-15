# Vishnu Vision — Sensorium Camera Contract

Vishnu Vision gives a paired Vishnu runtime bounded visual observations from cameras that the owner explicitly enables. It extends the existing Sensorium, DeviceGateway, device permissions, model router and audit/event boundaries; it is not a second device-control system and it does not grant execution authority.

## Current supported surfaces

- **Web/laptop browser:** the user presses **Start camera**, the browser displays its camera indicator and a local preview, and Vishnu receives a single resized JPEG only when the user presses **Analyze snapshot**. The camera stops after five minutes, on Stop, on emergency stop, or when the page becomes hidden.
- **Android companion:** a remote start request creates a high-priority consent notification. The user must tap it and keep the dedicated Vishnu Vision activity visible. CameraX shows a live preview and allows snapshot requests for at most five minutes. Leaving the activity, disconnecting, expiring or stopping the session unbinds the camera hardware.
- **iOS companion:** the owner must open the Vishnu app and enable the **Vishnu Vision** toggle. The session is foreground-only, uses the iOS camera privacy indicator, expires after five minutes and stops as soon as the app resigns active. Remote requests cannot arm the camera.

## Data and model rules

1. Camera frames are classified **sensitive** at the model-routing boundary.
2. A frame exists only long enough to complete one analysis request. Android may use a temporary cache file for CameraX capture; it is deleted immediately after reading. Browser capture uses an in-memory canvas. iOS uses in-memory photo data.
3. Raw frame bytes and base64 data are never returned in Sensorium API responses, written to Vishnu memory, or emitted to the event bus by the camera service.
4. Audit/events record metadata only: requesting device, source, MIME type, frame byte count and policy flags.
5. Visual observations are explicitly **untrusted context** and have `execution_authority=false`. Seeing something cannot satisfy an approval or authorize a tool/action.
6. Biometric identity recognition is **off**. Vision may describe visible people but must not claim a person is the owner, identify a person biometrically, or infer sensitive traits from appearance. Any future identity feature requires a separate owner opt-in and separate governance.

## Authorization

- Same-device browser snapshots require an authenticated paired device with `device:read`, plus the browser's own explicit camera permission and Analyze action.
- Remote mobile camera reads additionally require the requesting controller to have `memory:sensitive`; cross-device reads require `device:admin`.
- The target mobile device must be active and allow `device:read`.
- Native operating-system camera permissions remain authoritative and cannot be bypassed by Vishnu.

## Session lifecycle

The camera is **off by default**. A Vision session is bounded to five minutes. Camera sessions terminate on explicit Stop, expiry, relevant disconnect, app/page backgrounding, or owner emergency control where the surface supports it. Continuous always-on capture is intentionally not part of this implementation.

## Recommended next adaptations

These are follow-up hardening/expansion items rather than prerequisites for snapshot Vision:

- Introduce a dedicated `sensor:camera` permission and per-device policy UI (`deny`, `ask each time`, `allow this session`). Avoid a permanent silent allow mode.
- Add optional on-device preprocessing: resolution/downsampling, document-region crop, face blurring for bystanders, and sensitive-screen/redaction helpers before any external model route.
- Add **bounded live vision** as a separate mode using sparse frames (for example 0.2–1 FPS), explicit duration and bandwidth/battery limits instead of video streaming by default.
- Add semantic-only retention controls: owner may save a derived note/observation without retaining the image.
- Add front/back/external-camera selection and multi-camera device inventory.
- Add local/private vision-model preference for sensitive frames and an owner-visible indicator when an external provider would be used.
- Add bystander/privacy mode and a visible reason string (for example, “Vision active for setup help”) on native camera surfaces.
- Add native desktop webcam adapters for macOS/Windows/Linux if camera access is required outside the browser companion.
- Keep face verification/recognition, if ever added, isolated behind separate biometric enrollment, local encrypted templates, explicit purpose limitation and deletion controls.

## Non-goals

Vishnu Vision is not covert surveillance, continuous recording, automatic facial recognition, or a source of autonomous action authority. Camera access should remain obvious, revocable, short-lived and attributable to a specific trusted device/session.
