"""
Chess Claim Tool: ntfy

Publishes claims through ntfy using ntfy_notifier.py and ntfy_config.json
(generated from the configuration panel). Sending happens on a worker thread
so a stalled tournament network cannot freeze the window.

Copyright (C) 2026 Chess Claim Tool contributors

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
any later version.
"""
import os
import sys

from PyQt5.QtCore import QRunnable, QThreadPool

from ntfy_notifier import DEFAULT_CONFIG, NtfyNotifier
from src.Claims import ClaimType
from src.helpers import get_appdata_path
from src.logging_setup import get_logger

logger = get_logger("ntfy")

CONFIG_FILENAME = "ntfy_config.json"
LEGACY_SETTINGS_FILENAME = "ntfy_settings.json"
DEFAULT_SERVER = "https://ntfy.sh"

CLAIM_TYPE_TO_CODE = {
    ClaimType.THREEFOLD: "3FR",
    ClaimType.FIVEFOLD: "5FR",
    ClaimType.FIFTY_MOVES: "50M",
    ClaimType.SEVENTYFIVE_MOVES: "75M",
    ClaimType.FIFTY_MOVES_FROM_START: "55M",
    ClaimType.EARLY_DRAW: "AGR",
}


def generate_topic() -> str:
    import secrets
    return f"cct-{secrets.token_hex(6)}"


def _meipass() -> str:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return ""


def appdata_config_path() -> str:
    return os.path.join(get_appdata_path(), CONFIG_FILENAME)


def _candidate_config_paths():
    paths = [os.path.join(os.path.abspath("."), CONFIG_FILENAME)]
    if getattr(sys, "frozen", False):
        paths.append(os.path.join(os.path.dirname(sys.executable), CONFIG_FILENAME))
    paths.append(appdata_config_path())
    meipass = _meipass()
    if meipass:
        paths.append(os.path.join(meipass, CONFIG_FILENAME))
    seen = set()
    for path in paths:
        if path not in seen:
            seen.add(path)
            yield path


def _writable_config_path(loaded_from: str) -> str:
    meipass = _meipass()
    if meipass and loaded_from.startswith(meipass):
        return appdata_config_path()
    return loaded_from


def _ensure_config_file() -> str:
    """ Use the panel JSON next to the app when present; otherwise app data. """
    for path in _candidate_config_paths():
        if os.path.exists(path):
            return path

    os.makedirs(get_appdata_path(), exist_ok=True)
    path = appdata_config_path()
    notifier = NtfyNotifier(path)
    notifier.config = json_copy(DEFAULT_CONFIG)
    _merge_legacy_settings(notifier.config)
    notifier.save_config(path)
    return path


def json_copy(data):
    import json
    return json.loads(json.dumps(data))


def notification_rows(config: dict):
    """ Yield (id, item) in panel order, filling missing types from defaults. """
    notifications = config.setdefault("notifications", {})
    defaults = DEFAULT_CONFIG.get("notifications", {})
    seen = set()
    for key in defaults:
        item = notifications.get(key) or {}
        merged = json_copy(defaults[key])
        merged.update(item)
        merged["tags"] = ""
        notifications[key] = merged
        seen.add(key)
        yield key, merged
    for key, item in notifications.items():
        if key not in seen:
            item["tags"] = ""
            yield key, item


