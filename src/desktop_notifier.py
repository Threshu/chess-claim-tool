"""
Chess Claim Tool: Desktop notifications (Windows / macOS)

Desktop notifications are independent from ntfy:
- OS notifications should be shown for every detected claim (i.e. every entry
  that the app emits based on Claim Settings -> Claims).
- ntfy notifications are handled separately and follow the ntfy tab settings.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from typing import Optional

from src.logging_setup import get_logger

logger = get_logger("desktop_notifier")


@dataclass(frozen=True)
class DesktopNotification:
    title: str
    body: str


class DesktopNotifier:
    """Best-effort desktop notifier.

    On Windows uses `windows-toasts` if available.
    On macOS uses `MacNotification` if available.
    Other platforms: no-op.
    """

    def __init__(self, app_name: str = "Chess Claim Tool"):
        self._impl = _create_impl(app_name)

    def notify(self, notification: DesktopNotification) -> None:
        try:
            self._impl.notify(notification)
        except Exception:
            logger.warning("desktop notify failed", exc_info=True)


class _NotifierBase:
    def notify(self, notification: DesktopNotification) -> None:  # pragma: no cover
        raise NotImplementedError


class _NoopNotifier(_NotifierBase):
    def notify(self, notification: DesktopNotification) -> None:
        return


class _WindowsToastsNotifier(_NotifierBase):
    def __init__(self, app_name: str):
        try:
            # Windows-Toasts 1.x API:
            #   from windows_toasts import Toast, WindowsToaster
            from windows_toasts import Toast, WindowsToaster  # type: ignore

            self._Toast = Toast
            self._toaster = WindowsToaster(app_name)
        except Exception:
            # Missing dependency, unsupported OS version, etc.
            self._Toast = None
            self._toaster = None
            logger.info("Windows toast notifications unavailable (windows_toasts import failed)")

    def notify(self, notification: DesktopNotification) -> None:
        if not self._toaster or not self._Toast:
            return
        toast = self._Toast()
        # 1st field is the headline, 2nd is the body (common Windows toast layout).
        toast.text_fields = [notification.title, notification.body]
        self._toaster.show_toast(toast)


class _MacOsNotifier(_NotifierBase):
    def __init__(self):
        try:
            from src.MacNotification import Notification  # type: ignore

            self._center = Notification()
        except Exception:
            self._center = None
            logger.info("macOS notifications unavailable (pyobjc/MacNotification import failed)")

    def notify(self, notification: DesktopNotification) -> None:
        if not self._center:
            return
        # MacNotification supports (title, subtitle, text)
        self._center.notify(notification.title, "", notification.body)


def _create_impl(app_name: str) -> _NotifierBase:
    system = platform.system()
    if system == "Windows":
        return _WindowsToastsNotifier(app_name)
    if system == "Darwin":
        return _MacOsNotifier()
    return _NoopNotifier()

