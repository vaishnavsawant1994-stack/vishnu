# Our Products platform runner

## Purpose

The platform runner is the governed compilation boundary for product targets that should not be compiled inside the Vishnu web process. It supports Android, iOS, Windows, macOS, Linux and Docker/OCI build jobs while keeping product compilation separate from the owner application runtime.

The owner runtime creates a build request first. A platform build job can be produced only from the immutable frozen product version referenced by that build. The job contains a sanitized product manifest, target/build identity, requested artifact kinds and explicit isolation constraints. It never exports owner conversations, memory, unrelated products, the complete Vishnu source tree or owner-side credential references.

## Trust boundaries

Production build jobs are signed with the dedicated Vishnu Product Ed25519 signing key. A trusted compiler validates that signature and can pin `VISHNU_PRODUCT_SIGNING_PUBLIC_KEY_B64` so a valid signature from an unexpected key is rejected.

A separate `VISHNU_PRODUCT_RUNNER_TOKEN` authenticates external compiler installations. This bearer token is builder authority and belongs only in the Vishnu deployment secret store and the trusted runner secret store.

The owner browser cannot directly manufacture artifact filename, URI, checksum, compiler status, signing status, provisioning status or notarization status. Distribution authority is registered only through the verified local builder or authenticated platform-runner path.

## Autonomous queue and leases

Production runners no longer need an operator to hand them a build ID. The canonical cloud app exposes an autonomous claim surface under `/iphone/api/products/runner`.

A runner calls:

- `POST /iphone/api/products/runner/claim?target=android|ios|windows|macos|linux|docker`
- bearer authorization with `VISHNU_PRODUCT_RUNNER_TOKEN`
- `X-Vishnu-Runner-ID` identifying the runner installation

Only frozen requested/queued builds are claimable. A successful claim atomically reserves one build, moves it into `running`, and returns the signed build-job bytes plus a random per-build lease token in `X-Vishnu-Runner-Lease`.

Lease properties:

- only SHA-256 of the lease token is persisted
- default duration is 900 seconds and is configurable with `VISHNU_PRODUCT_RUNNER_LEASE_SECONDS`
- `POST /iphone/api/products/runner/{build_id}/heartbeat` renews the active lease
- `POST /iphone/api/products/runner/{build_id}/release` safely fails/requeues a running build when a runner cannot finish
- `POST /iphone/api/products/runner/{build_id}/complete` closes the lease only after the build reaches a terminal state
- expired leases are recovered durably; a still-running build is recorded failed with an expiry reason and then returned to `queued`
- a recovered build increments its runner attempt when claimed again
- aggregate queue/lease status never returns lease tokens or token hashes

The global bearer token authenticates the runner installation; the per-build lease is a concurrency/recovery credential. Lease handling prevents two healthy runners from compiling the same queued build at the same time.

## Artifact callback authority

The authenticated platform runner uploads raw artifact bytes together with target evidence. Vishnu verifies the artifact filename, byte limit, SHA-256, destination containment and evidence identity before writing distribution authority.

`vishnu.platform-runner-evidence/v1` is bound to:

- product ID
- build ID
- frozen product version
- target
- artifact filename
- artifact SHA-256
- compiler verification
- target-specific signing/provisioning/notarization metadata

Callback retry is idempotent: if a runner loses the HTTP response and replays the exact same terminal artifact, Vishnu returns the existing succeeded build. A different filename, digest, identity or payload can never replace an already-succeeded artifact.

## Production-readiness rules

A target selection, queue claim or successful compiler invocation is not by itself distribution authority.

- Android requires production mode, verified compilation and verified APK signing.
- iOS requires production mode, verified compilation, verified signing and verified provisioning/export evidence.
- Windows requires production mode, verified compilation and verified Authenticode signing.
- macOS requires production mode, verified compilation, verified code signing and verified notarization.
- Linux requires production mode and verified package compilation.
- Docker/OCI requires production mode, verified image compilation and verified attestation metadata.

Development/debug artifacts are useful qualification evidence but remain non-downloadable from the production artifact endpoint.

## Android compiler adapter

`packaging/product_platform_runner.py` implements the Android adapter. It generates a clean Android application project from the build job instead of copying `android-companion` or Vishnu itself.

The generated application contains only the sanitized frozen product manifest, a product-specific application ID, a bounded product UI shell and declared product/component information. Owner state and credentials are excluded.

Without all dedicated Android signing secrets the adapter builds a debug APK and reports `signing_verified=false`. With all four values configured it builds release, verifies the result with `apksigner`, and may provide production-ready evidence:

