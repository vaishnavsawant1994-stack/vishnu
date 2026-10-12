from integrations.discovery.import_catalog import main
from integrations.discovery.catalog_store import CapabilityCatalogStore


def test_offline_catalog_cli(tmp_path, capsys):
    snapshot = tmp_path / "README.md"
    snapshot.write_text("""### Weather
| API | Description | Auth | HTTPS | CORS |
| --- | --- | --- | --- | --- |
| [Forecast](https://example.org/docs) | Weather | No | Yes | Yes |
""", encoding="utf-8")
    db = tmp_path / "catalog.sqlite3"
    assert main([str(snapshot), "--db", str(db)]) == 0
    assert "Imported 1 inert catalog entries" in capsys.readouterr().out
    assert CapabilityCatalogStore(db).search()[0]["executable"] is False
