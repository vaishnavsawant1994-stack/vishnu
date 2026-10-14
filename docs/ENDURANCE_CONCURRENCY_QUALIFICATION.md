# Endurance and concurrency qualification

This focused suite repeatedly writes through the shared SQLite connection and transaction helpers, runs concurrent MemoryStore creates/usage tracking/search, reopens the encrypted store, and overlaps SecretVault reads with a staged root-key rotation. It checks that all writes remain present, SQLite integrity is intact, protected memory text is absent from database/WAL bytes, and the vault is readable after restart.

The approval single-use race now starts sixteen concurrent contenders against one approval. Exactly one dispatch may succeed; the rest must fail with PermissionError and the governed side effect must execute once.

Run the focused qualification with:

```sh
pytest -q tests/test_endurance_concurrency.py tests/test_p6_approval_security.py::test_concurrent_approval_race_consumes_existing_ticket_at_most_once
```
