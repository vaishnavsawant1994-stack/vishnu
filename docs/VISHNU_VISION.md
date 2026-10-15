# Vishnu Vision — Governed Sensorium Camera Architecture

Vishnu Vision gives a paired Vishnu runtime bounded visual observations from cameras the owner explicitly enables. It reuses Sensorium, DeviceRegistry, DeviceGateway, MemoryStore, SecretVault, model routing, Voice, audit/events, ToolRegistry and ApprovalManager boundaries. It is not a second device-control system and it never grants execution authority.

## Permission model

Camera access has two separate gates:

1. `sensor:camera` is a DeviceRegistry scope. It permits a device to **request** camera consent.
2. `SensorPermissionStore` decides whether a particular camera resource may actually be used.

Persistent camera policy can only be:

- `never`
- `ask`

`session` is a temporary state created after explicit local consent. It lasts at most ten minutes, is five minutes by default, is independently keyed by camera resource, and is invalidated on Vishnu restart. There is intentionally no durable `always allow` or silent-camera mode.

Biometric identity is a separate `sensor:biometric` owner scope, defaults to `never`, and is not called by Camera Vision.

## Supported camera surfaces

### Browser / laptop

The owner selects a real `videoinput`, presses **Start camera**, receives the browser/OS camera indicator and a local preview, and only then receives a five-minute `sensor:camera` grant. Hiding the page, emergency stop, explicit Stop, or expiry stops tracks and revokes the session.

The browser supports:

- exact multi-camera selection
- one-shot analysis
- bounded Live Vision
- local face redaction when the browser supplies `FaceDetector`
- task-mode selection
- visual-memory selection
- Vision + Voice using separate microphone permission and browser speech recognition where available
- local speech output of the answer

### Android companion

A remote start request creates a high-priority consent notification. The owner must tap it and keep the Vishnu Vision activity visible. CameraX enumerates Camera2 devices, including exposed external cameras, and can bind an exact camera ID. Each foreground activation creates a fresh random local sensor-session ID.

Before an Android frame leaves the device it can be cropped, explicitly redacted, face-redacted with local Android face detection, downsampled and JPEG recompressed. Temporary CameraX files are deleted immediately. Leaving the activity, disconnecting, expiry or Stop unbinds the camera hardware and destroys the session ID.

### iOS companion

The owner must open Vishnu, choose an AVCapture camera and enable Vision. A remote request cannot arm the camera. The foreground session creates a fresh random sensor-session ID, expires after five minutes and stops when the app resigns active.

Requested privacy processing occurs on-device before upload. Apple Vision face detection can redact visible faces locally. The app also provides an explicit **Vision + Voice together** control; camera and microphone permissions remain independent.

### Native desktop cameras

`DesktopCameraAdapter` discovers and captures local webcams without requiring the browser:

- Linux: V4L2 `/dev/video*`
- macOS: AVFoundation
- Windows: DirectShow

The adapter uses a discovered-camera allowlist, fixed subprocess argument arrays, no shell execution, capture timeouts and bounded JPEG output. USB/UVC cameras exposed by the operating system appear as independent camera resources and therefore receive independent sensor policies.

### Registered external / IoT cameras

Owners may register an exact HTTPS snapshot endpoint in `ExternalCameraRegistry`. Capture never accepts an arbitrary request-time URL. Redirects are disabled, TLS verification remains enabled, response type/size/time are bounded, and bearer/basic credentials live only in SecretVault. Each registered external camera has its own `sensor:camera` resource policy and can be revoked independently.

## Bounded Live Vision

Live Vision is sparse visual sampling, not video streaming. `LiveVisionManager` enforces:

- 0.2–1 sample/second
- maximum ten-minute session duration
- frame-count budget
- byte budget
- model-call budget
- explicit owner stop
- expiry stop
- device/session identity binding

