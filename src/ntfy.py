"""
Chess Claim Tool: ntfy

Pushes claims to the arbiter's phone (and from there to their watch) through
ntfy - a pub/sub service where publishing is a single HTTP POST to a topic URL
and every subscribed device gets a notification.

The topic name is the only credential on the public server: anyone who knows it
can read the claims and publish to them. So a topic is generated at random the
first time rather than left to a guessable default.

Sending happens on a worker thread. A claim arrives on the GUI thread, and the
tournament network is known to stall mid-request - a synchronous POST there
would freeze the window for the duration of the timeout.

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
import json
import os
import secrets
import urllib.request
from urllib.error import HTTPError, URLError

from PyQt5.QtCore import QRunnable, QThreadPool

from src.DownloadPgn import get_ssl_context
from src.helpers import get_appdata_path
from src.logging_setup import get_logger

logger = get_logger("ntfy")

SETTINGS_FILENAME = "ntfy_settings.json"
DEFAULT_SERVER = "https://ntfy.sh"
SEND_TIMEOUT = 5


def generate_topic() -> str:
    """ A topic nobody else will land on by accident or by guessing. """
    return f"cct-{secrets.token_hex(6)}"


class NtfyConfig:
    """ Where to publish, and whether to publish at all. """

    __slots__ = ["enabled", "server", "topic"]

    def __init__(self, enabled: bool = False, server: str = DEFAULT_SERVER, topic: str = ""):
        self.enabled = enabled
        self.server = server.rstrip("/") or DEFAULT_SERVER
        self.topic = topic.strip() or generate_topic()

    @property
    def url(self) -> str:
        return f"{self.server}/{self.topic}"

    @classmethod
    def load(cls) -> "NtfyConfig":
        """ Read the saved config, falling back to a fresh disabled one. """
        path = os.path.join(get_appdata_path(), SETTINGS_FILENAME)
        try:
            with open(path) as f:
                data = json.load(f)
            return cls(
                enabled=bool(data.get("enabled", False)),
                server=str(data.get("server") or DEFAULT_SERVER),
                topic=str(data.get("topic") or ""),
            )
        except Exception:
            """ No file yet on first run, which is the normal case. """
            return cls()

    def save(self) -> None:
        path = os.path.join(get_appdata_path(), SETTINGS_FILENAME)
        try:
            with open(path, "w") as f:
                json.dump({"enabled": self.enabled, "server": self.server, "topic": self.topic},
                          f, indent=2)
        except Exception:
            logger.warning("could not save ntfy settings to %s", path, exc_info=True)


CLAIM_PRIORITY = "5"


def _publish(url: str, title: str, body: str, priority: str = CLAIM_PRIORITY,
             tags: str = "chess_pawn") -> None:
    """ POST one notification. Raises on failure; callers decide what that means.

    ntfy carries the title in a header, and headers are ASCII only, so anything
    outside it is stripped there. The body is sent as UTF-8 and keeps accents,
    which is where the player names go.

    Priority decides whether the phone interrupts. ntfy routes each priority to
    its own Android notification channel, and only 4 and 5 get a channel that
    pops up on screen with sound - 3 and below land silently in the drawer. An
    arbiter who has to open an app to find out about a claim has not been
    notified, so claims go out at 5.
    """
    request = urllib.request.Request(
        url,
        data=body.encode("utf-8"),
        headers={
            "Title": title.encode("ascii", "ignore").decode("ascii"),
            "Priority": priority,
            "Tags": tags,
        },
        method="POST",
    )
    urllib.request.urlopen(request, timeout=SEND_TIMEOUT, context=get_ssl_context()).read()


def send_test(config: NtfyConfig) -> str:
    """ Publish a test notification, synchronously, for the settings dialog.

    Sent at the same priority as a real claim: the point of the test is to show
    exactly how the phone will behave when a claim fires, and a quieter test
    would prove nothing about the case that matters.

    Returns:
        An empty string on success, otherwise a message fit to show the user.
    """
    try:
        _publish(config.url, "Chess Claim Tool",
                 "Test notification - this is how a claim will look.",
                 priority=CLAIM_PRIORITY, tags="white_check_mark")
    except HTTPError as error:
        return f"Server rejected the message (HTTP {error.code})."
    except URLError as error:
        return f"Could not reach {config.server} ({error.reason})."
    except Exception as error:
        logger.warning("ntfy test send failed", exc_info=True)
        return f"Send failed: {error}"

    logger.info("ntfy test sent to %s", config.url)
    return ""


class _SendClaim(QRunnable):
    """ One claim, published off the GUI thread. """

    def __init__(self, url: str, title: str, body: str):
        super().__init__()
        self.url = url
        self.title = title
        self.body = body

    def run(self):
        try:
            _publish(self.url, self.title, self.body)
        except Exception:
            """ Contained here on purpose. An exception escaping QRunnable.run()
            takes the process down, and a missed phone notification must never
            cost the arbiter the running scan."""
            logger.warning("ntfy send failed for %s", self.title, exc_info=True)


def send_claim(config: NtfyConfig, claim_type: str, players: str, move: str) -> None:
    """ Queue a claim for delivery. Returns immediately.

    Args:
        config: Where to publish, and whether to.
        claim_type: The kind of draw, used as the notification title.
        players: The names of the players.
        move: With which move the draw is valid.
    """
    if not config.enabled or not config.topic:
        return
    QThreadPool.globalInstance().start(_SendClaim(config.url, claim_type, f"{players}\n{move}"))
