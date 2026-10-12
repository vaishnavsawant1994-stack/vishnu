from integrations.discovery.catalog_store import CapabilityCatalogStore

SAMPLE = """### Weather
| API | Description | Auth | HTTPS | CORS |
| --- | --- | --- | --- | --- |
| [Forecast](https://example.org/docs) | Forecast | apiKey | Yes | Yes |
"""


def test_persistent_catalog(tmp_path):
    path = tmp_path / "catalog.sqlite3"
    store = CapabilityCatalogStore(path)
    assert store.import_markdown(SAMPLE) == 1
    assert store.import_markdown(SAMPLE) == 1
    results = CapabilityCatalogStore(path).search("Forecast")
    assert len(results) == 1
    assert results[0]["executable"] is False
    assert results[0]["lifecycle"] == "discovered"


def test_search_validation(tmp_path):
    import pytest
    store = CapabilityCatalogStore(tmp_path / "catalog.sqlite3")
    with pytest.raises(ValueError):
        store.search(limit=101)
