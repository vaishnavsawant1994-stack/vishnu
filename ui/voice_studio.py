from __future__ import annotations

import io
import json
from pathlib import Path

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
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
from voice.intelligence import (
    BUILTIN_VOICE_PACKS,
    SUPPORTED_VOICE_STYLES,
    VoicePersona,
    VoicePreferences,
)
from voice.platform import VoiceIntelligenceService


class VoiceStudioDialog(QDialog):
    """Owner UI for presentation policy and the existing governed voice registry."""

    def __init__(self, runtime, parent=None):
        super().__init__(parent)
        self.runtime = runtime
        models = runtime.get("models")
        if models is None:
            raise RuntimeError("model router is unavailable")
        settings = runtime.get("settings") or getattr(models, "settings", None)
        data_dir = Path(getattr(settings, "data_dir", Path.home() / ".personal_ai"))
        self.service = VoiceIntelligenceService(models, data_dir=data_dir)
        self.setWindowTitle("Vishnu — Voice Studio")
        fit_window_to_screen(self, preferred=(920, 760), minimum=(720, 560))
        self.setStyleSheet(design_system_stylesheet())

        layout = QVBoxLayout(self)
        heading = QLabel("VISHNU VOICE STUDIO")
        heading.setStyleSheet("font-size:20px;font-weight:650")
        layout.addWidget(heading)
        intro = QLabel(
            "Personas control presentation, language and expression. Authorized voices remain "
            "consent-gated by Vishnu's existing governed profile registry."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._preferences_tab(), "Voice & expression")
        self.tabs.addTab(self._personas_tab(), "Personas")
        self.tabs.addTab(self._profiles_tab(), "Authorized voices")
        self.tabs.addTab(self._pronunciation_tab(), "Pronunciation")
        self.tabs.addTab(self._status_tab(), "Status")
        layout.addWidget(self.tabs, 1)
        self.refresh_all()

    def _preferences_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        form = QFormLayout()
        self.default_persona = QComboBox()
        self.default_language = QLineEdit()
        self.default_language.setPlaceholderText("en, en-GB, hi, mr, de-DE …")
        self.default_style = QComboBox()
        self.default_style.addItem("Automatic", "")
        for style in SUPPORTED_VOICE_STYLES:
            self.default_style.addItem(style.title(), style)
        self.speaking_rate = self._number(0.65, 1.5, 0.05, 2)
        self.expression_intensity = self._number(0.0, 2.0, 0.1, 1)
        self.formality = self._number(0.0, 1.0, 0.1, 1)
        form.addRow("Default persona", self.default_persona)
        form.addRow("Preferred language", self.default_language)
        form.addRow("Expression style", self.default_style)
        form.addRow("Speaking rate", self.speaking_rate)
        form.addRow("Expression intensity", self.expression_intensity)
        form.addRow("Formality", self.formality)
        layout.addLayout(form)
        save = QPushButton("Save voice preferences")
        save.clicked.connect(self.save_preferences)
        layout.addWidget(save)
        layout.addWidget(QLabel("Test sentence"))
        self.test_text = QLineEdit("Hello. I am Vishnu, and this is my current voice persona.")
        layout.addWidget(self.test_text)
        test = QPushButton("Generate & play")
        test.clicked.connect(self.test_voice)
        layout.addWidget(test)
        self.test_result = QTextBrowser()
        self.test_result.setMaximumHeight(160)
        layout.addWidget(self.test_result)
        layout.addStretch(1)
        return page

    def _personas_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        notice = QLabel(
            "Built-in Vishnu packs cannot be overwritten or deleted. Custom personas can reference only "
            "an already enrolled governed voice profile ID."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.persona_view = QTextBrowser()
        layout.addWidget(self.persona_view, 1)
        row = QHBoxLayout()
        create = QPushButton("Create custom persona")
        create.clicked.connect(self.create_persona)
        delete = QPushButton("Delete custom persona")
        delete.clicked.connect(self.delete_persona)
        row.addWidget(create)
        row.addWidget(delete)
        row.addStretch(1)
        layout.addLayout(row)
        return page

    def _profiles_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        notice = QLabel(
            "Enrollment is local-only and requires explicit consent attestation plus owner reauthentication. "
            "Synthesis never accepts an arbitrary clone URL or unmanaged reference path."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        self.profile_view = QTextBrowser()
        layout.addWidget(self.profile_view, 1)
        row = QHBoxLayout()
        enroll = QPushButton("Enroll authorized WAV…")
        enroll.clicked.connect(self.enroll_profile)
        revoke = QPushButton("Revoke profile")
        revoke.clicked.connect(self.revoke_profile)
        delete = QPushButton("Delete profile")
        delete.clicked.connect(self.delete_profile)
        row.addWidget(enroll)
        row.addWidget(revoke)
        row.addWidget(delete)
        row.addStretch(1)
        layout.addLayout(row)
        return page

    def _pronunciation_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        notice = QLabel(
            "Pronunciation entries are local presentation hints. They do not rewrite semantic text or retain transcripts."
        )
        notice.setWordWrap(True)
        layout.addWidget(notice)
        form = QFormLayout()
        self.pronunciation_term = QLineEdit()
        self.pronunciation_value = QLineEdit()
        form.addRow("Term", self.pronunciation_term)
        form.addRow("Pronunciation hint", self.pronunciation_value)
        layout.addLayout(form)
        row = QHBoxLayout()
        save = QPushButton("Save pronunciation")
        save.clicked.connect(self.save_pronunciation)
        remove = QPushButton("Remove pronunciation")
        remove.clicked.connect(self.remove_pronunciation)
        row.addWidget(save)
        row.addWidget(remove)
        row.addStretch(1)
        layout.addLayout(row)
        self.pronunciation_view = QTextBrowser()
        layout.addWidget(self.pronunciation_view, 1)
        return page

    def _status_tab(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.status_view = QTextBrowser()
        layout.addWidget(self.status_view, 1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_all)
        layout.addWidget(refresh)
        return page

    @staticmethod
    def _number(minimum, maximum, step, decimals):
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setSingleStep(step)
        widget.setDecimals(decimals)
        return widget

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: str):
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def refresh_all(self):
        self.service.refresh()
        personas = self.service.list_personas()
        self.default_persona.blockSignals(True)
        self.default_persona.clear()
        self.default_persona.addItem("Automatic / Vishnu Original", "")
        for persona in personas:
            self.default_persona.addItem(persona["name"], persona["id"])
        self.default_persona.blockSignals(False)

        preferences = self.service.preferences()
        self._set_combo_data(self.default_persona, preferences.persona_id or "")
        self.default_language.setText(preferences.language or "")
        self._set_combo_data(self.default_style, preferences.style or "")
        self.speaking_rate.setValue(preferences.speaking_rate or 1.0)
        self.expression_intensity.setValue(preferences.expression_intensity)
        self.formality.setValue(preferences.formality if preferences.formality is not None else 0.5)

        self.persona_view.setPlainText(json.dumps(personas, indent=2, default=str))
        self.profile_view.setPlainText(json.dumps(self.service.list_voice_profiles(), indent=2, default=str))
        self.pronunciation_view.setPlainText(json.dumps(dict(self.service.lexicon.items()), indent=2))
        self.status_view.setPlainText(json.dumps(self.service.status(), indent=2, default=str))

    def save_preferences(self):
        try:
            self.service.set_preferences(
                VoicePreferences(
                    persona_id=self.default_persona.currentData() or None,
                    language=self.default_language.text().strip() or None,
                    style=self.default_style.currentData() or None,
                    speaking_rate=float(self.speaking_rate.value()),
                    expression_intensity=float(self.expression_intensity.value()),
                    formality=float(self.formality.value()),
                )
            )
            self.refresh_all()
            QMessageBox.information(self, "Voice preferences", "Voice preferences saved locally.")
        except Exception as exc:
            QMessageBox.warning(self, "Voice preferences", str(exc))

    def test_voice(self):
        text = self.test_text.text().strip()
        if not text:
            return
        try:
            result = self.service.synthesize(text)
            self.test_result.setPlainText(
                json.dumps(
                    {
                        "plan": result.plan.public(),
                        "quality": result.quality,
                        "pronunciation_hints": result.pronunciation_hints,
                        "language_segments": result.language_segments,
                    },
                    indent=2,
                    default=str,
                )
            )
            try:
                import sounddevice as sd
                import soundfile as sf

                audio, sample_rate = sf.read(io.BytesIO(result.audio), dtype="float32")
                sd.play(audio, sample_rate)
            except Exception:
                QMessageBox.information(
                    self,
                    "Voice generated",
                    "Audio was generated, but this desktop could not start local playback.",
                )
        except Exception as exc:
            QMessageBox.warning(self, "Voice test failed", str(exc))

    def create_persona(self):
        persona_id, ok = QInputDialog.getText(self, "Persona ID", "Stable persona ID:")
        if not ok:
            return
        name, ok = QInputDialog.getText(self, "Persona name", "Display name:")
        if not ok:
            return
        style, ok = QInputDialog.getItem(
            self,
            "Persona style",
            "Default expression style:",
            list(SUPPORTED_VOICE_STYLES),
            editable=False,
        )
        if not ok:
            return
        active_profiles = [row["profile_id"] for row in self.service.list_voice_profiles() if row.get("active")]
        profile, ok = QInputDialog.getItem(
            self,
            "Authorized voice",
            "Governed enrolled voice profile:",
            ["(no conversion)", *active_profiles],
            editable=False,
        )
        if not ok:
            return
        language, ok = QInputDialog.getText(self, "Language", "Default language:", text="en")
        if not ok:
            return
        try:
            self.service.put_persona(
                VoicePersona(
                    persona_id.strip(),
                    name.strip(),
                    voice_profile_id=None if profile == "(no conversion)" else profile,
                    language=language.strip(),
                    style=style,
                )
            )
            self.refresh_all()
        except Exception as exc:
            QMessageBox.warning(self, "Persona not created", str(exc))

    def delete_persona(self):
        custom = [row for row in self.service.list_personas() if row["id"] not in BUILTIN_VOICE_PACKS]
        if not custom:
            QMessageBox.information(self, "Personas", "There are no custom personas to delete.")
            return
        persona_id, ok = QInputDialog.getItem(
            self,
            "Delete persona",
            "Custom persona:",
            [row["id"] for row in custom],
            editable=False,
        )
        if not ok:
            return
        if QMessageBox.question(self, "Delete persona", f"Delete custom persona {persona_id}?") != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.delete_persona(persona_id)
            self.refresh_all()
        except Exception as exc:
            QMessageBox.warning(self, "Persona not deleted", str(exc))

    def enroll_profile(self):
        if not self._reauthenticated("enroll an authorized voice"):
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select authorized reference WAV",
            str(Path.home()),
            "WAV audio (*.wav)",
        )
        if not path:
            return
        display_name, ok = QInputDialog.getText(self, "Voice name", "Display name:")
        if not ok:
            return
        purpose, ok = QInputDialog.getText(self, "Allowed purpose", "Purpose for this enrolled voice:")
        if not ok:
            return
        if QMessageBox.question(
            self,
            "Consent attestation",
            "Do you attest that the voice subject explicitly authorized this enrollment and stated purpose?",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.enroll_voice_profile(
                Path(path).read_bytes(),
                display_name=display_name,
                purpose=purpose,
                consent_attested=True,
            )
            self.refresh_all()
            QMessageBox.information(self, "Voice enrolled", "The authorized voice was stored locally.")
        except Exception as exc:
            QMessageBox.warning(self, "Voice not enrolled", str(exc))

    def revoke_profile(self):
        rows = [row for row in self.service.list_voice_profiles() if row.get("active") and not row.get("canonical")]
        profile_id = self._choose_profile(rows, "Revoke voice profile")
        if not profile_id or not self._reauthenticated("revoke a voice profile"):
            return
        try:
            self.service.revoke_voice_profile(profile_id)
            self.refresh_all()
        except Exception as exc:
            QMessageBox.warning(self, "Voice not revoked", str(exc))

    def delete_profile(self):
        rows = [row for row in self.service.list_voice_profiles() if not row.get("canonical")]
        profile_id = self._choose_profile(rows, "Delete voice profile")
        if not profile_id or not self._reauthenticated("delete a voice profile"):
            return
        if QMessageBox.question(
            self,
            "Delete voice profile",
            f"Permanently delete {profile_id} and its local reference audio?",
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.delete_voice_profile(profile_id)
            self.refresh_all()
        except Exception as exc:
            QMessageBox.warning(self, "Voice not deleted", str(exc))

    def _choose_profile(self, rows: list[dict], title: str) -> str | None:
        if not rows:
            QMessageBox.information(self, title, "No eligible voice profiles are available.")
            return None
        value, ok = QInputDialog.getItem(
            self,
            title,
            "Voice profile:",
            [row["profile_id"] for row in rows],
            editable=False,
        )
        return value if ok else None

    def save_pronunciation(self):
        try:
            self.service.set_pronunciation(
                self.pronunciation_term.text().strip(),
                self.pronunciation_value.text().strip(),
            )
            self.pronunciation_term.clear()
            self.pronunciation_value.clear()
            self.refresh_all()
        except Exception as exc:
            QMessageBox.warning(self, "Pronunciation not saved", str(exc))

    def remove_pronunciation(self):
        term = self.pronunciation_term.text().strip()
        if not term:
            existing = [item[0] for item in self.service.lexicon.items()]
            if not existing:
                return
            term, ok = QInputDialog.getItem(
                self,
                "Remove pronunciation",
                "Term:",
                existing,
                editable=False,
            )
            if not ok:
                return
        self.service.remove_pronunciation(term)
        self.pronunciation_term.clear()
        self.pronunciation_value.clear()
        self.refresh_all()

    def _reauthenticated(self, action: str) -> bool:
        owner = self.runtime.get("owner_access")
        if owner is None or not owner.password_configured():
            QMessageBox.warning(
                self,
                "Owner reauthentication required",
                f"Configure the owner password before you {action}.",
            )
            return False
        password, ok = QInputDialog.getText(
            self,
            "Owner reauthentication",
            f"Enter the owner password to {action}:",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return False
        if not owner.verify_password(password):
            QMessageBox.warning(self, "Owner reauthentication", "Owner reauthentication failed. Nothing changed.")
            return False
        return True
