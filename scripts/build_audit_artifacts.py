#!/usr/bin/env python3
"""Build source-led audit inventories from a Vishnu checkout and PR export JSON."""

from __future__ import annotations

import ast
import csv
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "audit"
PR_FILES = [Path(f"/tmp/vishnu_prs{i}.json") for i in (1, 2, 3)]

PURPOSES = {
    "activities": "Activity and ambient-intelligence domain.",
    "agent": "Agent planning, execution, context and coordination.",
    "android-companion": "Native Android companion, trusted-device and Sensorium flows.",
    "app": "Desktop application entry and runtime composition.",
    "approvals": "Canonical approval policy and decision records.",
    "apps_tools": "Owner-facing app and tool catalog surfaces.",
    "automation": "Workflow scheduling and governed automation runtime.",
    "browser": "Browser integration and browser-control support.",
    "capabilities": "Capability catalog, OpenAPI/MCP governance and execution.",
    "cloud_runtime": "Hosted runtime composition and configuration.",
    "config": "Configuration parsing and validation.",
    "continuity": "Cross-device continuity, synchronization and leases.",
    "core": "Shared runtime primitives, SQLite and event foundations.",
    "dashboard": "Dashboard and owner/runtime overview services.",
    "data_plane": "Local-first policy, placement, transfer, encryption and reconciliation.",
    "deploy": "Deployment configuration and self-hosted model support.",
    "desktop": "PyQt/native desktop product surface and controls.",
    "devices": "Device identity, registry, pairing, trust and gateway.",
    "docs": "Product, architecture, qualification and operational documentation.",
    "evidence": "Evidence records and qualification artifacts.",
    "evolution": "Governed self-improvement and code-evolution pipeline.",
    "file_intelligence": "File parsing, extraction and content understanding.",
    "future_intelligence": "Isolated experimental intelligence, workers and capability-factory systems.",
    "identity": "Owner identity, authentication, sessions and recovery identity.",
    "installer": "Installer entry points and platform setup.",
    "integrations": "External connector and third-party integration adapters.",
    "intelligence_lab": "Gated research, benchmark and experiment workspace.",
    "ios-companion": "Native iOS companion, trusted-device and Sensorium flows.",
    "knowledge": "Knowledge ingestion, indexing, retrieval and citations.",
    "memory": "Owner memory capture, retrieval, governance and storage.",
    "models": "Model/provider abstraction, routing and local model support.",
    "notifications": "Notification generation and delivery preferences.",
    "onboarding": "First-run, create/join/restore and enrollment flows.",
    "packaging": "Product build runners, distribution and release packaging.",
    "personal-ai": "Legacy product-specific source boundary retained in repository.",
    "playbooks": "Reusable task playbooks and procedures.",
    "plugins": "Plugin descriptors and discovery boundary.",
    "proactive": "Proactive monitoring and user attention flows.",
    "products": "Product catalog, composition and product lifecycle.",
    "projects": "Project workspace, work orders and autonomy flows.",
    "pwa": "Progressive web application assets and client runtime.",
    "qualification": "Qualification harnesses and evidence schemas.",
    "readiness": "Release and readiness state models.",
    "recovery": "Backup, restore and disaster-recovery logic.",
    "scripts": "Build, lockfile, validation and repository maintenance scripts.",
    "security": "Authentication enforcement, vault, threat controls and assurance.",
    "sensorium": "Sensor/device perception abstractions, providers and evidence.",
    "server": "FastAPI applications, API routers and hosted runtime.",
    "tests": "Unit, integration, API, browser and qualification tests.",
    "tools": "Tool definitions and governed tool registry/execution.",
    "training": "Model/content training, export and governance.",
    "trust_continuity": "Trust and cross-device continuity protocols.",
    "ui": "Shared UI assets and product surfaces.",
    "updates": "Signed update metadata and update workflows.",
    "vision": "Vision services and image understanding.",
    "visual_intelligence": "Visualization runtime, sources and owner workspace.",
    "voice": "Voice intelligence, provider adapters and Voice Lab.",
    "web-companion": "Browser-based companion surface and support.",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, errors="replace")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def read_prs() -> list[dict]:
    return [p for f in PR_FILES for p in json.loads(f.read_text())]


