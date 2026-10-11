from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from products.build_lifecycle import ProductBuildLifecycle
from products.platform_jobs import ProductPlatformBuildJobs, REMOTE_PLATFORM_TARGETS
from products.store import ProductStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an isolated Vishnu product platform build job for qualification")
    parser.add_argument("--target", choices=REMOTE_PLATFORM_TARGETS, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--production", action="store_true", help="Require configured product signing instead of an unsigned development job")
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    store = ProductStore(workspace / "products.sqlite3")
    product = store.create(
        name=f"Qualified {args.target.title()} Product",
        product_type="ai_employee",
        description=f"Isolated {args.target} platform-runner qualification product.",
        targets=[args.target],
    )
    store.set_ai_policy(product["id"], {"mode": "disabled"})
    store.add_component(
        product["id"],
        component_type="workflow",
        component_ref="qualification.workflow",
        name="Qualification Workflow",
        config={"portable": True, "target": args.target},
    )
    store.create_version(product["id"], version="0.1.0")
    build = store.request_build(product["id"], target=args.target)
    if build is None:
        raise RuntimeError("Unable to create product build request")
    jobs = ProductPlatformBuildJobs(store, ProductBuildLifecycle(store.path), workspace / "artifacts")
    filename, raw, metadata = jobs.prepare_job(product["id"], build["id"], development=not args.production)
    output.write_bytes(raw)
    report = {
        "product_id": product["id"],
        "build_id": build["id"],
        "target": args.target,
        "version": "0.1.0",
        "job_file": str(output),
        "job_filename": filename,
        **metadata,
    }
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
