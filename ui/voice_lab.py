"""Owner-facing Vishnu Voice Lab control surface."""
from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ui.design_tokens import fit_window_to_screen, stylesheet as design_system_stylesheet
from voice.lab.catalog import all_capabilities, gaps, qualification_required
from voice.lab.comparison import ComparisonCandidate, ProviderComparison
from voice.lab.dashboard import VOICE_LAB_SECTIONS, snapshot
from voice.lab.evidence import EvidenceStore
from voice.lab.experiments import VoiceExperimentSpec
from voice.lab.fixtures import FixtureRegistry
from voice.lab.release import ReleaseManager
from voice.lab.runner import LabRunControl, VoiceExperimentRunner
from voice.lab.telephony import TelephonyLab, TelephonyPolicy


_CATEGORY_MAP = {
    "Conversation": {"conversation", "authority"},
    "STT": {"speech-recognition"},
    "TTS": {"speech-synthesis"},
    "Voice Profiles": {"identity", "voice-conversion"},
    "Voice Intelligence": {"intelligence"},
    "Multilingual": {"language"},
    "Realtime": {"providers", "conversation"},
    "Audio / Sensorium": {"sensorium", "content"},
    "Devices": {"devices", "qualification"},
    "Providers & Models": {"providers", "governance", "runtime"},
    "Telephony": {"communications"},
}

_RELIABILITY_METRICS = {"success_rate", "failure_recovery_rate", "provider_failures"}


class _ExperimentWorker(QThread):
    result_ready = pyqtSignal(object)
    failed = pyqtSignal(object)

    def __init__(self, runner, spec, control):
        super().__init__()
        self.runner = runner
        self.spec = spec
        self.control = control

    def run(self):
        try:
            self.result_ready.emit(self.runner.run(self.spec, control=self.control))
        except Exception as exc:
            self.failed.emit(exc)


