from __future__ import annotations

from PyQt6.QtWidgets import QPushButton

from core.runtime_presentation import presentation_for
from data_plane.runtime import get_data_plane
from devices.local_gateway import get_local_device_gateway
from ui.main_window import MainWindow
from ui.mobile_pairing_dialog import MobilePairingDialog
from ui.products_panel import ProductsPanel
from ui.storage_settings_dialog import StorageSettingsDialog


class CanonicalMainWindow(MainWindow):
    """Desktop Home whose semantic Core state is a read-only runtime projection.

    The legacy MainWindow still contains compatibility presentation calls used by
    older tests/surfaces. This V1 entrypoint deliberately ignores those calls;
    only RuntimeStateAuthority snapshots/events may change semantic Core state.
    """

    NAV = (
        "Home",
        "Conversation",
        "Memory",
        "Knowledge",
        "Activities",
        "Dashboard",
        "Apps & Tools",
        "Our Products",
        "Settings",
    )

    HINTS = {
        'IDLE': 'I am here.',
        'ACTIVE': 'I am ready.',
        'LISTENING': 'I am listening to you.',
        'UNDERSTANDING': 'I am interpreting what you mean.',
        'THINKING': 'I am working through the request.',
        'MEMORY_RETRIEVAL': 'I am recalling relevant memory.',
        'KNOWLEDGE_RETRIEVAL': 'I am retrieving relevant knowledge.',
        'TOOL_ACTION': 'I am carrying out governed work.',
        'RESPONDING': 'I am communicating the result.',
        'NEEDS_APPROVAL': 'I need your decision before continuing.',
        'BACKGROUND': 'Work is continuing in the background.',
        'SUCCESS': 'The current work completed.',
        'WARNING': 'The current work needs attention.',
        'ERROR': 'Something prevented the current work from continuing.',
    }

    def __init__(self, *, events, executor, memory, runtime=None):
        self._canonical_render = False
        self._canonical_sequence = -1
        super().__init__(events=events, executor=executor, memory=memory, runtime=runtime)
        self._runtime_unsubscribe = events.subscribe('runtime.state', self._on_runtime_state)
        snapshot = events.runtime_state.snapshot()
        self._apply_canonical(snapshot.state.value, snapshot.sequence)
        self._local_device_gateway = None
        if self.runtime:
            # Attach exactly one local-first data-plane authority to the existing
            # runtime. It reuses the canonical DeviceRegistry/DeviceGateway and
            # never turns a provider into a second execution authority.
            get_data_plane(self.runtime)
            try:
                gateway = get_local_device_gateway(self.runtime)
                gateway.start_if_needed()
                self._local_device_gateway = gateway
            except Exception as exc:
                events.emit('device.local_gateway_unavailable', error_type=type(exc).__name__)

    def _build_page(self, name):
        if name == "Our Products":
            return ProductsPanel(runtime=self.runtime)
        return super()._build_page(name)

    def _settings_content(self, layout):
        super()._settings_content(layout)
        storage = QPushButton('Data & Cloud Storage')
        storage.setObjectName('navAction')
        storage.setToolTip('Local-first data rules, remote access and optional online storage providers')
        storage.clicked.connect(self.open_storage_settings)
        layout.addWidget(storage)
        connect = QPushButton('Connect phone or device')
        connect.setObjectName('navAction')
        connect.setToolTip('Generate a short-lived one-time QR for the Vishnu Android or iPhone companion')
        connect.clicked.connect(self.open_mobile_pairing)
        layout.addWidget(connect)

    def open_storage_settings(self):
        StorageSettingsDialog(self.runtime, self).exec()
        self._refresh_home_indicators()

    def open_mobile_pairing(self):
        MobilePairingDialog(self.runtime, self).exec()
        self._refresh_home_indicators()

    def _set_state(self, state):
        # Compatibility/local UI code cannot invent semantic AI truth.
        if not self._canonical_render:
            return
        self._render_projection(state)

    def on_state(self, event):
        # Legacy `state` events are explicitly non-authoritative in V1.
        return None

    def _on_runtime_state(self, event):
        self._apply_canonical(event.get('state'), event.get('sequence'))

    def _apply_canonical(self, state, sequence):
        presentation = presentation_for(state)
        try:
            sequence = int(sequence)
        except (TypeError, ValueError):
            return
        if presentation is None or sequence <= self._canonical_sequence:
            return
        self._canonical_sequence = sequence
        self._canonical_render = True
        try:
            self._render_projection(presentation.state.value)
        finally:
            self._canonical_render = False

    def _render_projection(self, state):
        presentation = presentation_for(state)
        if presentation is None:
            return
        self.state.setText(presentation.label)
        self.state.setAccessibleName(f'Vishnu state: {presentation.label}')
        self.state_hint.setText(self.HINTS[presentation.state.value])
        self.pulse.set_state(presentation.visual)
        self.pulse.setAccessibleDescription(presentation.label)
        if presentation.attention in {'approval', 'warning', 'error'}:
            self.needs_label.setText(presentation.label)
            self.needs_label.setVisible(True)
        else:
            self.needs_label.setVisible(False)
        self._refresh_home_indicators()

    def closeEvent(self, event):
        unsubscribe = getattr(self, '_runtime_unsubscribe', None)
        if unsubscribe:
            unsubscribe()
            self._runtime_unsubscribe = None
        gateway = getattr(self, '_local_device_gateway', None)
        if gateway:
            gateway.stop()
            self._local_device_gateway = None
        super().closeEvent(event)
