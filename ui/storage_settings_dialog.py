from __future__ import annotations

import json

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from data_plane.policy import CloudMode, StoragePolicy
from data_plane.provider_bridge import connect_runtime_provider, runtime_provider_reference
from data_plane.runtime import get_data_plane
from ui.design_tokens import fit_window_to_screen, stylesheet as design_system_stylesheet


class StorageSettingsDialog(QDialog):
    """Owner-facing local-first storage policy and provider controls."""

    def __init__(self, runtime, parent=None):
        super().__init__(parent)
        self.runtime = runtime
        self.data_plane = get_data_plane(runtime)
        if self.data_plane is None:
            raise RuntimeError('Data & Cloud Storage requires the canonical Vishnu settings/data directory')
        self.setWindowTitle('Data & Cloud Storage')
        fit_window_to_screen(self, preferred=(760, 860))
        self.setStyleSheet(design_system_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)
        layout.addWidget(QLabel('<h2>Data & Cloud Storage</h2>'))
        layout.addWidget(QLabel(
            'Local-first is the permanent baseline. Online storage is optional. '
            'Device-only data never becomes a permanent copy elsewhere unless you explicitly change its policy.'
        ))
        ai_note = QLabel(
            '<b>Storage and AI are separate.</b> Turning online storage off does not disable Claude, OpenAI, Gemini or local models. '
            'AI-provider controls remain under AI Providers; only context you authorize may be sent for inference.'
        )
        ai_note.setWordWrap(True)
        layout.addWidget(ai_note)

        self.cloud = QCheckBox('Enable online / cloud storage')
        self.cloud.setToolTip('Master switch. When OFF, new cloud provider use is denied below the UI. Existing remote bytes are not silently deleted.')
        layout.addWidget(self.cloud)

        form = QFormLayout()
        self.cloud_mode = QComboBox()
        self.cloud_mode.addItem('Local only', CloudMode.LOCAL_ONLY.value)
        self.cloud_mode.addItem('My own cloud', CloudMode.OWN_CLOUD.value)
        self.cloud_mode.addItem('Vishnu Cloud', CloudMode.VISHNU_CLOUD.value)
        self.cloud_mode.addItem('Hybrid', CloudMode.HYBRID.value)
        form.addRow('Storage mode', self.cloud_mode)

        self.default_policy = QComboBox()
        self.default_policy.addItem('Keep only here', StoragePolicy.DEVICE_ONLY.value)
        self.default_policy.addItem('Sync everywhere', StoragePolicy.SYNC_EVERYWHERE.value)
        self.default_policy.addItem('Sync progress only', StoragePolicy.PROGRESS_ONLY.value)
        self.default_policy.addItem('On demand', StoragePolicy.ON_DEMAND.value)
        self.default_policy.setToolTip('On demand syncs location/reference metadata; bytes materialize only through a separately authorized transfer.')
        form.addRow('Default data rule', self.default_policy)
        layout.addLayout(form)

        self.remote_access = QCheckBox('Allow secure remote view/use from my trusted devices')
        self.remote_access.setToolTip('Viewing does not grant permanent copy/move authority.')
        layout.addWidget(self.remote_access)
        self.backup = QCheckBox('Allow optional encrypted online backup')
        layout.addWidget(self.backup)

        cloud_warning = QLabel(
            'Cloud OFF prevents future Vishnu cloud-storage operations. It does not claim that copies already stored at a provider were deleted. '
            'Removing an existing remote copy must be a separately verified action before an item can be declared device-only.'
        )
        cloud_warning.setWordWrap(True)
        layout.addWidget(cloud_warning)

        save_row = QHBoxLayout()
        self.owner_password = QLineEdit()
        self.owner_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.owner_password.setPlaceholderText('Owner password for storage policy changes')
        save = QPushButton('Save data policy')
        save.clicked.connect(self.save_policy)
        save_row.addWidget(self.owner_password, 1)
        save_row.addWidget(save)
        layout.addLayout(save_row)

        layout.addWidget(QLabel('<h3>Online storage providers</h3>'))
        layout.addWidget(QLabel(
            'Providers can be combined. Existing governed Vishnu connections are reused when possible. '
            'A provider is available only after a real connector/native bridge/managed service or vault-backed adapter verifies.'
        ))
        provider_row = QHBoxLayout()
        self.provider = QComboBox()
        self.provider_ref = QLineEdit()
        self.provider_ref.setPlaceholderText('Connector or vault reference (never a raw API key)')
        provider_row.addWidget(self.provider, 1)
        provider_row.addWidget(self.provider_ref, 2)
        layout.addLayout(provider_row)

        buttons = QHBoxLayout()
        enable = QPushButton('Enable provider')
        enable.clicked.connect(lambda: self.set_provider(True))
        disable = QPushButton('Disable provider')
        disable.clicked.connect(lambda: self.set_provider(False))
        refresh = QPushButton('Refresh')
        refresh.clicked.connect(self.refresh)
        buttons.addWidget(enable)
        buttons.addWidget(disable)
        buttons.addWidget(refresh)
        layout.addLayout(buttons)

        self.status = QPlainTextEdit()
        self.status.setReadOnly(True)
        layout.addWidget(self.status, 1)
        self.refresh()

    def _reauthenticated(self) -> bool:
        owner = self.runtime.get('owner_access')
        password = self.owner_password.text()
        self.owner_password.clear()
        if not owner or not owner.password_configured():
            QMessageBox.warning(self, 'Reauthentication required', 'Configure the owner password before changing storage authority.')
            return False
        if not owner.verify_password(password):
            QMessageBox.warning(self, 'Reauthentication required', 'Owner reauthentication failed. Nothing was changed.')
            return False
        return True

    def _select_data(self, combo: QComboBox, value: str):
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def refresh(self):
        current_provider = self.provider.currentData() if self.provider.count() else None
        config = self.data_plane.settings()
        self.cloud.setChecked(bool(config['cloud_enabled']))
        self.remote_access.setChecked(bool(config['remote_access_enabled']))
        self.backup.setChecked(bool(config['encrypted_backup_enabled']))
        self._select_data(self.cloud_mode, str(config['cloud_mode']))
        self._select_data(self.default_policy, str(config['default_policy']))

        self.provider.blockSignals(True)
        self.provider.clear()
        inventory = self.data_plane.provider_inventory()
        for item in inventory:
            if item['provider_id'] == 'local':
                continue
            state = 'available' if item['available'] else ('enabled' if item['enabled'] else 'off')
            existing = runtime_provider_reference(item['provider_id'], self.runtime)
            suffix = ' · existing Vishnu connection' if existing else ''
            self.provider.addItem(f"{item['label']} — {state}{suffix}", item['provider_id'])
        if current_provider:
            self._select_data(self.provider, str(current_provider))
        self.provider.blockSignals(False)

        safe_inventory = [
            {
                'provider_id': item['provider_id'],
                'label': item['label'],
                'category': item['category'],
                'configured': item['configured'],
                'enabled': item['enabled'],
                'available': item['available'],
                'has_existing_vishnu_connection': bool(runtime_provider_reference(item['provider_id'], self.runtime)),
                'verified_at': item['verified_at'],
                'notes': item['notes'],
            }
            for item in inventory
        ]
        diagnostics = self.data_plane.diagnostics()
        self.status.setPlainText(json.dumps({
            'policy': config,
            'online_devices': self.data_plane.online_devices(),
            'remote_durable_locations': diagnostics.get('remote_durable_locations', 0),
            'providers': safe_inventory,
        }, indent=2, default=str))

    def save_policy(self):
        if not self._reauthenticated():
            return
        enabled = self.cloud.isChecked()
        selected_mode = str(self.cloud_mode.currentData())
        if enabled and selected_mode == CloudMode.LOCAL_ONLY.value:
            selected_mode = CloudMode.HYBRID.value
        try:
            self.data_plane.update_settings(
                cloud_enabled=enabled,
                cloud_mode=selected_mode,
                remote_access_enabled=self.remote_access.isChecked(),
                default_policy=str(self.default_policy.currentData()),
                encrypted_backup_enabled=self.backup.isChecked(),
            )
            self.refresh()
            QMessageBox.information(self, 'Data policy saved', 'Local-first storage policy updated. Cloud OFF is enforced by the data plane, not only by this screen.')
        except Exception as exc:
            QMessageBox.warning(self, 'Data policy not changed', str(exc))

    def set_provider(self, enabled: bool):
        provider_id = str(self.provider.currentData() or '')
        if not provider_id:
            return
        if not self._reauthenticated():
            return
        try:
            persisted = self.data_plane.settings()
            if enabled and not persisted['cloud_enabled']:
                raise PermissionError('Turn on online/cloud storage and save the data policy before enabling a provider.')
            existing_ref = runtime_provider_reference(provider_id, self.runtime)
            if enabled and existing_ref:
                connect_runtime_provider(self.data_plane, self.runtime, provider_id)
                self.provider_ref.clear()
                self.refresh()
                QMessageBox.information(self, 'Provider connected', 'Vishnu reused the existing governed connection. No second provider token was stored.')
                return
            ref = self.provider_ref.text().strip() or None
            status = self.data_plane.provider_status(provider_id)
            if enabled and status['credential_kind'] not in {'managed', 'native_bridge'} and not ref:
                raise ValueError('Connect/configure this provider first or select a vault/connector reference. Raw API keys are never stored here.')
            self.data_plane.configure_provider(
                provider_id,
                enabled=enabled,
                credential_ref=ref,
                config={},
                verified=False,
            )
            self.provider_ref.clear()
            self.refresh()
            if enabled:
                QMessageBox.information(self, 'Provider configured', 'The provider remains unavailable until its real adapter/connector verifies successfully. Vishnu fails closed until then.')
            else:
                QMessageBox.information(self, 'Provider disabled', 'Future online-storage use through this provider is disabled.')
        except Exception as exc:
            QMessageBox.warning(self, 'Provider not changed', str(exc))
