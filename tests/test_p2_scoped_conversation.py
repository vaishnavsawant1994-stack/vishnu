"""Phase 2: Project/Workspace AI grounding must not read unscoped stores or execute tools."""
from __future__ import annotations

from agent.executor import AgentExecutor
from core.personal_ai_runtime import CanonicalTurnRuntime
from devices.continuity import ContinuityService


class StubMemory:
    def __init__(self):
        self.entries = []

    def add_message(self, role, content, *, conversation_id=None, device_id=None):
        self.entries.append({"role": role, "content": content, "conversation_id": conversation_id})

    def recent_messages(self, limit, conversation_id=None):
        return [
            {"role": row["role"], "content": row["content"]}
            for row in self.entries if row["conversation_id"] == conversation_id
        ][-limit:]


class GuardedModels:
    def __init__(self):
        self.turns = []

    def chat(self, text, **kwargs):
        self.turns.append((text, kwargs))
        return "Scoped answer, no external actions."

    def json(self, *args, **kwargs):
        raise AssertionError("Scoped turn must not call the planning model")


class ForbiddenSources:
    def search(self, *args, **kwargs):
        raise AssertionError("General Knowledge source was accessed")

    def context(self, *args, **kwargs):
        raise AssertionError("Global Second Brain was accessed")


class ForbiddenTools:
    def schema_text(self):
        raise AssertionError("Tool registry was read from a scoped conversation")


class Events:
    def __init__(self):
        self.rows = []

    def emit(self, name, **kwargs):
        self.rows.append((name, kwargs))


def test_scoped_turn_uses_only_verified_metadata_and_own_history():
    memory, models, events = StubMemory(), GuardedModels(), Events()
    executor = AgentExecutor(
        models=models, tools=ForbiddenTools(), memory=memory, events=events,
        knowledge=ForbiddenSources(), second_brain=ForbiddenSources(),
        identity_context_provider=lambda: (_ for _ in ()).throw(
            AssertionError("Global personal identity context was accessed")),
    )
    result = executor.chat(
        "What is finished?", conversation_id="project-1",
        scoped_context_only=True,
        verified_context="Project: Verified Work\nGoal: Patient CRM",
    )
    assert result == "Scoped answer, no external actions."
    assert len(models.turns) == 1
    text, params = models.turns[0]
    assert text == "What is finished?"
    assert "Project: Verified Work" in params["system"]
    assert "No global memory or knowledge was searched" in params["system"]
    assert params["private_context"] == ""
    assert params["history"] == []
    assert [row["content"] for row in memory.entries] == [
        "What is finished?", "Scoped answer, no external actions."
    ]
    assert any(name == "conversation.assistant" for name, _ in events.rows)


def test_scoped_turn_rejects_missing_server_grounding_before_writing():
    memory = StubMemory()
    executor = AgentExecutor(
        models=GuardedModels(), tools=ForbiddenTools(), memory=memory,
        events=Events(), second_brain=ForbiddenSources(),
        knowledge=ForbiddenSources(),
    )
    import pytest

    with pytest.raises(ValueError, match="verified server context"):
        executor.chat("Hello", conversation_id="x", scoped_context_only=True)
    assert memory.entries == []


def test_scoped_runtime_skips_autonomous_p10_selector(tmp_path):
    class UnavailableSelector:
        def select(self, *args, **kwargs):
            raise AssertionError("Scoped request entered unscoped P10")

    continuity = ContinuityService(tmp_path / "continuity.sqlite3")
    runtime = CanonicalTurnRuntime(
        executor=object(), continuity=continuity, path=tmp_path / "turns.sqlite3",
    )
    runtime.p10_selector = UnavailableSelector()
    assert runtime._orchestrate(
        "Please execute arbitrary actions", request_id="scoped-1",
        owner_id="owner", device_id="d1", session_id="s1",
        privacy_level="normal", risk_level="low",
        kwargs={"scoped_context_only": True},
    ) is None
