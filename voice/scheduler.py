"""Priority scheduler for bounded voice inference.

A single worker serializes inference to prevent competing TTS/STT jobs from
contending for the same GPU or accelerator. Higher-priority interactive work
runs before lower-priority long-form work that is still queued.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import IntEnum
from itertools import count
from typing import Any, Generic, TypeVar


T = TypeVar("T")


class VoicePriority(IntEnum):
    EMERGENCY = 0
    LIVE_CONVERSATION = 10
    AGENT_RESPONSE = 20
    NOTIFICATION = 30
    LONG_FORM = 40


class VoiceSchedulerClosedError(RuntimeError):
    """Raised when work is submitted after the scheduler has closed."""


@dataclass(order=True, slots=True)
class _ScheduledItem(Generic[T]):
    priority: int
    sequence: int
    operation: Callable[[], Awaitable[T]] = field(compare=False)
    future: asyncio.Future[T] = field(compare=False)


class VoiceInferenceScheduler:
    """Serialize voice inference while respecting queue priority."""

    def __init__(self) -> None:
        self._queue: asyncio.PriorityQueue[_ScheduledItem[Any]] = asyncio.PriorityQueue()
        self._sequence = count()
        self._worker: asyncio.Task[None] | None = None
        self._closed = False

    @property
    def running(self) -> bool:
        return self._worker is not None and not self._worker.done()

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    async def start(self) -> None:
        if self._closed:
            raise VoiceSchedulerClosedError("voice inference scheduler is closed")
        if not self.running:
            self._worker = asyncio.create_task(self._run(), name="vishnu-voice-inference")

    async def submit(self, priority: VoicePriority, operation: Callable[[], Awaitable[T]]) -> T:
        if self._closed:
            raise VoiceSchedulerClosedError("voice inference scheduler is closed")
        loop = asyncio.get_running_loop()
        future: asyncio.Future[T] = loop.create_future()
        await self._queue.put(
            _ScheduledItem(
                priority=int(priority),
                sequence=next(self._sequence),
                operation=operation,
                future=future,
            )
        )
        return await future

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass

        while not self._queue.empty():
            item = self._queue.get_nowait()
            if not item.future.done():
                item.future.set_exception(VoiceSchedulerClosedError("voice inference scheduler closed"))
            self._queue.task_done()

    async def _run(self) -> None:
        while True:
            item = await self._queue.get()
            try:
                if item.future.cancelled():
                    continue
                result = await item.operation()
                if not item.future.done():
                    item.future.set_result(result)
            except asyncio.CancelledError:
                if not item.future.done():
                    item.future.set_exception(VoiceSchedulerClosedError("voice inference scheduler stopped"))
                raise
            except Exception as exc:  # noqa: BLE001 - provider failures are isolated per job.
                if not item.future.done():
                    item.future.set_exception(exc)
            finally:
                self._queue.task_done()
