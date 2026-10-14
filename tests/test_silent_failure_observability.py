from __future__ import annotations

import logging

from core.events import EventBus
from devices.registry import DeviceRegistry


def test_event_bus_reports_listener_failure_and_continues_dispatch(caplog):
    failures = []
    delivered = []
    events = EventBus(listener_failure_handler=lambda event, exc: failures.append((event, type(exc).__name__)))

    def broken(_message):
        raise RuntimeError('listener failed')

    events.subscribe('example', broken)
    events.subscribe('example', lambda message: delivered.append(message['value']))

    with caplog.at_level(logging.ERROR):
        events.emit('example', value=7)

    assert delivered == [7]
    assert failures == [('example', 'RuntimeError')]
    assert 'Event listener failed for example' in caplog.text


def test_event_bus_failure_handler_failure_does_not_break_dispatch(caplog):
    delivered = []

    def broken_handler(_event, _exc):
        raise RuntimeError('handler failed')

    events = EventBus(listener_failure_handler=broken_handler)
    events.subscribe('example', lambda _message: (_ for _ in ()).throw(ValueError('listener failed')))
    events.subscribe('example', lambda message: delivered.append(message['value']))

    with caplog.at_level(logging.ERROR):
        events.emit('example', value=9)

    assert delivered == [9]
    assert 'Event listener failure handler failed for example' in caplog.text


def test_device_revoke_remains_authoritative_when_secondary_cleanup_fails(tmp_path, monkeypatch, caplog):
    import integrations.state as connector_state

    diagnostics = []
    events = EventBus()
    events.subscribe('device.revoke_cleanup_failed', diagnostics.append)
    registry = DeviceRegistry(tmp_path / 'devices.sqlite3', events=events)
    device, _token = registry.enroll('Phone', 'android')

    # The connector store must exist for the secondary cleanup path to run.
    (tmp_path / 'connectors.sqlite3').touch()

    class BrokenConnectorStateStore:
        def __init__(self, _path):
            pass

        def invalidate_device(self, _device_id):
            raise RuntimeError('secondary cleanup failed')

    monkeypatch.setattr(connector_state, 'ConnectorStateStore', BrokenConnectorStateStore)

    with caplog.at_level(logging.ERROR):
        assert registry.revoke(device['id']) is True

    assert registry.is_active(device['id']) is False
    assert len(diagnostics) == 1
    assert diagnostics[0]['device_id'] == device['id']
    assert diagnostics[0]['cleanup'] == 'connector_transactions'
    assert diagnostics[0]['error_type'] == 'RuntimeError'
    assert 'connector transaction cleanup failed' in caplog.text
