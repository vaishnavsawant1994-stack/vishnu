from __future__ import annotations

import io
import wave
from pathlib import Path

import pytest
from PIL import Image

from file_intelligence import (
    ContentKind,
    FasterWhisperProvider,
    FileIntelligenceEngine,
    LocalContentIndex,
    MediaProbe,
    MediaUnavailable,
    WhisperCppProvider,
    detect_content,
    read_subtitles,
)


def _wav_bytes(seconds: float = 1.0) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buffer.getvalue()


def _png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (320, 180), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_media_detection_uses_signatures_and_extensions():
    wav = _wav_bytes()
    assert detect_content("renamed.bin", wav).kind == ContentKind.AUDIO
    assert detect_content("clip.flac", b"fLaC" + b"\x00" * 32).kind == ContentKind.AUDIO
    assert detect_content("clip.opus", b"OggS" + b"\x00" * 32).extension == ".opus"
    assert detect_content("clip.mp3", b"ID3" + b"\x00" * 32).kind == ContentKind.AUDIO
    assert detect_content("movie.mp4", b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32).kind == ContentKind.VIDEO
    assert detect_content("movie.webm", b"\x1aE\xdf\xa3" + b"\x00" * 32).extension == ".webm"
    assert detect_content("captions.srt", b"1\n00:00:00,000 --> 00:00:01,000\nHi\n").extension == ".srt"


class _Speech:
    name = "fixture-speech-local"
    external = False

    def transcribe(self, wav_bytes, *, filename="audio.wav", language=None):
        assert wav_bytes.startswith(b"RIFF")
        return [
            {"text": "First decision", "start": 1.25, "end": 3.5, "confidence": 0.97, "language": "en"},
            {"text": "Second action", "start": 4.0, "end": 6.75, "confidence": 0.91, "speaker": "speaker-1"},
        ]


def test_audio_is_first_class_with_exact_timestamp_provenance():
    document = FileIntelligenceEngine(speech_provider=_Speech()).extract(
        filename="meeting.wav",
        data=_wav_bytes(8.0),
        declared_mime="audio/wav",
    )
    assert document.content_kind == ContentKind.AUDIO
    assert document.schema_version == "1.3"
    assert document.media_version and "fixture-speech-local" in document.media_version
    transcript = [block for block in document.blocks if block.kind == "transcript"]
    assert [block.text for block in transcript] == ["First decision", "Second action"]
    assert transcript[0].source.timestamp_start == 1.25
    assert transcript[0].source.timestamp_end == 3.5
    assert transcript[0].confidence == 0.97
    assert transcript[1].metadata["speaker"] == "speaker-1"


def test_audio_without_local_model_remains_indexable_and_never_calls_cloud(monkeypatch):
    monkeypatch.delenv("VISHNU_WHISPER_MODEL", raising=False)
    document = FileIntelligenceEngine(speech_provider=None).extract(filename="voice.wav", data=_wav_bytes())
    assert document.content_kind == ContentKind.AUDIO
    assert any(block.kind == "media_metadata" for block in document.blocks)
    assert any("No local speech-to-text model" in warning for warning in document.warnings)


class _ExternalSpeech:
    name = "external-test"
    external = True


def test_external_speech_is_rejected_by_default():
    with pytest.raises(MediaUnavailable, match="External speech-to-text is disabled"):
        FileIntelligenceEngine(speech_provider=_ExternalSpeech())


def test_local_model_providers_refuse_missing_paths_before_runtime_or_download(tmp_path: Path):
    missing = tmp_path / "not-a-model"
    with pytest.raises(MediaUnavailable, match="existing local model file"):
        WhisperCppProvider(model_path=missing)
    with pytest.raises(MediaUnavailable, match="existing local model directory"):
        FasterWhisperProvider(model_path=missing)


def test_whisper_cpp_current_json_offsets_become_seconds(tmp_path: Path):
    model = tmp_path / "ggml.bin"
    model.write_bytes(b"local")
    provider = WhisperCppProvider(model_path=model)
    parsed = provider._parse_json(
        {
            "result": {"language": "en"},
            "transcription": [
                {"offsets": {"from": 0, "to": 11000}, "text": "Hello world."},
                {"offsets": {"from": 11000, "to": 12500}, "text": "Next."},
            ],
        }
    )
    assert parsed[0]["start"] == 0.0
    assert parsed[0]["end"] == 11.0
    assert parsed[1]["start"] == 11.0
    assert parsed[1]["end"] == 12.5


class _VideoDecoder:
    name = "fixture-media/1"

    def probe(self, data, *, filename):
        return MediaProbe(duration=60.0, has_audio=True, has_video=True, format_name="mp4", width=1280, height=720)

    def to_wav(self, data, *, filename):
        return _wav_bytes(8.0)

    def keyframes(self, data, *, filename, duration, max_frames=12):
        return [(10.0, _png_bytes()), (40.0, _png_bytes())]


class _FrameOcr:
    name = "fixture-frame-ocr"
    external = False

    def extract(self, image_bytes, *, filename="image.png", access_class="owner"):
        return [{"text": f"Slide text {filename}", "confidence": 0.95, "bbox": [5, 5, 200, 40]}]


def test_video_combines_audio_transcript_and_timestamped_frame_ocr():
    fake_mp4 = b"\x00\x00\x00\x18ftypisom" + b"\x00" * 128
    document = FileIntelligenceEngine(
        speech_provider=_Speech(),
        media_decoder=_VideoDecoder(),
        ocr_provider=_FrameOcr(),
    ).extract(filename="review.mp4", data=fake_mp4, declared_mime="video/mp4")
    assert document.content_kind == ContentKind.VIDEO
    assert document.media_version == "fixture-media/1;fixture-speech-local"
    transcript = [block for block in document.blocks if block.kind == "transcript"]
    frames = [block for block in document.blocks if block.kind == "frame_text" and not block.metadata.get("derived")]
    assert transcript and len(frames) == 2
    assert [block.source.timestamp_start for block in frames] == [10.0, 40.0]
    assert all(block.source.timestamp_end == block.source.timestamp_start for block in frames)
    assert frames[0].source.image.endswith("frame-001.png")
    assert document.ocr_version == "fixture-frame-ocr"


def test_subtitles_become_timestamped_transcript_blocks():
    blocks = read_subtitles(
        b"1\n00:00:01,500 --> 00:00:03,250\nFirst line\n\n2\n00:01:00,000 --> 00:01:02,500\nSecond line\n"
    )
    assert len(blocks) == 2
    assert blocks[0].text == "First line"
    assert blocks[0].source.timestamp_start == 1.5
    assert blocks[0].source.timestamp_end == 3.25
    assert blocks[1].source.timestamp_start == 60.0


def test_media_timestamp_survives_local_index_and_citation(tmp_path: Path):
    document = FileIntelligenceEngine(speech_provider=_Speech()).extract(filename="meeting.wav", data=_wav_bytes(8.0))
    index = LocalContentIndex(tmp_path / "content.sqlite3")
    index.index_document(document, scope_type="project", scope_id="project-1")
    results = index.search("decision", scope_type="project", scope_id="project-1")
    assert results
    assert results[0]["source"]["timestamp_start"] == 1.25
    assert results[0]["citation"]["source"]["timestamp_end"] == 3.5
    state = index.state(document_id=document.document_id, scope_type="project", scope_id="project-1")
    assert state["metadata"]["media_version"] == document.media_version
