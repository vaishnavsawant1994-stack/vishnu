# Our Products distribution contract

## Purpose

`Our Products` turns selected Vishnu capabilities into separate Product Projects without exporting the complete Vishnu owner system. A product can represent an AI employee, agent, agent team, automation, workflow, tool, knowledge assistant, integration, SaaS application, business system, or custom product.

Vishnu remains the private factory. Client delivery is always a bounded product artifact/deployment derived from an immutable Product Project version.

Upstream product composition is documented in `OUR_PRODUCTS_PRODUCT_COMPOSER.md`.

## Product boundary

A customer Product Project does **not** receive:

- the complete Vishnu source tree
- owner conversations, memory, or private knowledge
- unrelated agents, projects, workflows, automations, or products
- another customer's data or private rules
- raw owner API keys, passwords, tokens, or signing keys
- owner-vault references such as `secret_ref`
- Owner Controls or Vishnu product-building authority

Only the bounded product contract/components/configuration and target-specific client files cross the owner/client boundary.

## Portable product package

The canonical portable contract uses the `.vishnu-product` extension. It is ZIP-compatible and contains exactly:

- `manifest.json` — sanitized `vishnu.product/v1` contract
- `package.json` — package schema, manifest digest, and signing envelope
- `checksums.json` — SHA-256 integrity metadata

Owner-side credential references are removed during distribution sanitization. When a product needs a credential, the client/runtime receives a `runtime-provisioned` requirement rather than an owner vault location.

## Production signing

Commercial product packages and product licenses use a dedicated Ed25519 trust domain:

- `VISHNU_PRODUCT_SIGNING_PRIVATE_KEY_B64`
- `VISHNU_PRODUCT_SIGNING_PUBLIC_KEY_B64`

This is intentionally separate from Vishnu application-release signing. The private key belongs only in a protected deployment secret store.

Production package generation fails closed when product signing is unavailable. Unsigned packages are permitted only through the explicit development path and remain development artifacts.

## Client verification

A production client/runtime pins the trusted Product public key and verifies:

1. allowed package structure
2. SHA-256 checksums
3. production signature presence
4. embedded signer identity against the pinned key
5. Ed25519 signature validity
6. supported manifest schema
7. relevant license/product/version binding

A downloaded public key is not trusted merely because it arrived inside the same package it is supposed to authenticate.

## Product licenses

Licenses use `vishnu.product-license/v1` and are signed in the Product trust domain. They can bind:

- product identity
- client identity
- version constraint
- license type
- start/expiry time
- maximum users/devices
- managed-AI entitlement
- server-controlled issuance metadata

Client-supplied arbitrary metadata is not accepted by the owner API. Revocation remains authoritative registry state; online/managed deployments consult revocation according to deployment policy.

## AI configuration boundary

A product can operate in one of the supported AI modes:

- disabled / no AI
- client-owned API/BYOK
- managed AI
- local/self-hosted AI
- hybrid/fallback

The manifest describes policy and requirements but never embeds a raw provider credential. No-AI products remain first-class products.

## Immutable build authority

Commercial artifacts are generated from a frozen Product Project version. A target builder must:

1. load the immutable version manifest
2. verify the requested target is enabled
3. sanitize distribution data
4. compile/generate the bounded target files
5. apply required target signing/provisioning/notarization/attestation
6. calculate and verify SHA-256 evidence
7. register the exact artifact against the product build record
8. expose download only while registered evidence still matches the artifact

Target selection alone is never treated as proof that a downloadable artifact exists.

## Local runtime targets

Web, PWA, API, and Worker have owner-side verified local artifact builders.

### Web

Generates a bounded static product shell plus sanitized manifest/runtime capability declaration.

### PWA

Generates the Web product shell plus web manifest/service worker for installable browser delivery.

### API / Worker

Generates a bounded standard-library Python host and sanitized product contract. These bundles can boot independently of the owner Vishnu installation.

