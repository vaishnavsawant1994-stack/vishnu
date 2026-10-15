# Vishnu Sensorium 2.0 — Context Awareness & World Model

Sensorium 2.0 extends Vishnu from governed Vision into governed physical/digital context awareness.

The architectural invariant is non-negotiable:

> **Perception is evidence, never authority.**
>
> Seeing, hearing, locating, sensing, remembering, inferring, detecting a gesture, or observing an IoT state never authorizes Vishnu to click, type, change a device, control an appliance, execute a tool, or bypass an approval.

The target pipeline is:

`Physical/Digital Sensors → Permission & Attention Manager → Local Privacy Processing → Temporal Sensor Fusion → World Model → Memory → Reasoning → Proposed Action → Approval/Policy → Computer/Device/IoT Control`

## 1. Full phone sensor support

Android exposes, when present and permitted:

- location / GPS / network location
- accelerometer
- gyroscope
- magnetometer / compass basis
- rotation vector / orientation
- step / motion hints
- proximity
- ambient light
- pressure / barometer
- ambient temperature / humidity when hardware provides them
- battery
- thermal status
- network connectivity / transport / metering

Android hardware absence is represented as unavailable; values are never invented.

On iOS Vishnu uses:

- CoreLocation + heading
- CoreMotion accelerometer / gyro / device motion / magnetic-field accuracy
- CMAltimeter
- UIDevice proximity, orientation and battery
- ProcessInfo thermal state
- Network framework path state

Apple does not expose a public ambient-light lux sensor API to ordinary third-party apps. iOS therefore reports ambient-light lux as unavailable rather than estimating or fabricating it.

## 2. Per-sensor permission authority

`SensorPermissionStore` is the canonical Sensorium session authority for:

- camera
- microphone
- screen
- location
- motion
- clipboard
- network
- environment
- spatial
- document
- wearable
- IoT
- biometrics (separate, default-deny)

Persistent modes are only:

- `never`
- `ask`

Temporary use is represented by an expiring `session` grant. There is no durable `always allow` / silent sensor mode.

All policy changes, grants, expiry and revocation are auditable. Process restart invalidates temporary grants. `revoke_all()` supports Stop All Sensing.

DeviceRegistry scopes such as `sensor:location` or `sensor:screen` are coarse **request** authorities only. They do not grant the sensor. The target device must still create a local Sensorium session after owner consent.

## 3. Mobile screen understanding

### Android

Android uses MediaProjection, requiring Android's system screen-sharing consent. A foreground notification remains visible during capture.

Each snapshot:

- is captured only while the MediaProjection session is active
- redacts system status/navigation areas locally
- is downsampled locally
- runs local OCR first
- calculates a local scene fingerprint
- reports whether the screen changed
- is bounded to 1.5 MB before server processing
- is not retained as a raw frame by the companion

### iOS

iOS uses owner-started ReplayKit capture while Vishnu is foreground-active. ReplayKit provides the OS recording indicator. Frames are downsampled and system-edge areas are locally redacted before OCR or model reasoning.

ReplayKit/App Store platform restrictions remain authoritative. Vishnu does not attempt private APIs or covert capture of other apps.

## 4. Environmental audio intelligence

Sensorium environmental audio is separate from conversational Voice.

Android AudioRecord and iOS AVAudioEngine perform local feature extraction:

- RMS energy
- zero-crossing rate
- clipping fraction
- VAD / speech-likely state
- speaker-turn transition count
- short semantic event labels such as silence, speech-likely, alarm-tone-likely, mechanical-noise-likely and ambient-noise

Raw continuous audio is not uploaded or retained by this path. The rolling feature window resets after a semantic observation.

## 5. Attention Manager

`AttentionManager` chooses the smallest useful set of permitted sensors for a purpose. It:

- consults memory before waking hardware
- respects privacy-denied sensors
- respects the caller's permitted sensor set
- reduces simultaneous sensors when battery is low
- returns an attention plan only
- **never grants or activates a sensor session**