class VoiceLabDialog(QDialog):
    def __init__(self, runtime, parent=None):
        super().__init__(parent)
        self.runtime = runtime
        settings = runtime.get("settings")
        models = runtime.get("models")
        settings = settings or getattr(models, "settings", None)
        data_dir = Path(getattr(settings, "data_dir", Path.home() / ".personal_ai"))
        self.store = EvidenceStore(data_dir / "voice_lab" / "evidence.sqlite3")
        self.fixtures = FixtureRegistry()
        self.runner = VoiceExperimentRunner(
            fixtures=self.fixtures,
            evidence=self.store,
            adapters=runtime.get("voice_lab_adapters", {}),
        )
        telephony_policy = runtime.get("voice_lab_telephony_policy")
        if not isinstance(telephony_policy, TelephonyPolicy):
            telephony_policy = TelephonyPolicy()
        self.telephony = TelephonyLab(
            policy=telephony_policy,
            providers=runtime.get("voice_lab_telephony_providers", {}),
        )
        self.release_manager = ReleaseManager(self.store)
        self._candidate = None
        self._approval = None
        self._worker = None
        self._run_control = None
        self.views = {}

        self.setWindowTitle("Vishnu — Voice Lab")
        fit_window_to_screen(self, preferred=(1080, 820), minimum=(780, 600))
        self.setStyleSheet(design_system_stylesheet())
        layout = QVBoxLayout(self)
        heading = QLabel("VISHNU VOICE LAB")
        heading.setStyleSheet("font-size:20px;font-weight:650")
        layout.addWidget(heading)
        notice = QLabel(
            "Isolated voice research, benchmarks and qualification. Production remains STT → Vishnu → TTS. "
            "The Lab never auto-promotes a provider, never treats simulator evidence as physical acoustic evidence, "
            "and keeps telephony default-off until an explicitly governed provider is injected."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        for section in VOICE_LAB_SECTIONS:
            if section == "Experiments":
                page = self._experiments_page()
            elif section == "Benchmarks":
                page = self._benchmarks_page()
            elif section == "Release":
                page = self._release_page()
            else:
                page = QWidget()
                page_layout = QVBoxLayout(page)
                view = QTextBrowser()
                self.views[section] = view
                page_layout.addWidget(view, 1)
            self.tabs.addTab(page, section)
        row = QHBoxLayout()
        refresh = QPushButton("Refresh Voice Lab")
        refresh.clicked.connect(self.refresh)
        row.addStretch(1)
        row.addWidget(refresh)
        layout.addLayout(row)
        self.refresh()

    def _experiments_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.exp_provider = QLineEdit("local")
        self.exp_model = QLineEdit("qualification-model")
        self.exp_device = QLineEdit("desktop")
        self.exp_language = QLineEdit("en")
        self.exp_fixtures = QLineEdit("clean-short")
        form.addRow("Lab adapter/provider", self.exp_provider)
        form.addRow("Exact model/revision label", self.exp_model)
        form.addRow("Device", self.exp_device)
        form.addRow("Language", self.exp_language)
        form.addRow("Fixture IDs", self.exp_fixtures)
        layout.addLayout(form)
        row = QHBoxLayout()
        self.run_button = QPushButton("Run isolated experiment")
        self.run_button.clicked.connect(self.run_experiment)
        self.cancel_button = QPushButton("Cancel experiment")
        self.cancel_button.clicked.connect(self.cancel_experiment)
        self.cancel_button.setEnabled(False)
        row.addWidget(self.run_button)
        row.addWidget(self.cancel_button)
        layout.addLayout(row)
        self.experiment_view = QTextBrowser()
        layout.addWidget(self.experiment_view, 1)
        return page

    def _benchmarks_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.benchmark_view = QTextBrowser()
        layout.addWidget(self.benchmark_view, 1)
        form = QFormLayout()
        self.compare_evidence_ids = QLineEdit()
        self.compare_evidence_ids.setPlaceholderText("two or more evidence IDs, comma-separated")
        self.compare_metrics = QLineEdit("wer,first_audio_latency_ms,real_time_factor")
        self.compare_lower = QLineEdit("wer,first_audio_latency_ms,real_time_factor")
        form.addRow("Compare evidence", self.compare_evidence_ids)
        form.addRow("Metrics", self.compare_metrics)
        form.addRow("Lower is better", self.compare_lower)
        layout.addLayout(form)
        compare = QPushButton("Compare exact fixtures")
        compare.clicked.connect(self.compare_evidence)
        layout.addWidget(compare)
        baseline_row = QHBoxLayout()
        self.baseline_evidence_id = QLineEdit()
        self.baseline_evidence_id.setPlaceholderText("qualified evidence ID to accept as its family baseline")
        accept = QPushButton("Accept immutable baseline")
        accept.clicked.connect(self.accept_baseline)
        baseline_row.addWidget(self.baseline_evidence_id, 1)
        baseline_row.addWidget(accept)
        layout.addLayout(baseline_row)
        self.comparison_view = QTextBrowser()
        layout.addWidget(self.comparison_view, 1)
        return page

    def _release_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.release_capabilities = QLineEdit()
        self.release_capabilities.setPlaceholderText("capability IDs, comma-separated")
        self.release_evidence = QLineEdit()
        self.release_evidence.setPlaceholderText("qualified evidence IDs, comma-separated")
        form.addRow("Capabilities", self.release_capabilities)
        form.addRow("Evidence", self.release_evidence)
        layout.addLayout(form)
        row = QHBoxLayout()
        prepare = QPushButton("Prepare immutable candidate")
        prepare.clicked.connect(self.prepare_release)
        approve = QPushButton("Owner approve candidate")
        approve.clicked.connect(self.approve_release)
        row.addWidget(prepare)
        row.addWidget(approve)
        layout.addLayout(row)
        self.release_view = QTextBrowser()
        layout.addWidget(self.release_view, 1)
        return page

    @staticmethod
    def _csv(value: str) -> tuple[str, ...]:
        return tuple(item.strip() for item in value.split(",") if item.strip())

    @staticmethod
    def _candidate_from_evidence(row):
        configuration = dict(row.get("configuration", ()))
        provenance = dict(row.get("provenance", ()))
        metrics = tuple((name, float(value)) for name, value in row.get("metrics", ()))
        reliability = tuple((name, value) for name, value in metrics if name in _RELIABILITY_METRICS)
        return ComparisonCandidate(
            row["evidence_id"],
            tuple(row.get("fixture_refs", ())),
            metrics,
            privacy=provenance.get("privacy") or configuration.get("metadata:privacy", "unspecified"),
            hardware=provenance.get("hardware") or configuration.get("metadata:hardware", "unspecified"),
            licensing=provenance.get("licensing") or configuration.get("metadata:licensing", "unspecified"),
            cost=provenance.get("cost") or configuration.get("metadata:cost", "unspecified"),
            reliability=reliability,
        )

    def run_experiment(self):
        if self._worker is not None and self._worker.isRunning():
            return
        try:
            spec = VoiceExperimentSpec(
                title="Owner Voice Lab experiment",
                provider=self.exp_provider.text().strip(),
                model=self.exp_model.text().strip(),
                device=self.exp_device.text().strip(),
                language=self.exp_language.text().strip(),
                fixture_refs=self._csv(self.exp_fixtures.text()),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Voice Lab experiment", str(exc))
            return
        self._run_control = LabRunControl.bounded(120.0)
        self._worker = _ExperimentWorker(self.runner, spec, self._run_control)
        self._worker.result_ready.connect(self._experiment_complete)
        self._worker.failed.connect(self._experiment_failed)
        self._worker.finished.connect(self._experiment_finished)
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.experiment_view.setPlainText("Experiment running in the isolated Lab adapter. Production voice is unchanged.")
        self._worker.start()

    def cancel_experiment(self):
        if self._run_control is not None:
            self._run_control.cancel()
            self.experiment_view.setPlainText(
                "Cancellation requested. In-process adapters stop at a control checkpoint; "
                "BoundedSubprocessAdapter can terminate an external child process at the deadline."
            )

    def _experiment_complete(self, result):
        self.experiment_view.setPlainText(
            json.dumps(
                {
                    "evidence_id": result.evidence_id,
                    "status": result.report.status.value,
                    "non_passing_gates": result.report.non_passing_gate_ids,
                    "automatic_regressions": result.regressions,
                },
                indent=2,
            )
        )
        self.baseline_evidence_id.setText(result.evidence_id)
        self.refresh()

    def _experiment_failed(self, exc):
        QMessageBox.warning(self, "Voice Lab experiment", str(exc))

    def _experiment_finished(self):
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._run_control = None

    def accept_baseline(self):
        evidence_id = self.baseline_evidence_id.text().strip()
        row = self.store.get(evidence_id) if evidence_id else None
        if row is None:
            QMessageBox.warning(self, "Voice Lab baseline", "Choose an existing evidence record.")
            return
        gates = row.get("gates", [])
        if any(gate.get("status") != "pass" for gate in gates):
            QMessageBox.warning(self, "Voice Lab baseline", "Only fully passing evidence can become a baseline.")
            return
        try:
            self.store.accept_baseline(row["baseline_key"], evidence_id)
            self.comparison_view.setPlainText(
                json.dumps({"accepted_baseline": row["baseline_key"], "evidence_id": evidence_id}, indent=2)
            )
        except Exception as exc:
            QMessageBox.warning(self, "Voice Lab baseline", str(exc))

    def compare_evidence(self):
        ids = self._csv(self.compare_evidence_ids.text())
        rows = [self.store.get(evidence_id) for evidence_id in ids]
        if len(ids) < 2 or any(row is None for row in rows):
            QMessageBox.warning(self, "Voice Lab comparison", "Provide at least two existing evidence IDs.")
            return
        candidates = tuple(self._candidate_from_evidence(row) for row in rows)
        result = ProviderComparison(
            candidates,
            self._csv(self.compare_metrics.text()),
            self._csv(self.compare_lower.text()),
        ).evaluate()
        self.comparison_view.setPlainText(json.dumps(result, indent=2, default=str))

    def prepare_release(self):
        try:
            self._candidate = self.release_manager.prepare(
                self._csv(self.release_capabilities.text()),
                self._csv(self.release_evidence.text()),
            )
            self._approval = None
            self._refresh_release_view()
        except Exception as exc:
            QMessageBox.warning(self, "Release candidate blocked", str(exc))

    def approve_release(self):
        if self._candidate is None:
            QMessageBox.information(self, "Voice Lab release", "Prepare an exact qualified candidate first.")
            return
        owner = self.runtime.get("owner_access")
        if not owner or not owner.password_configured():
            QMessageBox.warning(self, "Owner approval", "Configure owner reauthentication before release approval.")
            return
        password, ok = QInputDialog.getText(self, "Owner approval", "Owner password:", QLineEdit.EchoMode.Password)
        if not ok or not owner.verify_password(password):
            QMessageBox.warning(self, "Owner approval", "Owner reauthentication failed. Nothing was approved.")
            return
        attestation, ok = QInputDialog.getText(
            self,
            "Release attestation",
            "Attestation for this exact candidate:",
        )
        if not ok or not attestation.strip():
            return
        self._approval = self.release_manager.approve(
            self._candidate,
            owner_id="owner",
            attestation=attestation,
        )
        self._refresh_release_view()

    def _refresh_release_view(self):
        if self._candidate is None:
            self.release_view.setPlainText(
                "No release candidate prepared. Voice Lab never changes production or Git refs automatically."
            )
            return
        decision = self.release_manager.evaluate(self._candidate, self._approval)
        self.release_view.setPlainText(
            json.dumps(
                {
                    "candidate_id": self._candidate.candidate_id,
                    "manifest_digest": self._candidate.manifest_digest,
                    "owner_approved": self._approval is not None,
                    "ready_to_request_separate_promotion": decision.allowed,
                    "reasons": decision.reasons,
                    "production_mutated": False,
                },
                indent=2,
            )
        )

    def refresh(self):
        recent = self.store.list_recent(100)
        snap = snapshot(evidence_count=len(recent), experiment_count=len({row["experiment_id"] for row in recent}))
        overview = {
            "sections": snap.sections,
            "capabilities": snap.capabilities,
            "known_gaps": snap.gaps,
            "qualification_required": snap.qualification_required,
            "evidence_records": snap.evidence_count,
            "experiments": snap.experiment_count,
            "registered_lab_adapters": sorted(self.runner.adapters),
            "registered_telephony_adapters": self.telephony.registered_providers(),
            "raw_audio_retained_by_evidence_store": False,
        }
        self.views["Overview"].setPlainText(json.dumps(overview, indent=2))
        capabilities = all_capabilities()
        for section, categories in _CATEGORY_MAP.items():
            rows = [
                {"id": item.capability_id, "title": item.title, "state": item.state.value, "notes": item.qualification_notes}
                for item in capabilities
                if item.category in categories
            ]
            self.views[section].setPlainText(json.dumps(rows, indent=2))
        telephony_capabilities = [
            {"id": item.capability_id, "title": item.title, "state": item.state.value, "notes": item.qualification_notes}
            for item in capabilities
            if item.category == "communications"
        ]
        self.views["Telephony"].setPlainText(
            json.dumps(
                {
                    "capabilities": telephony_capabilities,
                    "policy": {
                        "enabled": self.telephony.policy.enabled,
                        "allow_outbound": self.telephony.policy.allow_outbound,
                        "allow_inbound": self.telephony.policy.allow_inbound,
                        "allow_recording": self.telephony.policy.allow_recording,
                        "allow_live_provider": self.telephony.policy.allow_live_provider,
                        "max_call_seconds": self.telephony.policy.max_call_seconds,
                    },
                    "registered_providers": self.telephony.registered_providers(),
                    "owner_approval": "exact request required by default",
                    "recording": "off unless policy + consent + exact approval allow it",
                    "emergency_calls": "blocked in Voice Lab",
                    "destination_evidence": "masked plus SHA-256 fingerprint; raw destination is not evidence metadata",
                },
                indent=2,
            )
        )
        self.benchmark_view.setPlainText(json.dumps(recent, indent=2, default=str))
        self.views["Qualification"].setPlainText(
            json.dumps(
                {
                    "qualification_required": [item.capability_id for item in qualification_required()],
                    "gaps": [item.capability_id for item in gaps()],
                    "automatic_regression": "runs whenever an immutable baseline exists for the experiment family",
                    "hard_timeout_adapter": "BoundedSubprocessAdapter terminates external experiments on cancellation/deadline",
                    "telephony": "software framework implemented; live provider/number/jurisdiction quality remains exact evidence",
                    "rule": "Missing, blocked or not-run evidence never becomes PASS.",
                },
                indent=2,
            )
        )
        if not self.experiment_view.toPlainText():
            self.experiment_view.setPlainText(
                json.dumps(
                    {
                        "fixtures": [item.fixture_id for item in self.fixtures.list()],
                        "registered_adapters": sorted(self.runner.adapters),
                        "note": "No adapter is contacted unless explicitly injected into the Voice Lab runtime.",
                    },
                    indent=2,
                )
            )
        self._refresh_release_view()

    def closeEvent(self, event):
        if self._worker is not None and self._worker.isRunning():
            if self._run_control is not None:
                self._run_control.cancel()
            QMessageBox.information(
                self,
                "Voice Lab experiment",
                "Cancellation was requested. Close Voice Lab after the Lab adapter acknowledges the stop checkpoint.",
            )
            event.ignore()
            return
        super().closeEvent(event)
