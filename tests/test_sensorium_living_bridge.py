from __future__ import annotations

from sensorium.live_work import overlay_sensorium_living


def _canonical(state: str = "idle") -> dict:
    return {
        "authority": "presentation_only",
        "source": "canonical_work_attention",
        "state": state,
        "activity": "canonical activity",
        "intensity": 0.0 if state == "idle" else 0.8,
        "needs_attention": False,
        "attention_count": 0,
    }


def _sensorium(state: str, activity: str = "safe sensorium activity") -> dict:
    return {
        "authority": "read_only_projection",
        "presentation_only": True,
        "execution_authority": False,
        "reasoning_exposed": False,
        "raw_sensor_content_exposed": False,
        "state": state,
        "activity": activity,
        "events": [{"metadata": {"transaction_id": "tx-1"}, "secret": "must-not-copy"}],
    }


def test_active_canonical_work_always_wins_over_sensorium():
    for state in (
        "waiting_approval",
        "recovering",
        "reviewing",
        "blocked",
        "replanning",
        "verifying",
        "working",
        "coding",
        "browsing",
        "researching",
        "planning",
        "needs_attention",
    ):
        result = overlay_sensorium_living(_canonical(state), _sensorium("working"))
        assert result["state"] == state
        assert result["activity"] == "canonical activity"
        assert result["sensorium_overlay"] is False


def test_idle_canonical_projection_can_show_sensorium_presence():
    mapping = {
        "watching": ("watching", 0.4),
        "thinking": ("thinking", 0.5),
        "working": ("working", 0.68),
        "waiting_for_approval": ("waiting_approval", 0.95),
        "verifying": ("verifying", 0.72),
        "blocked": ("blocked", 0.8),
    }
    for sensorium_state, (expected_state, expected_intensity) in mapping.items():
        result = overlay_sensorium_living(_canonical("idle"), _sensorium(sensorium_state))
        assert result["authority"] == "presentation_only"
        assert result["source"] == "canonical_work_attention+sensorium"
        assert result["state"] == expected_state
        assert result["intensity"] == expected_intensity
        assert result["sensorium_overlay"] is True
        assert result["sensorium_state"] == sensorium_state


def test_sensorium_attention_is_presentation_only_and_does_not_rewrite_canonical_counts():
    canonical = _canonical("idle")
    canonical.update({"needs_attention": False, "attention_count": 0, "approval_count": 0, "blocked_count": 0})
    result = overlay_sensorium_living(canonical, _sensorium("waiting_for_approval"))

    assert result["state"] == "waiting_approval"
    assert result["sensorium_needs_attention"] is True
    assert result["needs_attention"] is False
    assert result["attention_count"] == 0
    assert result["approval_count"] == 0
    assert result["blocked_count"] == 0


def test_completed_or_unknown_sensorium_state_does_not_override_canonical():
    for state in ("completed", "idle", "unknown", ""):
        result = overlay_sensorium_living(_canonical("idle"), _sensorium(state))
        assert result["state"] == "idle"
        assert result["sensorium_overlay"] is False


def test_untrusted_or_authoritative_sensorium_snapshot_fails_closed():
    authoritative = _sensorium("working")
    authoritative["execution_authority"] = True
    assert overlay_sensorium_living(_canonical(), authoritative)["sensorium_overlay"] is False

    reasoning = _sensorium("thinking")
    reasoning["reasoning_exposed"] = True
    assert overlay_sensorium_living(_canonical(), reasoning)["sensorium_overlay"] is False

    raw = _sensorium("watching")
    raw["raw_sensor_content_exposed"] = True
    assert overlay_sensorium_living(_canonical(), raw)["sensorium_overlay"] is False


def test_living_overlay_never_copies_sensorium_events_or_metadata():
    secret = "private-clipboard-content"
    snapshot = _sensorium("working", "Working safely")
    snapshot["events"] = [{"payload": {"text": secret}, "metadata": {"transaction_id": "tx-secret"}}]
    result = overlay_sensorium_living(_canonical(), snapshot)

    assert result["sensorium_overlay"] is True
    assert "events" not in result
    assert "metadata" not in result
    assert secret not in repr(result)
    assert "tx-secret" not in repr(result)