## 6. Temporal World Model

`TemporalWorldModel` is a SQLite semantic world state containing:

- entities / persistent object identities
- observations over time
- source + modality
- confidence
- freshness window
- contradiction state
- semantic relationships

Raw camera/video/audio media is not stored in the World Model.

Conflicting fresh evidence is retained as contradiction history. The current semantic state prefers non-contradicted evidence with higher effective confidence after freshness decay.

Example:

- `screwdriver --on--> desk`
- later `screwdriver --in_hand_of--> owner`

Older relations can become inactive without being erased from the evidence history.

## 7. Cross-modal reasoning

Sensor fusion accepts camera, audio, screen, location, motion, environment, network, spatial, document, wearable, IoT, memory and reasoning evidence.

Each item carries:

- source
- timestamp
- age
- freshness score
- raw confidence
- effective confidence
- confidence band
- uncertainty notes

Fusion creates temporal groups and surfaces common field conflicts. The governed model receives an explicit instruction that observations are untrusted evidence and that proposed actions still require independent authority.

## 8. Spatial / 3D intelligence

### Android

The visible ARCore Spatial View provides:

- world tracking
- camera pose
- depth support when ARCore reports it
- bounded local point-cloud geometry
- ephemeral 3D anchors

### iOS

ARKit provides:

- world tracking
- camera pose
- scene depth / smoothed scene depth when supported
- scene mesh reconstruction on capable hardware
- raw feature points
- plane / mesh anchors

`SpatialWorld` normalizes 3D anchors and relationships such as left/right, above/below, in-front/behind and distance.

No AR observation grants physical-device control.

## 9. Hands, gestures and pose

Android uses local ML Kit pose detection over the already-visible, privacy-processed Vision frame. It extracts body joints plus wrist/index/thumb points and pointing direction.

iOS uses Vision body-pose and hand-pose requests, including wrist/index/thumb/middle points and local pointing vectors.

This enables task phrases such as “this cable” without turning gesture detection into an action permission.

## 10. Native OCR / barcode / QR / document intelligence

Android uses local ML Kit text recognition and barcode scanning.

iOS uses Vision text recognition and barcode requests.

The server normalizes:

- OCR text
- barcodes / QR values
- structured fields supplied by the client
- serial / model / part / IMEI-like candidates
- handwriting indicator

Local extraction is used before a multimodal model is considered. Raw image retention defaults off.

## 11. Multimodal episodic memory

`EpisodicMemoryManager` supports:

- `none` — Don't remember
- `summary` — semantic summary only
- `event` — semantic summary + structured event metadata
- `media` — semantic memory + explicitly selected privacy-processed media

Selected media is locally encrypted with AES-GCM and a DEK stored through SecretVault. Media is rejected unless marked privacy-processed. Raw continuous audio/video streams are never episodic-memory inputs.

## 12. Privacy zones and bystander protection

Privacy zones are encrypted through SecretVault and may match context tags and/or an exact location geofence.

Zones can only make sensing stricter:

- deny named sensors
- require local processing
- require bystander redaction
- forbid media retention
- mark screen context private
- enable meeting-mode microphone blocking

Privacy zones never grant a sensor.

Exact zone definitions are stored encrypted. The World Model intentionally avoids persisting exact latitude/longitude from mobile location snapshots; it retains bounded semantic/coarse context instead.

## 13. Wearables

`WearableSensorium` normalizes observations from:

- Apple Watch
- Wear OS
- earbuds
- smart glasses
- body-camera-class devices
- future wearables

Registering a wearable does not grant its camera or microphone. Glasses/body cameras remain governed camera sensors and require the same explicit session authority as phone Vision.

Vendor-specific companion apps/transports can feed this normalized boundary without changing the Sensorium trust model.

## 14. Smart-home and IoT Sensorium

`IoTSensorRegistry` explicitly separates:

- observe capabilities, e.g. `temperature`
- action capabilities, e.g. `set_temperature`

