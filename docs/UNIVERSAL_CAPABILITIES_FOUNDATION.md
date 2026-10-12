# Universal capabilities: first implementation tranche

This branch introduces an inert, deterministic parser for the public-apis Markdown catalog.

## Authority boundaries

- Public catalog entries are **discovery metadata**, not registered connector manifests, trusted tools, installed plugins, or grants.
- The importer does not access the network, execute arbitrary code, inspect credentials, or modify the existing integration registry.
- Existing `integrations.registry`, `integrations.gateway`, `core.permissions`, approval continuation, and OAuth remain the execution authorities.
- A discovered entry must pass a separate provider-specific qualification and owner grant before any runtime integration.

## Next work

1. Add versioned, additive persistence and source snapshot provenance.
2. Implement a bounded offline catalog refresh worker with explicit network controls.
3. Add owner-authenticated, read-only search endpoints and UI projection.
4. Add OpenAPI/MCP normalization, risk review, credential management, and governed execution only in subsequent qualified tranches.

Run: `pytest -q tests/test_capability_discovery_public_apis.py`.
