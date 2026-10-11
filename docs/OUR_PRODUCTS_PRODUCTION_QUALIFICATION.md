# Our Products production qualification

This document covers the final environment-owned qualification step for Android, iOS, Windows, macOS, Linux and Docker product artifacts.

The compilers and autonomous queue are part of Vishnu. Production credentials are not. Vishnu therefore keeps production authority fail-closed until a real runner host proves the required signing/provisioning/notarization/attestation evidence for a real frozen product build.

## Preflight

`packaging/product_production_preflight.py` emits a machine-readable, secret-redacted readiness document:

```text
python packaging/product_production_preflight.py --scope server --require-ready
python packaging/product_production_preflight.py --scope worker --target android --require-ready
python packaging/product_production_preflight.py --scope compiler --target macos --require-ready
```

The result schema is `vishnu.product-production-preflight/v1`. It reports only boolean/readiness details and never emits credential values.

Scopes:

- `server`: validates the Vishnu Product Ed25519 public/private key pair, runner bearer-token strength, artifact size limit and lease duration.
- `compiler`: validates the target host, required compiler/signing tools, pinned product public key and target production credentials.
- `worker`: includes all compiler checks plus the HTTPS runner URL, bearer token and stable runner ID needed for autonomous queue execution.

A preflight result is not release evidence. It proves only that the host appears correctly configured. Production authority still requires the real compiler to run and return verified target evidence.

## Governed GitHub environment workflow

The manual **Our Products Production Qualification** workflow is intentionally `workflow_dispatch` only. It never runs automatically on a pull request because production credentials belong to protected GitHub Environments, not ordinary CI.

For each target create a protected environment named:

```text
product-android-production
product-ios-production
product-windows-production
product-macos-production
product-linux-production
product-docker-production
```

Use environment protection/reviewer rules appropriate for the organization. The workflow has only `contents: read` repository permission.

Each environment needs the common secret `VISHNU_PRODUCT_SIGNING_PUBLIC_KEY_B64`, the common secret `VISHNU_PRODUCT_RUNNER_TOKEN`, and environment variable `VISHNU_PRODUCT_RUNNER_BASE_URL` pointing to the HTTPS Vishnu production server. The private Vishnu Product signing key stays on the server and is deliberately not supplied to compiler runners.

## Target environment secrets

Android:

```text
VISHNU_ANDROID_KEYSTORE_B64
VISHNU_ANDROID_KEY_ALIAS
VISHNU_ANDROID_KEYSTORE_PASSWORD
VISHNU_ANDROID_KEY_PASSWORD
```

The workflow decodes the protected keystore into the ephemeral runner directory and exposes only its temporary path to the compiler.

Windows:

```text
VISHNU_WINDOWS_SIGNING_CERT_B64
VISHNU_WINDOWS_SIGNING_PASSWORD
```

Windows uses the default RFC3161 timestamp service configured by the compiler and verifies the final executable with `signtool verify /pa /all`.

Docker:

```text
VISHNU_DOCKER_COSIGN_KEY_B64
COSIGN_PASSWORD
```

The workflow installs the pinned cosign CLI, materializes the key only in the ephemeral runner directory, and the compiler verifies the exact `image.tar` signature before production readiness can become true.

macOS:

```text
VISHNU_APPLE_SIGNING_IDENTITY
VISHNU_APPLE_SIGNING_CERT_P12_B64
VISHNU_APPLE_SIGNING_CERT_PASSWORD
VISHNU_APPLE_NOTARY_APPLE_ID
VISHNU_APPLE_NOTARY_TEAM_ID
VISHNU_APPLE_NOTARY_APP_PASSWORD
```

The workflow creates a temporary keychain, imports the certificate, verifies that the requested signing identity exists, creates a temporary `notarytool` credential profile, and then runs the production worker. The compiler still independently requires successful `codesign`, notarization, stapling and staple validation.

iOS:

```text
VISHNU_APPLE_SIGNING_IDENTITY
VISHNU_APPLE_SIGNING_CERT_P12_B64
VISHNU_APPLE_SIGNING_CERT_PASSWORD
VISHNU_IOS_PROVISIONING_PROFILE_B64
```

The workflow creates the temporary signing keychain and materializes the provisioning profile. The compiler decodes the profile itself and verifies that its application identifier authorizes the actual queued product bundle ID before signing the IPA.

Linux has no target signing secret in the current contract. It still requires the common pinned product public key, runner bearer token and HTTPS production server because the production artifact must come from a signed frozen Vishnu product job claimed through the governed queue.

## Running a real qualification

1. In the Vishnu owner workspace, freeze the product version that is intended for release.
2. Request the target build. The build must be `requested` or `queued`; do not manually manufacture an artifact.
3. Open **Our Products Production Qualification** in GitHub Actions.
4. Select the target.
5. First run with `execute=false`. This validates the protected environment, runner host and credential/tool readiness without claiming product work.
6. Resolve every failed preflight check. Do not bypass it.
7. Run again with `execute=true`.
8. The worker claims exactly one real queued build, keeps the lease alive, compiles it, returns the complete target evidence, and asks Vishnu to register the artifact.
9. The workflow fails if no real build is queued, if compilation fails, or if Vishnu does not report `distribution_ready=true`.
10. Preserve the uploaded non-secret preflight/result evidence and the matching Vishnu build record for the release audit.

The workflow cannot make a development artifact production-ready. The final assertion is against Vishnu's accepted build state after the authenticated, lease-bound callback.

## Target evidence required

- Android: compiler verification + release APK signing verification.
- iOS: compiler verification + code signing + matching provisioning profile.
- Windows: compiler verification + Authenticode verification.
- macOS: compiler verification + code signing + Apple notarization/stapling verification.
- Linux: compiler verification of the generated DEB.
- Docker: compiler verification + verified cosign attestation of the exact saved image archive.

Any missing requirement keeps the artifact non-downloadable as a production artifact.

## Secret-handling rules

- Never put production credentials in product manifests, build-job ZIPs, workflow artifacts, PR bodies or test fixtures.
- Never install `VISHNU_PRODUCT_SIGNING_PRIVATE_KEY_B64` on a normal compiler runner.
- Use protected GitHub Environment secrets or an equivalent runner-side secret store.
- The workflow uploads only preflight JSON, final non-secret result JSON and worker logs. GitHub secret masking remains a secondary defense; runner/compiler code is still written not to print raw secrets.
- Rotate the global runner bearer token if a runner installation is decommissioned or suspected compromised.
- Use a unique `VISHNU_PRODUCT_RUNNER_ID` per long-lived production runner so lease/evidence history remains attributable.

Issue #160 remains open until the real production environments have completed their target qualifications. Compiler implementation and development CI qualification are necessary but are not substitutes for these environment-owned release proofs.
