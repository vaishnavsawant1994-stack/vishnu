# Vishnu iPhone PWA

This PWA is the responsive owner web/iPhone surface for the frozen Vishnu Home V1 and the physical-iPhone P3 qualification path.

The normal product experience is conversation-first:

- Home keeps the asymmetric living AI Core, persistent conversation, text input, document attachment and one-tap continuous voice.
- Mobile navigation exposes Home, Memory, Knowledge, Activities and More.
- The owner orb opens Settings, trusted devices and runtime/model status.
- Workflows, Apps & Tools, Devices and Dashboard remain behind progressive disclosure.
- P3 evidence controls live only in Settings > Advanced and never block normal conversation.

The responsive PWA uses the shared first-run and owner-security authority. On a genuinely uninitialized runtime, the browser can create the owner, configure a WebAuthn passkey where supported, save recovery codes, choose privacy settings and register this browser as the first trusted device. Existing owners can authenticate and enroll another browser through the current session and device system. The browser is a trusted device, not the owner identity or a Vishnu server.

Runtime requirements:

- serve `server.cloud_app:app` behind HTTPS
- configure the high-entropy one-time `PERSONAL_AI_BOOTSTRAP_SECRET` before remote first-owner creation, then invalidate it after creation
- keep `PERSONAL_AI_IPHONE_ALLOW_INSECURE=false`
- provider credentials are sent to the canonical encrypted credential store and never written to browser storage
- use persistent storage for Vishnu data and P3 evidence

The browser does not host or provision the Python runtime. A supported runtime must already be reachable; browser creation initializes its owner, while runtime location and data placement remain separate decisions. Open `/iphone/` on desktop or mobile. Enrollment creates a trusted `ios-pwa` device using the existing DeviceRegistry and stores the session in Secure, HttpOnly, SameSite cookies. A browser cookie is a session/device artifact, not the Vishnu identity. Browser-only creation still requires recovery codes and a passkey where WebAuthn is supported; no browser-only hosting claim is made.

A CI pass proves implementation readiness only. Physical voice qualification requires real iPhone sessions and the frozen P3.1 evidence gates.
