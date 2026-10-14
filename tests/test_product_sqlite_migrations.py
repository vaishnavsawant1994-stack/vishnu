from __future__ import annotations

import pytest

from core.sqlite import MigrationError, connect_sqlite, run_script_migration, schema_version
from products.build_lifecycle import ProductBuildLifecycle
from products.capability_catalog import CapabilityCatalog
from products.composer import ProductComposer
from products.license_store import ProductLicenseStore
from products.runner_leases import ProductRunnerLeases
from products.store import ProductStore


def test_product_persistence_components_register_versioned_schemas(tmp_path):
    path = tmp_path / "products.sqlite3"

    def initialize():
        store = ProductStore(path)
        catalog = CapabilityCatalog(path)
        ProductComposer(path, catalog, store, None)
        ProductLicenseStore(path)
        lifecycle = ProductBuildLifecycle(path)
        ProductRunnerLeases(store, lifecycle)
        return store

    initialize()
    initialize()  # restart/retry must be idempotent

    expected = {
        "products.store",
        "products.capability_catalog",
        "products.composer",
        "products.license_store",
        "products.build_lifecycle",
        "products.runner_leases",
    }
    with connect_sqlite(path) as con:
        assert {row["component"] for row in con.execute(
            "SELECT component FROM vishnu_schema_versions"
        )} >= expected
        assert all(schema_version(con, component) == 1 for component in expected)


def test_legacy_product_tables_are_preserved_when_schema_version_is_recorded(tmp_path):
    path = tmp_path / "products.sqlite3"
    store = ProductStore(path)
    product = store.create(name="Legacy product", product_type="custom")
    with store.con() as con:
        con.execute(
            "DELETE FROM vishnu_schema_versions WHERE component='products.store'"
        )

    ProductStore(path)
    with connect_sqlite(path) as con:
        row = con.execute(
            "SELECT name FROM products WHERE id=?", (product["id"],)
        ).fetchone()
        assert row["name"] == "Legacy product"
        assert schema_version(con, "products.store") == 1


def test_script_migration_rolls_back_and_can_retry(tmp_path):
    path = tmp_path / "migration.sqlite3"
    with connect_sqlite(path) as con:
        with pytest.raises(MigrationError, match="migration 1"):
            run_script_migration(
                con,
                component="tests.script_migration",
                script=(
                    "CREATE TABLE should_rollback(id INTEGER PRIMARY KEY);\n"
                    "INSERT INTO missing_table VALUES(1);\n"
                ),
            )
        assert con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='should_rollback'"
        ).fetchone() is None
        assert schema_version(con, "tests.script_migration") == 0

        run_script_migration(
            con,
            component="tests.script_migration",
            script="CREATE TABLE retry_succeeds(id INTEGER PRIMARY KEY);\n",
        )
        assert schema_version(con, "tests.script_migration") == 1
