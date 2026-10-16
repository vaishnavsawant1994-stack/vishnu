from __future__ import annotations

import itertools
import queue
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Callable


class InferencePriority(IntEnum):
    """Voice-work admission order from safety-critical to deferrable work.

    The legacy names remain aliases so callers added before the full priority
    model continue to behave the same way.
    """

    EMERGENCY = 0
    LIVE = 10
    AGENT = 20
    NOTIFICATION = 30
    LONG_FORM = 40

    INTERACTIVE = LIVE
    NORMAL = AGENT
    BACKGROUND = LONG_FORM


@dataclass(slots=True)
class _Job:
    future: Future[Any]
    function: Callable[..., Any]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    enqueued_at: float
    timeout_seconds: float | None


class InferenceScheduler:
    """Bounded priority scheduler for voice inference only."""

    def __init__(self, *, max_workers: int = 1, max_pending: int = 32) -> None:
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")
        if max_pending < 1:
            raise ValueError("max_pending must be >= 1")
        self._max_workers = max_workers
        self._queue: queue.PriorityQueue[tuple[int, int, _Job]] = queue.PriorityQueue(maxsize=max_pending)
        self._sequence = itertools.count()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._accepting = False

    @property
    def running(self) -> bool:
        with self._lock:
            return self._accepting

    def start(self) -> None:
        with self._lock:
            if self._accepting:
                return
            self._stop.clear()
            self._accepting = True
            self._threads = [
                threading.Thread(target=self._worker, name=f"vishnu-voice-{index}", daemon=True)
                for index in range(self._max_workers)
            ]
            for thread in self._threads:
                thread.start()

    def submit(
        self,
        function: Callable[..., Any],
        /,
        *args: Any,
        priority: InferencePriority = InferencePriority.AGENT,
        timeout_seconds: float | None = None,
        **kwargs: Any,
    ) -> Future[Any]:
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        with self._lock:
            if not self._accepting:
                raise RuntimeError("voice inference scheduler is not running")
            job = _Job(Future(), function, args, kwargs, time.monotonic(), timeout_seconds)
            try:
                self._queue.put_nowait((int(priority), next(self._sequence), job))
            except queue.Full as exc:
                raise RuntimeError("voice inference queue is full") from exc
            return job.future

    def shutdown(self, *, wait: bool = True, cancel_pending: bool = True) -> None:
        with self._lock:
            if not self._accepting and not self._threads:
                return
            self._accepting = False
            threads = list(self._threads)
            if cancel_pending:
                self._cancel_pending()
            self._stop.set()
        if wait:
            for thread in threads:
                thread.join()
            with self._lock:
                self._threads = []

    def _cancel_pending(self) -> None:
        while True:
            try:
                _, _, job = self._queue.get_nowait()
            except queue.Empty:
                return
            job.future.cancel()
            self._queue.task_done()

    def _worker(self) -> None:
        while True:
            if self._stop.is_set() and self._queue.empty():
                return
            try:
                _, _, job = self._queue.get(timeout=0.05)
            except queue.Empty:
                continue
            try:
                if job.timeout_seconds is not None and time.monotonic() - job.enqueued_at > job.timeout_seconds:
                    job.future.set_exception(TimeoutError("voice inference job expired before execution"))
                    continue
                if not job.future.set_running_or_notify_cancel():
                    continue
                try:
                    result = job.function(*job.args, **job.kwargs)
                except BaseException as exc:
                    job.future.set_exception(exc)
                else:
                    job.future.set_result(result)
            finally:
                self._queue.task_done()
