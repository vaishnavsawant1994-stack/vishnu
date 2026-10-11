from __future__ import annotations

from types import SimpleNamespace
import zipfile

import pytest

from models.hardware_profile import HardwareProfile
from models.model_bundle import (
    checkpoint_inventory_sha256,
    create_portable_model_bundle,
    verify_portable_model_bundle,
)
from models.portable_runtime import PortableIntelligenceRuntime
from models.router import Provider


class FakeResponse:
    def close(self):
        return None


class FakeRouter:
    def __init__(self):
        self.providers = {
            "self_hosted": Provider(
                id="self_hosted",
                base_url="http://127.0.0.1:11434/v1",
                api_key="",
                model="vishnu-small-v1",
                private=True,
                capabilities=("chat",),
                cost_rank=1,
                latency_rank=1,
            )
        }
        self.owner_privacy = "local_only"
        self.disabled = set()
        self.owner_allowed = ()
        self.health_timeout = 1.0

    def _request(self, provider, method, path, *, timeout=None, **kwargs):
        return FakeResponse()


class FixedHardware:
    def probe(self, path=".", *, online=False):
        return HardwareProfile(
            platform="linux",
            architecture="x86_64",
            cpu_logical_cores=8,
            ram_gb=16.0,
            disk_free_gb=100.0,
            accelerator="none",
            online=bool(online),
        )


class FakeGovernance:
    def active_model(self):
        return {"model_id": "model-active"}


class FakeTrainingRegistry:
    def __init__(self, model):
        self.model = model
        self.governance = FakeGovernance()

    def get_model(self, model_id):
        return self.model if model_id == self.model.model_id else None


def _checkpoint(tmp_path):
    root = tmp_path / "checkpoint"
    root.mkdir()
    (root / "adapter_model.safetensors").write_bytes(b"weights-v1")
    (root / "adapter_config.json").write_text('{"r":8}', encoding="utf-8")
    tokenizer = root / "tokenizer"
    tokenizer.mkdir()
    (tokenizer / "tokenizer.json").write_text('{"version":1}', encoding="utf-8")
    return root


def test_portable_model_bundle_is_deterministic_and_inventory_bound(tmp_path):
    checkpoint = _checkpoint(tmp_path)
    inventory_sha = checkpoint_inventory_sha256(checkpoint)

    first = create_portable_model_bundle(
        checkpoint,
        tmp_path / "first.zip",
        model_id="model-active",
        expected_inventory_sha256=inventory_sha,
    )
    second = create_portable_model_bundle(
        checkpoint,
        tmp_path / "second.zip",
        model_id="model-active",
        expected_inventory_sha256=inventory_sha,
    )

    assert first.inventory_sha256 == inventory_sha
    assert second.inventory_sha256 == inventory_sha
    assert first.bundle_sha256 == second.bundle_sha256
    assert first.size_bytes == second.size_bytes
    assert verify_portable_model_bundle(first.path, expected_model_id="model-active").inventory_sha256 == inventory_sha


def test_portable_model_bundle_rejects_unexpected_member_tampering(tmp_path):
    checkpoint = _checkpoint(tmp_path)
    bundle = create_portable_model_bundle(checkpoint, tmp_path / "model.zip", model_id="model-active")
    with zipfile.ZipFile(bundle.path, mode="a") as archive:
        archive.writestr("unexpected.txt", b"tampered")
    with pytest.raises(RuntimeError, match="unexpected or missing"):
        verify_portable_model_bundle(bundle.path, expected_model_id="model-active")


def test_portable_model_bundle_rejects_checkpoint_symlink(tmp_path):
    checkpoint = _checkpoint(tmp_path)
    link = checkpoint / "unsafe-link"
    try:
        link.symlink_to(checkpoint / "adapter_config.json")
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is unavailable on this platform")
    with pytest.raises(ValueError, match="symbolic links"):
        checkpoint_inventory_sha256(checkpoint)


def test_active_trained_directory_enters_restore_package_vault_and_offline_pack(tmp_path):
    checkpoint = _checkpoint(tmp_path)
    inventory_sha = checkpoint_inventory_sha256(checkpoint)
    model = SimpleNamespace(
        model_id="model-active",
        checkpoint_ref=str(checkpoint),
        method="lora",
        created_at="2026-10-11T00:00:00+00:00",
        metrics={"artifact_sha256": inventory_sha},
    )
    registry = FakeTrainingRegistry(model)
    runtime = PortableIntelligenceRuntime(
        tmp_path / "runtime",
        model_router=FakeRouter(),
        settings=SimpleNamespace(
            local_ai_model_tier="small",
            local_ai_min_ram_gb=1.0,
            local_ai_min_vram_gb=0.0,
        ),
        training_registry=registry,
        vault_persistent=True,
    )
    runtime.hardware = FixedHardware()

    package = runtime.publish_current_restore_package(core_version="test-revision")
    assert len(package.artifacts) == 1
    artifact = package.artifacts[0]
    assert artifact.artifact_id == "model-active"
    assert artifact.name == "active-trained-model-bundle"
    assert artifact.kind.value == "adapter"
    record = runtime.vault.verify("owner", "model-active")
    assert record.artifact.sha256 == artifact.sha256

    trained_ref = next(item for item in package.manifest.models if item.name == "trained:active")
    assert trained_ref.sha256 == inventory_sha

    offline = runtime.prepare_offline_pack()
    assert offline.local_artifacts["model-active"] == artifact.sha256
    assert offline.manifest.artifacts[0].artifact_id == "model-active"
    assert runtime.status()["active_trained_model_artifact_included"] is True
