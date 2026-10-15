from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

REA_VERSION = "6.5.0"
NODE_RANGE = "^22.19.0 || ^24.11.0 || >=26.0.0"
_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")


def node_supported(version: str) -> bool:
    match = _VERSION_RE.match(version.strip())
    if not match:
        return False
    major, minor, _patch = (int(value) for value in match.groups())
    return (major == 22 and minor >= 19) or (major == 24 and minor >= 11) or major >= 26


def _run(command: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False,
    )
    return result.stdout.strip()


def _write_runtime_manifest(prefix: Path) -> None:
    manifest = {
        "name": "vishnu-rea-runtime",
        "version": "1.0.0",
        "private": True,
        "description": "Pinned REA runtime bundled with Vishnu.",
        "dependencies": {"rea-agents": REA_VERSION},
    }
    (prefix / "package.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def install(repo_root: Path) -> Path:
    node = shutil.which("node")
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not node or not npm:
        raise RuntimeError(f"REA requires Node.js {NODE_RANGE} and npm; install them before installing Vishnu REA support")
    node_version = _run([node, "--version"])
    if not node_supported(node_version):
        raise RuntimeError(f"REA requires Node.js {NODE_RANGE}; found {node_version or 'unknown'}")

    prefix = repo_root / ".rea"
    prefix.mkdir(parents=True, exist_ok=True)
    _write_runtime_manifest(prefix)
    _run([npm, "install", "--prefix", str(prefix), "--save-exact", f"rea-agents@{REA_VERSION}"])
    executable = prefix / "node_modules" / ".bin" / ("rea.cmd" if os.name == "nt" else "rea")
    if not executable.is_file():
        raise RuntimeError("REA installation completed but the rea executable is missing")
    reported = _run([str(executable), "--version"])
    if REA_VERSION not in reported:
        raise RuntimeError(f"REA version verification failed: expected {REA_VERSION}, got {reported or 'no version'}")
    return executable


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    try:
        executable = install(repo_root)
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f"REA installation failed: {exc}", file=sys.stderr)
        return 1
    print(f"REA {REA_VERSION} installed and verified at {executable}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
