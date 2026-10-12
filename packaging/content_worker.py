from __future__ import annotations

import argparse
import json
import os
import socket
import time
from pathlib import Path

from core.config import settings
from file_intelligence.production import ContentWorker, ProductionContentStore


def _int_env(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name, default)).strip())
    except (TypeError, ValueError):
        return default


def build_store() -> ProductionContentStore:
    return ProductionContentStore(
        settings.data_dir / "content-runtime.sqlite3",
        settings.data_dir / "content-runtime",
        max_upload_bytes=_int_env("VISHNU_CONTENT_MAX_UPLOAD_BYTES", 20 * 1024 * 1024 * 1024),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run a Vishnu Universal Content Intelligence production worker")
    parser.add_argument("--worker-id", default=f"{socket.gethostname()}-{os.getpid()}")
    parser.add_argument("--gpu", action="store_true", help="Allow this worker to claim GPU-required content jobs")
    parser.add_argument("--once", action="store_true", help="Process at most one job and exit")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--max-materialize-bytes", type=int, default=_int_env("VISHNU_CONTENT_WORKER_MATERIALIZE_BYTES", 2 * 1024 * 1024 * 1024))
    args = parser.parse_args(argv)

    store = build_store()
    worker = ContentWorker(
        store,
        worker_id=args.worker_id,
        has_gpu=args.gpu,
        max_materialize_bytes=max(1, args.max_materialize_bytes),
    )
    print(json.dumps({"event": "content.worker.ready", "worker_id": args.worker_id, "gpu": args.gpu, "health": store.health()}), flush=True)
    while True:
        result = worker.process_once()
        if result:
            print(json.dumps({"event": "content.worker.job", "job_id": result["job_id"], "status": result["status"], "attempts": result["attempts"]}), flush=True)
        if args.once:
            return 0
        if result is None:
            time.sleep(max(0.1, min(float(args.poll_seconds), 30.0)))


if __name__ == "__main__":
    raise SystemExit(main())
