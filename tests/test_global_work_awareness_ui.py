from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "pwa" / "global-work-awareness.js"
LOADER = ROOT / "pwa" / "home-chat-redesign.js"
SERVICE_WORKER = ROOT / "pwa" / "sw.js"
GLOBAL_API = ROOT / "server" / "global_work_api.py"
CLOUD_APP = ROOT / "server" / "cloud_app.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_global_work_awareness_is_read_only_and_canonical():
    source = _read(RUNTIME)

    for marker in (
        "authority:'presentation_only'",
        "source:'canonical_project_work'",
        "/work/summary",
        "read_only_projection",
        "WAITING_APPROVAL",
        "RECOVERY_REQUIRED",
        "UNCERTAIN",
        "Canonical Work state only.",
        "Vishnu work",
        "openProject(order.projectId,'live')",
    ):
        assert marker in source, marker

    assert "method:'POST'" not in source
    assert 'method:"POST"' not in source
    assert "/execute" not in source
    assert "/pause" not in source
    assert "/resume" not in source
    assert "/cancel" not in source
    assert "approve(" not in source.lower()


def test_global_awareness_updates_home_today_and_idle_living_state_only():
    source = _read(RUNTIME)

    assert "globalWorkPulse" in source
    assert "globalWorkTodaySection" in source
    assert "stateLabel" in source
    assert "status" in source
    assert "['idle','active','background'].includes(stateName)" in source
    assert "@media(max-width:760px)" in source
    assert "REFRESH_MS=30000" in source


def test_global_summary_api_is_owner_scoped_read_only_projection():
    source = _read(GLOBAL_API)
    cloud = _read(CLOUD_APP)

    assert 'APIRouter(prefix="/iphone/api/work"' in source
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

    # v52 refreshes the onboarding shell while retaining the canonical work and
    # global-awareness assets in the same offline cache.
    assert "personal-ai-iphone-v52" in sw
    assert "'/iphone/global-work-awareness.js'" in sw
    assert "'/iphone/adaptive-composer.js'" in sw
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
    )
    assert result.returncode == 0, result.stderr
