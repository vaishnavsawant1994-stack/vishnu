import pytest
from integrations.discovery.mcp import normalize_mcp_server


def test_mcp_discovery_is_inert():
    result = normalize_mcp_server({"name": "Example", "url": "https://mcp.example.org/mcp"})
    assert result["transport"] == "streamable-http"
    assert result["executable"] is False
    assert result["requires_owner_approval"] is True


@pytest.mark.parametrize("descriptor", [
    {"name": "Bad", "url": "http://example.org/mcp"},
    {"name": "Bad", "url": "https://user:pass@example.org/mcp"},
    {"name": "Bad", "url": "https://example.org/mcp", "command": "python"},
    {"name": "Bad", "url": "https://example.org/mcp", "token": "secret"},
])
def test_mcp_discovery_rejects_unsafe_metadata(descriptor):
    with pytest.raises(ValueError):
        normalize_mcp_server(descriptor)