Browser clients perform a first local 16×16 scene-change check to avoid uploading unchanged scenes. The server performs a second scene fingerprint/delta check before consuming a model call. Stable frames therefore do not repeatedly invoke vision models.

There is no 30/60 FPS camera-to-model stream and no background autonomous camera loop.

## Privacy preprocessing

`PrivacyOptions` supports:

- maximum-edge downsampling
- normalized region crop
- normalized redaction regions
- fail-closed face-redaction requirement
- client proof that face processing happened locally

Server-side `sanitize_image()` defensively decodes, crops, redacts and recompresses every received frame before model use or optional retention. Mobile/browser clients can perform the equivalent work before upload so external model routes never need the original capture.

Sensitive frames use the existing model-routing policy. Vishnu remains local-first when an allowed local vision provider is available; sensitive external routing continues to obey the owner's existing external-sensitive-data policy.

## Visual memory controls

Every observation chooses one explicit retention mode:

- `none` — retain nothing
- `description` — store only the semantic model observation in the encrypted MemoryStore
- `image` — store the semantic observation and the **privacy-processed** image

Optional saved images are AES-GCM encrypted as local visual-memory blobs with a DEK protected by SecretVault. Raw camera frames are never accepted by the visual-memory manager. The Sensorium camera API does not expose a raw-image retrieval endpoint.

## Visual task assistance

The camera service supports bounded system guidance for:

- general visual questions
- repair guidance
- cooking assistance
- exercise-form observations
- document reading
- equipment setup
- room/environment understanding
- screen troubleshooting
- general troubleshooting

These modes add domain-specific caution and uncertainty handling. They do not add tool/action authority.

## Vision + Voice

`VisionVoiceCoordinator` explicitly joins an existing speech transcript with a governed visual observation. The transcript becomes the visual question; all camera permission, privacy, memory and sensitive-routing checks still run. The answer can be sent through the existing Voice runtime/model speech path.

The camera never implicitly grants microphone access and the microphone never implicitly grants camera access.

## Separate biometric identity

`BiometricIdentityStore` is isolated from ordinary Vision. Camera Vision does not import or invoke it.

Biometric identity requires:

- owner-only `sensor:biometric`
- global explicit enable
- explicit enrollment consent
- an independent temporary biometric sensor session for matching
- encrypted-at-rest numeric templates
- no raw face-image enrollment in the biometric store
- profile listing and deletion

A visible person can therefore be described without Vishnu claiming who that person is. “I see a person” and “this is Vaishnav” are intentionally different authorities.

## Multimodal Sensorium context

`SensorFusionContext` combines permitted evidence from:

- Camera
- Microphone
- Screen
- Location
- other Sensors
- Memory
- Reasoning
- Computer Control state
- Device Control state

Every context envelope returns `execution_authority=false`. Camera/Microphone/Screen/Location/Memory content is untrusted evidence. Computer Control and Device Control entries are marked `authority_separate`; including their status in a reasoning context cannot authorize execution.

`/sensorium/context/reason` lets the model reason over this multimodal envelope. If it concludes that an action would help, it may only suggest the action. Execution must separately pass the canonical ToolRegistry/ApprovalManager/Computer Control or Device Control authority.

## Data and audit rules

1. Camera frames are classified sensitive at the model-routing boundary.
2. Raw frames exist only long enough to validate/privacy-process a sample.
3. Raw frame bytes/base64 are never returned by Sensorium camera responses or emitted to the event bus.
4. Audit/events contain bounded metadata, not media.
5. Visual observations are untrusted context and have `execution_authority=false`.
6. Scene-change fingerprints are low-resolution transient tuples and are not persisted as visual memory.
7. Biometric identity remains off unless separately enabled and enrolled.

## Security non-goals

Vishnu Vision is not covert surveillance, continuous recording, permanent background camera access, automatic facial recognition, or a shortcut around approvals. Camera and microphone use must remain visible, revocable, short-lived and attributable to a specific trusted device/session.
