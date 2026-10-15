# Vishnu Sensorium 2.0 — Context Awareness & World Model

Sensorium 2.0 extends Vishnu from governed Vision into governed physical/digital context awareness.

The architectural invariant is non-negotiable:

> **Perception is evidence, never authority.**
>
> Seeing, hearing, locating, sensing, remembering, inferring, detecting a gesture, or observing an IoT state never authorizes Vishnu to click, type, change a device, control an appliance, execute a tool, or bypass an approval.

The pipeline is:

`Physical/Digital Sensors → Permission & Attention Manager → Local Privacy Processing → Temporal Sensor Fusion → World Model → Memory → Reasoning → Proposed Action → Approval/Policy → Computer/Device/IoT Control`

## 1. Full phone sensor support

Android exposes, when present and permitted: GPS/network location, accelerometer, gyroscope, magnetometer/compass basis, rotation/orientation, step/motion hints, proximity, ambient light, barometer, ambient temperature/humidity when hardware provides them, battery, thermal status and network state.

iOS uses CoreLocation/heading, CoreMotion accelerometer/gyro/device motion/magnetic accuracy, CMAltimeter, UIDevice proximity/orientation/battery, ProcessInfo thermal state and Network path state. Apple does not expose public ambient-light lux to ordinary third-party iOS apps, so Vishnu reports it unavailable rather than fabricating it.

Hardware absence is represented as unavailable; values are never invented.

## 2. Per-sensor permission authority

`SensorPermissionStore` is the canonical authority for camera, microphone, screen, location, motion, clipboard, network, environment, spatial, document, wearable, IoT and separately default-deny biometrics.

Persistent modes are only `never` and `ask`. Temporary use is an expiring `session` grant; there is no durable silent `always allow` mode. Policy changes, grants, expiry and revocation are audited. Process restart invalidates temporary grants and Stop All Sensing revokes all active sessions.

DeviceRegistry `sensor:*` scopes are only coarse request authorities. The target device still has to prove local owner consent with the exact active session ID before a read is accepted.

Clipboard context is implemented on Android and iOS as foreground/session-only bounded text/type metadata. It is never silently read in the background and is not automatically retained.

## 3. Mobile screen understanding

Android uses MediaProjection with Android system consent and a persistent foreground notification. Frames are locally redacted/downsampled, OCR runs locally first, a scene fingerprint detects change, snapshots are bounded, and raw frames are not retained.

iOS uses owner-started ReplayKit while Vishnu is foreground-active. OS recording indicators remain authoritative; frames are downsampled and edge-redacted before OCR/model reasoning. Vishnu does not use private APIs to defeat platform privacy controls.

## 4. Environmental audio intelligence

Environmental audio is separate from conversational Voice. Android AudioRecord and iOS AVAudioEngine extract local semantic features including RMS/peak energy, zero-crossing rate, clipping, VAD, activity ratio, energy variation and speaker-turn transitions.

Conservative local labels include silence, speech-likely, alarm-tone-likely, doorbell-likely, appliance-hum-likely, mechanical-noise-likely, music-likely, ambient-noise and unknown. These are context cues, not identity or safety-critical classifiers. Ambiguous audio remains unknown. Raw continuous audio is not uploaded or retained by this path, and the rolling feature window resets after a semantic observation.

## 5. Attention Manager

`AttentionManager` selects the smallest useful set of permitted sensors. It consults memory before waking hardware, respects privacy-denied sensors and the caller's permissions, reduces simultaneous sensing under low battery, and returns a plan only. It never grants or activates a sensor.

## 6. Temporal World Model

`TemporalWorldModel` is a SQLite semantic world state with persistent object identities, timestamped observations, source/modality, confidence, freshness, contradiction state and semantic relationships. Raw camera/video/audio media is not stored in the World Model.

Conflicting fresh evidence is preserved rather than overwritten. Current semantic state is selected using effective confidence after freshness decay while contradiction history remains auditable. Relationships can move from `screwdriver --on--> desk` to `screwdriver --in_hand_of--> owner` without erasing the earlier evidence.

## 7. Cross-modal reasoning

Fusion accepts camera, audio, screen, location, motion, environment, network, spatial, document, wearable, IoT, memory and reasoning evidence. Every item carries source, timestamp/age, freshness, raw/effective confidence, confidence band and uncertainty. Fusion groups temporally aligned observations and surfaces cross-source conflicts. Model prompts explicitly state that all observations are untrusted evidence and never action authority.

## 8. Spatial / 3D intelligence

Android's visible ARCore Spatial View provides world tracking, camera pose, depth capability when supported, bounded point-cloud geometry and ephemeral anchors.

iOS ARKit provides camera pose, scene/smoothed depth when supported, mesh reconstruction on capable hardware, feature points and plane/mesh anchors.

`SpatialWorld` normalizes 3D anchors and relationships such as left/right, above/below, in-front/behind and distance. Spatial perception grants no control authority.

## 9. Hands, gestures and pose

Android uses local ML Kit pose detection over the already-visible Vision frame, including wrist/index/thumb points and pointing direction. iOS uses Vision body/hand pose requests with local pointing vectors. This supports phrases such as “this cable” without treating a gesture as permission to act.

## 10. Native OCR / barcode / QR / document intelligence

Android uses local ML Kit text recognition and barcode scanning; iOS uses Vision text recognition and barcode requests. Server normalization covers OCR text, barcodes/QR, structured fields, serial/model/part/IMEI-like candidates and handwriting indicators. Local extraction runs before an expensive multimodal model is considered, and raw image retention defaults off.

## 11. Multimodal episodic memory

`EpisodicMemoryManager` supports `none`, `summary`, `event` and `media`. Selected media is accepted only when explicitly chosen and privacy-processed, then encrypted with AES-GCM and a SecretVault-managed DEK. Raw continuous audio/video streams are never episodic-memory inputs.

