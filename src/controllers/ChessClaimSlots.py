"""
Chess Claim Tool: SourceDialogSlots

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
import os.path
import time
from threading import Lock
from typing import List

from src.views.ChessClaimView import sources_warning, ChessClaimView
from src.Claims import Claims, ClaimType
from src.controllers.SourceDialogController import SourceDialogController
from src.views.SourceDialogView import AddSourceDialog
from src.views.settings_view import ClaimSettingsDialog
from src.helpers import get_appdata_path, Status
from src.workers import DownloadGames, MakePgn, Scan, Stop
from src.board_viewer import BoardViewerWindow
from src.logging_setup import get_logger, log_exceptions

logger = get_logger("slots")


class ChessClaimSlots:
    """ Handles user interaction with the GUI of the Main Window. Each function
    is called when a specific action is performed by the user, to fulfill
    the request that corresponds to that action model and views wise.

    Attributes:
        model: Object of the Claims class.
        view:  The views of the Main Window.
    """

    def __init__(self, model: Claims, view: ChessClaimView) -> None:
        self.claims_model = model
        self.view = view
        self.sources_dialog = None

        self.make_pgn_worker = None
        self.stop_worker = None
        self.download_worker = None
        self.scan_worker = None
        self.board_viewer = None

        # Load and apply persisted claim settings
        self.claims_model.set_enabled_claims(self._load_claim_settings())

    def on_sources_button_clicked(self) -> None:
        """ Initialize the Source Dialog MVC model and opens the Source Dialog.

        trigger: User clicks the "Add Sources" Button on the Main Window.
        """
        if not self.sources_dialog:
            self.sources_dialog = SourceDialogController()
            dialog_view = AddSourceDialog()
            dialog_view.accepted.connect(self.update_status_bar_sources)

            self.sources_dialog.set_view(dialog_view)
            self.sources_dialog.do_start()
            return

        self.on_stop_button_clicked()
        self.sources_dialog.do_resume()

    def on_scan_button_clicked(self) -> None:
        """ Creates the necessary thread(workers) in order to scan the pgn(s)
        for the draw claims.

        trigger: User clicks the "Start Scan" Button on the Main Window.
        """
        if not self.sources_dialog or not self.sources_dialog.has_valid_sources():
            sources_warning()
            return

        """ If the scan thread is alive it means the scan button is already
        clicked before. So if the user click it again nothing should happen."""
        if self.scan_worker and self.scan_worker.is_running:
            return

        self.view.clear_table()
        self.view.change_scan_button_text(Status.WAIT)

        download_list = self.sources_dialog.get_download_list()
        if download_list:
            self.start_download_worker(download_list)

        games_pgn_mutex = Lock()
        self.start_make_png_worker(games_pgn_mutex)
        self.start_scan_worker(games_pgn_mutex)

    def on_stop_button_clicked(self) -> None:
        """ Creates a thread in order to stop all the other running Threads(
        downloadWorker, makePgnWorker,scanWorker)

        trigger: User clicks the "Stop" Button on the Main Window.
        """
        if self.scan_worker and not self.scan_worker.is_running:
            return

        if self.download_worker:
            self.stop_worker = Stop(self.claims_model, self.make_pgn_worker, self.scan_worker, self.download_worker)
        else:
            self.stop_worker = Stop(self.claims_model, self.make_pgn_worker, self.scan_worker)

        self.stop_worker.enable_signal.connect(self.on_stop_enable_status)
        self.stop_worker.disable_signal.connect(self.on_stop_disable_status)
        self.stop_worker.start()

    def on_about_clicked(self) -> None:
        """ Calls the views in order to display the About Dialog.
        trigger: User clicked the About section in the menu.
        """
        self.view.load_about_dialog()

    def on_settings_clicked(self) -> None:
        dialog = ClaimSettingsDialog(
            enabled_claims=self.claims_model.enabled_claims,
            parent=self.view,
        )
        if dialog.exec_() == ClaimSettingsDialog.Accepted:
            enabled = dialog.get_enabled_claims()
            self.claims_model.set_enabled_claims(enabled)
            self._save_claim_settings(enabled)

    def _load_claim_settings(self) -> set:
        path = os.path.join(get_appdata_path(), "claim_settings.json")
        try:
            with open(path) as f:
                data = json.load(f)
            return {ClaimType[k] for k, v in data.items() if v and k in ClaimType.__members__}
        except Exception:
            return set(ClaimType)  # all enabled by default

    def _save_claim_settings(self, enabled: set) -> None:
        path = os.path.join(get_appdata_path(), "claim_settings.json")
        data = {ct.name: (ct in enabled) for ct in ClaimType}
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    @log_exceptions
    def on_board_viewer_clicked(self) -> None:
        app_path = get_appdata_path()
        pgn_path = os.path.join(app_path, "games.pgn")

        if not os.path.exists(pgn_path):
            logger.warning("Board Viewer: %s does not exist yet", pgn_path)
            return

        if self.board_viewer is None:
            logger.info("Board Viewer: creating window from %s", pgn_path)
            self.board_viewer = BoardViewerWindow(pgn_path=pgn_path)
        else:
            self.board_viewer.reload_pgn(pgn_path)
            self.board_viewer.go_end()

        self.board_viewer.show()
        self.board_viewer.raise_()

    @log_exceptions
    def open_viewer_for_claim(self, game_index: int, move_index: int) -> None:
        app_path = get_appdata_path()
        pgn_path = os.path.join(app_path, "games.pgn")

        if self.board_viewer is None:
            if not os.path.exists(pgn_path):
                return
            self.board_viewer = BoardViewerWindow(pgn_path=pgn_path)
        else:
            self.board_viewer.reload_pgn(pgn_path)

        try:
            self.board_viewer.load_game_at_index(game_index)
            self.board_viewer.jump_to_move(move_index)
        except Exception:
            logger.exception("could not open viewer at game %s move %s", game_index, move_index)
            return

        self.board_viewer.show()
        self.board_viewer.raise_()

    @log_exceptions
    def on_new_move(self) -> None:
        """ Refresh the Board Viewer whenever games.pgn changes.

        Runs on every scan cycle the viewer is open for, and re-parses the whole
        pgn each time, so it is timed: if it outgrows the scan interval the GUI
        thread is the bottleneck.
        """
        if self.board_viewer is None:
            return

        app_path = get_appdata_path()
        pgn_path = os.path.join(app_path, "games.pgn")

        started_at = time.monotonic()
        self.board_viewer.reload_pgn(pgn_path)
        elapsed = time.monotonic() - started_at

        logger.debug("Board Viewer reload took %.2fs", elapsed)
        if elapsed > 1.0:
            logger.warning(
                "Board Viewer reload took %.2fs on the GUI thread - the window "
                "is unresponsive for that long on every scan cycle", elapsed,
            )

    def on_stop_disable_status(self) -> None:
        """ Disables the "Scan" & "Stop" Buttons and the statusBar.
        Also changes the status of the scanButton.

        trigger: By the disableSignal(pyqtSignal)
        """
        self.view.change_scan_button_text(Status.WAIT)
        self.view.disable_buttons()
        self.view.disable_status_bar()

    def on_stop_enable_status(self) -> None:
        """ Enables the "Scan" & "Stop" Buttons and the statusBar.
        Also changes the status of the scanButton, download and scan info at the
        statusBar.

        trigger: By the enableSignal(pyqtSignal)
        """
        self.view.change_scan_button_text(Status.STOP)
        self.update_download_status(Status.STOP)
        self.update_bar_scan_status(Status.STOP)

        self.view.enable_buttons()
        self.view.enable_status_bar()

    def update_status_bar_sources(self) -> None:
        valid_sources = self.sources_dialog.get_valid_sources()
        if valid_sources:
            self.view.set_sources_status(Status.OK, valid_sources)
        else:
            self.view.set_sources_status(Status.ERROR)

    @log_exceptions
    def update_claims_table(self, entry) -> None:
        logger.info("claim: %s | board %s | %s | move %s",
                    entry.type.name, entry.board_number, entry.players, entry.move)
        self.view.add_item_to_table(entry)

    def update_download_status(self, status: Status) -> None:
        self.view.set_download_status(status)

    def update_bar_scan_status(self, status: Status) -> None:
        self.view.set_scan_status(status)

    def start_download_worker(self, downloads: List[str]) -> None:
        if not downloads:
            return
        interval = self.view.button_box.interval_spinbox.value()
        self.download_worker = DownloadGames(downloads, True, interval)
        self.download_worker.status_signal.connect(self.update_download_status)
        self.download_worker.start()

    def start_make_png_worker(self, lock: Lock) -> None:
        filepaths = self.sources_dialog.get_filepath_list()
        interval = self.view.button_box.interval_spinbox.value()
        self.make_pgn_worker = MakePgn(filepaths, True, lock, interval)
        self.make_pgn_worker.start()

    def start_scan_worker(self, lock: Lock) -> None:
        app_path = get_appdata_path()
        filename = os.path.join(app_path, "games.pgn")
        interval = self.view.button_box.interval_spinbox.value()

        self.scan_worker = Scan(self.claims_model, filename, lock, self.view.live_pgn_option, interval)
        self.scan_worker.add_entry_signal.connect(self.update_claims_table)
        self.scan_worker.status_signal.connect(self.update_bar_scan_status)
        self.scan_worker.new_move_signal.connect(self.on_new_move)
        self.scan_worker.start()