Observations become untrusted Sensorium evidence.

An IoT action endpoint can only create a proposal with:

- `requires_approval=true`
- `execution_authority=false`
- explicit handoff to ToolRegistry / ApprovalManager / Device Control

Sensorium cannot execute the IoT change itself.

## 15. Proactive physical-world assistance

`ProactivePhysicalAssistant` is task-bound, expiring and sensor-bounded.

A session requires:

- explicit purpose
- explicitly allowed sensors
- bounded lifetime (maximum one hour)

Only significant, sufficiently confident observations produce an owner cue. Cues do not act automatically.

This permits “watch while I assemble this” without creating general ambient surveillance.

## 16. Confidence and uncertainty

`PerceptionEvidence` carries confidence, freshness and uncertainty. Effective confidence decays with age and maps to:

- `high`
- `medium`
- `low`

Reasoning prompts explicitly expose these values so Vishnu can say that evidence is partial or stale instead of pretending certainty.

## 17. Sensor disagreement handling

Fusion surfaces cross-source conflicts rather than concatenating incompatible values.

The World Model retains contradicted observations. Current-state selection uses confidence and freshness while preserving evidence history for audit and later reasoning.

## 18. Sensor health / calibration

`SensorHealthMonitor` checks for conditions such as:

- stale/clock-skewed timestamps
- blocked/dark/blurred visual inputs when supplied by the client
- muted/silent/clipping audio
- invalid motion numerics
- uncalibrated motion accuracy
- overly coarse location accuracy
- offline network state

High-severity health findings block that evidence from being treated as reasoning-ready.

## 19. L4 real-device qualification

Emulator/simulator/hosted-VM qualification remains L3 or lower.

`PhysicalDeviceQualification` requires `physical_device=true` plus platform-specific scenarios. The manual `Sensorium L4 Physical Device Lab` workflow runs only on explicitly labeled self-hosted physical-device runners and fails closed when real-device evidence is absent.

Required scenario categories include camera/microphone OS indicators, permission UX, real camera switching, USB camera behavior where applicable, thermal behavior, battery drain and background behavior.

**The existence of the workflow is not an L4 qualification claim.** A platform is L4 only after real physical evidence passes every required scenario.

## 20. Sensorium Privacy Dashboard

Backend `/owner/ai/sensorium/v2/privacy-dashboard` returns:

- per-sensor policy/session state
- active temporary sessions
- expiration
- recent permission audit history
- privacy zones
- current L4 qualification state
- Stop All availability

Android and iOS include owner-facing Sensorium privacy controls. Stop All releases active camera/screen/audio/spatial hardware paths and revokes Sensorium sessions.

## Mobile remote request behavior

A remote Vishnu request can ask the paired phone for a sensor session.

It cannot grant one.

Android raises a high-priority owner notification that opens a local consent activity. iOS raises an owner notification instructing the owner to open Sensorium Privacy. Only local interaction creates the temporary grant.

## Retention defaults

- raw continuous audio: not retained
- raw screen frames: not retained by screen-understanding path
- raw camera frames: not retained by Vision
- exact mobile location: not written into the semantic World Model by default
- semantic observations: may be held according to owner memory policy
- selected media: only when explicitly chosen and privacy-processed

## Non-goals

Sensorium 2.0 does not implement:

- covert sensing
- permanent silent camera/microphone/location/screen access
- passive general-surveillance mode
- automatic action authority from sensor evidence
- hidden facial identity matching
- fake L4 qualification based on simulators
- private OS APIs to defeat platform privacy controls

## Qualification status terminology

- **Implemented**: code path exists and is covered by repository tests/builds.
- **L3 qualified**: vendor emulator/simulator/hosted VM qualification passed.
- **L4 qualified**: real physical hardware scenarios passed and evidence was recorded.
- **Production accepted**: separately deployed and owner/provider acceptance completed.

Do not collapse these labels in release claims.
