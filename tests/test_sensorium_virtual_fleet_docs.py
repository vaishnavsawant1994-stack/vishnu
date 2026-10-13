from pathlib import Path


def test_virtual_device_fleet_docs_preserve_simulation_authority_boundary():
    text = Path("docs/virtual-device-fleet.md").read_text(encoding="utf-8")
    assert "simulation only" in text.lower()
    assert "no physical execution authority" in text.lower()
    assert "device:admin" in text
    assert "memory:sensitive" in text
    assert "real devices later" in text.lower()
