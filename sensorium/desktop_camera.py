from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


MAX_NATIVE_FRAME_BYTES = 2_000_000
CAPTURE_TIMEOUT_SECONDS = 8.0
DISCOVERY_TIMEOUT_SECONDS = 5.0


@dataclass(frozen=True)
class DesktopCameraSource:
    id: str
    label: str
    backend: str
    selector: str
    external: bool = False

    def public(self) -> dict:
        return {
            "camera_id": self.id,
            "label": self.label,
            "backend": self.backend,
            "external": self.external,
            "native": True,
        }


class DesktopCameraAdapter:
    """Native macOS/Windows/Linux webcam capture using fixed subprocess arrays.

    No shell is used and callers cannot supply arbitrary commands. Camera
    selectors must come from this adapter's discovery result. Capture is
    snapshot-only and stdout is bounded before being returned to Sensorium.
    """

    def __init__(self, *, ffmpeg_path: str | None = None, events=None) -> None:
        self.ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
        self.events = events

    @staticmethod
    def _run(args: list[str], *, timeout: float, text: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
            text=text,
            shell=False,
        )

    @staticmethod
    def _safe_id(prefix: str, selector: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", selector).strip("-")[:120] or "camera"
        return f"desktop:{prefix}:{normalized}"

    def available(self) -> bool:
        return bool(self.ffmpeg)

    def list_sources(self) -> list[dict]:
        if not self.ffmpeg:
            return []
        system = platform.system().lower()
        if system == "linux":
            sources = self._linux_sources()
        elif system == "darwin":
            sources = self._mac_sources()
        elif system == "windows":
            sources = self._windows_sources()
        else:
            sources = []
        return [source.public() for source in sources]

    def _linux_sources(self) -> list[DesktopCameraSource]:
        output = []
        for path in sorted(Path("/dev").glob("video*")):
            try:
                resolved = str(path.resolve())
            except OSError:
                continue
            if not re.fullmatch(r"/dev/video\d+", resolved):
                continue
            name_path = Path("/sys/class/video4linux") / path.name / "name"
            try:
                label = name_path.read_text(errors="replace").strip()[:160]
            except OSError:
                label = path.name
            output.append(
                DesktopCameraSource(
                    id=self._safe_id("v4l2", path.name),
                    label=label or path.name,
                    backend="v4l2",
                    selector=resolved,
                    external="usb" in (label or "").lower(),
                )
            )
        return output[:32]

    def _mac_sources(self) -> list[DesktopCameraSource]:
        # AVFoundation indexes are the selectors ffmpeg accepts. Parse only the
        # video-device section from ffmpeg's own bounded device-list output.
        proc = self._run(
            [self.ffmpeg, "-hide_banner", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            timeout=DISCOVERY_TIMEOUT_SECONDS,
        )
        text = (proc.stderr or "")[:100_000]
        in_video = False
        sources: list[DesktopCameraSource] = []
        for line in text.splitlines():
            if "AVFoundation video devices" in line:
                in_video = True
                continue
            if "AVFoundation audio devices" in line:
                break
            if not in_video:
                continue
            match = re.search(r"\[(\d+)\]\s+(.+?)\s*$", line)
            if not match:
                continue
            index, label = match.group(1), match.group(2).strip()
            sources.append(
                DesktopCameraSource(
                    id=self._safe_id("avfoundation", index),
                    label=label[:160],
                    backend="avfoundation",
                    selector=index,
                    external=any(term in label.lower() for term in ("usb", "external", "continuity")),
                )
            )
        return sources[:32]

    def _windows_sources(self) -> list[DesktopCameraSource]:
        proc = self._run(
            [self.ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            timeout=DISCOVERY_TIMEOUT_SECONDS,
        )
        text = (proc.stderr or "")[:100_000]
        sources: list[DesktopCameraSource] = []
        for line in text.splitlines():
            if "(video)" not in line.lower():
                continue
            match = re.search(r'"([^"]+)"', line)
            if not match:
                continue
            label = match.group(1).strip()
            if not label or any(item.label == label for item in sources):
                continue
            sources.append(
                DesktopCameraSource(
                    id=self._safe_id("dshow", label),
                    label=label[:160],
                    backend="dshow",
                    selector=label,
                    external=any(term in label.lower() for term in ("usb", "external")),
                )
            )
        return sources[:32]

    def _sources_internal(self) -> list[DesktopCameraSource]:
        public = self.list_sources()
        system = platform.system().lower()
        sources = []
        for item in public:
            camera_id = str(item["camera_id"])
            label = str(item["label"])
            backend = str(item["backend"])
            if system == "linux":
                suffix = camera_id.rsplit(":", 1)[-1]
                selector = f"/dev/{suffix}"
            elif system == "darwin":
                selector = camera_id.rsplit(":", 1)[-1]
            else:
                selector = label
            sources.append(DesktopCameraSource(camera_id, label, backend, selector, bool(item.get("external"))))
        return sources

    def _resolve(self, camera_id: str) -> DesktopCameraSource:
        requested = str(camera_id or "").strip()
        sources = self._sources_internal()
        if not sources:
            raise RuntimeError("no native desktop cameras are available")
        if requested in {"", "auto", "desktop:auto"}:
            return sources[0]
        for source in sources:
            if source.id == requested:
                return source
        raise ValueError("camera_id is not a currently discovered desktop camera")

    def capture(self, camera_id: str = "auto") -> dict:
        if not self.ffmpeg:
            raise RuntimeError("ffmpeg is required for native desktop camera capture")
        source = self._resolve(camera_id)
        if source.backend == "v4l2":
            args = [
                self.ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "v4l2",
                "-i", source.selector, "-frames:v", "1", "-vf", "scale='min(1280,iw)':-2",
                "-q:v", "5", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1",
            ]
        elif source.backend == "avfoundation":
            args = [
                self.ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "avfoundation",
                "-i", f"{source.selector}:none", "-frames:v", "1", "-vf", "scale='min(1280,iw)':-2",
                "-q:v", "5", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1",
            ]
        elif source.backend == "dshow":
            args = [
                self.ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "dshow",
                "-i", f"video={source.selector}", "-frames:v", "1", "-vf", "scale='min(1280,iw)':-2",
                "-q:v", "5", "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1",
            ]
        else:
            raise RuntimeError("unsupported native camera backend")
        try:
            proc = self._run(args, timeout=CAPTURE_TIMEOUT_SECONDS, text=False)
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("native desktop camera capture timed out") from exc
        raw = bytes(proc.stdout or b"")
        if proc.returncode != 0 or not raw:
            raise RuntimeError("native desktop camera capture failed")
        if len(raw) > MAX_NATIVE_FRAME_BYTES:
            raise RuntimeError("native desktop camera frame exceeded the size limit")
        if not raw.startswith(b"\xff\xd8"):
            raise RuntimeError("native desktop camera returned an invalid JPEG frame")
        if self.events is not None:
            self.events.emit(
                "sensorium.camera.desktop_captured",
                camera_id=source.id,
                frame_bytes=len(raw),
                backend=source.backend,
            )
        return {
            "camera_id": source.id,
            "label": source.label,
            "mime_type": "image/jpeg",
            "bytes": raw,
            "backend": source.backend,
            "external": source.external,
        }
