from __future__ import annotations

import json

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from core.config import settings
from products.models import AIMode, PlatformTarget, ProductType
from products.store import ProductStore


_TYPE_LABELS = {
    "ai_employee": "AI Employee",
    "agent": "Agent",
    "agent_team": "Agent Team",
    "automation": "Automation",
    "workflow": "Workflow",
    "tool": "Tool",
    "knowledge_assistant": "Knowledge Assistant",
    "integration": "Integration",
    "business_system": "Business System",
    "custom": "Custom Product",
}
_AI_LABELS = {
    "disabled": "AI: Disabled",
    "client_api": "AI: Client API",
    "managed": "AI: Our Managed AI",
    "local": "AI: Local / Private",
    "hybrid": "AI: Hybrid",
}


class CreateProductDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Product")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        intro = QLabel("Create a reusable product without exposing the rest of Vishnu.")
        intro.setWordWrap(True)
        intro.setObjectName("muted")
        layout.addWidget(intro)

        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("ACME Sales Employee")
        form.addRow("Product name", self.name)
        self.client = QLineEdit()
        self.client.setPlaceholderText("Optional client or Internal Use")
        form.addRow("Client", self.client)
        self.kind = QComboBox()
        for item in ProductType:
            self.kind.addItem(_TYPE_LABELS[item.value], item.value)
        form.addRow("Product type", self.kind)
        self.ai_mode = QComboBox()
        for item in AIMode:
            self.ai_mode.addItem(_AI_LABELS[item.value].removeprefix("AI: "), item.value)
        form.addRow("AI mode", self.ai_mode)
        self.description = QLineEdit()
        self.description.setPlaceholderText("What this product does")
        form.addRow("Description", self.description)
        layout.addLayout(form)

        target_label = QLabel("Delivery targets")
        target_label.setStyleSheet("font-weight:600;margin-top:8px")
        layout.addWidget(target_label)
        target_row = QGridLayout()
        self.targets = {}
        defaults = {"web", "android", "windows"}
        for index, item in enumerate(PlatformTarget):
            check = QCheckBox(item.value.replace("_", " ").title())
            check.setChecked(item.value in defaults)
            self.targets[item.value] = check
            target_row.addWidget(check, index // 4, index % 4)
        layout.addLayout(target_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Create Product")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _accept(self):
        if not self.name.text().strip():
            QMessageBox.warning(self, "Create Product", "Product name is required.")
            return
        self.accept()

    def payload(self):
        return {
            "name": self.name.text().strip(),
            "client_name": self.client.text().strip(),
            "description": self.description.text().strip(),
            "product_type": self.kind.currentData(),
            "ai_mode": self.ai_mode.currentData(),
            "targets": [target for target, check in self.targets.items() if check.isChecked()],
        }


class ProductDetailDialog(QDialog):
    def __init__(self, store: ProductStore, product_id: str, parent=None):
        super().__init__(parent)
        self.store = store
        self.product_id = product_id
        product = store.get(product_id)
        self.setWindowTitle(product["name"] if product else "Product")
        self.resize(820, 680)
        layout = QVBoxLayout(self)
        if not product:
            layout.addWidget(QLabel("Product not found"))
            return

        title = QLabel(product["name"])
        title.setStyleSheet("font-size:26px;font-weight:650")
        layout.addWidget(title)
        summary = QLabel(
            f"{_TYPE_LABELS.get(product['product_type'], product['product_type'])} · "
            f"{product['status'].replace('_', ' ').title()} · Version {product['version']}"
        )
        summary.setObjectName("muted")
        layout.addWidget(summary)

        facts = QGridLayout()
        facts.addWidget(self._fact("Client", product.get("client_name") or "Internal Use"), 0, 0)
        facts.addWidget(self._fact("AI policy", _AI_LABELS.get(product["ai_mode"], product["ai_mode"])), 0, 1)
        facts.addWidget(self._fact("Components", product.get("component_count", 0)), 1, 0)
        facts.addWidget(self._fact("Targets", ", ".join(t["target"] for t in product["targets"] if t["enabled"]) or "None"), 1, 1)
        layout.addLayout(facts)

        manifest_title = QLabel("Canonical Product Manifest")
        manifest_title.setStyleSheet("font-weight:650;margin-top:12px")
        layout.addWidget(manifest_title)
        manifest = QTextBrowser()
        manifest.setPlainText(json.dumps(store.manifest(product_id), indent=2, sort_keys=True))
        layout.addWidget(manifest, 1)

        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        close.clicked.connect(self.accept)
        layout.addWidget(close)

    @staticmethod
    def _fact(name, value):
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        label = QLabel(name)
        label.setObjectName("muted")
        layout.addWidget(label)
        strong = QLabel(str(value))
        strong.setStyleSheet("font-size:16px;font-weight:620")
        strong.setWordWrap(True)
        layout.addWidget(strong)
        return frame


class ProductsPanel(QWidget):
    """Owner-only Our Products catalogue backed by ProductStore."""

    def __init__(self, runtime=None, parent=None):
        super().__init__(parent)
        self.runtime = runtime or {}
        self.store = self.runtime.get("products") or ProductStore(settings.data_dir / "products.sqlite3")
        self.runtime.setdefault("products", self.store)
        self._metric_values = {}
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 16, 12, 12)
        root.setSpacing(12)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        title = QLabel("Our Products")
        title.setStyleSheet("font-size:30px;font-weight:700")
        titles.addWidget(title)
        subtitle = QLabel("Build, package, deploy and manage AI employees, agents, automations and client systems.")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        titles.addWidget(subtitle)
        head.addLayout(titles, 1)
        self.convert_button = QPushButton("Import / Convert from Project")
        self.convert_button.setObjectName("navAction")
        self.convert_button.clicked.connect(self._convert_project)
        head.addWidget(self.convert_button)
        create = QPushButton("＋  Create Product")
        create.setObjectName("navAction")
        create.clicked.connect(self._create_product)
        head.addWidget(create)
        root.addLayout(head)

        self.metrics = QGridLayout()
        for column, (key, label) in enumerate((
            ("total", "Total Products"),
            ("development", "In Development"),
            ("ready", "Ready to Deploy"),
            ("live", "Live / Deployed"),
            ("clients", "Clients"),
            ("needs_attention", "Needs Attention"),
        )):
            self.metrics.addWidget(self._metric(key, label), 0, column)
        root.addLayout(self.metrics)

        filters = QHBoxLayout()
        self.type_filter = QComboBox()
        self.type_filter.addItem("All products", "all")
        for item in ProductType:
            self.type_filter.addItem(_TYPE_LABELS[item.value], item.value)
        self.type_filter.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self.type_filter)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search products, clients, agents, workflows…")
        self.search.textChanged.connect(self.refresh)
        filters.addWidget(self.search, 1)
        self.sort = QComboBox()
        self.sort.addItem("Sort: Recent", "recent")
        self.sort.addItem("Sort: Name", "name")
        self.sort.addItem("Sort: Created", "created")
        self.sort.currentIndexChanged.connect(self.refresh)
        filters.addWidget(self.sort)
        root.addLayout(filters)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cards_host = QWidget()
        self.cards = QGridLayout(self.cards_host)
        self.cards.setContentsMargins(0, 0, 0, 0)
        self.cards.setSpacing(10)
        self.scroll.setWidget(self.cards_host)
        root.addWidget(self.scroll, 1)

        activity_title = QLabel("Recent Product Activity")
        activity_title.setStyleSheet("font-size:15px;font-weight:650")
        root.addWidget(activity_title)
        self.activity = QLabel("")
        self.activity.setObjectName("muted")
        self.activity.setWordWrap(True)
        root.addWidget(self.activity)

    def _metric(self, key, label):
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        value = QLabel("0")
        value.setStyleSheet("font-size:24px;font-weight:700")
        caption = QLabel(label)
        caption.setObjectName("muted")
        layout.addWidget(value)
        layout.addWidget(caption)
        self._metric_values[key] = value
        return frame

    def _clear_cards(self):
        while self.cards.count():
            item = self.cards.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def refresh(self, *_):
        summary = self.store.summary()
        for key, label in self._metric_values.items():
            label.setText(str(summary.get(key, 0)))

        rows = self.store.list(
            self.search.text() if hasattr(self, "search") else "",
            product_type=self.type_filter.currentData() if hasattr(self, "type_filter") else "all",
            sort=self.sort.currentData() if hasattr(self, "sort") else "recent",
        )
        self._clear_cards()
        if not rows:
            empty = QFrame()
            empty.setObjectName("card")
            box = QVBoxLayout(empty)
            title = QLabel("No products yet")
            title.setStyleSheet("font-size:20px;font-weight:650")
            box.addWidget(title)
            text = QLabel("Create a product from scratch or promote a completed Vishnu project when project conversion is available.")
            text.setObjectName("muted")
            text.setWordWrap(True)
            box.addWidget(text)
            self.cards.addWidget(empty, 0, 0, 1, 2)
        else:
            for index, product in enumerate(rows):
                self.cards.addWidget(self._product_card(product), index // 3, index % 3)

        activity = self.store.activity(limit=5)
        if activity:
            self.activity.setText("  •  ".join(
                f"{item.get('product_name') or 'Product'} — {item['message']}" for item in activity
            ))
        else:
            self.activity.setText("No product activity yet.")

    def _product_card(self, product):
        frame = QFrame()
        frame.setObjectName("card")
        frame.setMinimumHeight(250)
        layout = QVBoxLayout(frame)
        layout.setSpacing(7)

        row = QHBoxLayout()
        name = QLabel(product["name"])
        name.setStyleSheet("font-size:16px;font-weight:700")
        name.setWordWrap(True)
        row.addWidget(name, 1)
        status = QLabel(product["status"].replace("_", " ").title())
        status.setStyleSheet("padding:4px 8px;border:1px solid #294653;border-radius:9px")
        row.addWidget(status)
        layout.addLayout(row)

        kind = QLabel(_TYPE_LABELS.get(product["product_type"], product["product_type"]))
        kind.setObjectName("muted")
        layout.addWidget(kind)

        description = QLabel(product.get("description") or "No description yet.")
        description.setWordWrap(True)
        layout.addWidget(description)

        client = product.get("client_name") or "Internal Use"
        info = QLabel(f"Client  ·  {client}\nVersion  ·  {product['version']}\nComponents  ·  {product.get('component_count', 0)}")
        info.setObjectName("muted")
        layout.addWidget(info)

        target_names = [t["target"] for t in product.get("targets", []) if t.get("enabled")]
        targets = QLabel("Platforms  ·  " + ("  ·  ".join(target_names) if target_names else "Not selected"))
        targets.setWordWrap(True)
        layout.addWidget(targets)

        ai = QLabel(_AI_LABELS.get(product["ai_mode"], product["ai_mode"]))
        ai.setStyleSheet("padding:5px 8px;background:#0b1720;border-radius:8px;color:#a8d8ef")
        layout.addWidget(ai)
        layout.addStretch(1)

        actions = QHBoxLayout()
        open_button = QPushButton("Open")
        open_button.setObjectName("navAction")
        open_button.clicked.connect(lambda _checked=False, product_id=product["id"]: self._open_product(product_id))
        actions.addWidget(open_button)
        manifest_button = QPushButton("Manifest")
        manifest_button.clicked.connect(lambda _checked=False, product_id=product["id"]: self._show_manifest(product_id))
        actions.addWidget(manifest_button)
        layout.addLayout(actions)
        return frame

    def _create_product(self):
        dialog = CreateProductDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            product = self.store.create(**dialog.payload())
            self.refresh()
            self._open_product(product["id"])
        except ValueError as exc:
            QMessageBox.warning(self, "Create Product", str(exc))

    def _open_product(self, product_id):
        ProductDetailDialog(self.store, product_id, self).exec()
        self.refresh()

    def _show_manifest(self, product_id):
        product = self.store.get(product_id)
        if product:
            ProductDetailDialog(self.store, product_id, self).exec()

    def _convert_project(self):
        # Project authority differs across current Vishnu generations. Until a
        # single canonical project store is exposed to this surface, fail closed
        # rather than creating a detached/fake conversion.
        project_store = self.runtime.get("project_store")
        if project_store is None:
            QMessageBox.information(
                self,
                "Convert Project to Product",
                "Project conversion is waiting for the canonical project-store adapter. No project data was changed.",
            )
            return
        QMessageBox.information(
            self,
            "Convert Project to Product",
            "The project adapter is available. The selection flow is implemented in the next product-workspace tranche.",
        )
