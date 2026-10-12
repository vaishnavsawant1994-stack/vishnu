import pytest
from integrations.discovery.openapi import parse_openapi


def test_openapi_operations_remain_inert():
    document = {"openapi": "3.0.3", "paths": {"/users": {"get": {"summary": "List users"}, "post": {"operationId": "createUser"}}}}
    entries = parse_openapi(document)
    assert len(entries) == 2
    assert [item["risk"] for item in entries] == ["read", "write"]
    assert all(item["lifecycle"] == "discovered" and item["executable"] is False for item in entries)
    assert entries == parse_openapi(document)


def test_invalid_openapi_rejected():
    with pytest.raises(ValueError):
        parse_openapi({"openapi": "2.0", "paths": {}})
    with pytest.raises(ValueError):
        parse_openapi({"openapi": "3.1.0", "paths": []})
