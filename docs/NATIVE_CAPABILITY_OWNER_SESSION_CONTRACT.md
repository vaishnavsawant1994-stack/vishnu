# Native owner-session security contract (PR #183)

## Existing authority

The browser owner-session implementation is `security/pwa_sessions.py` and `server/pwa_session_middleware.py`. The capability API requires a `TrustedRequestContext` backed by an active device and authorization scope; sensitive mutations also require recent owner reauthentication (300 seconds). The Android/iOS companion pairing bearer is **not** an owner-session credential. Never accept it as such.

## Required native flow (not yet implemented)

1. Native app starts a system-browser authentication request using a one-time, expiring challenge bound to the requesting app, installation, and redirect URI. Use a platform-verified Android App Link / iOS Universal Link; reject unregistered redirects.
2. Owner authenticates through the existing Vishnu owner login and explicitly approves native access. The server verifies the existing authenticated session and current device authority. A device-pairing token alone cannot authorize this step.
3. Server issues a short-lived **single-use authorization code** bound to the challenge and PKCE S256 verifier, with an atomic consumption transaction. Do not put bearer tokens in redirect URLs.
4. Native app exchanges the code and PKCE verifier over HTTPS. Server creates a revocable, narrowly scoped native session associated with the owner/device and stores only a hash of the bearer credential. Never derive authority from client-provided device IDs or scopes.
5. Android stores credentials in Android Keystore-backed encrypted storage; iOS stores them in Keychain with appropriate accessibility. Do not log or back up bearer credentials. Implement explicit logout and revoke, expiry and rotation; ensure stolen refresh tokens cannot be replayed.
6. Authentication middleware validates the native token server-side on every capability API request, checks revocation, active owner/device, audience, scopes, and recent reauthentication for privileged operations, then constructs the trusted request context. Native and browser flows share the same authorization rules; neither can forge `TrustedRequestContext` from arbitrary headers.
7. Cover replay, code substitution, cross-device exchange, invalid PKCE, expired sessions, revoked devices, logout, scope escalation, and concurrency with integration tests. Run Android instrumentation and iOS device tests before exposing privileged UI actions.

## Release gate

The current companions open the browser capability console; **native direct API management remains blocked** until all above are implemented and tested. Existing browser owner sessions remain the supported management path. Do not claim native capability management is complete or merge PR #183 on this document alone.
