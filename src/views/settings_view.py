"""
Chess Claim Tool: Claim Settings Dialog
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QCheckBox,
    QPushButton, QLabel, QGroupBox,
)
from PyQt5.QtCore import Qt

from src.Claims import ClaimType

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

    def __init__(self, enabled_claims: set, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Claim Settings")
        self.setMinimumWidth(460)
        self.setWindowFlags(self.windowFlags() ^ Qt.WindowContextHelpButtonHint)

        self._checkboxes = {}
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

    def get_enabled_claims(self) -> set:
        return {ct for ct, cb in self._checkboxes.items() if cb.isChecked()}
