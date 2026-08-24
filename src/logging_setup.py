"""
Chess Claim Tool: logging_setup

Crash diagnostics for the app. Captures three classes of failure that
otherwise leave no trace when the app runs without a console (a built .exe):

  1. Unhandled Python exceptions on any thread. Under PyQt5 an exception that
     escapes a slot invoked from C++ terminates the process via qFatal(), so
     these show up to the user as "the app just disappeared".
  2. Fatal Qt messages (qFatal / failed Q_ASSERT), plus Qt warnings that
     normally go to a stderr nobody reads.
  3. Hard native crashes (access violations), via faulthandler.

Everything lands in ONE file, chess-claim-tool.log, sitting next to the
executable so it can be collected by just zipping the program folder. When the
program folder is read-only (an install under Program Files) it falls back to
the app data directory. The file never multiplies into .log.1/.log.2 backups:
once it hits the size cap the older half is dropped in place.

Also writes a session marker on start and a clean-exit marker via atexit, so a
log that ends without "session end" is by definition a crash.

Copyright (C) 2026 Chess Claim Tool contributors

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
import atexit
import faulthandler
import functools
import inspect
import logging
import logging.handlers
import os
import platform
import sys
import threading
from datetime import datetime

from src.helpers import get_appdata_path

LOGGER_NAME = "chess_claim_tool"
LOG_FILENAME = "chess-claim-tool.log"
_MAX_BYTES = 5 * 1024 * 1024

# Kept at module scope so the fd stays open for faulthandler's lifetime.
_native_crash_file = None
_is_configured = False


class SingleFileHandler(logging.handlers.BaseRotatingHandler):
    """ Size-capped handler that never produces a second file.

    RotatingFileHandler cannot do this: with backupCount=0 its doRollover()
    reopens the file in append mode and the log grows without bound, and with
    backupCount>0 it spawns .log.1, .log.2 and so on. Here the cap is enforced
    by dropping the oldest half of the file in place, which keeps recent
    history - the part that explains a crash - while the path stays constant.
    """

    def __init__(self, filename, max_bytes, encoding="utf-8"):
        super().__init__(filename, mode="a", encoding=encoding, delay=False)
        self.max_bytes = max_bytes

    def shouldRollover(self, record):
        if self.stream is None:
            self.stream = self._open()
        if self.max_bytes <= 0:
            return False
        self.stream.seek(0, os.SEEK_END)
        return self.stream.tell() + len(self.format(record)) >= self.max_bytes

    def doRollover(self):
        """ Halve the file in place, keeping the newest lines. """
        if self.stream:
            self.stream.close()
            self.stream = None
        try:
            with open(self.baseFilename, "rb") as f:
                f.seek(-(self.max_bytes // 2), os.SEEK_END)
                f.readline()  # discard the partial line we landed in
                tail = f.read()
            with open(self.baseFilename, "wb") as f:
                f.write(b"--- older entries dropped to keep a single capped log file ---\r\n")
                f.write(tail)
        except Exception:
            """ Diagnostics must never take the app down. Worst case the cap
            is not applied on this pass and we try again on the next record."""
            pass
        self.stream = self._open()


def _is_writable(directory: str) -> bool:
    """ Probe by actually writing: os.access lies on Windows. """
    probe = os.path.join(directory, ".write-test")
    try:
        os.makedirs(directory, exist_ok=True)
        with open(probe, "w") as f:
            f.write("")
        os.remove(probe)
        return True
    except Exception:
        return False


def get_log_dir() -> str:
    """ Directory holding the log file.

    Next to the executable, so collecting logs means zipping the program
    folder. Falls back to the app data directory when that is not writable,
    which is the normal case for an install under Program Files.
    """
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        # src/logging_setup.py -> the project root next to main.py
        exe_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if _is_writable(exe_dir):
        return exe_dir

    fallback = os.path.join(get_appdata_path(), "logs")
    os.makedirs(fallback, exist_ok=True)
    return fallback


def get_logger(name: str = None) -> logging.Logger:
    """ Return the app logger, or a child of it.

    Args:
        name: Optional child name, typically the module or class doing the logging.
    """
    if name:
        return logging.getLogger(f"{LOGGER_NAME}.{name}")
    return logging.getLogger(LOGGER_NAME)


def setup_logging(level: int = logging.INFO) -> str:
    """ Configure file logging and install every crash hook. Idempotent.

    Args:
        level: Logging level for the app logger.

    Returns:
        The path of the main log file.
    """
    global _native_crash_file, _is_configured

    log_dir = get_log_dir()
    log_path = os.path.join(log_dir, LOG_FILENAME)

    if _is_configured:
        return log_path

    logger = get_logger()
    logger.setLevel(level)
    logger.propagate = False

    file_handler = SingleFileHandler(log_path, max_bytes=_MAX_BYTES)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s [%(threadName)s] %(name)s: %(message)s"
    ))
    logger.addHandler(file_handler)

    # Only useful when launched from a terminal; harmless otherwise.
    if sys.stderr is not None:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(logging.Formatter("%(levelname)-8s %(name)s: %(message)s"))
        logger.addHandler(stream_handler)

    _install_python_excepthook()
    _install_thread_excepthook()
    _install_faulthandler(log_path)
    _install_qt_message_handler()
    atexit.register(_log_session_end)

    logger.info("=" * 70)
    logger.info("session start  %s", datetime.now().isoformat(timespec="seconds"))
    logger.info("python %s | %s %s", sys.version.split()[0], platform.system(), platform.release())
    logger.info("frozen=%s | log=%s", getattr(sys, "frozen", False), log_path)
    try:
        from PyQt5.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
        logger.info("Qt %s | PyQt %s", QT_VERSION_STR, PYQT_VERSION_STR)
    except Exception:  # pragma: no cover - diagnostics must never block startup
        pass

    _is_configured = True
    return log_path


def _install_python_excepthook() -> None:
    """ Route unhandled main-thread exceptions to the log.

    PyQt5 routes exceptions escaping a slot through sys.excepthook and then
    aborts the process, so this is the single most important hook here.
    """
    logger = get_logger("excepthook")
    previous_hook = sys.excepthook

    def handler(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            previous_hook(exc_type, exc_value, exc_traceback)
            return
        logger.critical(
            "UNHANDLED EXCEPTION - if this came from a Qt slot the process is about "
            "to be aborted by PyQt",
            exc_info=(exc_type, exc_value, exc_traceback),
        )
        _flush()
        previous_hook(exc_type, exc_value, exc_traceback)

    sys.excepthook = handler


def _install_thread_excepthook() -> None:
    """ Route unhandled exceptions on worker threads to the log. """
    logger = get_logger("thread")

    def handler(args):
        if issubclass(args.exc_type, SystemExit):
            return
        logger.critical(
            "UNHANDLED EXCEPTION in thread %s",
            getattr(args.thread, "name", "?"),
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )
        _flush()

    threading.excepthook = handler


def _install_faulthandler(log_path: str) -> None:
    """ Dump the native stack on a hard crash (access violation, abort).

    Writes into the same single log file through its own append-mode handle.
    faulthandler needs a real fd it can use from a signal handler, so it cannot
    go through logging. Append mode means every write lands at the current end
    of the file, so this stays correct even after the handler trims the log.
    """
    global _native_crash_file
    try:
        _native_crash_file = open(log_path, "a", encoding="utf-8")
        _native_crash_file.write(
            f"--- faulthandler armed {datetime.now().isoformat(timespec='seconds')} "
            f"(a native stack dump below this line means a hard crash) ---\n"
        )
        _native_crash_file.flush()
        faulthandler.enable(file=_native_crash_file, all_threads=True)
    except Exception:
        get_logger().warning("could not arm faulthandler", exc_info=True)


def _install_qt_message_handler() -> None:
    """ Route Qt's own diagnostics into the log, including fatal ones. """
    try:
        from PyQt5.QtCore import qInstallMessageHandler, QtMsgType
    except Exception:
        return

    logger = get_logger("qt")
    level_of = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def handler(mode, context, message):
        level = level_of.get(mode, logging.INFO)
        location = ""
        if context is not None and context.file:
            location = f" ({context.file}:{context.line})"
        logger.log(level, "%s%s", message, location)
        if level >= logging.CRITICAL:
            _flush()

    qInstallMessageHandler(handler)


