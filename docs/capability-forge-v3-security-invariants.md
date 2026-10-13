# Capability Forge V3 Security Invariants

1. Generated source never receives raw OAuth access tokens, refresh tokens, provider client secrets, or SecretVault handles.
2. Capability OAuth grants are namespaced per capability + provider and remain owned by the existing PKCE OAuthAccountManager.
3. Generated package activation is impossible without server-recorded qualified build lineage.
4. V3 build lineage marks provenance as required; deleting `provenance.json` is a hard failure, not a legacy fallback.
5. Provenance binds manifest digest, every declared source file hash, build lineage, and a vault-keyed HMAC key ID.
6. Internal and limited canaries run without catalog activation. Generated action canaries validate only the isolated plan and never dispatch side effects.
7. Rollout promotion is sequential and consumes exact owner approvals bound to capability, version, manifest digest, device/session and security epoch.
8. Live-provider probes use existing read-only ToolRegistry tools, destination validation and verification; Forge performs no arbitrary network request.
9. Active health regression may automatically remove authority by disabling/detaching a capability. Automatic restoration, rollback, merge, deploy, or production activation is forbidden.
10. Restart rehydration verifies V3 provenance before attaching generated tools and disables provenance-required entries that fail verification.
11. Native production association data, OAuth callback origins, domains, fingerprints and Apple identifiers remain externally configured and fail readiness closed when absent.
