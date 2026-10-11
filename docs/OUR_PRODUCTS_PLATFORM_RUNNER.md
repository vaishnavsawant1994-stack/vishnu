# Our Products platform runner

## Purpose

The platform runner is the governed compilation boundary for product targets that should not be compiled inside the Vishnu web process. It is designed for Android, iOS, Windows, macOS, Linux and container builds.

The owner runtime creates a build request first. A platform build job can then be produced only from the immutable frozen product version referenced by that build. The build job contains a sanitized product manifest, target/build identity, requested artifact kinds and explicit isolation constraints. It never exports owner conversations, memory, unrelated products, the complete Vishnu source tree or owner-side credential references.

## Trust boundaries

Production build jobs are signed with the dedicated Vishnu Product Ed25519 signing key. The runner verifies the build-job signature and can pin `VISHNU_PRODUCT_SIGNING_PUBLIC_KEY_B64` so a valid signature from an unexpected product signing key is still rejected.

A separate `VISHNU_PRODUCT_RUNNER_TOKEN` authenticates the external compiler when it retrieves a production build job or uploads its resulting artifact. This token is builder authority and must be stored only in the Vishnu deployment secret store and the trusted runner's secret store.

The owner browser cannot directly supply artifact filename, URI, checksum or signing evidence to the build lifecycle. Those fields are registered only by the verified local builder or authenticated platform runner adapter.

## Owner flow

1. Configure the product and target in **Our Products**.
2. Freeze the product version.
3. Request a build for Android, iOS, Windows, macOS, Linux or Docker.
4. Configure product signing and the dedicated runner token.
5. The trusted runner retrieves `/iphone/api/products/runner/{product_id}/{build_id}/job` with its bearer token. Retrieving the job advances the build into `running` state.
6. The runner validates the signed job, compiles the isolated client product and verifies its output digest/signing state.
7. The runner uploads raw artifact bytes to `/iphone/api/products/runner/{product_id}/{build_id}/artifact` with artifact name, SHA-256, platform-signing result and bounded runner metadata headers.
8. Vishnu writes the artifact under the product-artifact root, re-hashes the finished file and records evidence through `ProductBuildLifecycle` with verified-builder authority.
9. Native Android/iOS/Windows/macOS artifacts become normal downloadable production artifacts only when platform signing is reported verified by the authenticated runner. Unsigned/debug native outputs remain non-ready.

The owner can also download a build job manually from `/iphone/api/products/{product_id}/builds/{build_id}/platform-job`. Production job download requires product signing. `?development=true` explicitly produces an unsigned development job.

## Android compiler adapter

`packaging/product_platform_runner.py` now implements the Android adapter.

It generates a clean Android application project from the build job rather than copying `android-companion` or the Vishnu application. The generated app contains only:

- the sanitized frozen product manifest
- a product-specific Android application ID derived from product ID
- a bounded product UI shell
- the declared product/component summary
- no owner source tree, memory database or credentials

The adapter builds a debug APK when production Android signing secrets are absent. Debug APKs are intentionally returned with `platform_signing_verified=false`, so native build lifecycle policy does not expose them as production-ready artifacts.

When all of these runner secrets are configured, the adapter builds `release` and verifies the final APK with `apksigner` before reporting platform signing as verified:

- `VISHNU_ANDROID_KEYSTORE_PATH`
- `VISHNU_ANDROID_KEY_ALIAS`
- `VISHNU_ANDROID_KEYSTORE_PASSWORD`
- `VISHNU_ANDROID_KEY_PASSWORD`

The repository workflow **Our Products Android Runner** performs a real Gradle compile of an isolated development product job and verifies the resulting APK and digest on every relevant pull request.

## Runner configuration

Vishnu runtime:

```text
VISHNU_PRODUCT_SIGNING_PUBLIC_KEY_B64=<public key>
VISHNU_PRODUCT_SIGNING_PRIVATE_KEY_B64=<private key; server only>
VISHNU_PRODUCT_RUNNER_TOKEN=<long random secret>
VISHNU_PRODUCT_RUNNER_MAX_ARTIFACT_BYTES=536870912
```

Trusted runner:

```text
VISHNU_PRODUCT_SIGNING_PUBLIC_KEY_B64=<same pinned public key>
VISHNU_PRODUCT_RUNNER_TOKEN=<same runner token>
```

Android production runner additionally receives its Android keystore values listed above. Never put the runner token, private signing key, keystore passwords or keystore bytes in Git or a downloadable product.

## Current target status

- Web: verified local runtime bundle implemented.
- PWA: verified local runtime bundle implemented.
- API: verified local runtime bundle implemented.
- Worker: verified local runtime bundle implemented.
- Android: external build-job contract and real Gradle APK compiler implemented; production readiness requires configured release signing.
- iOS: build-job transport supported; compiler/signing adapter still pending.
- Windows: build-job transport supported; product-specific compiler/signing adapter still pending.
- macOS: build-job transport supported; product-specific compiler/notarization adapter still pending.
- Linux: build-job transport supported; product-specific package adapter still pending.
- Docker: build-job transport supported; OCI image builder/attestation adapter still pending.

The system must continue to fail closed for every pending platform. A target selection or build request is not evidence that a downloadable artifact exists.