Actual agent/tool execution is intentionally not implemented by copying Vishnu's owner runtime wholesale. When a Product Project requires executable intelligence, it must use a separately approved product execution/runtime connector or product-specific execution code. That boundary is what keeps the customer deliverable separate from Vishnu.

## Native and container platform runners

The native/container runner infrastructure is implemented for:

- Android
- iOS
- Windows
- macOS
- Linux
- Docker/OCI

This supersedes the older documentation that described those builders as future work.

The autonomous platform system includes:

- durable queued build jobs
- exclusive claim/lease authority
- heartbeat renewal
- bounded lease expiry
- stale-run recovery
- retry handling
- signed production job verification
- replay-safe artifact callbacks
- streamed artifact ingestion with bounded limits
- SHA-256 artifact evidence
- exact target/artifact contracts
- owner-side runner readiness projection

### Android

The runner generates/compiles a product-specific Android application. A production Android artifact is not distribution-ready without verified release signing using the configured client/product keystore.

### iOS

The Apple runner supports simulator qualification and a production IPA path. Production authority requires a valid Apple signing identity and matching provisioning profile.

### Windows

The runner builds the bounded client executable and supports dedicated Authenticode signing/verification. Unsigned development executables are not production-ready.

### macOS

The runner builds a native application bundle/DMG and supports code signing plus notarization verification. Production distribution requires both where configured by policy.

### Linux

The runner builds the bounded client runtime and DEB artifact. Linux does not inherit a fake signing result; production readiness is based on the target's actual evidence policy.

### Docker / OCI

The runner builds a product-specific image/archive and supports cosign/attestation evidence. A development image without required production attestation is not promoted as production-ready.

## Autonomous platform worker boundary

Platform workers authenticate with dedicated runner credentials and consume signed product build jobs. They receive only the immutable product build input required for that target.

A platform worker is not granted the Vishnu Product private signing key used for package/license authority. Target platform signing credentials are separately scoped to the relevant runner/environment.

## Production preflight and protected qualification

`packaging/product_production_preflight.py` checks environment-owned readiness without exposing secret values.

The protected `Our Products Production Qualification` workflow validates real environment authority for a chosen target and can optionally claim, compile, and return one real queued production Product Project build.

A target is not declared production-qualified merely because development CI compiled a sample. Final production qualification requires the real environment-owned credentials and a real end-to-end Product Project build.

Examples of external authority that must be real rather than invented include:

- Android production keystore/alias/passwords
- Apple distribution signing identity/certificate
- iOS provisioning profile
- macOS notarization credentials
- Windows Authenticode certificate/password
- Docker cosign signing/attestation authority
- production Product signing key pair
- production runner HTTPS endpoint/token

See `OUR_PRODUCTS_PRODUCTION_QUALIFICATION.md` for the operator contract.

## Artifact integrity and download

Build downloads are checksum-bound. Resolution rejects:

- product/build mismatches
- malformed artifact URIs
- path traversal
- paths outside the configured artifact root
- missing artifact files
- SHA-256 mismatch/tampering

Owner APIs do not accept arbitrary client-supplied filenames/checksums/readiness flags as production evidence.

## Current implementation boundary

Implemented software includes:

- Product Projects and sanitized manifests
- immutable versions
- Product Composer / capability reuse flow
- product signing and verification
- product license issue/revoke/verification
- Web/PWA/API/Worker artifact builders
- Android/iOS/Windows/macOS/Linux/Docker platform compiler infrastructure
- autonomous runner queue/leases/heartbeat/recovery
- build evidence/checksum/tamper validation
- owner-side build/readiness UI
- protected production preflight/qualification workflow
- CI/security/package/browser/platform qualification around the implementation

Operational production qualification still depends on real external credentials and a real production runner environment. Missing credentials keep a target fail-closed; they are not treated as missing application code and are never generated or committed to the repository.
