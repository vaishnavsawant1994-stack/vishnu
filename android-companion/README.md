# Vishnu for Android

The Android application provides an existing-runtime companion and a native
first-device setup surface:

- **Open Vishnu** launches the production cloud experience in a secure Chrome
  Custom Tab. This preserves Google sign-in, trusted-device cookies, microphone
  access, voice responses and conversation continuity.
- **Advanced device pairing** retains the encrypted local-computer companion and
  background command channel. Pairing credentials stay in Android encrypted
  preferences.
- **Create my Vishnu / Restore Vishnu** can initialize the canonical owner on a
  separately provisioned, reachable HTTPS runtime using its one-time bootstrap
  code, or enroll this phone on an existing runtime with a one-time recovery
  code. Each flow creates an independent Android device credential in encrypted
  preferences. Recovery codes remain encrypted locally while setup is pending.
  AI setup can select a supported provider or be skipped; API credentials are
  sent over HTTPS to the canonical encrypted model credential store and are
  not retained by this app.

This app does not host the Vishnu runtime, create a runtime deployment, perform
offline owner initialization, or currently register an Android passkey. The
owner password and recovery code remain the supported native creation and
recovery methods. The bootstrap code is a short-lived setup authorization, not
an everyday login credential. Do not expose an uninitialized runtime publicly
without configuring its high-entropy bootstrap secret and HTTPS.

CI builds an installable debug APK and publishes it with a SHA-256 checksum. The
debug artifact is suitable for owner testing and must be replaced by a privately
held release signing key before public distribution or Play Store publishing.
