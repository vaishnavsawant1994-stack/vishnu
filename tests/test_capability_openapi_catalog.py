from integrations.discovery.catalog_store import CapabilityCatalogStore


def test_openapi_import_and_detail(tmp_path):
    store = CapabilityCatalogStore(tmp_path / "catalog.sqlite3")
    document = {"openapi": "3.1.0", "paths": {"/weather": {"get": {"summary": "Read forecast"}, "post": {"summary": "Update forecast"}}}}
    assert store.import_openapi(document) == 2
    assert store.import_openapi(document) == 2
    items = store.search("forecast")
    assert len(items) == 2
    assert all(item["executable"] is False for item in items)
    assert {item["risk"] for item in items} == {"read", "write"}
    assert store.get(items[0]["id"]) == items[0]
    assert store.get("missing") is None