def extract_routes() -> list[dict]:
    found = []
    tracked_paths = git("ls-files").splitlines()
    for rel in sorted(p for p in tracked_paths if p.endswith(".py") and not p.startswith("tests/")):
        path = ROOT / rel
        try:
            tree = ast.parse(path.read_text(errors="replace"))
        except SyntaxError:
            continue
        prefixes: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = node.value
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if isinstance(value, ast.Call) and getattr(value.func, "id", "") == "APIRouter":
                    prefix = ""
                    for kw in value.keywords:
                        if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                            prefix = str(kw.value.value)
                    for target in targets:
                        if isinstance(target, ast.Name):
                            prefixes[target.id] = prefix
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
                    continue
                method = dec.func.attr.upper()
                if method not in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}:
                    continue
                owner = dec.func.value.id if isinstance(dec.func.value, ast.Name) else ""
                route = ""
                if dec.args and isinstance(dec.args[0], ast.Constant):
                    route = str(dec.args[0].value)
                full_path = prefixes.get(owner, "") + route
                found.append(
                    {
                        "method": method,
                        "path": full_path,
                        "module": path.relative_to(ROOT).as_posix(),
                        "handler": node.name,
                        "router": owner or "unknown",
                        "auth": "NOT VERIFIED by static inventory; inspect handler dependencies",
                        "approval": "NOT VERIFIED except where explicit capability/work policy is documented",
                        "tests": "Not mapped per route in this inventory; use linked domain tests",
                        "status": "STATIC ROUTE DECLARED; runtime reachability/security not fully verified",
                    }
                )
    return sorted(found, key=lambda r: (r["path"], r["method"], r["module"]))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    head = git("rev-parse", "HEAD").strip()
    tracked = git("ls-files").splitlines()
    root_names = sorted({p.split("/", 1)[0] for p in tracked if "/" in p and not p.startswith(".github/")})
    rootdirs = [ROOT / name for name in root_names if (ROOT / name).is_dir()]
    inventory = []
    for d in sorted(rootdirs, key=lambda p: p.name):
        files = sorted(p for p in tracked if p.startswith(d.name + "/"))
        inventory.append(
            {
                "name": d.name,
                "path": d.name,
                "purpose": PURPOSES.get(d.name, "Purpose requires source-owner review."),
                "tracked_file_count": len(files),
                "source_entry_points": [
                    p
                    for p in files
                    if p.endswith(("__main__.py", "main.py", "app.py", "api.py", "App.swift", "MainActivity.kt"))
                ][:12],
                "api_exposure": "See API_INVENTORY.md; not implied by directory presence",
                "storage": "See DATA_ARCHITECTURE.md",
                "ui_exposure": "See UI_SCREEN_INVENTORY.md",
                "tests": "See TEST_COVERAGE_MAP.md",
                "status": "ACTIVE_CANDIDATE; exact runtime reachability varies and is documented separately",
                "evidence": [p for p in files if p.startswith("docs/")][:8],
            }
        )
    write_json(
        OUT / "repository_inventory.json",
        {"repository": "vaishnavsawant1994-stack/vishnu", "audited_sha": head, "subsystems": inventory},
    )

    prs = sorted(read_prs(), key=lambda p: p["number"])
    prrows = []
    for p in prs:
        body = p.get("body") or ""
        section = re.search(
            r"(?im)^#{1,2}\s+(?:Summary|Implemented|What(?:'|&#39;)?s included|Implementation)\b([\s\S]*?)(?=^#{1,2}\s+|\Z)",
            body,
        )
        source = section.group(1) if section else body
        bullets = [
            re.sub(r"\s+", " ", line.strip(" -*\t"))
            for line in source.splitlines()
            if re.match(r"^\s*(?:[-*]|\d+\.)\s+", line)
        ]
        paragraphs = [
            re.sub(r"\s+", " ", s).strip()
            for s in re.split(r"\n\s*\n", source)
            if s.strip() and not s.lstrip().startswith(("-", "*", "#"))
        ]
        details = (paragraphs[:1] + bullets[:5])[:6]
        summary = " ".join(details).strip()[:900]
        prrows.append(
            {
                "number": p["number"],
                "title": p["title"],
                "state": p["state"],
                "merged_at": p.get("merged_at"),
                "head_sha": (p.get("head") or {}).get("sha"),
                "base_ref": (p.get("base") or {}).get("ref"),
                "merge_commit_sha": p.get("merge_commit_sha"),
                "url": p["html_url"],
                "implementation_summary": summary,
                "changed_files": p.get("changed_files"),
                "additions": p.get("additions"),
                "deletions": p.get("deletions"),
            }
        )
    write_json(
        OUT / "pr_implementation_ledger.json",
        {
            "audited_main_sha": head,
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": "GitHub REST pulls state=all, three pages, 100 per page",
            "pull_requests": prrows,
        },
    )

    routes = extract_routes()
    write_json(
        OUT / "api_inventory.json",
        {
            "audited_sha": head,
            "extraction": "AST scan of tracked Python files outside tests; FastAPI-style router decorators; statically declared only",
            "routes": routes,
        },
    )

    log = git("log", "--diff-merges=first-parent", "--date=short", "--format=%H%x09%ad%x09%P%x09%s", "--name-only")
    commits = []
    cur = None
    for line in log.splitlines():
        if not line:
            continue
        parts = line.split("\t", 3)
        if len(parts) == 4 and re.fullmatch(r"[0-9a-f]{40}", parts[0]):
            if cur:
                commits.append(cur)
            cur = {
                "sha": parts[0],
                "date": parts[1],
                "parents": parts[2].split() if parts[2] else [],
                "subject": parts[3],
                "files": [],
            }
        elif cur:
            cur["files"].append(line)
    if cur:
        commits.append(cur)
    with (OUT / "commit_ledger.csv").open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["sha", "date", "parents", "subject", "changed_file_count", "changed_files"],
            lineterminator="\n",
        )
        w.writeheader()
        for c in commits:
            w.writerow(
                {
                    "sha": c["sha"],
                    "date": c["date"],
                    "parents": " ".join(c["parents"]),
                    "subject": c["subject"],
                    "changed_file_count": len(c["files"]),
                    "changed_files": " | ".join(c["files"]),
                }
            )

    with (OUT / "pr_implementation_ledger.md").open("w") as f:
        f.write(
            f"# Pull request implementation ledger\n\nAudited `main` SHA: `{head}`. Source: GitHub REST `pulls?state=all`, retrieved at {datetime.now(timezone.utc).isoformat()}. {len(prrows)} PR records were returned: {sum(bool(p['merged_at']) for p in prrows)} merged and {sum(p['state'] == 'open' for p in prrows)} open; the remaining records are closed without merge. This is a change ledger, not a claim that each PR's feature is currently user-complete.\n\nEach row gives the PR's own stated implementation scope and records its head and merge commits. Current code and tests still determine product truth. For every commit on the audited branch, see [commit_ledger.csv](commit_ledger.csv).\n\n| PR | State | Title | Stated implementation scope | Head | Merge commit |\n|---:|---|---|---|---|---|\n"
        )
        for p in prrows:
            state = "merged" if p["merged_at"] else p["state"]
            headsha = (p["head_sha"] or "")[:12]
            merge = (p["merge_commit_sha"] or "")[:12] or "—"
            title = p["title"].replace("|", "\\|")
            summary = p["implementation_summary"].replace("|", "\\|") or "No implementation summary in PR description."
            f.write(f"| [#{p['number']}]({p['url']}) | {state} | {title} | {summary} | `{headsha}` | `{merge}` |\n")

    print(
        json.dumps(
            {
                "sha": head,
                "subsystems": len(inventory),
                "prs": len(prrows),
                "merged": sum(bool(p["merged_at"]) for p in prrows),
                "commits": len(commits),
                "routes": len(routes),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
