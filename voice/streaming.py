from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterator

from voice.intelligence import chunk_text_for_voice


class VoiceStreamState(str, Enum):
    STARTED = "started"
    CHUNK = "chunk"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class VoiceStreamProgress:
    state: VoiceStreamState
    completed_chunks: int
    total_chunks: int
    completed_chars: int
    total_chars: int

    @property
    def fraction(self) -> float:
        if self.total_chars <= 0:
            return 1.0
        return min(1.0, self.completed_chars / self.total_chars)


class ProgressiveVoiceStreamer:
    """Application-level synthesis streaming with privacy-safe progress events."""

    def __init__(self, service, *, events=None) -> None:
        self.service = service
        self.events = events

    def synthesize(
        self,
        text: str,
        *,
        max_chars: int = 320,
        cancelled: Callable[[], bool] | None = None,
        progress: Callable[[VoiceStreamProgress], None] | None = None,
        **synthesis_kwargs,
    ) -> Iterator:
        chunks = tuple(chunk_text_for_voice(text, max_chars=max_chars))
        total_chars = sum(len(chunk) for chunk in chunks)
        completed_chars = 0
        completed_chunks = 0
        self._report(
            VoiceStreamProgress(
                VoiceStreamState.STARTED,
                completed_chunks,
                len(chunks),
                completed_chars,
                total_chars,
            ),
            progress,
        )
        for chunk in chunks:
            if cancelled is not None and cancelled():
                self._report(
                    VoiceStreamProgress(
                        VoiceStreamState.CANCELLED,
                        completed_chunks,
                        len(chunks),
                        completed_chars,
                        total_chars,
                    ),
                    progress,
                )
                return
            result = self.service.synthesize(chunk, **synthesis_kwargs)
            if cancelled is not None and cancelled():
                self._report(
                    VoiceStreamProgress(
                        VoiceStreamState.CANCELLED,
                        completed_chunks,
                        len(chunks),
                        completed_chars,
                        total_chars,
                    ),
                    progress,
                )
                return
            completed_chunks += 1
            completed_chars += len(chunk)
            self._report(
                VoiceStreamProgress(
                    VoiceStreamState.CHUNK,
                    completed_chunks,
                    len(chunks),
                    completed_chars,
                    total_chars,
                ),
                progress,
            )
            yield result
        self._report(
            VoiceStreamProgress(
                VoiceStreamState.COMPLETED,
                completed_chunks,
                len(chunks),
                completed_chars,
                total_chars,
            ),
            progress,
        )

    def _report(
        self,
        item: VoiceStreamProgress,
        callback: Callable[[VoiceStreamProgress], None] | None,
    ) -> None:
        if callback is not None:
            callback(item)
        if self.events is not None:
            self.events.emit(
                "voice.streaming.progress",
                state=item.state.value,
                completed_chunks=item.completed_chunks,
                total_chunks=item.total_chunks,
                completed_chars=item.completed_chars,
                total_chars=item.total_chars,
                fraction=item.fraction,
            )
