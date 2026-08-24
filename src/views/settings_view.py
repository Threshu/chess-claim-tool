"""
Chess Claim Tool: Claim Settings Dialog
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QCheckBox,
    QPushButton, QLabel, QGroupBox, QLineEdit, QApplication,
)
from PyQt5.QtCore import Qt

from src.Claims import ClaimType
from src.ntfy import NtfyConfig, generate_topic, send_test

# Claims that are informational / low-priority
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


class ClaimSettingsDialog(QDialog):

    def __init__(self, enabled_claims: set, ntfy_config: NtfyConfig = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Claim Settings")
        self.setMinimumWidth(460)
        self.setWindowFlags(self.windowFlags() ^ Qt.WindowContextHelpButtonHint)

        self._checkboxes = {}
        self._ntfy_config = ntfy_config or NtfyConfig()
        self._build_ui(enabled_claims)

    def _build_ui(self, enabled_claims: set) -> None:
        layout = QVBoxLayout()

        intro = QLabel(
            "Select which claim types should be detected during scanning.\n"
            "Changes take effect on the next scan."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # Critical group (red)
        red_group = QGroupBox("Critical claims")
        red_layout = QVBoxLayout()

        # Informational group (orange)
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
        layout.addWidget(self._build_ntfy_group())

        # Buttons
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

    def _build_ntfy_group(self) -> QGroupBox:
        """ Phone/watch delivery: on/off, the topic, and a way to prove it works. """
        group = QGroupBox("Phone && watch notifications (ntfy)")
        group_layout = QVBoxLayout()

        self._ntfy_enabled = QCheckBox("Also send every claim to my phone")
        self._ntfy_enabled.setChecked(self._ntfy_config.enabled)
        group_layout.addWidget(self._ntfy_enabled)

        help_text = QLabel(
            "Install the ntfy app on your phone and subscribe to the topic below. "
            "The phone forwards the notification to a paired watch. Anyone who "
            "knows this topic can read your claims, so keep it private."
        )
        help_text.setWordWrap(True)
        group_layout.addWidget(help_text)

        topic_row = QHBoxLayout()
        topic_row.addWidget(QLabel("Topic:"))
        self._ntfy_topic = QLineEdit(self._ntfy_config.topic)
        topic_row.addWidget(self._ntfy_topic)

        btn_new = QPushButton("New")
        btn_new.setToolTip("Generate a fresh random topic")
        btn_new.clicked.connect(lambda: self._ntfy_topic.setText(generate_topic()))
        topic_row.addWidget(btn_new)

        btn_copy = QPushButton("Copy")
        btn_copy.setToolTip("Copy the topic so you can type it into the phone app")
        btn_copy.clicked.connect(self._copy_topic)
        topic_row.addWidget(btn_copy)
        group_layout.addLayout(topic_row)

        test_row = QHBoxLayout()
        btn_test = QPushButton("Send test notification")
        btn_test.clicked.connect(self._send_test)
        test_row.addWidget(btn_test)
        self._ntfy_result = QLabel("")
        self._ntfy_result.setWordWrap(True)
        test_row.addWidget(self._ntfy_result, 1)
        group_layout.addLayout(test_row)

        group.setLayout(group_layout)
        return group

    def _copy_topic(self) -> None:
        QApplication.clipboard().setText(self._ntfy_topic.text().strip())
        self._ntfy_result.setText("Topic copied.")
        self._ntfy_result.setStyleSheet("color: #006000;")

    def _send_test(self) -> None:
        """ Send now and report, so the arbiter is not left guessing.

        Deliberately synchronous: the point is the answer, and the dialog is
        modal anyway. The send has its own short timeout.
        """
        topic = self._ntfy_topic.text().strip()
        if not topic:
            self._ntfy_result.setText("Enter a topic first.")
            self._ntfy_result.setStyleSheet("color: #aa0000;")
            return

        self._ntfy_result.setText("Sending...")
        self._ntfy_result.setStyleSheet("color: #505050;")
        QApplication.processEvents()  # paint the label before we block

        error = send_test(NtfyConfig(enabled=True, server=self._ntfy_config.server, topic=topic))
        if error:
            self._ntfy_result.setText(error)
            self._ntfy_result.setStyleSheet("color: #aa0000;")
        else:
            self._ntfy_result.setText("Sent. Check your phone.")
            self._ntfy_result.setStyleSheet("color: #006000;")

    def get_enabled_claims(self) -> set:
        return {ct for ct, cb in self._checkboxes.items() if cb.isChecked()}

    def get_ntfy_config(self) -> NtfyConfig:
        return NtfyConfig(
            enabled=self._ntfy_enabled.isChecked(),
            server=self._ntfy_config.server,
            topic=self._ntfy_topic.text().strip(),
        )
