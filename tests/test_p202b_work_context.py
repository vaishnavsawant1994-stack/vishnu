"""P2-02B: Work conversation classification reuses canonical continuity context JSON."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from devices.continuity import ContinuityService
from server.iphone_pwa import ConversationCreateBody, ConversationWorkProjectBody


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


def test_work_project_association_survives_restart_without_changing_personal(tmp_path):
    db = tmp_path / "continuity.sqlite3"
    first = ContinuityService(db)
    work_id = first.create_thread(
        "Planning", device_id="device-1", context={"conversation_kind": "work"}
    )
    personal_id = first.create_thread("Personal", device_id="device-1")
    first.update_context(work_id, {"work_project_id": "project-verified"})
    assert first.thread(work_id)["context"] == {
        "conversation_kind": "work", "work_project_id": "project-verified"
    }
    assert first.thread(personal_id)["context"] == {}
    restarted = ContinuityService(db)
    assert restarted.thread(work_id)["context"]["work_project_id"] == "project-verified"
    assert restarted.export_thread(work_id)["conversation"]["context"]["work_project_id"] == "project-verified"
    restarted.update_context(work_id, {"work_project_id": None})
    assert restarted.thread(work_id)["context"]["conversation_kind"] == "work"
    assert restarted.thread(work_id)["context"]["work_project_id"] is None
    assert restarted.thread(personal_id)["context"] == {}


def test_project_link_request_requires_confirmation_and_bounded_id():
    assert ConversationWorkProjectBody(project_id="project-1", confirm=True).project_id == "project-1"
    assert ConversationWorkProjectBody(project_id=None, confirm=True).project_id is None
    with pytest.raises(ValidationError):
        ConversationWorkProjectBody(project_id="project-1", confirm=False)
    with pytest.raises(ValidationError):
        ConversationWorkProjectBody(project_id="a" * 81, confirm=True)
    with pytest.raises(ValidationError):
        ConversationWorkProjectBody(project_id="project-1")


def test_kind_filter_applies_before_history_limit(tmp_path):
    ledger = ContinuityService(tmp_path / 'many-conversations.sqlite3')
    old_work_id = ledger.create_thread('Old Work', context={'conversation_kind': 'work'})
    # Previously the newest 200 mixed threads were selected before the Work filter.
    for number in range(205):
        ledger.create_thread(f'Personal {number}')
    ledger.create_thread('Recent Work', context={'conversation_kind': 'work'})
    work = ledger.list_threads(limit=2, kind='work')
    assert len(work) == 2
    assert {row['id'] for row in work} >= {old_work_id}
    assert {row['context'].get('conversation_kind') for row in work} == {'work'}
    personal = ledger.list_threads(limit=3, kind='personal')
    assert len(personal) == 3
    assert all(row['context'].get('conversation_kind') != 'work' for row in personal)
    assert len(ledger.list_threads(limit=3)) == 3  # Original unfiltered API unchanged.
    with pytest.raises(ValueError, match='Unsupported conversation kind'):
        ledger.list_threads(kind='project')
