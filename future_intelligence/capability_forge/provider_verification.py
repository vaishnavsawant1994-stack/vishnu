from __future__ import annotations

import time
from typing import Any

from tools.registry import Risk, VerificationResult


class CapabilityProviderVerifier:
    """Probe live providers only through already-governed read-only Vishnu tools.

    Forge never performs arbitrary requests itself. OpenAPI/MCP/connector
    networking, credentials, destination checks and response verification remain
    owned by their existing runtime Tool definitions and ToolRegistry.
    """

    def __init__(self, *, tools, rollout=None, events=None):
        self.tools = tools
        self.rollout = rollout
        self.events = events

    def verify(
        self,
        tool_name: str,
        parameters: dict[str, Any],
        *,
        capability_id: str | None = None,
        version: str | None = None,
        data_classification: str = "internal",
    ) -> dict[str, Any]:
        tool = self.tools.get(str(tool_name))
        if Risk(int(tool.risk)) is not Risk.READ_ONLY:
            raise PermissionError("live provider verification is limited to read-only probes")
        if str(getattr(tool, "verification_method", "") or "").startswith("qualified_generated"):
            raise PermissionError("generated capabilities cannot verify providers through generated-to-generated delegation")
        if str(data_classification or "internal").strip().lower() != "internal":
            raise PermissionError("live provider verification cannot receive sensitive, secret, or restricted data")
        decision = self.tools.authorize(
            tool,
            confirmed=False,
            parameters=dict(parameters),
            data_classification="internal",
        )
        if not decision.allowed:
            raise PermissionError(f"provider verification probe is not authorized: {decision.reason}")
        started = time.monotonic()
        ok = False
        error_code = None
        try:
            result = self.tools.dispatch(tool, dict(parameters))
            verification = self.tools.verify_result(tool, dict(parameters), result)
            if isinstance(verification, VerificationResult):
                ok = bool(verification.verified)
                reason = str(verification.reason)
                evidence_keys = sorted(str(key) for key in dict(verification.evidence or {}).keys())[:30]
            elif isinstance(verification, dict):
                ok = bool(verification.get("verified"))
                reason = str(verification.get("reason") or "")
                evidence_keys = sorted(str(key) for key in dict(verification.get("evidence") or {}).keys())[:30]
            else:
                ok = bool(verification)
                reason = "verified" if ok else "verification failed"
                evidence_keys = []
            if not ok:
                error_code = "provider_verification_failed"
        except Exception as exc:
            error_code = type(exc).__name__[:120]
            raise
        finally:
            duration_ms = max(0.0, (time.monotonic() - started) * 1000.0)
            if self.rollout is not None and capability_id and version:
                try:
                    self.rollout.record_sample(
                        str(capability_id), str(version), ok=ok,
                        duration_ms=duration_ms, source="provider_probe",
                    )
                except Exception:
                    pass
            if self.events is not None:
                self.events.emit(
                    "capability_forge.provider_verified" if ok else "capability_forge.provider_verification_failed",
                    tool_name=str(tool_name),
                    capability_id=str(capability_id) if capability_id else None,
                    version=str(version) if version else None,
                    duration_ms=duration_ms,
                    error_code=error_code,
                )
        return {
            "verified": ok,
            "tool_name": str(tool_name),
            "duration_ms": duration_ms,
            "reason": reason,
            "evidence_keys": evidence_keys,
            "result_redacted": True,
        }
