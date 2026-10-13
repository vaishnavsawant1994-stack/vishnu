from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "pwa" / "global-work-awareness.js"
LOADER = ROOT / "pwa" / "projects-work-loader.js"
SERVICE_WORKER = ROOT / "pwa" / "sw.js"
API = ROOT / "server" / "global_work_api.py"
CLOUD = ROOT / "server" / "cloud.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_global_work_awareness_uses_existing_read_only_surfaces_and_no_execution_authority():
    source = _read(RUNTIME)

    assert "/iphone/api/global-work/summary" in source
    assert "/iphone/api/projects/${encodeURIComponent(id)}/status" in source
    assert "/iphone/api/projects/${encodeURIComponent(id)}/work-plan" in source
    assert "/iphone/api/projects/${encodeURIComponent(id)}/activity?limit=24" in source
    assert "/iphone/api/projects/${encodeURIComponent(id)}/live-work" in source
    assert "/iphone/api/projects/${encodeURIComponent(id)}/health" in source
    assert "/iphone/api/projects/${encodeURIComponent(id)}/timeline" in source
    assert "/iphone/api/projects/${encodeURIComponent(id)}/recent-events?limit=12" in source

    assert "fetch(url,{credentials:'same-origin',headers:{Accept:'application/json'}})" in source
    assert "method:'POST'" not in source
    assert "method:'PATCH'" not in source
    assert "method:'DELETE'" not in source
    assert "execute" not in source.lower()
    assert "approval" not in source.lower()


def test_global_work_awareness_renders_multi_project_status_and_attention_signals():
    source = _read(RUNTIME)

    assert "Global work awareness" in source
    assert "Needs your attention" in source
    assert "Projects continuing" in source
    assert "project.workspace" in source
    assert "project.status" in source
    assert "project.health" in source
    assert "project.progress" in source
    assert "project.blocker" in source
    assert "project.next_action" in source
    assert "project.last_activity" in source
    assert "project.live_work" in source
    assert "project.timeline" in source


def test_global_work_summary_api_is_read_only_and_reuses_existing_project_authority():
    source = _read(API)
    cloud = _read(CLOUD)

    assert '@router.get("/summary")' in source
    assert '"authority": "read_only_projection"' in source
    assert 'execution_authority = "canonical_work" if authority else "existing_p10_p6_runtime"' in source
    assert '"work_authority_mode": work_authority_mode' in source
    assert "registry.authenticate(device_id, token)" in source
    assert "execute_task" not in source
    assert "@router.post" not in source
    assert "global_work_router(runtime,project_store)" in cloud


def test_global_awareness_loads_after_canonical_project_surfaces_and_is_precached():
    loader = _read(LOADER)
    sw = _read(SERVICE_WORKER)

    assert "/iphone/projects-work-runtime.js" in loader
    assert "/iphone/projects-work-visualization-runtime.js" in loader
    assert "/iphone/global-work-awareness.js" in loader
    assert "data-global-work-awareness" in loader
    assert "loadGlobalAwareness" in loader
    assert "visual.onload=loadGlobalAwareness" in loader

    assert "personal-ai-iphone-v37" in sw
    assert "'/iphone/global-work-awareness.js'" in sw
    assert "url.pathname.startsWith('/iphone/api/')" in sw


def test_global_work_awareness_has_valid_javascript_syntax():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is not installed in this test environment")
    result = subprocess.run(
        [node, "--check", str(RUNTIME)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
