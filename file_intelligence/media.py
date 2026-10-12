from __future__ import annotations

import io
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .models import ExtractionMethod, SourceReference, VishnuBlock
from .ocr import OcrUnavailable
from .readers import ContentReadError, read_image


class MediaUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MediaProbe:
    duration: float | None = None
    has_audio: bool = False
    has_video: bool = False
    format_name: str | None = None
    sample_rate: int | None = None
    channels: int | None = None
    width: int | None = None
    height: int | None = None

    def as_dict(self) -> dict:
        return {
            key: value
            for key, value in {
                "duration": self.duration,
                "has_audio": self.has_audio,
                "has_video": self.has_video,
                "format_name": self.format_name,
                "sample_rate": self.sample_rate,
                "channels": self.channels,
                "width": self.width,
                "height": self.height,
            }.items()
            if value is not None
        }


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    text: str
    start: float
    end: float
    confidence: float | None = None
    language: str | None = None
    speaker: str | None = None
    metadata: dict | None = None

    def as_dict(self) -> dict:
        return {
            key: value
            for key, value in {
                "text": self.text,
                "start": self.start,
                "end": self.end,
                "confidence": self.confidence,
                "language": self.language,
                "speaker": self.speaker,
                "metadata": self.metadata or None,
            }.items()
            if value is not None
        }


class SpeechToTextProvider(Protocol):
    name: str
    external: bool

    def transcribe(
        self,
        wav_bytes: bytes,
        *,
        filename: str = "audio.wav",
        language: str | None = None,
    ) -> list[dict]: ...


