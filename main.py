"""
Chess Claim Tool

Copyright (C) 2022 Serntedakis Athanasios <thanserd@hotmail.com>

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
import sys

from src.logging_setup import setup_logging, get_logger

""" Logging is configured before anything heavy is imported: a missing or
broken dependency raises at import time, long before the code below runs, and
a log that only starts afterwards cannot record it. Keep this block first. """
log_path = setup_logging()
logger = get_logger("main")

try:
    from src.controllers.ChessClaimController import ChessClaimController
    from src.views.ChessClaimView import ChessClaimView
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QIcon
    from src.helpers import resource_path
except Exception:
    logger.critical("startup imports failed - the app cannot launch", exc_info=True)
    raise

if __name__ == '__main__':
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)

    app = ChessClaimController()
    app.setStyle('fusion')
    app.setWindowIcon(QIcon(resource_path("logo.png")))

    css_path = "src/views/main.css"
    with open(resource_path(css_path), 'r') as css_file:
        css = css_file.read().replace('\n', '')
    app.setStyleSheet(css)

    view = ChessClaimView()
    app.set_view(view)

    app.do_start()

    """ Pin down who ends the session: a real window close fires closeEvent,
    lastWindowClosed means the window went away some other way, and aboutToQuit
    with neither of those means something called quit() directly."""
    app.lastWindowClosed.connect(lambda: logger.info("signal: lastWindowClosed"))
    app.aboutToQuit.connect(lambda: logger.info("signal: aboutToQuit"))
    logger.info("main window visible=%s geometry=%s",
                view.isVisible(), view.geometry().getRect())

    logger.info("entering Qt event loop")
    exit_code = app.exec_()
    logger.info("Qt event loop returned %s", exit_code)
    sys.exit(exit_code)
