"""
Chess Claim Tool: Claim Settings Dialog
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QCheckBox,
    QPushButton, QLabel, QGroupBox, QLineEdit, QApplication,
    QTabWidget, QScrollArea, QWidget, QSlider, QFrame,
)
from PyQt5.QtCore import Qt

from src.Claims import ClaimType
from ntfy_notifier import DEFAULT_CONFIG
from src.ntfy import NtfyConfig, generate_topic, send_test, notification_rows

ORANGE_CLAIMS = {ClaimType.TWOFOLD, ClaimType.FIFTY_MOVES_FROM_START}

CLAIM_LABELS = {
    ClaimType.TWOFOLD:               "2 Fold Repetition  (early warning)",
    ClaimType.THREEFOLD:             "3 Fold Repetition  (player may claim draw)",
    ClaimType.FIVEFOLD:              "5 Fold Repetition  (arbiter must intervene)",
    ClaimType.FIFTY_MOVES:           "55 Moves Rule  (player may claim draw)",
    ClaimType.SEVENTYFIVE_MOVES:     "75 Moves Rule  (arbiter must intervene)",
    ClaimType.FIFTY_MOVES_FROM_START:"55 Moves from Start  (early warning)",
    ClaimType.EARLY_DRAW:            "Early Draw  (game ended before 30 moves)",
}

TEST_BOARD = "6"
TEST_WHITE = "Nowak Jan"
TEST_BLACK = "Kowalski Piotr"


def _preview(template: str, code: str, name: str) -> str:
    return (template
            .replace("{code}", code)
            .replace("{board}", TEST_BOARD)
            .replace("{white}", TEST_WHITE)
            .replace("{black}", TEST_BLACK)
            .replace("{name}", name))


class ClaimSettingsDialog(QDialog):

    def __init__(self, enabled_claims: set, ntfy_config: NtfyConfig = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Claim Settings")
        self.setMinimumSize(560, 640)
        self.setWindowFlags(self.windowFlags() ^ Qt.WindowContextHelpButtonHint)

        self._checkboxes = {}
        self._ntfy_rows = {}
        self._ntfy_config = ntfy_config or NtfyConfig()
        self._build_ui(enabled_claims)

    def _build_ui(self, enabled_claims: set) -> None:
        layout = QVBoxLayout()
        tabs = QTabWidget()
        tabs.addTab(self._build_claims_tab(enabled_claims), "Claims")
        tabs.addTab(self._build_ntfy_tab(), "ntfy")
        layout.addWidget(tabs)

        btn_row = QHBoxLayout()
        btn_ok     = QPushButton("OK")
        btn_cancel = QPushButton("Cancel")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(btn_ok)
        btn_row.addWidget(btn_cancel)
        layout.addLayout(btn_row)

        self.setLayout(layout)

    def _build_claims_tab(self, enabled_claims: set) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        intro = QLabel(
            "Select which claim types should be detected during scanning.\n"
            "Changes take effect on the next scan."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        red_group = QGroupBox("Critical claims")
        red_layout = QVBoxLayout()
        orange_group = QGroupBox("Informational / early warnings")
        orange_layout = QVBoxLayout()

        for ct in ClaimType:
            label = CLAIM_LABELS.get(ct, ct.value)
            cb = QCheckBox(label)
            cb.setChecked(ct in enabled_claims)

            if ct in ORANGE_CLAIMS:
                cb.setStyleSheet("color: #b05000;")
                orange_layout.addWidget(cb)
            else:
                cb.setStyleSheet("color: #aa0000;")
                red_layout.addWidget(cb)

            self._checkboxes[ct] = cb

        red_group.setLayout(red_layout)
        orange_group.setLayout(orange_layout)
        layout.addWidget(red_group)
        layout.addWidget(orange_group)
        layout.addStretch()
        return page

    def _build_ntfy_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        self._ntfy_enabled = QCheckBox("Send claims to ntfy (phone / watch)")
        self._ntfy_enabled.setChecked(self._ntfy_config.enabled)
        layout.addWidget(self._ntfy_enabled)

        help_text = QLabel(
            "Subscribe to the topic in the ntfy app. Notifications are text only "
            "(no icons). Placeholders: {code} {board} {white} {black} {name}"
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        server_row = QHBoxLayout()
        server_row.addWidget(QLabel("Server:"))
        self._ntfy_server = QLineEdit(self._ntfy_config.server)
        server_row.addWidget(self._ntfy_server)
        layout.addLayout(server_row)

        topic_row = QHBoxLayout()
        topic_row.addWidget(QLabel("Topic:"))
        self._ntfy_topic = QLineEdit(self._ntfy_config.topic)
        topic_row.addWidget(self._ntfy_topic)
        btn_new = QPushButton("New")
        btn_new.setToolTip("Generate a fresh random topic")
        btn_new.clicked.connect(lambda: self._ntfy_topic.setText(generate_topic()))
        topic_row.addWidget(btn_new)
        btn_copy = QPushButton("Copy")
        btn_copy.clicked.connect(self._copy_topic)
        topic_row.addWidget(btn_copy)
        layout.addLayout(topic_row)

        token_row = QHBoxLayout()
        token_row.addWidget(QLabel("Token:"))
        self._ntfy_token = QLineEdit(self._ntfy_config.token)
        self._ntfy_token.setEchoMode(QLineEdit.Password)
        self._ntfy_token.setPlaceholderText("Optional Bearer token")
        token_row.addWidget(self._ntfy_token)
        layout.addLayout(token_row)

        self._ntfy_result = QLabel("")
        self._ntfy_result.setWordWrap(True)
        layout.addWidget(self._ntfy_result)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        cards = QWidget()
        cards_layout = QVBoxLayout(cards)
        cards_layout.setContentsMargins(0, 0, 8, 0)

        for key, item in notification_rows(self._ntfy_config.notifier.config):
            cards_layout.addWidget(self._build_ntfy_card(key, item))

        cards_layout.addStretch()
        scroll.setWidget(cards)
        layout.addWidget(scroll, 1)
        return page

    def _build_ntfy_card(self, key: str, item: dict) -> QFrame:
        defaults = DEFAULT_CONFIG["notifications"].get(key, {})
        code = item.get("code") or defaults.get("code") or key.upper()
        name = item.get("name") or defaults.get("name") or code

        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        card = QVBoxLayout(frame)

        top = QHBoxLayout()
        enabled = QCheckBox(code)
        enabled.setChecked(bool(item.get("enabled", True)))
        top.addWidget(enabled)
        top.addStretch()
        btn_test = QPushButton("Test")
        top.addWidget(btn_test)
        card.addLayout(top)

        name_label = QLabel(name)
        name_label.setWordWrap(True)
        name_label.setStyleSheet("color: #555555; font-size: 11px;")
        card.addWidget(name_label)

        prio_row = QHBoxLayout()
        prio_row.addWidget(QLabel("Priority:"))
        slider = QSlider(Qt.Horizontal)
        slider.setRange(1, 5)
        slider.setValue(int(item.get("priority", 3) or 3))
        prio_value = QLabel(f"P{slider.value()}")
        slider.valueChanged.connect(lambda v, lbl=prio_value: lbl.setText(f"P{v}"))
        prio_row.addWidget(slider, 1)
        prio_row.addWidget(prio_value)
        card.addLayout(prio_row)

        title = QLineEdit(item.get("titleTemplate", "{code} #{board}"))
        body = QLineEdit(item.get("bodyTemplate", "{white} - {black}"))
        card.addWidget(QLabel("Title template"))
        card.addWidget(title)
        card.addWidget(QLabel("Body template"))
        card.addWidget(body)

        preview = QLabel()
        preview.setWordWrap(True)
        preview.setStyleSheet("color: #1a5276; background: #eaf2f8; padding: 6px;")
        card.addWidget(preview)

        def refresh_preview():
            preview.setText(
                f"{_preview(title.text(), code, name)}\n"
                f"{_preview(body.text(), code, name)}"
            )

        def set_enabled(on: bool):
            title.setEnabled(on)
            body.setEnabled(on)
            slider.setEnabled(on)
            btn_test.setEnabled(on)
            refresh_preview()

        title.textChanged.connect(lambda _: refresh_preview())
        body.textChanged.connect(lambda _: refresh_preview())
        enabled.toggled.connect(set_enabled)
        btn_test.clicked.connect(lambda _, k=key: self._send_row_test(k))
        set_enabled(enabled.isChecked())

        self._ntfy_rows[key] = {
            "code": code,
            "name": name,
            "enabled": enabled,
            "priority": slider,
            "title": title,
            "body": body,
        }
        return frame

    def _copy_topic(self) -> None:
        QApplication.clipboard().setText(self._ntfy_topic.text().strip())
        self._ntfy_result.setText("Topic copied.")
        self._ntfy_result.setStyleSheet("color: #006000;")

    def _connection_kwargs(self) -> dict:
        return {
            "server": self._ntfy_server.text().strip() or self._ntfy_config.server,
            "topic": self._ntfy_topic.text().strip(),
            "token": self._ntfy_token.text().strip(),
        }

    def _send_row_test(self, key: str) -> None:
        row = self._ntfy_rows[key]
        topic = self._ntfy_topic.text().strip()
        if not topic:
            self._ntfy_result.setText("Enter a topic first.")
            self._ntfy_result.setStyleSheet("color: #aa0000;")
            return

        self._ntfy_result.setText(f"Sending {row['code']}...")
        self._ntfy_result.setStyleSheet("color: #505050;")
        QApplication.processEvents()

        error = send_test(
            self._ntfy_config,
            claim_code=row["code"],
            title_template=row["title"].text(),
            body_template=row["body"].text(),
            priority=row["priority"].value(),
            **self._connection_kwargs(),
        )
        if error:
            self._ntfy_result.setText(error)
            self._ntfy_result.setStyleSheet("color: #aa0000;")
        else:
            self._ntfy_result.setText(f"Sent {row['code']}. Check your phone.")
            self._ntfy_result.setStyleSheet("color: #006000;")

    def get_enabled_claims(self) -> set:
        return {ct for ct, cb in self._checkboxes.items() if cb.isChecked()}

    def get_ntfy_config(self) -> NtfyConfig:
        cfg = NtfyConfig(
            enabled=self._ntfy_enabled.isChecked(),
            server=self._ntfy_server.text().strip() or self._ntfy_config.server,
            topic=self._ntfy_topic.text().strip(),
            token=self._ntfy_token.text().strip(),
            notifier=self._ntfy_config.notifier,
        )
        notifications = cfg.notifier.config.setdefault("notifications", {})
        for key, row in self._ntfy_rows.items():
            item = notifications.setdefault(key, {})
            item["code"] = row["code"]
            item["name"] = row["name"]
            item["enabled"] = row["enabled"].isChecked()
            item["priority"] = int(row["priority"].value())
            item["titleTemplate"] = row["title"].text()
            item["bodyTemplate"] = row["body"].text()
            item["tags"] = ""
        return cfg
