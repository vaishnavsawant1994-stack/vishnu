from scripts.install_rea import node_supported


def test_rea_node_range_matches_upstream_requirement():
    assert node_supported("v22.19.0") is True
    assert node_supported("22.20.1") is True
    assert node_supported("v22.18.9") is False
    assert node_supported("v23.9.0") is False
    assert node_supported("v24.10.9") is False
    assert node_supported("v24.11.0") is True
    assert node_supported("v25.0.0") is False
    assert node_supported("v26.0.0") is True
    assert node_supported("garbage") is False
