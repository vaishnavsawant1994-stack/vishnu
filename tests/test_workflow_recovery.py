import sqlite3
import threading
import time
from security.approvals import ApprovalManager

from agent.executor import ExecutionCancelled
from automation.engine import AutomationEngine


class ImmediateExecutor:
    def chat(self, prompt, cancel_event=None):
        return f'ok:{prompt}'


class BlockingExecutor:
    def __init__(self):
        self.started = threading.Event()

    def chat(self, prompt, cancel_event=None):
        self.started.set()
        while not cancel_event.wait(.01):
            pass
        raise ExecutionCancelled('cancelled')


def test_restart_requires_owner_review_then_resumes_from_checkpoint(tmp_path):
    path = tmp_path / 'workflows.sqlite3'
    first = AutomationEngine(path, executor=ImmediateExecutor())
    workflow_id = first.create_workflow('Recoverable', {'type': 'manual'}, [
        {'kind': 'set', 'key': 'one', 'value': 1},
        {'kind': 'set', 'key': 'two', 'value': 2},
    ])
    run_id = first.run_workflow(workflow_id)
    with sqlite3.connect(path) as con:
        con.execute(
            "UPDATE workflow_runs SET status='running',current_step=1,completed_at=NULL WHERE id=?",
            (run_id,),
        )

    reopened = AutomationEngine(path, executor=ImmediateExecutor())

    assert reopened.runs()[0]['status'] == 'recovery_required'
    result = reopened.resume_run(run_id, background=False)
    assert result['checkpoint'] == 1
    assert reopened.runs()[0]['status'] == 'completed'


def test_owner_cancellation_stops_active_workflow_cooperatively(tmp_path):
    executor = BlockingExecutor()
    engine = AutomationEngine(tmp_path / 'workflows.sqlite3', executor=executor)
    workflow_id = engine.create_workflow('Cancelable', {'type': 'manual'}, [
        {'kind': 'prompt', 'prompt': 'wait', 'retries': 0},
    ])
    run_id = engine.run_workflow(workflow_id, background=True)
    assert executor.started.wait(2)

    result = engine.cancel_run(run_id)
    assert result['status'] == 'cancelled'
    for _ in range(100):
        if engine.runs()[0]['status'] == 'cancelled':
            break
        time.sleep(.01)
    assert engine.runs()[0]['status'] == 'cancelled'


def test_cancelled_run_cannot_be_overwritten_as_completed(tmp_path):
    class SlowReturnExecutor:
        def __init__(self): self.started = threading.Event(); self.release = threading.Event()
        def chat(self, prompt, cancel_event=None):
            self.started.set(); self.release.wait(2); return 'late result'

    executor = SlowReturnExecutor();engine = AutomationEngine(tmp_path/'race.sqlite3',executor=executor)
    workflow_id=engine.create_workflow('Race safe',{'type':'manual'},[{'kind':'prompt','prompt':'wait','retries':0}])
    run_id=engine.run_workflow(workflow_id,background=True);assert executor.started.wait(2)
    engine.cancel_run(run_id);executor.release.set();time.sleep(.05)
    assert engine._run(run_id)['status']=='cancelled'


def test_expired_tool_approval_closes_waiting_workflow(tmp_path):
    class ApprovalAwareExecutor(ImmediateExecutor):
        pass

    executor = ApprovalAwareExecutor()
    executor.approvals = ApprovalManager(path=tmp_path / 'approvals.sqlite3', ttl_seconds=1)
    engine = AutomationEngine(tmp_path / 'approval-expiry.sqlite3', executor=executor)
    workflow_id = engine.create_workflow('Expires', {'type': 'manual'}, [
        {'kind': 'set', 'key': 'done', 'value': True},
    ])
    run_id = engine.run_workflow(workflow_id)
    ticket = executor.approvals.create('execution-1', 'write_tool', {'value': 'x'})
    with engine._con() as con:
        con.execute("UPDATE workflow_runs SET status='waiting_approval',pending_approval_id=?,completed_at=NULL WHERE id=?",
                    (ticket.id, run_id))
    time.sleep(1.05)
    assert engine.runs()[0]['status'] == 'cancelled'
    assert engine._run(run_id)['pending_approval_id'] is None
    assert engine._run(run_id)['error'] == 'approval expired'


