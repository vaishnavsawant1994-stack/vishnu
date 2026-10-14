# Dependency locks

Vishnu keeps human-maintained dependency ranges in `requirements.txt`, `requirements-ml.txt`, and `requirements-training.txt`. The generated lock files pin exact versions and include SHA-256 hashes for supported platforms. `requirements.lock` covers runtime dependencies; `requirements-ml.lock` and `requirements-training.lock` keep optional workloads separate. `requirements-tools.in` adds CI, packaging, and audit tools on top of runtime dependencies.

The lock generator is pinned by `requirements-bootstrap.in` and `requirements-bootstrap.lock` to `uv==0.12.23`. Regenerate a lock after intentionally editing its input with:

```sh
python -m pip install --require-hashes -r requirements-bootstrap.lock
uv pip compile --generate-hashes --universal --python-version 3.11 --no-header --quiet --output-file requirements.lock requirements.txt
```

Use the corresponding output and input names for tools, ML, and training locks. The repository verifier checks that every generated lock matches its source input, and CI runs it before tests.

Install a profile with `python scripts/install_locked_requirements.py runtime`, `tools`, `ml`, or `training`. The installer verifies the bootstrap and profile locks before installing with hash checking. Use `--check-all --check-only` to verify all lock files locally without changing the environment.

The root `package.json` and `package-lock.json` pin the Playwright browser-test dependencies. Browser workflows use `npm ci`; Playwright browser binaries are installed separately by the matching `npx playwright install` command.
