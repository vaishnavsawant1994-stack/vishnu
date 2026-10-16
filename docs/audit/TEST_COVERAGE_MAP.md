# Test and qualification coverage map

**Baseline SHA:** `a8d3310b4d9090a42800621b1b27cb6045443c1e`.

The repository contains 647 Python `tests/test_*.py` files, 684 total test files, platform-specific Android/iOS tests, browser qualification scripts, and 35 GitHub workflows. These are inventory counts, not test results. At the audited exact `main` SHA, GitHub reported successful `test`, `assurance`, `release-authority`, `local-first-security-and-recovery`, `voice-lab`, `qualification-evidence`, and `sbom` checks. A clean local full-suite rerun passed all 3,840 tests after unsetting the container's injected SOCKS proxy. Exact CI check results apply to `a8d3310b4d9090a42800621b1b27cb6045443c1e`, not the final audit documentation PR.

## Current source-defined CI gates

- `.github/workflows/ci.yml`: locked dependencies, pip/npm checks, targeted Ruff/mypy, compileall, product composer/build/distribution tests, Intelligence governance, evolution, Visualize, canonical Work, recovery, endurance/concurrency, architecture conformance, release, content-intelligence and the full `pytest -q` suite.
- `reliability.yml`: security/audit checks, Sensorium/device boundaries, product distribution security, P7–P10 focused adversarial/E2E/performance/recovery suites, scheduled soak, encrypted backup/restore.
- `cybersecurity-assurance.yml`: exact candidate SHA assurance artifact.
- Additional workflows cover Android emulator/instrumentation, iOS simulator/physical handoff/TestFlight, PWA mobile preview and responsive UI, native device lab, data plane, Intelligence Lab, voice lab, packaging, release authority, SBOM, reproducibility, production trust continuity, product runners and qualification evidence.

## Feature-to-evidence summary

| Area | Evidence present | What it does not prove |
|---|---|---|
| SQLite/migrations, identity/recovery, vault rotation | Unit/integration, concurrency and fault-injection tests | Running production DB path or an accepted production restore |
| OpenAPI/MCP/capabilities | Security fixtures for HTTPS/host pinning, redirects, response bounds, invalid parameters, approvals, rotation, rehydration | Arbitrary live provider compatibility or consent |
| Data plane/storage fabric | Placement, resumable transfer/reconciliation and encryption tests | Live S3-compatible account configuration or production backup acceptance |
| Android/iOS | Build, instrumentation/simulator and native-lab workflows | Real physical device behavior, store acceptance or signing |
| PWA | Browser scripts and responsive/mobile preview workflow | Every browser/viewport/control, external provider, or production acceptance |
| Voice/Sensorium | Provider/runtime isolation, benchmark/fixture, emulator/simulator/VM evidence | Real acoustic performance, provider account behavior or physical sensors |
| Work/products/evolution | Domain, security, lifecycle, recovery and performance suites | Production worker or release action without exact approval/configuration |

## Execution result

Initial direct `pytest -q` attempt failed with shell status 127 (`pytest: command not found`). The repository installer with `--system` was denied while replacing a shared runtime package; a local virtual environment was created and populated from the locked `requirements-tools.lock`. The first full run had 3,837 passes and three identical provider-adapter failures caused by the container's `ALL_PROXY=socks5h://...` setting without `socksio`. Those 12 provider contract tests passed with `ALL_PROXY`/`all_proxy` unset. A second full run with those variables unset completed **3,840 passed, 73 warnings in 115.48 seconds**. This is local test evidence on the unchanged product baseline plus audit-only docs/scripts; production and real-provider behavior are not implied.
