from __future__ import annotations

import math
import statistics
from typing import Any


def _levenshtein(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[j] + 1,
                    previous[j - 1] + (ca != cb),
                )
            )
        previous = current
    return previous[-1]


class SensoriumBenchmark:
    """Deterministic metrics for perception and world-intelligence qualification."""

    @staticmethod
    def object_persistence(
        predicted_ids: list[str],
        truth_ids: list[str],
    ) -> dict[str, float | int]:
        if len(predicted_ids) != len(truth_ids):
            raise ValueError("object persistence arrays must have equal length")
        correct = sum(
            1
            for predicted, truth in zip(predicted_ids, truth_ids)
            if predicted == truth
        )
        total = len(truth_ids)
        return {
            "accuracy": correct / total if total else 1.0,
            "correct": correct,
            "total": total,
        }

    @staticmethod
    def location_rmse(
        predicted: list[tuple[float, float]],
        truth: list[tuple[float, float]],
    ) -> float:
        if len(predicted) != len(truth):
            raise ValueError("location arrays must have equal length")
        if not truth:
            return 0.0
        distances_sq = []
        radius = 6_371_000.0
        for (plat, plon), (tlat, tlon) in zip(predicted, truth):
            lat1, lat2 = math.radians(plat), math.radians(tlat)
            x = math.radians(plon - tlon) * math.cos((lat1 + lat2) / 2)
            y = math.radians(plat - tlat)
            distances_sq.append((radius * math.sqrt(x * x + y * y)) ** 2)
        return math.sqrt(sum(distances_sq) / len(distances_sq))

    @staticmethod
    def classification(
        predicted: list[str],
        truth: list[str],
        *,
        positive_label: str,
    ) -> dict[str, float]:
        if len(predicted) != len(truth):
            raise ValueError("classification arrays must have equal length")
        tp = sum(
            1
            for p, t in zip(predicted, truth)
            if p == positive_label and t == positive_label
        )
        fp = sum(
            1
            for p, t in zip(predicted, truth)
            if p == positive_label and t != positive_label
        )
        fn = sum(
            1
            for p, t in zip(predicted, truth)
            if p != positive_label and t == positive_label
        )
        precision = tp / (tp + fp) if tp + fp else 1.0
        recall = tp / (tp + fn) if tp + fn else 1.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        return {"precision": precision, "recall": recall, "f1": f1}

    @staticmethod
    def ocr_character_error_rate(predicted: str, truth: str) -> float:
        return _levenshtein(predicted, truth) / max(len(truth), 1)

    @staticmethod
    def expected_calibration_error(
        samples: list[dict[str, Any]],
        *,
        bins: int = 10,
    ) -> float:
        if bins < 1 or bins > 100:
            raise ValueError("bins must be between 1 and 100")
        if not samples:
            return 0.0
        total = len(samples)
        error = 0.0
        for index in range(bins):
            low, high = index / bins, (index + 1) / bins
            bucket = [
                item
                for item in samples
                if low <= float(item["confidence"]) < high
                or (
                    index == bins - 1
                    and float(item["confidence"]) == 1.0
                )
            ]
            if not bucket:
                continue
            confidence = statistics.mean(
                float(item["confidence"]) for item in bucket
            )
            accuracy = sum(bool(item["correct"]) for item in bucket) / len(bucket)
            error += abs(accuracy - confidence) * len(bucket) / total
        return error

    @staticmethod
    def causal_hypothesis_accuracy(
        predicted: list[bool],
        truth: list[bool],
    ) -> float:
        if len(predicted) != len(truth):
            raise ValueError("causal arrays must have equal length")
        return (
            sum(p == t for p, t in zip(predicted, truth)) / len(truth)
            if truth
            else 1.0
        )

    @staticmethod
    def task_progress_mae(
        predicted: list[float],
        truth: list[float],
    ) -> float:
        if len(predicted) != len(truth):
            raise ValueError("task progress arrays must have equal length")
        return (
            sum(abs(float(p) - float(t)) for p, t in zip(predicted, truth))
            / len(truth)
            if truth
            else 0.0
        )

    @staticmethod
    def battery_drain(samples: list[dict[str, Any]]) -> dict[str, float]:
        if len(samples) < 2:
            return {"percent_per_hour": 0.0, "sample_hours": 0.0}
        ordered = sorted(samples, key=lambda item: float(item["timestamp"]))
        start, end = ordered[0], ordered[-1]
        hours = max(
            (float(end["timestamp"]) - float(start["timestamp"])) / 3600.0,
            1e-9,
        )
        drain = max(
            0.0,
            float(start["battery_percent"]) - float(end["battery_percent"]),
        )
        return {"percent_per_hour": drain / hours, "sample_hours": hours}

    @staticmethod
    def privacy_violations(
        events: list[dict[str, Any]],
    ) -> dict[str, float | int]:
        violations = sum(
            1
            for event in events
            if bool(event.get("sensor_used_without_permission"))
            or bool(event.get("retention_policy_violated"))
            or bool(event.get("raw_media_leaked"))
        )
        return {
            "violations": violations,
            "events": len(events),
            "violation_rate": violations / len(events) if events else 0.0,
        }

    def report(self, suite: dict[str, Any]) -> dict[str, Any]:
        report: dict[str, Any] = {"metrics": {}, "execution_authority": False}
        if "object_persistence" in suite:
            item = suite["object_persistence"]
            report["metrics"]["object_persistence"] = self.object_persistence(
                item["predicted"],
                item["truth"],
            )
        if "ocr" in suite:
            item = suite["ocr"]
            report["metrics"]["ocr_character_error_rate"] = (
                self.ocr_character_error_rate(item["predicted"], item["truth"])
            )
        if "calibration" in suite:
            report["metrics"]["expected_calibration_error"] = (
                self.expected_calibration_error(suite["calibration"])
            )
        if "causal" in suite:
            item = suite["causal"]
            report["metrics"]["causal_hypothesis_accuracy"] = (
                self.causal_hypothesis_accuracy(item["predicted"], item["truth"])
            )
        if "task_progress" in suite:
            item = suite["task_progress"]
            report["metrics"]["task_progress_mae"] = self.task_progress_mae(
                item["predicted"],
                item["truth"],
            )
        if "battery" in suite:
            report["metrics"]["battery"] = self.battery_drain(suite["battery"])
        if "privacy" in suite:
            report["metrics"]["privacy"] = self.privacy_violations(
                suite["privacy"]
            )
        return report