def _merge_legacy_settings(config: dict) -> None:
    legacy = os.path.join(get_appdata_path(), LEGACY_SETTINGS_FILENAME)
    try:
        import json
        with open(legacy, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return
    if "enabled" in data:
        config["enabled"] = bool(data["enabled"])
    if data.get("server"):
        config["serverUrl"] = str(data["server"]).rstrip("/")
    if data.get("topic"):
        config["topic"] = str(data["topic"]).strip()
    logger.info("migrated legacy ntfy_settings.json into ntfy_config.json")


class NtfyConfig:
    """ Facade over ntfy_config.json for the settings dialog. """

    def __init__(self, enabled: bool = True, server: str = DEFAULT_SERVER,
                 topic: str = "", token: str = "", notifier: NtfyNotifier = None):
        self._notifier = notifier or NtfyNotifier(_ensure_config_file())
        cfg = self._notifier.config
        cfg["enabled"] = enabled
        cfg["serverUrl"] = (server or DEFAULT_SERVER).rstrip("/")
        cfg["topic"] = (topic or "").strip()
        cfg["token"] = token if token is not None else cfg.get("token", "")

    @property
    def enabled(self) -> bool:
        return bool(self._notifier.config.get("enabled", True))

    @property
    def server(self) -> str:
        return str(self._notifier.config.get("serverUrl") or DEFAULT_SERVER).rstrip("/")

    @property
    def topic(self) -> str:
        return str(self._notifier.config.get("topic") or "").strip()

    @property
    def token(self) -> str:
        return str(self._notifier.config.get("token") or "")

    @property
    def notifier(self) -> NtfyNotifier:
        return self._notifier

    @classmethod
    def load(cls) -> "NtfyConfig":
        path = _ensure_config_file()
        notifier = NtfyNotifier(path)
        list(notification_rows(notifier.config))
        cfg = notifier.config
        return cls(
            enabled=bool(cfg.get("enabled", True)),
            server=str(cfg.get("serverUrl") or DEFAULT_SERVER),
            topic=str(cfg.get("topic") or ""),
            token=str(cfg.get("token") or ""),
            notifier=notifier,
        )

    def save(self) -> None:
        path = _writable_config_path(self._notifier.config_file)
        try:
            self._notifier.save_config(path)
            self._notifier.config_file = path
        except Exception:
            logger.warning("could not save ntfy config to %s", path, exc_info=True)


def send_test(config: NtfyConfig, server: str = None, topic: str = None,
              token: str = None, claim_code: str = "3FR",
              title_template: str = None, body_template: str = None,
              priority: int = None) -> str:
    """ Publish a test notification synchronously for the settings dialog. """
    temp = NtfyNotifier.__new__(NtfyNotifier)
    temp.config_file = config.notifier.config_file
    temp.config = json_copy(config.notifier.config)
    temp.config["enabled"] = True
    temp.config["serverUrl"] = (server or config.server or DEFAULT_SERVER).rstrip("/")
    temp.config["topic"] = (topic if topic is not None else config.topic).strip()
    temp.config["token"] = token if token is not None else config.token
    for item in temp.config.get("notifications", {}).values():
        if item.get("code") == claim_code:
            item["enabled"] = True
            if title_template is not None:
                item["titleTemplate"] = title_template
            if body_template is not None:
                item["bodyTemplate"] = body_template
            if priority is not None:
                item["priority"] = int(priority)
            break
    ok = temp.send_claim_notification(
        claim_code, 6, "Nowak Jan", "Kowalski Piotr", extra_data={"move": "test"}
    )
    if ok:
        logger.info("ntfy test sent to %s/%s", temp.config["serverUrl"], temp.config["topic"])
        return ""
    return "Send failed. Check server, topic, and token."


class _SendClaim(QRunnable):
    def __init__(self, notifier: NtfyNotifier, claim_code: str, board_num,
                 white: str, black: str, extra_data: dict):
        super().__init__()
        self.notifier = notifier
        self.claim_code = claim_code
        self.board_num = board_num
        self.white = white
        self.black = black
        self.extra_data = extra_data

    def run(self):
        try:
            self.notifier.send_claim_notification(
                self.claim_code, self.board_num, self.white, self.black, self.extra_data
            )
        except Exception:
            logger.warning("ntfy send failed for %s", self.claim_code, exc_info=True)


def _split_players(players: str):
    if " - " in players:
        white, black = players.split(" - ", 1)
        return white, black
    return players, ""


def send_claim(config: NtfyConfig, claim_type: ClaimType, board_number: str,
               players: str, move: str) -> None:
    """ Queue a claim for delivery. Returns immediately. """
    if not config.enabled or not config.topic:
        return
    code = CLAIM_TYPE_TO_CODE.get(claim_type)
    if not code:
        return
    white, black = _split_players(players)
    QThreadPool.globalInstance().start(_SendClaim(
        config.notifier, code, board_number, white, black, {"move": move}
    ))


def send_code(config: NtfyConfig, claim_code: str, board_num="",
              white_player="", black_player="", extra_data=None) -> None:
    """ Queue a named event (ERR_PGN, TIME, ...) for delivery. """
    if not config.enabled or not config.topic:
        return
    QThreadPool.globalInstance().start(_SendClaim(
        config.notifier, claim_code, board_num, white_player, black_player, extra_data or {}
    ))