- `VISHNU_ANDROID_KEYSTORE_PATH`
- `VISHNU_ANDROID_KEY_ALIAS`
- `VISHNU_ANDROID_KEYSTORE_PASSWORD`
- `VISHNU_ANDROID_KEY_PASSWORD`

The **Our Products Android Runner** workflow performs a real Gradle compilation and APK verification on relevant pull requests.

## Linux compiler adapter

`packaging/product_desktop_container_runner.py` implements the Linux product compiler on a Linux runner.

It generates a bounded standalone client runtime from the frozen sanitized manifest, compiles that runtime into a one-file executable with PyInstaller, and packages it as an installable Debian `.deb`. The package installs only the client product executable and launcher under the Vishnu Products namespace; it does not package the owner repository.

The **Our Products Linux and Docker Runners** workflow performs a real PyInstaller build, DEB compilation, `dpkg-deb --info` verification and package extraction check.

## Windows compiler adapter

The same desktop/container runner builds a Windows one-file `.exe` on Windows. If no dedicated client-product certificate is present, the development artifact remains unsigned and therefore non-production.

Production Authenticode configuration is intentionally separate from Vishnu application-release signing:

- `VISHNU_WINDOWS_SIGNING_CERT_PATH` or `VISHNU_WINDOWS_SIGNING_CERT_B64`
- `VISHNU_WINDOWS_SIGNING_PASSWORD`
- optional `VISHNU_WINDOWS_TIMESTAMP_URL`

When configured, the runner calls `signtool sign` with SHA-256 and an RFC3161 timestamp and then calls `signtool verify /pa /all`. Only a verified result may set Windows product signing evidence.

The **Our Products Windows Runner** workflow performs a real PyInstaller EXE compilation and digest/evidence validation on `windows-latest`.

## Docker / OCI compiler adapter

The Docker adapter generates a minimal product-specific container context from the sanitized frozen manifest. The image exposes `/health` and `/product`; product execution itself remains behind the separately approved runtime-connector boundary.

The runner performs a real `docker build`, captures the resulting image ID, saves the exact image to `image.tar`, records its SHA-256 and wraps the image archive with manifest/evidence files in an OCI delivery ZIP.

Production Docker distribution additionally requires a verified attestation. When `VISHNU_DOCKER_COSIGN_KEY` is configured the runner uses `cosign sign-blob` against the exact `image.tar`, derives the corresponding public key and verifies the signature before reporting `attestation_verified=true`. `COSIGN_PASSWORD` is supplied through the protected runner environment when the key requires it.

Without verified attestation, even a successful production Docker build remains fail-closed from product download authority.

## Runner configuration

Vishnu runtime:

```text
VISHNU_PRODUCT_SIGNING_PUBLIC_KEY_B64=<public key>
VISHNU_PRODUCT_SIGNING_PRIVATE_KEY_B64=<private key; server only>
VISHNU_PRODUCT_RUNNER_TOKEN=<long random secret>
VISHNU_PRODUCT_RUNNER_MAX_ARTIFACT_BYTES=536870912
VISHNU_PRODUCT_RUNNER_LEASE_SECONDS=900
```

Every trusted runner receives the pinned product public key and runner bearer token. Target-specific signing keys/certificates belong only on runners that are authorized to produce that platform's production artifact.

Never place runner tokens, private product-signing keys, Android keystores, Windows PFX certificates/passwords, Apple signing material or cosign private keys in Git or inside downloadable product manifests.

## Current target status

- Web: verified local runtime bundle implemented and qualified.
- PWA: verified local runtime bundle implemented and qualified.
- API: verified local runtime bundle implemented and qualified.
- Worker: verified local runtime bundle implemented and qualified.
- Android: real Gradle APK compiler implemented and qualified in development; production readiness requires deployment-owned release-signing qualification.
- Linux: real PyInstaller + DEB compiler implemented in this tranche and independently qualified by its target workflow before merge.
- Windows: real PyInstaller EXE compiler implemented in this tranche and independently qualified by its target workflow before merge; production requires Authenticode verification.
- Docker: real image/OCI archive compiler implemented in this tranche and independently qualified by its target workflow before merge; production requires verified attestation.
- macOS: build-job/evidence transport exists; product-specific signed/notarized compiler remains pending.
- iOS: build-job/evidence transport exists; Xcode archive/export and provisioning verification remain pending.

Issue #160 stays open until the remaining macOS/iOS compiler work, deployment-owned production signing/attestation qualification, and final end-to-end runner operations are complete.