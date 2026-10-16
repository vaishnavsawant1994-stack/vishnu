"""Owner-facing Vishnu Voice Lab control surface.

Opening this dialog does not start a microphone, provider, model download or production voice route.
Experiments run only through adapters explicitly injected as runtime['voice_lab_adapters'].
"""
from __future__ import annotations

import json
from pathlib import Path

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
from voice.lab.dashboard import VOICE_LAB_SECTIONS, snapshot
from voice.lab.evidence import EvidenceStore
from voice.lab.experiments import VoiceExperimentSpec
from voice.lab.fixtures import FixtureRegistry
from voice.lab.release import ReleaseManager
from voice.lab.runner import VoiceExperimentRunner


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
}


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
        self.release_manager = ReleaseManager(self.store)
        self._candidate = None
        self._approval = None
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
            "The Lab never auto-promotes a provider or treats simulator evidence as physical acoustic evidence."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)
        for section in VOICE_LAB_SECTIONS:
            if section == "Experiments":
                page = self._experiments_page()
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
        run = QPushButton("Run isolated experiment")
        run.clicked.connect(self.run_experiment)
        layout.addWidget(run)
        self.experiment_view = QTextBrowser()
        layout.addWidget(self.experiment_view, 1)
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

    def run_experiment(self):
        try:
            spec = VoiceExperimentSpec(
                title="Owner Voice Lab experiment",
                provider=self.exp_provider.text().strip(),
                model=self.exp_model.text().strip(),
                device=self.exp_device.text().strip(),
                language=self.exp_language.text().strip(),
                fixture_refs=self._csv(self.exp_fixtures.text()),
            )
            result = self.runner.run(spec)
            self.experiment_view.setPlainText(
                json.dumps(
                    {
                        "experiment_id": spec.experiment_id,
                        "evidence_id": result.evidence_id,
                        "status": result.report.status.value,
                        "non_passing_gates": result.report.non_passing_gate_ids,
                    },
                    indent=2,
                )
            )
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Voice Lab experiment", str(exc))

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
        password, ok = QInputDialog.getText(
            self,
            "Owner approval",
            "Owner password:",
            QLineEdit.EchoMode.Password,
        )
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
            "raw_audio_retained_by_evidence_store": False,
        }
        self.views["Overview"].setPlainText(json.dumps(overview, indent=2))
        capabilities = all_capabilities()
        for section, categories in _CATEGORY_MAP.items():
            rows = [
                {
                    "id": item.capability_id,
                    "title": item.title,
                    "state": item.state.value,
                    "notes": item.qualification_notes,
                }
                for item in capabilities
                if item.category in categories
            ]
            self.views[section].setPlainText(json.dumps(rows, indent=2))
        self.views["Benchmarks"].setPlainText(json.dumps(recent, indent=2, default=str))
        self.views["Qualification"].setPlainText(
            json.dumps(
                {
                    "qualification_required": [item.capability_id for item in qualification_required()],
                    "gaps": [item.capability_id for item in gaps()],
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
