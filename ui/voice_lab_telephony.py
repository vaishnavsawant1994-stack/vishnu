"""Operational Owner UI for governed Vishnu Voice Lab telephony."""
from __future__ import annotations

import json

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from voice.lab.evidence import EvidenceRecord, EvidenceStore
from voice.lab.runner import LabRunControl
from voice.lab.telephony import (
    CallState,
    TelephonyApproval,
    TelephonyCallRequest,
    TelephonyLab,
    looks_like_emergency_destination,
    masked_destination,
)


class _TelephonyWorker(QThread):
    result_ready = pyqtSignal(object)
    failed = pyqtSignal(object)

    def __init__(self, telephony, request, approval, control):
        super().__init__()
        self.telephony = telephony
        self.request = request
        self.approval = approval
        self.control = control

    def run(self):
        try:
            result = self.telephony.place_call(
                self.request,
                approval=self.approval,
                control=self.control,
            )
            self.result_ready.emit(result)
        except Exception as exc:
            self.failed.emit(exc)


class TelephonyLabPage(QWidget):
    """Explicit call controls; no call happens on construction or refresh."""

    def __init__(self, runtime, telephony: TelephonyLab, evidence: EvidenceStore, parent=None):
        super().__init__(parent)
        self.runtime = runtime
        self.telephony = telephony
        self.evidence = evidence
        self._worker = None
        self._control = None
        self._last_run = None
        self._last_evidence_id = ""

        layout = QVBoxLayout(self)
        heading = QLabel("TELEPHONY LAB")
        heading.setStyleSheet("font-size:16px;font-weight:650")
        layout.addWidget(heading)
        notice = QLabel(
            "Default-off provider-injected PSTN/SIP/WebRTC qualification. Every outbound call requires an exact "
            "destination-bound owner approval. Emergency calls are blocked. Recording requires separate consent. "
            "Raw destinations and call audio are never stored as Voice Lab evidence."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)

        self.status_view = QTextBrowser()
        self.status_view.setMaximumHeight(180)
        layout.addWidget(self.status_view)

        form = QFormLayout()
        self.provider = QLineEdit()
        self.provider.setPlaceholderText("registered telephony provider")
        self.destination = QLineEdit()
        self.destination.setPlaceholderText("destination used only for this exact request")
        self.purpose = QLineEdit("Voice Lab telephony qualification")
        self.recording_consent = QLineEdit()
        self.recording_consent.setPlaceholderText("leave blank for no recording")
        form.addRow("Provider", self.provider)
        form.addRow("Destination", self.destination)
        form.addRow("Purpose", self.purpose)
        form.addRow("Recording consent reference", self.recording_consent)
        layout.addLayout(form)

        buttons = QHBoxLayout()
        self.call_button = QPushButton("Owner approve & place governed call")
        self.call_button.clicked.connect(self.place_call)
        self.cancel_button = QPushButton("Cancel call setup")
        self.cancel_button.clicked.connect(self.cancel_call)
        self.cancel_button.setEnabled(False)
        self.hangup_button = QPushButton("Hang up current call")
        self.hangup_button.clicked.connect(self.hangup_call)
        self.hangup_button.setEnabled(False)
        buttons.addWidget(self.call_button)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.hangup_button)
        layout.addLayout(buttons)

        self.result_view = QTextBrowser()
        layout.addWidget(self.result_view, 1)

    def refresh_status(self, capabilities) -> None:
        rows = [
            {
                "id": item.capability_id,
                "title": item.title,
                "state": item.state.value,
                "notes": item.qualification_notes,
            }
            for item in capabilities
            if item.category == "communications"
        ]
        self.status_view.setPlainText(
            json.dumps(
                {
                    "capabilities": rows,
                    "policy": {
                        "enabled": self.telephony.policy.enabled,
                        "allow_outbound": self.telephony.policy.allow_outbound,
                        "allow_inbound": self.telephony.policy.allow_inbound,
                        "allow_recording": self.telephony.policy.allow_recording,
                        "allow_live_provider": self.telephony.policy.allow_live_provider,
                        "max_call_seconds": self.telephony.policy.max_call_seconds,
                    },
                    "registered_providers": self.telephony.registered_providers(),
                    "live_promotion": "requires non-sandbox live-provider evidence plus exact call/hangup gates",
                },
                indent=2,
            )
        )

    def place_call(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        provider_name = self.provider.text().strip()
        destination = self.destination.text().strip()
        purpose = self.purpose.text().strip()
        recording_consent = self.recording_consent.text().strip()

        if not self.telephony.policy.enabled or not self.telephony.policy.allow_outbound:
            QMessageBox.warning(self, "Telephony Lab", "Outbound Telephony Lab policy is not explicitly enabled.")
            return
        if provider_name not in self.telephony.providers:
            QMessageBox.warning(self, "Telephony Lab", "Choose an explicitly registered Telephony Lab provider.")
            return
        if looks_like_emergency_destination(destination):
            QMessageBox.warning(self, "Telephony Lab", "Emergency-number calls are blocked inside Voice Lab.")
            return
        try:
            request = TelephonyCallRequest(
                provider=provider_name,
                destination=destination,
                purpose=purpose,
                recording_requested=bool(recording_consent),
                consent_reference=recording_consent or None,
            )
        except Exception as exc:
            QMessageBox.warning(self, "Telephony Lab", str(exc))
            return
        if request.recording_requested and not self.telephony.policy.allow_recording:
            QMessageBox.warning(self, "Telephony Lab", "Recording is not enabled by Telephony Lab policy.")
            return

        owner = self.runtime.get("owner_access")
        if not owner or not owner.password_configured():
            QMessageBox.warning(self, "Telephony Lab", "Configure owner reauthentication before placing calls.")
            return
        password, ok = QInputDialog.getText(
            self,
            "Telephony owner approval",
            f"Owner password for exact destination {masked_destination(destination)}:",
            QLineEdit.EchoMode.Password,
        )
        if not ok or not owner.verify_password(password):
            QMessageBox.warning(self, "Telephony Lab", "Owner reauthentication failed. No provider was contacted.")
            return
        attestation, ok = QInputDialog.getText(
            self,
            "Telephony call attestation",
            "Attestation for this exact provider, destination, purpose and recording state:",
        )
        if not ok or not attestation.strip():
            return
        approval = TelephonyApproval.for_request(
            request,
            owner_id="owner",
            attestation=attestation,
            allow_recording=request.recording_requested,
        )
        self._control = LabRunControl.bounded(float(self.telephony.policy.max_call_seconds) + 30.0)
        self._worker = _TelephonyWorker(self.telephony, request, approval, self._control)
        self._worker.result_ready.connect(self._call_complete)
        self._worker.failed.connect(self._call_failed)
        self._worker.finished.connect(self._call_finished)
        self.call_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.hangup_button.setEnabled(False)
        self.result_view.setPlainText(
            json.dumps(
                {
                    "request_id": request.request_id,
                    "destination_masked": masked_destination(destination),
                    "state": "starting governed provider call",
                    "raw_destination_persisted": False,
                },
                indent=2,
            )
        )
        self._worker.start()

    def cancel_call(self) -> None:
        if self._control is not None:
            self._control.cancel()
            self.result_view.setPlainText(
                "Cancellation requested. The registered provider must honor the Telephony control checkpoint/time bound."
            )

    def _call_complete(self, run) -> None:
        self._last_run = run
        self.destination.clear()
        evidence_id = self._persist(run)
        self._last_evidence_id = evidence_id
        payload = run.evidence_metadata()
        payload.update(
            {
                "evidence_id": evidence_id,
                "software_path_qualified": run.qualified,
                "live_provider_evidence": any(
                    gate.gate_id == "telephony-live-provider-evidence" and gate.status.value == "pass"
                    for gate in run.gates
                ),
                "raw_destination_persisted": False,
            }
        )
        self.result_view.setPlainText(json.dumps(payload, indent=2, default=str))
        self.hangup_button.setEnabled(
            run.state is CallState.CONNECTED and run.result is not None and bool(run.result.call_id)
        )

    def _call_failed(self, exc) -> None:
        self.destination.clear()
        QMessageBox.warning(self, "Telephony Lab call", str(exc))

    def _call_finished(self) -> None:
        self.call_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._control = None

    def hangup_call(self) -> None:
        run = self._last_run
        if run is None or run.result is None or not run.result.call_id:
            return
        gate = self.telephony.hangup(run.provider, run.result.call_id)
        evidence_id = self._persist(run, extra_gates=(gate,))
        self._last_evidence_id = evidence_id
        self.hangup_button.setEnabled(False)
        payload = run.evidence_metadata()
        payload.update(
            {
                "hangup_gate": (gate.gate_id, gate.status.value),
                "final_evidence_id": evidence_id,
                "raw_destination_persisted": False,
            }
        )
        self.result_view.setPlainText(json.dumps(payload, indent=2, default=str))

    def _persist(self, run, *, extra_gates=()) -> str:
        result = run.result
        metrics = {"telephony_call_completion_rate": 1.0 if result and result.connected else 0.0}
        if result and result.connect_latency_ms is not None:
            metrics["telephony_connect_latency_ms"] = float(result.connect_latency_ms)
        if result and result.duration_ms is not None:
            metrics["telephony_duration_ms"] = float(result.duration_ms)
        provider = self.telephony.providers.get(run.provider)
        provenance = {
            "request_id": run.request_id,
            "destination_sha256": run.destination_digest,
            "destination_masked": run.destination_masked,
            "provider_sandbox": str(bool(getattr(provider, "sandbox", False))).lower(),
        }
        record = EvidenceRecord.build(
            experiment_id=f"telephony:{run.request_id}",
            baseline_key=f"telephony:{run.provider}",
            provider=run.provider,
            model="telephony-transport",
            device="owner-control-center",
            device_class="telephony",
            os_name="",
            language="und",
            route="telephony",
            fixture_refs=("telephony-loopback",),
            configuration={
                "raw_destination_retained": "false",
                "raw_call_audio_retained": "false",
            },
            provenance=provenance,
            metrics=metrics,
            gates=tuple(run.gates) + tuple(extra_gates),
        )
        self.evidence.append(record)
        return record.evidence_id

    def can_close(self) -> bool:
        if self._worker is not None and self._worker.isRunning():
            if self._control is not None:
                self._control.cancel()
            return False
        return True
