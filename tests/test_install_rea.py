import json

from scripts.install_rea import REA_VERSION, _write_runtime_manifest, node_supported


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


def test_rea_runtime_manifest_has_valid_private_npm_identity(tmp_path):
    _write_runtime_manifest(tmp_path)
    manifest = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "vishnu-rea-runtime"
    assert manifest["private"] is True
    assert manifest["dependencies"] == {"rea-agents": REA_VERSION}
