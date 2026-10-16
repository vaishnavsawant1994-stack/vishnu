from __future__ import annotations

import json

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
)

from ui.design_tokens import fit_window_to_screen, stylesheet as design_system_stylesheet
from ui.voice_studio import VoiceStudioDialog
from voice.platform import VoiceIntelligenceService


class ControlPanel(QDialog):
    def __init__(self, runtime, parent=None):
        super().__init__(parent)
        self.runtime = runtime
        self.setWindowTitle("Vishnu — Owner Control Center")
        fit_window_to_screen(self, preferred=(900, 650))
        self.setStyleSheet(design_system_stylesheet())

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("OWNER CONTROL CENTER"))
        top.addStretch(1)

        voice = QPushButton("Voice Studio")
        voice.setToolTip("Manage Vishnu voice personas, expression, pronunciation and authorized voices")
        voice.clicked.connect(self.open_voice_studio)
        top.addWidget(voice)

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        top.addWidget(refresh)
        layout.addLayout(top)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.views = {}
        for name in [
            "Overview",
            "Devices & Presence",
            "Automations",
            "Integrations",
            "Models",
            "Voice",
            "Privacy & Data",
            "Security",
            "Preferences",
        ]:
            view = QTextBrowser()
            self.views[name] = view
            self.tabs.addTab(view, name)
        self.refresh()

    def open_voice_studio(self):
        try:
            VoiceStudioDialog(self.runtime, self).exec()
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Voice Studio", f"Voice Studio is unavailable: {type(exc).__name__}")

    def _voice_status(self) -> dict:
        models = self.runtime.get("models")
        settings = self.runtime.get("settings") or getattr(models, "settings", None)
        if models is None or settings is None:
            return {"available": False}
        try:
            service = VoiceIntelligenceService(models, data_dir=settings.data_dir)
            return {"available": True, **service.status()}
        except Exception as exc:
            return {"available": False, "error_type": type(exc).__name__}

    def refresh(self):
        runtime = self.runtime
        graph = runtime["second_brain"].graph()
        self.views["Overview"].setPlainText(
            json.dumps(
                {
                    "memory_nodes": len(graph.get("nodes", [])),
                    "memory_edges": len(graph.get("edges", [])),
                    "tools": len(runtime["tools"].all()),
                    "automations": len(runtime["automations"].list()),
                    "devices": len(runtime["device_registry"].list()),
                    "voice_intelligence": self._voice_status().get("available", False),
                },
                indent=2,
            )
        )

        devices = []
        online = set(runtime["device_gateway"].online()) if runtime.get("device_gateway") else set()
        for item in runtime["device_registry"].list():
            active = not bool(item.get("revoked"))
            device_id = item.get("id")
            devices.append(
                {
                    "device_id": device_id,
                    "platform": item.get("platform"),
                    "trust_state": "trusted" if active else "revoked",
                    "presence_state": (
                        "online"
                        if active and device_id in online
                        else ("revoked" if not active else "unknown")
                    ),
                    "last_seen_at": item.get("last_seen_at"),
                    "permissions": item.get("permissions", []),
                }
            )
        self.views["Devices & Presence"].setPlainText(json.dumps(devices, indent=2, default=str))
        self.views["Automations"].setPlainText(
            json.dumps(runtime["automations"].list(), indent=2, default=str)
        )
        self.views["Integrations"].setPlainText(
            json.dumps(runtime["integrations"].list(), indent=2, default=str)
        )

        models = runtime.get("models")
        model_status = (
            models.health_status(probe=False)
            if models and hasattr(models, "health_status")
            else {"available": bool(models)}
        )
        self.views["Models"].setPlainText(json.dumps(model_status, indent=2, default=str))
        self.views["Voice"].setPlainText(json.dumps(self._voice_status(), indent=2, default=str))

        preferences = runtime["preferences"].snapshot()
        self.views["Privacy & Data"].setPlainText(
            json.dumps(
                {
                    "sensitive_memory_remote_access": "scope-gated",
                    "secret_store_exported_in_backups": False,
                    "backup_service": "available" if runtime.get("backups") else "unavailable",
                    "device_presence": "live-evidence-only",
                    "permission_default": "deny",
                    "model_privacy_mode": preferences.get("model_privacy_mode", "local_preferred"),
                },
                indent=2,
            )
        )
        self.views["Preferences"].setPlainText(
            json.dumps(
                {
                    "wake_phrase": preferences.get("wake_phrase"),
                    "launch_voice_on_start": preferences.get("launch_voice_on_start"),
                    "show_memory_hints": preferences.get("show_memory_hints"),
                    "reduce_motion": preferences.get("reduce_motion"),
                    "high_contrast": preferences.get("high_contrast"),
                    "autonomy_mode": preferences.get("autonomy_mode"),
                    "model_privacy_mode": preferences.get("model_privacy_mode"),
                },
                indent=2,
                default=str,
            )
        )
        self.views["Security"].setPlainText(
            json.dumps(
                {
                    "autonomy_mode": runtime["tools"].settings.autonomy_mode,
                    "vault_enabled": runtime.get("vault") is not None,
                    "remote_control": "authenticated device bearer token",
                    "pairing": "loopback initiated",
                    "browser_profile": "persistent local profile",
                    "voice_enrollment": "owner-reauthenticated + explicit-consent",
                },
                indent=2,
            )
        )
