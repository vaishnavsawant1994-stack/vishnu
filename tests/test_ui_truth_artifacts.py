from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ui_truth_artifacts_validate() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_ui_truth.py")],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "63 canonical screens" in result.stdout