def _log_session_end() -> None:
    """ Marker proving the process exited cleanly rather than crashing. """
    get_logger().info("session end (clean exit)")
    _flush()


def _flush() -> None:
    """ Force handlers to disk. A crashing process will not flush on its own. """
    for handler in get_logger().handlers:
        try:
            handler.flush()
        except Exception:
            pass


def log_exceptions(func):
    """ Decorator for Qt slots: log the traceback before PyQt aborts the process.

    Qt slots are called from C++, so an exception escaping one is not caught by
    any Python frame above it. Wrapping the slot means the failure is recorded
    with its arguments and the app stays alive.
    """
    logger = get_logger("slot")

    """ A slot is allowed to accept fewer arguments than its signal carries -
    Qt drops the extras - but PyQt decides how many to drop by reading the
    arity of whatever it was handed. Handed this wrapper it reads *args,
    concludes the slot takes everything, and drops nothing: clicked(bool)
    then reaches a self-only slot as a TypeError. So do the trimming here,
    exactly as PyQt would have done on the undecorated function."""
    code = getattr(func, "__code__", None)
    accepts_varargs = bool(code.co_flags & inspect.CO_VARARGS) if code else True
    max_positional = code.co_argcount if code else None

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not accepts_varargs and len(args) > max_positional:
            args = args[:max_positional]
        try:
            return func(*args, **kwargs)
        except Exception:
            logger.exception("exception in slot %s (swallowed to keep app alive)", func.__qualname__)
            _flush()
            return None

    return wrapper
