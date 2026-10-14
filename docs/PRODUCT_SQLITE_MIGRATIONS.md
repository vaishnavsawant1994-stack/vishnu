# Product persistence SQLite migrations

ProductStore, ProductComposer, CapabilityCatalog, ProductLicenseStore,
ProductBuildLifecycle, and ProductRunnerLeases share the configured product
SQLite database and the common connection/migration foundation in
`core.sqlite`.

Each component has an independent, versioned schema entry. Existing tables are
kept intact: the initial migration uses idempotent `CREATE ... IF NOT EXISTS`
statements before registering the component version. SQL statements run inside
the migration transaction individually; schema creation does not use
`Connection.executescript`, whose implicit commit can defeat rollback.

Run the focused checks with:

```sh
pytest -q tests/test_product_sqlite_migrations.py tests/test_products_platform.py
```
