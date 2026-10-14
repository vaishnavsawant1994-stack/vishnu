# Vishnu iPhone Companion

The iOS app supports joining an existing Vishnu and a native first-device
creation/recovery ceremony against a configured runtime.

The app also includes an **Open Vishnu** route through Safari so the same Google
sign-in, trusted-device cookie, microphone permissions, voice experience and
persistent conversations are shared with the web and desktop surfaces. This
repository can build and test an unsigned iOS Simulator artifact without an
Apple account. Installation on a physical iPhone and TestFlight still require
an Apple Developer team and Apple-issued signing assets.

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
- native owner passkey registration through Apple Authentication Services
- phone-only owner-controlled runtime provisioning through the checked-in hosted Blueprint
- portable `.vdr` disaster-recovery import into a fresh Vishnu runtime
- simulator CI workflow
- separate physical-iPhone validation workflow

Native **Create my Vishnu** and recovery screens use the canonical server
first-run, owner-security, device-registry and disaster-recovery APIs. Device
credentials and pending recovery material are stored in Keychain.

If no Vishnu runtime exists yet, **I don't have a Vishnu runtime yet** generates
a high-entropy one-time bootstrap secret locally in Keychain and opens the
owner-approved Render deployment in Safari. The secret is copied only on an
explicit owner action and is never placed in the deployment URL. After the
provider creates the HTTPS runtime, the owner returns to **Create my Vishnu**
and uses that runtime address and the same one-time code. The temporary code is
removed from Keychain after this iPhone has a trusted device credential.

The iPhone app does not embed the full Python runtime inside the iOS application.
Instead, a phone-only owner can explicitly provision the canonical headless
Vishnu runtime from the app, or use another compatible self-hosted HTTPS runtime.
The hosting provider is optional infrastructure; it does not become the Vishnu
identity, owner authority, or mandatory data provider.

After this iPhone becomes a trusted owner device, **Protect Vishnu with a
passkey** uses Apple Authentication Services against the same canonical
`OwnerAccessStore` WebAuthn authority used by the browser. Passkey registration
fails closed unless the signed app and HTTPS runtime share an explicit Apple
`webcredentials` association. The checked-in project uses the non-routable
`passkeys.invalid` build setting until an approved runtime domain is supplied.
Face ID / Touch ID are used by the operating system to protect the passkey when
available; simulator qualification does not claim physical biometric coverage.

**Restore from encrypted recovery package** accepts the authenticated `.vdr`
package plus its separately passphrase-encrypted recovery-key file, stages both
to a fresh HTTPS runtime, schedules restore before normal runtime startup, then
creates fresh owner security and enrolls this iPhone as a new trusted device for
the same stable Vishnu identity. Password hashes, passkeys, sessions, recovery
hashes and old device-private credentials are deliberately not restored.

AI setup can select a supported provider or be skipped; provider credentials are
sent over HTTPS to the canonical encrypted model credential store and are not
retained by the app.

## iOS lifecycle boundary

iOS normally suspends ordinary apps in the background. The companion therefore
does not pretend that a WebSocket is permanently alive after the app is
backgrounded. It reconnects when the app becomes active and can receive
system-scheduled background refresh opportunities. Continuous background
execution is reserved for legitimate Apple-supported modes, such as an active
audio session.

A later push-notification stage can add production APNs wake/notification
delivery for server-initiated mobile events.

## Pairing

1. Start or provision Vishnu on an owner-controlled HTTPS runtime and create the one-time pairing offer.
2. On iPhone, enter or scan the runtime's secure address, pairing token, and six-digit code.
3. Pairing returns a device ID and bearer credential. The bearer is written to Keychain and is never placed in a URL.

For development on a trusted LAN only, the UI has an explicit insecure HTTP/WS
toggle. Production should use trusted HTTPS/WSS.

## Generate project

```bash
cd ios-companion
brew install xcodegen
xcodegen generate
open PersonalAICompanion.xcodeproj
```

For a real iPhone, configure signing with an Apple Development team in Xcode.
The physical-device GitHub workflow expects a self-hosted macOS runner with the
iPhone attached plus `IOS_DEVICE_UDID` and `IOS_DEVELOPMENT_TEAM` repository
secrets.
