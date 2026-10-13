from __future__ import annotations

import io
import time

import qrcode
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from core.security import PairingManager
from devices.pairing_payload import build_pairing_uri, normalize_vishnu_origin
from ui.design_tokens import fit_window_to_screen, stylesheet as design_system_stylesheet


class MobilePairingDialog(QDialog):
    """Generate one-time mobile pairing QR codes from the canonical authority."""

    def __init__(self, runtime: dict, parent=None):
        super().__init__(parent)
        self.runtime = runtime
        self.settings = runtime['settings']
        self.preferences = runtime.get('preferences')
        self.registry = runtime.get('device_registry')
        self.manager = PairingManager(self.settings.pairing_ttl_seconds)
        self.offer = None
        self.baseline_devices: set[str] = set()

        self.setWindowTitle('Connect phone or device')
        fit_window_to_screen(self, preferred=(620, 760), minimum=(520, 620))
        self.setStyleSheet(design_system_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        layout.setSpacing(14)

        brand = QLabel('V I S H N U')
        brand.setStyleSheet('color:#71818b;font-size:11px;font-weight:700;letter-spacing:3px;')
        layout.addWidget(brand)
        title = QLabel('Connect phone or device')
        title.setStyleSheet('font-size:28px;font-weight:650;color:#edf3f6;')
        layout.addWidget(title)
        copy = QLabel(
            'Open Vishnu on Android or iPhone and choose “Scan Vishnu QR”. '
            'The QR contains a short-lived one-time connection offer. The phone receives its own revocable device credential after the offer is consumed.'
        )
        copy.setWordWrap(True)
        copy.setStyleSheet('color:#8fa0aa;')
        layout.addWidget(copy)

        self.base = QLineEdit()
        previous = self.preferences.get('mobile_pairing_base_url', '') if self.preferences else ''
        self.base.setText(str(previous or ''))
        self.base.setPlaceholderText('https://your-vishnu.example.com')
        layout.addWidget(QLabel('Address this phone can use to reach this Vishnu'))
        layout.addWidget(self.base)

        self.local_http = QCheckBox('Allow HTTP only for localhost emulator/simulator development')
        layout.addWidget(self.local_http)

        generate = QPushButton('Generate one-time QR')
        generate.clicked.connect(self.generate)
        layout.addWidget(generate)

        self.qr = QLabel('No active connection offer')
        self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr.setMinimumHeight(290)
        self.qr.setStyleSheet('background:#ffffff;color:#111;border-radius:16px;padding:12px;')
        layout.addWidget(self.qr)

        self.expiry = QLabel('')
        self.expiry.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.expiry.setStyleSheet('color:#8fa0aa;')
        layout.addWidget(self.expiry)

        manual_title = QLabel('Manual fallback')
        manual_title.setStyleSheet('font-size:15px;font-weight:600;')
        layout.addWidget(manual_title)
        manual_copy = QLabel('If the camera is unavailable, enter all three values in the mobile app. The six-digit code alone is never sufficient.')
        manual_copy.setWordWrap(True)
        manual_copy.setStyleSheet('color:#71818b;')
        layout.addWidget(manual_copy)

        self.origin = self._readonly('Vishnu address')
        self.connection_key = self._readonly('Connection key')
        self.code = self._readonly('6-digit code')
        layout.addWidget(self.origin)
        layout.addWidget(self.connection_key)
        layout.addWidget(self.code)

        self.status = QLabel('Ready to create a connection offer.')
        self.status.setWordWrap(True)
        self.status.setStyleSheet('color:#9badb7;')
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = QPushButton('Close')
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    @staticmethod
    def _readonly(placeholder: str) -> QLineEdit:
        field = QLineEdit()
        field.setReadOnly(True)
        field.setPlaceholderText(placeholder)
        field.setClearButtonEnabled(False)
        return field

    def _device_ids(self) -> set[str]:
        if not self.registry or not hasattr(self.registry, 'list'):
            return set()
        try:
            return {str(row.get('id')) for row in self.registry.list() if row.get('id') and not row.get('revoked')}
        except Exception:
            return set()

    def generate(self):
        if not bool(getattr(self.settings, 'control_server_enabled', False)):
            QMessageBox.warning(
                self,
                'Device pairing service is disabled',
                'This Vishnu is not currently running its device control server. Enable the governed control server for the address you intend to use, then restart Vishnu. No QR was created.',
            )
            return
        try:
            origin = normalize_vishnu_origin(
                self.base.text(),
                allow_local_http=self.local_http.isChecked(),
            )
        except Exception as exc:
            QMessageBox.warning(self, 'Vishnu address', str(exc))
            return

        if self.offer is not None:
            self.manager.invalidate(self.offer.token)
        self.baseline_devices = self._device_ids()
        self.offer = self.manager.create()
        try:
            uri = build_pairing_uri(
                base_url=origin,
                token=self.offer.token,
                code=self.offer.code,
                expires_at=self.offer.expires_at,
                allow_local_http=self.local_http.isChecked(),
            )
        except Exception as exc:
            self.manager.invalidate(self.offer.token)
            self.offer = None
            QMessageBox.warning(self, 'Pairing offer', str(exc))
            return

        if self.preferences is not None:
            self.preferences.set('mobile_pairing_base_url', origin)
        image = qrcode.make(uri)
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        pixmap = QPixmap()
        if not pixmap.loadFromData(stream.getvalue(), 'PNG'):
            self.manager.invalidate(self.offer.token)
            self.offer = None
            QMessageBox.warning(self, 'Pairing QR', 'Vishnu could not render the pairing QR.')
            return
        self.qr.setPixmap(
            pixmap.scaled(
                280,
                280,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.origin.setText(origin)
        self.connection_key.setText(self.offer.token)
        self.code.setText(self.offer.code)
        self.status.setText('One-time offer active. Scan it from the Vishnu mobile app.')
        self._tick()

    def _tick(self):
        if self.offer is None:
            self.expiry.setText('')
            return
        remaining = max(0, int(self.offer.expires_at - time.time()))
        current = self._device_ids()
        added = current - self.baseline_devices
        if added:
            device_id = sorted(added)[0]
            name = device_id
            try:
                row = next((item for item in self.registry.list() if str(item.get('id')) == device_id), None)
                if row:
                    name = str(row.get('name') or device_id)
            except Exception:
                pass
            self.status.setText(f'Connected successfully: {name}')
            self.expiry.setText('Device credential issued and independently revocable in Vishnu.')
            self.offer = None
            return
        if remaining <= 0:
            self.status.setText('This connection offer expired. Generate a new QR to try again.')
            self.expiry.setText('Expired')
            self.qr.setPixmap(QPixmap())
            self.qr.setText('Connection offer expired')
            self.connection_key.clear()
            self.code.clear()
            self.offer = None
            return
        minutes, seconds = divmod(remaining, 60)
        self.expiry.setText(f'Expires in {minutes:02d}:{seconds:02d} · one use only')
