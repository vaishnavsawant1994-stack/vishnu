# Vishnu Virtual Device Fleet

The Virtual Device Fleet extends Sensorium's Virtual Device Lab into reusable, hardware-free Android, iOS, Windows, macOS, and Linux device models.

## Purpose

The fleet exists so Vishnu can qualify device-aware behavior before real hardware is available. It is simulation only and has no physical execution authority.

## Supported virtual platforms

- Android phone
- iPhone / iOS
- Windows desktop
- macOS desktop
- Linux desktop

Each profile declares bounded Sensorium capabilities and starts with explicit virtual permission state.

## Simulated state

The fleet can simulate:

- battery percentage and charging
- Wi-Fi, cellular, Ethernet, offline and airplane-mode network state
- signal strength
- lock/unlock state
- foreground app/window observation
- camera, microphone, location, notification, clipboard and screen permissions
- GPS/location fixtures
- notification fixtures
- camera image fixtures by reference and bounded analysis
- microphone/audio fixtures by reference and bounded transcript
- device disconnect/reconnect
- standard fault scenarios for network loss, low battery, permission revocation and transport recovery

Camera and microphone simulation stores no raw binary media. Fixture references and bounded analysis/transcripts are treated as sensitive Sensorium payloads. Shared EventBus projections receive metadata only.

## Security boundary

Virtual fleet mutations change simulated state only. The fleet intentionally provides no host mouse/keyboard dispatch, application launch, URL opening, package installation, physical notification sending, or other execution method.

Vishnu's existing governed Computer Control, ToolRegistry, ApprovalManager, device/session policy, emergency stop, verification and durable recovery remain the only physical action authority.

## API authorization

The fleet is exposed under the authenticated Sensorium API.

- reads require `device:read`
- simulated state mutations require `device:admin`
- sensitive fixture operations (location, foreground-window title, notifications, camera and microphone) additionally require `memory:sensitive`

All returned fleet snapshots explicitly declare `simulated: true` and `execution_authority: false`.

## Real devices later

This layer does not claim physical-device qualification. When real Android/iOS/desktop hardware is available, the real adapters should be tested against the same observable contracts, permission lifecycle, disconnect/reconnect behavior and recovery expectations without granting Sensorium independent action authority.
