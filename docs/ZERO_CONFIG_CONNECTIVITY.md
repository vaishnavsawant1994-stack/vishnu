# Vishnu Zero-Configuration Device Connectivity

This internal milestone removes IP-address and port entry from normal Android/iOS companion setup without exposing the full Vishnu owner/control plane to the LAN.

## Trust model

1. Desktop Vishnu owns a persistent local-device TLS identity.
2. Settings → Connect phone or device starts a minimal HTTPS/WSS device gateway when needed.
3. Only the gateway is advertised with DNS-SD/mDNS as `_vishnu._tcp.local.`.
4. The QR carries a stable service ID, SHA-256 certificate fingerprint, one-use pairing token, six-digit confirmation code, and expiry. It does not carry a LAN IP/port.
5. Android uses NSD and iOS uses Bonjour to resolve the service.
6. The native app pins the discovered endpoint to the exact certificate fingerprint from the QR before sending the pairing token/code.
7. Successful pairing still enrolls through the canonical DeviceRegistry and issues the existing scoped/revocable device bearer.
8. Paired native clients persist the service ID and TLS fingerprint and rediscover the desktop after ordinary address changes.

## LAN surface

The dedicated local gateway exposes only:

- `GET /device-gateway/health`
- `POST /pair/confirm`
- `WS /device/ws/{device_id}`

It does not expose conversations, owner settings, OAuth, memory search, tool execution, dashboards, cloud relay APIs, capability administration, or `/pair/start`.

## Remote fallback

If the owner has already configured a public HTTPS Vishnu endpoint, the QR may include that normalized origin as an optional fallback. Native clients try zero-config local discovery first. No public endpoint is created automatically and no tunnel is opened implicitly.

## Security boundaries

- Pairing offers remain short-lived and one-use through the existing process-scoped PairingManager.
- mDNS advertisements contain service metadata only; no pairing token, owner secret, model key, device bearer, memory, or approval authority is advertised.
- The local self-signed certificate is accepted by native companions only when its SHA-256 leaf fingerprint matches the QR trust anchor.
- The local gateway TLS private key is stored under the Vishnu data directory with restrictive file permissions where supported.
- The full Vishnu control server keeps its existing bind/configuration behavior and is not automatically moved from loopback to the LAN.
- Simulator/emulator qualification is not physical-device evidence.
