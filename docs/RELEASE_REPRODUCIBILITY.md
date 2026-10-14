# Release reproducibility evidence

The signed installer manifest binds packages to an exact source SHA and records package checksums, dependency lock identities, CycloneDX SBOM file hashes, build workflow/run identity, and successful qualification results.

Package Validation produces this evidence from Windows, macOS, and Linux installer artifacts and preserves it as a 90-day workflow artifact. Signed Release creates the same evidence after its platform build jobs and includes it inside the existing signed installer manifest. Pull-request qualification uses no release signing keys and publishes no production release.

Evidence generation fails if a dependency lock or SBOM is missing, an installer checksum is invalid, or any recorded qualification result is not successful.
