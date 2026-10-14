from __future__ import annotations

from collections import defaultdict
import logging
from threading import RLock
from typing import Any, Callable


logger = logging.getLogger(__name__)
ListenerFailureHandler = Callable[[str, BaseException], None]


class EventBus:
    def __init__(self, listener_failure_handler: ListenerFailureHandler | None = None):
        self._listeners = defaultdict(list)
        self._lock = RLock()
        self._listener_failure_handler = listener_failure_handler
        from core.runtime_state import RuntimeStateAuthority
        self.runtime_state = RuntimeStateAuthority(self)

    def subscribe(self, event: str, callback: Callable[[dict[str, Any]], None]):
        with self._lock:
            self._listeners[event].append(callback)

        def unsubscribe():
            with self._lock:
                listeners = self._listeners.get(event, [])
                if callback in listeners:
                    listeners.remove(callback)
        return unsubscribe

    def set_listener_failure_handler(self, handler: ListenerFailureHandler | None) -> None:
        self._listener_failure_handler = handler

    @staticmethod
    def _turn_request_id():
        try:
            from core.turn_context import current_turn_context
            turn = current_turn_context()
            return str(turn.request_id) if turn is not None and turn.request_id else None
        except Exception:
            logger.debug('Unable to resolve turn request id for event dispatch', exc_info=True)
            return None

    def _report_listener_failure(self, event: str, exc: BaseException) -> None:
        logger.error('Event listener failed for %s', event, exc_info=(type(exc), exc, exc.__traceback__))
        handler = self._listener_failure_handler
        if handler is None:
            return
        try:
            handler(event, exc)
        except Exception:
            logger.error('Event listener failure handler failed for %s', event, exc_info=True)

    def emit(self, event: str, **payload):
        if 'request_id' not in payload:
            request_id = self._turn_request_id()
            if request_id:
                payload = {'request_id': request_id, **payload}
        with self._lock:
            listeners = list(self._listeners.get(event, []))
        msg = {'event': event, **payload}
        for fn in listeners:
            try:
                fn(msg)
            except Exception as exc:
                self._report_listener_failure(event, exc)