def _bounded_confidence(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return max(0.0, min(1.0, number))


def _seconds(value) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


class WhisperCppProvider:
    """Offline whisper.cpp provider. A local model file is always required."""

    external = False

    def __init__(
        self,
        *,
        model_path: str | os.PathLike,
        command: str | None = None,
        timeout_seconds: int = 900,
        threads: int | None = None,
    ):
        self.model_path = Path(model_path).expanduser().resolve()
        if not self.model_path.is_file():
            raise MediaUnavailable("whisper.cpp requires an existing local model file")
        self.command = command
        self.timeout_seconds = max(10, int(timeout_seconds))
        self.threads = max(1, int(threads)) if threads else None
        self.name = f"whisper.cpp:{self.model_path.name}"

    def _executable(self) -> str:
        if self.command:
            candidate = Path(self.command).expanduser()
            if candidate.is_file():
                return str(candidate.resolve())
            resolved = shutil.which(self.command)
            if resolved:
                return resolved
        for name in ("whisper-cli", "main"):
            resolved = shutil.which(name)
            if resolved:
                return resolved
        raise MediaUnavailable("whisper.cpp executable was not found locally")

    @staticmethod
    def _parse_json(payload: dict) -> list[dict]:
        candidates = payload.get("transcription") or payload.get("segments") or payload.get("result") or []
        if isinstance(candidates, dict):
            candidates = candidates.get("segments") or candidates.get("transcription") or []
        result: list[dict] = []
        for index, item in enumerate(candidates if isinstance(candidates, list) else []):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or item.get("content") or "").strip()
            if not text:
                continue
            offsets = item.get("offsets") if isinstance(item.get("offsets"), dict) else {}
            timestamps = item.get("timestamps") if isinstance(item.get("timestamps"), dict) else {}
            start = item.get("start", item.get("t0", offsets.get("from", timestamps.get("from", 0.0))))
            end = item.get("end", item.get("t1", offsets.get("to", timestamps.get("to", start))))
            # whisper.cpp JSON may express offsets in milliseconds.
            if isinstance(offsets, dict) and ("from" in offsets or "to" in offsets):
                try:
                    start = float(start) / 1000.0
                    end = float(end) / 1000.0
                except (TypeError, ValueError):
                    pass
            result.append(
                {
                    "text": text,
                    "start": _seconds(start),
                    "end": max(_seconds(start), _seconds(end)),
                    "confidence": _bounded_confidence(item.get("confidence") or item.get("probability")),
                    "metadata": {"segment": index + 1},
                }
            )
        return result

    def transcribe(self, wav_bytes: bytes, *, filename: str = "audio.wav", language: str | None = None) -> list[dict]:
        executable = self._executable()
        with tempfile.TemporaryDirectory(prefix="vishnu-whisper-") as temp_dir:
            temp = Path(temp_dir)
            wav_path = temp / "input.wav"
            output_prefix = temp / "transcript"
            wav_path.write_bytes(wav_bytes)
            command = [
                executable,
                "-m", str(self.model_path),
                "-f", str(wav_path),
                "-oj",
                "-of", str(output_prefix),
                "-np",
            ]
            if language:
                command.extend(["-l", str(language)])
            if self.threads:
                command.extend(["-t", str(self.threads)])
            try:
                completed = subprocess.run(
                    command,
                    shell=False,
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=self.timeout_seconds,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise MediaUnavailable("Local whisper.cpp transcription failed safely") from exc
            if completed.returncode != 0:
                raise MediaUnavailable("Local whisper.cpp transcription returned an error")
            json_path = output_prefix.with_suffix(".json")
            if not json_path.is_file():
                raise MediaUnavailable("Local whisper.cpp did not produce JSON output")
            try:
                payload = json.loads(json_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise MediaUnavailable("Local whisper.cpp JSON output was invalid") from exc
        return self._parse_json(payload)


class FasterWhisperProvider:
    """Optional local CTranslate2 provider. It refuses remote model identifiers."""

    external = False

    def __init__(
        self,
        *,
        model_path: str | os.PathLike,
        device: str = "auto",
        compute_type: str = "default",
    ):
        self.model_path = Path(model_path).expanduser().resolve()
        if not self.model_path.exists():
            raise MediaUnavailable("faster-whisper requires an existing local model directory")
        self.device = str(device)
        self.compute_type = str(compute_type)
        self.name = f"faster-whisper:{self.model_path.name}"
        self._model = None

    def _runtime(self):
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise MediaUnavailable("faster-whisper is not installed locally") from exc
        try:
            self._model = WhisperModel(
                str(self.model_path),
                device=self.device,
                compute_type=self.compute_type,
                local_files_only=True,
            )
        except Exception as exc:
            raise MediaUnavailable("Local faster-whisper model could not be loaded") from exc
        return self._model

    def transcribe(self, wav_bytes: bytes, *, filename: str = "audio.wav", language: str | None = None) -> list[dict]:
        model = self._runtime()
        with tempfile.TemporaryDirectory(prefix="vishnu-faster-whisper-") as temp_dir:
            wav_path = Path(temp_dir) / "input.wav"
            wav_path.write_bytes(wav_bytes)
            try:
                segments, info = model.transcribe(str(wav_path), language=language, word_timestamps=True)
                result = []
                detected_language = getattr(info, "language", None)
                for index, segment in enumerate(segments, 1):
                    text = str(getattr(segment, "text", "") or "").strip()
                    if not text:
                        continue
                    average_log_probability = getattr(segment, "avg_logprob", None)
                    confidence = None
                    if average_log_probability is not None:
                        try:
                            confidence = max(0.0, min(1.0, math.exp(float(average_log_probability))))
                        except (TypeError, ValueError, OverflowError):
                            confidence = None
                    result.append(
                        {
                            "text": text,
                            "start": _seconds(getattr(segment, "start", 0.0)),
                            "end": _seconds(getattr(segment, "end", 0.0)),
                            "confidence": confidence,
                            "language": detected_language,
                            "metadata": {"segment": index},
                        }
                    )
            except Exception as exc:
                raise MediaUnavailable("Local faster-whisper transcription failed safely") from exc
        return result


class LocalMediaDecoder:
    """Bounded local FFmpeg/FFprobe adapter with a native WAV fast path."""

    name = "vishnu-local-media/1"

    def __init__(self, *, ffmpeg: str | None = None, ffprobe: str | None = None, timeout_seconds: int = 300):
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.timeout_seconds = max(10, int(timeout_seconds))

    @staticmethod
    def _wav_probe(data: bytes) -> MediaProbe | None:
        try:
            with wave.open(io.BytesIO(data), "rb") as stream:
                frames = stream.getnframes()
                rate = stream.getframerate()
                channels = stream.getnchannels()
                duration = frames / rate if rate else 0.0
                return MediaProbe(
                    duration=float(duration),
                    has_audio=True,
                    has_video=False,
                    format_name="wav",
                    sample_rate=int(rate),
                    channels=int(channels),
                )
        except (wave.Error, EOFError):
            return None

    def _binary(self, configured: str | None, fallback: str) -> str:
        if configured:
            candidate = Path(configured).expanduser()
            if candidate.is_file():
                return str(candidate.resolve())
            resolved = shutil.which(configured)
            if resolved:
                return resolved
        resolved = shutil.which(fallback)
        if resolved:
            return resolved
        raise MediaUnavailable(f"Local {fallback} executable was not found")

    def probe(self, data: bytes, *, filename: str) -> MediaProbe:
        native = self._wav_probe(data)
        if native:
            return native
        suffix = Path(filename).suffix or ".bin"
        with tempfile.TemporaryDirectory(prefix="vishnu-media-probe-") as temp_dir:
            source = Path(temp_dir) / f"source{suffix}"
            source.write_bytes(data)
            command = [
                self._binary(self.ffprobe, "ffprobe"),
                "-v", "error",
                "-show_streams",
                "-show_format",
                "-of", "json",
                str(source),
            ]
            try:
                completed = subprocess.run(
                    command,
                    shell=False,
                    check=False,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=self.timeout_seconds,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise MediaUnavailable("Local media probe failed safely") from exc
            if completed.returncode != 0:
                raise MediaUnavailable("Local media probe returned an error")
            try:
                payload = json.loads(completed.stdout.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise MediaUnavailable("Local media probe output was invalid") from exc
        streams = payload.get("streams") if isinstance(payload, dict) else []
        streams = streams if isinstance(streams, list) else []
        audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
        video = next((item for item in streams if item.get("codec_type") == "video"), None)
        format_data = payload.get("format") if isinstance(payload.get("format"), dict) else {}
        duration = format_data.get("duration")
        if duration is None:
            duration = next((item.get("duration") for item in streams if item.get("duration") is not None), None)
        return MediaProbe(
            duration=_seconds(duration) if duration is not None else None,
            has_audio=audio is not None,
            has_video=video is not None,
            format_name=str(format_data.get("format_name") or "") or None,
            sample_rate=int(audio.get("sample_rate")) if audio and str(audio.get("sample_rate") or "").isdigit() else None,
            channels=int(audio.get("channels")) if audio and str(audio.get("channels") or "").isdigit() else None,
            width=int(video.get("width")) if video and str(video.get("width") or "").isdigit() else None,
            height=int(video.get("height")) if video and str(video.get("height") or "").isdigit() else None,
        )

    def to_wav(self, data: bytes, *, filename: str) -> bytes:
        native = self._wav_probe(data)
        if native and native.sample_rate == 16000 and native.channels == 1:
            try:
                with wave.open(io.BytesIO(data), "rb") as stream:
                    if stream.getsampwidth() == 2:
                        return data
            except wave.Error:
                pass
        suffix = Path(filename).suffix or ".bin"
        with tempfile.TemporaryDirectory(prefix="vishnu-media-audio-") as temp_dir:
            source = Path(temp_dir) / f"source{suffix}"
            output = Path(temp_dir) / "audio.wav"
            source.write_bytes(data)
            command = [
                self._binary(self.ffmpeg, "ffmpeg"),
                "-nostdin", "-v", "error", "-y",
                "-i", str(source),
                "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le",
                str(output),
            ]
            try:
                completed = subprocess.run(command, shell=False, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=self.timeout_seconds)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise MediaUnavailable("Local audio normalization failed safely") from exc
            if completed.returncode != 0 or not output.is_file():
                raise MediaUnavailable("Local audio normalization returned an error")
            return output.read_bytes()

    def keyframes(self, data: bytes, *, filename: str, duration: float | None, max_frames: int = 12) -> list[tuple[float, bytes]]:
        if not duration or duration <= 0:
            return []
        count = max(1, min(int(max_frames), 24))
        if duration <= 5:
            timestamps = [duration / 2.0]
        else:
            interval = max(5.0, duration / (count + 1))
            timestamps = [min(duration - 0.1, interval * index) for index in range(1, count + 1) if interval * index < duration]
        suffix = Path(filename).suffix or ".bin"
        frames: list[tuple[float, bytes]] = []
        with tempfile.TemporaryDirectory(prefix="vishnu-video-frames-") as temp_dir:
            source = Path(temp_dir) / f"source{suffix}"
            source.write_bytes(data)
            executable = self._binary(self.ffmpeg, "ffmpeg")
            for index, timestamp in enumerate(timestamps, 1):
                output = Path(temp_dir) / f"frame-{index:03d}.png"
                command = [
                    executable, "-nostdin", "-v", "error", "-y",
                    "-ss", f"{timestamp:.3f}", "-i", str(source),
                    "-frames:v", "1", "-vf", "scale='min(1600,iw)':-2", str(output),
                ]
                try:
                    completed = subprocess.run(command, shell=False, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=self.timeout_seconds)
                except (OSError, subprocess.TimeoutExpired):
                    continue
                if completed.returncode == 0 and output.is_file() and output.stat().st_size:
                    frames.append((float(timestamp), output.read_bytes()))
        return frames


def discover_local_speech_provider() -> SpeechToTextProvider | None:
    """Opt-in local discovery. Environment values must resolve to existing local model paths."""
    model = str(os.getenv("VISHNU_WHISPER_MODEL") or "").strip()
    if not model:
        return None
    path = Path(model).expanduser()
    if not path.exists():
        return None
    backend = str(os.getenv("VISHNU_WHISPER_BACKEND") or "whisper.cpp").strip().lower()
    if backend in {"faster-whisper", "faster_whisper"}:
        return FasterWhisperProvider(model_path=path)
    return WhisperCppProvider(model_path=path, command=os.getenv("VISHNU_WHISPER_CPP") or None)


def _transcript_blocks(segments: list[dict]) -> list[VishnuBlock]:
    blocks: list[VishnuBlock] = []
    for index, item in enumerate(segments, 1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        start = _seconds(item.get("start"))
        end = max(start, _seconds(item.get("end")))
        metadata = dict(item.get("metadata") or {})
        metadata.update({"segment": metadata.get("segment", index), "language": item.get("language"), "speaker": item.get("speaker")})
        metadata = {key: value for key, value in metadata.items() if value is not None}
        blocks.append(
            VishnuBlock(
                "transcript",
                text,
                SourceReference(timestamp_start=start, timestamp_end=end),
                ExtractionMethod.SPEECH,
                _bounded_confidence(item.get("confidence")),
                metadata=metadata,
            )
        )
    return blocks


def read_audio(
    data: bytes,
    *,
    filename: str,
    speech_provider: SpeechToTextProvider | None,
    decoder: LocalMediaDecoder,
    language: str | None = None,
) -> tuple[list[VishnuBlock], list[str], str]:
    warnings: list[str] = []
    try:
        probe = decoder.probe(data, filename=filename)
    except MediaUnavailable as exc:
        probe = MediaProbe(has_audio=True)
        warnings.append(str(exc))
    blocks = [
        VishnuBlock(
            "media_metadata",
            "Audio media",
            SourceReference(timestamp_start=0.0, timestamp_end=probe.duration),
            ExtractionMethod.MEDIA,
            data=probe.as_dict(),
            metadata={"media_type": "audio"},
        )
    ]
    if speech_provider is None:
        warnings.append("No local speech-to-text model is configured; audio metadata was indexed without a transcript")
        return blocks, warnings, decoder.name
    if bool(getattr(speech_provider, "external", False)):
        raise MediaUnavailable("External speech-to-text is disabled by default")
    try:
        wav_bytes = decoder.to_wav(data, filename=filename)
        segments = speech_provider.transcribe(wav_bytes, filename=filename, language=language)
        blocks.extend(_transcript_blocks(segments))
    except MediaUnavailable as exc:
        warnings.append(str(exc))
    if len(blocks) == 1:
        warnings.append("No speech transcript was produced")
    return blocks, warnings, f"{decoder.name};{getattr(speech_provider, 'name', 'local-speech')}"


def read_video(
    data: bytes,
    *,
    filename: str,
    speech_provider: SpeechToTextProvider | None,
    decoder: LocalMediaDecoder,
    ocr_provider=None,
    language: str | None = None,
    max_keyframes: int = 12,
) -> tuple[list[VishnuBlock], list[str], str, str | None]:
    warnings: list[str] = []
    try:
        probe = decoder.probe(data, filename=filename)
    except MediaUnavailable as exc:
        probe = MediaProbe(has_video=True)
        warnings.append(str(exc))
    blocks = [
        VishnuBlock(
            "media_metadata",
            "Video media",
            SourceReference(timestamp_start=0.0, timestamp_end=probe.duration),
            ExtractionMethod.MEDIA,
            data=probe.as_dict(),
            metadata={"media_type": "video"},
        )
    ]
    if speech_provider is not None and probe.has_audio:
        if bool(getattr(speech_provider, "external", False)):
            raise MediaUnavailable("External speech-to-text is disabled by default")
        try:
            wav_bytes = decoder.to_wav(data, filename=filename)
            blocks.extend(_transcript_blocks(speech_provider.transcribe(wav_bytes, filename=filename, language=language)))
        except MediaUnavailable as exc:
            warnings.append(str(exc))
    elif probe.has_audio:
        warnings.append("No local speech-to-text model is configured; video audio was not transcribed")

    ocr_version = None
    try:
        frames = decoder.keyframes(data, filename=filename, duration=probe.duration, max_frames=max_keyframes)
    except MediaUnavailable as exc:
        frames = []
        warnings.append(str(exc))
    for index, (timestamp, frame_bytes) in enumerate(frames, 1):
        frame_name = f"{Path(filename).stem}-frame-{index:03d}.png"
        if ocr_provider is None:
            blocks.append(
                VishnuBlock(
                    "video_frame",
                    f"Video frame {index}",
                    SourceReference(image=frame_name, timestamp_start=timestamp, timestamp_end=timestamp),
                    ExtractionMethod.MEDIA,
                    metadata={"frame": index},
                )
            )
            continue
        try:
            frame_blocks, frame_ocr_version = read_image(frame_bytes, frame_name, ocr_provider)
            ocr_version = frame_ocr_version or ocr_version
        except (ContentReadError, OcrUnavailable) as exc:
            warnings.append(f"Frame {index} OCR skipped: {exc}")
            continue
        for block in frame_blocks:
            block.kind = "frame_text"
            block.source.timestamp_start = timestamp
            block.source.timestamp_end = timestamp
            block.source.image = frame_name
            block.metadata = {**block.metadata, "frame": index, "video_timestamp": timestamp}
            blocks.append(block)
    return blocks, warnings, f"{decoder.name};{getattr(speech_provider, 'name', 'no-speech-model')}", ocr_version


_TIMESTAMP = re.compile(r"(?P<h>\d{1,2}):(?P<m>\d{2}):(?P<s>\d{2})[,.](?P<ms>\d{3})")


def _parse_timestamp(value: str) -> float:
    match = _TIMESTAMP.search(value.strip())
    if not match:
        return 0.0
    return (
        int(match.group("h")) * 3600
        + int(match.group("m")) * 60
        + int(match.group("s"))
        + int(match.group("ms")) / 1000.0
    )


def read_subtitles(data: bytes) -> list[VishnuBlock]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ContentReadError("Subtitle file is not valid UTF-8") from exc
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks: list[VishnuBlock] = []
    chunks = re.split(r"\n\s*\n", normalized)
    for index, chunk in enumerate(chunks, 1):
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        if not lines:
            continue
        if lines[0].upper() == "WEBVTT":
            continue
        timing_index = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        start_text, end_text = lines[timing_index].split("-->", 1)
        content = "\n".join(lines[timing_index + 1:]).strip()
        if not content:
            continue
        start, end = _parse_timestamp(start_text), _parse_timestamp(end_text)
        blocks.append(
            VishnuBlock(
                "transcript",
                content,
                SourceReference(timestamp_start=start, timestamp_end=max(start, end)),
                ExtractionMethod.NATIVE,
                metadata={"subtitle_cue": index},
            )
        )
    return blocks
