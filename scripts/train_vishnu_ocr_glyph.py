from __future__ import annotations

import argparse
import json
from pathlib import Path

from training.content_models import ContentModelCoordinator
from training.ocr_family import OCRModelMaturationCoordinator


def _load_samples(path: Path) -> list[dict]:
    root = path.expanduser().resolve().parent
    rows: list[dict] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at line {line_number}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"sample at line {line_number} must be an object")
        image_path = str(payload.pop("image_path", "") or "").strip()
        if not image_path:
            raise ValueError(f"sample at line {line_number} requires image_path")
        resolved = (root / image_path).resolve() if not Path(image_path).is_absolute() else Path(image_path).resolve()
        if not resolved.is_file():
            raise ValueError(f"sample image does not exist at line {line_number}: {resolved}")
        payload["image_bytes"] = resolved.read_bytes()
        rows.append(payload)
    if not rows:
        raise ValueError("sample manifest is empty")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Train Vishnu's governed isolated-glyph OCR-family candidate. "
            "This command never owner-approves or activates a model."
        )
    )
    parser.add_argument("--samples", required=True, type=Path, help="JSONL manifest with image_path and governed metadata")
    parser.add_argument("--data-dir", required=True, type=Path, help="Durable/local directory for datasets, artifacts and registry")
    parser.add_argument("--dataset-name", default="vishnu-ocr-glyph-v1")
    parser.add_argument(
        "--shadow-with-tesseract",
        action="store_true",
        help="Run local Tesseract shadow comparison after training. Fails closed if Tesseract is unavailable.",
    )
    args = parser.parse_args()

    data_dir = args.data_dir.expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    content = ContentModelCoordinator(
        datasets_root=data_dir / "datasets",
        artifacts_root=data_dir / "artifacts",
        registry_path=data_dir / "content-models.sqlite3",
        artifact_persistent=False,
    )
    maturation = OCRModelMaturationCoordinator(
        content,
        shadow_store_path=data_dir / "ocr-shadow.sqlite3",
    )
    model = maturation.train_candidate(_load_samples(args.samples.expanduser().resolve()), dataset_name=args.dataset_name)
    output = {
        "model_id": model["model_id"],
        "status": model["status"],
        "task": model["task"],
        "backend_id": model["backend_id"],
        "dataset_snapshot_id": model["dataset_snapshot_id"],
        "artifact_id": model["artifact_id"],
        "checkpoint_ref": model["checkpoint_ref"],
        "metrics": model["metrics"],
        "evaluation": model["evaluation"],
        "metadata": model["metadata"],
        "owner_approved": False,
        "activated": False,
    }
    if args.shadow_with_tesseract:
        output["shadow"] = maturation.shadow_qualify(model["model_id"])
    print(json.dumps(output, sort_keys=True, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
