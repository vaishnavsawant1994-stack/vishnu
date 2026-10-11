from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from PIL import Image, ImageChops

from .contracts import VisualDefect


@dataclass(frozen=True)
class VisualDiffResult:
    changed: bool
    mismatch_ratio: float
    changed_bbox: tuple[int, int, int, int] | None
    baseline_size: tuple[int, int]
    candidate_size: tuple[int, int]

    def to_dict(self) -> dict[str, object]:
        return {
            "changed": self.changed,
            "mismatch_ratio": self.mismatch_ratio,
            "changed_bbox": list(self.changed_bbox) if self.changed_bbox else None,
            "baseline_size": list(self.baseline_size),
            "candidate_size": list(self.candidate_size),
        }


class VisualRegressionAnalyzer:
    """Deterministic image diff plus optional sanitized Vishnu vision review."""

    @staticmethod
    def _image(source: str | Path | bytes) -> Image.Image:
        if isinstance(source, bytes):
            image = Image.open(io.BytesIO(source))
        else:
            image = Image.open(Path(source))
        return image.convert("RGBA")

    def compare(self, baseline: str | Path | bytes, candidate: str | Path | bytes, *, threshold: int = 12) -> VisualDiffResult:
        first = self._image(baseline)
        second = self._image(candidate)
        if first.size != second.size:
            return VisualDiffResult(True, 1.0, (0, 0, max(first.width, second.width), max(first.height, second.height)), first.size, second.size)
        diff = ImageChops.difference(first, second).convert("RGB")
        raw = diff.tobytes()
        pixels = max(1, first.width * first.height)
        changed = 0
        limit = max(0, min(255, int(threshold)))
        for index in range(0, len(raw), 3):
            if max(raw[index:index + 3]) > limit:
                changed += 1
        bbox = diff.getbbox()
        return VisualDiffResult(changed > 0, changed / pixels, bbox, first.size, second.size)

    def analyze_sanitized_candidate(
        self,
        *,
        screen_understanding,
        sanitized_source: Mapping[str, Any],
        route: str,
        screen: str,
        browser: str,
        viewport: str,
        state: str,
        deterministic_diff: VisualDiffResult,
        dom_evidence: Mapping[str, Any] | None = None,
        evidence_binding: Mapping[str, str] | None = None,
    ) -> tuple[VisualDefect, ...]:
        if not deterministic_diff.changed:
            return ()
        question = (
            "Review this sanitized candidate UI screenshot for a software-engineering visual regression. "
            f"Route={route}; screen={screen}; browser={browser}; viewport={viewport}; state={state}; "
            f"deterministic mismatch_ratio={deterministic_diff.mismatch_ratio:.6f}. "
            "Identify only visible defects. Do not infer hidden or redacted content. "
            "Return concise diagnosis including suspected visible element and corrective direction."
        )
        result = screen_understanding.analyze(
            question,
            sanitized_source=dict(sanitized_source),
            application_context={"route": route, "screen": screen, "browser": browser, "viewport": viewport, "state": state, "dom": dict(dom_evidence or {})},
            evidence_binding=dict(evidence_binding or {}),
        )
        analysis = str(result.get("analysis") or "")
        if not analysis or analysis.startswith("visual_evidence_unavailable"):
            analysis = "deterministic visual regression detected; model visual evidence unavailable"
        region: dict[str, float] = {}
        if deterministic_diff.changed_bbox:
            left, top, right, bottom = deterministic_diff.changed_bbox
            region = {"x": float(left), "y": float(top), "width": float(right-left), "height": float(bottom-top)}
        return (
            VisualDefect(
                screen=screen,
                route=route,
                viewport=viewport,
                browser=browser,
                state=state,
                severity="review",
                expected="approved visual baseline",
                actual=analysis[:4000],
                region=region,
                suspected_element=str((dom_evidence or {}).get("suspected_element") or ""),
                suspected_component=str((dom_evidence or {}).get("suspected_component") or ""),
                screenshot_evidence=str(result.get("screenshot_evidence_ref") or ""),
                confidence=min(1.0, max(0.1, deterministic_diff.mismatch_ratio * 10)),
                recommended_action="correlate changed region with DOM/source mapping, repair within EngineeringSpec scope, and rerun qualification",
            ),
        )
