# Dependency license compliance

The SBOM Evidence workflow runs a license policy report for the locked Python runtime, build tools, optional ML/training profiles, and npm browser dependencies. Python runtime/tool license metadata comes from installed distribution metadata; optional profiles that are not installed are explicitly marked for review. npm metadata comes from the lock-derived CycloneDX document.

The policy is in `config/license-policy.json`. Only exact SPDX identifiers in `deny_spdx_ids` fail the workflow. `allow_spdx_ids` are accepted by repository policy; all missing, custom, or unlisted licenses are reported for human/legal review and do not fail CI. Reports include package version, profile, direct/transitive status, license source, policy result, and a redistribution/notice follow-up.

Run locally after generating SBOMs:

```sh
python scripts/license_compliance.py --sbom-dir dist/sbom --output dist/sbom/license-report.json
```
