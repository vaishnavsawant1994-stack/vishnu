# Vishnu for Android

The Android application provides an existing-runtime companion and a native
first-device setup surface:

- **Open Vishnu** launches the configured Vishnu web experience in a secure Chrome
  Custom Tab. This preserves Google sign-in, trusted-device cookies, microphone
  access, voice responses and conversation continuity.
- **Advanced device pairing** retains the encrypted local-computer companion and
  background command channel. Pairing credentials stay in Android encrypted
  preferences.
- **Create my Vishnu / Restore Vishnu** can initialize the canonical owner on a
  reachable HTTPS runtime using its one-time bootstrap code, or enroll this phone
  on an existing runtime with a one-time recovery code. Each flow creates an
  independent Android device credential in encrypted preferences. Recovery codes
  remain encrypted locally while setup is pending. AI setup can select a supported
  provider or be skipped; API credentials are sent over HTTPS to the canonical
  encrypted model credential store and are not retained by this app.
- **I don't have a Vishnu runtime yet** provides the phone-only bootstrap path.
  Android generates a high-entropy one-time setup secret locally, stores it in
  encrypted preferences, copies it only on an explicit owner action, and opens
  the repository's owner-approved Render Blueprint in the system browser. The
  secret is never placed in the deployment URL. After the HTTPS runtime is live,
  the owner returns to **Create my Vishnu** and uses the same one-time code.
- **Protect Vishnu with a passkey** uses Android Credential Manager after this
  phone is a trusted owner device. Registration reuses Vishnu's canonical owner
  WebAuthn authority and is enabled only when the HTTPS runtime publishes a
  Digital Asset Link for the signed Android app. The private passkey never
  leaves Android's credential provider.
- **Restore from encrypted recovery package** accepts the authenticated `.vdr`
  archive plus its separately encrypted recovery-key file, stages them to a
  fresh HTTPS runtime, recreates fresh owner security after the restore restart,
  and enrolls this phone as a new trusted device for the same Vishnu identity.

The Android app does not embed the full Python runtime inside the APK. Instead,
a phone-only owner can explicitly provision the canonical headless Vishnu runtime
from the app, or use any compatible self-hosted HTTPS runtime they control. The
checked-in hosted template uses persistent storage and disables automatic deploys.
The hosting provider is optional infrastructure; it is not the Vishnu identity,
owner authority, or mandatory data provider.

The bootstrap secret is setup authorization, not an everyday login credential.
It is erased from Android encrypted storage after a trusted device credential is
established. Do not expose an uninitialized runtime without HTTPS and a strong
one-time bootstrap secret.

Native passkey support is deliberately fail-closed: internal/testing builds do
not hard-code a production runtime or signing association. Release configuration
must supply the approved HTTPS runtime and signed-app association before passkey
registration can succeed.

CI builds an installable debug APK and publishes it with a SHA-256 checksum. The
debug artifact is suitable for owner testing and must be replaced by a privately
held release signing key before public distribution or Play Store publishing.