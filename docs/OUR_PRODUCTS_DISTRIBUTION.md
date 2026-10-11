# Our Products distribution contract

## Purpose

`Our Products` turns selected Vishnu capabilities into client-specific products without exporting the complete Vishnu owner system. A product can represent an AI employee, agent, agent team, automation, workflow, tool, knowledge assistant, integration, business system, or custom product.

The owner-side product record remains inside Vishnu. Client delivery uses a sanitized distribution manifest and separate client/runtime configuration.

## Portable product package

The canonical portable artifact uses the `.vishnu-product` extension. It is a ZIP-compatible envelope containing exactly:

- `manifest.json` — sanitized `vishnu.product/v1` product contract
- `package.json` — package schema, manifest digest and signing envelope
- `checksums.json` — SHA-256 integrity metadata

It does **not** contain:

- the complete Vishnu source tree
- owner conversations, memory or knowledge
- unrelated agents, projects or client products
- raw API keys, passwords, tokens or signing keys
- Vishnu owner-vault references such as `secret_ref`

Owner-side secret references are converted to a runtime requirement (`credentials: runtime-provisioned`). The client runtime must provision credentials independently through its approved secret store or onboarding flow.

## Production signing

Commercial product packages and product licenses use a dedicated Ed25519 signing trust domain:

- `VISHNU_PRODUCT_SIGNING_PRIVATE_KEY_B64`
- `VISHNU_PRODUCT_SIGNING_PUBLIC_KEY_B64`

Both values represent raw 32-byte Ed25519 keys encoded as base64. The private key belongs only in the protected deployment secret store. Never put it in Git, a product manifest, an application bundle, or a downloadable package.

These keys are intentionally separate from `PERSONAL_AI_RELEASE_PRIVATE_KEY_B64` / `RELEASE_PUBLIC_KEY_B64`, which protect Vishnu application releases. Compromise or rotation of one trust domain must not automatically compromise the other.

Production package generation fails closed when product signing is unavailable. An unsigned package can be generated only through the explicit development path and is marked `UNSIGNED-DEVELOPMENT`.

## Client runtime verification

A production runtime must pin the trusted Vishnu Product public key. It must not trust a public key merely because that key is embedded in the package or license.

Before loading a product, the runtime verifies:

1. package structure contains only the allowed files
2. SHA-256 checksums match
3. a production signature is present
4. the embedded signing key matches the trusted/pinned product public key
5. the Ed25519 signature over the sanitized manifest is valid
6. the manifest schema is supported

Unsigned packages are accepted only when the runtime explicitly enables development mode.

## Product licenses

Client licenses use schema `vishnu.product-license/v1` and are separately signed by the Product signing key. A license can contain:

- product ID and name
- client name
- version constraint
- license type
- start and expiry time
- maximum users
- maximum devices
- whether managed AI is included
- server-controlled issuance metadata

Client-supplied arbitrary metadata is not accepted by the owner API.

A runtime validates the signature against the pinned Product public key, product identity, optional client identity, allowed version, start time and expiry time. License revocation is an authoritative registry state: revoking a license does not mutate the original signed document, so online/managed deployments must consult the authoritative revocation status according to their deployment policy.

## AI configuration boundary

The portable product describes the AI policy but never carries a raw provider key. Depending on the product policy, credentials are supplied at runtime by:

- the client (client-owned provider/API key)
- the managed Vishnu service
- a local/self-hosted provider
- an enterprise/private provider
- a hybrid/fallback combination
- nobody, when AI is disabled

No-AI products remain valid products; deterministic workflows, integrations and business logic must not require a model merely because the product was created in Vishnu.

## Verified runtime artifacts

Web, PWA, API and Worker targets have an owner-side verified runtime-bundle builder. These artifacts are separate from the portable `.vishnu-product` contract package.

A verified runtime artifact can be generated only from a **frozen product version**. The builder:

1. loads the immutable frozen manifest
2. validates that the requested target is enabled in that frozen version
3. runs the same distribution sanitizer used by portable-package export
4. generates only the bounded client runtime files for the requested target
5. writes the artifact atomically below the configured `product-artifacts` root
6. calculates SHA-256 and re-reads the finished file to verify the digest
7. registers artifact filename, controlled `product-artifact://` URI and checksum through `ProductBuildLifecycle` using verified-builder authority
8. exposes download only while the file exists and its checksum still matches the registered evidence

Download resolution rejects artifact URI/product mismatches, malformed paths, path traversal, files outside the artifact root, missing files and checksum changes.

### Web runtime bundle

The Web bundle contains a static `index.html`, `runtime.js`, `runtime.css`, sanitized `manifest.json`, a runtime-capability declaration and a README. It is a bounded product presentation/runtime shell and never embeds the owner's Vishnu application tree.

### PWA runtime bundle

The PWA bundle contains the Web runtime plus an application web manifest and service worker so it can be installed as a standalone browser application. It remains a client product shell; native APK/IPA claims require native platform builders.

### API and Worker runtime bundles

API and Worker bundles contain a standard-library Python runtime host, sanitized product manifest, runtime-capability declaration and README. The generated runtime can boot independently of the owner's Vishnu installation and exposes product/health contract endpoints.

Actual agent/tool/work execution is intentionally declared as `runtime-connector-required`. The bundle does **not** silently copy Vishnu's owner agent/tool runtime. An approved client runtime connector or separately qualified execution runtime must be provisioned before `/invoke` can execute product work.

## Artifact API boundary

The trusted owner workspace can:

- execute a requested Web/PWA/API/Worker build with `POST /iphone/api/products/{product_id}/builds/{build_id}/execute`
- download a qualified artifact with `GET /iphone/api/products/{product_id}/builds/{build_id}/artifact`

Build execution requires a current trusted owner request context. Downloads require a trusted Vishnu device/browser session. The server does not accept owner-supplied artifact filenames, paths, checksums or readiness flags through these endpoints.

## Native platform builds

The product manifest can target Web/PWA, Android, iOS, Windows, macOS, Linux, Docker/server, API and Worker delivery. Target selection is not proof that a native artifact exists.

A native build becomes downloadable only after a target-specific builder has:

1. consumed an immutable product/version manifest
2. generated the correct application/runtime shell
3. completed target compilation
4. applied required platform signing/provisioning
5. produced a SHA-256 digest
6. passed target qualification
7. registered the exact artifact against the product build record

Until those conditions are met, Our Products records the build as requested/pending and must not claim that an APK, AAB, IPA, MSI/EXE, DMG, PKG, OCI image or other platform artifact is ready.

## Current implementation boundary

Implemented and qualified foundations include the portable `.vishnu-product` package, product signing, product-license issuance/revocation, package/license verification, immutable product versions, build lifecycle authority, and owner distribution APIs.

This tranche adds real verified **Web, PWA, API and Worker ZIP runtime artifacts** with checksum-bound downloads. It deliberately does not convert those artifacts into native mobile/desktop installers or OCI images. Android, iOS, Windows, macOS, Linux packaging and container-image production remain separate platform-runner qualification stages and stay fail-closed until implemented, signed where required, tested and registered with verified evidence.