## 12. Privacy zones and bystander protection

Privacy-zone definitions are encrypted through SecretVault and may match context tags and/or geofences. A zone can deny sensors, require local processing, require bystander redaction, forbid media retention, mark screens private and enable meeting-mode microphone blocking. Zones only restrict; they can never grant a sensor.

The semantic World Model intentionally avoids persisting exact latitude/longitude from mobile location observations by default.

## 13. Wearables

Wearable support now has both a normalized evidence boundary and native phone-side transports:

- Apple Watch observations can arrive through iOS WatchConnectivity.
- Wear OS observations can arrive through the Android Wear OS Data Layer.
- Earbud/headphone connection-route context is exposed semantically on iOS and Android without reading audio content.
- Smart-glasses/body-camera semantic relays are represented through the paired-phone boundary.

Every wearable path still requires an explicit temporary `sensor:wearable` session on the phone. Native relays refuse raw image/video/audio media; glasses/body-camera camera or microphone streams must use the separately governed camera/microphone Sensorium paths. The server pulls wearable observations through the existing trusted DeviceGateway and validates the exact local session proof.

Native transport code does not itself constitute real-watch/glasses hardware qualification; physical acceptance remains L4 evidence.

## 14. Smart-home and IoT Sensorium

`IoTSensorRegistry` separates observe capabilities such as `temperature` from action capabilities such as `set_temperature`. Observations are untrusted Sensorium evidence. Action requests can only become proposals with `requires_approval=true`, `execution_authority=false` and handoff to the existing ToolRegistry/ApprovalManager/Device Control authorities.

Sensorium 2 also includes a real read-only Home Assistant observation adapter. It uses an owner-registered exact base URL, stores bearer credentials in SecretVault, blocks redirects, bounds time/response size, revalidates DNS/address safety, permits cleartext HTTP only when the owner explicitly registers a private/loopback endpoint, and reads only `/api/states/{entity}`. It has no Home Assistant service/action endpoint, so the observation adapter cannot change an appliance.

## 15. Proactive physical-world assistance

`ProactivePhysicalAssistant` is task-bound, expiring and sensor-bounded. It requires an explicit purpose, an explicit allowed-sensor set and a maximum one-hour lifetime. Only sufficiently significant/confident observations create owner cues; cues never act automatically. This supports “watch while I assemble this” without general ambient surveillance.

## 16. Confidence and uncertainty

`PerceptionEvidence` carries confidence, freshness and uncertainty. Effective confidence decays with age and maps to high/medium/low bands. Reasoning receives those values so Vishnu can say that evidence is partial, obscured or stale instead of pretending certainty.

## 17. Sensor disagreement handling

Fusion surfaces incompatible cross-source fields instead of concatenating them. The World Model retains contradicted observations and selects current state using confidence/freshness while preserving history for audit and later reasoning.

## 18. Sensor health / calibration

`SensorHealthMonitor` checks stale or clock-skewed timestamps, blocked/dark/blurred visual inputs when supplied, muted/silent/clipping audio, invalid motion numbers, motion calibration, overly coarse location accuracy and offline network state. High-severity findings prevent that evidence from being considered reasoning-ready.

## 19. L4 real-device qualification

Emulator/simulator/hosted-VM qualification remains L3 or lower. `PhysicalDeviceQualification` requires `physical_device=true` plus platform-specific scenarios. The manual `Sensorium L4 Physical Device Lab` runs only on explicitly labelled self-hosted physical-device runners and fails closed if real-device evidence is absent.

Required scenario categories include OS camera/microphone indicators, real permission UX, camera switching, USB-camera behavior where applicable, thermal behavior, battery drain, background behavior and related physical-platform checks.

**The existence of this code/workflow is not an L4 claim.** Android, iPhone, Windows, macOS and Linux are L4 only after real physical evidence passes every required scenario.

## 20. Sensorium Privacy Dashboard

Backend `/owner/ai/sensorium/v2/privacy-dashboard` returns per-sensor policy/session state, active sessions and expiration, recent permission audit, privacy zones, current L4 state and Stop All availability.

Android and iOS have owner-facing native privacy dashboards showing current session state/countdowns, reason/resource, retention defaults and recent local session audit. The server remains the durable per-device audit authority. Stop All releases camera/screen/audio/spatial/wearable paths and revokes temporary sessions.

## Mobile remote request behavior

Remote Vishnu may request a sensor session, but it cannot grant one. Android raises a high-priority owner notification that opens local consent UI. iOS raises an owner notification and requires the user to open Sensorium Privacy. Only local interaction creates the temporary grant.

## Retention defaults

- raw continuous audio: not retained
- raw screen frames: not retained by screen-understanding path
- raw camera frames: not retained by Vision
- clipboard context: transient, not automatically retained
- wearable relay observations: semantic-only; raw media rejected
- exact mobile location: not written into the semantic World Model by default
- semantic observations: retained only according to owner memory policy
- selected media: only explicitly selected, privacy-processed media may be retained

## Non-goals

Sensorium 2.0 does not implement covert sensing, permanent silent camera/microphone/location/screen access, passive general surveillance, automatic action authority from perception, hidden facial identity matching, fake L4 qualification, or private OS APIs that defeat platform privacy controls.

## Qualification terminology

- **Implemented**: the code path exists; this label becomes release-ready only after its exact-head tests/builds pass.
- **L3 qualified**: vendor emulator/simulator/hosted-VM qualification passed.
- **L4 qualified**: real physical-hardware scenarios passed and evidence was recorded.
- **Production accepted**: separately deployed and owner/provider acceptance completed.

Do not collapse these labels in release claims.
