"""
Chess Claim Tool: ChessClaimView

Copyright (C) 2019 Serntedakis Athanasios <thanasis@brainfriz.com>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
import json
import os
import platform
from datetime import datetime
from typing import Optional, Callable

from PyQt5.QtCore import Qt, QSize, QEvent, QSortFilterProxyModel
from PyQt5.QtGui import QStandardItemModel, QPixmap, QMovie, QStandardItem, QColor
from PyQt5.QtWidgets import (QMainWindow, QWidget, QTreeView, QPushButton, QDesktopWidget,
                             QAbstractItemView, QHBoxLayout, QVBoxLayout, QLabel, QStatusBar, QMessageBox, QAction,
                             QDialog, QLineEdit, QMenu, QSpinBox)

from src.Claims import ClaimType
from src.helpers import resource_path, get_appdata_path, Status

if platform.system() == "Darwin":
    from src.MacNotification import Notification as Notification
elif platform.system() == "Windows":
    from win10toast import ToastNotifier as Notification


class ClaimsFilterProxy(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self._text = ""

    def set_filter(self, text: str) -> None:
        self._text = text.lower().strip()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:
        if not self._text:
            return True
        model = self.sourceModel()
        for col in (3, 4):  # Board, Players
            item = model.item(source_row, col)
            if item and self._text in item.text().lower():
                return True
        return False


def sources_warning():
    """ Displays a Warning Dialog. """
    warning_dialog = QMessageBox()
    warning_dialog.setIcon(warning_dialog.Warning)
    warning_dialog.setWindowTitle("Warning")
    warning_dialog.setText("PGN File(s) Not Found")
    warning_dialog.setInformativeText("Please enter at least one valid PGN source.")
    warning_dialog.exec()


class ChessClaimView(QMainWindow):
    ICON_SIZE = 16
    __slots__ = ["slots", "claims_table", "live_pgn_option", "claims_table_model", "proxy_model", "filter_edit",
                 "button_box", "ok_pixmap", "error_pixmap", "source_label", "source_image", "download_label",
                 "download_image", "scan_label", "scan_image", "spinner", "status_bar", "about_dialog", "notification"]

    def __init__(self) -> None:
        super().__init__()

        self.slots = None
        self.resize(720, 275)
        self.setWindowTitle('Chess Claim Tool')
        self.center()

        self.claims_table = QTreeView()
        self.live_pgn_option = QAction('Live PGN', self)
        self.claims_table_model = QStandardItemModel()
        self.proxy_model = ClaimsFilterProxy()
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter by player or board…")
        self.filter_edit.setObjectName("claimsFilter")
        self.button_box = ButtonBox()
        self.ok_pixmap = QPixmap(resource_path("check_icon.png"))
        self.error_pixmap = QPixmap(resource_path("error_icon.png"))
        self.source_label = QLabel()
        self.source_image = QLabel()
        self.download_label = QLabel()
        self.download_image = QLabel()
        self.scan_label = QLabel()
        self.scan_image = QLabel()
        self.spinner = QMovie(resource_path("spinner.gif"))
        self.status_bar = QStatusBar()
        self.about_dialog = AboutDialog()

        self.notification = Notification()

    def center(self) -> None:
        """ Centers the window on the screen """
        screen = QDesktopWidget().screenGeometry()
        size = self.geometry()
        self.move(int((screen.width() - size.width()) / 2),
                  int((screen.height() - size.height()) / 2))

    def set_gui(self) -> None:
        """ Initialize GUI components. """

        self.create_menu()
        self.create_claims_table()
        self.create_status_bar()

        self.button_box.set_scan_button_callback(self.slots.on_scan_button_clicked)
        self.button_box.set_stop_button_callback(self.slots.on_stop_button_clicked)
        self.button_box.set_board_button_callback(self.slots.on_board_viewer_clicked)
        self.button_box.set_settings_button_callback(self.slots.on_settings_clicked)

        self.filter_edit.textChanged.connect(self.proxy_model.set_filter)

        container_layout = QVBoxLayout()
        container_layout.setSpacing(0)
        container_layout.addWidget(self.claims_table)
        container_layout.addWidget(self.filter_edit)
        container_layout.addWidget(self.button_box)

        container_widget = QWidget()
        container_widget.setLayout(container_layout)

        self.setCentralWidget(container_widget)
        self.setStatusBar(self.status_bar)
        self._load_geometry()

    def create_menu(self) -> None:
        self.live_pgn_option.setCheckable(True)
        about_action = QAction('About', self)

        menu_bar = self.menuBar()

        options_menu = menu_bar.addMenu('&Options')
        options_menu.addAction(self.live_pgn_option)

        about_menu = menu_bar.addMenu('&Help')
        about_menu.addAction(about_action)
        about_action.triggered.connect(self.slots.on_about_clicked)

    def create_claims_table(self) -> None:
        from PyQt5.QtWidgets import QHeaderView

        self.claims_table.setFocusPolicy(Qt.NoFocus)
        self.claims_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.claims_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.claims_table.setSortingEnabled(True)
        self.claims_table.setIndentation(0)
        self.claims_table.setUniformRowHeights(True)

        labels = ["#", "Timestamp", "Type", "Board", "Players", "Move"]
        self.claims_table_model.setHorizontalHeaderLabels(labels)

        self.proxy_model.setSourceModel(self.claims_table_model)
        self.claims_table.setModel(self.proxy_model)
        self.claims_table.header().setDefaultAlignment(Qt.AlignCenter)

        self.claims_table.clicked.connect(self.on_claim_clicked)
        self.claims_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.claims_table.customContextMenuRequested.connect(self.on_table_context_menu)

        header = self.claims_table.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        header.setSectionResizeMode(5, QHeaderView.Stretch)
        self.claims_table.setColumnWidth(4, 400)
        header.setStretchLastSection(False)

    def create_status_bar(self) -> None:
        sources_button = QPushButton("Add Sources")
        sources_button.setObjectName("sources")
        sources_button.clicked.connect(self.slots.on_sources_button_clicked)

        self.source_image.setObjectName("source-image")
        self.download_image.setObjectName("download-image")
        self.scan_image.setObjectName("scan-image")

        self.spinner.setScaledSize(QSize(self.ICON_SIZE, self.ICON_SIZE))
        self.spinner.start()

        self.status_bar.setSizeGripEnabled(False)
        self.status_bar.addWidget(self.source_label)
        self.status_bar.addWidget(self.source_image)
        self.status_bar.addWidget(self.download_label)
        self.status_bar.addWidget(self.download_image)
        self.status_bar.addWidget(self.scan_label)
        self.status_bar.addWidget(self.scan_image)
        self.status_bar.addPermanentWidget(sources_button)
        self.status_bar.setContentsMargins(10, 5, 9, 5)

    def resize_claims_table(self) -> None:
        """ Resize the table (if needed) after the insertion of a new element. """
        for index in range(0, 6):
            self.claims_table.resizeColumnToContents(index)

    def set_slots(self, slots) -> None:
        """ Connect the Slots """
        self.slots = slots

    def add_item_to_table(self, entry) -> None:
        """Add new row to the claimsTable. entry is a ClaimEntry object."""
        claim_type = entry.type
        board_number = entry.board_number
        players = entry.players
        move = entry.move

        self.remove_rows_by_claim_type(claim_type, players)

        timestamp = str(datetime.now().strftime('%H:%M:%S'))
        count = str(self.claims_table_model.rowCount() + 1)
        items = [count, timestamp, claim_type.value, board_number, players, move]

        row = []
        for idx, item in enumerate(items):
            standard_item = self.create_standard_item(item, idx)
            row.append(standard_item)

        self.claims_table_model.insertRow(0, row)

        # Store game_index and move_index in the first column item for Board Viewer navigation
        first_item = self.claims_table_model.item(0, 0)
        first_item.setData(
            {"game_index": entry.game_index, "move_index": entry.move_counter},
            Qt.UserRole,
        )

        self.resize_claims_table()
        self.claims_table.scrollToTop()
        self.notify(claim_type, players, move)

    def on_claim_clicked(self, index) -> None:
        """Open Board Viewer at the correct game and move when a claim row is clicked."""
        source_index = self.proxy_model.mapToSource(index)
        first_col_item = self.claims_table_model.item(source_index.row(), 0)
        if first_col_item is None:
            return

        data = first_col_item.data(Qt.UserRole)
        if not data:
            return

        game_index = data.get("game_index")
        move_index = data.get("move_index")

        if game_index is None or move_index is None:
            return

        self.slots.open_viewer_for_claim(game_index, move_index)

    def on_table_context_menu(self, pos) -> None:
        selected_rows = {
            self.proxy_model.mapToSource(idx).row()
            for idx in self.claims_table.selectedIndexes()
            if idx.column() == 0
        }
        if not selected_rows:
            return

        handled_map = {
            r: bool(self.claims_table_model.item(r, 0) and
                    self.claims_table_model.item(r, 0).data(Qt.UserRole + 1))
            for r in selected_rows
        }
        has_unhandled = not all(handled_map.values())
        has_handled = any(handled_map.values())

        menu = QMenu(self)
        mark_action = menu.addAction("Mark as handled") if has_unhandled else None
        unmark_action = menu.addAction("Unmark") if has_handled else None

        chosen = menu.exec_(self.claims_table.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == mark_action:
            for row in selected_rows:
                if not handled_map[row]:
                    self.toggle_handled(row)
        elif chosen == unmark_action:
            for row in selected_rows:
                if handled_map[row]:
                    self.toggle_handled(row)

    def toggle_handled(self, row: int) -> None:
        first_item = self.claims_table_model.item(row, 0)
        if first_item is None:
            return
        marking = not bool(first_item.data(Qt.UserRole + 1))

        _ORANGE = {ClaimType.TWOFOLD.value, ClaimType.FIFTY_MOVES_FROM_START.value}
        _RED = {ClaimType.THREEFOLD.value, ClaimType.FIVEFOLD.value,
                ClaimType.FIFTY_MOVES.value, ClaimType.SEVENTYFIVE_MOVES.value,
                ClaimType.EARLY_DRAW.value}

        for col in range(self.claims_table_model.columnCount()):
            item = self.claims_table_model.item(row, col)
            if item is None:
                continue
            font = item.font()
            font.setStrikeOut(marking)
            item.setFont(font)
            if marking:
                item.setData(QColor(160, 160, 160), Qt.ForegroundRole)
            else:
                if col == 2:
                    text = item.text()
                    if text in _ORANGE:
                        item.setData(QColor(180, 80, 0), Qt.ForegroundRole)
                    elif text in _RED:
                        item.setData(QColor(180, 0, 0), Qt.ForegroundRole)
                    else:
                        item.setData(None, Qt.ForegroundRole)
                else:
                    item.setData(None, Qt.ForegroundRole)

        first_item.setData(marking, Qt.UserRole + 1)

    @staticmethod
    def create_standard_item(text: str, idx: int) -> QStandardItem:
        q_item = QStandardItem(text)
        q_item.setTextAlignment(Qt.AlignCenter)

        if idx == 2:
            font = q_item.font()
            font.setBold(True)
            q_item.setFont(font)
            # Colour claim type cell
            _ORANGE = {ClaimType.TWOFOLD.value, ClaimType.FIFTY_MOVES_FROM_START.value}
            _RED    = {ClaimType.THREEFOLD.value, ClaimType.FIVEFOLD.value,
                       ClaimType.FIFTY_MOVES.value, ClaimType.SEVENTYFIVE_MOVES.value,
                       ClaimType.EARLY_DRAW.value}
            if text in _ORANGE:
                q_item.setData(QColor(180, 80, 0), Qt.ForegroundRole)
            elif text in _RED:
                q_item.setData(QColor(180, 0, 0), Qt.ForegroundRole)

        return q_item

    def notify(self, claim_type: ClaimType, players: str, move: str) -> None:
        """ Send notification depending on the OS.
        Args:
            claim_type: The type of the draw (3 Fold Repetition, 5 Fold Repetition,
                                        50 Moves Rule, 75 Moves Rule).
            players: The names of the players.
            move: With which move the draw is valid.
        """
        if platform.system() == "Darwin":
            self.notification.clearNotifications()
            self.notification.notify(claim_type.value, players, move)
        elif platform.system() == "Windows":
            try:
                self.notification.show_toast(claim_type.value,
                                             f"{players} \n {move}",
                                             icon_path=resource_path("logo.ico"),
                                             duration=5,
                                             threaded=True)
            except Exception:
                pass

    def remove_row_by_index(self, index: int) -> None:
        """ Remove element from the claimsTable.
        Args:
            index: The index of the row we want to remove. First row has index=0.
        """
        self.claims_table_model.removeRow(index)

    def remove_rows_by_claim_type(self, claim_type: ClaimType, players: str) -> None:
        """ Removes a existing row from the Claims Table when same players made
        the same type of draw with a new move - or they made 5-Fold Repetition
        over the 3-Fold or 75 Moves Rule over 50 moves Rule.

        Args:
            claim_type: The type of the draw (3-Fold Repetition, 5-Fold Repetition,
                                        50 Moves Rule, 75 Moves Rule).
            players: The names of the players.
        """
        for index in range(self.claims_table_model.rowCount()):
            try:
                model_type = self.claims_table_model.item(index, 2).text()
                model_players = self.claims_table_model.item(index, 4).text()
            except AttributeError:
                model_type = ""
                model_players = ""

            if model_type == claim_type.value and model_players == players:
                self.remove_row_by_index(index)
                self.reset_column_count()
                break
            elif (claim_type is ClaimType.FIVEFOLD and
                  model_type == ClaimType.THREEFOLD.value and
                  model_players == players):
                self.remove_row_by_index(index)
                self.reset_column_count()
                break
            elif (claim_type is ClaimType.SEVENTYFIVE_MOVES and
                  model_type == ClaimType.FIFTY_MOVES.value and
                  model_players == players):
                self.remove_row_by_index(index)
                self.reset_column_count()
                break

    def reset_column_count(self) -> None:
        """Re-index the '#' column after row removal, preserving UserRole data."""
        row_count = self.claims_table_model.rowCount()
        for index in range(row_count):
            item = self.claims_table_model.item(index, 0)
            if item:
                item.setText(str(index + 1))

    def clear_table(self):
        """ Clear all the elements off the Claims Table. """
        for index in range(self.claims_table_model.rowCount()):
            self.claims_table_model.removeRow(0)

    def set_sources_status(self, status: Status, valid_sources: Optional[str] = None):
        """ Adds the sources in the statusBar.
        Args:
            status(str): The status of the validity of the sources.
                "ok": At least one source is valid.
                "error": None of the sources are valid.
            valid_sources(list): The list of valid sources, if there is any.
                This list is used here to display the ToolTip.
        """
        if valid_sources is None:
            valid_sources = []
        self.source_label.setText("Sources:")

        # Set the ToolTip if there are sources.
        try:
            text = ""
            for idx, source in enumerate(valid_sources):
                text += f"{idx + 1}) {source.get_value()}"
                if idx != len(valid_sources) - 1:
                    text += "\n"
            self.source_label.setToolTip(text)
        except TypeError:
            pass

        self.set_pixmap(self.source_image, status)

    def set_download_status(self, status: Status) -> None:
        """ Adds download status in the statusBar.
        Args:
            status(str): The status of the download(s).
                "ok": The download of the sources is successful.
                "error": The download of the sources failed.
                "stop": The download process stopped.
        """
        timestamp = str(datetime.now().strftime('%H:%M:%S'))
        self.download_label.setText(f"{timestamp} Download:")

        self.set_pixmap(self.download_image, status)

        if status is Status.STOP:
            self.download_image.clear()
            self.download_label.clear()

    def set_scan_status(self, status: Status) -> None:
        """ Adds the scan status in the statusBar. """
        timestamp = str(datetime.now().strftime('%H:%M:%S'))
        self.scan_label.setText(f"{timestamp} Scan:")
        self.set_pixmap(self.scan_image, status)

        if status is Status.ACTIVE:
            self.scan_image.clear()
            self.scan_image.setMovie(self.spinner)
        elif status is Status.STOP:
            self.scan_label.clear()
            self.scan_image.clear()

    def change_scan_button_text(self, status: Status) -> None:
        """ Changes the text of the scanButton depending on the status of the application.
        Args:
            status(str): The status of the scan process.
                "active": The scan process is active.
                "wait": The scan process is being terminated
                "stop": The scan process stopped.
        """
        if status is Status.ACTIVE:
            self.button_box.scan_button.setText("Scanning PGN...")
        elif status is Status.STOP:
            self.button_box.scan_button.setText("Start Scan")
        elif status is Status.WAIT:
            self.button_box.scan_button.setText("Please Wait")

    def set_pixmap(self, image: QLabel, status: Status):
        if status is Status.OK or status is Status.WAIT:
            image.setPixmap(
                self.ok_pixmap.scaled(self.ICON_SIZE, self.ICON_SIZE, transformMode=Qt.SmoothTransformation))
        elif status is Status.ERROR:
            image.setPixmap(
                self.error_pixmap.scaled(self.ICON_SIZE, self.ICON_SIZE, transformMode=Qt.SmoothTransformation))

    def enable_buttons(self):
        self.button_box.scan_button.setEnabled(True)
        self.button_box.stop_button.setEnabled(True)

    def disable_buttons(self):
        self.button_box.scan_button.setEnabled(False)
        self.button_box.stop_button.setEnabled(False)

    def enable_status_bar(self):
        """ Show download and scan status messages - if they were previously
        hidden (by disable_statusBar) - from the statusBar."""
        self.download_label.setVisible(True)
        self.scan_label.setVisible(True)
        self.download_image.setVisible(True)
        self.scan_image.setVisible(True)

    def disable_status_bar(self):
        """ Hide download and scan status messages from the statusBar. """
        self.download_label.setVisible(False)
        self.download_image.setVisible(False)
        self.scan_label.setVisible(False)
        self.scan_image.setVisible(False)

    def _geometry_path(self) -> str:
        return os.path.join(get_appdata_path(), "window_geometry.json")

    def _save_geometry(self) -> None:
        geo = self.geometry()
        try:
            with open(self._geometry_path(), "w") as f:
                json.dump({"x": geo.x(), "y": geo.y(),
                           "width": geo.width(), "height": geo.height()}, f)
        except Exception:
            pass

    def _load_geometry(self) -> None:
        try:
            with open(self._geometry_path()) as f:
                d = json.load(f)
            self.setGeometry(d["x"], d["y"], d["width"], d["height"])
        except Exception:
            pass

    def closeEvent(self, event: QEvent):
        """ Reimplement the close button
        If the program is actively scanning a pgn a warning dialog shall be raised
        in order to make sure that the user didn't clicked the close Button accidentally.
        Args:
            event: The exit QEvent.
        """
        self._save_geometry()
        try:
            if self.slots.scan_worker.is_running:
                exit_dialog = QMessageBox()
                exit_dialog.setWindowTitle("Warning")
                exit_dialog.setText("Scanning in Progress")
                exit_dialog.setInformativeText("Do you want to quit?")
                exit_dialog.setIcon(exit_dialog.Warning)
                exit_dialog.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
                exit_dialog.setDefaultButton(QMessageBox.Cancel)
                replay = exit_dialog.exec()

                if replay == QMessageBox.Yes:
                    event.accept()
                else:
                    event.ignore()
        except:
            event.accept()

    def load_about_dialog(self):
        """ Displays the About Dialog."""
        self.about_dialog.set_gui()
        self.about_dialog.show()


class ButtonBox(QWidget):
    __slots__ = ["scan_button", "stop_button", "board_button", "settings_button", "interval_spinbox"]

    def __init__(self):
        super().__init__()

        self.scan_button = QPushButton("Start Scan")
        self.scan_button.setObjectName("Scan")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("Stop")
        self.board_button = QPushButton("Board Viewer")
        self.board_button.setObjectName("BoardViewer")
        self.settings_button = QPushButton("Claim Settings")
        self.settings_button.setObjectName("Settings")

        self.interval_spinbox = QSpinBox()
        self.interval_spinbox.setRange(1, 60)
        self.interval_spinbox.setValue(2)
        self.interval_spinbox.setSuffix(" s")
        self.interval_spinbox.setToolTip("Scan interval in seconds")

        interval_label = QLabel("Interval:")

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 5, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(self.scan_button)
        layout.addWidget(self.stop_button)
        layout.addWidget(self.board_button)
        layout.addWidget(self.settings_button)
        layout.addStretch()
        layout.addWidget(interval_label)
        layout.addWidget(self.interval_spinbox)

        self.setLayout(layout)

    def set_scan_button_callback(self, on_clicked: Callable) -> None:
        self.scan_button.clicked.connect(on_clicked)

    def set_stop_button_callback(self, on_clicked: Callable) -> None:
        self.stop_button.clicked.connect(on_clicked)

    def set_board_button_callback(self, on_clicked: Callable) -> None:
        self.board_button.clicked.connect(on_clicked)

    def set_settings_button_callback(self, on_clicked: Callable) -> None:
        self.settings_button.clicked.connect(on_clicked)


class AboutDialog(QDialog):
    """ About dialog's GUI. """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("About")
        self.setWindowFlags(self.windowFlags() ^ Qt.WindowContextHelpButtonHint)

    def set_gui(self) -> None:
        """ Initialize GUI components. """

        # Create the logo
        logo = QLabel()
        logo_pixmap = QPixmap(resource_path("logo.png"))
        logo.setPixmap(logo_pixmap)

        # Create the information labels
        appname = QLabel("Chess Claim Tool")
        appname.setObjectName("appname")
        version = QLabel("Version 0.2.1")
        version.setObjectName("version")
        copyright = QLabel("Serntedakis Athanasios 2022 © All Rights Reserved")
        copyright.setObjectName("copyright")

        # Align All elements to the center.
        logo.setAlignment(Qt.AlignCenter)
        appname.setAlignment(Qt.AlignCenter)
        version.setAlignment(Qt.AlignCenter)
        copyright.setAlignment(Qt.AlignCenter)

        # Add all the above elements to layout.
        layout = QVBoxLayout()
        layout.addWidget(logo)
        layout.addWidget(appname)
        layout.addWidget(version)
        layout.addWidget(copyright)

        self.setLayout(layout)
