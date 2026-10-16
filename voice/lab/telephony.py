"""Governed, provider-injected telephony qualification for Vishnu Voice Lab.

The module is inert on import. It never opens a socket, allocates a phone number,
reads credentials, records audio, or places a call by itself. Real PSTN/SIP
providers must be injected explicitly and remain subject to owner approval.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
from typing import Protocol

from .evaluation import GateStatus, QualificationGate


class CallDirection(str, Enum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class CallState(str, Enum):
    BLOCKED = "blocked"
    CONNECTED = "connected"
    ENDED = "ended"


_COMMON_EMERGENCY_DESTINATIONS = frozenset({"110", "112", "911", "999"})


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def destination_fingerprint(destination: str) -> str:
    normalized = _digits(destination)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def masked_destination(destination: str) -> str:
    normalized = _digits(destination)
    if not normalized:
        return ""
    if len(normalized) <= 2:
        return "*" * len(normalized)
    return "*" * (len(normalized) - 2) + normalized[-2:]


def looks_like_emergency_destination(destination: str) -> bool:
    return _digits(destination) in _COMMON_EMERGENCY_DESTINATIONS


@dataclass(frozen=True, slots=True)
class TelephonyPolicy:
    enabled: bool = False
    allow_outbound: bool = False
    allow_inbound: bool = False
    allow_recording: bool = False
    allow_live_provider: bool = False
    require_owner_approval: bool = True
    max_call_seconds: int = 300

    def __post_init__(self) -> None:
        if self.max_call_seconds <= 0 or self.max_call_seconds > 3600:
            raise ValueError("telephony max_call_seconds must be between 1 and 3600")


@dataclass(frozen=True, slots=True)
class TelephonyCallRequest:
    provider: str
    destination: str
    purpose: str
    direction: CallDirection = CallDirection.OUTBOUND
    recording_requested: bool = False
    consent_reference: str | None = None

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("telephony provider is required")
        if not self.destination.strip():
            raise ValueError("telephony destination is required")
        if not self.purpose.strip():
            raise ValueError("telephony purpose is required")
        if self.recording_requested and not self.consent_reference:
            raise ValueError("recording requires an explicit consent reference")

    @property
    def destination_digest(self) -> str:
        return destination_fingerprint(self.destination)

    @property
    def request_id(self) -> str:
        body = "|".join(
            (
                self.provider.strip(),
                self.destination_digest,
                self.purpose.strip(),
                self.direction.value,
                str(self.recording_requested),
                self.consent_reference or "",
            )
        )
        return "vlcall-" + hashlib.sha256(body.encode("utf-8")).hexdigest()[:24]


@dataclass(frozen=True, slots=True)
class TelephonyApproval:
    request_id: str
    destination_digest: str
    owner_id: str
    attestation: str
    allow_recording: bool = False

    @classmethod
    def for_request(
        cls,
        request: TelephonyCallRequest,
        *,
        owner_id: str,
        attestation: str,
        allow_recording: bool = False,
    ) -> "TelephonyApproval":
        if not owner_id.strip() or not attestation.strip():
            raise ValueError("owner identity and attestation are required")
        return cls(
            request.request_id,
            request.destination_digest,
            owner_id.strip(),
            attestation.strip(),
            bool(allow_recording),
        )


@dataclass(frozen=True, slots=True)
class TelephonyProviderResult:
    call_id: str
    connected: bool
    connect_latency_ms: float | None = None
    duration_ms: float | None = None
    hangup_confirmed: bool = False
    recording_active: bool = False
    provider_reference: str = ""

    def __post_init__(self) -> None:
        if not self.call_id.strip():
            raise ValueError("provider call_id is required")
        if self.connect_latency_ms is not None and self.connect_latency_ms < 0:
            raise ValueError("connect latency cannot be negative")
        if self.duration_ms is not None and self.duration_ms < 0:
            raise ValueError("call duration cannot be negative")


class TelephonyControl(Protocol):
    def checkpoint(self) -> None: ...


class TelephonyProvider(Protocol):
    """Explicit Lab adapter. Implementations own provider-specific transport."""

    sandbox: bool

    def place_call(
        self,
        request: TelephonyCallRequest,
        *,
        control: TelephonyControl,
        max_call_seconds: int,
    ) -> TelephonyProviderResult: ...

    def hangup(self, call_id: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class TelephonyLabRun:
    request_id: str
    state: CallState
    provider: str
    destination_digest: str
    destination_masked: str
    result: TelephonyProviderResult | None
    gates: tuple[QualificationGate, ...]

    @property
    def qualified(self) -> bool:
        return bool(self.gates) and all(gate.status is GateStatus.PASS for gate in self.gates)

    def evidence_metadata(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "state": self.state.value,
            "provider": self.provider,
            "destination_sha256": self.destination_digest,
            "destination_masked": self.destination_masked,
            "connected": bool(self.result and self.result.connected),
            "connect_latency_ms": None if self.result is None else self.result.connect_latency_ms,
            "duration_ms": None if self.result is None else self.result.duration_ms,
            "hangup_confirmed": bool(self.result and self.result.hangup_confirmed),
            "recording_active": bool(self.result and self.result.recording_active),
            "gates": tuple((gate.gate_id, gate.status.value) for gate in self.gates),
        }


class TelephonyLab:
    """Fail-closed call qualification; no provider is contacted unless every gate allows it."""

    def __init__(
        self,
        *,
        policy: TelephonyPolicy | None = None,
        providers: dict[str, TelephonyProvider] | None = None,
    ):
        self.policy = policy or TelephonyPolicy()
        self.providers = dict(providers or {})

    def registered_providers(self) -> tuple[str, ...]:
        return tuple(sorted(self.providers))

    def _preflight_gates(
        self,
        request: TelephonyCallRequest,
        approval: TelephonyApproval | None,
    ) -> tuple[QualificationGate, ...]:
        enabled = self.policy.enabled
        direction_allowed = (
            self.policy.allow_outbound if request.direction is CallDirection.OUTBOUND else self.policy.allow_inbound
        )
        provider = self.providers.get(request.provider)
        provider_allowed = provider is not None and (bool(getattr(provider, "sandbox", False)) or self.policy.allow_live_provider)
        exact_approval = bool(
            approval
            and approval.request_id == request.request_id
            and approval.destination_digest == request.destination_digest
            and approval.owner_id.strip()
            and approval.attestation.strip()
        )
        recording_allowed = not request.recording_requested or bool(
            self.policy.allow_recording
            and request.consent_reference
            and approval
            and approval.allow_recording
        )
        not_emergency = not looks_like_emergency_destination(request.destination)
        return (
            QualificationGate(
                "telephony-enabled",
                GateStatus.PASS if enabled else GateStatus.BLOCKED,
                notes="telephony Lab explicitly enabled" if enabled else "telephony Lab is default-off",
            ),
            QualificationGate(
                "telephony-direction-policy",
                GateStatus.PASS if direction_allowed else GateStatus.BLOCKED,
                notes="call direction permitted" if direction_allowed else "call direction is not permitted",
            ),
            QualificationGate(
                "telephony-provider-boundary",
                GateStatus.PASS if provider_allowed else GateStatus.BLOCKED,
                notes=(
                    "explicit sandbox/live-authorized provider registered"
                    if provider_allowed
                    else "provider missing or live provider not explicitly allowed"
                ),
            ),
            QualificationGate(
                "telephony-owner-approval",
                GateStatus.PASS if (exact_approval or not self.policy.require_owner_approval) else GateStatus.BLOCKED,
                notes="approval binds exact request" if exact_approval else "exact owner approval required",
            ),
            QualificationGate(
                "telephony-recording-consent",
                GateStatus.PASS if recording_allowed else GateStatus.BLOCKED,
                notes="recording disabled or explicitly consented" if recording_allowed else "recording consent is incomplete",
            ),
            QualificationGate(
                "telephony-emergency-boundary",
                GateStatus.PASS if not_emergency else GateStatus.BLOCKED,
                notes=(
                    "destination is not a recognized emergency number"
                    if not_emergency
                    else "Voice Lab never places calls to recognized emergency numbers"
                ),
            ),
        )

    def place_call(
        self,
        request: TelephonyCallRequest,
        *,
        approval: TelephonyApproval | None,
        control: TelephonyControl,
    ) -> TelephonyLabRun:
        gates = self._preflight_gates(request, approval)
        if any(gate.status is not GateStatus.PASS for gate in gates):
            return TelephonyLabRun(
                request.request_id,
                CallState.BLOCKED,
                request.provider,
                request.destination_digest,
                masked_destination(request.destination),
                None,
                gates,
            )
        control.checkpoint()
        provider = self.providers[request.provider]
        result = provider.place_call(request, control=control, max_call_seconds=self.policy.max_call_seconds)
        control.checkpoint()
        post = list(gates)
        post.append(
            QualificationGate(
                "telephony-connectivity",
                GateStatus.PASS if result.connected else GateStatus.FAIL,
                observed=result.connect_latency_ms,
                notes="provider connected the qualified call" if result.connected else "provider did not connect",
            )
        )
        recording_ok = result.recording_active == request.recording_requested
        post.append(
            QualificationGate(
                "telephony-recording-state",
                GateStatus.PASS if recording_ok else GateStatus.FAIL,
                notes="provider recording state matches the approved request" if recording_ok else "provider recording state violated request",
            )
        )
        duration_ok = result.duration_ms is None or result.duration_ms <= self.policy.max_call_seconds * 1000
        post.append(
            QualificationGate(
                "telephony-duration-bound",
                GateStatus.PASS if duration_ok else GateStatus.FAIL,
                observed=result.duration_ms,
                threshold=f"<= {self.policy.max_call_seconds * 1000} ms",
            )
        )
        state = CallState.CONNECTED if result.connected else CallState.ENDED
        return TelephonyLabRun(
            request.request_id,
            state,
            request.provider,
            request.destination_digest,
            masked_destination(request.destination),
            result,
            tuple(post),
        )

    def hangup(self, provider_name: str, call_id: str) -> QualificationGate:
        provider = self.providers.get(provider_name)
        if provider is None or not call_id.strip():
            return QualificationGate(
                "telephony-hangup-control",
                GateStatus.BLOCKED,
                notes="registered provider and call ID are required",
            )
        confirmed = bool(provider.hangup(call_id))
        return QualificationGate(
            "telephony-hangup-control",
            GateStatus.PASS if confirmed else GateStatus.FAIL,
            notes="provider confirmed hangup" if confirmed else "provider did not confirm hangup",
        )
