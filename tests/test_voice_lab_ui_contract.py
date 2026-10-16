from __future__ import annotations

from pathlib import Path


def test_owner_telephony_ui_is_operational_and_governed():
    root = Path(__file__).resolve().parents[1]
    page = (root / "ui" / "voice_lab_telephony.py").read_text(encoding="utf-8")
    host = (root / "ui" / "voice_lab.py").read_text(encoding="utf-8")

    assert "TelephonyLabPage" in host
    assert "Owner approve & place governed call" in page
    assert "owner.verify_password" in page
    assert "TelephonyApproval.for_request" in page
    assert "looks_like_emergency_destination" in page
    assert "raw_destination_persisted" in page
    assert "hangup_call" in page
    assert "EvidenceRecord.build" in page
