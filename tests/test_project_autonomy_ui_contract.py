from pathlib import Path


def test_project_autonomy_ui_uses_only_existing_authoritative_endpoints():
    text = Path("pwa/project-autonomy-controls.js").read_text()
    assert "/work/autonomy" in text
    assert "/advance" in text
    assert "method:'PUT'" in text
    assert "method:'POST'" in text
    assert "localStorage" not in text
    assert "sessionStorage" not in text
    assert "existing P10/P6 runtime" in text
    assert "Completion Judge" in text or "completion" in text.lower()
    assert "Emergency Stop" in text
    assert "Approval is required" in text
    assert "Recovery or remote-state reconciliation" in text


def test_project_autonomy_ui_is_loaded_after_canonical_work_and_precached():
    loader = Path("pwa/home-chat-redesign.js").read_text()
    assert "script.onload=loadProjectAutonomy" in loader
    assert "controls.onload=loadVisualizations" in loader
    assert "project-autonomy-controls.js" in loader
    assert "projects-work-runtime.js" in loader
    assert "projects-work-visualization-runtime.js" in loader
    sw = Path("pwa/sw.js").read_text()
    assert "project-autonomy-controls.js" in sw
    # P2-01 v61 refreshes the installed shell with its new canonical Home assets
    # while retaining the bounded local-first continuation cache.
    # The cache version assertion remains strict to catch stale PWA bundles.
    assert "personal-ai-iphone-v61" in sw
    assert "adaptive-composer.js" in sw
    assert "data-plane-cache.js" in sw
    assert "agents.html" in sw
    assert "agents-workforce.js" in sw
    assert "url.pathname.startsWith('/iphone/api/')" in sw
    assert "SHELL_SET.has(url.pathname)" in sw
    assert "dataPolicy==='device_only'" in sw
