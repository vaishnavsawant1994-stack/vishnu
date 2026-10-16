from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_labs_hub_is_reachable_from_main_pwa_and_uses_existing_surfaces():
    pwa = (ROOT / "pwa/index.html").read_text(encoding="utf-8")

    assert 'data-app-module="labs"' in pwa
    assert "labs:['Labs & Workspaces'" in pwa
    assert "else if(name==='labs')loadLabs()" in pwa
    assert "'labs'].includes(name)" in pwa
    assert 'data-lab-module="projects"' in pwa
    assert 'data-lab-module="visualize"' in pwa
    assert 'data-lab-href="/iphone/agents.html"' in pwa
    assert 'data-lab-href="/iphone/our-products.html"' in pwa
    assert 'data-lab-href="/capabilities/forge"' in pwa
    assert 'data-lab-href="/capabilities/forge/production-readiness"' in pwa
    assert 'data-lab-settings="advanced"' in pwa


def test_labs_hub_preserves_existing_owner_and_approval_boundaries():
    pwa = (ROOT / "pwa/index.html").read_text(encoding="utf-8")
    forge = (ROOT / "server/capability_forge_v3_ui.py").read_text(encoding="utf-8")

    assert "experimental controls keep their existing owner and approval gates" in pwa
    assert "Activation remains governed by Vishnu’s separate approval authority." in pwa
    assert "cannot self-approve production activation" in forge
