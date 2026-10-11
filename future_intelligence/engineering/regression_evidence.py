from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable

from .qualification import VerificationObservation


_TEST_SUFFIXES = (
    ".test.js", ".test.jsx", ".test.ts", ".test.tsx",
    ".spec.js", ".spec.jsx", ".spec.ts", ".spec.tsx",
    "_test.py", "_tests.py",
)


def is_test_path(path: str) -> bool:
    value = str(path or "").replace("\\", "/").strip("/")
    if not value:
        return False
    pure = PurePosixPath(value)
    parts = {part.lower() for part in pure.parts[:-1]}
    name = pure.name.lower()
    return (
        bool(parts & {"test", "tests", "__tests__", "spec", "specs"})
        or name.startswith("test_")
        or name.endswith(_TEST_SUFFIXES)
    )


def failure_fingerprint(defects: Iterable[str]) -> str:
    normalized = "\n".join(str(item).strip() for item in defects if str(item).strip())
    if not normalized:
        normalized = "unknown-verification-defect"
    return hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()


@dataclass(frozen=True)
class RegressionProof:
    candidate_revision: str
    repair_cycles: int
    failure_fingerprints: tuple[str, ...]
    test_paths: tuple[str, ...]
    integration_checks: tuple[tuple[str, str], ...]

    @property
    def passed(self) -> bool:
        return (
            self.repair_cycles > 0
            and bool(self.failure_fingerprints)
            and bool(self.test_paths)
            and bool(self.integration_checks)
            and bool(self.candidate_revision)
        )

    @property
    def evidence_refs(self) -> tuple[str, ...]:
        refs = [f"failure:{item}" for item in self.failure_fingerprints]
        refs.extend(f"verification:{digest}" for _name, digest in self.integration_checks if digest)
        refs.extend(f"test-path:{path}" for path in self.test_paths)
        return tuple(dict.fromkeys(refs))

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_revision": self.candidate_revision,
            "repair_cycles": self.repair_cycles,
            "failure_fingerprints": list(self.failure_fingerprints),
            "test_paths": list(self.test_paths),
            "integration_checks": [
                {"name": name, "output_hash": digest} for name, digest in self.integration_checks
            ],
            "passed": self.passed,
            "evidence_refs": list(self.evidence_refs),
        }

    def observation(self) -> VerificationObservation:
        if self.passed:
            return VerificationObservation(
                gate="regression_test",
                passed=True,
                summary=(
                    f"repair produced permanent regression coverage in {len(self.test_paths)} test path(s) "
                    "and the repaired revision passed trusted integration verification"
                ),
                evidence=self.evidence_refs,
                metadata={
                    "candidate_revision": self.candidate_revision,
                    "repair_cycles": self.repair_cycles,
                    "test_paths": list(self.test_paths),
                    "failure_fingerprints": list(self.failure_fingerprints),
                    "trusted_source": "engineering-repair-runtime",
                },
            )
        missing = []
        if not self.failure_fingerprints:
            missing.append("failure fingerprint")
        if not self.test_paths:
            missing.append("changed regression test")
        if not self.integration_checks:
            missing.append("passing integration/full-suite verification")
        return VerificationObservation(
            gate="regression_test",
            passed=False,
            summary="permanent regression proof is incomplete: " + ", ".join(missing or ("unknown evidence",)),
            evidence=self.evidence_refs,
            metadata={
                "candidate_revision": self.candidate_revision,
                "repair_cycles": self.repair_cycles,
                "test_paths": list(self.test_paths),
                "failure_fingerprints": list(self.failure_fingerprints),
                "trusted_source": "engineering-repair-runtime",
            },
        )


def build_regression_proof(
    *,
    candidate_revision: str,
    repair_cycles: int,
    failure_fingerprints: Iterable[str],
    changed_test_paths: Iterable[str],
    verification_report,
) -> RegressionProof:
    checks: list[tuple[str, str]] = []
    if verification_report is not None and bool(getattr(verification_report, "passed", False)):
        for check in getattr(verification_report, "checks", ()):
            name = str(getattr(check, "name", ""))
            lower = name.lower()
            # A permanent repair proof must be executed by a broad trusted test
            # lane, not merely compile/static checks.
            if bool(getattr(check, "passed", False)) and (
                "integration" in lower or "full-suite" in lower or "e2e" in lower
            ):
                digest = str(getattr(check, "output_hash", "")).strip()
                if digest:
                    checks.append((name, digest))
    return RegressionProof(
        candidate_revision=str(candidate_revision),
        repair_cycles=max(0, int(repair_cycles)),
        failure_fingerprints=tuple(dict.fromkeys(str(item) for item in failure_fingerprints if str(item))),
        test_paths=tuple(dict.fromkeys(str(item) for item in changed_test_paths if is_test_path(str(item)))),
        integration_checks=tuple(dict.fromkeys(checks)),
    )
