from __future__ import annotations

import pytest

from integrations.discovery import parse_public_apis, parse_public_apis_category


SAMPLE = """### Weather
| API | Description | Auth | HTTPS | CORS |
| --- | --- | --- | --- | --- |
| [Forecast](https://example.org/docs) | Weather forecasts | apiKey | Yes | Yes |
| [Forecast](https://example.org/docs) | Weather forecasts | apiKey | Yes | Yes |
| [Insecure](http://example.org/api) | Ignored | No | No | No |
### Finance
| API | Description | Auth | HTTPS | CORS |
| --- | --- | --- | --- | --- |
| [Exchange](https://finance.example.org/) | Currency data | No | Yes | Unknown |
"""


def test_import_is_deterministic_and_deduplicated():
    first = parse_public_apis(SAMPLE)
    assert first == parse_public_apis(SAMPLE)
    assert len(first) == 2
    assert [x["category"] for x in first] == ["Weather", "Finance"]
    assert all(x["lifecycle"] == "discovered" and x["executable"] is False for x in first)
    assert all(x["id"].startswith("public_apis:") for x in first)


def test_metadata_fields_are_preserved():
    entries = parse_public_apis_category(SAMPLE)
    assert entries[0].auth == "apiKey"
    assert entries[0].https is True
    assert entries[1].cors == "Unknown"


def test_catalog_bounds():
    with pytest.raises(ValueError):
        parse_public_apis(SAMPLE, max_entries=0)
    with pytest.raises(ValueError):
        parse_public_apis("x" * 5_000_001)
    assert len(parse_public_apis(SAMPLE, max_entries=1)) == 1


def test_malformed_or_unsafe_urls_are_not_imported():
    text = """### Security
| API | Description | Auth | HTTPS | CORS |
| --- | --- | --- | --- | --- |
| [Bad](https://user:pass@example.org/) | No | No | Yes | No |
| [Valid](https://example.org/) | Yes | No | Yes | No |
"""
    assert [x["name"] for x in parse_public_apis(text)] == ["Valid"]
