# Vishnu iPhone Companion

The iOS app supports joining an existing Vishnu and a native first-device
creation/recovery ceremony against a configured runtime.

The app also includes a cloud-first **Open Vishnu** route. It hands off to
Safari so the same Google sign-in, trusted-device cookie, microphone permissions,
voice experience and persistent conversations are shared with the web and desktop
surfaces. This repository can build and test an unsigned iOS Simulator artifact
without an Apple account. Installation on a physical iPhone and TestFlight still
require an Apple Developer team and Apple-issued signing assets.

## Implemented foundation

- SwiftUI iPhone app foundation (iOS 17+)
- existing Vishnu desktop pairing token + six-digit code flow
- device identity and bearer credential stored in iOS Keychain with `ThisDeviceOnly` protection
- HTTPS/WSS required by default; plaintext HTTP/WS is an explicit development-only opt-in
- authenticated `URLSessionWebSocketTask` command channel
- reconnect on foreground/active lifecycle and scheduled `BGAppRefreshTask` refresh attempts
- device info and battery commands
- local notification delivery command
- URL/universal-link/custom-scheme handoff; arbitrary app launch is not claimed because iOS restricts it
- active `AVAudioSession` voice/microphone foundation using voice-chat mode
- simulator CI workflow
- separate physical-iPhone validation workflow

Native Create my Vishnu and Restore Vishnu screens use the canonical server
first-run and recovery APIs. Device credentials and pending recovery codes are
stored in Keychain. Native creation requires a reachable HTTPS Vishnu runtime
and its high-entropy one-time bootstrap code. The app does not host or provision
the runtime, cannot create an owner offline, and does not yet register a native
passkey. Creation uses the canonical owner password and one-time recovery-code
authority. AI setup can select a supported provider or be skipped; provider
credentials are sent over HTTPS to the canonical encrypted model credential
store and are not retained by the app. Restore enrolls a new device on an existing runtime; it does not
restore a lost runtime or move data between runtimes. No physical-device Face ID
qualification is claimed by simulator tests.

## iOS lifecycle boundary

iOS normally suspends ordinary apps in the background. The companion therefore does not pretend that a WebSocket is permanently alive after the app is backgrounded. It reconnects when the app becomes active and can receive system-scheduled background refresh opportunities. Continuous background execution is reserved for legitimate Apple-supported modes, such as an active audio session.

A later push-notification stage can add production APNs wake/notification delivery for server-initiated mobile events.

## Pairing

1. Start Vishnu on the trusted computer and create the one-time pairing offer locally.
2. On iPhone, enter the computer's secure HTTPS address, pairing token, and six-digit code.
3. Pairing returns a device ID and bearer credential. The bearer is written to Keychain and is never placed in a URL.

For development on a trusted LAN only, the UI has an explicit insecure HTTP/WS toggle. Production should use trusted HTTPS/WSS.

## Generate project

```bash
cd ios-companion
brew install xcodegen
xcodegen generate
open PersonalAICompanion.xcodeproj
```

For a real iPhone, configure signing with an Apple Development team in Xcode. The physical-device GitHub workflow expects a self-hosted macOS runner with the iPhone attached plus `IOS_DEVICE_UDID` and `IOS_DEVELOPMENT_TEAM` repository secrets.
