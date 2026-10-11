from __future__ import annotations

from dataclasses import dataclass

import pytest

from training.self_improvement import TrainedModelStatus
from training.specialists import SpecialistAdapterRegistry


@dataclass
class FakeModel:
    model_id: str
    checkpoint_ref: str
    base_model: str = "base/model"
    method: str = "lora"
    status: TrainedModelStatus = TrainedModelStatus.ACTIVE


class FakeModels:
    def __init__(self, *models: FakeModel) -> None:
        self.rows = {model.model_id: model for model in models}

    def get_model(self, model_id: str):
        return self.rows.get(model_id)


def test_only_production_active_model_can_be_bound(tmp_path):
    candidate = FakeModel("candidate", "/models/candidate", status=TrainedModelStatus.PROMOTION_READY)
    registry = SpecialistAdapterRegistry(tmp_path / "specialists.db", FakeModels(candidate))

    with pytest.raises(ValueError, match="production-active"):
        registry.bind(owner_id="owner", specialist_role="coding", model_id="candidate")


def test_owner_can_bind_and_resolve_active_specialist_model(tmp_path):
    model = FakeModel("coder-v1", "/models/coder-v1")
    registry = SpecialistAdapterRegistry(tmp_path / "specialists.db", FakeModels(model))

    binding = registry.bind(
        owner_id="owner",
        specialist_role="Coding",
        task_domain="software-engineering",
        model_id="coder-v1",
    )

    assert binding.specialist_role == "coding"
    assert binding.task_domain == "software-engineering"
    assert binding.active is True
    assert binding.public()["promotion_authority"] is False
    assert registry.resolve("coding", "software-engineering") == binding


def test_non_owner_cannot_change_specialist_bindings(tmp_path):
    model = FakeModel("coder-v1", "/models/coder-v1")
    registry = SpecialistAdapterRegistry(tmp_path / "specialists.db", FakeModels(model))

    with pytest.raises(PermissionError, match="canonical owner"):
        registry.bind(owner_id="user-2", specialist_role="coding", model_id="coder-v1")


def test_new_binding_supersedes_prior_binding_for_same_role_and_domain(tmp_path):
    first = FakeModel("coder-v1", "/models/coder-v1")
    second = FakeModel("coder-v2", "/models/coder-v2")
    registry = SpecialistAdapterRegistry(tmp_path / "specialists.db", FakeModels(first, second))

    old = registry.bind(owner_id="owner", specialist_role="coding", task_domain="general", model_id="coder-v1")
    new = registry.bind(owner_id="owner", specialist_role="coding", task_domain="general", model_id="coder-v2")

    assert registry.resolve("coding").model_id == "coder-v2"
    old_after = registry.get(old.binding_id)
    assert old_after.active is False
    assert old_after.superseded_at is not None
    assert new.active is True
    assert len(registry.active_bindings()) == 1


def test_domain_specific_resolution_can_fall_back_to_general_specialist(tmp_path):
    model = FakeModel("research-v1", "/models/research-v1")
    registry = SpecialistAdapterRegistry(tmp_path / "specialists.db", FakeModels(model))
    general = registry.bind(owner_id="owner", specialist_role="research", task_domain="general", model_id="research-v1")

    assert registry.resolve("research", "aerospace") == general


def test_binding_becomes_ineligible_if_canonical_model_is_no_longer_active(tmp_path):
    model = FakeModel("coder-v1", "/models/coder-v1")
    models = FakeModels(model)
    registry = SpecialistAdapterRegistry(tmp_path / "specialists.db", models)
    registry.bind(owner_id="owner", specialist_role="coding", model_id="coder-v1")

    model.status = TrainedModelStatus.REJECTED
    assert registry.resolve("coding") is None
    assert registry.active_bindings() == ()


def test_binding_becomes_ineligible_if_checkpoint_identity_changes(tmp_path):
    model = FakeModel("coder-v1", "/models/coder-v1")
    models = FakeModels(model)
    registry = SpecialistAdapterRegistry(tmp_path / "specialists.db", models)
    registry.bind(owner_id="owner", specialist_role="coding", model_id="coder-v1")

    model.checkpoint_ref = "/models/unexpected"
    assert registry.resolve("coding") is None


def test_owner_can_unbind_without_changing_model_state(tmp_path):
    model = FakeModel("design-v1", "/models/design-v1")
    registry = SpecialistAdapterRegistry(tmp_path / "specialists.db", FakeModels(model))
    registry.bind(owner_id="owner", specialist_role="design", model_id="design-v1")

    assert registry.unbind(owner_id="owner", specialist_role="design") is True
    assert registry.resolve("design") is None
    assert model.status is TrainedModelStatus.ACTIVE


def test_general_role_is_not_treated_as_specialist(tmp_path):
    model = FakeModel("general-v1", "/models/general-v1")
    registry = SpecialistAdapterRegistry(tmp_path / "specialists.db", FakeModels(model))

    with pytest.raises(ValueError, match="specialist_role"):
        registry.bind(owner_id="owner", specialist_role="general", model_id="general-v1")
