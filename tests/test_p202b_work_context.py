"""P2-02B: Work conversation classification reuses canonical continuity context JSON."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from devices.continuity import ContinuityService
from server.iphone_pwa import ConversationCreateBody


def test_work_scope_persists_without_new_table(tmp_path):
    db = tmp_path / "continuity.sqlite3"
    first = ContinuityService(db)
    work_id = first.create_thread(
        "Marketing research", device_id="device-1", context={"conversation_kind": "work"}
    )
    personal_id = first.create_thread("Personal conversation", device_id="device-1")
    assert first.thread(work_id)["context"]["conversation_kind"] == "work"
    assert first.thread(personal_id)["context"] == {}
    assert len(first.list_threads(limit=10)) == 2

    # Existing conversation archive/export and restart continue to use one ledger.
    restarted = ContinuityService(db)
    assert restarted.thread(work_id)["context"]["conversation_kind"] == "work"
    restarted.rename_thread(work_id, "Strategy review")
    assert restarted.thread(work_id)["context"]["conversation_kind"] == "work"
    restarted.archive_thread(work_id)
    assert restarted.thread(work_id)["closed_at"] is not None
    assert restarted.thread(personal_id)["closed_at"] is None


def test_work_create_body_opt_in_and_invalid_type_fail_closed():
    assert ConversationCreateBody(title="Default").context_type == "personal"
    assert ConversationCreateBody(title="Work", context_type="work").context_type == "work"
    with pytest.raises(ValidationError):
        ConversationCreateBody(title="Unsafe", context_type="project")