def test_workflow_update_persists_valid_configuration_and_rejects_invalid_input(tmp_path):
    path = tmp_path / 'workflows.sqlite3'
    engine = AutomationEngine(path, executor=ImmediateExecutor())
    workflow_id = engine.create_workflow(
        'First title', {'type': 'manual'}, [{'kind': 'prompt', 'prompt': 'old step'}]
    )
    updated = engine.update_workflow(
        workflow_id,
        title='Updated title',
        trigger={'type': 'schedule', 'timezone': 'Asia/Kolkata'},
        steps=[{'kind': 'prompt', 'prompt': 'new step'}],
        next_run_at='2026-10-07T08:00:00+05:30',
    )
    assert updated['title'] == 'Updated title'
    assert updated['trigger']['timezone'] == 'Asia/Kolkata'
    assert updated['steps'][0]['prompt'] == 'new step'
    assert AutomationEngine(path, executor=ImmediateExecutor()).workflow(workflow_id)['title'] == 'Updated title'
    try:
        engine.update_workflow(
            workflow_id, title='Invalid', trigger={'type': 'schedule'},
            steps=[{'kind': 'prompt', 'prompt': 'step'}],
        )
    except ValueError as exc:
        assert 'next_run_at' in str(exc)
    else:
        raise AssertionError('schedule without next run must be rejected')
    assert engine.workflow(workflow_id)['title'] == 'Updated title'


def test_workflow_recurring_weekday_schedule_uses_timezone_and_weekdays_only():
    from datetime import datetime, timezone

    trigger = {
        'type': 'schedule', 'repeat': 'weekdays', 'timezone': 'Asia/Kolkata', 'local_time': '08:00'
    }
    after = datetime.fromisoformat('2026-10-09T03:00:00+00:00')  # Friday, 8:30 AM IST
    next_run = datetime.fromisoformat(AutomationEngine._next_recurring_run(trigger, after))
    assert next_run.astimezone(timezone.utc).isoformat() == '2026-10-12T02:30:00+00:00'


def test_workflow_update_persists_review_policy(tmp_path):
    engine = AutomationEngine(tmp_path / 'workflows.sqlite3', executor=ImmediateExecutor())
    workflow_id = engine.create_workflow(
        'Review policy', {'type': 'manual'}, [{'kind': 'prompt', 'prompt': 'summarize'}]
    )
    updated = engine.update_workflow(
        workflow_id, title='Review policy',
        trigger={'type': 'manual', 'policy': {'approval_threshold': 'read_only'}},
        steps=[{'kind': 'prompt', 'prompt': 'summarize'}],
    )
    assert updated['policy']['approval_threshold'] == 'read_only'
    try:
        engine.update_workflow(
            workflow_id, title='Review policy',
            trigger={'type': 'manual', 'policy': {'approval_threshold': 'destructive'}},
            steps=[{'kind': 'prompt', 'prompt': 'summarize'}],
        )
    except ValueError as exc:
        assert 'read_only or consequential' in str(exc)
    else:
        raise AssertionError('weaker approval threshold must be rejected')


def test_workflow_create_persists_review_policy(tmp_path):
    engine = AutomationEngine(tmp_path / 'workflows.sqlite3', executor=ImmediateExecutor())
    workflow_id = engine.create_workflow(
        'Review on create', {'type': 'manual'},
        [{'kind': 'prompt', 'prompt': 'summarize'}],
        policy={'approval_threshold': 'read_only'},
    )
    assert engine.workflow(workflow_id)['policy']['approval_threshold'] == 'read_only'
