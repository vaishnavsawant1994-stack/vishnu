# Capability Forge V3 — Production Readiness Boundary

Capability Forge V3 extends the merged V1/V2 implementation without creating a second catalog, approval engine, ToolRegistry, Engineering Runtime, OAuth manager, canary evaluator, or deployment authority.

## Added in V3

- Capability-scoped OAuth namespaces over the existing PKCE OAuthAccountManager and SecretVault.
- Durable state-to-capability OAuth callback routing.
- Vault-keyed HMAC provenance binding the generated manifest, every declared source file, and Forge build lineage.
- Durable provenance-required build markers so a missing sidecar cannot downgrade a V3 package to legacy activation behavior.
- Staged canary flow: internal -> limited -> broad_eligible, with existing Engineering canary comparison logic.
- Exact owner approval for every rollout promotion.
- Read-only live-provider verification through existing ToolRegistry authorization/verification boundaries only.
- Automatic health quarantine that can only remove authority; restoration and rollback remain owner-approved.
- Provenance-aware restart rehydration that disables tampered V3 catalog entries before runtime exposure.
- Production/native readiness validation for HTTPS origin, OAuth callback, Android App Links, iOS Universal Links, native PKCE redirect registrations, provenance, provider verification, canary support, and capability OAuth.

## Explicit non-authorities

V3 does not create or hard-code production domains, OAuth clients, Android signing fingerprints, Apple Team IDs, provider credentials, deployments, releases, merges, pushes, or production activation. Production activation remains false until operator-supplied configuration and the repository's independent release gates establish authority.

## Production configuration

The runtime expects externally supplied values such as:

- `VISHNU_PUBLIC_BASE_URL`
- `VISHNU_CAPABILITY_OAUTH_REDIRECT_URI`
- `VISHNU_NATIVE_CLIENT_REDIRECTS`
- `VISHNU_ANDROID_ASSET_LINKS_JSON`
- `VISHNU_APPLE_APP_SITE_ASSOCIATION_JSON`

Missing or inconsistent production configuration fails readiness closed rather than falling back to a baked-in host.
