# Our Products platform runner

## Purpose

The platform runner is the governed compilation boundary for product targets that should not be compiled inside the Vishnu web process. It supports Android, iOS, Windows, macOS, Linux and Docker/OCI build jobs while keeping product compilation separate from the owner application runtime.

The owner runtime creates a build request first. A platform build job can be produced only from the immutable frozen product version referenced by that build. The job contains a sanitized product manifest, target/build identity, requested artifact kinds and explicit isolation constraints. It never exports owner conversations, memory, unrelated products, the complete Vishnu source tree or owner-side credential references.

## Trust boundaries

Production build jobs are signed with the dedicated Vishnu Product Ed25519 signing key. A trusted compiler validates that signature and can pin `VISHNU_PRODUCT_SIGNING_PUBLIC_KEY_B64` so a valid signature from an unexpected key is rejected.

A separate `VISHNU_PRODUCT_RUNNER_TOKEN` authenticates external compiler installations. This bearer token is builder authority and belongs only in the Vishnu deployment secret store and the trusted runner secret store.

The owner browser cannot directly manufacture artifact filename, URI, checksum, compiler status, signing status, provisioning status, notarization status or image-attestation status. Distribution authority is registered only through the verified local builder or authenticated platform-runner path.

## Autonomous queue and leases

Production runners do not need an operator to hand them a build ID. The canonical cloud app exposes an autonomous claim surface under `/iphone/api/products/runner`.

A runner calls:

- `POST /iphone/api/products/runner/claim?target=android|ios|windows|macos|linux|docker`
- bearer authorization with `VISHNU_PRODUCT_RUNNER_TOKEN`
- `X-Vishnu-Runner-ID` identifying the runner installation

Only frozen requested/queued builds are claimable. A successful claim reserves one build, moves it into `running`, and returns the signed build-job bytes plus a random per-build lease token in `X-Vishnu-Runner-Lease`.

Claim selection and lease creation run inside a SQLite `BEGIN IMMEDIATE` transaction. This is deliberate: the Python lock protects one process, while the database transaction prevents two independent Vishnu API processes from claiming the same build concurrently.

Lease properties:

- only SHA-256 of the lease token is persisted
- default duration is 900 seconds and is configurable with `VISHNU_PRODUCT_RUNNER_LEASE_SECONDS`
- `POST /iphone/api/products/runner/{build_id}/heartbeat` renews the active lease
- `POST /iphone/api/products/runner/{build_id}/release` safely fails/requeues a running build when a runner cannot finish
- `POST /iphone/api/products/runner/{build_id}/complete` closes the lease only after the build reaches a terminal state
- expired leases are recovered durably; a still-running build is recorded failed with an expiry reason and then returned to `queued`
- a recovered build increments its runner attempt when claimed again
- aggregate queue/lease status never returns lease tokens or token hashes

The global bearer token authenticates the runner installation; the per-build lease is a concurrency/recovery credential. Both are required by the autonomous callback flow.

## Autonomous runner worker

`packaging/product_runner_worker.py` is the reusable worker process for an installed build host. It:

1. claims the next build for one target;
2. verifies the build-job SHA-256 returned by Vishnu;
3. keeps the lease alive with heartbeats while compilation runs;
4. dispatches to the target-specific compiler;
5. verifies the compiler's artifact/evidence digest agreement;
6. uploads the artifact together with the complete runner-evidence document and lease;
7. completes the lease only after Vishnu accepts the terminal build; and
8. reports a bounded failure reason if compilation or callback fails.

The worker accepts only HTTPS Vishnu URLs except for localhost development. Artifact callback retries reopen the artifact from disk for every attempt so a transient HTTP failure cannot cause an exhausted file stream to be replayed as an empty upload.

Example installation command:

```text
python packaging/product_runner_worker.py --target linux
```

Required/shared environment:

```text
VISHNU_PRODUCT_RUNNER_BASE_URL=https://vishnu.example.com
VISHNU_PRODUCT_RUNNER_TOKEN=<long random secret>
VISHNU_PRODUCT_RUNNER_ID=linux-builder-01
VISHNU_PRODUCT_RUNNER_HEARTBEAT_SECONDS=60
VISHNU_PRODUCT_RUNNER_POLL_SECONDS=30
VISHNU_PRODUCT_SIGNING_PUBLIC_KEY_B64=<pinned product signing public key>
```

The Vishnu server additionally owns `VISHNU_PRODUCT_SIGNING_PRIVATE_KEY_B64`. That private key must never be installed on an ordinary compiler runner.

## Artifact callback authority

The authenticated autonomous runner upload is bound to both the global bearer credential and the active per-build lease. It must supply `X-Vishnu-Runner-Evidence` containing the full `vishnu.platform-runner-evidence/v1` document.

Vishnu bounds the upload while streaming request chunks, so a missing or inaccurate `Content-Length` cannot bypass `VISHNU_PRODUCT_RUNNER_MAX_ARTIFACT_BYTES`. It then verifies artifact filename, SHA-256, destination containment and evidence identity before writing distribution authority.

`vishnu.platform-runner-evidence/v1` is bound to:

- product ID
- build ID
- frozen product version
- target
- artifact filename
- artifact SHA-256
- compiler verification
- target-specific signing/provisioning/notarization/attestation metadata

Callback retry is idempotent: if a runner loses the HTTP response and replays the exact same terminal artifact, Vishnu returns the existing succeeded build. A different filename, digest, identity or payload can never replace an already-succeeded artifact.

## Owner-facing readiness

The trusted owner workspace can read `GET /iphone/api/products/{product_id}/runner-readiness`. This endpoint deliberately returns only safe operational state: builder type, configured/not-configured runner state, production requirements and latest build evidence. It never returns the runner bearer token, lease token or persisted lease hash.

