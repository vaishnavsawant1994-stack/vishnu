from __future__ import annotations

import queue
import shutil
import tempfile
import threading
from enum import Enum
from pathlib import Path

from voice.config import VoiceRuntimeSettings
from voice.providers import (
    SpeechToTextProvider,
    SpeechToTextRequest,
    SpeechToTextResult,
    TextToSpeechProvider,
    TextToSpeechRequest,
    TextToSpeechResult,
)
from voice.scheduler import InferencePriority, InferenceScheduler
from voice.sensorium import SpeechIntent, SpeechIntentBridge


class VoiceRuntimeState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"


class VoiceRuntime:
    """Streaming audio compatibility layer plus an isolated voice inference runtime.

    Existing listening and ``speak`` methods intentionally remain independent of
    the new inference feature flag. The provider runtime is additive and must be
    explicitly enabled before it allocates workers or an ephemeral workspace.
    """

    def __init__(
        self,
        recorder=None,
        tts=None,
        events=None,
        *,
        settings: VoiceRuntimeSettings | None = None,
        stt_provider: SpeechToTextProvider | None = None,
        tts_provider: TextToSpeechProvider | None = None,
        speech_intent_bridge: SpeechIntentBridge | None = None,
    ):
        self.recorder = recorder
        self.tts = tts
        self.events = events
        self.frames = queue.Queue(maxsize=128)
        self._running = False

        self.settings = settings or VoiceRuntimeSettings.from_env()
        self.stt_provider = stt_provider
        self.tts_provider = tts_provider
        self.speech_intents = speech_intent_bridge or SpeechIntentBridge(events=events)
        self._state = VoiceRuntimeState.STOPPED
        self._state_lock = threading.RLock()
        self._workspace: Path | None = None
        self._scheduler: InferenceScheduler | None = None

    @property
    def state(self) -> VoiceRuntimeState:
        with self._state_lock:
            return self._state

    @property
    def workspace(self) -> Path | None:
        with self._state_lock:
            return self._workspace

    def start(self) -> bool:
        """Start isolated provider execution when the feature is enabled."""
        with self._state_lock:
            if not self.settings.enabled:
                return False
            if self._state is VoiceRuntimeState.RUNNING:
                return True
            if self._state not in {VoiceRuntimeState.STOPPED, VoiceRuntimeState.FAILED}:
                raise RuntimeError(f"cannot start voice runtime while {self._state.value}")
            self._state = VoiceRuntimeState.STARTING
            try:
                root = self.settings.workspace_root
                if root is not None:
                    root.mkdir(parents=True, exist_ok=True)
                self._workspace = Path(tempfile.mkdtemp(prefix="vishnu-voice-", dir=root))
                self._scheduler = InferenceScheduler(
                    max_workers=self.settings.workers,
                    max_pending=self.settings.max_pending_jobs,
                )
                self._scheduler.start()
                self._state = VoiceRuntimeState.RUNNING
                return True
            except BaseException:
                self._cleanup_locked()
                self._state = VoiceRuntimeState.FAILED
                raise

    def stop(self) -> None:
        with self._state_lock:
            if self._state is VoiceRuntimeState.STOPPED:
                return
            self._state = VoiceRuntimeState.STOPPING
            self._cleanup_locked()
            self._state = VoiceRuntimeState.STOPPED

    def restart(self) -> bool:
        self.stop()
        return self.start()

    def transcribe(
        self,
        request: SpeechToTextRequest,
        *,
        timeout_seconds: float | None = None,
        priority: InferencePriority = InferencePriority.LIVE,
    ) -> SpeechToTextResult:
        provider = self.stt_provider
        if provider is None:
            raise RuntimeError("no speech-to-text provider configured")
        future = self._submit(
            provider.transcribe,
            request,
            timeout_seconds=timeout_seconds,
            priority=priority,
        )
        result = future.result(timeout=timeout_seconds)
        if not isinstance(result, SpeechToTextResult):
            raise TypeError("speech-to-text provider returned an invalid result")
        return result

    def transcribe_intent(
        self,
        request: SpeechToTextRequest,
        *,
        timeout_seconds: float | None = None,
        priority: InferencePriority = InferencePriority.LIVE,
        source: str = "microphone",
        device_id: str | None = None,
        audio_features: dict | None = None,
    ) -> SpeechIntent:
        result = self.transcribe(
            request,
            timeout_seconds=timeout_seconds,
            priority=priority,
        )
        return self.speech_intents.from_transcription(
            result,
            source=source,
            device_id=device_id,
            audio_features=audio_features,
        )

    def synthesize(
        self,
        request: TextToSpeechRequest,
        *,
        timeout_seconds: float | None = None,
        priority: InferencePriority = InferencePriority.LIVE,
    ) -> TextToSpeechResult:
        provider = self.tts_provider
        if provider is None:
            raise RuntimeError("no text-to-speech provider configured")
        future = self._submit(
            provider.synthesize,
            request,
            timeout_seconds=timeout_seconds,
            priority=priority,
        )
        result = future.result(timeout=timeout_seconds)
        if not isinstance(result, TextToSpeechResult):
            raise TypeError("text-to-speech provider returned an invalid result")
        return result

    def _submit(
        self,
        function,
        request,
        *,
        timeout_seconds: float | None,
        priority: InferencePriority,
    ):
        with self._state_lock:
            if self._state is not VoiceRuntimeState.RUNNING or self._scheduler is None:
                raise RuntimeError("voice provider runtime is not running")
            return self._scheduler.submit(
                function,
                request,
                priority=priority,
                timeout_seconds=timeout_seconds,
            )

    def _cleanup_locked(self) -> None:
        scheduler = self._scheduler
        self._scheduler = None
        if scheduler is not None:
            scheduler.shutdown(wait=True, cancel_pending=True)
        workspace = self._workspace
        self._workspace = None
        if workspace is not None:
            shutil.rmtree(workspace, ignore_errors=False)

    # Existing streaming API retained for compatibility.
    def start_listening(self):
        self._running = True
        if self.events:
            self.events.emit("state", state="listening")

    def stop_listening(self):
        self._running = False
        if self.events:
            self.events.emit("state", state="idle")

    def push_pcm(self, frame: bytes):
        if not self._running:
            return False
        try:
            self.frames.put_nowait(frame)
            return True
        except queue.Full:
            return False

    def speak(self, text: str):
        if self.events:
            self.events.emit("state", state="speaking")
        if self.tts:
            self.tts.speak(text)
        if self.events:
            self.events.emit("state", state="idle")
