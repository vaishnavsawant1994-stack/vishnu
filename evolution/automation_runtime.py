from __future__ import annotations

import threading
from typing import Any

from .code_body import CodeBodyRunStatus


class AutomaticCodeEvolutionRuntime:
    """Automatically implement only already owner-approved evolution handoffs.

    The cadence cannot approve candidates. It skips existing runs, including
    failures, so an unsafe/broken candidate is never retried indefinitely. The
    underlying AutomaticCodeEvolution stops at VERIFIED and cannot review,
    adopt, merge, deploy or activate a Body revision.
    """

    MIN_INTERVAL = 3600

    def __init__(self, automatic, *, handoffs, runtime_epoch, interval_seconds: int = 3600, events=None) -> None:
        self.automatic = automatic
        self.handoffs = handoffs
        self.runtime_epoch = runtime_epoch
        self.interval_seconds = max(self.MIN_INTERVAL, min(24 * 3600, int(interval_seconds)))
        self.events = events
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._cycles = 0
        self._last_error: str | None = None
        self._last_candidate: str | None = None

    @property
    def enabled(self) -> bool:
        return self.automatic is not None and self.handoffs is not None

    def run_once(self, *, limit: int = 3) -> tuple[str, ...]:
        if not self.enabled:
            return ()
        completed: list[str] = []
        try:
            for handoff in self.handoffs.list():
                if len(completed) >= max(1, min(10, int(limit))):
                    break
                existing = self.automatic.code_body.latest(handoff.candidate_id)
                if existing is not None:
                    # VERIFIED/REVIEW_READY/etc are already done, while FAILED
                    # requires explicit owner/operator attention instead of an
                    # unbounded automatic retry loop.
                    continue
                self._last_candidate = handoff.candidate_id
                try:
                    run = self.automatic.run(
                        handoff.candidate_id,
                        runtime_epoch=int(self.runtime_epoch() if callable(self.runtime_epoch) else self.runtime_epoch),
                    )
                    if run.status in {CodeBodyRunStatus.VERIFIED, CodeBodyRunStatus.REVIEW_READY}:
                        completed.append(handoff.candidate_id)
                except Exception as exc:
                    self._last_error = type(exc).__name__
                    if self.events is not None:
                        self.events.emit(
                            'evolution.auto_implementation.failed',
                            candidate_id=handoff.candidate_id,
                            error_type=type(exc).__name__,
                            owner_review_required=True,
                        )
            self._cycles += 1
            if completed:
                self._last_error = None
            return tuple(completed)
        except Exception as exc:
            self._last_error = type(exc).__name__
            return tuple(completed)

    def _loop(self) -> None:
        # Do not mutate source at application boot. The first cadence waits so
        # startup/recovery remains predictable.
        while not self._stop.wait(self.interval_seconds):
            self.run_once()

    def start(self) -> bool:
        if not self.enabled or (self._thread is not None and self._thread.is_alive()):
            return False
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name='vishnu-code-evolution', daemon=True)
        self._thread.start()
        if self.events is not None:
            self.events.emit('evolution.auto_implementation.started', interval_seconds=self.interval_seconds)
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None

    def status(self) -> dict[str, Any]:
        base = self.automatic.status() if self.automatic is not None else {'available': False}
        return {
            **base,
            'enabled': self.enabled,
            'running': bool(self._thread and self._thread.is_alive()),
            'interval_seconds': self.interval_seconds,
            'cycles': self._cycles,
            'last_candidate': self._last_candidate,
            'last_error': self._last_error,
            'failed_runs_retry_automatically': False,
        }