The **Build & Export** tab uses this data to distinguish states such as compiler implemented, runner not configured, waiting, running, failed and production artifact ready. Target selection by itself is never presented as proof that a downloadable binary exists.

## Production-readiness rules

A target selection, queue claim or successful compiler invocation is not by itself distribution authority.

- Android requires production mode, verified compilation and verified APK signing.
- iOS requires production mode, verified compilation, verified code signing and a matching verified provisioning profile.
- Windows requires production mode, verified compilation and verified Authenticode signing.
- macOS requires production mode, verified compilation, verified code signing and verified notarization/stapling.
- Linux requires production mode and verified package compilation.
- Docker/OCI requires production mode, verified image compilation and verified attestation metadata.

Development/debug/simulator artifacts are useful compiler qualification evidence but remain non-production.

## Android compiler adapter

`packaging/product_platform_runner.py` implements the Android adapter. It generates a clean Android application project from the build job instead of copying `android-companion` or Vishnu itself.

The generated application contains only the sanitized frozen product manifest, a product-specific application ID, a bounded product UI shell and declared product/component information. Owner state and credentials are excluded.

Without all dedicated Android signing secrets the adapter builds a debug APK and reports `signing_verified=false`. With all four values configured it builds release, verifies the result with `apksigner`, and may provide production-ready evidence:

- `VISHNU_ANDROID_KEYSTORE_PATH`
- `VISHNU_ANDROID_KEY_ALIAS`
- `VISHNU_ANDROID_KEYSTORE_PASSWORD`
- `VISHNU_ANDROID_KEY_PASSWORD`

The **Our Products Android Runner** workflow performs a real Gradle compilation and APK verification.

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

## macOS compiler adapter

`packaging/product_apple_runner.py` implements the native macOS client-product compiler. On a macOS/Xcode host it compiles a product-specific AppKit application with `xcrun swiftc`, writes a bounded app bundle, and creates a DMG with `hdiutil`.

Development qualification may create an unsigned DMG, but production mode fails closed unless both of the following succeed:

- `VISHNU_MACOS_SIGNING_IDENTITY` -> `codesign` signing and strict verification
- `VISHNU_MACOS_NOTARY_KEYCHAIN_PROFILE` -> `notarytool submit --wait`, `stapler staple`, and `stapler validate`

Only then can macOS evidence report both `signing_verified=true` and `notarization_verified=true`.

## iOS compiler adapter

The Apple runner also implements iOS. Development qualification builds a real UIKit simulator application against the installed Xcode simulator SDK and emits an app ZIP. That simulator artifact is compiler evidence only and cannot become production distribution authority.

Production iOS builds target `iphoneos`/arm64 and require both:

- `VISHNU_IOS_SIGNING_IDENTITY`
- `VISHNU_IOS_PROVISIONING_PROFILE`

The provisioning profile is decoded with `security cms`; its `application-identifier` must authorize the generated product bundle ID. The runner embeds the profile, signs with the profile entitlements, verifies the app with `codesign`, and emits an IPA. Production mode fails closed if any of those checks fail.

The **Our Products Apple Runners** workflow independently compiles and verifies the development macOS DMG and iOS simulator application. It intentionally does not claim production Apple signing/notarization qualification because CI does not own client production credentials.

## Runner configuration summary

Vishnu server:

```text
VISHNU_PRODUCT_SIGNING_PUBLIC_KEY_B64=<public key>
VISHNU_PRODUCT_SIGNING_PRIVATE_KEY_B64=<private key; server only>
VISHNU_PRODUCT_RUNNER_TOKEN=<long random secret>
VISHNU_PRODUCT_RUNNER_MAX_ARTIFACT_BYTES=536870912
VISHNU_PRODUCT_RUNNER_LEASE_SECONDS=900
```

Runner worker:

```text
VISHNU_PRODUCT_RUNNER_BASE_URL=https://vishnu.example.com
VISHNU_PRODUCT_RUNNER_TOKEN=<same protected runner bearer secret>
VISHNU_PRODUCT_RUNNER_ID=<stable installation ID>
VISHNU_PRODUCT_RUNNER_HEARTBEAT_SECONDS=60
VISHNU_PRODUCT_RUNNER_POLL_SECONDS=30
VISHNU_PRODUCT_SIGNING_PUBLIC_KEY_B64=<public key only>
```

Target-specific production credentials belong only on runners authorized for that client/platform. Never place runner tokens, private product-signing keys, Android keystores, Windows PFX certificates/passwords, Apple signing material or cosign private keys in Git or inside downloadable product manifests.

## Current target status

- Web: verified local runtime bundle implemented and qualified.
- PWA: verified local runtime bundle implemented and qualified.
- API: verified local runtime bundle implemented and qualified.
- Worker: verified local runtime bundle implemented and qualified.
- Android: real Gradle APK compiler implemented; development qualification is covered by the Android workflow; production readiness still requires deployment-owned client release signing evidence.
- Linux: real PyInstaller + DEB compiler implemented; target workflow provides real development compilation evidence.
- Windows: real PyInstaller EXE compiler implemented; target workflow provides real development compilation evidence; production requires deployment-owned Authenticode verification.
- Docker: real image/OCI archive compiler implemented; target workflow provides real development compilation evidence; production requires deployment-owned verified attestation.
- macOS: real AppKit + DMG compiler implemented; Apple workflow provides real development compilation evidence; production requires deployment-owned code signing and notarization evidence.
- iOS: real UIKit simulator and device/IPA paths implemented; Apple workflow provides real simulator compilation evidence; production requires deployment-owned matching provisioning and code-signing evidence.

Issue #160 remains open through exact-head qualification and deployment-owned production credential/evidence qualification. Development CI success must not be used as a substitute for real client release signing, provisioning, notarization or attestation.