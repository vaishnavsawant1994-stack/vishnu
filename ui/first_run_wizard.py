from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QUrl, QRectF
from PyQt6.QtGui import QColor, QDesktopServices, QLinearGradient, QPainter, QPen, QPixmap, QRadialGradient
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from data_plane.runtime import get_data_plane
from onboarding.first_run import FirstRunCoordinator, SetupMode


class VishnuCore(QWidget):
    """Render the exact transparent Core asset shared by every Vishnu client."""

    def __init__(self, state: str = 'identity', size: int = 220):
        super().__init__()
        self.state = state
        self.setFixedSize(size, size)
        asset = Path(__file__).resolve().parents[1] / 'pwa' / 'assets' / 'genesis' / 'vishnu-core.png'
        self.pixmap = QPixmap(str(asset))
        self.setAccessibleName(f'Vishnu intelligence core, {state} state')

    def paintEvent(self, event):  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if not self.pixmap.isNull():
            painter.drawPixmap(self.rect(), self.pixmap)


class FirstRunWizard(QDialog):
    """Owner-first setup UI for a fresh Vishnu desktop installation."""

    def __init__(self, runtime: dict, coordinator: FirstRunCoordinator):
        super().__init__()
        self.runtime = runtime
        self.coordinator = coordinator
        self.mode: SetupMode | None = None
        self.recovery_codes: list[str] = []
        self.restart_required = False
        self.external_connect = False
        self.setWindowTitle('Welcome to Vishnu')
        self.setObjectName('firstRunWizard')
        self.setModal(True)
        self.resize(1280, 800)
        self.setMinimumSize(900, 680)
        self.setStyleSheet(self._stylesheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(38, 32, 38, 32)
        root.setSpacing(20)
        brand = QLabel('V I S H N U')
        brand.setObjectName('brand')
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(brand)
        wordmark_line = QFrame(self)
        wordmark_line.setFixedSize(180, 1)
        wordmark_line.setStyleSheet("background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 transparent,stop:0.5 #4ddcff,stop:1 transparent); border:0;")
        root.addWidget(wordmark_line, 0, Qt.AlignmentFlag.AlignHCenter)
        self.genesis_progress = QLabel('Screen 1 of 10   ● ○ ○ ○ ○ ○ ○ ○ ○ ○')
        self.genesis_progress.setObjectName('progress')
        self.genesis_progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.genesis_progress)
        self.title = QLabel('Welcome to Vishnu')
        self.title.setObjectName('title')
        self.subtitle = QLabel('Create your owner intelligence, connect to an existing Vishnu, or restore a backup.')
        self.subtitle.setObjectName('subtitle')
        self.subtitle.setWordWrap(True)

        self.stack = QStackedWidget()
        # Keep native forms aligned to the same centered content column as the
        # responsive web Genesis instead of stretching fields edge-to-edge.
        self.stack.setMaximumWidth(720)
        root.addWidget(self.stack, 1, Qt.AlignmentFlag.AlignHCenter)
        self.stack.addWidget(self._welcome_page())       # 0
        self.stack.addWidget(self._owner_page())            # 1 / Genesis 02
        self.stack.addWidget(self._security_choice_page())  # 2 / Genesis 03
        self.stack.addWidget(self._security_page())         # 3 / Genesis 04
        self.stack.addWidget(self._recovery_page())         # 4 / Genesis 05
        self.stack.addWidget(self._device_page())           # 5 / Genesis 06
        self.stack.addWidget(self._data_page())             # 6 / Genesis 07
        self.stack.addWidget(self._model_page())            # 7 / Genesis 08
        self.stack.addWidget(self._privacy_page())          # 8 / Genesis 09
        self.stack.addWidget(self._review_page())           # 9 / Genesis 10
        self.stack.addWidget(self._restore_page())          # 10
        self.stack.addWidget(self._connect_page())          # 11
        self.stack.currentChanged.connect(self._update_progress)

        footer = QHBoxLayout()
        self.back_button = QPushButton('Back')
        self.back_button.clicked.connect(self._back)
        self.back_button.setVisible(False)
        footer.addWidget(self.back_button)
        privacy = QPushButton('Privacy')
        privacy.setObjectName('footerLink')
        footer.addWidget(privacy)
        accessibility = QPushButton('Accessibility')
        accessibility.setObjectName('footerLink')
        footer.addWidget(accessibility)
        footer.addStretch(1)
        self.cancel_button = QPushButton('Exit setup')
        self.cancel_button.clicked.connect(self.reject)
        footer.addWidget(self.cancel_button)
        root.addLayout(footer)

        state = self.coordinator.snapshot()
        self._restore_form_values()
        self._resume_state(state)
        self._update_progress(self.stack.currentIndex())
        if state.get('status') == 'restore_failed' and state.get('last_error'):
            QMessageBox.warning(self, 'Restore needs attention', str(state['last_error']))

    def _stylesheet(self) -> str:
        background = (Path(__file__).resolve().parents[1] / 'pwa' / 'assets' / 'genesis' / 'cosmic-desktop.png').as_posix()
        return """
        QDialog#firstRunWizard { background-color:#02060b; border-image:url('__BACKGROUND__') 0 0 0 0 stretch stretch; color:#f5faff; font-family:"Segoe UI"; }
        QDialog#firstRunWizard QWidget { background:transparent; color:#f5faff; font-family:"Segoe UI"; }
        QLabel#brand { color:#f5faff; font-size:22px; font-weight:450; letter-spacing:7px; }
        QLabel#title { font-size:38px; font-weight:350; color:#f5faff; }
        QLabel#subtitle { color:#a7bacb; font-size:15px; }
        QLabel#progress { color:#4ddcff; font-size:12px; letter-spacing:2px; }
        QLabel#section { font-size:25px; font-weight:450; color:#f5faff; }
        QLabel#hint { color:#687f94; font-size:12px; }
        QPushButton { background:rgba(5,18,30,184); border:1px solid rgba(61,174,235,90); border-radius:13px; padding:12px 18px; color:#f5faff; }
        QPushButton:hover, QPushButton:focus { border-color:#4ddcff; background:#071d2d; }
        QPushButton#primary { background:#073b61; color:#f5faff; border:1px solid #4ddcff; border-radius:26px; font-weight:600; min-height:28px; }
        QPushButton#choice { text-align:left; min-height:64px; font-size:14px; border-radius:17px; }
        QPushButton#footerLink { border:0; background:transparent; color:#687f94; padding:8px; }
        QLineEdit, QComboBox { background:#03111e; border:1px solid rgba(61,174,235,100); border-radius:13px; padding:11px; color:#f5faff; min-height:24px; }
        QLineEdit:focus, QComboBox:focus { border-color:#4ddcff; }
        QComboBox QAbstractItemView { background:#071522; color:#f5faff; selection-background-color:#0b456a; }
        QCheckBox { color:#a7bacb; spacing:10px; }
        """.replace('__BACKGROUND__', background)

    def _page(self, heading: str, copy: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setMaximumWidth(920)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 8, 20, 0)
        layout.setSpacing(14)
        core_size = 300 if heading == 'Welcome to Vishnu' else 190
        core = VishnuCore('ready' if 'Review' in heading else 'security' if 'Secure' in heading else 'identity', core_size)
        layout.addWidget(core, 0, Qt.AlignmentFlag.AlignHCenter)
        heading_label = QLabel(heading)
        heading_label.setObjectName('section')
        heading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading_label)
        copy_label = QLabel(copy)
        copy_label.setObjectName('subtitle')
        copy_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        copy_label.setWordWrap(True)
        layout.addWidget(copy_label)
        return page, layout

    def _next_button(self, text: str, callback):
        button = QPushButton(text)
        button.setObjectName('primary')
        button.clicked.connect(callback)
        return button

    def _update_progress(self, index: int):
        if 0 <= index <= 9:
            step = index + 1
            dots = ' '.join('●' if item <= step else '○' for item in range(1, 11))
            self.genesis_progress.setText(f'Screen {step} of 10   {dots}')
            self.genesis_progress.setVisible(index > 0)
        else:
            self.genesis_progress.setVisible(False)

    def _welcome_page(self):
        page, layout = self._page('Welcome to Vishnu', 'Your personal intelligence. Your data. Your world.')
        create = QPushButton('Create my Vishnu  →')
        create.setObjectName('primary')
        create.setFixedWidth(420)
        create.clicked.connect(lambda: self._choose_mode(SetupMode.CREATE))
        layout.addWidget(create, 0, Qt.AlignmentFlag.AlignHCenter)
        secondary = QHBoxLayout()
        connect = QPushButton('I already have Vishnu')
        connect.setObjectName('footerLink')
        connect.clicked.connect(lambda: self._choose_mode(SetupMode.CONNECT))
        restore = QPushButton('Restore Vishnu')
        restore.setObjectName('footerLink')
        restore.clicked.connect(lambda: self._choose_mode(SetupMode.RESTORE))
        secondary.addStretch(1)
        secondary.addWidget(connect)
        secondary.addWidget(restore)
        secondary.addStretch(1)
        layout.addLayout(secondary)
        layout.addStretch(1)
        return page

    def _owner_page(self):
        page, layout = self._page('Create your Vishnu identity', 'This is how Vishnu will know and address you.')
        form = QFormLayout()
        self.first_name = QLineEdit()
        self.last_name = QLineEdit()
        self.display_name = QLineEdit()
        self.display_name.setPlaceholderText('How Vishnu should address you')
        form.addRow('First name', self.first_name)
        form.addRow('Last name', self.last_name)
        form.addRow('Display name', self.display_name)
        layout.addLayout(form)
        layout.addStretch(1)
        layout.addWidget(self._next_button('Continue', self._save_owner))
        return page

    def _security_choice_page(self):
        page, layout = self._page('Secure your Vishnu', 'Choose how Vishnu should verify it is you.')
        self.authentication_choice = QComboBox()
        self.authentication_choice.addItem('Passkey — recommended', 'passkey')
        self.authentication_choice.addItem('Password', 'password')
        self.authentication_choice.addItem('Passkey + password', 'both')
        layout.addWidget(self.authentication_choice)
        hint = QLabel('A private owner password initializes recovery security. When Windows passkey support is available, Vishnu will offer the selected passkey option without changing your owner identity.')
        hint.setObjectName('hint')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        layout.addWidget(self._next_button('Continue', lambda: self.stack.setCurrentIndex(3)))
        return page

    def _security_page(self):
        page, layout = self._page('Configure your authentication', 'Create the private owner credential and recovery security for this Vishnu.')
        form = QFormLayout()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_confirm = QLineEdit()
        self.password_confirm.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow('Owner password', self.password)
        form.addRow('Confirm password', self.password_confirm)
        layout.addLayout(form)
        hint = QLabel('Minimum 12 characters. Vishnu stores a password hash, never this plaintext password.')
        hint.setObjectName('hint')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        layout.addWidget(self._next_button('Create security', self._save_security))
        return page

    def _recovery_page(self):
        page, layout = self._page('Save your recovery codes', 'These one-time codes are shown only now. Store them somewhere separate from this computer before continuing.')
        self.recovery_label = QLabel('Recovery codes will appear here after owner security is created.')
        self.recovery_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.recovery_label.setStyleSheet('background:#080d11;border:1px solid #1b2b34;border-radius:12px;padding:18px;font-family:monospace;')
        layout.addWidget(self.recovery_label)
        self.saved_codes = QCheckBox('I saved these recovery codes in a safe place')
        layout.addWidget(self.saved_codes)
        layout.addStretch(1)
        layout.addWidget(self._next_button('Continue', self._confirm_recovery_codes))
        return page

    def _device_page(self):
        page, layout = self._page('Register this device', 'Make this computer part of your trusted Vishnu network.')
        device = QLabel('This Windows computer\nSecure device credential will be created\nThis device can be reviewed or revoked later')
        device.setWordWrap(True)
        device.setStyleSheet('background:#071522;border:1px solid rgba(61,174,235,90);border-radius:17px;padding:18px;')
        layout.addWidget(device)
        layout.addStretch(1)
        layout.addWidget(self._next_button('Trust this device', lambda: self.stack.setCurrentIndex(6)))
        return page

    def _privacy_page(self):
        page, layout = self._page('Choose what Vishnu can access', 'You stay in control. Vishnu only uses permissions and information you allow.')
        form = QFormLayout()
        self.privacy = QComboBox()
        self.privacy.addItem('Local only — never use external models', 'local_only')
        self.privacy.addItem('Local preferred — external fallback when permitted', 'local_preferred')
        self.privacy.addItem('External allowed — use configured providers subject to policy', 'external_allowed')
        self.privacy.setCurrentIndex(1)
        self.autonomy = QComboBox()
        self.autonomy.addItem('Observe', 'observe')
        self.autonomy.addItem('Suggest', 'suggest')
        self.autonomy.addItem('Ask before acting — recommended', 'ask')
        self.autonomy.addItem('Act within permissions', 'act')
        self.autonomy.setCurrentIndex(2)
        form.addRow('Model privacy', self.privacy)
        form.addRow('Autonomy', self.autonomy)
        layout.addLayout(form)
        self.memory_enabled = QCheckBox('Enable governed personal memory')
        self.memory_enabled.setChecked(True)
        layout.addWidget(self.memory_enabled)
        layout.addStretch(1)
        layout.addWidget(self._next_button('Continue', self._save_preferences))
        return page

    def _data_page(self):
        page, layout = self._page('Choose where your data lives', 'Decide how Vishnu stores and reaches information across your trusted devices. Changing this default never silently moves data that already exists.')
        form = QFormLayout()
        self.data_policy = QComboBox()
        self.data_policy.addItem('Device only — keep governed data on this device', 'device_only')
        self.data_policy.addItem('Progress only — share only continuation/progress data', 'progress_only')
        self.data_policy.addItem('Sync everywhere — sync permitted data to trusted locations', 'sync_everywhere')
        self.data_policy.addItem('On demand — move data only when explicitly required', 'on_demand')
        form.addRow('Data placement', self.data_policy)
        layout.addLayout(form)
        hint = QLabel('Cloud is optional. A policy change controls future placement decisions; any explicit movement of existing data remains a separate governed action.')
        hint.setObjectName('hint')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        layout.addWidget(self._next_button('Save data placement', self._save_data_policy))
        return page

    def _model_page(self):
        page, layout = self._page('Set up Vishnu’s intelligence', 'Choose how Vishnu should think and which AI providers it may use. Owner-entered credentials are encrypted in the Vishnu vault.')
        form = QFormLayout()
        self.provider = QComboBox()
        for label, value in (
            ('Local AI', 'local'),
            ('OpenAI', 'openai'),
            ('Gemini', 'gemini'),
            ('OpenRouter', 'openrouter'),
        ):
            self.provider.addItem(label, value)
        self.provider.currentIndexChanged.connect(self._provider_changed)
        self.model = QLineEdit()
        self.model.setPlaceholderText('Model ID returned by your provider')
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key.setPlaceholderText('Provider API key')
        form.addRow('Provider', self.provider)
        form.addRow('Model', self.model)
        form.addRow('API key', self.api_key)
        layout.addLayout(form)
        self.skip_model = QCheckBox('Skip model configuration for now')
        layout.addWidget(self.skip_model)
        self.model_hint = QLabel('Local mode uses the configured local OpenAI-compatible endpoint. No API key is required here.')
        self.model_hint.setObjectName('hint')
        self.model_hint.setWordWrap(True)
        layout.addWidget(self.model_hint)
        layout.addStretch(1)
        layout.addWidget(self._next_button('Continue', self._save_model_setup))
        self._provider_changed()
        return page

    def _review_page(self):
        page, layout = self._page('Your Vishnu is ready to be created', 'Review your setup, then create your Vishnu.')
        self.review_label = QLabel('Your setup summary will appear here.')
        self.review_label.setAccessibleName('Review setup')
        self.review_label.setWordWrap(True)
        self.review_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.review_label.setStyleSheet('background:#080d11;border:1px solid #1b2b34;border-radius:12px;padding:18px;')
        layout.addWidget(self.review_label)
        hint = QLabel('Finish is idempotent: retrying after interruption resumes the same Vishnu identity rather than creating a duplicate owner.')
        hint.setObjectName('hint')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        layout.addWidget(self._next_button('Create my Vishnu', self._finish_review))
        return page

    def _restore_page(self):
        page, layout = self._page('Restore Vishnu', 'Restore is performed before the next runtime starts, so live databases are never overwritten while Vishnu is using them. Security authority is intentionally not restored; you will create fresh owner security afterward.')
        row = QHBoxLayout()
        self.restore_path = QLineEdit()
        self.restore_path.setReadOnly(True)
        browse = QPushButton('Choose backup')
        browse.clicked.connect(self._choose_backup)
        row.addWidget(self.restore_path, 1)
        row.addWidget(browse)
        layout.addLayout(row)
        key_row = QHBoxLayout()
        self.restore_key_path = QLineEdit()
        self.restore_key_path.setReadOnly(True)
        key_browse = QPushButton('Choose encrypted recovery key…')
        key_browse.clicked.connect(self._choose_recovery_key)
        key_row.addWidget(self.restore_key_path, 1)
        key_row.addWidget(key_browse)
        layout.addLayout(key_row)
        self.restore_passphrase = QLineEdit()
        self.restore_passphrase.setEchoMode(QLineEdit.EchoMode.Password)
        self.restore_passphrase.setPlaceholderText('Recovery passphrase for .vdr key file')
        layout.addWidget(self.restore_passphrase)
        hint = QLabel('For a .vdr portable recovery package, select its separate encrypted .key file and enter the recovery passphrase. The recovery key is decrypted only to validate the package, then saved encrypted to this device for the next-start restore. Old .paibackup files still use the existing root-key restore path.')
        hint.setObjectName('hint')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        layout.addWidget(self._next_button('Validate and restart for restore', self._schedule_restore))
        return page

    def _connect_page(self):
        page, layout = self._page('Connect to your existing Vishnu', 'This avoids creating a second owner brain. The trusted browser/mobile session remains governed by the existing Vishnu device registry and owner authentication.')
        self.connect_url = QLineEdit()
        self.connect_url.setPlaceholderText('https://your-vishnu.example.com')
        layout.addWidget(self.connect_url)
        hint = QLabel('Native second-desktop runtime attachment is not yet a separate thin-client authority. This flow opens the existing secure Vishnu web/PWA surface, where the device can be enrolled and revoked independently.')
        hint.setObjectName('hint')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)
        layout.addWidget(self._next_button('Open existing Vishnu', self._connect_existing))
        return page

    def _restore_form_values(self):
        preferences = self.runtime.get('preferences')
        if preferences is not None:
            self.first_name.setText(str(preferences.get('profile_first_name', '') or ''))
            self.last_name.setText(str(preferences.get('profile_last_name', '') or ''))
            self.display_name.setText(str(preferences.get('preferred_name', '') or ''))
            privacy_index = self.privacy.findData(str(preferences.get('model_privacy_mode', 'local_preferred') or 'local_preferred'))
            if privacy_index >= 0:
                self.privacy.setCurrentIndex(privacy_index)
            autonomy_index = self.autonomy.findData(str(preferences.get('autonomy_mode', 'ask') or 'ask'))
            if autonomy_index >= 0:
                self.autonomy.setCurrentIndex(autonomy_index)
            self.memory_enabled.setChecked(bool(preferences.get('memory_enabled', True)))
        try:
            settings = get_data_plane(self.runtime).settings()
            index = self.data_policy.findData(str(settings.get('default_policy') or 'device_only'))
            if index >= 0:
                self.data_policy.setCurrentIndex(index)
        except Exception:
            pass

    def _resume_state(self, state: dict):
        status = str(state.get('status') or '')
        stage = str(state.get('stage') or 'welcome')
        completed = set(state.get('completed_steps') or [])
        mode_value = str(state.get('mode') or '')

        if status == 'connect_pending':
            self.mode = SetupMode.CONNECT
            self.connect_url.setText(str(state.get('connect_url') or ''))
            self.stack.setCurrentIndex(11)
            self.back_button.setVisible(True)
            self.title.setText('Connect to Vishnu')
            return
        if status == 'restore_failed':
            self.mode = SetupMode.RESTORE
            self.stack.setCurrentIndex(10)
            self.back_button.setVisible(True)
            self.title.setText('Restore Vishnu')
            return
        if status != 'setup_in_progress':
            return

        self.mode = SetupMode.CREATE
        self.back_button.setVisible(True)
        self.title.setText('Finish restoring Vishnu' if mode_value == SetupMode.RESTORE.value else 'Continue setting up Vishnu')
        if stage == 'owner':
            self.stack.setCurrentIndex(1)
        elif stage == 'security':
            self.stack.setCurrentIndex(2)
        elif stage == 'recovery' and 'recovery_saved' not in completed:
            self.stack.setCurrentIndex(3)
            self.subtitle.setText('Setup was interrupted before recovery codes were confirmed. Re-enter an owner password to generate a fresh recovery-code set.')
        elif stage == 'privacy' or ('recovery_saved' in completed and 'privacy' not in completed):
            self.stack.setCurrentIndex(5)
        elif {'model', 'model_skipped'} & completed:
            self._refresh_review()
            self.stack.setCurrentIndex(8 if 'privacy' not in completed else 9)
        else:
            self.stack.setCurrentIndex(6)

    def _choose_mode(self, mode: SetupMode):
        self.mode = mode
        self.coordinator.begin(mode)
        self.back_button.setVisible(True)
        if mode is SetupMode.CREATE:
            self.stack.setCurrentIndex(1)
            self.title.setText('Set up your Vishnu')
        elif mode is SetupMode.RESTORE:
            self.stack.setCurrentIndex(10)
            self.title.setText('Restore Vishnu')
        else:
            self.stack.setCurrentIndex(11)
            self.title.setText('Connect to Vishnu')

    def _back(self):
        index = self.stack.currentIndex()
        if index in {1, 10, 11}:
            self.stack.setCurrentIndex(0)
            self.back_button.setVisible(False)
            self.title.setText('Welcome to Vishnu')
            return
        if self.mode is SetupMode.CREATE:
            previous = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 8: 7, 9: 8}.get(index)
            if previous is not None:
                self.stack.setCurrentIndex(previous)

    def _save_owner(self):
        try:
            self.coordinator.configure_owner(
                first_name=self.first_name.text(),
                last_name=self.last_name.text(),
                display_name=self.display_name.text(),
            )
        except Exception as exc:
            QMessageBox.warning(self, 'Owner details', str(exc))
            return
        self.stack.setCurrentIndex(2)

    def _save_security(self):
        if self.password.text() != self.password_confirm.text():
            QMessageBox.warning(self, 'Owner security', 'The passwords do not match.')
            return
        try:
            self.recovery_codes = self.coordinator.configure_security(self.password.text())
        except Exception as exc:
            QMessageBox.warning(self, 'Owner security', str(exc))
            return
        self.password.clear()
        self.password_confirm.clear()
        self.saved_codes.setChecked(False)
        self.recovery_label.setText('\n'.join(self.recovery_codes))
        self.stack.setCurrentIndex(4)

    def _confirm_recovery_codes(self):
        if not self.saved_codes.isChecked():
            QMessageBox.warning(self, 'Recovery codes', 'Confirm that you saved the recovery codes before continuing.')
            return
        try:
            self.coordinator.confirm_recovery_codes_saved()
        except Exception as exc:
            QMessageBox.warning(self, 'Recovery codes', str(exc))
            return
        self.recovery_codes = []
        self.recovery_label.setText('Recovery codes saved and hidden. Regenerate them from Settings → Security if they are ever lost.')
        self.stack.setCurrentIndex(5)

    def _save_preferences(self):
        try:
            self.coordinator.configure_preferences(
                privacy_mode=str(self.privacy.currentData()),
                autonomy_mode=str(self.autonomy.currentData()),
                memory_enabled=self.memory_enabled.isChecked(),
            )
        except Exception as exc:
            QMessageBox.warning(self, 'Privacy and autonomy', str(exc))
            return
        self._refresh_review()
        self.stack.setCurrentIndex(9)

    def _save_data_policy(self):
        try:
            result = get_data_plane(self.runtime).update_settings(default_policy=str(self.data_policy.currentData()))
            if str(result.get('default_policy') or '') != str(self.data_policy.currentData()):
                raise RuntimeError('Vishnu did not confirm the selected data placement policy')
        except Exception as exc:
            QMessageBox.warning(self, 'Data placement', str(exc))
            return
        self.stack.setCurrentIndex(7)

    def _provider_changed(self):
        local = self.provider.currentData() == 'local'
        self.model.setEnabled(not local)
        self.api_key.setEnabled(not local)
        self.model_hint.setText(
            'Local mode uses the configured local OpenAI-compatible endpoint. No API key is required here.'
            if local else
            'The provider key is live-validated, then passed directly to the canonical model router/vault and is never written to onboarding state.'
        )

    def _save_model_setup(self):
        try:
            if self.skip_model.isChecked():
                self.coordinator.skip_model_configuration()
            else:
                self.coordinator.configure_model(
                    provider_id=str(self.provider.currentData()),
                    model=self.model.text(),
                    api_key=self.api_key.text(),
                )
        except Exception as exc:
            QMessageBox.warning(self, 'AI configuration', str(exc))
            return
        self.api_key.clear()
        self.stack.setCurrentIndex(8)

    def _refresh_review(self):
        preferences = self.runtime.get('preferences')
        owner = ''
        privacy = str(self.privacy.currentText())
        autonomy = str(self.autonomy.currentText())
        if preferences is not None:
            owner = str(preferences.get('preferred_name', '') or '').strip()
        if not owner:
            owner = self.display_name.text().strip() or self.first_name.text().strip() or 'Vishnu Owner'
        try:
            policy = str(get_data_plane(self.runtime).settings().get('default_policy') or self.data_policy.currentData())
        except Exception:
            policy = str(self.data_policy.currentData())
        policy_label = {
            'device_only': 'Device only',
            'progress_only': 'Progress only',
            'sync_everywhere': 'Sync everywhere',
            'on_demand': 'On demand',
        }.get(policy, policy)
        ai = 'Configure later' if self.skip_model.isChecked() else str(self.provider.currentText())
        if not self.skip_model.isChecked() and self.model.text().strip():
            ai += f' — {self.model.text().strip()}'
        self.review_label.setText(
            f'Owner: {owner}\n\n'
            'First trusted device: this desktop\n\n'
            'Security: owner password configured; passkeys can be added from Settings → Security\n\n'
            'Recovery: one-time recovery codes saved and acknowledged\n\n'
            f'Data placement: {policy_label}\n\n'
            f'Privacy: {privacy}\n\n'
            f'Autonomy: {autonomy}\n\n'
            f'AI: {ai}'
        )

    def _finish_review(self):
        try:
            self.coordinator.complete()
        except Exception as exc:
            QMessageBox.warning(self, 'Finish setup', str(exc))
            return
        QMessageBox.information(self, 'Vishnu is ready', 'Your Vishnu identity is ready on this first trusted device.')
        self.accept()

    def _choose_backup(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose Vishnu backup', '', 'Vishnu Backup (*.paibackup *.vdr);;All files (*)')
        if path:
            self.restore_path.setText(path)

    def _choose_recovery_key(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Choose encrypted recovery key', '', 'Vishnu Recovery Key (*.vdr.key *.key);;All files (*)')
        if path:
            self.restore_key_path.setText(path)

    def _schedule_restore(self):
        try:
            if str(self.restore_path.text()).lower().endswith('.vdr'):
                restore = self.coordinator.schedule_disaster_recovery(
                    self.restore_path.text(), self.restore_key_path.text(), self.restore_passphrase.text(),
                )
                self.restore_passphrase.clear()
            else:
                restore = self.coordinator.schedule_restore(self.restore_path.text())
        except Exception as exc:
            QMessageBox.warning(self, 'Restore', str(exc))
            return
        self.restart_required = True
        QMessageBox.information(
            self,
            'Restart required',
            f"Backup {restore.get('archive', '')} was authenticated and scheduled. Vishnu will restore it before the next runtime starts, then ask you to create fresh owner security.",
        )
        self.accept()

    def _connect_existing(self):
        raw = self.connect_url.text().strip()
        try:
            state = self.coordinator.mark_connect_pending(raw)
        except Exception as exc:
            QMessageBox.warning(self, 'Connect', str(exc))
            return
        origin = str(state.get('connect_url') or '').rstrip('/')
        self.connect_url.setText(origin)
        self.external_connect = True
        QDesktopServices.openUrl(QUrl(origin + '/iphone/'))
        QMessageBox.information(self, 'Existing Vishnu opened', 'Complete owner sign-in/device enrollment in the secure Vishnu page that just opened. This local installation has not created a second owner brain.')
        self.accept()
