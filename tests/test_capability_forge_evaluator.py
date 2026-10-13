from future_intelligence.capability_forge.evaluator import GeneratedCapabilityEvaluator
from future_intelligence.capability_forge.lifecycle import CapabilityForgeLifecycle


def _activate(store, capability_id, version, suffix):
    return store.record_activation(
        activation_id=f"activation:{suffix}",
        capability_id=capability_id,
        version=version,
        package_ref=f"generated-capabilities/{capability_id}/{version}",
        manifest_digest=f"digest-{suffix}",
        build_id=f"build-{suffix}",
        status="active",
        payload={"catalog_payload": {"id": capability_id, "version": version}},
    )


def test_evaluator_recommends_but_never_auto_rolls_back_regressed_version(tmp_path):
    lifecycle = CapabilityForgeLifecycle(tmp_path / "forge.sqlite3")
    capability_id = "generated.test"
    _activate(lifecycle, capability_id, "1.0.0", "v1")
    for _ in range(20):
        lifecycle.record_invocation(
            capability_id=capability_id,
            version="1.0.0",
            ok=True,
            duration_ms=10,
        )
    _activate(lifecycle, capability_id, "1.1.0", "v2")
    for index in range(20):
        lifecycle.record_invocation(
            capability_id=capability_id,
            version="1.1.0",
            ok=index >= 4,
            duration_ms=30,
            error_code="candidate_error" if index < 4 else None,
        )

    health = GeneratedCapabilityEvaluator(lifecycle).evaluate(capability_id)

    assert health.sufficient_evidence is True
    assert health.rollback_recommended is True
    assert health.state == "rollback_recommended"
    assert health.automatic_rollback_authority is False
    assert health.baseline_version == "1.0.0"
    assert health.active_version == "1.1.0"


def test_evaluator_observes_new_capability_until_sample_threshold(tmp_path):
    lifecycle = CapabilityForgeLifecycle(tmp_path / "forge.sqlite3")
    _activate(lifecycle, "generated.new", "1.0.0", "new")
    lifecycle.record_invocation(
        capability_id="generated.new",
        version="1.0.0",
        ok=True,
        duration_ms=5,
    )

    health = GeneratedCapabilityEvaluator(lifecycle).evaluate("generated.new")

    assert health.state == "observing"
    assert health.sufficient_evidence is False
    assert health.rollback_recommended is False
