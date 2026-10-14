# SBOM evidence

The `SBOM Evidence` workflow generates CycloneDX JSON for the locked Python runtime, optional ML and training profiles, and the Node browser qualification dependencies. It runs for pull requests, pushes to `main`, version tags, and manual dispatches.

Each run uploads the SBOMs with a manifest containing the checked-out source SHA, workflow reference and run identity, generator versions, SHA-256 identities for every lock input, SHA-256 checksums for each SBOM, and any vulnerability findings reported while generating Python CycloneDX output. Findings remain visible in the SBOM and manifest; the repository's security workflows remain the enforcement gates.

Version-tag runs preserve this evidence as a 90-day workflow artifact named with the source SHA. To generate locally, install locked tools and Node dependencies, then run:

```sh
python scripts/install_locked_requirements.py tools
npm ci --ignore-scripts
python scripts/generate_sbom.py --output-dir dist/sbom
```
